"""
60 FPS High-Performance CapCut-Style Subpixel Avatar Compositor.
Renders buttery-smooth 60.0 FPS keyframe animated presenter avatars
directly into FFmpeg hardware NVENC encoder with subpixel anti-aliasing.
"""

import os
import sys
import math
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

import cv2
import numpy as np

from modules.keyframe_engine import (
    KeyframeTrack,
    build_capcut_intro_track,
    build_capcut_outro_track
)

logger = logging.getLogger("ClipHub.AvatarAnimator")





def render_60fps_avatar_segment(
    input_video: str,
    freeze_t: float,
    audio_path: str,
    duration: float,
    out_file: str,
    avatar_path: str,
    is_intro: bool = False,
    crop_coords: Optional[Dict[str, Any]] = None,
    dynamic_crop_x: Optional[List[int]] = None,
    fps: float = 60.0,
    click_sfx_path: Optional[str] = None,
    use_nvenc: bool = True
) -> bool:
    """
    Renders a 60 FPS keyframe-animated avatar segment with CapCut easing and subpixel motion.
    Pipes 60.0 FPS raw frames directly into FFmpeg with zero dropped frames.
    """
    t_start = time.time()
    total_frames = max(1, int(round(duration * fps)))
    logger.info(f"[AvatarAnimator] 🎬 Rendering 60 FPS avatar segment: {total_frames} frames ({duration:.2f}s) -> {os.path.basename(out_file)}")

    # 1. Load avatar RGBA image
    if not avatar_path or not os.path.exists(avatar_path):
        logger.error(f"[AvatarAnimator] Avatar image not found: {avatar_path}")
        return False

    avatar_raw = cv2.imread(avatar_path, cv2.IMREAD_UNCHANGED)
    if avatar_raw is None:
        logger.error(f"[AvatarAnimator] Failed to read avatar image: {avatar_path}")
        return False

    # Ensure 4 channels (RGBA)
    if len(avatar_raw.shape) == 2:
        avatar_raw = cv2.cvtColor(avatar_raw, cv2.COLOR_GRAY2BGRA)
    elif avatar_raw.shape[2] == 3:
        avatar_raw = cv2.cvtColor(avatar_raw, cv2.COLOR_BGR2BGRA)

    av_h_orig, av_w_orig = avatar_raw.shape[:2]
    target_av_h = 1400
    target_av_w = int(round(av_w_orig * (target_av_h / av_h_orig)))
    if target_av_w > 1000:
        target_av_w = 932
        target_av_h = int(round(av_h_orig * (target_av_w / av_w_orig)))

    avatar_scaled = cv2.resize(avatar_raw, (target_av_w, target_av_h), interpolation=cv2.INTER_LANCZOS4)

    # 2. Extract and prepare background frame from source video
    bg_frame = _extract_and_prepare_background(
        input_video=input_video,
        freeze_t=freeze_t,
        crop_coords=crop_coords or {"crop_w": 1080, "crop_h": 1080, "crop_x": 0},
        dynamic_crop_x=dynamic_crop_x,
        is_intro=is_intro,
        fps=fps
    )

    # 3. Build CapCut keyframe track
    if is_intro:
        track = build_capcut_intro_track(duration=duration, w_av=target_av_w, h_av=target_av_h)
    else:
        track = build_capcut_outro_track(duration=duration, w_av=target_av_w, h_av=target_av_h)

    # 4. Prepare FFmpeg process with NVENC (or libx264 fallback)
    has_click = bool(click_sfx_path and os.path.exists(click_sfx_path))
    ffmpeg_cmd, pipe_idx = _build_ffmpeg_pipe_cmd(
        out_file=out_file,
        audio_path=audio_path,
        duration=duration,
        fps=fps,
        has_click=has_click,
        click_sfx_path=click_sfx_path,
        use_nvenc=use_nvenc
    )

    proc = None
    try:
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
    except Exception as e:
        logger.warning(f"[AvatarAnimator] NVENC pipe launch failed ({e}), falling back to libx264...")
        ffmpeg_cmd, pipe_idx = _build_ffmpeg_pipe_cmd(
            out_file=out_file,
            audio_path=audio_path,
            duration=duration,
            fps=fps,
            has_click=has_click,
            click_sfx_path=click_sfx_path,
            use_nvenc=False
        )
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )

    # 5. Render frames in 60.0 FPS subpixel loop
    w_canvas, h_canvas = 1080, 1920
    x_base = (w_canvas - target_av_w) / 2.0
    y_rest = (h_canvas - target_av_h) + 100.0
    anchor_x = target_av_w / 2.0
    anchor_y = target_av_h - 40.0 # Anchor near lower torso for natural pivot

    # Pre-split avatar channels for ultra-fast alpha compositing
    av_bgr = avatar_scaled[:, :, :3]
    av_alpha_orig = (avatar_scaled[:, :, 3].astype(np.float32) / 255.0)

    try:
        for i in range(total_frames):
            t_curr = i / fps
            state = track.evaluate(t_curr)

            # Construct Subpixel Affine Transformation Matrix
            scale_val = state.scale
            rot_val = state.rotation
            tx = x_base + state.x
            ty = y_rest + state.y

            # Rotation & scale around anchor point
            M = cv2.getRotationMatrix2D((anchor_x, anchor_y), -rot_val, scale_val)
            # Translation to canvas position
            M[0, 2] += (tx - (anchor_x * (scale_val - 1.0)))
            M[1, 2] += (ty - (anchor_y * (scale_val - 1.0)))

            # Transform BGR and Alpha channels with subpixel bilinear filtering
            warped_bgr = cv2.warpAffine(
                av_bgr, M, (w_canvas, h_canvas),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0)
            )
            
            effective_alpha = av_alpha_orig * state.opacity
            warped_alpha = cv2.warpAffine(
                effective_alpha, M, (w_canvas, h_canvas),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0.0
            )

            # Vectorized 3-channel alpha blend over background
            alpha_3d = np.expand_dims(warped_alpha, axis=2)
            frame_out = (bg_frame * (1.0 - alpha_3d) + warped_bgr * alpha_3d).astype(np.uint8)

            # Stream raw BGR24 frame directly to FFmpeg pipe
            proc.stdin.write(frame_out.tobytes())

        proc.stdin.close()
        stderr_output = proc.stderr.read().decode("utf-8", errors="ignore")
        proc.wait()

        if proc.returncode != 0:
            logger.error(f"[AvatarAnimator] FFmpeg returned error {proc.returncode}: {stderr_output}")
            return False

        logger.info(f"[AvatarAnimator] ✅ 60 FPS avatar segment completed in {time.time() - t_start:.2f}s ({total_frames} frames)")
        return True

    except Exception as e:
        logger.error(f"[AvatarAnimator] Frame rendering exception: {e}")
        if proc and proc.stdin:
            try: proc.stdin.close()
            except: pass
        if proc:
            try: proc.kill()
            except: pass
        return False


def _extract_and_prepare_background(
    input_video: str,
    freeze_t: float,
    crop_coords: Dict[str, Any],
    dynamic_crop_x: Optional[List[int]],
    is_intro: bool,
    fps: float
) -> np.ndarray:
    """
    Extracts a frame from input_video at freeze_t, applies crop, lanczos scale,
    cinematic background blur (18px) and darkening to produce a 1080x1920 canvas.
    """
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        logger.warning(f"[AvatarAnimator] Could not open video {input_video}, using clean dark background.")
        bg = np.zeros((1920, 1080, 3), dtype=np.uint8)
        bg[:, :] = (15, 16, 20)
        return bg

    v_fps = cap.get(cv2.CAP_PROP_FPS) or fps
    frame_idx = max(0, int(freeze_t * v_fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, raw_frame = cap.read()
    cap.release()

    if not ret or raw_frame is None:
        logger.warning(f"[AvatarAnimator] Failed to read frame at {freeze_t}s, using dark canvas.")
        bg = np.zeros((1920, 1080, 3), dtype=np.uint8)
        bg[:, :] = (15, 16, 20)
        return bg

    fh, fw = raw_frame.shape[:2]
    crop_w = crop_coords.get("crop_w", min(fw, fh))
    crop_h = crop_coords.get("crop_h", min(fw, fh))
    
    if is_intro and dynamic_crop_x and len(dynamic_crop_x) > 0:
        crop_x = dynamic_crop_x[0]
    elif dynamic_crop_x and len(dynamic_crop_x) > 0:
        d_idx = min(len(dynamic_crop_x) - 1, max(0, int(freeze_t * fps)))
        crop_x = dynamic_crop_x[d_idx]
    else:
        crop_x = crop_coords.get("crop_x", 0)

    crop_x = max(0, min(fw - crop_w, crop_x))
    cropped = raw_frame[0:crop_h, crop_x:crop_x + crop_w]

    # Scale cropped host to 1080x1080
    host_1080 = cv2.resize(cropped, (1080, 1080), interpolation=cv2.INTER_LANCZOS4)

    # Cinematic background blur & contrast adjustment
    blurred_host = cv2.GaussianBlur(host_1080, (41, 41), 18)
    # Slight contrast and brightness reduction
    blurred_host = cv2.convertScaleAbs(blurred_host, alpha=1.05, beta=-15)

    # Pad onto 1080x1920 vertical canvas
    canvas = np.zeros((1920, 1080, 3), dtype=np.uint8)
    canvas[420:1500, 0:1080] = blurred_host

    return canvas.astype(np.float32)


def _build_ffmpeg_pipe_cmd(
    out_file: str,
    audio_path: str,
    duration: float,
    fps: float,
    has_click: bool,
    click_sfx_path: Optional[str],
    use_nvenc: bool
) -> Tuple[List[str], int]:
    """
    Constructs FFmpeg pipeline command reading raw video frames from stdin.
    """
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", "1080x1920",
        "-pix_fmt", "bgr24",
        "-r", str(int(fps)),
        "-i", "-",
        "-i", audio_path
    ]

    inp_cnt = 2
    clk_idx = -1
    if has_click and click_sfx_path:
        cmd += ["-i", click_sfx_path]
        clk_idx = inp_cnt
        inp_cnt += 1

    # Audio mixing filter
    if has_click and clk_idx >= 0:
        filter_str = (
            f"[{clk_idx}:a]volume=0.30[clk];"
            f"[1:a][clk]amix=inputs=2:duration=first:dropout_transition=0,aformat=channel_layouts=stereo:sample_rates=48000,asetpts=PTS-STARTPTS[a]"
        )
        cmd += ["-filter_complex", filter_str, "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]

    # Video encoding
    if use_nvenc:
        enc_args = [
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", "19",
            "-b:v", "12M",
            "-maxrate", "18M",
            "-bufsize", "24M"
        ]
    else:
        enc_args = [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18"
        ]

    cmd += enc_args + [
        "-r", str(int(fps)),
        "-t", f"{duration:.3f}",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ac", "2",
        "-ar", "48000",
        "-pix_fmt", "yuv420p",
        out_file
    ]

    return cmd, 0

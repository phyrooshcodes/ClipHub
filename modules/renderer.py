# ============================================================
# renderer.py — Module 6: FFmpeg NVENC Final Renderer
# Hardware Target: GPU — NVENC ASIC Block (RTX 3050)
# Purpose: Encode the final 9:16 vertical clip with:
#          - Precise trim (ss/to)
#          - Face-tracked crop filter
#          - Burned-in ASS subtitle overlay
#          - Hardware-accelerated H.264 encoding via NVENC
#          GPU shader cores remain IDLE — only ASIC encodes.
# ============================================================

import subprocess
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ─── NVENC Encoding Defaults ─────────────────────────────────
NVENC_PRESET   = "p4"    # Balanced speed/quality (p1=fastest, p7=best quality)
NVENC_CQ       = "23"    # Constant Quality factor (18=near-lossless, 28=compressed)
AUDIO_BITRATE  = "192k"  # AAC audio quality
_nvenc_available: Optional[bool] = None


def render_clip(
    input_video:   str,
    output_path:   str,
    start_ms:      int,
    end_ms:        int,
    crop_coords:   Dict,
    subtitle_path: str,
    music_choice:  Optional[Dict[str, Any]] = None,
    clip_index:    int = 0,
    encoder:       str = "auto"
) -> str:
    """
    Render a final vertical clip using FFmpeg.
    Encoder auto-selects NVENC if available, or can be forced to "h264_nvenc" or "libx264".
    """
    import os
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    start_s = start_ms / 1000.0
    end_s   = end_ms   / 1000.0
    duration_s = end_s - start_s

    crop_w = crop_coords["crop_w"]
    crop_h = crop_coords["crop_h"]
    
    # Check if dynamic crop is available
    dynamic_crop_x = crop_coords.get("dynamic_crop_x", [])
    fps = crop_coords.get("fps", 30.0)
    use_dynamic = len(dynamic_crop_x) > 0

    # Proper path escaping for ASS filter (handles spaces, colons, quotes)
    import re, platform
    # Convert to forward slashes and escape special chars for FFmpeg filter strings
    rel_sub = os.path.relpath(subtitle_path).replace("\\", "/")
    # On Windows, escape colon in drive letter (e.g. C:/... → C\:/...)
    if platform.system() == "Windows":
        rel_sub = re.sub(r'^([A-Za-z]):', r'\1\\:', rel_sub)
    safe_sub_path = rel_sub.replace("'", "'\\''")

    command = [
        "ffmpeg", "-y",
        "-ss", f"{start_s:.3f}",
        "-t", f"{duration_s:.3f}",
        "-i", input_video,
    ]

    vf_filter = ""
    
    if use_dynamic:
        # Generate sendcmd text file
        sendcmd_path = output_path + ".sendcmd.txt"
        with open(sendcmd_path, "w") as f:
            for i, cx in enumerate(dynamic_crop_x):
                t_start = i / fps
                t_end = (i + 1) / fps
                # To crop dynamically using overlay: shift video left by cx on 9:16 canvas
                f.write(f"{t_start:.3f}-{t_end:.3f} [enter] overlay x {-cx};\n")
        
        # Add black canvas matching 9:16 crop aspect box
        command += ["-f", "lavfi", "-i", f"color=c=black:s={crop_w}x{crop_h}:r={fps}:d={duration_s:.3f}"]
        
        # Build a Windows-safe sendcmd path for FFmpeg
        sendcmd_ffmpeg = sendcmd_path.replace("\\", "/")
        import platform as _plat
        if _plat.system() == "Windows":
            sendcmd_ffmpeg = re.sub(r'^([A-Za-z]):', r'\1\\:', sendcmd_ffmpeg)
        
        # Filter complex: overlay video on 9:16 canvas, scale to 1080x1920 HD vertical, and add subtitles
        filter_complex = (
            f"[1:v]sendcmd=f='{sendcmd_ffmpeg}'[v_cmd]; "
            f"[v_cmd][0:v]overlay[over_out]; "
            f"[over_out]scale=1080:1920,"
            f"ass='{safe_sub_path}'[v_final]"
        )
    else:
        # Fallback to static crop
        crop_x = crop_coords.get("crop_x", 0)
        crop_y = 0
        vf_filter = (
            f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
            f"scale=1080:1920,"
            f"ass='{safe_sub_path}'"
        )

    if music_choice:
        import av
        has_audio = False
        try:
            with av.open(input_video) as container:
                has_audio = len(container.streams.audio) > 0
        except Exception:
            pass

        command += [
            "-stream_loop", "-1",
            "-ss", f"{float(music_choice['start_s']):.3f}",
            "-i", music_choice["path"],
        ]
        
        if use_dynamic:
            filter_complex += f"; " + _music_mix_filter(duration_s, has_audio)
            command += ["-filter_complex", filter_complex, "-map", "[v_final]", "-map", "[mixed_audio]"]
        else:
            command += [
                "-filter_complex", _music_mix_filter(duration_s, has_audio),
                "-map", "0:v:0",
                "-map", "[mixed_audio]",
            ]
    else:
        if use_dynamic:
            command += ["-filter_complex", filter_complex, "-map", "[v_final]", "-map", "0:a?"]
        else:
            command += ["-map", "0:v:0", "-map", "0:a?"]

    use_nvenc = check_nvenc_available() if encoder == "auto" else (encoder == "h264_nvenc")
    
    if use_nvenc:
        enc_args = ["-c:v", "h264_nvenc", "-preset", NVENC_PRESET, "-cq", NVENC_CQ, "-r", "60"]
    else:
        enc_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-r", "60"]

    if vf_filter:
        command += ["-vf", vf_filter]
        
    command += enc_args + [
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-shortest",
        output_path,
    ]

    logger.info(f"[Renderer] Rendering clip {clip_index + 1}: {output_path} (NVENC={use_nvenc})")
    
    try:
        _run_ffmpeg(command)
    except Exception as e:
        err_msg = str(e)
        if use_nvenc and ("nvenc" in err_msg.lower() or "encoder" in err_msg.lower() or "calledprocesserror" in err_msg.lower()):
            logger.warning("[Renderer] ⚠️ NVENC hardware encoder failed. Falling back to CPU encoder (libx264)...")
            return render_clip(
                input_video, output_path, start_ms, end_ms, crop_coords,
                subtitle_path, music_choice, clip_index, encoder="libx264"
            )
        else:
            raise e

    logger.info(f"[Renderer] ✅ Clip {clip_index + 1} rendered → {output_path}")
    return output_path


def _run_ffmpeg(command: list) -> None:
    """
    Execute an FFmpeg command and raise a detailed error if it fails.

    Args:
        command: List of command tokens.

    Raises:
        RuntimeError: On non-zero FFmpeg exit code.
    """
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"[Renderer] FFmpeg failed with exit code {e.returncode}.\n"
            f"Command: {' '.join(command)}\n"
            f"FFmpeg stderr:\n{stderr}"
        ) from e


def check_nvenc_available() -> bool:
    """
    Check whether NVENC (h264_nvenc) is available in this FFmpeg build.

    Returns:
        True if NVENC is available, False otherwise.
    """
    global _nvenc_available
    if _nvenc_available is not None:
        return _nvenc_available

    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        output = result.stdout.decode("utf-8", errors="ignore")
        available = "h264_nvenc" in output
        if available:
            # An encoder being listed does not guarantee that the installed
            # driver can initialise it. Test once so every clip does not first
            # suffer a slow, noisy NVENC failure before using the CPU fallback.
            probe = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=256x256:r=1",
                    "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            available = probe.returncode == 0
            if not available:
                detail = probe.stderr.decode("utf-8", errors="ignore").strip().splitlines()
                logger.warning(
                    "[Renderer] NVENC is listed but cannot start with this driver; using libx264. %s",
                    detail[-1] if detail else ""
                )
        if available:
            logger.info("[Renderer] ✅ h264_nvenc (NVENC) is available.")
        else:
            logger.warning(
                "[Renderer] ⚠️  h264_nvenc not found. "
                "Falling back to libx264 (CPU encoding)."
            )
        _nvenc_available = available
        return _nvenc_available
    except FileNotFoundError:
        logger.error("[Renderer] ❌ FFmpeg not found in PATH.")
        return False


def _music_mix_filter(clip_duration_s: float, has_audio: bool = True) -> str:
    """Return an exact-length, very quiet bed with automatic voice ducking."""
    duration = max(0.1, clip_duration_s)
    fade_in = min(0.8, duration / 3)
    fade_out = min(1.3, duration / 3)
    fade_out_start = max(0.0, duration - fade_out)

    if not has_audio:
        return (
            f"[1:a]aformat=channel_layouts=stereo,atrim=duration={duration:.3f},"
            f"asetpts=N/SR/TB,afade=t=in:st=0:d={fade_in:.3f},"
            f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f},"
            f"volume=0.035[mixed_audio]"
        )

    return (
        f"[1:a]aformat=channel_layouts=stereo,atrim=duration={duration:.3f},"
        f"asetpts=N/SR/TB,afade=t=in:st=0:d={fade_in:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f},"
        f"volume=0.035[bed];"
        f"[bed][0:a]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=300[ducked_bed];"
        f"[0:a][ducked_bed]amix=inputs=2:duration=first:normalize=0:dropout_transition=0,"
        f"alimiter=limit=0.95[mixed_audio]"
    )



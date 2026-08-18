# ============================================================
# face_tracker.py — Module 4: Face Tracking & Crop Calculation
# Purpose: High-precision face detection + 1-Euro Filter camera motion.
#          Zero GPU shader usage — pure CPU / DNN optimized graph.
# ============================================================

import os
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
import cv2
import numpy as np
import logging
import math
from pathlib import Path
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

TARGET_ASPECT_W = 1
TARGET_ASPECT_H = 1


class OneEuroFilter:
    """1-Euro Filter for sub-pixel, zero-jitter, buttery-smooth camera tracking."""
    def __init__(self, freq: float = 30.0, min_cutoff: float = 0.3, beta: float = 0.005, d_cutoff: float = 1.0):
        self.freq = float(freq)
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.x_prev = None
        self.dx_prev = None

    def _alpha(self, cutoff: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te = 1.0 / self.freq
        return 1.0 / (1.0 + tau / te)

    def filter(self, x: float) -> float:
        if self.x_prev is None:
            self.x_prev = x
            self.dx_prev = 0.0
            return x

        dx = (x - self.x_prev) * self.freq
        edx = self._alpha(self.d_cutoff) * dx + (1.0 - self._alpha(self.d_cutoff)) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(edx)
        a = self._alpha(cutoff)
        x_hat = a * x + (1.0 - a) * self.x_prev
        self.x_prev = x_hat
        self.dx_prev = edx
        return x_hat


import subprocess

_yunet_detector = None
_haar_cascade = None

def _get_detector(input_size: Tuple[int, int] = (640, 360)):
    """Returns (yunet_detector, haar_cascade). Prefers YuNet ONNX DNN face detector."""
    global _yunet_detector, _haar_cascade
    
    models_dir = Path(__file__).parent
    yunet_path = models_dir / "yunet.onnx"
    
    if not yunet_path.exists():
        url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
        try:
            import urllib.request, tempfile
            logger.info(f"[FaceTracker] Downloading YuNet DNN face model to {yunet_path}...")
            with urllib.request.urlopen(url, timeout=20) as resp:
                fd, tmp = tempfile.mkstemp(dir=str(models_dir))
                with os.fdopen(fd, 'wb') as f:
                    f.write(resp.read())
                os.replace(tmp, yunet_path)
            logger.info(f"[FaceTracker] YuNet DNN model ready!")
        except Exception as e:
            logger.warning(f"[FaceTracker] Could not download YuNet ONNX: {e}. Falling back to Haar Cascade.")

    if yunet_path.exists() and hasattr(cv2, "FaceDetectorYN"):
        try:
            detector = cv2.FaceDetectorYN.create(
                str(yunet_path), "", input_size,
                score_threshold=0.35, nms_threshold=0.3
            )
            return detector, None
        except Exception as e:
            logger.warning(f"[FaceTracker] Failed to init YuNet: {e}")

    # Fallback to Haar Cascade
    cascade_path = models_dir / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
        try:
            import urllib.request, tempfile
            with urllib.request.urlopen(url, timeout=20) as resp:
                fd, tmp = tempfile.mkstemp(dir=str(models_dir))
                with os.fdopen(fd, 'wb') as f:
                    f.write(resp.read())
                os.replace(tmp, cascade_path)
        except Exception as e:
            raise RuntimeError(f"Failed to download Haar cascade: {e}") from e

    cascade = cv2.CascadeClassifier(str(cascade_path))
    return None, cascade


def compute_crop_coords(
    input_video: str,
    start_ms: int,
    end_ms: int,
    smoothing_window: int = 15,
    sample_every_n_frames: int = 1,
    adaptive_sampling: bool = False,
    activity_threshold: float = 1.5,
) -> Dict:
    """
    Analyze video segment and compute buttery-smooth 9:16 vertical crop coordinates
    following the speaker's face using ultra-fast FFmpeg decoding + YuNet DNN + 1-Euro Filter.
    """
    # Probe source video dimensions and fps via OpenCV
    cap = cv2.VideoCapture(input_video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()

    if src_w <= 0 or src_h <= 0:
        src_w, src_h = 1920, 1080
    if fps <= 0 or not math.isfinite(fps):
        fps = 30.0

    # Calculate exact 1:1 square crop dimensions
    crop_h = min(src_h, src_w)
    crop_w = crop_h
    if crop_w % 2 != 0:
        crop_w -= 1
        crop_h -= 1

    start_s = max(0.0, start_ms / 1000.0)
    end_s = max(start_s + 1.0, end_ms / 1000.0)
    dur_s = end_s - start_s

    # Resize to 640x360 for 100x faster, robust DNN face detection
    scale_w = 640
    scale_h = max(180, int(640 * (src_h / float(src_w))))
    if scale_h % 2 != 0: scale_h += 1
    sample_fps = 4  # Sample 4 frames per second

    yunet, cascade = _get_detector(input_size=(scale_w, scale_h))

    logger.info(
        f"[FaceTracker] Source: {src_w}x{src_h} | "
        f"1:1 Square Crop: {crop_w}x{crop_h} at {fps:.2f}fps (YuNet={yunet is not None}, Range={start_s:.1f}s-{end_s:.1f}s)"
    )

    # Decode directly using FFmpeg pipe (instant multi-threaded seek & resize)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_s:.3f}",
        "-t", f"{dur_s:.3f}",
        "-i", input_video,
        "-vf", f"fps={sample_fps},scale={scale_w}:{scale_h}",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-"
    ]

    frame_size = scale_w * scale_h * 3
    sampled_xs = []
    face_detected = False
    frames_read = 0
    last_face_x = src_w / 2.0
    proc = None

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        while True:
            raw = proc.stdout.read(frame_size)
            if not raw or len(raw) < frame_size:
                break
            
            frame_arr = np.frombuffer(raw, dtype=np.uint8).reshape((scale_h, scale_w, 3))
            frames_read += 1

            if yunet:
                _, faces = yunet.detect(frame_arr)
                if faces is not None and len(faces) > 0:
                    face_detected = True
                    # Filter confident faces
                    valid_faces = [f for f in faces if len(f) <= 4 or f[4] >= 0.30]
                    if not valid_faces:
                        valid_faces = faces
                    
                    if len(valid_faces) == 1:
                        fx, fy, fw, fh = valid_faces[0][:4]
                        orig_cx = (fx + fw / 2.0) * (src_w / float(scale_w))
                        last_face_x = orig_cx
                    else:
                        # Multi-person scene: check if conversation group fits in 1:1 window
                        min_fx = min(f[0] for f in valid_faces)
                        max_fx = max(f[0] + f[2] for f in valid_faces)
                        span_orig = (max_fx - min_fx) * (src_w / float(scale_w))
                        if span_orig <= crop_w:
                            # Both/all people fit inside 1:1 crop! Center on group midpoint
                            orig_cx = ((min_fx + max_fx) / 2.0) * (src_w / float(scale_w))
                            last_face_x = orig_cx
                        else:
                            # Group is wider than crop -> track largest/primary speaker
                            sorted_faces = sorted(valid_faces, key=lambda f: f[2] * f[3], reverse=True)
                            fx, fy, fw, fh = sorted_faces[0][:4]
                            orig_cx = (fx + fw / 2.0) * (src_w / float(scale_w))
                            last_face_x = orig_cx
            elif cascade:
                gray = cv2.cvtColor(frame_arr, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(30, 30))
                if len(faces) > 0:
                    face_detected = True
                    if len(faces) == 1:
                        fx, fy, fw, fh = faces[0]
                        orig_cx = (fx + fw / 2.0) * (src_w / float(scale_w))
                        last_face_x = orig_cx
                    else:
                        min_fx = min(f[0] for f in faces)
                        max_fx = max(f[0] + f[2] for f in faces)
                        span_orig = (max_fx - min_fx) * (src_w / float(scale_w))
                        if span_orig <= crop_w:
                            orig_cx = ((min_fx + max_fx) / 2.0) * (src_w / float(scale_w))
                            last_face_x = orig_cx
                        else:
                            sorted_faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                            fx, fy, fw, fh = sorted_faces[0]
                            orig_cx = (fx + fw / 2.0) * (src_w / float(scale_w))
                            last_face_x = orig_cx

            sampled_xs.append(last_face_x)
    except Exception as e:
        logger.warning(f"[FaceTracker] FFmpeg face pipe failed: {e}")
    finally:
        if proc:
            try:
                if proc.stdout:
                    proc.stdout.close()
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    total_output_frames = max(1, int(dur_s * fps))

    # ─── 1-Euro Filter Cinematic Motion Smoothing ──────────────────
    dynamic_crop_x = []
    if not face_detected or len(sampled_xs) == 0:
        logger.warning("[FaceTracker] No face detected — using static center 9:16 crop.")
        static_x = max(0, (src_w - crop_w) // 2)
        dynamic_crop_x = [static_x] * total_output_frames
    else:
        # Interpolate sampled_xs to full framerate
        if len(sampled_xs) == 1:
            full_xs = [sampled_xs[0]] * total_output_frames
        else:
            sample_t = np.linspace(0, 1, len(sampled_xs))
            full_t = np.linspace(0, 1, total_output_frames)
            full_xs = np.interp(full_t, sample_t, sampled_xs)

        # Pre-smooth with Gaussian window
        try:
            from scipy.ndimage import gaussian_filter1d
            raw_smoothed = gaussian_filter1d(full_xs, sigma=10.0, mode='nearest')
        except ImportError:
            raw_smoothed = full_xs

        euro_filter = OneEuroFilter(freq=fps, min_cutoff=0.20, beta=0.005)
        deadband_px = max(18.0, src_w * 0.04)
        last_anchor_x = float(raw_smoothed[0])

        for raw_x in raw_smoothed:
            if abs(raw_x - last_anchor_x) > deadband_px:
                last_anchor_x = last_anchor_x + 0.25 * (raw_x - last_anchor_x)
            
            smooth_center_x = euro_filter.filter(float(last_anchor_x))
            cx = int(round(smooth_center_x - crop_w / 2.0))
            cx = max(0, min(cx, src_w - crop_w))
            dynamic_crop_x.append(cx)

    static_crop_x = int(np.median(dynamic_crop_x)) if len(dynamic_crop_x) > 0 else max(0, (src_w - crop_w) // 2)

    logger.info(
        f"[FaceTracker] Face detected: {face_detected} | "
        f"Generated {len(dynamic_crop_x)} dynamic crop positions (Static Crop X: {static_crop_x}px)."
    )

    return {
        "crop_w":        crop_w,
        "crop_h":        crop_h,
        "crop_x":        static_crop_x,
        "dynamic_crop_x": dynamic_crop_x,
        "fps":           fps,
        "src_w":         src_w,
        "src_h":         src_h,
        "face_detected": face_detected
    }

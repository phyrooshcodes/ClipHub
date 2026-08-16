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

TARGET_ASPECT_W = 9
TARGET_ASPECT_H = 16


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


_yunet_detector = None
_haar_cascade = None

def _get_detector():
    """Returns (yunet_detector, haar_cascade). Prefers YuNet ONNX DNN face detector."""
    global _yunet_detector, _haar_cascade
    if _yunet_detector is not None or _haar_cascade is not None:
        return _yunet_detector, _haar_cascade

    import urllib.request, os, tempfile
    models_dir = Path(__file__).parent
    yunet_path = models_dir / "yunet.onnx"
    
    if not yunet_path.exists():
        url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
        try:
            logger.info(f"[FaceTracker] Downloading YuNet DNN face model to {yunet_path}...")
            with urllib.request.urlopen(url, timeout=20) as resp:
                fd, tmp = tempfile.mkstemp(dir=str(models_dir))
                with os.fdopen(fd, 'wb') as f:
                    f.write(resp.read())
                os.replace(tmp, yunet_path)
            logger.info(f"[FaceTracker] ✅ YuNet DNN model ready!")
        except Exception as e:
            logger.warning(f"[FaceTracker] Could not download YuNet ONNX: {e}. Falling back to Haar Cascade.")

    if yunet_path.exists() and hasattr(cv2, "FaceDetectorYN"):
        try:
            _yunet_detector = cv2.FaceDetectorYN.create(str(yunet_path), "", (320, 320), score_threshold=0.6, nms_threshold=0.3)
            logger.info("[FaceTracker] ✅ Initialized YuNet DNN face detector.")
            return _yunet_detector, None
        except Exception as e:
            logger.warning(f"[FaceTracker] Failed to init YuNet: {e}")

    # Fallback to Haar Cascade
    cascade_path = models_dir / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                fd, tmp = tempfile.mkstemp(dir=str(models_dir))
                with os.fdopen(fd, 'wb') as f:
                    f.write(resp.read())
                os.replace(tmp, cascade_path)
        except Exception as e:
            raise RuntimeError(f"Failed to download Haar cascade: {e}") from e

    _haar_cascade = cv2.CascadeClassifier(str(cascade_path))
    return None, _haar_cascade


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
    following the speaker's face using YuNet DNN + 1-Euro Filter.
    """
    yunet, cascade = _get_detector()

    import av
    container = av.open(input_video)
    video_stream = container.streams.video[0]
    
    fps = float(video_stream.average_rate) or 30.0
    src_w = video_stream.width
    src_h = video_stream.height

    # Calculate exact 9:16 crop width based on source height
    crop_h = src_h
    crop_w = int(src_h * (9.0 / 16.0))
    if crop_w % 2 != 0: crop_w += 1
    if crop_w > src_w:
        crop_w = src_w
        crop_h = min(src_h, int(src_w * (16.0 / 9.0)))
        if crop_h % 2 != 0: crop_h -= 1

    logger.info(
        f"[FaceTracker] Source: {src_w}x{src_h} | "
        f"9:16 Vertical Crop: {crop_w}x{crop_h} at {fps:.2f}fps (YuNet={yunet is not None})"
    )

    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    tb = video_stream.time_base or (1.0 / fps)
    seek_ts = int(start_s / tb)
    try:
        container.seek(seek_ts, stream=video_stream)
    except Exception:
        pass

    sampled_frames = []
    sampled_xs = []
    
    face_detected = False
    frames_read = 0

    # Default center fallback
    last_face_x = src_w / 2.0

    sample_step = max(1, int(sample_every_n_frames))
    frame_idx = 0

    if yunet:
        yunet.setInputSize((src_w, src_h))

    for frame in container.decode(video=0):
        t = frame.time
        if t is not None:
            if t < start_s:
                continue
            if t > end_s:
                break

        # Only run DNN face detection on sampled frames for performance
        if frame_idx % sample_step == 0:
            img = frame.to_ndarray(format="bgr24")
            if yunet:
                _, faces = yunet.detect(img)
                if faces is not None and len(faces) > 0:
                    face_detected = True
                    # Sort by area (largest face)
                    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                    fx, fy, fw, fh = faces[0][:4]
                    last_face_x = fx + (fw / 2.0)
            else:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(50, 50))
                if len(faces) > 0:
                    face_detected = True
                    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                    fx, fy, fw, fh = faces[0]
                    last_face_x = fx + (fw / 2.0)

        sampled_frames.append(frames_read)
        sampled_xs.append(last_face_x)
        frames_read += 1
        frame_idx += 1

    container.close()

    if frames_read == 0:
        frames_read = 1
        sampled_frames = [0]
        sampled_xs = [last_face_x]

    # ─── 1-Euro Filter Cinematic Motion Smoothing ──────────────────
    dynamic_crop_x = []
    if not face_detected or len(sampled_xs) == 0:
        logger.warning("[FaceTracker] No face detected — using static center 9:16 crop.")
        static_x = max(0, (src_w - crop_w) // 2)
        dynamic_crop_x = [static_x] * frames_read
    else:
        # Initialize 1-Euro Filter for buttery smooth sub-pixel tracking
        euro_filter = OneEuroFilter(freq=fps, min_cutoff=0.25, beta=0.005)
        
        # Pre-smooth raw detections with Gaussian window (sigma=5) to eliminate single-frame glitches
        try:
            from scipy.ndimage import gaussian_filter1d
            raw_smoothed = gaussian_filter1d(sampled_xs, sigma=5.0, mode='nearest')
        except ImportError:
            raw_smoothed = sampled_xs

        # Apply deadband window (4% of width) so micro-head-movements keep camera rock-solid
        deadband_px = max(15.0, src_w * 0.04)
        last_anchor_x = float(raw_smoothed[0]) if len(raw_smoothed) > 0 else (src_w / 2.0)

        for raw_x in raw_smoothed:
            if abs(raw_x - last_anchor_x) > deadband_px:
                # Smoothly shift the anchor towards the new face position
                last_anchor_x = last_anchor_x + 0.3 * (raw_x - last_anchor_x)
            
            smooth_center_x = euro_filter.filter(float(last_anchor_x))
            cx = int(round(smooth_center_x - crop_w / 2.0))
            cx = max(0, min(cx, src_w - crop_w))
            dynamic_crop_x.append(cx)

    static_crop_x = int(np.median(dynamic_crop_x)) if len(dynamic_crop_x) > 0 else max(0, (src_w - crop_w) // 2)

    logger.info(
        f"[FaceTracker] ✅ Face detected: {face_detected} | "
        f"Generated {len(dynamic_crop_x)} dynamic crop positions (1-Euro Filter smooth, sample_step={sample_step})."
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

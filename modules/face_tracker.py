# ============================================================
# face_tracker.py — Module 4: Face Tracking & Crop Calculation
# Hardware Target: CPU — Google MediaPipe
# Purpose: Detect the speaker's face frame-by-frame and
#          compute a smooth 9:16 vertical crop window.
#          Zero GPU shader usage — pure CPU optimized graph.
# ============================================================

import cv2
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

TARGET_ASPECT_W = 9
TARGET_ASPECT_H = 16

_global_face_cascade = None

def _get_cascade():
    global _global_face_cascade
    if _global_face_cascade is not None:
        return _global_face_cascade

    from pathlib import Path
    import urllib.request
    import os
    import tempfile
    
    cascade_path = Path(__file__).parent / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        logger.info(f"[FaceTracker] Cascade file not found locally. Downloading from official OpenCV GitHub...")
        url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                fd, tmp_path = tempfile.mkstemp(dir=str(cascade_path.parent))
                with os.fdopen(fd, 'wb') as f:
                    f.write(response.read())
                os.replace(tmp_path, cascade_path)
            logger.info(f"[FaceTracker] Successfully downloaded cascade file to: {cascade_path}")
        except Exception as e:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"[FaceTracker] Failed to download Haar Cascade XML from {url}: {e}") from e

    _global_face_cascade = cv2.CascadeClassifier(str(cascade_path))
    if _global_face_cascade.empty():
        raise RuntimeError(f"[FaceTracker] Failed to load Haar Cascade from {cascade_path}")
    return _global_face_cascade


def compute_crop_coords(
    input_video: str,
    start_ms: int,
    end_ms: int,
    smoothing_window: int = 15,
    sample_every_n_frames: int = 5,
    adaptive_sampling: bool = False,
    activity_threshold: float = 1.5,
) -> Dict:
    """
    Analyze a video segment and compute a smooth 9:16 crop box
    centered on the detected face(s).

    Args:
        input_video:         Path to the source video file.
        start_ms:            Clip start time in milliseconds.
        end_ms:              Clip end time in milliseconds.
        smoothing_window:    Number of frames to average for
                             smooth crop movement.
        sample_every_n_frames: Only run face detection every N frames.
        adaptive_sampling: Skip sampled Haar detections on visually unchanged
            frames. Disabled by default to preserve legacy output exactly.
        activity_threshold: Mean grayscale pixel difference required to run a
            sampled detection when ``adaptive_sampling`` is enabled.

    Returns:
        A dict containing:
        {
            "crop_w": int,      # Crop width in pixels
            "crop_h": int,      # Crop height (= source height)
            "crop_x": int,      # Final crop X offset (left edge)
            "src_w":  int,      # Original video width
            "src_h":  int,      # Original video height
            "face_detected": bool
        }
    """
    face_cascade = _get_cascade()

    import av
    container = av.open(input_video)
    video_stream = container.streams.video[0]
    
    fps = float(video_stream.average_rate)
    src_w = video_stream.width
    src_h = video_stream.height

    # Calculate the crop dimensions for 9:16 aspect ratio
    # We always use full height and calculate the matching width
    crop_h = src_h
    crop_w = int(src_h * (TARGET_ASPECT_W / TARGET_ASPECT_H))

    # If source video is already narrower than needed, use source width
    if crop_w > src_w:
        crop_w = src_w

    logger.info(
        f"[FaceTracker] Source: {src_w}x{src_h} | "
        f"9:16 Crop: {crop_w}x{crop_h}"
    )

    # Seek to clip start (PyAV uses time_base)
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    seek_ts = int(start_s / video_stream.time_base)
    container.seek(seek_ts, stream=video_stream)

    if sample_every_n_frames < 1:
        raise ValueError("sample_every_n_frames must be at least 1")
    if activity_threshold < 0:
        raise ValueError("activity_threshold must be non-negative")
    if adaptive_sampling:
        from modules.native_accel import mean_absolute_difference

    face_x_positions: List[float] = []
    face_detected = False
    previous_sample_gray: Optional[np.ndarray] = None
    frames_read = 0

    for frame in container.decode(video=0):
        t = frame.time
        if t < start_s:
            continue
        if t > end_s:
            break

        # Only run detection every N frames (CPU saver)
        if frames_read % sample_every_n_frames == 0:
            img = frame.to_ndarray(format="bgr24")
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Haar detection is already native OpenCV. When explicitly opted
            # in, the C++ activity kernel can avoid re-running it on static
            # podcast frames while retaining the original default schedule.
            should_detect = True
            if adaptive_sampling and previous_sample_gray is not None:
                should_detect = mean_absolute_difference(previous_sample_gray, gray) >= activity_threshold
            previous_sample_gray = gray
            if not should_detect:
                frames_read += 1
                continue

            # Detect faces
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.2,
                minNeighbors=5,
                minSize=(60, 60)
            )

            if len(faces) > 0:
                face_detected = True
                # Sort faces by size (width * height) descending and pick the largest face
                faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                fx, fy, fw, fh = faces[0]
                
                # Calculate face center X in pixels
                face_center_x = fx + (fw / 2.0)
                face_x_positions.append(face_center_x)

        frames_read += 1

    container.close()

    # ─── Calculate final crop X offset ──────────────────────
    crop_x = _calculate_smooth_crop_x(
        face_x_positions, crop_w, src_w, smoothing_window
    )

    logger.info(
        f"[FaceTracker] ✅ Face detected: {face_detected} | "
        f"Crop X offset: {crop_x}px | "
        f"Sampled {len(face_x_positions)} face positions."
    )

    return {
        "crop_w":        crop_w,
        "crop_h":        crop_h,
        "crop_x":        crop_x,
        "src_w":         src_w,
        "src_h":         src_h,
        "face_detected": face_detected
    }


class KalmanCropSmoother:
    """
    1D constant-velocity Kalman filter for face-position smoothing.

    State vector:  x = [position, velocity]  (2×1)
    Observation:   z = [position]             (1×1, measures position only)

    Matrices
    --------
    F  (2×2) — state transition (assumes dt = 1 frame)
    H  (1×2) — observation model
    Q  (2×2) — process noise covariance
    R  (1×1) — measurement noise covariance
    P  (2×2) — state error covariance (initialised to R on diagonal)
    K  (2×1) — Kalman gain (computed each step)
    """

    def __init__(
        self,
        process_noise_q: float = 1.0,
        measurement_noise_r: float = 50.0,
    ) -> None:
        self.q = float(process_noise_q)
        self.r = float(measurement_noise_r)

        dt: float = 1.0

        # State-transition matrix  F
        self.F: np.ndarray = np.array([[1.0, dt],
                                        [0.0, 1.0]])

        # Observation matrix  H  (we only measure position)
        self.H: np.ndarray = np.array([[1.0, 0.0]])

        # Process-noise covariance  Q
        self.Q: np.ndarray = self.q * np.array([
            [dt ** 4 / 4.0, dt ** 3 / 2.0],
            [dt ** 3 / 2.0, dt ** 2],
        ])

        # Measurement-noise covariance  R
        self.R: np.ndarray = np.array([[self.r]])

    def smooth(self, measurements: List[float]) -> List[float]:
        """
        Run the Kalman filter forward pass over *measurements* and return
        a list of smoothed position estimates (one per measurement).

        Args:
            measurements: Raw face-center X positions (pixels), one per
                          sampled frame.

        Returns:
            List of filtered position values, same length as *measurements*.
        """
        if not measurements:
            return []

        # Initialise state from the first observation
        x: np.ndarray = np.array([[measurements[0]],
                                    [0.0]])          # [position, velocity]
        P: np.ndarray = np.array([[self.r, 0.0],
                                    [0.0,   self.r]])  # initial covariance

        smoothed: List[float] = []

        for z_val in measurements:
            # ── Predict ──────────────────────────────────────────
            x_pred: np.ndarray = self.F @ x
            P_pred: np.ndarray = self.F @ P @ self.F.T + self.Q

            # ── Update ───────────────────────────────────────────
            z: np.ndarray = np.array([[z_val]])
            S: np.ndarray = self.H @ P_pred @ self.H.T + self.R   # innovation covariance
            K: np.ndarray = P_pred @ self.H.T @ np.linalg.inv(S)  # Kalman gain  (2×1)

            y: np.ndarray = z - self.H @ x_pred                   # innovation
            x = x_pred + K @ y
            P = (np.eye(2) - K @ self.H) @ P_pred

            smoothed.append(float(x[0, 0]))  # record filtered position

        return smoothed


def _calculate_smooth_crop_x(
    face_x_positions: List[float],
    crop_w: int,
    src_w: int,
    smoothing_window: int
) -> int:
    """
    Calculate the optimal crop X offset based on collected face positions.

    Uses a Kalman filter for smooth, stable crop placement.
    Falls back to center crop if no faces were detected.

    Args:
        face_x_positions: List of face center X coordinates (pixels).
        crop_w:           Width of the 9:16 crop box.
        src_w:            Source video width.
        smoothing_window: Retained for API compatibility (unused by Kalman).

    Returns:
        Integer X offset (left edge of crop box).
    """
    if not face_x_positions:
        # No face detected → center crop fallback
        logger.warning("[FaceTracker] No face detected — defaulting to center crop.")
        return max(0, (src_w - crop_w) // 2)

    # Apply the 1-D Kalman filter and take the median of the smoothed series.
    # The median is robust against transient detection outliers.
    smoothed = KalmanCropSmoother().smooth(face_x_positions)
    avg_face_x = float(np.median(smoothed))

    crop_x = int(avg_face_x - crop_w / 2)
    return max(0, min(crop_x, src_w - crop_w))

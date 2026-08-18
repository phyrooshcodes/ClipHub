"""Stable Python API for optional C++ acceleration.

The pipeline always works without the extension.  Install the project with
``pip install -e .`` to use the native kernels automatically.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

try:
    import clip_engine_core as _native
except ImportError:  # Source-only checkout or unsupported compiler platform.
    _native = None


def native_available() -> bool:
    """Return whether the optional compiled extension is importable."""
    return _native is not None


def mean_absolute_difference(previous: np.ndarray, current: np.ndarray) -> float:
    """Return mean absolute difference of equally shaped grayscale uint8 frames.

    The Rust kernel avoids NumPy's temporary signed arrays. A NumPy fallback
    preserves availability for source-only Python workflows.
    """
    previous = np.ascontiguousarray(np.asarray(previous, dtype=np.uint8))
    current = np.ascontiguousarray(np.asarray(current, dtype=np.uint8))
    if previous.ndim != 2 or current.ndim != 2 or previous.shape != current.shape:
        raise ValueError("previous and current must be equally shaped 2-D grayscale frames")
    if previous.size == 0:
        raise ValueError("frames must not be empty")
    if _native is not None and hasattr(_native, "mean_absolute_difference"):
        return float(_native.mean_absolute_difference(previous, current))
    return float(np.abs(previous.astype(np.int16) - current.astype(np.int16)).mean())


def smooth_crop_x(
    positions: Sequence[float], crop_width: int, source_width: int, smoothing_window: int = 10
) -> int:
    """Return the legacy face-centered crop offset, optionally using Rust."""
    if crop_width < 0 or source_width < 0 or crop_width > source_width:
        raise ValueError("crop_width must be between zero and source_width")
    if smoothing_window <= 0:
        raise ValueError("smoothing_window must be positive")
    values = np.asarray(positions, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("positions must contain only finite values")
    if _native is not None and hasattr(_native, "smooth_crop_x"):
        return int(_native.smooth_crop_x(values.tolist(), crop_width, source_width, smoothing_window))

    if not len(values):
        return max(0, (source_width - crop_width) // 2)
    if len(values) > smoothing_window:
        values = np.convolve(values, np.ones(smoothing_window) / smoothing_window, mode="valid")
        center = float(np.median(values))
    else:
        center = float(np.mean(values))
    return max(0, min(int(center - crop_width / 2), source_width - crop_width))

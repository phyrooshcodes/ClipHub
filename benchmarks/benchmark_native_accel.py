#!/usr/bin/env python3
"""Compare the native face-activity kernel with the NumPy fallback.

Run after ``pip install -e .``. This benchmark does not require a video,
model, GPU, or OpenCV installation.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from modules.native_accel import mean_absolute_difference, native_available, smooth_crop_x


def numpy_mad(previous: np.ndarray, current: np.ndarray) -> float:
    return float(np.abs(previous.astype(np.int16) - current.astype(np.int16)).mean())


def timed(callable_, iterations: int) -> tuple[float, float]:
    start = time.perf_counter()
    result = 0.0
    for _ in range(iterations):
        result = callable_()
    return time.perf_counter() - start, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    rng = np.random.default_rng(7)
    previous = rng.integers(0, 256, (args.height, args.width), dtype=np.uint8)
    current = rng.integers(0, 256, (args.height, args.width), dtype=np.uint8)

    numpy_seconds, numpy_value = timed(lambda: numpy_mad(previous, current), args.iterations)
    native_seconds, native_value = timed(lambda: mean_absolute_difference(previous, current), args.iterations)
    assert abs(numpy_value - native_value) < 1e-12
    assert smooth_crop_x([100.0, 200.0, 300.0], 100, 1000, 15) == 100

    print(f"native extension: {'available' if native_available() else 'unavailable (NumPy fallback)'}")
    print(f"frame: {args.width}x{args.height}; iterations: {args.iterations}")
    print(f"NumPy MAD:  {numpy_seconds:.4f}s")
    print(f"selected MAD implementation: {native_seconds:.4f}s")
    if native_available():
        print(f"speedup: {numpy_seconds / native_seconds:.2f}x")


if __name__ == "__main__":
    main()

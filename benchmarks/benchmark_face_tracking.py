#!/usr/bin/env python3
"""Measure legacy and adaptive face tracking on the same video segment.

This intentionally reports both crop coordinates instead of asserting equality:
adaptive mode is an opt-in sampling policy and can observe fewer face samples.
Use representative talking-head footage before enabling it in production.
"""

from __future__ import annotations

import argparse
import time

from modules.face_tracker import compute_crop_coords
from modules.native_accel import native_available


def run(label: str, **kwargs: object) -> tuple[float, dict]:
    start = time.perf_counter()
    result = compute_crop_coords(**kwargs)
    elapsed = time.perf_counter() - start
    print(f"{label}: {elapsed:.3f}s; crop_x={result['crop_x']}; face={result['face_detected']}")
    return elapsed, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--start-ms", type=int, default=0)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--threshold", type=float, default=1.5)
    args = parser.parse_args()
    base = {"input_video": args.video, "start_ms": args.start_ms, "end_ms": args.end_ms}

    print(f"native extension: {'available' if native_available() else 'unavailable (NumPy fallback)'}")
    baseline_seconds, _ = run("legacy", **base)
    adaptive_seconds, _ = run(
        "adaptive", **base, adaptive_sampling=True, activity_threshold=args.threshold
    )
    print(f"adaptive speedup: {baseline_seconds / adaptive_seconds:.2f}x")


if __name__ == "__main__":
    main()

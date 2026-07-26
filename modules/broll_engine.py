# ============================================================
# broll_engine.py — B-Roll Overlay Engine
# Purpose: Download stock footage from the Pexels Video API,
#          cache it locally, and composite B-Roll overlays onto
#          already-rendered clips using a single FFmpeg
#          filter_complex pass with smooth alpha-fade transitions.
# ============================================================

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)

# ─── Constants & Config ──────────────────────────────────────
PEXELS_API_URL = "https://api.pexels.com/videos/search"
BROLL_CACHE_DIR = Path(__file__).parent.parent / "broll_cache"
BROLL_DURATION_S = 4.0   # Each B-Roll overlay lasts 4 seconds
BROLL_FADE_S = 0.5       # Fade in/out duration
BROLL_OPACITY = 0.85     # Overlay opacity (0-1)
BROLL_MAX_PER_CLIP = 3   # Maximum B-Roll overlays per clip
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

# Timeout for Pexels API and download requests (seconds)
_API_TIMEOUT = 15
_DOWNLOAD_TIMEOUT = 120
_DOWNLOAD_CHUNK_SIZE = 1024 * 256  # 256 KB chunks


# ─── Helper: cache key ───────────────────────────────────────

def _cache_key(keyword: str) -> str:
    """Return a deterministic hex digest suitable for filenames."""
    return hashlib.sha256(keyword.strip().lower().encode("utf-8")).hexdigest()[:16]


# ─── Helper: pick best video file ────────────────────────────

def _pick_best_video_file(video_files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Select the video file whose resolution is closest to 1080×1920.

    Prefers portrait / vertical files.  Falls back to the closest
    resolution if no portrait candidate exists.

    Args:
        video_files: List of Pexels ``video_files`` dicts, each
            containing at least ``width``, ``height``, and ``link``.

    Returns:
        The best-matching file dict, or ``None`` if *video_files* is
        empty.
    """
    if not video_files:
        return None

    def _score(vf: Dict[str, Any]) -> float:
        w = vf.get("width", 0)
        h = vf.get("height", 0)
        # Euclidean distance from the target resolution
        return ((w - TARGET_WIDTH) ** 2 + (h - TARGET_HEIGHT) ** 2) ** 0.5

    return min(video_files, key=_score)


# ─── Helper: get base-clip duration ──────────────────────────

def _probe_duration(video_path: str) -> Optional[float]:
    """Return the duration (seconds) of *video_path* via ``ffprobe``.

    Returns ``None`` on any failure so callers can fall back gracefully.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return float(result.stdout.decode().strip())
    except Exception as exc:
        logger.debug("[BRollEngine] ffprobe failed for %s: %s", video_path, exc)
        return None


# ─── Function 1: fetch_broll_video ───────────────────────────

def fetch_broll_video(
    keyword: str,
    api_key: str,
    cache_dir: Optional[Path] = None,
) -> Optional[str]:
    """Search the Pexels Video API and download a stock clip.

    The downloaded file is stored in a local cache directory keyed by
    a SHA-256 hash of the *keyword*.  Subsequent calls with the same
    keyword return the cached path instantly.

    Args:
        keyword:   Search term (e.g. ``"city skyline"``).
        api_key:   Pexels API key.  If falsy, the function returns
                   ``None`` immediately.
        cache_dir: Override for the cache directory.  Defaults to
                   ``BROLL_CACHE_DIR``.

    Returns:
        Absolute path to the downloaded MP4, or ``None`` on failure.
    """
    if not api_key:
        logger.warning("[BRollEngine] No Pexels API key provided — skipping B-Roll fetch.")
        return None

    if not _REQUESTS_AVAILABLE:
        logger.warning("[BRollEngine] 'requests' library not installed — skipping B-Roll fetch.")
        return None

    cache = Path(cache_dir) if cache_dir else BROLL_CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)

    key = _cache_key(keyword)
    cached_path = cache / f"broll_{key}.mp4"

    # ── Cache hit ─────────────────────────────────────────────
    if cached_path.exists() and cached_path.stat().st_size > 0:
        logger.info("[BRollEngine] Cache hit for '%s' → %s", keyword, cached_path)
        return str(cached_path)

    # ── API search ────────────────────────────────────────────
    logger.info("[BRollEngine] Searching Pexels for '%s' …", keyword)
    try:
        resp = requests.get(
            PEXELS_API_URL,
            headers={"Authorization": api_key},
            params={
                "query": keyword,
                "per_page": 5,
                "orientation": "portrait",
            },
            timeout=_API_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("[BRollEngine] Pexels API request failed: %s", exc)
        return None

    data = resp.json()
    videos = data.get("videos", [])
    if not videos:
        logger.info("[BRollEngine] No portrait results for '%s', falling back to any orientation...", keyword)
        try:
            resp = requests.get(
                PEXELS_API_URL,
                headers={"Authorization": api_key},
                params={
                    "query": keyword,
                    "per_page": 5,
                },
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            videos = data.get("videos", [])
        except Exception as exc:
            logger.warning("[BRollEngine] Pexels fallback API request failed: %s", exc)
            return None

    if not videos:
        logger.warning("[BRollEngine] No Pexels results for '%s' even with fallback orientation.", keyword)
        return None

    # ── Pick the best file across all returned videos ─────────
    best_file: Optional[Dict[str, Any]] = None
    best_score = float("inf")

    for video in videos:
        vf_list = video.get("video_files", [])
        candidate = _pick_best_video_file(vf_list)
        if candidate is None:
            continue
        w = candidate.get("width", 0)
        h = candidate.get("height", 0)
        score = ((w - TARGET_WIDTH) ** 2 + (h - TARGET_HEIGHT) ** 2) ** 0.5
        if score < best_score:
            best_score = score
            best_file = candidate

    if best_file is None:
        logger.warning("[BRollEngine] No suitable video files found for '%s'.", keyword)
        return None

    download_url = best_file.get("link", "")
    if not download_url:
        logger.warning("[BRollEngine] Selected video file has no download link.")
        return None

    # ── Download ──────────────────────────────────────────────
    logger.info(
        "[BRollEngine] Downloading B-Roll (%dx%d) for '%s' …",
        best_file.get("width", 0),
        best_file.get("height", 0),
        keyword,
    )

    # Write to a temp file first, then atomically move into cache
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4", dir=str(cache))
    tmp_fd_closed = False
    try:
        dl_resp = requests.get(download_url, stream=True, timeout=_DOWNLOAD_TIMEOUT)
        dl_resp.raise_for_status()

        total_size = int(dl_resp.headers.get("content-length", 0))
        downloaded = 0
        last_logged_pct = -10.0
        with os.fdopen(tmp_fd, "wb") as f:
            tmp_fd_closed = True
            for chunk in dl_resp.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = (downloaded / total_size) * 100
                        if pct - last_logged_pct >= 10.0 or downloaded == total_size:
                            logger.info(
                                f"[BRollEngine] Downloading B-Roll for '{keyword}': {pct:.0f}% "
                                f"({downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)"
                            )
                            last_logged_pct = pct
                    else:
                        if downloaded % (2 * 1024 * 1024) < _DOWNLOAD_CHUNK_SIZE:
                            logger.info(
                                f"[BRollEngine] Downloading B-Roll for '{keyword}': "
                                f"{downloaded / (1024*1024):.1f} MB"
                            )

        shutil.move(tmp_path, str(cached_path))
        logger.info("[BRollEngine] ✅ Cached → %s", cached_path)
        return str(cached_path)

    except Exception as exc:
        logger.warning("[BRollEngine] Download failed for '%s': %s", keyword, exc)
        # Clean up partial temp file
        if not tmp_fd_closed:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return None


# ─── Function 2: prepare_broll_clip ──────────────────────────

def prepare_broll_clip(
    broll_path: str,
    output_path: str,
    duration_s: float = BROLL_DURATION_S,
) -> str:
    """Trim, scale, and apply a Ken Burns zoom to a raw B-Roll clip.

    The output is a portrait-oriented clip of exactly *duration_s*
    seconds at 1080×1920, ready to be overlaid onto a base clip.

    Processing steps:
      1. Trim to *duration_s* seconds from the start.
      2. Scale to ≥ 1080×1920 (preserving aspect ratio), then
         centre-crop to exactly 1080×1920.
      3. Apply a subtle Ken Burns (slow zoom-in) via ``zoompan``.

    Args:
        broll_path:  Path to the source B-Roll video.
        output_path: Destination path for the prepared clip.
        duration_s:  Target duration in seconds.

    Returns:
        *output_path* on success.

    Raises:
        RuntimeError: If FFmpeg exits with a non-zero code.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # The filter chain:
    #   1. scale + crop → exact 1080x1920
    #   2. zoompan     → Ken Burns slow-zoom
    vf_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.0008,1.25)':"
        f"d={int(duration_s * 30)}:"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "s=1080x1920:"
        "fps=30"
    )

    command = [
        "ffmpeg", "-y",
        "-i", broll_path,
        "-t", f"{duration_s:.3f}",
        "-vf", vf_filter,
        "-an",                   # Strip audio — B-Roll is silent in composites
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    logger.info(
        "[BRollEngine] Preparing B-Roll clip: %s → %s (%.1fs)",
        broll_path, output_path, duration_s,
    )

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"[BRollEngine] FFmpeg failed preparing B-Roll.\n"
            f"Command: {' '.join(command)}\n"
            f"stderr:\n{stderr}"
        ) from exc

    logger.info("[BRollEngine] ✅ Prepared B-Roll → %s", output_path)
    return output_path


# ─── Function 3: composite_broll_overlays ────────────────────

def composite_broll_overlays(
    base_clip_path: str,
    broll_cues: List[Dict[str, Any]],
    api_key: str,
    temp_dir: str,
    output_path: Optional[str] = None,
) -> str:
    """Overlay one or more B-Roll clips onto *base_clip_path*.

    All overlays are composited in a **single** FFmpeg
    ``-filter_complex`` pass so there is no generational quality
    loss.  Each overlay fades in/out smoothly and the base clip's
    audio is preserved untouched.

    Args:
        base_clip_path: Path to the rendered base clip.
        broll_cues:     List of cue dicts, each containing:

            - ``keyword``  (str): Pexels search term.
            - ``offset_s`` (float): Seconds into the clip where
              the overlay should appear.

        api_key:   Pexels API key.
        temp_dir:  Directory for intermediate files.
        output_path:
            Destination for the composited clip.  If ``None`` the
            base clip is **replaced** (rendered to a temp file,
            then moved over the original).

    Returns:
        Path to the final composited clip, or *base_clip_path*
        unchanged if compositing is skipped or fails.
    """
    # ── Guard: nothing to do ──────────────────────────────────
    if not broll_cues:
        logger.info("[BRollEngine] No B-Roll cues provided — skipping overlay.")
        return base_clip_path

    if not api_key and not _REQUESTS_AVAILABLE:
        logger.warning(
            "[BRollEngine] No API key or requests unavailable — skipping all B-Roll."
        )
        return base_clip_path

    os.makedirs(temp_dir, exist_ok=True)

    # ── Probe base clip duration ──────────────────────────────
    base_duration = _probe_duration(base_clip_path)
    if base_duration is None:
        logger.warning(
            "[BRollEngine] Could not determine base clip duration — skipping B-Roll."
        )
        return base_clip_path

    # ── Enforce maximum overlays per clip ─────────────────────
    cues = broll_cues[:BROLL_MAX_PER_CLIP]
    if len(broll_cues) > BROLL_MAX_PER_CLIP:
        logger.info(
            "[BRollEngine] Limiting B-Roll cues from %d to %d.",
            len(broll_cues), BROLL_MAX_PER_CLIP,
        )

    # ── Fetch, prepare, and validate each cue ─────────────────
    prepared: List[Dict[str, Any]] = []  # [{path, offset_s, duration_s}, …]

    for idx, cue in enumerate(cues):
        keyword = cue.get("keyword", "")
        offset_s = float(cue.get("offset_s", 0.0))

        if not keyword:
            logger.warning("[BRollEngine] Cue %d has empty keyword — skipping.", idx)
            continue

        # Clamp offset so overlay doesn't start past the clip end
        if offset_s >= base_duration:
            logger.warning(
                "[BRollEngine] Cue %d offset (%.1fs) ≥ clip duration (%.1fs) — skipping.",
                idx, offset_s, base_duration,
            )
            continue

        # Clamp overlay duration if it would exceed the base clip
        effective_duration = min(BROLL_DURATION_S, base_duration - offset_s)
        if effective_duration < 0.5:
            logger.warning(
                "[BRollEngine] Cue %d effective duration too short (%.2fs) — skipping.",
                idx, effective_duration,
            )
            continue

        # Check for overlap with already-accepted cues
        overlapping = False
        for prev in prepared:
            prev_start = prev["offset_s"]
            prev_end = prev_start + prev["duration_s"]
            cur_start = offset_s
            cur_end = offset_s + effective_duration

            if cur_start < prev_end and cur_end > prev_start:
                logger.warning(
                    "[BRollEngine] Cue %d '%s' @%.1fs overlaps with a previous overlay "
                    "(%.1f–%.1fs) — skipping.",
                    idx, keyword, offset_s, prev_start, prev_end,
                )
                overlapping = True
                break

        if overlapping:
            continue

        # Fetch from Pexels
        raw_path = fetch_broll_video(keyword, api_key)
        if raw_path is None:
            logger.warning(
                "[BRollEngine] Could not fetch B-Roll for '%s' — skipping cue %d.",
                keyword, idx,
            )
            continue

        # Prepare (trim, scale, Ken Burns)
        prep_path = os.path.join(temp_dir, f"broll_prep_{idx}.mp4")
        try:
            prepare_broll_clip(raw_path, prep_path, duration_s=effective_duration)
        except RuntimeError as exc:
            logger.warning("[BRollEngine] Failed to prepare B-Roll cue %d: %s", idx, exc)
            continue

        prepared.append({
            "path": prep_path,
            "offset_s": offset_s,
            "duration_s": effective_duration,
        })

    if not prepared:
        logger.info("[BRollEngine] No B-Roll clips were prepared — returning base clip.")
        return base_clip_path

    # ── Build FFmpeg filter_complex ────────────────────────────
    #
    # Inputs:
    #   [0]  = base clip
    #   [1]… = prepared B-Roll clips (in order)
    #
    # For each overlay i (0-indexed), the filter:
    #   1. Convert to yuva420p (for alpha channel)
    #   2. Fade alpha in at t=0 and out near the end
    #   3. Shift PTS so the overlay starts at offset_s
    #
    # Then chain overlay filters left-to-right:
    #   [0:v][broll0] overlay → [tmp0]
    #   [tmp0][broll1] overlay → [tmp1]  …  → [outv]

    filter_parts: List[str] = []

    for i, entry in enumerate(prepared):
        offset = entry["offset_s"]
        dur = entry["duration_s"]
        fade_in_d = min(BROLL_FADE_S, dur / 2)
        fade_out_start = max(0.0, dur - BROLL_FADE_S)
        fade_out_d = min(BROLL_FADE_S, dur - fade_out_start)

        # Per-overlay preparation filter
        # colorchannelmixer is used to apply a global opacity < 1.0
        # by scaling the alpha channel: aa=BROLL_OPACITY
        filter_parts.append(
            f"[{i + 1}:v]"
            f"format=yuva420p,"
            f"colorchannelmixer=aa={BROLL_OPACITY},"
            f"fade=t=in:st=0:d={fade_in_d:.3f}:alpha=1,"
            f"fade=t=out:st={fade_out_start:.3f}:d={fade_out_d:.3f}:alpha=1,"
            f"setpts=PTS+{offset}/TB"
            f"[broll{i}]"
        )

    # Chain overlay operations
    n = len(prepared)
    for i, entry in enumerate(prepared):
        offset = entry["offset_s"]
        dur = entry["duration_s"]
        end_t = offset + dur

        # Source label for the "bottom" layer
        if i == 0:
            src_label = "0:v"
        else:
            src_label = f"tmp{i - 1}"

        # Output label
        if i == n - 1:
            out_label = "outv"
        else:
            out_label = f"tmp{i}"

        filter_parts.append(
            f"[{src_label}][broll{i}]"
            f"overlay=0:0:enable='between(t,{offset:.3f},{end_t:.3f})'"
            f"[{out_label}]"
        )

    filter_complex = ";\n".join(filter_parts)

    # ── Decide output destination ─────────────────────────────
    replace_in_place = output_path is None
    if replace_in_place:
        final_output = base_clip_path
        render_target = os.path.join(temp_dir, "broll_composite_tmp.mp4")
    else:
        final_output = output_path
        render_target = output_path
        os.makedirs(os.path.dirname(render_target) or ".", exist_ok=True)

    # ── Build FFmpeg command ──────────────────────────────────
    command = ["ffmpeg", "-y"]

    # Input 0: base clip
    command += ["-i", base_clip_path]

    # Inputs 1…N: prepared B-Roll clips
    for entry in prepared:
        command += ["-i", entry["path"]]

    command += [
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a",                   # Preserve original audio
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "copy",                  # Audio passthrough — untouched
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-shortest",
        render_target,
    ]

    logger.info(
        "[BRollEngine] Compositing %d B-Roll overlay(s) onto %s",
        len(prepared), base_clip_path,
    )
    logger.debug("[BRollEngine] filter_complex:\n%s", filter_complex)

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore")
        logger.error(
            "[BRollEngine] FFmpeg composite failed — returning base clip unchanged.\n"
            "Command: %s\nstderr:\n%s",
            " ".join(command), stderr,
        )
        return base_clip_path

    # ── Replace in-place if requested ─────────────────────────
    if replace_in_place:
        try:
            shutil.move(render_target, final_output)
            logger.info("[BRollEngine] ✅ Replaced base clip with composited output.")
        except OSError as exc:
            logger.error(
                "[BRollEngine] Failed to move composited file into place: %s", exc
            )
            return base_clip_path
    else:
        logger.info("[BRollEngine] ✅ Composited output → %s", final_output)

    return final_output

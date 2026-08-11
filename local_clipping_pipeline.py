#!/usr/bin/env python3
# ============================================================
# local_clipping_pipeline.py — Obscura Clips Orchestrator
# ============================================================
# Zero-Strain Local-Hybrid AI Video Clipper
# Built for: Asus TUF A15 (Ryzen 7 + RTX 3050 4GB)
#
# Pipeline:
#   Input MP4
#     → [CPU] Audio Demux       (audio_demux.py)
#     → [CPU] ASR Transcription (transcriber.py)
#     → [☁]  Hook Detection    (hook_detector.py  — NVIDIA NIM)
#     → [CPU] Face Tracking     (face_tracker.py   — MediaPipe)
#     → [CPU] Subtitle Gen      (subtitle_engine.py — ASS)
#     → [GPU] NVENC Render      (renderer.py        — h264_nvenc)
#     → output/*.mp4
#
# Usage:
#   python local_clipping_pipeline.py --input video.mp4
#   python local_clipping_pipeline.py --input video.mp4 --model small --max-clips 5
# ============================================================

import argparse
import io
import logging
import os
import sys
import shutil
import time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# ── Inject local bin/ into PATH so FFmpeg is found even as a subprocess ──
_BASE = Path(__file__).parent
for _bin_candidate in [
    _BASE / "bin",
    Path("C:/ffmpeg/bin"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
]:
    if _bin_candidate.exists() and str(_bin_candidate) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = str(_bin_candidate) + os.pathsep + os.environ.get("PATH", "")



# ─── Setup Logging ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

BANNER = """
+==============================================================+
|         *  O B S C U R A   C L I P S  *                    |
|                                                            |
+==============================================================+
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Obscura Clips — AI-powered vertical video clipper.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        metavar="VIDEO",
        help="Path to the input video file (MP4 recommended)."
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="output",
        metavar="DIR",
        help="Directory where rendered clips will be saved.\n"
             "Default: ./output/"
    )
    parser.add_argument(
        "--model", "-m",
        default="small",
        choices=["tiny", "base", "small"],
        help="Whisper model size for ASR transcription.\n"
             "  tiny  → fastest, lower accuracy\n"
             "  base  → balanced\n"
             "  small → more accurate (default, recommended with GPU)"
    )
    parser.add_argument(
        "--language", "-l",
        default=None,
        metavar="LANG",
        help="ISO 639-1 language code (e.g. 'en', 'hi').\n"
             "Leave blank for auto-detection."
    )
    parser.add_argument(
        "--max-clips",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of clips to generate. Range: 1-30. Default: 10"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the temp/ directory after processing.\n"
             "Useful for debugging subtitle/audio files."
    )
    parser.add_argument(
        "--music",
        default="none",
        help="Background music choice: 'none', 'ambient', 'lofi', 'focus', 'auto' (random matches), or custom file."
    )
    parser.add_argument(
        "--caption-style",
        default="kinetic_slide",
        choices=[
            "kinetic_slide", "tiktok_pop", "cyberpunk_neon", "smooth_wave", "vibrant_gradient",
            "cinematic_swing", "karaoke_glow", "minimal_fade", "future_cyber", "hormozi_gold",
            "mrbeast_lightning", "fire_ember", "emerald_money", "glitch_matrix", "neon_purple_rain",
            "bold_impact_red", "sunset_vibes", "pastel_dream", "stomp_kinetic"
        ],
        help="Caption animation style:\n"
             "  kinetic_slide      -> smooth slide & bounce (default)\n"
             "  hormozi_gold       -> Alex Hormozi signature warm gold punch\n"
             "  mrbeast_lightning  -> electric cyan with energetic tilt\n"
             "  fire_ember         -> fiery orange leaping words\n"
             "  emerald_money      -> wealth emerald green pop\n"
             "  glitch_matrix      -> hacker neon green jitter\n"
             "  neon_purple_rain   -> electric violet breathing zoom\n"
             "  bold_impact_red    -> aggressive drama blood red\n"
             "  sunset_vibes       -> warm sunset floating glow\n"
             "  pastel_dream       -> soft lavender creamy aesthetic\n"
             "  stomp_kinetic      -> action slam down animation\n"
             "  tiktok_pop         -> fast word zoom pop\n"
             "  cyberpunk_neon     -> cyan & pink tilt pop\n"
             "  smooth_wave        -> smooth karaoke highlights\n"
             "  vibrant_gradient   -> orange-to-yellow vibrant gradient\n"
             "  cinematic_swing    -> elegant swing tilt\n"
             "  karaoke_glow       -> glowing neon outline\n"
             "  minimal_fade       -> elegant word fade\n"
             "  future_cyber       -> tech-inspired active glow"
    )
    parser.add_argument(
        "--font-preset",
        default="default",
        choices=["default", "hormozi", "beast", "minimal"],
        help="Visual font style preset:\n"
             "  default  -> Clean Arial, white text, medium outline\n"
             "  hormozi  -> Bold Impact, yellow text, thick outline\n"
             "  beast    -> Heavy Arial Black, yellow text, thick outline\n"
             "  minimal  -> Light Arial, white text, thin outline"
     )
    parser.add_argument(
        "--font-name",
        default="",
        help="Custom font name override (must be installed locally)."
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=0,
        help="Custom font size override (pixels)."
    )
    parser.add_argument(
        "--primary-color",
        default="",
        help="Custom primary color (HTML hex, e.g. '#FF0000')."
    )
    parser.add_argument(
        "--outline-color",
        default="",
        help="Custom outline color (HTML hex, e.g. '#000000')."
    )
    parser.add_argument(
        "--no-title",
        action="store_true",
        help="Disable the permanent title hook banner at the top of the video."
    )
    parser.add_argument(
        "--broll",
        action="store_true",
        help="Enable AI-powered B-Roll stock footage overlays on clips."
    )
    parser.add_argument(
        "--pexels-key",
        default="",
        help="Pexels API key for downloading stock footage B-Roll. "
             "Required when --broll is enabled. Get one free at pexels.com/api"
    )
    parser.add_argument(
        "--auto-publish",
        action="store_true",
        help="Queue each completed clip for personal Instagram publishing in the background."
    )
    return parser.parse_args()


def preflight_checks(input_video: str) -> None:
    """
    Verify system requirements before starting the pipeline.
    Raises SystemExit on any critical failure.
    """
    logger.info("─── Pre-flight Checks ──────────────────────────────")

    # 1. FFmpeg
    if shutil.which("ffmpeg") is None:
        logger.error("❌ FFmpeg not found in PATH.")
        logger.error(
            "   Install from https://ffmpeg.org/download.html\n"
            "   Then add C:\\ffmpeg\\bin to your Windows PATH."
        )
        sys.exit(1)
    logger.info("✅ FFmpeg found in PATH.")

    # 2. FFprobe
    if shutil.which("ffprobe") is None:
        logger.error("❌ FFprobe not found (usually bundled with FFmpeg).")
        sys.exit(1)
    logger.info("✅ FFprobe found in PATH.")

    # 3. Input video exists
    if not os.path.isfile(input_video):
        logger.error(f"❌ Input video not found: {input_video}")
        sys.exit(1)
    logger.info(f"✅ Input video found: {input_video}")

    # 4. Python packages
    missing = []
    try:
        import faster_whisper
    except ImportError:
        missing.append("faster-whisper")
    try:
        import openai
    except ImportError:
        missing.append("openai")
    try:
        import cv2
    except ImportError:
        missing.append("opencv-python")
    try:
        import mediapipe
    except ImportError:
        missing.append("mediapipe")
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    try:
        import av
    except ImportError:
        missing.append("av")

    if missing:
        logger.error(f"❌ Missing packages: {', '.join(missing)}")
        logger.error("   Run: pip install -r requirements.txt")
        sys.exit(1)
    logger.info("✅ All Python packages present.")

    # 5. NVENC availability (non-fatal — falls back to CPU)
    from modules.renderer import check_nvenc_available
    check_nvenc_available()

    logger.info("─── Pre-flight Passed ──────────────────────────────\n")


def run_pipeline(args: argparse.Namespace) -> None:
    """Main pipeline execution."""

    input_video = os.path.abspath(args.input)
    output_dir  = os.path.abspath(args.output_dir)
    
    # Generate job-specific processing folder under temp
    job_id = os.path.basename(output_dir.rstrip("/\\"))
    temp_dir = os.path.abspath(os.path.join("temp", f"processing_{job_id}"))

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir,   exist_ok=True)

    total_start = time.time()

    # ─── STAGE 1: Audio Demux ────────────────────────────────
    logger.info("═══ STAGE 1/6 ─ Audio Demux (CPU) ══════════════════")
    from modules.audio_demux import extract_audio, get_video_duration

    audio_path = os.path.join(temp_dir, "audio.wav")
    extract_audio(input_video, audio_path)
    video_duration = get_video_duration(input_video)
    logger.info(f"   Video duration: {video_duration:.1f}s\n")

    # ─── STAGE 2: ASR Transcription (Whisper) ─────────────────
    logger.info("═══ STAGE 2/6 ─ ASR Transcription (🖥 Local GPU/CPU) ═══")
    import hashlib
    import json
    from modules.transcriber import words_to_timed_transcript, transcribe_audio
    
    file_stat = os.stat(args.input)
    hash_str = f"{os.path.abspath(args.input)}_{file_stat.st_size}_{args.language}"
    cache_key = hashlib.md5(hash_str.encode()).hexdigest()[:8]
    words_cache_path = os.path.join(temp_dir, f"words_{cache_key}.json")
    
    if os.path.exists(words_cache_path):
        logger.info(f"[Transcriber] Found cached transcription: {words_cache_path}")
        with open(words_cache_path, "r", encoding="utf-8") as f:
            words = json.load(f)
    else:
        words = transcribe_audio(audio_path, model_size=args.model, language=args.language)
        # Cache for subsequent runs
        with open(words_cache_path, "w", encoding="utf-8") as f:
            json.dump(words, f, indent=2, ensure_ascii=False)
            
    timed_transcript = words_to_timed_transcript(words)

    # Save transcript for debugging
    transcript_path = os.path.join(temp_dir, "transcript.txt")
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(timed_transcript)
    logger.info(f"   Transcript saved → {transcript_path}\n")

    # ─── STAGE 3: Hook Detection (NVIDIA NIM Cloud) ───────────
    logger.info("═══ STAGE 3/6 ─ Hook Detection (☁ NVIDIA NIM) ══════")
    from modules.hook_detector import detect_hooks

    hooks_cache_path = os.path.join(temp_dir, f"hooks_{cache_key}_{args.max_clips}.json")
    if os.path.exists(hooks_cache_path):
        logger.info(f"[HookDetector] Found cached hooks: {hooks_cache_path}")
        with open(hooks_cache_path, "r", encoding="utf-8") as f:
            clips = json.load(f)
    else:
        clips = detect_hooks(
            words=words,
            video_duration_seconds=video_duration,
            max_clips=args.max_clips
        )
        with open(hooks_cache_path, "w", encoding="utf-8") as f:
            json.dump(clips, f, indent=2, ensure_ascii=False)

    if not clips:
        logger.warning("⚠️  No hooks detected. Exiting.")
        return

    logger.info(f"   {len(clips)} clips queued for rendering.\n")

    # Save clips metadata to a JSON file for the Web UI/server to read
    metadata_file = os.path.join(output_dir, "clips_metadata.json")
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(clips, f, indent=2, ensure_ascii=False)
        logger.info(f"   Saved clips metadata -> {metadata_file}")
    except Exception as e:
        logger.warning(f"   Failed to save clips metadata: {e}")
    # ─── STAGES 4-6: Per-Clip Processing ─────────────────────
    from modules.face_tracker   import compute_crop_coords
    from modules.subtitle_engine import generate_ass_subtitles
    from modules.renderer import (
        render_clip,
        check_nvenc_available
    )
    from modules.music_director import MusicDirector

    use_nvenc = check_nvenc_available()
    rendered_clips = []
    # Background music director setup
    music_director = None
    if args.music and args.music.lower() not in ("none", "off", ""):
        if args.music.lower() == "auto":
            music_director = MusicDirector(Path(__file__).parent / "Music")
        else:
            from modules.bg_music import get_music_track
            track_path = get_music_track(args.music)
            if track_path:
                music_director = MusicDirector(Path(__file__).parent / "Music")
                # Intercept _library_entries to only return this specific file
                original_entries = music_director._library_entries
                def custom_entries():
                    entries = original_entries()
                    target_name = os.path.basename(track_path)
                    return [e for e in entries if e["name"] == target_name]
                music_director._library_entries = custom_entries
            else:
                logger.warning(f"Background music track '{args.music}' could not be loaded; continuing without background music.")

    used_music_paths = set()
    for idx, clip in enumerate(clips):
        clip_num  = idx + 1
        start_ms  = clip["start_ms"]
        end_ms    = clip["end_ms"]
        title     = clip.get("title", f"clip_{clip_num:03d}")
        score     = clip.get("hook_score", "?")

        # Sanitize title for use as filename
        safe_title = "".join(c if c.isalnum() or c in " _-" else "" for c in title)
        safe_title = safe_title.strip().replace(" ", "_")[:40]
        clip_filename = f"{safe_title}.mp4"
        clip["filename"] = clip_filename
        output_path   = os.path.join(output_dir, clip_filename)
        sub_path      = os.path.join(temp_dir, f"subtitles_{clip_num:02d}.ass")
        clip_words = [
            word for word in words
            if word["start"] >= start_ms / 1000.0 and word["end"] <= end_ms / 1000.0
        ]

        logger.info(
            f"\n═══ CLIP {clip_num}/{len(clips)} ══════════════════════════════\n"
            f"   Title:  {title}\n"
            f"   Score:  {score}\n"
            f"   Reason: {clip.get('reason', 'N/A')}\n"
            f"   Range:  [{start_ms/1000:.1f}s → {end_ms/1000:.1f}s] "
            f"({(end_ms - start_ms)/1000:.1f}s)\n"
        )

        # ─── Stage 4: Face Tracking ──────────────────────────
        logger.info(f"   [4/6] Face Tracking (CPU — MediaPipe) ...")
        crop_coords = compute_crop_coords(
            input_video,
            start_ms=start_ms,
            end_ms=end_ms
        )

        # ─── Stage 5: Subtitle Generation ────────────────────
        logger.info(f"   [5/6] Generating kinetic subtitles ...")
        clip_title_str = "" if args.no_title else title
        generate_ass_subtitles(
            words=words,
            clip_start_s=start_ms / 1000.0,
            clip_end_s=end_ms   / 1000.0,
            output_path=sub_path,
            style_name=args.caption_style,
            clip_title=clip_title_str,
            preset_name=args.font_preset,
            font_name=args.font_name,
            font_size=args.font_size,
            primary_color=args.primary_color,
            outline_color=args.outline_color
        )

        music_choice = None
        if music_director:
            music_choice = music_director.choose(
                clip=clip,
                clip_words=clip_words,
                clip_duration_s=(end_ms - start_ms) / 1000.0,
                used_paths=used_music_paths,
            )
            if music_choice:
                used_music_paths.add(music_choice["path"])
                logger.info(
                    f"   [Music] {music_choice['name']} | "
                    f"{music_choice['mood'].replace('_', ' ')} | "
                    f"excerpt starts {music_choice['start_s']:.1f}s"
                )
            else:
                logger.info("   [Music] no safe local track found; preserving original audio only.")

        # ─── Stage 6: NVENC Render ───────────────────────────
        logger.info(f"   [6/6] Rendering with {'NVENC ⚡' if use_nvenc else 'libx264 (CPU fallback)'} ...")
        render_clip(
            input_video=input_video,
            output_path=output_path,
            start_ms=start_ms,
            end_ms=end_ms,
            crop_coords=crop_coords,
            subtitle_path=sub_path,
            music_choice=music_choice,
            clip_index=idx,
            encoder="auto" if use_nvenc else "libx264"
        )

        # ─── B-Roll Overlay (optional post-render composite) ──
        if args.broll and args.pexels_key:
            broll_cues = clip.get("broll_cues", [])
            if broll_cues:
                try:
                    from modules.broll_engine import composite_broll_overlays
                    logger.info(f"   [B-Roll] Compositing {len(broll_cues)} B-Roll overlay(s) ...")
                    composite_broll_overlays(
                        base_clip_path=output_path,
                        broll_cues=broll_cues,
                        api_key=args.pexels_key,
                        temp_dir=temp_dir,
                        output_path=None  # Replace in-place
                    )
                    logger.info(f"   [B-Roll] ✅ B-Roll compositing complete.")
                except ImportError:
                    logger.warning("   [B-Roll] ⚠️ broll_engine module not found. Skipping B-Roll.")
                except Exception as e:
                    logger.warning(f"   [B-Roll] ⚠️ B-Roll overlay failed: {e}. Keeping original clip.")
            else:
                logger.info("   [B-Roll] No B-Roll cues detected by LLM for this clip.")
        elif args.broll and not args.pexels_key:
            logger.warning("   [B-Roll] ⚠️ --broll enabled but no --pexels-key provided. Skipping B-Roll.")

    # Save final updated clips metadata with filenames
    metadata_file = os.path.join(output_dir, "clips_metadata.json")
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(clips, f, indent=2, ensure_ascii=False)
        logger.info(f"   Saved updated clips metadata -> {metadata_file}")
    except Exception as e:
        logger.warning(f"   Failed to save clips metadata: {e}")

        # Keep publishing independent from generation: enqueue only. The
        # persistent queue owns browser work on its own worker thread.
        if args.auto_publish:
            try:
                import urllib.request
                import json
                
                caption = clip.get("social_caption") or clip.get("caption") or title
                job_id_val = os.path.basename(os.path.normpath(args.output_dir))
                if job_id_val == "output": job_id_val = ""
                
                req_data = {
                    "job_id": job_id_val,
                    "clip_filename": clip_filename,
                    "title": title,
                    "caption": caption,
                    "platforms": ["instagram", "youtube"],
                    "allow_duplicate": True
                }
                req = urllib.request.Request(
                    "http://127.0.0.1:7842/api/social/post",
                    data=json.dumps(req_data).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    logger.info("   [AutoPublish] API responded: %s", res)
            except Exception as exc:
                logger.warning("   [AutoPublish] Auto Publish was not queued: %s", exc)

        rendered_clips.append(output_path)
        logger.info(f"   ✅ Done → {output_path}")

    # ─── Cleanup ─────────────────────────────────────────────
    if not args.keep_temp and os.path.exists(temp_dir):
        # Delete only large audio.wav files and subtitle files, keeping cache words.json
        audio_file = os.path.join(temp_dir, "audio.wav")
        if os.path.exists(audio_file):
            try:
                os.remove(audio_file)
                logger.info("[Cleanup] Removed temporary audio.wav file.")
            except Exception as e:
                logger.warning(f"[Cleanup] Failed to remove audio file: {e}")
        
        # Clean up temporary ASS files
        try:
            for f in os.listdir(temp_dir):
                if f.endswith(".ass"):
                    os.remove(os.path.join(temp_dir, f))
        except Exception as e:
            logger.warning(f"[Cleanup] Failed to remove subtitle files: {e}")
        logger.info(f"\n[Cleanup] Temporary processing files cleaned up (cache preserved).")

    # ─── Summary ─────────────────────────────────────────────
    total_elapsed = time.time() - total_start
    logger.info("\n" + "═" * 60)
    logger.info("  ✦  OBSCURA CLIPS — DONE")
    logger.info("═" * 60)
    logger.info(f"  Clips rendered : {len(rendered_clips)}")
    logger.info(f"  Output folder  : {output_dir}")
    logger.info(f"  Total time     : {total_elapsed:.1f}s")
    logger.info("═" * 60)
    for path in rendered_clips:
        logger.info(f"   → {os.path.basename(path)}")
    logger.info("═" * 60 + "\n")


def main() -> None:
    # Reconfigure stdout to UTF-8 so Unicode chars work on Windows terminals
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print(BANNER)
    args = parse_args()

    # Run pre-flight before anything else
    preflight_checks(args.input)

    try:
        run_pipeline(args)
    except KeyboardInterrupt:
        logger.info("\n[Pipeline] Interrupted by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"\n[Pipeline] ❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

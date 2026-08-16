#!/usr/bin/env python3
# ============================================================
# local_clipping_pipeline.py — ClipHub Orchestrator
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
import json
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
        description="ClipHub — AI-powered vertical video clipper.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--input", "-i",
        default="",
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
        "--commentary-mode",
        default="hook_commentary",
        choices=["off", "hook_only", "hook_commentary", "full_editorial"],
        help="AI Commentary Mode:\n"
             "  off             -> Standard clip extraction (no AI voice)\n"
             "  hook_only       -> AI Hook + Source Clip\n"
             "  hook_commentary -> AI Hook + Source Clip + AI Commentary (default)\n"
             "  full_editorial  -> AI Hook + Source Clip + AI Commentary + AI Takeaway"
    )
    parser.add_argument(
        "--commentary-voice",
        default="af_sarah",
        help="Voice ID for Kokoro TTS (default: af_sarah)."
    )
    parser.add_argument(
        "--intro-duration",
        type=float,
        default=2.5,
        help="Duration of the visual blur/zoom during the AI intro hook (seconds)."
    )
    parser.add_argument(
        "--auto-publish",
        action="store_true",
        help="Queue each completed clip for personal Instagram publishing in the background."
    )
    parser.add_argument(
        "--phase",
        default="all",
        choices=["1", "2", "all"],
        help="Pipeline Execution Phase:\n"
             "  1   -> Run Analysis & AI Generation only (Hooks, Commentary) and exit.\n"
             "  2   -> Run Rendering only (loads metadata from phase 1).\n"
             "  all -> Run end-to-end (default)."
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run comprehensive system preflight diagnostic tests and exit."
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
        import soundfile
    except ImportError:
        missing.append("soundfile")
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


def _prune_stale_temp_files(temp_root: str = "temp", max_age_days: int = 7) -> None:
    """Evicts intermediate artifacts and temporary processing directories older than max_age_days without touching active jobs."""
    if not os.path.exists(temp_root):
        return
    now = time.time()
    cutoff = now - (max_age_days * 86400)
    
    # Check journal to avoid deleting active or recently modified jobs
    active_job_ids = set()
    journal_path = os.path.join(temp_root, ".jobs_journal.json")
    if os.path.exists(journal_path):
        try:
            with open(journal_path, "r", encoding="utf-8") as f:
                jdata = json.load(f)
                for jid, job in jdata.get("jobs", {}).items():
                    if not job.get("done", False) or (now - job.get("start_time", 0) < 86400):
                        active_job_ids.add(jid)
        except Exception:
            pass

    for entry in os.scandir(temp_root):
        try:
            if entry.name.startswith("processing_") and entry.is_dir():
                folder_job_id = entry.name.replace("processing_", "")
                if folder_job_id not in active_job_ids and entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry.path, ignore_errors=True)
            elif entry.is_file() and entry.name != ".jobs_journal.json" and entry.stat().st_mtime < cutoff:
                os.remove(entry.path)
        except Exception:
            pass


def _compute_fast_content_fingerprint(filepath: str) -> str:
    """Content-addressed fingerprint: head + tail + middle chunks + exact file size."""
    import hashlib
    hasher = hashlib.sha256()
    stat = os.stat(filepath)
    hasher.update(str(stat.st_size).encode())
    with open(filepath, "rb") as f:
        # First 64KB
        hasher.update(f.read(65536))
        # Middle 64KB
        if stat.st_size > 131072:
            f.seek(stat.st_size // 2)
            hasher.update(f.read(65536))
        # Last 64KB
        if stat.st_size > 196608:
            f.seek(max(0, stat.st_size - 65536))
            hasher.update(f.read(65536))
    return hasher.hexdigest()[:16]


def run_pipeline(args: argparse.Namespace) -> None:
    """Main pipeline execution."""
    _prune_stale_temp_files()

    input_video = os.path.abspath(args.input)
    output_dir  = os.path.abspath(args.output_dir)
    
    # Generate job-specific processing folder under temp
    job_id = os.path.basename(output_dir.rstrip("/\\"))
    temp_dir = os.path.abspath(os.path.join("temp", f"processing_{job_id}"))

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir,   exist_ok=True)

    total_start = time.time()

    if args.phase in ("1", "all"):
        # ─── STAGE 1: Audio Demux ────────────────────────────────
        logger.info("═══ STAGE 1/6 ─ Audio Demux (CPU) ══════════════════")
        from modules.audio_demux import extract_audio, get_video_duration

        audio_path = os.path.join(temp_dir, "audio.wav")
        extract_audio(input_video, audio_path)
        video_duration = get_video_duration(input_video)
        logger.info(f"   Video duration: {video_duration:.1f}s\n")
    else:
        # Phase 2 fallback logic to get duration and audio_path
        from modules.audio_demux import get_video_duration
        audio_path = os.path.join(temp_dir, "audio.wav")
        video_duration = get_video_duration(input_video)

    # Define deterministic content & version-based cache keys
    import hashlib
    PIPELINE_VERSION = "2.3.0"
    HOOK_DETECTOR_VERSION = "2.2.0"
    content_hash = _compute_fast_content_fingerprint(input_video)
    
    # Transcript cache: content-addressed to binary chunks, whisper model, language, and pipeline version
    transcript_hash_str = f"{content_hash}_{args.model}_{args.language}_{PIPELINE_VERSION}"
    words_cache_key = hashlib.sha256(transcript_hash_str.encode()).hexdigest()[:12]
    words_cache_path = os.path.join(temp_dir, f"words_{words_cache_key}.json")
    
    metadata_file = os.path.join(output_dir, "clips_metadata.json")
    # Hook cache: content-addressed to transcript key, max_clips, commentary mode, and detector version
    hook_hash_str = f"{words_cache_key}_{args.max_clips}_{getattr(args, 'commentary_mode', 'off')}_{HOOK_DETECTOR_VERSION}"
    hook_cache_key = hashlib.sha256(hook_hash_str.encode()).hexdigest()[:12]
    hooks_cache_path = os.path.join(temp_dir, f"hooks_{hook_cache_key}.json")
    
    if args.phase in ("1", "all"):
        # ─── STAGE 2: ASR Transcription (Whisper) ─────────────────
        logger.info("═══ STAGE 2/6 ─ ASR Transcription (🖥 Local GPU/CPU) ═══")
        from modules.transcriber import words_to_timed_transcript, transcribe_audio
        
        if os.path.exists(words_cache_path):
            logger.info(f"[Transcriber] Found cached transcription: {words_cache_path}")
            with open(words_cache_path, "r", encoding="utf-8") as f:
                words = json.load(f)
        else:
            words = transcribe_audio(audio_path, model_size=args.model, language=args.language)
            with open(words_cache_path, "w", encoding="utf-8") as f:
                json.dump(words, f, indent=2, ensure_ascii=False)
                
        timed_transcript = words_to_timed_transcript(words)
        transcript_path = os.path.join(temp_dir, "transcript.txt")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(timed_transcript)
        logger.info(f"   Transcript saved → {transcript_path}\n")

        # ─── STAGE 3: Hook Detection (NVIDIA NIM Cloud) ───────────
        logger.info("═══ STAGE 3/6 ─ Hook Detection (☁ NVIDIA NIM) ══════")
        from modules.hook_detector import detect_hooks

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

        # ─── STAGE 3.5: AI Commentary Generation ───────────
        if getattr(args, "commentary_mode", "off") != "off":
            logger.info(f"═══ STAGE 3.5/6 ─ AI Commentary ({args.commentary_mode}) ══════")
            from modules.commentary_generator import generate_commentary
            
            for i, clip in enumerate(clips):
                if "editorial_data" in clip:
                    continue
                    
                start_s = clip["start_ms"] / 1000.0
                end_s = clip["end_ms"] / 1000.0
                
                clip_words = [w for w in words if start_s <= w["start"] <= end_s]
                clip_transcript = " ".join([w["word"].strip() for w in clip_words])
                
                ctx_start = max(0, start_s - 30.0)
                ctx_end = min(video_duration, end_s + 30.0)
                ctx_words = [w for w in words if ctx_start <= w["start"] <= ctx_end]
                surrounding_context = " ".join([w["word"].strip() for w in ctx_words])
                
                logger.info(f"   Generating commentary for clip {i+1}...")
                editorial_data = generate_commentary(
                    clip_transcript=clip_transcript,
                    surrounding_context=surrounding_context,
                    topic=clip.get("title", "Unknown")
                )
                
                # Enforce modes
                if args.commentary_mode == "hook_only":
                    editorial_data["commentary_segments"] = []
                    editorial_data["takeaway"] = None
                elif args.commentary_mode == "hook_commentary":
                    editorial_data["takeaway"] = None
                    
                clip["editorial_data"] = editorial_data
                
            with open(hooks_cache_path, "w", encoding="utf-8") as f:
                json.dump(clips, f, indent=2, ensure_ascii=False)

        # Save metadata JSON file
        try:
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(clips, f, indent=2, ensure_ascii=False)
            logger.info(f"   Saved clips metadata -> {metadata_file}")
        except Exception as e:
            logger.warning(f"   Failed to save clips metadata: {e}")

        if args.phase == "1":
            logger.info("\n[Phase 1] Analysis and AI Generation complete. Exiting cleanly.")
            return
    else:
        # Phase 2 -> Load required state from disk
        logger.info(f"═══ STAGE 4-6 ─ Loading Phase 1 Data ({metadata_file}) ══════")
        if not os.path.exists(metadata_file):
            logger.error(f"❌ Cannot start Phase 2: Metadata file not found ({metadata_file})")
            sys.exit(1)
        if not os.path.exists(words_cache_path):
            logger.error(f"❌ Cannot start Phase 2: Words cache not found ({words_cache_path})")
            sys.exit(1)
            
        with open(words_cache_path, "r", encoding="utf-8") as f:
            words = json.load(f)
        with open(metadata_file, "r", encoding="utf-8") as f:
            clips = json.load(f)
            
    # ─── STAGES 4-6: Per-Clip Processing ─────────────────────
    from modules.face_tracker   import compute_crop_coords
    from modules.subtitle_engine import generate_ass_subtitles
    from modules.renderer import (
        render_clip,
        check_nvenc_available
    )

    use_nvenc = check_nvenc_available()
    rendered_clips = []

    # Clean old .mp4 clips in output_dir from previous runs to prevent gallery pollution
    if os.path.exists(output_dir):
        valid_prefixes = {f"clip_{i+1:02d}_" for i in range(len(clips))}
        for existing in os.listdir(output_dir):
            if existing.endswith(".mp4") and existing.startswith("clip_"):
                if not any(existing.startswith(vp) for vp in valid_prefixes):
                    try:
                        os.remove(os.path.join(output_dir, existing))
                    except Exception:
                        pass

    for idx, clip in enumerate(clips):
        clip_num  = idx + 1
        start_ms  = clip["start_ms"]
        end_ms    = clip["end_ms"]
        title     = clip.get("title", f"clip_{clip_num:03d}")
        score     = clip.get("hook_score", "?")

        # Sanitize title for use as filename with clip_XX_ prefix for exact metadata indexing
        safe_title = "".join(c if c.isalnum() or c in " _-" else "" for c in title)
        safe_title = safe_title.strip().replace(" ", "_")[:35]
        clip_filename = f"clip_{clip_num:02d}_{safe_title}.mp4"
        clip["filename"] = clip_filename
        output_path   = os.path.join(output_dir, clip_filename)
        sub_path      = os.path.join(temp_dir, f"subtitles_{clip_num:02d}.ass")
        clip_words = [
            word for word in words
            if word["end"] > start_ms / 1000.0 and word["start"] < end_ms / 1000.0
        ]

        # ─── Stage 4: Face Tracking ──────────────────────────
        logger.info(f"   [4/6] Face Tracking (CPU — MediaPipe) ...")
        crop_coords = compute_crop_coords(
            input_video,
            start_ms=start_ms,
            end_ms=end_ms
        )

        # ─── Stage 4.5: AI Editorial Composition ──────────────
        ai_audio_events = []
        if getattr(args, "commentary_mode", "off") != "off":
            logger.info(f"   [4.5/6] Building Editorial Timeline ...")
            from modules.editorial_compositor import align_editorial_timeline
            clip_words, ai_audio_events = align_editorial_timeline(
                clip=clip,
                source_words=clip_words,
                temp_dir=temp_dir,
                voice_id=getattr(args, "commentary_voice", "af_sarah")
            )
            clip["ai_audio_events"] = ai_audio_events

        # ─── Stage 5: Subtitle Generation ────────────────────
        logger.info(f"   [5/6] Generating kinetic subtitles ...")
        clip_title_str = "" if args.no_title else title
        generate_ass_subtitles(
            words=clip_words,
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

        # ─── Stage 6: NVENC Render ───────────────────────────
        logger.info(f"   [6/6] Rendering with {'NVENC ⚡' if use_nvenc else 'libx264 (CPU fallback)'} ...")
        
        # Prepare editorial arguments
        editorial_data = clip.get("editorial_data") if getattr(args, "commentary_mode", "off") != "off" else None
        
        render_clip(
            input_video=input_video,
            output_path=output_path,
            start_ms=start_ms,
            end_ms=end_ms,
            crop_coords=crop_coords,
            subtitle_path=sub_path,
            clip_index=idx,
            encoder="auto" if use_nvenc else "libx264",
            editorial_data=editorial_data,
            commentary_voice=getattr(args, "commentary_voice", "af_sarah"),
            intro_duration=getattr(args, "intro_duration", 2.5),
            ai_audio_events=ai_audio_events
        )

        # Keep publishing independent from generation: enqueue only. The
        # persistent queue owns browser work on its own worker thread.
        if args.auto_publish:
            try:
                import urllib.request
                
                caption = clip.get("social_caption") or clip.get("caption") or title
                job_id_val = os.path.basename(os.path.normpath(args.output_dir))
                if job_id_val == "output": job_id_val = ""
                
                platforms = ["instagram"]
                if os.environ.get("CLIPHUB_AUTO_PUBLISH_YOUTUBE", "0").lower() in ("1", "true", "yes"):
                    platforms.append("youtube")
                req_data = {
                    "job_id": job_id_val,
                    "clip_filename": clip_filename,
                    "title": title,
                    "caption": caption,
                    "platforms": platforms,
                    "allow_duplicate": False
                }
                server_base = os.environ.get("CLIPHUB_SERVER_URL", "http://127.0.0.1:7842").rstrip("/")
                headers = {"Content-Type": "application/json"}
                lan_tok = os.environ.get("CLIPHUB_LAN_TOKEN")
                if lan_tok:
                    headers["X-ClipHub-Token"] = lan_tok
                req = urllib.request.Request(
                    f"{server_base}/api/social/post",
                    data=json.dumps(req_data).encode("utf-8"),
                    headers=headers
                )
                with urllib.request.urlopen(req) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    logger.info("   [AutoPublish] API responded: %s", res)
            except Exception as exc:
                logger.warning("   [AutoPublish] Auto Publish was not queued: %s", exc)

        rendered_clips.append(output_path)
        logger.info(f"   ✅ Done → {output_path}")

    # Save final updated clips metadata with filenames
    metadata_file = os.path.join(output_dir, "clips_metadata.json")
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(clips, f, indent=2, ensure_ascii=False)
        logger.info(f"   Saved updated clips metadata -> {metadata_file}")
    except Exception as e:
        logger.warning(f"   Failed to save clips metadata: {e}")

    # ─── Cleanup ─────────────────────────────────────────────
    if not args.keep_temp and os.path.exists(temp_dir):
        # Delete only large audio.wav files, temporary subtitle files, sendcmd, and AI speech wavs
        audio_file = os.path.join(temp_dir, "audio.wav")
        if os.path.exists(audio_file):
            try:
                os.remove(audio_file)
                logger.info("[Cleanup] Removed temporary audio.wav file.")
            except Exception as e:
                logger.warning(f"[Cleanup] Failed to remove audio file: {e}")
        
        # Clean up temporary ASS, sendcmd, and intermediate TTS WAV files
        try:
            for f in os.listdir(temp_dir):
                if f.endswith(".ass") or f.endswith(".sendcmd.txt") or (f.endswith(".wav") and f != "audio.wav"):
                    try:
                        os.remove(os.path.join(temp_dir, f))
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[Cleanup] Failed to remove temporary processing files: {e}")
        logger.info(f"\n[Cleanup] Temporary processing files cleaned up (cache preserved).")

    # ─── Summary ─────────────────────────────────────────────
    total_elapsed = time.time() - total_start
    logger.info("\n" + "═" * 60)
    logger.info("  ✦  CLIPHUB CLIPS — DONE")
    logger.info("═" * 60)
    logger.info(f"  Clips rendered : {len(rendered_clips)}")
    logger.info(f"  Output folder  : {output_dir}")
    logger.info(f"  Total time     : {total_elapsed:.1f}s")
    logger.info("═" * 60)
    for path in rendered_clips:
        logger.info(f"   → {os.path.basename(path)}")
    logger.info("═" * 60 + "\n")


def run_doctor_diagnostic() -> None:
    """Run comprehensive system diagnostic test and print a Google-standard health report."""
    print("\n" + "=" * 65)
    print(" ✦  CLIPHUB PIPELINE SYSTEM DIAGNOSTIC (DOCTOR)")
    print("=" * 65)
    
    # 1. Python & Environment
    print(f" • Python Runtime       : {sys.version.split()[0]} ({sys.platform})")
    print(f" • Execution Prefix     : {sys.prefix}")
    
    # 2. FFmpeg & Hardware Encoders
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    ffprobe_ok = shutil.which("ffprobe") is not None
    print(f" • FFmpeg Binaries      : {'[OK] Installed' if ffmpeg_ok else '[FAIL] Missing in PATH'}")
    print(f" • FFprobe Binaries     : {'[OK] Installed' if ffprobe_ok else '[FAIL] Missing in PATH'}")
    
    from modules.renderer import check_nvenc_available
    nvenc_ok = check_nvenc_available()
    print(f" • NVENC GPU Encoding   : {'[OK] Hardware Accelerated (Active)' if nvenc_ok else '[INFO] CPU Fallback (libx264)'}")
    
    # 3. Whisper ASR
    try:
        from faster_whisper import WhisperModel
        print(" • Faster-Whisper ASR   : [OK] Installed & Ready")
    except Exception as e:
        print(f" • Faster-Whisper ASR   : [FAIL] {e}")
        
    # 4. Kokoro TTS
    try:
        from modules.kokoro_tts import get_kokoro_instance
        kokoro_inst = get_kokoro_instance()
        print(" • Kokoro-82M ONNX TTS  : [OK] Initialized & Ready")
    except Exception as e:
        print(f" • Kokoro-82M ONNX TTS  : [INFO] Lazy Download on First Run ({e})")
        
    # 5. Face Tracking
    try:
        import cv2
        print(" • OpenCV DNN (YuNet)   : [OK] Computer Vision Engine Ready")
    except Exception as e:
        print(f" • OpenCV DNN (YuNet)   : [FAIL] {e}")
        
    # 6. LLM API Key
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if api_key:
        masked = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "Set"
        print(f" • NVIDIA NIM API Key   : [OK] Present ({masked})")
    else:
        print(" • NVIDIA NIM API Key   : [WARN] Not Set (Will fallback to Local LM Studio)")
        
    print("=" * 65)
    print(" Diagnostic Complete. System is operational.\n")

def main() -> None:
    # Reconfigure stdout to UTF-8 so Unicode chars work on Windows terminals
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print(BANNER)
    args = parse_args()

    if args.doctor:
        run_doctor_diagnostic()
        sys.exit(0)

    if not args.input:
        logger.error("❌ Input video is required.\n   Usage: python local_clipping_pipeline.py --input <path_to_video.mp4>")
        sys.exit(1)

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

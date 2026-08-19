import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
import asyncio
from modules.kokoro_tts import generate_tts_sync, generate_tts
from modules.transcriber import transcribe_audio

logger = logging.getLogger(__name__)

def align_editorial_timeline(
    clip: Dict[str, Any],
    source_words: List[Dict[str, Any]],
    temp_dir: str,
    voice_id: str = "af_sarah"
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    New clip structure:
      [Kai Intro Hook (avatar freeze)] → [Full host clip, uninterrupted] → [Kai Closing Explanation (avatar freeze)]

    Returns:
      1. combined_words: Source words (shifted by hook duration) + AI intro words + AI closing words, sorted.
      2. ai_audio_events: List of dicts with 'type' ('hook' or 'closing'), 'audio_path', 'duration', 'start_s', 'end_s'.
    """
    editorial_data = clip.get("editorial_data")
    if not editorial_data:
        return source_words, []

    clip_start_s = clip["start_ms"] / 1000.0
    clip_end_s   = clip["end_ms"]   / 1000.0
    clip_duration = clip_end_s - clip_start_s

    ai_audio_events = []
    ai_words = []

    # ── 1. Kai Intro Hook ─────────────────────────────────────────────────────
    hook_val = editorial_data.get("hook")
    hook_text = hook_val.get("text", "") if isinstance(hook_val, dict) else (hook_val or "")
    duration_hook = 0.0

    if isinstance(hook_text, str) and hook_text.strip():
        clean_hook = hook_text.strip()
        safe_text = "".join(c if c.isalnum() else "_" for c in clean_hook[:20])
        hook_audio_path = os.path.join(temp_dir, f"hook_{clip['start_ms']}_{safe_text}.wav")
        duration_hook = generate_tts_sync(clean_hook, voice_id, hook_audio_path)

        if duration_hook > 0:
            hook_words = transcribe_audio(hook_audio_path, model_size="tiny", language="en")
            for w in hook_words:
                w["start"] += clip_start_s          # Place at the timeline start of this clip
                w["end"]   += clip_start_s
                w["is_ai"] = True
                ai_words.append(w)

            ai_audio_events.append({
                "type":        "hook",
                "audio_path":  hook_audio_path,
                "duration":    duration_hook,
                "source_time": 0.0,
                "start_s":     0.0,
                "end_s":       duration_hook,
                "text":        clean_hook
            })
            logger.info(f"[Compositor] Kai hook: {duration_hook:.2f}s — \"{clean_hook[:60]}\"")

    # ── 2. Kai Closing Explanation (plays AFTER speaker finishes) ─────────────
    # Accepts either 'closing_explanation' (new field) or falls back to
    # the first 'commentary_segments' entry (backwards-compat with cached clips).
    closing_text = ""
    closing_raw = editorial_data.get("closing_explanation")
    if isinstance(closing_raw, dict):
        closing_text = closing_raw.get("text", "").strip()
    elif isinstance(closing_raw, str):
        closing_text = closing_raw.strip()

    if not closing_text:
        # Backwards compatibility: use first commentary_segment text if closing_explanation absent
        segments = editorial_data.get("commentary_segments", [])
        if segments and isinstance(segments, list) and isinstance(segments[0], dict):
            closing_text = segments[0].get("text", "").strip()

    duration_closing = 0.0
    if closing_text:
        safe_text = "".join(c if c.isalnum() else "_" for c in closing_text[:20])
        closing_audio_path = os.path.join(temp_dir, f"closing_{clip['start_ms']}_{safe_text}.wav")
        duration_closing = generate_tts_sync(closing_text, voice_id, closing_audio_path)

        if duration_closing > 0:
            # Closing words start at: clip_start + hook_duration + clip_duration
            closing_timeline_start = duration_hook + clip_duration
            closing_words = transcribe_audio(closing_audio_path, model_size="tiny", language="en")
            for w in closing_words:
                w["start"] += closing_timeline_start + clip_start_s
                w["end"]   += closing_timeline_start + clip_start_s
                w["is_ai"] = True
                ai_words.append(w)

            ai_audio_events.append({
                "type":        "closing",
                "audio_path":  closing_audio_path,
                "duration":    duration_closing,
                "source_time": clip_duration,       # Fires after the full host clip
                "start_s":     closing_timeline_start,
                "end_s":       closing_timeline_start + duration_closing,
                "text":        closing_text
            })
            logger.info(f"[Compositor] Kai closing: {duration_closing:.2f}s — \"{closing_text[:60]}\"")

    # ── 3. Shift source words forward by hook duration (hook plays first) ─────
    shifted_source_words = []
    for w in source_words:
        w_copy = dict(w)
        w_copy["start"] += duration_hook
        w_copy["end"]   += duration_hook
        shifted_source_words.append(w_copy)

    # ── 4. Merge and sort all words chronologically ───────────────────────────
    combined_words = shifted_source_words + ai_words
    combined_words.sort(key=lambda x: x["start"])

    return combined_words, ai_audio_events

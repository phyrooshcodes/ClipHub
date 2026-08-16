import os
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
    Takes a clip with 'editorial_data' and 'start_ms', 'end_ms'.
    Generates TTS for Hook, Commentary, and Takeaway.
    Transcribes the TTS to get word-level timings.
    Returns:
      1. combined_words: Source words + AI words, correctly timed and sorted. Source words that overlap AI speech are removed.
      2. ai_audio_events: List of dicts with 'start_s', 'end_s', 'audio_path', 'type' (relative to clip start).
    """
    editorial_data = clip.get("editorial_data")
    if not editorial_data:
        return source_words, []

    clip_start_s = clip["start_ms"] / 1000.0
    clip_end_s = clip["end_ms"] / 1000.0
    clip_duration = clip_end_s - clip_start_s

    ai_audio_events = []
    ai_words = []

    # Helper to process a TTS segment
    def process_segment(text: str, start_time_rel: float, seg_type: str) -> float:
        if not text:
            return start_time_rel
            
        safe_text = "".join(c if c.isalnum() else "_" for c in text[:20])
        audio_path = os.path.join(temp_dir, f"{seg_type}_{clip['start_ms']}_{safe_text}.wav")
        
        # Generate TTS synchronously without event loop conflicts
        duration = generate_tts_sync(text, voice_id, audio_path)
        if duration <= 0:
            return start_time_rel
            
        # Transcribe to get word timings
        # model="tiny" is fast and sufficient for pristine TTS audio
        tts_words = transcribe_audio(audio_path, model_size="tiny", language="en")
        
        # Shift words to relative clip timeline
        for w in tts_words:
            w["start"] += start_time_rel + clip_start_s
            w["end"] += start_time_rel + clip_start_s
            w["is_ai"] = True  # flag for styling later if needed
            ai_words.append(w)
            
        ai_audio_events.append({
            "start_s": start_time_rel,
            "end_s": start_time_rel + duration,
            "audio_path": audio_path,
            "type": seg_type,
            "text": text
        })
        return start_time_rel + duration

    # 1. Hook (Starts at 0.0)
    current_time = 0.0
    hook_val = editorial_data.get("hook")
    hook_text = hook_val.get("text", "") if isinstance(hook_val, dict) else (hook_val or "")
    if isinstance(hook_text, str) and hook_text.strip():
        process_segment(hook_text.strip(), current_time, "hook")

    # 2. Commentary Segments
    # Find insertion points based on source words
    for seg in editorial_data.get("commentary_segments", []):
        insert_text = seg.get("insert_after_text", "").strip().lower()
        if not insert_text:
            continue
            
        # simple heuristic: find the word matching the last word of insert_text
        # inside the source_words.
        insert_words = insert_text.split()
        if not insert_words:
            continue
            
        last_word = insert_words[-1].strip(".,!?\"'")
        
        insert_time = -1.0
        # Search backwards to find the latest occurrence
        for w in reversed(source_words):
            if last_word in w["word"].lower():
                insert_time = w["end"] - clip_start_s
                break
                
        if insert_time >= 0:
            process_segment(seg.get("text", ""), insert_time, "commentary")
            
    # 3. Takeaway (Aligned to end of clip)
    takeaway_val = editorial_data.get("takeaway")
    takeaway_text = takeaway_val.get("text", "") if isinstance(takeaway_val, dict) else (takeaway_val or "")
    if isinstance(takeaway_text, str) and takeaway_text.strip():
        text = takeaway_text.strip()
        safe_text = "".join(c if c.isalnum() else "_" for c in text[:20])
        duration = generate_tts_sync(text, voice_id, audio_path)
        
        if duration > 0:
            insert_time = max(0.0, clip_duration - duration)
            tts_words = transcribe_audio(audio_path, model_size="tiny", language="en")
            
            for w in tts_words:
                w["start"] += insert_time + clip_start_s
                w["end"] += insert_time + clip_start_s
                w["is_ai"] = True
                ai_words.append(w)
                
            ai_audio_events.append({
                "start_s": insert_time,
                "end_s": insert_time + duration,
                "audio_path": audio_path,
                "type": "takeaway",
                "text": text
            })

    # Filter source words that overlap with AI events
    filtered_source_words = []
    for w in source_words:
        w_start_rel = w["start"] - clip_start_s
        w_end_rel = w["end"] - clip_start_s
        
        overlap = False
        for ev in ai_audio_events:
            # If word midpoint is within AI event
            midpoint = (w_start_rel + w_end_rel) / 2
            if ev["start_s"] <= midpoint <= ev["end_s"]:
                overlap = True
                break
        
        if not overlap:
            filtered_source_words.append(w)

    # Combine and sort
    combined_words = filtered_source_words + ai_words
    combined_words.sort(key=lambda x: x["start"])

    return combined_words, ai_audio_events

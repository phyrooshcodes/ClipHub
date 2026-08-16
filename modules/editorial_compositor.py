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
        nonlocal current_time
        if not text:
            return current_time
            
        safe_text = "".join(c if c.isalnum() else "_" for c in text[:20])
        audio_path = os.path.join(temp_dir, f"{seg_type}_{clip['start_ms']}_{safe_text}.wav")
        
        # Generate TTS synchronously without event loop conflicts
        duration = generate_tts_sync(text, voice_id, audio_path)
        if duration <= 0:
            return current_time
            
        # Ensure start time is strictly after previous AI audio segment
        target_start = max(start_time_rel, current_time + (0.1 if current_time > 0 else 0.0))
        
        # If segment overflows clip duration, attempt to place earlier if room exists
        if target_start + duration > clip_duration:
            if clip_duration - duration >= current_time + 0.1:
                target_start = max(current_time + 0.1, clip_duration - duration)
            else:
                # Does not fit in remaining clip timeline without clipping speech
                return current_time

        # Transcribe to get word timings
        # model="tiny" is fast and sufficient for pristine TTS audio
        tts_words = transcribe_audio(audio_path, model_size="tiny", language="en")
        
        # Shift words to relative clip timeline
        for w in tts_words:
            w["start"] += target_start + clip_start_s
            w["end"] += target_start + clip_start_s
            w["is_ai"] = True  # flag for styling later if needed
            ai_words.append(w)
            
        ai_audio_events.append({
            "start_s": target_start,
            "end_s": target_start + duration,
            "audio_path": audio_path,
            "type": seg_type,
            "text": text
        })
        current_time = target_start + duration
        return current_time

    # 1. Hook (Starts at 0.0)
    current_time = 0.0
    hook_val = editorial_data.get("hook")
    hook_text = hook_val.get("text", "") if isinstance(hook_val, dict) else (hook_val or "")
    if isinstance(hook_text, str) and hook_text.strip():
        current_time = process_segment(hook_text.strip(), current_time, "hook")

    # 2. Commentary Segments
    # Find insertion points based on exact phrase token sequence
    for seg in editorial_data.get("commentary_segments", []):
        insert_text = seg.get("insert_after_text", "").strip()
        if not insert_text:
            continue
            
        clean_tokens = [re.sub(r'[^\w]', '', t.lower()) for t in insert_text.split() if re.sub(r'[^\w]', '', t.lower())]
        if not clean_tokens:
            continue
            
        insert_time = -1.0
        n_tokens = len(clean_tokens)
        # Search backwards for multi-word token sequence
        for i in range(len(source_words) - n_tokens, -1, -1):
            window = [re.sub(r'[^\w]', '', source_words[i + k]["word"].lower()) for k in range(n_tokens)]
            if window == clean_tokens:
                insert_time = source_words[i + n_tokens - 1]["end"] - clip_start_s
                break
                
        # Fallback to exact single word match if sequence was not found
        if insert_time < 0:
            target_single = clean_tokens[-1]
            for w in reversed(source_words):
                if re.sub(r'[^\w]', '', w["word"].lower()) == target_single:
                    insert_time = w["end"] - clip_start_s
                    break
                
        if insert_time >= 0:
            # Ensure non-overlap with earlier AI events
            insert_time = max(insert_time, current_time + 0.1)
            if insert_time < clip_duration:
                current_time = process_segment(seg.get("text", ""), insert_time, "commentary")

    # 3. Takeaway (Aligned near end of clip, with safety margin)
    takeaway_val = editorial_data.get("takeaway")
    takeaway_text = takeaway_val.get("text", "") if isinstance(takeaway_val, dict) else (takeaway_val or "")
    if isinstance(takeaway_text, str) and takeaway_text.strip():
        text = takeaway_text.strip()
        est_words = len(text.split())
        est_dur = max(1.5, est_words * 0.35)
        ideal_start = max(0.0, clip_duration - est_dur - 0.5)
        actual_start = max(ideal_start, current_time + 0.2)
        if actual_start < clip_duration:
            process_segment(text, actual_start, "takeaway")

    # Filter source words that overlap with AI events
    filtered_source_words = []
    for w in source_words:
        w_start_rel = w["start"] - clip_start_s
        w_end_rel = w["end"] - clip_start_s
        
        overlap = False
        for ev in ai_audio_events:
            # If word overlaps any part of an AI speech event
            if max(w_start_rel, ev["start_s"]) < min(w_end_rel, ev["end_s"]):
                overlap = True
                break
        
        if not overlap:
            filtered_source_words.append(w)

    # Combine and sort
    combined_words = filtered_source_words + ai_words
    combined_words.sort(key=lambda x: x["start"])

    return combined_words, ai_audio_events

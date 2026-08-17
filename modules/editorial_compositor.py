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

    # 1. AI Intro Hook (Plays at start while video holds opening frame)
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
                w["start"] += clip_start_s
                w["end"] += clip_start_s
                w["is_ai"] = True
                ai_words.append(w)
                
            ai_audio_events.append({
                "type": "hook",
                "audio_path": hook_audio_path,
                "duration": duration_hook,
                "source_time": 0.0,
                "start_s": 0.0,
                "end_s": duration_hook,
                "text": clean_hook
            })

    # 2. AI Commentary Segment (Video pauses on freeze-frame while AI explains concept)
    comm_segments = editorial_data.get("commentary_segments", [])
    duration_comm = 0.0
    t_insert_src = None

    if comm_segments and isinstance(comm_segments, list):
        seg = comm_segments[0]
        comm_text = seg.get("text", "").strip()
        insert_text = seg.get("insert_after_text", "").strip()
        
        if comm_text:
            # Find insertion point in source words
            if insert_text:
                clean_tokens = [re.sub(r'[^\w]', '', t.lower()) for t in insert_text.split() if re.sub(r'[^\w]', '', t.lower())]
                n_tokens = len(clean_tokens)
                if n_tokens > 0:
                    for i in range(len(source_words) - n_tokens, -1, -1):
                        window = [re.sub(r'[^\w]', '', source_words[i + k]["word"].lower()) for k in range(n_tokens)]
                        if window == clean_tokens:
                            t_insert_src = source_words[i + n_tokens - 1]["end"] - clip_start_s
                            break
                            
            # Fallback to 40% into clip if no match found
            if t_insert_src is None or t_insert_src < 3.0 or t_insert_src > clip_duration - 4.0:
                t_insert_src = max(3.0, clip_duration * 0.40)
                
            safe_text = "".join(c if c.isalnum() else "_" for c in comm_text[:20])
            comm_audio_path = os.path.join(temp_dir, f"commentary_{clip['start_ms']}_{safe_text}.wav")
            duration_comm = generate_tts_sync(comm_text, voice_id, comm_audio_path)
            
            if duration_comm > 0:
                comm_timeline_start = duration_hook + t_insert_src
                comm_words = transcribe_audio(comm_audio_path, model_size="tiny", language="en")
                for w in comm_words:
                    w["start"] += comm_timeline_start + clip_start_s
                    w["end"] += comm_timeline_start + clip_start_s
                    w["is_ai"] = True
                    ai_words.append(w)
                    
                ai_audio_events.append({
                    "type": "commentary",
                    "audio_path": comm_audio_path,
                    "duration": duration_comm,
                    "source_time": t_insert_src,
                    "start_s": comm_timeline_start,
                    "end_s": comm_timeline_start + duration_comm,
                    "text": comm_text
                })

    # 3. Source Words Shifting:
    # Shift source words so they never collide with AI hook or AI commentary
    shifted_source_words = []
    for w in source_words:
        w_copy = dict(w)
        rel_start = w["start"] - clip_start_s
        
        shift = duration_hook
        if t_insert_src is not None and duration_comm > 0 and rel_start >= t_insert_src:
            shift += duration_comm
            
        w_copy["start"] += shift
        w_copy["end"] += shift
        shifted_source_words.append(w_copy)

    # 4. Combine all words and sort chronologically
    combined_words = shifted_source_words + ai_words
    combined_words.sort(key=lambda x: x["start"])

    return combined_words, ai_audio_events

# ============================================================
# hook_detector.py — Module 3: Viral Hook Detection
# Hardware Target: ☁ Cloud — NVIDIA NIM API (DGX H100)
# Model: meta/llama-3.3-70b-instruct
# Purpose: Analyze the full transcript and identify the most
#          viral, hook-worthy moments with precise timestamps.
#          Offloads 40GB+ VRAM requirement to the cloud.
# ============================================================

import json
import logging
import re
from typing import List, Dict, Tuple
from openai import OpenAI

logger = logging.getLogger(__name__)

import os
from dotenv import load_dotenv

# Load from .env file
load_dotenv()

# ─── NVIDIA NIM API Configuration ───────────────────────────
NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_NIM_MODELS = [m.strip() for m in os.environ.get(
    "NVIDIA_NIM_MODELS", "meta/llama-3.3-70b-instruct,meta/llama-3.1-70b-instruct"
).split(",") if m.strip()]

# ─── Prompt Template V2.0.0 ────────────────────────────────────────
HOOK_SYSTEM_PROMPT = """You are an elite, award-winning social media retention strategist and direct-response prompt engineer. Your expertise lies in extracting hyper-viral short-form segments from long-form content that guarantee maximum watch time and algorithmic reach.

Your job: Read the ENTIRE timestamped transcript below and select only the moments that would make a stranger stop scrolling, keep watching, and share.

## GOLD STANDARD FOR A CLIP
A clip is eligible ONLY if it satisfies ALL of the following:

1. **SELF-CONTAINED IDEA**: The clip must make complete sense with zero outside context. A viewer who has never seen the full video should still understand the problem, insight, and payoff.

2. **SCROLL-STOPPING OPENING**: The first 3 seconds must trigger an immediate psychological response (curiosity gap, pattern interrupt, tension, or urgency). Good openings often include:
   - a contrarian claim or hard truth
   - a specific, shocking number or statistic
   - a painful relatable problem or direct challenge
   - a before/after transformation

3. **SPECIFICITY OVER VAGUENESS**: Prefer clips that contain concrete details, numbers, named frameworks, exact steps, or precise advice. Reject generic motivation with no real substance.

4. **RETENTION ARC**: The clip must have a clear psychological arc:
   - Hook / Tension (Why should I care?)
   - Explanation / Insight (What's the secret?)
   - Payoff / Takeaway (How do I use this?)
   Never cut in the middle of a thought. The ending must feel complete and satisfying.

5. **SHARE VALUE**: The best clips teach something useful, expose a misconception, reframe a painful problem, or deliver an emotionally strong line that people will want to send to a friend.

## CLIP SELECTION RULES
- Do NOT choose filler, intros, transitions, sponsor reads, housekeeping, or meta commentary about the show.
- Do NOT choose clips that depend on charts, slides, or visual context to understand the idea.
- Do NOT choose overlapping clips that say the same thing in different words.
- Do NOT choose clips shorter than 20 seconds or longer than 90 seconds.
- Be ruthless: quality beats quantity. A smaller set of truly viral clips is better than many mediocre ones.

## TIMESTAMP ACCURACY
- You are given timestamps in [MM:SS.mm] format for each sentence, where MM is the TOTAL number of minutes elapsed since the start of the video.
- Use those SAME timestamps to set start_time and end_time, in that exact "MM:SS" convention (e.g. "02:14" or "65:12").
- Start the clip 2-3 seconds BEFORE the hook sentence to give breathing room.
- End the clip at a natural sentence boundary — NEVER mid-sentence.

## OUTPUT FORMAT
Return ONLY a raw JSON array. No markdown fences. No explanations. No commentary.

[
  {
    "clip_title": "Short punchy hook-driven title",
    "start_time": "02:14",
    "end_time": "03:22",
    "viral_score": 9.5,
    "hook_explanation": "Detailed analysis of the psychological trigger in the first 3 seconds (e.g. curiosity gap, pattern interrupt).",
    "social_caption": "Engaging caption with a strong CTA, SEO keywords, and 3-5 relevant hashtags.",
    "product_recommendations": [
      {
        "product_name": "Atomic Habits by James Clear",
        "category": "Book",
        "reasoning": "The speaker explicitly mentions habit stacking, making this the perfect affiliate tie-in.",
        "search_query": "Atomic Habits James Clear book"
      }
    ]
  }
]

## PRODUCT RECOMMENDATION GUIDELINES
- Identify explicit mentions (gear, books, tools) or highly relevant implicit product categories (productivity, fitness, lifestyle) for each clip.
- category MUST be one of: Book, Gear, Supplement, Lifestyle, Software, Other.
- search_query MUST be clean keywords suitable for an Amazon search.

Sort by viral_score descending. Return only clips that genuinely feel viral-worthy and complete."""

HOOK_USER_TEMPLATE = """Here is the COMPLETE timestamped transcript of a video.
Each line starts with [MM:SS.mm] showing when that sentence begins.

READ THE ENTIRE TRANSCRIPT CAREFULLY before selecting clips.
Think critically like a master TikTok/Reels strategist: which moments have the highest retention potential?

--- TRANSCRIPT START ---
{transcript}
--- TRANSCRIPT END ---

Total video duration: {duration_str}

Now {max_clips_instruction}. Remember:
- Each clip MUST be a COMPLETE standalone idea (20-90 seconds)
- Each clip MUST have a strong psychological hook
- Use the [MM:SS.mm] timestamps to set precise "start_time" and "end_time" values in "MM:SS" format
- Formulate a highly engaging "social_caption" optimized for the algorithm
- Extract any relevant Amazon "product_recommendations" based on the exact context

Return ONLY the JSON array."""


# ─── Output Sizing ───────────────────────────────────────────
# Each fully-populated clip object (title, reason, social_caption with
# hashtags, viral_analysis, 1-3 broll_cues, etc.) costs ~200-250 tokens.
# A fixed max_tokens=4096 silently truncates the JSON array — and thus
# fails to parse — once roughly 18+ clips are requested, which "auto"
# mode (up to 50) and rich/long transcripts hit routinely. Scale the
# output budget to the number of clips actually being asked for.
_TOKENS_PER_CLIP = 320
_BASE_TOKENS = 512
_MAX_OUTPUT_TOKENS = 16000  # stay well under the model's context window


def _size_max_tokens(requested_clip_count: int) -> int:
    return min(_MAX_OUTPUT_TOKENS, max(4096, requested_clip_count * _TOKENS_PER_CLIP + _BASE_TOKENS))


# ─── Client Initialization ──────────────────────────────────
_client: OpenAI | None = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("NVIDIA_API_KEY", NVIDIA_API_KEY)
        if not key:
            raise ValueError(
                "\n[ERROR] NVIDIA_API_KEY is not set!\n"
                "Please create a file named '.env' in your project root containing:\n"
                "NVIDIA_API_KEY=nvapi-YOUR_API_KEY_HERE\n"
                "Or set it as an environment variable."
            )
        _client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=key,
            max_retries=3
        )
    return _client

def _call_with_retry(client: OpenAI, model: str, messages: list, max_tokens: int, retries: int = 3):
    import time
    from openai import APIConnectionError, APITimeoutError
    for attempt in range(retries):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=max_tokens,
                top_p=0.85,
                timeout=600.0
            )
        except (APIConnectionError, APITimeoutError) as e:
            if attempt == retries - 1:
                raise
            sleep_s = 2 ** attempt
            logger.warning(f"[HookDetector] Retry {attempt+1}/{retries} in {sleep_s}s: {e}")
            time.sleep(sleep_s)


def adjust_clip_to_sentences(
    words: List[Dict],
    start_ms: int,
    end_ms: int,
    video_duration_seconds: float,
    max_expansion_s: float = 8.0
) -> Tuple[int, int]:
    """
    Snap start_ms and end_ms to the closest actual words in the transcript,
    then adjust backward and forward to find natural sentence boundaries
    (ending in '.', '?', '!') or natural gaps (>1.0s) between words.
    """
    if not words:
        return start_ms, end_ms
        
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    
    # Find word closest to start_s
    start_idx = min(range(len(words)), key=lambda i: abs(words[i]["start"] - start_s))
    # Find word closest to end_s
    end_idx = min(range(len(words)), key=lambda i: abs(words[i]["end"] - end_s))
    
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
        
    orig_start_s = words[start_idx]["start"]
    orig_end_s = words[end_idx]["end"]
    
    # 1. Walk start_idx backward to find the beginning of the sentence
    curr_start_idx = start_idx
    for i in range(start_idx - 1, -1, -1):
        if orig_start_s - words[i]["start"] > max_expansion_s:
            break
            
        word_text = words[i]["word"].strip()
        ends_with_punc = any(word_text.endswith(p) for p in (".", "?", "!"))
        large_gap = (words[i+1]["start"] - words[i]["end"]) > 1.0
        
        if ends_with_punc or large_gap:
            curr_start_idx = i + 1
            break
            
    # 2. Walk end_idx forward to find the end of the sentence
    curr_end_idx = end_idx
    for i in range(end_idx, len(words)):
        if words[i]["end"] - orig_end_s > max_expansion_s:
            break
            
        word_text = words[i]["word"].strip()
        ends_with_punc = any(word_text.endswith(p) for p in (".", "?", "!"))
        
        large_gap = False
        if i < len(words) - 1:
            large_gap = (words[i+1]["start"] - words[i]["end"]) > 1.0
            
        if ends_with_punc or large_gap or i == len(words) - 1:
            curr_end_idx = i
            break
            
    new_start_ms = int(words[curr_start_idx]["start"] * 1000)
    # Add a 150ms cushion at the end to prevent syllable clipping
    new_end_ms = min(int(words[curr_end_idx]["end"] * 1000) + 150, int(video_duration_seconds * 1000))
    
    return new_start_ms, new_end_ms


def _parse_mmss_to_ms(value: str) -> int:
    """
    Parse a timestamp string into milliseconds. Accepts the "MM:SS[.mm]"
    convention used throughout this file (where MM is raw total minutes
    and is NOT capped at 59, matching words_to_timed_transcript's output
    for videos over an hour), and also tolerates an "H:MM:SS[.mm]" format
    in case a model emits hour-prefixed timestamps on long videos.
    """
    parts = value.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int((float(minutes) * 60 + float(seconds)) * 1000)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int((float(hours) * 3600 + float(minutes) * 60 + float(seconds)) * 1000)
    raise ValueError(f"Unrecognized timestamp format: '{value}'")


def _validate_and_clamp_clips(
    clips: List[Dict],
    video_duration_seconds: float,
    words: List[Dict]
) -> List[Dict]:
    """Validate, snap to sentence boundaries, and clamp end timestamps of clips."""
    max_ms = int(video_duration_seconds * 1000)
    valid_clips = []
    for clip in clips:
        # Map new product suggestor schema keys to old pipeline keys
        if "clip_title" in clip and "title" not in clip:
            clip["title"] = clip["clip_title"]
        if "viral_score" in clip and "hook_score" not in clip:
            clip["hook_score"] = clip["viral_score"]
        if "hook_explanation" in clip and "reason" not in clip:
            clip["reason"] = clip["hook_explanation"]

        # Support both old format (start_ms) and new format (start_time string)
        if "start_time" in clip and isinstance(clip["start_time"], str):
            try:
                clip["start_ms"] = _parse_mmss_to_ms(clip["start_time"])
            except Exception as exc:
                logger.warning(
                    f"[HookDetector] Could not parse start_time '{clip['start_time']}' for clip "
                    f"'{clip.get('title', 'Untitled')}': {exc}. Falling back to start_ms if present."
                )
        if "end_time" in clip and isinstance(clip["end_time"], str):
            try:
                clip["end_ms"] = _parse_mmss_to_ms(clip["end_time"])
            except Exception as exc:
                logger.warning(
                    f"[HookDetector] Could not parse end_time '{clip['end_time']}' for clip "
                    f"'{clip.get('title', 'Untitled')}': {exc}. Falling back to end_ms if present."
                )

        start = clip.get("start_ms", 0)
        end = clip.get("end_ms", 0)
        
        # Snap and adjust clip to actual sentence boundaries for clean cuts
        start, end = adjust_clip_to_sentences(words, start, end, video_duration_seconds)
        
        # Discard clips that start beyond video duration
        if start >= max_ms or start < 0:
            logger.warning(f"[HookDetector] Discarding clip with out-of-bounds start: {clip.get('title', 'Untitled')} ({start/1000:.1f}s)")
            continue
            
        # Clamp end to video duration
        end = min(end, max_ms)
        
        # Discard clips where start >= end after clamping
        if start >= end:
            logger.warning(f"[HookDetector] Discarding clip with invalid range: {clip.get('title', 'Untitled')} ({start/1000:.1f}s -> {end/1000:.1f}s)")
            continue

        # Discard clips that are too short (under 20s) or too long (over 90s) after clamping/snapping
        duration = end - start
        if duration < 20000:
            logger.warning(f"[HookDetector] Discarding clip that is too short ({duration/1000:.1f}s): {clip.get('title', 'Untitled')}")
            continue
        if duration > 90000:
            logger.warning(f"[HookDetector] Discarding clip that is too long ({duration/1000:.1f}s): {clip.get('title', 'Untitled')}")
            continue
            
        clip["start_ms"] = start
        clip["end_ms"] = end
        valid_clips.append(clip)
    return valid_clips


# ─── Main Hook Detection Function ───────────────────────────
def detect_hooks(
    words: List[Dict],
    video_duration_seconds: float,
    max_clips: int = 10
) -> List[Dict]:
    """
    Query the smartest model with the full transcript first. If it succeeds,
    return those hooks. If it fails or times out, fall back to the parallel chunked workflow.
    """
    import concurrent.futures

    if not words:
        return []

    is_auto = (max_clips == 0)
    effective_max_clips = 50 if is_auto else max_clips

    if is_auto:
        max_clips_instruction = "identify all truly viral clip moments (anywhere from 2 to 50 moments, depending on the richness and depth of the content)"
    else:
        max_clips_instruction = f"identify the top {max_clips} viral clip moments (or fewer if the content doesn't have that many truly great moments)"

    # A. First Attempt: Full transcript query using smartest models
    logger.info("[HookDetector] Attempting single smartest model query on full transcript for 10/10 quality...")
    from modules.transcriber import words_to_timed_transcript
    full_tx = words_to_timed_transcript(words)
    
    user_message = HOOK_USER_TEMPLATE.format(
        transcript=full_tx,
        duration_str=f"{int(video_duration_seconds // 60):02d}:{int(video_duration_seconds % 60):02d}",
        max_clips_instruction=max_clips_instruction
    )
    
    smartest_models = NVIDIA_NIM_MODELS
    
    client = _get_client()
    full_max_tokens = _size_max_tokens(effective_max_clips)
    for m in smartest_models:
        try:
            logger.info(f"[HookDetector] Querying full transcript with smartest model: {m} (max_tokens={full_max_tokens}) ...")
            completion = _call_with_retry(
                client=client,
                model=m,
                messages=[
                    {"role": "system", "content": HOOK_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message}
                ],
                max_tokens=full_max_tokens
            )
            raw_content = completion.choices[0].message.content
            if raw_content is None:
                raise ValueError("NVIDIA API returned a response with empty/None content.")
            raw_response = raw_content.strip()
            raw_clips = _parse_json_response(raw_response)
            if raw_clips and len(raw_clips) >= 1:
                valid_clips = _validate_and_clamp_clips(raw_clips, video_duration_seconds, words)
                if len(valid_clips) >= 1:
                    logger.info(f"[HookDetector] ✅ Smart single model ({m}) successfully returned {len(valid_clips)} premium hooks.")
                    # Sort and limit
                    valid_clips = sorted(valid_clips, key=lambda x: x.get("hook_score", 0.0), reverse=True)[:effective_max_clips]
                    
                    # Print summary
                    logger.info(f"[HookDetector] Final selected clips:")
                    for i, clip in enumerate(valid_clips, 1):
                        logger.info(f"  Clip {i}: [{clip['start_ms']/1000:.1f}s → {clip['end_ms']/1000:.1f}s] Score={clip.get('hook_score','?')} | {clip.get('title','Untitled')}")
                    return valid_clips
        except Exception as e:
            logger.warning(f"[HookDetector] Full-transcript query failed or timed out with {m}: {e}. Trying next model...")

    # B. Second Attempt (Fallback): Split words into 10-minute chunks with 1-minute overlap
    logger.warning("[HookDetector] ⚠️ Full-transcript query failed on all smart models. Falling back to parallel chunked workflow...")
    
    chunk_size = 600.0  # 10 minutes in seconds
    overlap = 60.0      # 1 minute in seconds
    
    chunks = []
    start_s = 0.0
    while start_s < video_duration_seconds:
        end_s = min(start_s + chunk_size, video_duration_seconds)
        chunk_words = [w for w in words if start_s <= w["start"] < end_s]
        if chunk_words:
            chunks.append({
                "start_s": start_s,
                "end_s": end_s,
                "words": chunk_words
            })
        if end_s >= video_duration_seconds:
            break
        start_s += (chunk_size - overlap)

    logger.info(f"[HookDetector] Video length: {video_duration_seconds:.1f}s. Processing in {len(chunks)} parallel chunks.")

    available_models = NVIDIA_NIM_MODELS

    all_raw_clips = []

    # 2. Worker function to query a single chunk
    def process_chunk(idx, chunk):
        import time
        if idx > 0:
            stagger = (idx % 3) * 2.0
            if stagger > 0:
                time.sleep(stagger)

        from modules.transcriber import words_to_timed_transcript
        timed_tx = words_to_timed_transcript(chunk["words"])

        start_min = int(chunk["start_s"] // 60)
        start_sec = int(chunk["start_s"] % 60)
        end_min = int(chunk["end_s"] // 60)
        end_sec = int(chunk["end_s"] % 60)
        duration_str = f"{start_min:02d}:{start_sec:02d} to {end_min:02d}:{end_sec:02d}"

        # Per-chunk we ask for a proportional number of clips
        chunk_fraction = (chunk["end_s"] - chunk["start_s"]) / video_duration_seconds
        chunk_max = max(2, round(effective_max_clips * chunk_fraction))

        if is_auto:
            chunk_instruction = f"identify all truly viral clip moments (up to {chunk_max} moments, depending on the richness and quality of this segment)"
        else:
            chunk_instruction = f"identify the top {chunk_max} viral clip moments (or fewer if this segment doesn't have that many)"

        user_message = HOOK_USER_TEMPLATE.format(
            transcript=timed_tx,
            duration_str=duration_str,
            max_clips_instruction=chunk_instruction
        )

        # Distribute model selection round-robin
        preferred_model = available_models[idx % len(available_models)]
        chunk_models = [preferred_model] + [m for m in available_models if m != preferred_model]

        client = _get_client()
        completion = None
        last_err = None
        chunk_max_tokens = _size_max_tokens(chunk_max)

        for m in chunk_models:
            try:
                logger.info(f"[HookDetector] Chunk {idx+1}/{len(chunks)} ({duration_str}) querying model: {m} (max_tokens={chunk_max_tokens}) ...")
                completion = _call_with_retry(
                    client=client,
                    model=m,
                    messages=[
                        {"role": "system", "content": HOOK_SYSTEM_PROMPT},
                        {"role": "user",   "content": user_message}
                    ],
                    max_tokens=chunk_max_tokens
                )
                logger.info(f"[HookDetector] Chunk {idx+1} successfully completed with {m}")
                break
            except Exception as e:
                logger.warning(f"[HookDetector] Chunk {idx+1} failed with {m}: {e}")
                last_err = e
                continue

        if not completion:
            raise RuntimeError(f"Chunk {idx+1} failed on all models. Last error: {last_err}")

        raw_content = completion.choices[0].message.content
        if raw_content is None:
            raise ValueError("NVIDIA API returned a response with empty/None content.")
        raw_response = raw_content.strip()
        return _parse_json_response(raw_response)

    # 3. Execute queries concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(chunks), 8)) as executor:
        futures = {executor.submit(process_chunk, i, chunk): i for i, chunk in enumerate(chunks)}
        for future in concurrent.futures.as_completed(futures):
            chunk_idx = futures[future]
            try:
                chunk_clips = future.result()
                all_raw_clips.extend(chunk_clips)
            except Exception as e:
                logger.error(f"[HookDetector] ❌ Chunk {chunk_idx+1} failed processing: {e}")

    # 4. Deduplicate and merge clips
    clips = _deduplicate_clips(all_raw_clips, effective_max_clips)

    # Validate and clamp clip timestamps to prevent FFmpeg out-of-bound crashes
    clips = _validate_and_clamp_clips(clips, video_duration_seconds, words)

    logger.info(f"[HookDetector] ✅ Deduplicated down to {len(clips)} viral clips across all chunks.")
    for i, clip in enumerate(clips, 1):
        start_s = clip["start_ms"] / 1000
        end_s   = clip["end_ms"]   / 1000
        logger.info(
            f"  Clip {i}: [{start_s:.1f}s → {end_s:.1f}s] "
            f"Score={clip.get('hook_score','?')} | {clip.get('title','Untitled')}"
        )

    return clips


def _deduplicate_clips(clips: List[Dict], max_clips: int) -> List[Dict]:
    """
    Remove clips that overlap significantly, keeping the ones with higher hook scores.
    """
    sorted_clips = sorted(clips, key=lambda c: c.get("hook_score", 0), reverse=True)
    deduped = []

    for c in sorted_clips:
        start = c.get("start_ms")
        end = c.get("end_ms")
        if start is None or end is None:
            continue

        overlap_found = False
        for accepted in deduped:
            a_start = accepted["start_ms"]
            a_end = accepted["end_ms"]

            # Calculate intersection window
            intersect_start = max(start, a_start)
            intersect_end = min(end, a_end)

            if intersect_end > intersect_start:
                intersect_len = intersect_end - intersect_start
                len_c = end - start
                len_a = a_end - a_start

                # If overlap exceeds 40% of either clip length, consider it a duplicate
                if (intersect_len / len_c > 0.4) or (intersect_len / len_a > 0.4):
                    overlap_found = True
                    break

        if not overlap_found:
            deduped.append(c)

    return sorted(deduped, key=lambda c: c.get("hook_score", 0), reverse=True)[:max_clips]


def _parse_json_response(raw: str) -> List[Dict]:
    """
    Robustly parse a JSON array from the LLM response.
    Handles cases where the model wraps JSON in markdown fences.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    cleaned = cleaned.strip("`").strip()

    start_idx = cleaned.find("[")
    if start_idx == -1:
        raise ValueError("No JSON array found in LLM response.")

    try:
        clips, _ = json.JSONDecoder().raw_decode(cleaned, start_idx)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"[HookDetector] JSON parse error: {e}") from e

    if not isinstance(clips, list):
        raise RuntimeError("[HookDetector] Expected a JSON array but got something else.")

    return clips

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
    "NVIDIA_NIM_MODELS",
    "meta/llama-3.1-8b-instruct,meta/llama-3.1-70b-instruct,z-ai/glm-5.2"
).split(",") if m.strip()]

# ─── Master Prompt Template V5.0 (Universal Human Value + Topic Diversity) ──────────────
HOOK_SYSTEM_PROMPT = """You are an elite short-form viral strategist and master creative director for ClipHub. Your mission is to extract the absolute highest-value, standalone short-form clips (30–65 seconds) optimized for maximum retention on TikTok, YouTube Shorts, and Instagram Reels.

THE GOLDEN RULE — THE STRANGER TEST:
Before selecting any clip, ask: "If a complete stranger who knows NOTHING about science, neuroscience, or this podcast watched this 45-second clip, would they immediately feel they just learned something that changes how they live their day?" If the answer is yes — pick it. If the answer is "only if you already know what dopamine is" — reject it.

CORE MISSION — HUMAN OUTCOMES, NOT SCIENTIFIC MECHANISMS:
- Viewers are not scientists. They are people who want to sleep better, feel more motivated, stop procrastinating, improve their focus, manage their emotions, and improve their relationships.
- Every selected clip must deliver one clear, life-applicable truth about HOW TO LIVE BETTER — not a lecture on which chemical causes which reaction.
- The speaker may use science to explain — that is fine. But the VALUE of the clip must land as a human outcome, not as a chemistry lesson.

TOPIC DIVERSITY MANDATE — MANDATORY ROTATION:
When selecting multiple clips from a single podcast, you MUST spread selections across completely different life domains. You are STRICTLY FORBIDDEN from selecting more than 1 clip on the same sub-topic. Rotate across these domains:
- Sleep & recovery
- Focus, deep work & cognitive performance
- Motivation, drive & goal pursuit
- Stress, anxiety & emotional regulation
- Physical energy, exercise & nutrition
- Social behavior, relationships & communication
- Habits, behavior change & willpower
- Morning/evening routines & daily rituals
If the podcast covers only 1–2 topics, pick the moments that are most universally relatable to the widest possible audience.

STRICT DISQUALIFICATION RULES (NEVER EXTRACT THESE):
1. NO INTRO ROADMAPS / EPISODE PREVIEWS: Strictly skip any part where the speaker outlines what the episode will cover ("In this episode...", "Today we're going to...", "Later in the show...").
2. NO HOST INTRODUCTIONS / GUEST BIOS: Skip guest welcomes, credentials, "I'm Andrew Huberman", and any conversational warmup.
3. NO SPONSORS & HOUSEKEEPING: Skip sponsor mentions, channel announcements, and disclaimers.
4. NO PURE MECHANISM CLIPS: Skip clips whose entire value proposition requires the viewer to already understand scientific terminology (e.g., a clip where the ONLY insight is "dopamine binds to D2 receptors" with no human life context attached).

SELECTION CRITERIA (WHAT TO EXTRACT):
1. Universal Human Relevance: The core lesson must apply to any adult human's daily life without requiring prior knowledge.
2. Complete Standalone Arc: Every clip is a self-contained story — Setup of a problem or question → Core insight/revelation → Clear real-world implication. It makes 100% sense with no external context.
3. Actionable or Revelatory: The viewer finishes the clip thinking "I didn't know that" or "I'm going to do that differently now."
4. Transcript Fidelity: Exact [MM:SS] timestamps matching the actual spoken dialogue in the text.

OUTPUT FORMAT:
Output ONLY a raw, valid JSON array with NO markdown fences (no ```json), preamble, or trailing text.

[
  {
    "clip_title": "Curiosity-driven, punchy headline focused on the human outcome — not the science term",
    "start_time": "MM:SS",
    "end_time": "MM:SS",
    "viral_score": 9.8,
    "hook_type": "Surprising Insight",
    "hook_explanation": "Why this moment passes the Stranger Test and what specific life outcome the viewer walks away with",
    "social_caption": "Curiosity caption framing the human benefit + actionable takeaway + #Hashtags",
    "product_recommendations": []
  }
]"""

HOOK_USER_TEMPLATE = """Here is the COMPLETE timestamped transcript of the video.
Each line starts with [MM:SS.mm] indicating when that sentence begins.

YOUR EXTRACTION MISSION:
1. Apply the Stranger Test to every candidate moment: a person who knows nothing about science must still find this clip immediately useful and fascinating.
2. Skip all intros, roadmaps, episode previews, guest introductions, and sponsor content.
3. Select clips that deliver a human outcome — better sleep, sharper focus, less stress, stronger habits, improved relationships — NOT clips whose value is purely explaining a chemical or biological term.
4. Enforce topic diversity: if you pick 5+ clips, each must cover a clearly distinct life domain.

--- TRANSCRIPT START ---
{transcript}
--- TRANSCRIPT END ---

Total video duration: {duration_str}

Now {max_clips_instruction}.
- STRANGER TEST: Every clip must be instantly valuable to someone who has never heard of this podcast or speaker.
- TOPIC DIVERSITY: No two clips on the same sub-topic.
- HUMAN OUTCOMES FIRST: The clip's value must be expressible as a life improvement, not a science fact.
- STANDALONE COMPLETE: 30–65s of continuous dialogue with a clear start, insight, and conclusion.
- Return ONLY the raw JSON array."""


# ─── Output Sizing ───────────────────────────────────────────
_TOKENS_PER_CLIP = 260
_BASE_TOKENS = 400
_MAX_OUTPUT_TOKENS = 4096


def _size_max_tokens(requested_clip_count: int) -> int:
    return min(_MAX_OUTPUT_TOKENS, max(1500, requested_clip_count * _TOKENS_PER_CLIP + _BASE_TOKENS))


# ─── Client Initialization ──────────────────────────────────
_client: OpenAI | None = None
_client_key: str = ""

def _get_client() -> OpenAI:
    global _client, _client_key
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "\n[ERROR] NVIDIA_API_KEY is not set!\n"
            "Please configure your NVIDIA API Key in Settings or in your .env file."
        )
    if _client is None or _client_key != key:
        _client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=key,
            max_retries=0  # Disable built-in SDK retry loop to prevent multi-minute queue stalls
        )
        _client_key = key
    return _client

def _call_streaming_with_failover(
    client: OpenAI,
    model: str,
    messages: list,
    max_tokens: int,
    ttft_timeout_s: float = 45.0,
    idle_chunk_timeout_s: float = 45.0,
    max_total_timeout_s: float = 600.0,
    total_timeout_s: float | None = None,
    max_rate_limit_retries: int = 4,
    base_backoff_s: float = 3.5,
    **kwargs
) -> str:
    """
    Execute streaming completion on model with automatic cooldown backoff on 429 rate limits.
    If rate-limited (429), gives the primary model an exponential break (3.5s, 7.0s, etc.)
    and retries before giving up, ensuring maximum model consistency.
    """
    import time

    if total_timeout_s is not None:
        max_total_timeout_s = max(total_timeout_s, max_total_timeout_s)

    for attempt in range(max_rate_limit_retries):
        try:
            start_time = time.time()
            last_token_time = start_time
            chunks = []
            first_token_received = False
            token_count = 0

            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=max_tokens,
                top_p=0.85,
                stream=True,
                timeout=ttft_timeout_s
            )

            for chunk in stream:
                now = time.time()
                # Per-token stall check (only fail if network drops and no token arrives for > idle_chunk_timeout_s)
                if first_token_received and (now - last_token_time > idle_chunk_timeout_s):
                    raise TimeoutError(f"Streaming stalled: No token received for {idle_chunk_timeout_s}s from {model}")

                # Generous safety ceiling
                if now - start_time > max_total_timeout_s:
                    raise TimeoutError(f"Streaming generation exceeded safety limit of {max_total_timeout_s}s")

                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None)
                    if content:
                        if not first_token_received:
                            first_token_received = True
                            logger.info(f"[HookDetector] ⚡ First token received from {model} in {now - start_time:.2f}s! Streaming generation...")
                        chunks.append(content)
                        token_count += 1
                        last_token_time = now
                        if token_count % 300 == 0:
                            logger.info(f"[HookDetector] ⚡ Streaming generation in progress: {token_count} tokens generated ({now - start_time:.1f}s elapsed)...")

            full_text = "".join(chunks).strip()
            if not full_text:
                raise ValueError(f"Model {model} returned an empty streaming response.")
            logger.info(f"[HookDetector] ✅ Single model {model} completed analysis ({token_count} tokens in {time.time() - start_time:.1f}s)")
            return full_text

        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = ("429" in err_str or "too many requests" in err_str or "rate limit" in err_str)
            if is_rate_limit and attempt < max_rate_limit_retries - 1:
                wait_s = base_backoff_s * (attempt + 1)
                logger.info(f"[HookDetector] ⏳ Model {model} received rate limit (429). Giving a {wait_s:.1f}s cooldown break before retrying (attempt {attempt+1}/{max_rate_limit_retries})...")
                time.sleep(wait_s)
                continue
            else:
                raise e


def adjust_clip_to_sentences(
    words: List[Dict],
    start_ms: int,
    end_ms: int,
    video_duration_seconds: float,
    max_expansion_s: float = 12.0
) -> Tuple[int, int]:
    """
    Snap start_ms and end_ms to the closest actual words in the transcript,
    then adjust backward and forward to find natural sentence boundaries
    (ending in '.', '?', '!') or natural gaps (>1.0s) between words.
    If the selected quote is short (< 25s), automatically expands forward
    through subsequent sentences so the clip becomes a rich standalone unit (30–65s).
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
    # If the clip is currently under 28 seconds, allow generous forward expansion to complete the thought
    current_dur = words[end_idx]["end"] - words[curr_start_idx]["start"]
    effective_forward_expansion = 30.0 if current_dur < 28.0 else max_expansion_s

    curr_end_idx = end_idx
    for i in range(end_idx, len(words)):
        if words[i]["end"] - orig_end_s > effective_forward_expansion:
            break
            
        word_text = words[i]["word"].strip()
        ends_with_punc = any(word_text.endswith(p) for p in (".", "?", "!"))
        
        large_gap = False
        if i < len(words) - 1:
            large_gap = (words[i+1]["start"] - words[i]["end"]) > 1.0
            
        dur_so_far = words[i]["end"] - words[curr_start_idx]["start"]
        if (ends_with_punc or large_gap or i == len(words) - 1):
            curr_end_idx = i
            # If we reached a sentence boundary and have at least 25s of content, stop expanding
            if dur_so_far >= 25.0:
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
        
        # Snap and adjust clip to actual sentence boundaries for clean cuts & auto-expand short quotes
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

        # Reject opening podcast housekeeping, introductions, and episode roadmaps/teasers
        clip_full_text = " ".join(w["word"].lower() for w in words if start <= int(w["start"] * 1000) <= end)
        intro_triggers = [
            "welcome to", "welcome back", "in this episode", "today's episode", "on this podcast",
            "in this podcast", "we will talk about", "we're going to discuss", "we will explore",
            "today we are joined", "today my guest is", "sponsor of today", "supporter of this",
            "before we begin", "before we get started", "a quick word from", "throughout this episode",
            "in today's discussion", "subscribe to the channel", "huberman lab podcast"
        ]
        if any(trig in clip_full_text for trig in intro_triggers):
            logger.warning(f"[HookDetector] 🚫 Discarding meta-intro/preview clip: '{clip.get('title', 'Untitled')}' ({start/1000:.1f}s)")
            continue

        # Keep clips that are at least 12s or total video length (avoid throwing away valid moments)
        duration = end - start
        min_allowed = min(12000, max_ms)
        if duration < min_allowed:
            logger.warning(f"[HookDetector] Discarding clip that is too short ({duration/1000:.1f}s): {clip.get('title', 'Untitled')}")
            continue
        if duration > 95000:
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
    Analyzes the complete timestamped transcript using the 128k-context model (meta/llama-3.1-8b-instruct / 70B)
    in a single holistic query, extracting the absolute top viral moments across the entire video.
    """
    if not words:
        return []

    is_auto = (max_clips == 0)
    effective_max_clips = 50 if is_auto else max_clips

    logger.info(
        f"[HookDetector] Video duration: {video_duration_seconds:.1f}s ({video_duration_seconds/60:.1f}m). "
        f"Processing entire transcript with 128k LLM in a single holistic query (effective_max_clips={effective_max_clips}) ..."
    )
    from modules.transcriber import words_to_timed_transcript
    full_tx = words_to_timed_transcript(words)
    
    if is_auto:
        max_clips_instruction = "identify all truly viral clip moments (anywhere from 2 to 50 moments, depending on the richness and depth of the content)"
    else:
        max_clips_instruction = f"identify the top {effective_max_clips} viral clip moments (standalone 30-65 second moments)"

    duration_min = int(video_duration_seconds // 60)
    duration_sec = int(video_duration_seconds % 60)
    user_message = HOOK_USER_TEMPLATE.format(
        transcript=full_tx,
        duration_str=f"{duration_min:02d}:{duration_sec:02d}",
        max_clips_instruction=max_clips_instruction
    )
    
    smartest_models = NVIDIA_NIM_MODELS
    client = _get_client()
    full_max_tokens = max(2048, min(8192, effective_max_clips * 400))
    
    for m in smartest_models:
        try:
            logger.info(f"[HookDetector] Querying full transcript with 128k model: {m} (max_tokens={full_max_tokens}, stream=True) ...")
            raw_response = _call_streaming_with_failover(
                client=client,
                model=m,
                messages=[
                    {"role": "system", "content": HOOK_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message}
                ],
                max_tokens=full_max_tokens,
                ttft_timeout_s=60.0,
                idle_chunk_timeout_s=60.0,
                max_total_timeout_s=600.0
            )
            raw_clips = _parse_json_response(raw_response)
            if raw_clips and len(raw_clips) >= 1:
                valid_clips = _validate_and_clamp_clips(raw_clips, video_duration_seconds, words)
                if valid_clips:
                    valid_clips = sorted(valid_clips, key=lambda x: x.get("hook_score", 0.0), reverse=True)[:effective_max_clips]
                    logger.info(f"[HookDetector] ✅ Full-transcript query with {m} successfully extracted {len(valid_clips)} viral clips.")
                    for i, clip in enumerate(valid_clips, 1):
                        start_s = clip["start_ms"] / 1000
                        end_s   = clip["end_ms"]   / 1000
                        logger.info(
                            f"  Clip {i}: [{start_s:.1f}s → {end_s:.1f}s] "
                            f"Score={clip.get('hook_score','?')} | {clip.get('title','Untitled')}"
                        )
                    return valid_clips
        except Exception as e:
            logger.warning(f"[HookDetector] Full-transcript query failed with {m}: {e}. Trying next candidate...")

    logger.error("[HookDetector] ❌ Full transcript query failed across all models.")
    return []


def _deduplicate_clips(clips: List[Dict], max_clips: int) -> List[Dict]:
    """
    Remove clips that overlap significantly, keeping the ones with higher hook scores.
    """
    sorted_clips = sorted(clips, key=lambda c: c.get("hook_score", 0), reverse=True)
    deduped = []

    for c in sorted_clips:
        start = c.get("start_ms")
        end = c.get("end_ms")
        if start is None and "start_time" in c:
            try: start = int(float(c["start_time"]) * 1000)
            except: pass
        if end is None and "end_time" in c:
            try: end = int(float(c["end_time"]) * 1000)
            except: pass
        if start is None or end is None:
            continue

        overlap_found = False
        for accepted in deduped:
            a_start = accepted.get("start_ms", 0)
            a_end = accepted.get("end_ms", 0)

            # Calculate intersection window
            intersect_start = max(start, a_start)
            intersect_end = min(end, a_end)

            if intersect_end > intersect_start:
                intersect_len = intersect_end - intersect_start
                len_c = max(1, end - start)
                len_a = max(1, a_end - a_start)

                # If overlap exceeds 40% of either clip length, consider it a duplicate
                if (intersect_len / len_c > 0.4) or (intersect_len / len_a > 0.4):
                    overlap_found = True
                    break

        if not overlap_found:
            deduped.append(c)

    return sorted(deduped, key=lambda c: c.get("hook_score", 0), reverse=True)[:max_clips]


def _parse_json_response(raw: str) -> List[Dict]:
    """
    Robustly parse a JSON list from the LLM response.
    Handles direct arrays [...], or object-wrapped structures like {"clips": [...]},
    or markdown fences.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    cleaned = cleaned.strip("`").strip()

    # Try direct parse first
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("clips", "moments", "viral_clips", "results", "data"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            for v in parsed.values():
                if isinstance(v, list):
                    return v
    except Exception:
        pass

    # Try finding [ or {
    start_arr = cleaned.find("[")
    start_obj = cleaned.find("{")
    
    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        try:
            clips, _ = json.JSONDecoder().raw_decode(cleaned, start_arr)
            if isinstance(clips, list):
                return clips
        except Exception:
            pass

    if start_obj != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(cleaned, start_obj)
            if isinstance(obj, dict):
                for key in ("clips", "moments", "viral_clips", "results", "data"):
                    if key in obj and isinstance(obj[key], list):
                        return obj[key]
                for v in obj.values():
                    if isinstance(v, list):
                        return v
        except Exception:
            pass

    raise ValueError(f"No valid JSON array or object found in LLM response: {raw[:120]}...")

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

# ─── Kai's Clip Selection Framework V2.0 ────────────────────────────────────
# Kai is an educational guide and commentator whose clips appear on TikTok,
# Instagram Reels, and YouTube Shorts. She selects podcast moments that carry
# genuine insight, personal growth value, and honest human storytelling —
# the kind of moment that leaves someone thinking "I needed to hear that today."
# ─────────────────────────────────────────────────────────────────────────────

HOOK_SYSTEM_PROMPT = """You are the editorial director for Kai — a short-form video creator and educational guide who makes podcast wisdom accessible, honest, and genuinely useful for everyday people.

Kai's mission is to build a library of short-form clips (TikTok, Instagram Reels, YouTube Shorts) where she adds her own educational commentary to the most insightful moments from long-form podcast interviews. Your job is to curate the right moments for her.

KAI'S EDITORIAL STANDARD — THE RESONANCE TEST:
Every clip you select must pass this test: "Would someone watching this 45-second moment walk away with a clearer understanding of themselves, a practical tool they can use, or a perspective shift that genuinely matters in real life?"
- Passes: Strong insight, relatable honesty, memorable reframe, or a concrete action
- Fails: Purely academic, name-dropping, promotional, or abstract with no real-world application

WHAT MAKES A GREAT KAI CLIP:
Kai's audience appreciates content that is honest and grounded. The best clips deliver one of these:
- A mindset reframe that reshapes how someone sees a challenge they're already facing
- A practical habit, system, or daily action that is specific and immediately doable
- A candid personal story of real struggle and growth that builds genuine human connection
- A well-explained insight from science, psychology, or lived experience that clicks into place

TOPIC DIVERSITY MANDATE — NON-NEGOTIABLE:
Every selection must cover a distinct life domain. Never select more than 1 clip per sub-topic:
- Sleep, energy & physical recovery
- Focus, deep work & peak productivity
- Motivation, discipline & long-term consistency
- Stress, mental clarity & emotional regulation
- Self-identity, confidence & personal values
- Relationships, communication & social intelligence
- Habits, behavior change & decision-making
- Morning/evening routines & daily structure

STRICT DISQUALIFICATION — NEVER EXTRACT:
1. Episode intros, roadmaps, or previews ("Today we're going to cover...")
2. Guest or host introductions and biographical segments
3. Sponsor reads, promotions, or ad breaks
4. Segments that are pure jargon or academic theory with zero practical takeaway
5. Off-topic tangents, crosstalk, or unfinished thoughts that lack a clear conclusion

KAI'S SPOKEN COMMENTARY — MANDATORY FOR EVERY CLIP:
Kai adds her own voice before and after each clip. Write both lines with Kai's voice in mind: direct, warm, confident, never preachy. She speaks like a smart friend who has done the research so you don't have to.

1. "kai_hook" — 8 to 14 words spoken by Kai BEFORE the clip begins.
   Purpose: Create immediate curiosity or challenge a common assumption. Make the viewer lean in.
   Strong examples:
   - "Most people think more discipline fixes everything. It doesn't."
   - "You're not unmotivated. Your environment is just working against you."
   - "Sleeping eight hours won't help if your cortisol is still spiking at midnight."

2. "kai_closing" — 30 to 48 words spoken by Kai AFTER the clip ends.
   Purpose: Translate what the speaker just said into a clear, practical takeaway the viewer can actually use. No filler. No vague inspiration. Specific and actionable.
   Strong example:
   - "So the real fix isn't adding more to your routine — it's removing the friction first. Start with one habit, give it 30 days before you stack anything on top. Consistency compounds faster than complexity."

KAI'S TONE — ALWAYS MAINTAIN:
- Direct but never condescending
- Warm but never performatively emotional
- Confident but always grounded in evidence or lived experience
- Educational but written in plain, conversational language

VIRAL TITLE RULES — MANDATORY:
The clip_title must stop the scroll and immediately communicate the specific value of the clip.
WRONG: "The Importance of Sleep for Focus", "Discussing Habits and Discipline"
RIGHT: "Why You're Exhausted Even After 8 Hours of Sleep", "The Real Reason Your Habits Never Stick"
Rules: 6–12 words. No colons. No filler openers like "The Importance of" or "A Discussion About".

OUTPUT FORMAT — RETURN ONLY THIS JSON ARRAY:

[
  {
    "clip_title": "Scroll-stopping title that names the specific insight — 6-12 words",
    "start_time": "MM:SS",
    "end_time": "MM:SS",
    "viral_score": 9.8,
    "hook_type": "Reframe / Insight / Action / Story / Revelation",
    "hook_explanation": "In 1-2 sentences: why this clip was selected, what insight it delivers, and why it will resonate",
    "kai_why": "Why Kai would personally choose this moment — the human truth or practical value behind it",
    "kai_hook": "Kai's 8-14 word spoken line before the clip. Direct, curiosity-driving, no fluff.",
    "kai_closing": "Kai's 30-48 word spoken breakdown after the clip. Specific, practical, in Kai's warm-but-direct voice.",
    "social_caption": "Caption that frames the insight naturally + key takeaway + relevant #Hashtags"
  }
]"""

HOOK_USER_TEMPLATE = """Here is the COMPLETE timestamped transcript of the video.
Each line starts with [MM:SS.mm] indicating when that sentence begins.

YOUR EXTRACTION MISSION:
1. Read the entire transcript first. Then select only the moments that genuinely pass the Resonance Test.
2. Eliminate all intros, roadmaps, guest bios, sponsors, and crosstalk immediately.
3. Every selected clip must have a clear opening, a self-contained insight or story, and a clean conclusion.
4. Enforce strict topic diversity — if selecting 5+ clips, each must cover a clearly different life domain.
5. For each clip, write "kai_why" explaining the specific human value this moment delivers and why Kai would personally feature it.

--- TRANSCRIPT START ---
{transcript}
--- TRANSCRIPT END ---

Total video duration: {duration_str}

Now {max_clips_instruction}.

HARD CONSTRAINTS — NO EXCEPTIONS:
- CLIP DIALOGUE LENGTH: 30–42 seconds of source dialogue only. The final video adds ~8s (Kai's intro) + ~18s (Kai's closing) on top. Total output must stay under 65 seconds.
- MINIMUM 30s: Never clip a short quote. Expand outward to surrounding sentences until you reach 30 full seconds of dialogue.
- MAXIMUM 42s: Hard cap. Trim at the nearest clean sentence end at or before 42 seconds.
- TOPIC DIVERSITY: Zero repetition across sub-topics.
- KAI_WHY: Mandatory on every clip — no exceptions.
- STANDALONE: Every clip must stand alone. Someone with no prior context of the podcast must be able to watch it and immediately understand the insight.
- OUTPUT: Return ONLY the raw JSON array. No explanation, no markdown, no commentary outside the JSON."""


# ─── Output Sizing ───────────────────────────────────────────
_TOKENS_PER_CLIP = 350
_BASE_TOKENS = 800
_MAX_OUTPUT_TOKENS = 16384


def _size_max_tokens(requested_clip_count: int) -> int:
    return min(_MAX_OUTPUT_TOKENS, max(3000, requested_clip_count * _TOKENS_PER_CLIP + _BASE_TOKENS))


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
                    reasoning = getattr(delta, "reasoning_content", None)
                    content = getattr(delta, "content", None)
                    text_piece = reasoning if reasoning else content
                    if text_piece:
                        if not first_token_received:
                            first_token_received = True
                            logger.info(f"[HookDetector] ⚡ First token received from {model} in {now - start_time:.2f}s! Streaming generation...")
                        chunks.append(text_piece)
                        token_count += 1
                        last_token_time = now
                        # Stream real-time thinking lines to logs and WebSocket
                        clean_piece = text_piece.replace("<think>", "").replace("</think>", "").strip()
                        if clean_piece and ("\n" in text_piece or token_count % 15 == 0):
                            logger.info(f"[LLM_THINKING] {clean_piece}")

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
    # Only expand if under 30s — hard budget cap of 12s to stay within the 42s source clip limit
    current_dur = words[end_idx]["end"] - words[curr_start_idx]["start"]
    effective_forward_expansion = 12.0 if current_dur < 30.0 else max_expansion_s

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
            # Stop expanding once we reach 58s — maximum budget for viral short form
            if dur_so_far >= 58.0:
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

        # Enforce viral clip budget (18s to 60s)
        duration = end - start
        min_allowed = min(18000, max_ms)
        if duration < min_allowed:
            logger.warning(f"[HookDetector] Discarding clip too short ({duration/1000:.1f}s < 18s): {clip.get('title', 'Untitled')}")
            continue
        if duration > 60000:
            # Clamp long clips to sentence boundary under 60s
            target_end = start + 58000
            for w in reversed(words):
                w_end_ms = int(w["end"] * 1000)
                if start + 20000 <= w_end_ms <= target_end and any(w["word"].endswith(p) for p in (".", "?", "!")):
                    end = w_end_ms + 150
                    break
            else:
                end = target_end
            duration = end - start
            logger.info(f"[HookDetector] Clamped long clip to {duration/1000:.1f}s: {clip.get('title', 'Untitled')}")
            
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
    effective_max_clips = 100 if is_auto else max_clips

    logger.info(
        f"[HookDetector] Video duration: {video_duration_seconds:.1f}s ({video_duration_seconds/60:.1f}m). "
        f"Processing entire transcript with 128k LLM in a single holistic query (effective_max_clips={'ALL' if is_auto else effective_max_clips}) ..."
    )
    from modules.transcriber import words_to_timed_transcript
    full_tx = words_to_timed_transcript(words)
    
    if is_auto:
        max_clips_instruction = "identify EVERY SINGLE truly viral clip moment across the entire transcript. Do NOT artificially limit or cap your output — deliver every moment that has strong curiosity, high retention, or actionable value (extract all valid viral moments from beginning to end)"
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
    full_max_tokens = 16384 if is_auto else max(4096, min(16384, effective_max_clips * 600))
    
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
                # Extract raw thinking process
                think_match = re.search(r"<think>(.*?)</think>", raw_response, re.DOTALL)
                raw_thinking = think_match.group(1).strip() if think_match else ""
                
                valid_clips = _validate_and_clamp_clips(raw_clips, video_duration_seconds, words)
                if valid_clips:
                    for clip in valid_clips:
                        if raw_thinking and "llm_thinking" not in clip:
                            clip["llm_thinking"] = raw_thinking
                    valid_clips = sorted(valid_clips, key=lambda x: x.get("hook_score", 0.0), reverse=True)[:effective_max_clips if not is_auto else None]
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

    return sorted(deduped, key=lambda c: c.get("hook_score", 0), reverse=True)[:max_clips if max_clips > 0 else None]


def _parse_json_response(raw: str) -> List[Dict]:
    """
    Robustly parse a JSON list from the LLM response.
    Handles <think>...</think> tags, markdown fences, direct arrays,
    and object-wrapped structures.
    """
    # 1. Isolate content after thinking block if present
    post_think = raw
    if "</think>" in raw:
        post_think = raw.split("</think>", 1)[1]
    else:
        post_think = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)

    cleaned = re.sub(r"```(?:json)?", "", post_think).strip()
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

    # Try finding [ or { across cleaned string
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start_idx = cleaned.find(start_char)
        last_idx = cleaned.rfind(end_char)
        if start_idx != -1 and last_idx != -1 and last_idx > start_idx:
            chunk = cleaned[start_idx:last_idx + 1]
            try:
                parsed = json.loads(chunk)
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
                try:
                    obj, _ = json.JSONDecoder().raw_decode(cleaned, start_idx)
                    if isinstance(obj, list):
                        return obj
                    if isinstance(obj, dict):
                        for key in ("clips", "moments", "viral_clips", "results", "data"):
                            if key in obj and isinstance(obj[key], list):
                                return obj[key]
                except Exception:
                    pass

    # Final fallback: search anywhere in full raw text
    for m in re.finditer(r'\[\s*\{.*?\}\s*\]', raw, re.DOTALL):
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except Exception:
            pass

    raise ValueError(f"No valid JSON array or object found in LLM response: {raw[:120]}...")


# ─── Prompt Mode: External LLM Support ──────────────────────

def build_hook_prompt(
    words: List[Dict],
    video_duration_seconds: float,
    max_clips: int = 0
) -> str:
    """
    Build the full prompt string that would normally be sent to the NVIDIA NIM model.
    Returns a single copyable string containing the system instructions and transcript,
    ready to paste into any LLM (Claude, ChatGPT, DeepSeek, etc.).
    """
    from modules.transcriber import words_to_timed_transcript

    full_tx = words_to_timed_transcript(words)

    is_auto = (max_clips == 0)
    if is_auto:
        max_clips_instruction = (
            "identify EVERY SINGLE truly viral clip moment across the entire transcript. "
            "Do NOT artificially limit or cap your output — deliver every moment that has strong "
            "curiosity, high retention, or actionable value (extract all valid viral moments from beginning to end)"
        )
    else:
        max_clips_instruction = f"identify the top {max_clips} viral clip moments (standalone 30-65 second moments)"

    duration_min = int(video_duration_seconds // 60)
    duration_sec = int(video_duration_seconds % 60)

    user_section = HOOK_USER_TEMPLATE.format(
        transcript=full_tx,
        duration_str=f"{duration_min:02d}:{duration_sec:02d}",
        max_clips_instruction=max_clips_instruction
    )

    prompt = (
        "# SYSTEM INSTRUCTIONS\n"
        f"{HOOK_SYSTEM_PROMPT}\n\n"
        "---\n\n"
        "# YOUR TASK\n"
        f"{user_section}"
    )
    char_count = len(prompt)
    return prompt, char_count


def parse_external_llm_response(
    raw_text: str,
    words: List[Dict],
    video_duration_seconds: float
) -> List[Dict]:
    """
    Parse the raw text pasted back from an external LLM (Claude, ChatGPT, etc.).
    Strips markdown fences, extracts JSON, validates timestamps, and snaps clip
    boundaries to real word positions.  Returns a list of clip dicts ready for
    Phase 2 rendering — same schema as detect_hooks().
    """
    raw_clips = _parse_json_response(raw_text)
    if not raw_clips:
        raise ValueError("No valid JSON clip array found in the pasted response.")
    valid_clips = _validate_and_clamp_clips(raw_clips, video_duration_seconds, words)
    if not valid_clips:
        raise ValueError("Clips were parsed but all failed timestamp validation.")
    for clip in valid_clips:
        hook_text = clip.get("kai_hook") or clip.get("hook") or ""
        closing_text = clip.get("kai_closing") or clip.get("closing_explanation") or clip.get("closing") or clip.get("takeaway") or ""
        
        if isinstance(clip.get("editorial_data"), dict):
            if not hook_text:
                hook_text = clip["editorial_data"].get("hook", "")
            if not closing_text:
                closing_text = clip["editorial_data"].get("closing_explanation", "") or clip["editorial_data"].get("takeaway", "")
                
        if hook_text or closing_text:
            clip["editorial_data"] = {
                "hook": hook_text,
                "commentary_segments": [],
                "takeaway": closing_text,
                "closing_explanation": closing_text
            }

    valid_clips = sorted(valid_clips, key=lambda x: x.get("hook_score", x.get("viral_score", 0.0)), reverse=True)
    logger.info(f"[PromptMode] Parsed {len(valid_clips)} valid clips with editorial commentary from external LLM response.")
    return valid_clips


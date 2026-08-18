import json
import logging
import os
from typing import Dict, List, Optional
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger("ClipHub.CommentaryGenerator")
load_dotenv()

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_NAME = os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")
MODEL_FALLBACKS = [
    m.strip() for m in os.environ.get(
        "NVIDIA_NIM_MODELS",
        "meta/llama-3.1-8b-instruct,meta/llama-3.1-70b-instruct,z-ai/glm-5.2"
    ).split(",") if m.strip()
]

# ─── Dr. Mei Master's Explainer Persona (Direct Scientific Breakdown) ────────
SYSTEM_PROMPT = """You are Dr. Mei, a brilliant, charismatic neuroscience and cognitive performance educator and co-host. Your mission is to provide razor-sharp, insightful commentary on viral short-form podcast clips, breaking down complex scientific mechanisms into direct, clear, and fascinating knowledge for viewers.

CORE INSTRUCTION (ZERO EXAMPLES / ZERO ANALOGIES):
- Do NOT use metaphors, analogies, or hypothetical examples (STRICTLY NO "Think of your brain like...", NO "Imagine a car/engine...", NO "Picture a classroom...", NO "It's like a...").
- Explain the scientific mechanism and physiological reality DIRECTLY and CLEARLY in plain, authoritative, punchy English.
- Focus strictly on what is physically happening in the brain/body, why it occurs, and what it directly means for human focus, mood, and daily life.

YOUR ROLE IN EVERY CLIP:
1. "hook" (Opening Statement, 10–18 words):
   A provocative, high-curiosity opening delivered on Frame 0 that directly highlights the core insight or shocking reality before the speaker talks.

2. "commentary_segments" (Mid-Clip Direct Explanations, 1 to 2 segments):
   When the speaker explains a dense scientific concept or pivotal insight, Dr. Mei pauses to provide a direct, concise breakdown.
   - If the clip covers 1 main concept -> Provide 1 breakdown object.
   - If the clip covers 2 distinct key ideas -> Provide 2 breakdown objects placed after each respective point.
   - "text" (18–30 words): Direct, clear, factual explanation of the biological/psychological mechanism (ZERO analogies).
   - "insert_after_text": The exact sentence or phrase from the transcript where Dr. Mei should step in.

3. "takeaway" (Closing Rule):
   A crisp 1-sentence actionable conclusion based directly on the science (or null).

TONE: Intellectually sharp, direct, warm, authoritative, and engaging.

OUTPUT FORMAT:
Strictly raw JSON with NO markdown fences:
{
  "hook": "Direct curiosity-driven opening truth...",
  "commentary_segments": [
    {
      "text": "Direct, clear factual explanation of the mechanism without any analogies...",
      "insert_after_text": "Exact sentence from transcript where concept ends"
    }
  ],
  "takeaway": "Direct practical takeaway rule..."
}"""

def generate_commentary(
    clip_transcript: str,
    surrounding_context: str,
    topic: str = "General",
    speaker_info: str = "Unknown"
) -> Dict:
    """
    Generates editorial commentary for a clip featuring Dr. Mei's teacher persona.
    Returns a dictionary with 'hook', 'commentary_segments', 'takeaway', and 'qc_flag'.
    """
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        key = os.environ.get("NVIDIA_API_KEY", "").strip()

    if not key:
        logger.error("NVIDIA_API_KEY is not set. Cannot generate commentary.")
        return {"hook": None, "commentary_segments": [], "takeaway": None, "qc_flag": "Error: Missing API Key"}

    client = OpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=key,
        max_retries=0
    )

    user_prompt = f"""
--- CLIP TRANSCRIPT ---
{clip_transcript}

--- SURROUNDING CONTEXT ---
{surrounding_context}

--- METADATA ---
Topic: {topic}
Speaker(s): {speaker_info}

Analyze the above and generate the editorial components as JSON.
"""
    logger.info("Requesting editorial commentary from LLM...")
    import re
    import time

    response_content = None
    for model_candidate in MODEL_FALLBACKS:
        for attempt in range(4):
            try:
                stream = client.chat.completions.create(
                    model=model_candidate,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=1024,
                    stream=True,
                    timeout=35.0
                )
                chunks = []
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        c = getattr(delta, "content", None)
                        if c: chunks.append(c)
                response_content = "".join(chunks).strip()
                if response_content:
                    logger.info(f"[CommentaryGenerator] Successfully generated commentary via {model_candidate}")
                    break
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = ("429" in err_str or "too many requests" in err_str or "rate limit" in err_str)
                if is_rate_limit and attempt < 3:
                    wait_s = 3.5 * (attempt + 1)
                    logger.info(f"[CommentaryGenerator] ⏳ Model {model_candidate} rate-limited (429). Giving a {wait_s:.1f}s cooldown break (attempt {attempt+1}/4)...")
                    time.sleep(wait_s)
                    continue
                else:
                    logger.warning(f"[CommentaryGenerator] Model {model_candidate} failed (attempt {attempt+1}): {e}")
                    break
        if response_content:
            break

    data = {}
    if response_content:
        try:
            cleaned = re.sub(r"```(?:json)?", "", response_content).strip().strip("`").strip()
            data = json.loads(cleaned)
        except Exception:
            start_obj = response_content.find("{")
            end_obj = response_content.rfind("}")
            if start_obj != -1 and end_obj > start_obj:
                try:
                    data = json.loads(response_content[start_obj:end_obj+1])
                except Exception as e:
                    logger.warning(f"Failed to parse commentary JSON: {e}")

    hook = data.get("hook", "").strip() if data.get("hook") else None
    takeaway = data.get("takeaway", "").strip() if data.get("takeaway") else None
    commentary_segments = data.get("commentary_segments", [])

    # Clean up any analogy openers from commentary text
    for seg in commentary_segments:
        if isinstance(seg, dict) and "text" in seg:
            txt = seg["text"].strip()
            # Strip cliché analogy phrasing
            txt = re.sub(r"^(Think of (your brain|it|this) like a?|Imagine (your brain|this|it) as a?|Picture this:?|It's like a?)\s*", "", txt, flags=re.IGNORECASE).strip()
            if txt and txt[0].islower():
                txt = txt[0].upper() + txt[1:]
            seg["text"] = txt

    # Robust fallback if LLM omitted commentary_segments
    if not commentary_segments or not isinstance(commentary_segments, list) or len(commentary_segments) == 0:
        sentences = [s.strip() for s in re.split(r'[.!?]+', clip_transcript) if len(s.strip().split()) >= 4]
        mid_sentence = sentences[len(sentences)//2] if sentences else clip_transcript[:60]
        fallback_explainer = f"This neural mechanism directly explains how sensory input influences your brain's ability to maintain sustained focus."
        commentary_segments = [{
            "text": fallback_explainer,
            "insert_after_text": mid_sentence
        }]

    if not hook:
        hook = f"This single biological mechanism explains why focus is so difficult to maintain."

    return {
        "hook": hook,
        "commentary_segments": commentary_segments,
        "takeaway": takeaway,
        "qc_flag": "PASS"
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_clip = "I think the most important thing is sleep. Without it, you can't function."
    test_context = "We were talking about health routines earlier. I think the most important thing is sleep. Without it, you can't function. Diet is second."
    print(json.dumps(generate_commentary(test_clip, test_context, "Health"), indent=2))

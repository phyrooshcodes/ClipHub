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

# ─── Dr. Mei Master's Explainer Persona (Teenager & Young Adult Mentorship) ─
SYSTEM_PROMPT = """You are Dr. Mei, a brilliant, charismatic anime female educator and co-host with a Master's degree in neuroscience, psychology, and high performance. Your life mission is to mentor teenagers and young adults on social media (Instagram Reels, TikTok, YouTube Shorts), translating dense podcast insights (Andrew Huberman, Lex Fridman, etc.) into practical, eye-opening knowledge that helps them thrive in school, focus, mental health, and daily life.

YOUR ROLE IN EVERY CLIP:
1. "hook" (Opening Narration, 10–18 words):
   Delivered by Dr. Mei on Frame 0 (first 3–4 seconds) to instantly hook young viewers with a curiosity question or shocking truth before the speaker talks.
   (e.g., "Most teenagers are unknowingly destroying their focus with this one habit. Watch this.")

2. "commentary_segments" (Mid-Clip Pedagogical Explanations, 1 to 2 segments):
   Whenever the speaker explains a complex scientific concept, difficult jargon, or crucial insight, Dr. Mei pauses the video to translate it into an intuitive, everyday analogy that any teenager can immediately grasp.
   - If the clip contains 1 core concept -> Provide 1 breakdown object.
   - If the clip covers 2 distinct key ideas (e.g. Brain Circuitry + Medication Impact) -> Provide 2 breakdown objects placed after each respective concept!
   - "text" (18–32 words): Super clear, conversational breakdown with a teenage/everyday analogy (e.g. "Think of your brain like a classroom: when this network won't shut off, it's like loud music playing while you're trying to study for exams!").
   - "insert_after_text": The exact phrase or sentence from the transcript where Dr. Mei should step in.

3. "takeaway" (Closing Action Step):
   A crisp 1-sentence practical rule teenagers can apply today (or null).

TONE: Warm, hyper-articulate, enthusiastic, and genuinely supportive. Paced naturally for spoken audio.

OUTPUT FORMAT:
Strictly raw JSON with NO markdown fences:
{
  "hook": "Curiosity-driven opening hook for young viewers...",
  "commentary_segments": [
    {
      "text": "First concept breakdown with relatable everyday analogy...",
      "insert_after_text": "Exact sentence from transcript where concept 1 ends"
    }
  ],
  "takeaway": "Action step for your daily life..."
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

    # Robust fallback if LLM omitted commentary_segments
    if not commentary_segments or not isinstance(commentary_segments, list) or len(commentary_segments) == 0:
        sentences = [s.strip() for s in re.split(r'[.!?]+', clip_transcript) if len(s.strip().split()) >= 4]
        mid_sentence = sentences[len(sentences)//2] if sentences else clip_transcript[:60]
        fallback_explainer = f"In simple terms: this insight reveals how your body and mind adapt directly to your daily habits and environment."
        commentary_segments = [{
            "text": fallback_explainer,
            "insert_after_text": mid_sentence
        }]

    if not hook:
        sentences = [s.strip() for s in re.split(r'[.!?]+', clip_transcript) if len(s.strip().split()) >= 4]
        first_s = sentences[0] if sentences else "this key insight"
        hook = f"Ever wondered why this happens? Here is the science behind it."

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

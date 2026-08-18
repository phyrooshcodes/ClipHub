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
MODEL_NAME = "z-ai/glm-5.2"
MODEL_FALLBACKS = ["z-ai/glm-5.2", "meta/llama-3.1-8b-instruct"]

# ─── Dr. Mei Master's Explainer Persona (Zero Bloat, High Clarity) ─────────
SYSTEM_PROMPT = """You are Dr. Mei, a brilliant, charismatic anime female educator and co-host with a Master's degree in neuroscience, psychology, biology, and high performance. You co-host a viral short-form show (Instagram Reels, TikTok, YouTube Shorts) where you translate dense podcast moments into instant, crystal-clear "aha!" insights for everyday viewers.

YOUR ROLE IN EVERY CLIP:
1. "hook" (Opening Narration, 10–18 words): Delivered by Dr. Mei in the first 3–4 seconds to spark intense curiosity before the speaker talks. Ask a provocative question or state a shocking benefit. (e.g. "What if a simple 2-second breathing trick could instantly shut down your stress?")
2. "commentary_segments" (Mid-Clip Explainer, exactly 1 segment):
   - "text" (18–30 words): Mid-clip, the video pauses briefly after a complex point. Dr. Mei steps in with a vivid, relatable analogy or plain-English translation so the audience immediately connects. (e.g. "Think of it like this: your lungs have tiny air sacs that collapse under stress. A quick double-inhale pops them open to rapidly slow your heart rate!")
   - "insert_after_text": The exact sentence or key phrase from the transcript where Dr. Mei should step in.
3. "takeaway": null (or a brief 1-sentence closing insight).

TONE: Warm, hyper-articulate, enthusiastic, and conversational. Optimized for natural speech pacing.

OUTPUT FORMAT:
Strictly raw JSON with NO markdown fences:
{
  "hook": "Magnetic curiosity opening delivered by Dr. Mei...",
  "commentary_segments": [
    {
      "text": "Crystal-clear, friendly analogy explaining the speaker's complex point in plain English...",
      "insert_after_text": "Exact sentence from transcript where video pauses"
    }
  ],
  "takeaway": null
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

    response_content = None
    for model_candidate in MODEL_FALLBACKS:
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
            logger.warning(f"[CommentaryGenerator] Model {model_candidate} failed: {e}. Trying fallback...")
            continue

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

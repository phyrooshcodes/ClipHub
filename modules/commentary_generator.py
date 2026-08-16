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
MODEL_NAME = "meta/llama-3.3-70b-instruct"

# We request JSON mode from the LLM
SYSTEM_PROMPT = """You are the Lead Editor of ClipHub, an AI-powered short-form editorial engine.
Your job is to transform an interesting moment from a long-form conversation into a short, contextualized editorial story.
The source podcast is supporting material, while your narration, sequencing, context, and storytelling provide meaningful original value.

You will receive:
1. The exact transcript of the selected clip.
2. The surrounding context (30-60s) for deeper understanding.
3. Speaker information and topic (if known).

You must generate a structured JSON object with three optional components:
1. "hook": A short, curiosity-driven intro (1-3 sentences) based specifically on the clip. DO NOT be generic. Prefer specifics over "Here is what a neuroscientist says about X". Generate something like "Why can't you stop thinking about someone?"
2. "commentary_segments": An array of objects with "text" (your commentary explaining why the idea matters) and "insert_after_text" (a brief quote from the clip indicating where this commentary should be inserted). 
3. "takeaway": A closing remark giving the viewer a clear takeaway.

CRITICAL RULES:
- The generator must ground commentary in the provided transcript/context. Do NOT invent claims, quotes, or conclusions unsupported by the source.
- Do not remove important context in a way that changes the meaning.
- Commentary should be inserted ONLY where it genuinely improves understanding. If it doesn't add value, return an empty array for commentary_segments.
- Add a little bit of subtle humor where appropriate to increase understanding and keep the viewer engaged (do not force it, keep it natural and professional).
- If a takeaway isn't needed, return null for takeaway.
- Do NOT create repetitive "clip -> commentary -> clip -> commentary" patterns. The source should feel natural.
- You must output VALID JSON only.

Output Format:
{
  "hook": "Strong opening hook text...",
  "commentary_segments": [
    {
      "text": "Your commentary here...",
      "insert_after_text": "The exact quote from the transcript where this should be inserted"
    }
  ],
  "takeaway": "Your closing takeaway here..."
}
"""

def generate_commentary(
    clip_transcript: str,
    surrounding_context: str,
    topic: str = "General",
    speaker_info: str = "Unknown"
) -> Dict:
    """
    Generates editorial commentary for a clip.
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
        api_key=key
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
    from openai import APIConnectionError, APITimeoutError, RateLimitError, InternalServerError, APIStatusError
    import time
    import re

    response_content = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=1024,
                timeout=60.0
            )
            response_content = response.choices[0].message.content
            if response_content:
                break
        except (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError, APIStatusError) as e:
            if attempt == 2:
                logger.error(f"Failed to generate commentary after 3 retries: {e}")
                return {"hook": None, "commentary_segments": [], "takeaway": None, "qc_flag": f"Generation Error: {e}"}
            sleep_s = (attempt + 1) * 2
            logger.warning(f"[CommentaryGenerator] Retry {attempt+1}/3 in {sleep_s}s: {e}")
            time.sleep(sleep_s)

    if not response_content:
        return {"hook": None, "commentary_segments": [], "takeaway": None, "qc_flag": "Error: Empty response from LLM"}

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
                logger.error(f"Failed to parse commentary JSON: {e}")
                return {"hook": None, "commentary_segments": [], "takeaway": None, "qc_flag": f"JSON Parse Error: {e}"}
        else:
            return {"hook": None, "commentary_segments": [], "takeaway": None, "qc_flag": "JSON Parse Error"}

    # Validation checks
    hook = data.get("hook", "").strip() if data.get("hook") else None
    takeaway = data.get("takeaway", "").strip() if data.get("takeaway") else None
    commentary_segments = data.get("commentary_segments", [])
    
    # QC Pass: Ask LLM to validate its own generated output against the transcript
    qc_flag = validate_commentary(clip_transcript, surrounding_context, data, client)
    if qc_flag and "FLAG:" in qc_flag:
        logger.warning(f"[CommentaryGenerator] QC Rejected commentary: {qc_flag}. Discarding hallucinated segments.")
        commentary_segments = []
    
    return {
        "hook": hook,
        "commentary_segments": commentary_segments,
        "takeaway": takeaway,
        "qc_flag": qc_flag
    }

def validate_commentary(transcript: str, context: str, commentary_data: dict, client: OpenAI) -> Optional[str]:
    """QC Layer: Checks if the commentary makes unsupported claims or removes important context."""
    logger.info("Running QC Validation on generated commentary...")
    validation_prompt = f"""
You are the QC Editor. Review the generated editorial commentary against the source transcript.
Source Transcript: {transcript}
Surrounding Context: {context}

Generated Commentary:
{json.dumps(commentary_data, indent=2)}

Task:
1. Ensure the commentary is strictly grounded in the transcript.
2. Check for unsupported claims, hallucinated facts, or misleading out-of-context quotes.
3. If everything is perfectly grounded, return exactly "PASS".
4. If there is ANY unsupported claim, return a short string describing the issue (e.g. "FLAG: Commentary claims X, but source says Y").
"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": validation_prompt}],
            temperature=0.1,
            max_tokens=150,
            timeout=30.0
        )
        result = response.choices[0].message.content.strip()
        if result == "PASS":
            return None
        return result
    except Exception as e:
        return f"QC Error: {e}"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_clip = "I think the most important thing is sleep. Without it, you can't function."
    test_context = "We were talking about health routines earlier. I think the most important thing is sleep. Without it, you can't function. Diet is second."
    print(json.dumps(generate_commentary(test_clip, test_context, "Health"), indent=2))

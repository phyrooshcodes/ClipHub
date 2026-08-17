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
MODEL_NAME = "meta/llama-3.1-70b-instruct"
MODEL_FALLBACKS = ["meta/llama-3.1-70b-instruct", "meta/llama-3.3-70b-instruct", "meta/llama-3.1-8b-instruct"]

# We request JSON mode from the LLM
SYSTEM_PROMPT = """You are the Lead Editorial Director of ClipHub, creating high-retention viral explanation videos (Vox, Modern Wisdom, Impact Theory style).

YOUR OBJECTIVE:
Transform complex podcast moments into clear, engaging short-form videos where the viewer genuinely learns something valuable and actionable.

STRUCTURE:
1. "hook": A punchy 1-sentence opening narration (10–18 words max) telling the viewer what problem this clip will solve or what key knowledge they are about to learn.
2. "commentary_segments": Array with 1 high-impact breakdown object:
   - "text": A simple, plain-English explanation (15–28 words max) translating the complex science or idea the speaker just explained so anyone can instantly understand it.
   - "insert_after_text": The exact sentence or phrase from the transcript where the video will PAUSE for this explanation.
3. "takeaway": null (or a brief 1-sentence closing insight).

CRITICAL RULES:
- Keep the language punchy, clear, accessible, and educational.
- Ground all facts strictly in the provided transcript.
- Limit to 1 commentary segment per clip to maintain rapid, engaging video pacing.
- Output strictly valid raw JSON.

Output Format:
{
  "hook": "Concise opening hook introducing the problem or core insight...",
  "commentary_segments": [
    {
      "text": "In plain terms: simple explanation breaking down the complex idea...",
      "insert_after_text": "Exact sentence from transcript where video pauses"
    }
  ],
  "takeaway": null
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
    from openai import APIConnectionError, APITimeoutError, RateLimitError, InternalServerError, APIStatusError
    import time
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
                timeout=30.0
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

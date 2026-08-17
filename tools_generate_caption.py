import sys
import json
import os
import re
import subprocess
from pathlib import Path
from openai import OpenAI

BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

def extract_audio(video_path, audio_path):
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(audio_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def transcribe(audio_path, model_size="base"):
    from modules.transcriber import transcribe_audio, words_to_full_text
    words = transcribe_audio(audio_path, model_size=model_size)
    return words_to_full_text(words)

def generate_caption(transcript):
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    model = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")

    if not api_key:
        base_url = "http://localhost:1234/v1"
        api_key = "lm-studio"
        model = "qwen2.5-14b-instruct"

    client = OpenAI(
        base_url=base_url,
        api_key=api_key
    )
    
    prompt = f"""You are an elite short-form social strategist and caption writer.

Write a HIGH-CONVERSION title and caption for a short-form clip based on the transcript below.

GOAL
- Make the title curiosity-driven, specific, and scroll-stopping.
- Make the caption feel native to Instagram Reels / TikTok.
- The caption should reinforce the clip's main idea, not repeat the transcript verbatim.

TITLE RULES
- Under 50 characters.
- Specific > generic.
- Prefer tension, curiosity, or a strong payoff.
- Avoid filler words and vague motivational language.

CAPTION RULES
- Start with a strong hook line.
- Include the core takeaway in 1-2 short lines.
- Add a brief CTA only if it feels natural.
- Include 3-6 highly relevant hashtags that match the clip's actual topic and audience.
- Avoid spammy tags like #fyp #viral unless they truly fit the niche.
- Keep it clean, punchy, and ready to paste.

OUTPUT RULES
- Output ONLY valid JSON with exactly two keys: "title" and "caption".
- Do not use markdown fences.
- Do not add explanations.

Transcript:
"{transcript}"
"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a social media expert. Always reply with raw JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500,
            timeout=30.0
        )
        content = response.choices[0].message.content.strip()
        cleaned = re.sub(r"```(?:json)?", "", content).strip().strip("`").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            s_idx = content.find("{")
            e_idx = content.rfind("}")
            if s_idx != -1 and e_idx > s_idx:
                return json.loads(content[s_idx:e_idx+1])
            raise
    except Exception as e:
        raise RuntimeError(f"NVIDIA API caption generation failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: tools_generate_caption.py <video_path> [model_size]"}))
        sys.exit(1)

    video_path = sys.argv[1]
    model_size = sys.argv[2] if len(sys.argv) > 2 else "base"
    audio_path = video_path + ".wav"
    
    try:
        extract_audio(video_path, audio_path)
        transcript = transcribe(audio_path, model_size=model_size)
        if not transcript:
            print(json.dumps({"error": "No speech detected in video."}))
            sys.exit(1)
            
        result = generate_caption(transcript)
        result["transcript"] = transcript
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    finally:
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass

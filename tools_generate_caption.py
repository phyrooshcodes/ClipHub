import sys
import json
import os
import subprocess
from pathlib import Path
from openai import OpenAI
from faster_whisper import WhisperModel

def extract_audio(video_path, audio_path):
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def transcribe(audio_path):
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, beam_size=5)
    text = ""
    for segment in segments:
        text += segment.text + " "
    return text.strip()

def generate_caption(transcript):
    client = OpenAI(
        base_url="http://localhost:1234/v1",
        api_key="lm-studio"
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
            model="qwen2.5-14b-instruct",
            messages=[
                {"role": "system", "content": "You are a social media expert. Always reply with raw JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500,
        )
        content = response.choices[0].message.content.strip()
        # Clean up markdown if any
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        return {"title": "Viral Video", "caption": "Check out this amazing video! #viral #fyp\n\n(Error: " + str(e) + ")"}

if __name__ == "__main__":
    video_path = sys.argv[1]
    audio_path = video_path + ".wav"
    
    try:
        extract_audio(video_path, audio_path)
        transcript = transcribe(audio_path)
        if not transcript:
            print(json.dumps({"error": "No speech detected in video."}))
            sys.exit(0)
            
        result = generate_caption(transcript)
        result["transcript"] = transcript
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

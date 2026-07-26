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

def generate_products(transcript):
    client = OpenAI(
        base_url="http://localhost:1234/v1",
        api_key="lm-studio"
    )
    
    prompt = f"""You are an affiliate marketing expert and product researcher.

Analyze the following transcript of a short-form video clip and suggest 1-3 highly relevant products that could be promoted in the caption or comments as affiliate links.

GOAL
- Identify explicit mentions of products, gear, tools, or books.
- If no explicit products are mentioned, suggest implicit products based on the topic (e.g., if the topic is productivity, suggest a popular productivity planner or book).
- Ensure the products actually exist on Amazon and are popular.

OUTPUT FORMAT
Output ONLY valid JSON containing a list of products under the key "products".
Each product should have:
- "product_name": The specific name of the product.
- "reason": A brief 1-sentence reason why this product is a good fit for this specific clip.
- "search_query": The best 3-5 word search query to find this exact product on Amazon.

Example JSON output:
{{
  "products": [
    {{
      "product_name": "Atomic Habits by James Clear",
      "reason": "The speaker mentions building tiny habits over time.",
      "search_query": "Atomic Habits James Clear book"
    }}
  ]
}}

Transcript:
"{transcript}"
"""
    try:
        response = client.chat.completions.create(
            model="qwen2.5-14b-instruct",
            messages=[
                {"role": "system", "content": "You are a product suggestion expert. Always reply with raw JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        return {"products": [], "error": str(e)}

if __name__ == "__main__":
    video_path = sys.argv[1]
    audio_path = video_path + ".wav"
    
    try:
        extract_audio(video_path, audio_path)
        transcript = transcribe(audio_path)
        if not transcript:
            print(json.dumps({"error": "No speech detected in video."}))
            sys.exit(0)
            
        result = generate_products(transcript)
        result["transcript"] = transcript
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

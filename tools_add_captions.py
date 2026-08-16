import sys
import json
import os
import subprocess
import tempfile
from pathlib import Path

# Ensure root dir is in sys.path
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

def apply_captions(input_video, style_name, output_video, model_size="base"):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
        audio_path = tmp_wav.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ass") as tmp_ass:
        ass_path = tmp_ass.name

    try:
        extract_audio(input_video, audio_path)
        
        from modules.transcriber import transcribe_audio
        words = transcribe_audio(audio_path, model_size=model_size)
        if not words:
            return {"error": "No speech detected in this video to caption."}

        max_end = max([w.get("end", 0.0) for w in words]) if words else 10.0
        duration_s = max_end + 5.0

        from modules.subtitle_engine import generate_ass_subtitles
        generate_ass_subtitles(
            words=words,
            clip_start_s=0.0,
            clip_end_s=duration_s,
            output_path=ass_path,
            style_name=style_name,
            clip_title="",
            preset_name="default"
        )

        safe_ass = str(Path(ass_path).resolve()).replace("\\", "/").replace(":", "\\:")

        # Render with ASS subtitle filter and AAC audio encoding
        cmd = [
            "ffmpeg", "-y", "-i", str(input_video),
            "-vf", f"ass={safe_ass}",
            "-c:a", "aac", "-b:a", "192k", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
            str(output_video)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return {"error": f"FFmpeg caption rendering failed: {res.stderr}"}

        return {"success": True, "words_count": len(words), "output": output_video}

    finally:
        if os.path.exists(audio_path):
            try: os.remove(audio_path)
            except Exception: pass
        if os.path.exists(ass_path):
            try: os.remove(ass_path)
            except Exception: pass

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: tools_add_captions.py <input_video> <style_name> <output_video> [model_size]"}))
        sys.exit(1)
        
    in_video = sys.argv[1]
    style = sys.argv[2]
    out_video = sys.argv[3]
    model_size = sys.argv[4] if len(sys.argv) > 4 else "base"
    
    try:
        res = apply_captions(in_video, style, out_video, model_size=model_size)
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

import os
from pathlib import Path
from modules.renderer import render_clip

def main():
    input_video = r"temp/test_short.mp4"
    if not os.path.exists(input_video):
        print("Input video not found!")
        return

    output_dir = Path("temp/test_render_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_video = output_dir / "rendered_test.mp4"

    # Mock editorial timeline
    # The new renderer expects: (start_t, end_t, comment_path, type)
    # where type is 'hook', 'commentary', 'takeaway'
    
    # We generated a kokoro test file earlier
    kokoro_path = r"temp/test_kokoro.wav"
    
    # Let's say source clip is from 10.0 to 30.0 (20s)
    # Hook from 0 to 4s (using kokoro)
    # Source plays 10 to 15s (5s)
    # Commentary from 5 to 9s (kokoro)
    # Source plays 15 to 20s (5s)
    
    ai_audio_events = [
        {"audio_path": kokoro_path, "start_s": 0.0, "end_s": 4.0, "type": "hook"},
        {"audio_path": kokoro_path, "start_s": 9.0, "end_s": 13.0, "type": "commentary"},
        {"audio_path": kokoro_path, "start_s": 18.0, "end_s": 22.0, "type": "takeaway"}
    ]
    
    # Just mock crop_coords
    crop_coords = {
        "crop_w": 405,
        "crop_h": 720,
        "crop_x": 437,
        "dynamic_crop_x": [],
        "fps": 30.0
    }
    
    # Create an empty subtitle file
    sub_path = "temp/test_sub.ass"
    with open(sub_path, "w") as f:
        f.write("""[Script Info]
Title: Test
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,Hello World
""")
    
    print("Testing Renderer...")
    try:
        render_clip(
            input_video=input_video,
            output_path=str(out_video),
            start_ms=0,
            end_ms=25000,
            crop_coords=crop_coords,
            subtitle_path=sub_path,
            commentary_voice="af_sarah",
            intro_duration=3.0,
            ai_audio_events=ai_audio_events
        )
        print("Success! Rendered output created at:", out_video)
    except Exception as e:
        print(f"Renderer failed: {e}")

if __name__ == "__main__":
    main()

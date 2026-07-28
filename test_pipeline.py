import sys
import logging
logging.basicConfig(level=logging.INFO)

from modules.face_tracker import compute_crop_coords
from modules.renderer import render_clip

print("Testing compute_crop_coords...")
crop_coords = compute_crop_coords("input_video.mp4", 0, 3000)
print(f"Crop coords generated: keys={crop_coords.keys()}, dynamic size={len(crop_coords.get('dynamic_crop_x', []))}")

# generate a dummy subtitle file
with open("test_sub.ass", "w") as f:
    f.write("[Script Info]\nScriptType: v4.00+\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:03.00,Default,,0,0,0,,Hello world\n")

print("Testing render_clip...")
render_clip("input_video.mp4", "test_render_out.mp4", 0, 3000, crop_coords, "test_sub.ass", encoder="libx264")
print("Done!")

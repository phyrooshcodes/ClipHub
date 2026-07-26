import sys
from modules.renderer import render_clip
render_clip("silent.mp4", "output_silent.mp4", 0, 1000, {"crop_w": 256, "crop_h": 256, "crop_x": 0}, "dummy.ass", {"path": "bg_music.mp3", "start_s": 0}, 0)

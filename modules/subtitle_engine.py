# ============================================================
# subtitle_engine.py — Module 5: Kinetic Subtitle Generator
# Hardware Target: CPU — Pure Python String Engine
# Purpose: Transform word-level timestamps into TikTok-style
#          rapid-fire ASS subtitle files with 2-3 words per
#          frame, yellow bold text, black outline, center-mid.
#          0% GPU usage — pure algorithmic string logic.
# ============================================================

import os
import logging
from typing import List, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── Kinetic Subtitle Configuration ─────────────────────────
MAX_CHARS_PER_GROUP  = 16     # Max characters before forcing a new group
MAX_WORDS_PER_GROUP  = 3      # Max words per subtitle frame
MIN_SUBTITLE_DURATION = 0.25  # Seconds — minimum display time per group

# ─── ASS Style Constants ─────────────────────────────────────────────────────────
# ASS Colour format: &HAABBGGRR  (alpha, blue, green, red in hex)
# Bright Yellow = &H0000FFFF (A=00, B=00, G=FF, R=FF)
# Black Outline  = &H00000000
# Shadow         = &H80000000 (50% transparent black)
#
# Alignment codes (numpad layout):
#  7=top-left   8=top-center    9=top-right
#  4=mid-left   5=mid-center    6=mid-right   ← Alignment=5 for center-middle
#  1=bot-left   2=bot-center    3=bot-right

PRESETS = {
    "default": {
        "fontname": "Arial",
        "fontsize": 90,
        "primary": "&H00FFFFFF&",  # White
        "outline": "&H00000000&",  # Black
        "bold": "-1",
        "outline_width": "6",
    },
    "hormozi": {
        "fontname": "Impact",
        "fontsize": 95,
        "primary": "&H0000FFFF&",  # Yellow
        "outline": "&H00000000&",  # Black
        "bold": "-1",
        "outline_width": "9",
    },
    "beast": {
        "fontname": "Arial Black",
        "fontsize": 90,
        "primary": "&H0000FFFF&",  # Yellow
        "outline": "&H00000000&",  # Black
        "bold": "-1",
        "outline_width": "8",
    },
    "minimal": {
        "fontname": "Arial",
        "fontsize": 80,
        "primary": "&H00FFFFFF&",  # White
        "outline": "&H00000000&",  # Black
        "bold": "0",
        "outline_width": "3",
    }
}

def html_color_to_ass(hex_color: str) -> str:
    """Convert HTML hex color (#RRGGBB or #AARRGGBB) to ASS color format (&H00BBGGRR&)"""
    hex_color = hex_color.lstrip('#').strip()
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H00{b}{g}{r}&"
    elif len(hex_color) == 8:
        a, r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6], hex_color[6:8]
        return f"&H{a}{b}{g}{r}&"
    return "&H00FFFFFF&"

def _get_ass_header(
    preset_name: str = "default",
    font_name: Optional[str] = None,
    font_size: Optional[int] = None,
    primary_color: Optional[str] = None,
    outline_color: Optional[str] = None
) -> str:
    p = dict(PRESETS.get(preset_name, PRESETS["default"]))
    
    if font_name and isinstance(font_name, str) and font_name.strip():
        p["fontname"] = font_name.strip()
    if font_size and isinstance(font_size, int) and font_size > 0:
        p["fontsize"] = font_size
    if primary_color and isinstance(primary_color, str) and primary_color.strip():
        p["primary"] = html_color_to_ass(primary_color)
    if outline_color and isinstance(outline_color, str) and outline_color.strip():
        p["outline"] = html_color_to_ass(outline_color)
        
    title_font = "Impact" if p["fontname"] == "Impact" else "Arial Black"
    
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kinetic,{p["fontname"]},{p["fontsize"]},{p["primary"]},&H000000FF&,{p["outline"]},&H80000000&,{p["bold"]},0,0,0,100,100,0,0,1,{p["outline_width"]},0,5,60,60,60,1
Style: TitleStyle,{p["fontname"]},55,&H00FFFFFF&,&H000000FF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,4,2,8,60,60,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text

"""
    return header

# Alignment=5 is center-middle (numpad 5)
# Fontsize=90 for large readable text on 1080x1920 canvas
# Outline=5 for thick black stroke
# PrimaryColour=&H0000FFFF = bright yellow


def generate_ass_subtitles(
    words: List[Dict],
    clip_start_s: float,
    clip_end_s: float,
    output_path: str,
    style_name: str = "kinetic_slide",
    clip_title: Optional[str] = None,
    preset_name: str = "default",
    font_name: Optional[str] = None,
    font_size: Optional[int] = None,
    primary_color: Optional[str] = None,
    outline_color: Optional[str] = None,
    ai_audio_events: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Generate a TikTok-style ASS subtitle file for a clip segment.

    Args:
        words:        Full word-timestamp list from transcriber.
        clip_start_s: Clip start time in SECONDS (float).
        clip_end_s:   Clip end time in SECONDS (float).
        output_path:  Where to save the .ass file.
        style_name:   Subtitle animation style.
        clip_title:   Title of the clip to display as a top banner.
        preset_name:  Selected styling preset (e.g. 'hormozi', 'beast').
        font_name:    Custom font name override.
        font_size:    Custom font size override.
        primary_color: Custom primary text color override.
        outline_color: Custom outline color override.
        ai_audio_events: AI voice commentary events for pause/context badges.

    Returns:
        Path to the generated ASS file.
    """
    parent = Path(output_path).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)

    # Filter and clamp words that fall within or intersect this clip's time window
    clip_words = []
    for w in words:
        if w["end"] > clip_start_s and w["start"] < clip_end_s:
            w_start = max(clip_start_s, w["start"])
            w_end = min(clip_end_s, w["end"])
            if w_end > w_start:
                clip_words.append({
                    "word": w["word"],
                    "start": w_start,
                    "end": w_end
                })

    if not clip_words:
        logger.warning(
            f"[SubtitleEngine] No words found in range "
            f"[{clip_start_s:.2f}s → {clip_end_s:.2f}s]. "
            "Creating empty subtitle file."
        )
        _write_ass(output_path, [], style_name, clip_title, preset_name, font_name, font_size, primary_color, outline_color, ai_audio_events)
        return output_path

    # Normalize timestamps: make them relative to clip start
    normalized_words = [
        {
            "word":  w["word"],
            "start": round(w["start"] - clip_start_s, 3),
            "end":   round(w["end"]   - clip_start_s, 3)
        }
        for w in clip_words
    ]

    # Group words into kinetic subtitle frames
    groups = _group_words_kinetic(normalized_words)

    logger.info(
        f"[SubtitleEngine] {len(clip_words)} words → "
        f"{len(groups)} subtitle groups for clip "
        f"[{clip_start_s:.1f}s → {clip_end_s:.1f}s]"
    )

    _write_ass(output_path, groups, style_name, clip_title, preset_name, font_name, font_size, primary_color, outline_color, ai_audio_events)
    logger.info(f"[SubtitleEngine] ✅ ASS file written → {output_path}")
    return output_path



def _group_words_kinetic(words: List[Dict]) -> List[Dict]:
    """
    Split word list into rapid-fire 2-3 word groups.
    Each group contains the original word dictionaries.

    Rules:
    - Max MAX_WORDS_PER_GROUP words per group
    - Max MAX_CHARS_PER_GROUP chars per group (force break if exceeded)
    - Minimum MIN_SUBTITLE_DURATION seconds display time

    Returns:
    Convert list of words to list of group dicts:
        [{"words": [...], "start": 0.24, "end": 0.90}, ...]
    """
    groups = []
    i = 0

    while i < len(words):
        group_words_data = []
        group_chars = 0
        group_start = words[i]["start"]
        group_end   = words[i]["end"]

        while i < len(words) and len(group_words_data) < MAX_WORDS_PER_GROUP:
            w_data = words[i]
            word = w_data["word"]
            candidate_chars = group_chars + len(word) + (1 if group_words_data else 0)

            if group_words_data and candidate_chars > MAX_CHARS_PER_GROUP:
                break  # This word goes in the next group

            group_words_data.append(w_data)
            group_chars    = candidate_chars
            group_end      = w_data["end"]
            i += 1

        duration = group_end - group_start

        # Enforce minimum display duration
        if duration < MIN_SUBTITLE_DURATION:
            group_end = group_start + MIN_SUBTITLE_DURATION

        groups.append({
            "words": group_words_data,
            "start": group_start,
            "end":   group_end
        })

    return groups


def _sanitize_word(text: str) -> str:
    """Sanitize transcript words to prevent ASS control tag corruption and screen overflow."""
    if not text:
        return ""
    clean = str(text).replace("{", "(").replace("}", ")").replace("\\", "/")
    if len(clean) > 16:
        clean = clean[:14] + ".."
    return clean

def _write_ass(
    output_path: str,
    groups: List[Dict],
    style_name: str = "kinetic_slide",
    clip_title: str = "",
    preset_name: str = "default",
    font_name: str = "",
    font_size: int = 0,
    primary_color: str = "",
    outline_color: str = "",
    ai_audio_events: Optional[List[Dict[str, Any]]] = None
) -> None:
    """
    Write the ASS file generating dynamic word-by-word slide-up, zoom, neon, karaoke,
    and tilt animations. Uses alpha layer overrides for alignment matching.

    Args:
        output_path: File path to write.
        groups:      List of group dicts.
        style_name:  Selected caption style.
        clip_title:   Clip title string to render as static header.
        preset_name:  Visual preset styling config name.
        font_name:    Custom font name override.
        font_size:    Custom font size override.
        primary_color: Custom primary color override.
        outline_color: Custom outline color override.
        ai_audio_events: AI voice commentary events for pause/context badges.
    """
    lines = [_get_ass_header(preset_name, font_name, font_size, primary_color, outline_color)]

    for group in groups:
        group_start = group["start"]
        group_end   = group["end"]
        group_words = group["words"]
        
        if not group_words:
            continue
            
        W_texts = [_sanitize_word(w.get("word", "")).upper() for w in group_words]

        # ─── Style: smooth_wave (Continuous Karaoke sweep) ───
        if style_name == "smooth_wave":
            parts = []
            last_time = group_start
            for idx, w in enumerate(group_words):
                gap = w["start"] - last_time
                if gap > 0.01:
                    parts.append(f"{{\\kf{int(round(gap * 100))}}}")
                
                dur = w["end"] - w["start"]
                word_str = w["word"].upper()
                if idx < len(group_words) - 1:
                    word_str += " "
                parts.append(f"{{\\kf{int(round(dur * 100))}}}{word_str}")
                last_time = w["end"]
                
            remain = group_end - last_time
            if remain > 0.01:
                parts.append(f"{{\\kf{int(round(remain * 100))}}}")
                
            start_ts = _seconds_to_ass_time(group_start)
            end_ts   = _seconds_to_ass_time(group_end)
            text     = "{\\pos(540,960)\\fad(150,150)\\2c&HFFFFFF&\\1c&H00FFFF&}" + "".join(parts)
            lines.append(f"Dialogue: 0,{start_ts},{end_ts},Kinetic,,0,0,0,,{text}")
            continue

        # ─── Styles: Word-by-Word State Machine ───
        for j, w in enumerate(group_words):
            w_start = w["start"]
            w_end   = w["end"]
            
            # Find start of next word or group end
            next_start = group_words[j+1]["start"] if j < len(group_words) - 1 else group_end
            
            pos_x, pos_y = 540, 960
            anim_y_start = 985
            anim_dur_max = 0.150
            
            # Defaults
            color_active = "00FFFF"       # Yellow (BBGGRR)
            color_other = "FFFFFF"        # White (BBGGRR)
            alpha_other = "00"            # Fully opaque
            
            active_tags = ""
            static_active_tags = ""
            anim_effect = ""
            
            if style_name == "kinetic_slide":
                # Default Improved: Smooth slide-up with a bounce/scale-pop on entry
                anim_dur_max = 0.150
                active_tags = "\\c&H00FFFF&\\fscx100\\fscy100\\t(0,80,\\fscx120\\fscy120)\\t(80,150,\\fscx100\\fscy100)"
                static_active_tags = "\\c&H00FFFF&"
                anim_effect = f"\\move({pos_x},{anim_y_start + 10},{pos_x},{pos_y},0,150)\\fad(100,0)"
                
            elif style_name == "tiktok_pop":
                # Static position, active word pops from 0% scale, overshoot to 135%, settles back to 100%
                anim_dur_max = 0.150
                active_tags = "\\c&H0000FFFF&\\fscx0\\fscy0\\t(0,100,\\fscx135\\fscy135)\\t(100,150,\\fscx100\\fscy100)"
                static_active_tags = "\\c&H0000FFFF&"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(80,0)"
                color_active = "0000FF" # Red outline / Shadow or bright yellow. Default style has outline.
                
            elif style_name == "cyberpunk_neon":
                # Neon Pink for active, 50% opacity Cyber Cyan for other words with tilt rotation
                anim_dur_max = 0.150
                color_active = "FF00FF" # Pink
                color_other = "FFFF00"  # Cyan
                alpha_other = "50"      # Opaque/semi-transparent
                active_tags = f"\\c&H{color_active}&\\frz-4\\fscx90\\fscy90\\t(0,100,\\frz3\\fscx115\\fscy115)\\t(100,150,\\frz0\\fscx100\\fscy100)"
                static_active_tags = f"\\c&H{color_active}&"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(100,0)"
                
            elif style_name == "vibrant_gradient":
                # Orange gradient to yellow pop, inactive words greyed out
                anim_dur_max = 0.180
                color_other = "808080"  # Grey
                alpha_other = "60"      # Semitransparent
                active_tags = "\\c&H00008CFF&\\fscx100\\fscy100\\t(0,100,\\c&H0000FFFF&\\fscx115\\fscy115)\\t(100,180,\\fscx100\\fscy100)"
                static_active_tags = "\\c&H0000FFFF&"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(100,0)"
                
            elif style_name == "cinematic_swing":
                # Elegant swing-in with tilt rotation and soft light grey background
                anim_dur_max = 0.200
                color_other = "D0D0D0"  # Soft light grey
                alpha_other = "20"      # Dimmed
                active_tags = "\\c&H0000FFFF&\\frz-8\\fscx95\\fscy95\\t(0,120,\\frz4\\fscx112\\fscy112)\\t(120,200,\\frz0\\fscx100\\fscy100)"
                static_active_tags = "\\c&H0000FFFF&"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(120,0)"
                
            elif style_name == "karaoke_glow":
                # Glowing neon yellow outline with soft blur, inactive words dimmed
                anim_dur_max = 0.150
                color_other = "D0D0D0"
                alpha_other = "30"
                active_tags = "\\c&H0000FFFF&\\shad1\\3c&H00FFFF&\\blur3\\fscx100\\fscy100\\t(0,100,\\fscx115\\fscy115)\\t(100,150,\\fscx100\\fscy100)"
                static_active_tags = "\\c&H0000FFFF&\\shad1\\3c&H00FFFF&\\blur3"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(80,0)"
                
            elif style_name == "minimal_fade":
                # High-end minimalistic design: pure opacity shifts, zero scale/motion distraction
                anim_dur_max = 0.100
                color_other = "FFFFFF"
                alpha_other = "70" # very dimmed
                active_tags = "\\c&HFFFFFF&"
                static_active_tags = "\\c&HFFFFFF&"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(60,0)"
                
            elif style_name == "future_cyber":
                # Tech-inspired: active cyan glow outline with swift scale popup
                anim_dur_max = 0.150
                color_other = "C0C0C0"
                alpha_other = "40"
                active_tags = "\\c&HFFFF00&\\shad2\\3c&H00FF00&\\blur2\\fscx90\\fscy90\\t(0,100,\\fscx120\\fscy120)\\t(100,150,\\fscx100\\fscy100)"
                static_active_tags = "\\c&HFFFF00&\\shad2\\3c&H00FF00&\\blur2"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(80,0)"

            elif style_name == "hormozi_gold":
                # Alex Hormozi signature warm gold punch, dramatic scale pop and thick outline
                anim_dur_max = 0.140
                color_active = "00D7FF" # Gold in BGR
                color_other = "E0E0E0"
                alpha_other = "35"
                active_tags = f"\\c&H{color_active}&\\shad3\\fscx0\\fscy0\\t(0,90,\\fscx145\\fscy145)\\t(90,140,\\fscx105\\fscy105)"
                static_active_tags = f"\\c&H{color_active}&\\shad3\\fscx105\\fscy105"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(60,0)"

            elif style_name == "mrbeast_lightning":
                # MrBeast style electric cyan with energetic tilt and bold contrast
                anim_dur_max = 0.150
                color_active = "FFFF00" # Pure Cyan in BGR
                color_other = "FFFFFF"
                alpha_other = "45"
                active_tags = f"\\c&H{color_active}&\\shad2\\frz-6\\fscx110\\fscy110\\t(0,80,\\frz4\\fscx135\\fscy135)\\t(80,150,\\frz-1\\fscx110\\fscy110)"
                static_active_tags = f"\\c&H{color_active}&\\shad2\\frz-1\\fscx110\\fscy110"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(70,0)"

            elif style_name == "fire_ember":
                # Hot fiery orange with subtle upward leap
                anim_dur_max = 0.160
                color_active = "0055FF" # Fire Orange in BGR
                color_other = "CCCCCC"
                alpha_other = "40"
                active_tags = f"\\c&H{color_active}&\\shad2\\blur2\\fscx95\\fscy95\\t(0,100,\\fscx125\\fscy125)\\t(100,160,\\fscx102\\fscy102)"
                static_active_tags = f"\\c&H{color_active}&\\shad2\\blur2\\fscx102\\fscy102"
                anim_effect = f"\\move({pos_x},{pos_y + 15},{pos_x},{pos_y},0,120)\\fad(80,0)"

            elif style_name == "emerald_money":
                # Wealth/finance business vibe with sharp green pop
                anim_dur_max = 0.140
                color_active = "50FF00" # Emerald Green in BGR
                color_other = "D8D8D8"
                alpha_other = "30"
                active_tags = f"\\c&H{color_active}&\\shad2\\fscx50\\fscy50\\t(0,90,\\fscx130\\fscy130)\\t(90,140,\\fscx100\\fscy100)"
                static_active_tags = f"\\c&H{color_active}&\\shad2"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(70,0)"

            elif style_name == "glitch_matrix":
                # Cyber hxcker neon green with quick horizontal jitter
                anim_dur_max = 0.120
                color_active = "00FF00" # Matrix Green in BGR
                color_other = "808080"
                alpha_other = "50"
                active_tags = f"\\c&H{color_active}&\\shad0\\3c&H00CC00&\\blur3\\fscx110\\fscy100\\t(0,60,\\fscx95\\fscy105)\\t(60,120,\\fscx100\\fscy100)"
                static_active_tags = f"\\c&H{color_active}&\\shad0\\3c&H00CC00&\\blur3"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(50,0)"

            elif style_name == "neon_purple_rain":
                # Electric magenta/violet with smooth breathing zoom
                anim_dur_max = 0.180
                color_active = "FF00AA" # Purple/Magenta in BGR
                color_other = "E0D0E0"
                alpha_other = "40"
                active_tags = f"\\c&H{color_active}&\\shad2\\blur2\\fscx90\\fscy90\\t(0,120,\\fscx120\\fscy120)\\t(120,180,\\fscx105\\fscy105)"
                static_active_tags = f"\\c&H{color_active}&\\shad2\\blur2\\fscx105\\fscy105"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(100,0)"

            elif style_name == "bold_impact_red":
                # Aggressive high-impact drama/crime style with punchy red
                anim_dur_max = 0.130
                color_active = "0000FF" # Pure Red in BGR
                color_other = "FFFFFF"
                alpha_other = "10" # Very little dimming for bold punch
                active_tags = f"\\c&H{color_active}&\\shad3\\fscx150\\fscy150\\t(0,80,\\fscx110\\fscy110)"
                static_active_tags = f"\\c&H{color_active}&\\shad3\\fscx110\\fscy110"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(40,0)"

            elif style_name == "sunset_vibes":
                # Warm sunset tones with gentle floating animation
                anim_dur_max = 0.200
                color_active = "60A0FF" # Warm Sunset Pink-Orange in BGR
                color_other = "EDEDED"
                alpha_other = "35"
                active_tags = f"\\c&H{color_active}&\\fscx95\\fscy95\\t(0,150,\\fscx112\\fscy112)\\t(150,200,\\fscx103\\fscy103)"
                static_active_tags = f"\\c&H{color_active}&\\fscx103\\fscy103"
                anim_effect = f"\\move({pos_x},{pos_y + 12},{pos_x},{pos_y},0,160)\\fad(100,0)"

            elif style_name == "pastel_dream":
                # Aesthetic lifestyle soft lavender with creamy elegance
                anim_dur_max = 0.180
                color_active = "F0D0FF" # Pastel Lavender in BGR
                color_other = "F5F5F5"
                alpha_other = "45"
                active_tags = f"\\c&H{color_active}&\\shad1\\blur1\\fscx98\\fscy98\\t(0,140,\\fscx108\\fscy108)"
                static_active_tags = f"\\c&H{color_active}&\\shad1\\blur1\\fscx108\\fscy108"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(120,0)"

            elif style_name == "stomp_kinetic":
                # Action stomp: slam instantly from 200% down to 100%
                anim_dur_max = 0.110
                color_active = "00FFFF" # Bright yellow in BGR
                color_other = "B0B0B0"
                alpha_other = "55"
                active_tags = f"\\c&H{color_active}&\\shad3\\fscx220\\fscy220\\t(0,80,\\fscx100\\fscy100)"
                static_active_tags = f"\\c&H{color_active}&\\shad3\\fscx100\\fscy100"
                anim_effect = f"\\pos({pos_x},{pos_y})\\fad(30,0)"
                
            else:
                anim_dur_max = 0.150
                active_tags = "\\c&H00FFFF&"
                static_active_tags = "\\c&H00FFFF&"
                anim_effect = f"\\move({pos_x},{anim_y_start},{pos_x},{pos_y},0,150)\\fad(150,0)"

            # 1. ANIMATION PHASE
            anim_dur = min(anim_dur_max, next_start - w_start)
            if anim_dur > 0.01:
                start_ts = _seconds_to_ass_time(w_start)
                end_ts   = _seconds_to_ass_time(w_start + anim_dur)
                
                pre_part = ""
                if j > 0:
                    pre_part = f"{{\\alpha&H{alpha_other}&\\c&H{color_other}&}}" + " ".join(W_texts[:j]) + " "
                    
                active_part = f"{{\\alpha&H00&{active_tags}}}" + W_texts[j]
                
                post_part = ""
                if j < len(W_texts) - 1:
                    post_part = " {\\alpha&HFF&}" + " ".join(W_texts[j+1:])
                    
                text = f"{{{anim_effect}}}" + pre_part + active_part + post_part
                lines.append(f"Dialogue: 0,{start_ts},{end_ts},Kinetic,,0,0,0,,{text}")
                
            # 2. STATIC PHASE
            static_start = w_start + anim_dur
            if next_start - static_start > 0.01:
                start_ts = _seconds_to_ass_time(static_start)
                end_ts   = _seconds_to_ass_time(next_start)
                
                pre_part = ""
                if j > 0:
                    pre_part = f"{{\\alpha&H{alpha_other}&\\c&H{color_other}&}}" + " ".join(W_texts[:j]) + " "
                    
                active_part = f"{{\\alpha&H00&{static_active_tags}}}" + W_texts[j]
                
                post_part = ""
                if j < len(W_texts) - 1:
                    post_part = " {\\alpha&HFF&}" + " ".join(W_texts[j+1:])
                    
                text = f"{{\\pos({pos_x},{pos_y})}}" + pre_part + active_part + post_part
                lines.append(f"Dialogue: 0,{start_ts},{end_ts},Kinetic,,0,0,0,,{text}")
                
        # 3. POST-GROUP PAUSE
        last_w_end = group_words[-1]["end"]
        if group_end - last_w_end > 0.05:
            start_ts = _seconds_to_ass_time(last_w_end)
            end_ts   = _seconds_to_ass_time(group_end)
            
            if style_name == "cyberpunk_neon":
                c_post = "FFFF00" # Cyan
            elif style_name == "vibrant_gradient" or style_name == "tiktok_pop":
                c_post = "00FFFF" # Yellow
            elif style_name == "cinematic_swing":
                c_post = "D0D0D0" # Soft light grey
            else:
                c_post = "FFFFFF" # White
                
            text = f"{{\\pos(540,960)\\c&H{c_post}&}}" + " ".join(W_texts)
            lines.append(f"Dialogue: 0,{start_ts},{end_ts},Kinetic,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _seconds_to_ass_time(seconds: float) -> str:
    """
    Convert a float seconds value to ASS timestamp format: H:MM:SS.cc
    (hundredths of a second, not milliseconds)

    Args:
        seconds: Time in seconds.

    Returns:
        ASS time string, e.g. "0:00:03.24"
    """
    seconds  = max(0.0, seconds)
    hours    = int(seconds // 3600)
    minutes  = int((seconds % 3600) // 60)
    secs     = seconds % 60
    centisec = int(round((secs - int(secs)) * 100))
    return f"{hours}:{minutes:02d}:{int(secs):02d}.{centisec:02d}"

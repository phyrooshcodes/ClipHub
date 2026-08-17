import os
import re
import subprocess
import logging
from typing import Any, Dict, Optional, List
import platform

logger = logging.getLogger(__name__)

NVENC_PRESET   = "p4"
NVENC_CQ       = "28"
AUDIO_BITRATE  = "192k"
_nvenc_available = None

def check_nvenc_available() -> bool:
    global _nvenc_available
    if _nvenc_available is not None:
        return _nvenc_available
    try:
        result = subprocess.run(["ffmpeg", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        available = "h264_nvenc" in result.stdout.decode("utf-8", errors="ignore")
        if available:
            probe = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=256x256:r=1", "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            available = probe.returncode == 0
        _nvenc_available = available
        return available
    except Exception:
        return False

def _run_ffmpeg(command: list) -> None:
    try:
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"FFmpeg failed with exit code {e.returncode}.\nCommand: {' '.join(command)}\nstderr:\n{stderr}") from e

def render_clip(
    input_video: str, output_path: str, start_ms: int, end_ms: int, crop_coords: Dict[str, Any],
    subtitle_path: str, music_choice: Optional[Dict[str, Any]] = None, clip_index: int = 0,
    encoder: str = "auto", editorial_data: Optional[Dict[str, Any]] = None,
    commentary_voice: str = "af_sarah", intro_duration: float = 2.5,
    ai_audio_events: List[Dict[str, Any]] = None
):
    ai_audio_events = ai_audio_events or []
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    duration_s = end_s - start_s
    crop_w, crop_h = crop_coords["crop_w"], crop_coords["crop_h"]
    dynamic_crop_x = crop_coords.get("dynamic_crop_x", [])
    fps = crop_coords.get("fps", 30.0)
    use_dynamic = len(dynamic_crop_x) > 0

    safe_sub_path = None
    if subtitle_path and os.path.exists(subtitle_path):
        rel_sub = os.path.relpath(subtitle_path).replace("\\", "/")
        if platform.system() == "Windows":
            rel_sub = re.sub(r'^([A-Za-z]):', r'\1\\:', rel_sub)
        safe_sub_path = rel_sub.replace("'", "'\\''")

    command = ["ffmpeg", "-y", "-ss", f"{start_s:.3f}", "-t", f"{duration_s:.3f}", "-i", input_video]
    input_idx = 1
    
    import av
    has_audio = False
    try:
        with av.open(input_video) as container:
            has_audio = len(container.streams.audio) > 0
    except Exception:
        pass

    silent_audio_idx = -1
    if not has_audio:
        command += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={duration_s:.3f}"]
        silent_audio_idx = input_idx
        input_idx += 1

    # Video Canvas Input (if dynamic crop)
    canvas_idx = -1
    if use_dynamic:
        command += ["-f", "lavfi", "-i", f"color=c=black:s={crop_w}x{crop_h}:r={fps}:d={duration_s:.3f}"]
        canvas_idx = input_idx
        input_idx += 1
        
        sendcmd_path = output_path + ".sendcmd.txt"
        with open(sendcmd_path, "w") as f:
            for i, cx in enumerate(dynamic_crop_x):
                f.write(f"{i/fps:.3f}-{(i+1)/fps:.3f} [enter] overlay x {-cx};\n")
        sendcmd_ffmpeg = sendcmd_path.replace("\\", "/")
        if platform.system() == "Windows":
            sendcmd_ffmpeg = re.sub(r'^([A-Za-z]):', r'\1\\:', sendcmd_ffmpeg)

    # AI Audio Inputs
    ai_inputs = []
    for ev in ai_audio_events:
        command += ["-i", ev["audio_path"]]
        ai_inputs.append({"idx": input_idx, "start_ms": int(ev["start_s"] * 1000)})
        input_idx += 1

    filter_complex = []
    
    # ─── Video Chain ───
    v_head = "0:v"
    if use_dynamic:
        filter_complex.append(f"[{canvas_idx}:v]sendcmd=f='{sendcmd_ffmpeg}'[v_cmd]")
        filter_complex.append(f"[v_cmd][0:v]overlay[over_out]")
        v_head = "over_out"
    else:
        crop_x = crop_coords.get("crop_x", 0)
        crop_y = 0
        filter_complex.append(f"[0:v]crop={crop_w}:{crop_h}:{crop_x}:{crop_y}[crop_out]")
        v_head = "crop_out"

    # Freeze-Frame Pause on Commentary & Voiceover
    # If AI commentary segments are present, freeze the video frame at the insertion point
    # so the video pauses with the pause icon while the AI speaks, and then resumes seamlessly.
    freeze_events = [
        ev for ev in ai_audio_events
        if ev.get("type") in ("commentary", "hook", "takeaway") and (ev.get("end_s", 0) - ev.get("start_s", 0)) > 0.5
    ]
    
    if freeze_events:
        freeze_events.sort(key=lambda x: x["start_s"])
        v_parts = []
        last_t = 0.0
        n_splits = len(freeze_events) + (1 if freeze_events[-1]["start_s"] < duration_s else 0)
        
        if n_splits > 1:
            split_tags = "".join(f"[v_sp_{i}]" for i in range(n_splits))
            filter_complex.append(f"[{v_head}]split={n_splits}{split_tags}")
            
            for f_idx, fev in enumerate(freeze_events):
                t_pause = min(duration_s, max(last_t + 0.05, fev["start_s"]))
                f_dur = fev["end_s"] - fev["start_s"]
                filter_complex.append(
                    f"[v_sp_{f_idx}]trim=start={last_t:.3f}:end={t_pause:.3f},setpts=PTS-STARTPTS,"
                    f"tpad=stop_mode=clone:stop_duration={f_dur:.3f}[v_frz_{f_idx}]"
                )
                v_parts.append(f"[v_frz_{f_idx}]")
                last_t = t_pause
                
            if last_t < duration_s and len(v_parts) < n_splits:
                tail_idx = len(freeze_events)
                filter_complex.append(
                    f"[v_sp_{tail_idx}]trim=start={last_t:.3f}:end={duration_s:.3f},setpts=PTS-STARTPTS[v_frz_tail]"
                )
                v_parts.append("[v_frz_tail]")
                
            if len(v_parts) > 1:
                concat_inputs = "".join(v_parts)
                filter_complex.append(f"{concat_inputs}concat=n={len(v_parts)}:v=1:a=0[v_paused]")
                v_head = "v_paused"
            elif len(v_parts) == 1:
                v_head = v_parts[0].strip("[]")

    # Scale and Subtitles (Always 100% crisp HD, zero random blur)
    if safe_sub_path:
        filter_complex.append(f"[{v_head}]scale=1080:1920,ass='{safe_sub_path}'[v_final]")
    else:
        filter_complex.append(f"[{v_head}]scale=1080:1920[v_final]")
    
    # ─── Audio Chain (Crystal-Clear Voiceover & Source Mixing) ───
    a_head = f"{silent_audio_idx}:a" if not has_audio else "0:a"
    
    if ai_inputs:
        # Delay AI tracks
        ai_delayed = []
        for ai in ai_inputs:
            filter_complex.append(f"[{ai['idx']}:a]adelay={ai['start_ms']}|{ai['start_ms']}[ai_{ai['idx']}]")
            ai_delayed.append(f"[ai_{ai['idx']}]")
            
        # Mix AI voice tracks with boost
        if len(ai_delayed) > 1:
            inputs_str = "".join(ai_delayed)
            filter_complex.append(f"{inputs_str}amix=inputs={len(ai_delayed)}:dropout_transition=0:normalize=0,volume=1.4[ai_mix]")
        else:
            filter_complex.append(f"{ai_delayed[0]}volume=1.4[ai_mix]")
            
        # Gently lower source background audio so AI voice is 100% intelligible
        filter_complex.append(f"[{a_head}]volume=0.65[bg_audio]")
        
        # Mix background audio and AI voice track cleanly, then apply EBU R128 broadcast normalization
        filter_complex.append(f"[bg_audio][ai_mix]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,loudnorm=I=-14:LRA=7:TP=-1.5,alimiter=limit=0.95[final_audio]")
        a_head = "final_audio"
    elif has_audio:
        filter_complex.append(f"[{a_head}]loudnorm=I=-14:LRA=7:TP=-1.5,alimiter=limit=0.95[final_audio]")
        a_head = "final_audio"

    filter_str = ";".join(filter_complex)
    
    use_nvenc = check_nvenc_available() if encoder == "auto" else (encoder == "h264_nvenc")
    enc_args = ["-c:v", "h264_nvenc", "-preset", NVENC_PRESET, "-cq", NVENC_CQ, "-r", "60", "-fps_mode", "cfr"] if use_nvenc else ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-r", "60", "-fps_mode", "cfr"]

    # If a_head is an input stream specifier (e.g. "0:a", "1:a"), map directly without brackets.
    # If a_head is a filtergraph label (e.g. "voice_mix", "final_audio"), enclose in brackets.
    is_direct_stream = (a_head == "0:a" or a_head == f"{silent_audio_idx}:a")
    mapped_audio = a_head if is_direct_stream else f"[{a_head}]"

    command += [
        "-filter_complex", filter_str,
        "-map", "[v_final]",
        "-map", mapped_audio,
    ] + enc_args + [
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-shortest", output_path
    ]

    logger.info(f"[Renderer] Rendering clip {clip_index + 1}: {output_path} (NVENC={use_nvenc})")
    try:
        _run_ffmpeg(command)
    except Exception as e:
        if use_nvenc and "nvenc" in str(e).lower():
            logger.warning("[Renderer] ⚠️ NVENC hardware encoder failed. Falling back to CPU encoder...")
            return render_clip(input_video, output_path, start_ms, end_ms, crop_coords, subtitle_path, music_choice, clip_index, "libx264", editorial_data, commentary_voice, intro_duration, ai_audio_events)
        raise e
    finally:
        if use_dynamic and 'sendcmd_path' in locals() and os.path.exists(sendcmd_path):
            try:
                os.remove(sendcmd_path)
            except Exception:
                pass
    logger.info(f"[Renderer] ✅ Clip {clip_index + 1} rendered → {output_path}")
    return output_path

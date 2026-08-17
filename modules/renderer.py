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
        if os.path.exists(ev["audio_path"]):
            command += ["-i", ev["audio_path"]]
            ev["input_idx"] = input_idx
            ai_inputs.append(ev)
            input_idx += 1

    filter_complex = []
    
    # ─── Video Cropping ───
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

    a_head = f"{silent_audio_idx}:a" if not has_audio else "0:a"

    # ─── Explainer Video & Audio Splicing (Strictly Sequential - ZERO Voice Overlap) ───
    if ai_inputs:
        v_segments = []
        a_segments = []
        
        # 1. AI Intro Hook (Video holds opening frame while Sarah introduces the clip)
        hook_ev = next((ev for ev in ai_inputs if ev.get("type") == "hook"), None)
        if hook_ev:
            filter_complex.append(f"[{v_head}]trim=start=0:end=0.1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={hook_ev['duration']:.3f}[v_seg_hook]")
            v_segments.append("[v_seg_hook]")
            filter_complex.append(f"[{hook_ev['input_idx']}:a]asetpts=PTS-STARTPTS[a_seg_hook]")
            a_segments.append("[a_seg_hook]")

        # 2. Source Speech and Mid-Clip Commentary Segments
        comm_events = [ev for ev in ai_inputs if ev.get("type") == "commentary"]
        comm_events.sort(key=lambda x: x.get("source_time", 0.0))
        
        last_src_t = 0.0
        for c_idx, cev in enumerate(comm_events):
            t_insert = min(duration_s, max(last_src_t + 0.1, cev.get("source_time", duration_s * 0.4)))
            
            # Source speech segment before commentary (Host speaks at full volume, AI is silent)
            filter_complex.append(f"[{v_head}]trim=start={last_src_t:.3f}:end={t_insert:.3f},setpts=PTS-STARTPTS[v_src_{c_idx}]")
            v_segments.append(f"[v_src_{c_idx}]")
            filter_complex.append(f"[{a_head}]atrim=start={last_src_t:.3f}:end={t_insert:.3f},asetpts=PTS-STARTPTS[a_src_{c_idx}]")
            a_segments.append(f"[a_src_{c_idx}]")
            
            # Freeze-frame pause during commentary (Host is 100% silent, AI explains concept)
            freeze_start = max(0.0, t_insert - 0.05)
            filter_complex.append(
                f"[{v_head}]trim=start={freeze_start:.3f}:end={t_insert:.3f},setpts=PTS-STARTPTS,"
                f"tpad=stop_mode=clone:stop_duration={cev['duration']:.3f}[v_frz_{c_idx}]"
            )
            v_segments.append(f"[v_frz_{c_idx}]")
            filter_complex.append(f"[{cev['input_idx']}:a]asetpts=PTS-STARTPTS[a_comm_{c_idx}]")
            a_segments.append(f"[a_comm_{c_idx}]")
            
            last_src_t = t_insert
            
        # 3. Final Source Speech segment to end of clip
        if last_src_t < duration_s:
            filter_complex.append(f"[{v_head}]trim=start={last_src_t:.3f}:end={duration_s:.3f},setpts=PTS-STARTPTS[v_src_tail]")
            v_segments.append("[v_src_tail]")
            filter_complex.append(f"[{a_head}]atrim=start={last_src_t:.3f}:end={duration_s:.3f},asetpts=PTS-STARTPTS[a_src_tail]")
            a_segments.append("[a_src_tail]")
            
        if len(v_segments) > 1:
            filter_complex.append(f"{''.join(v_segments)}concat=n={len(v_segments)}:v=1:a=0[v_sequenced]")
            v_head = "v_sequenced"
            
        if len(a_segments) > 1:
            filter_complex.append(f"{''.join(a_segments)}concat=n={len(a_segments)}:v=0:a=1,loudnorm=I=-14:LRA=7:TP=-1.5,alimiter=limit=0.95[final_audio]")
            a_head = "final_audio"
        elif len(a_segments) == 1:
            filter_complex.append(f"{a_segments[0]}loudnorm=I=-14:LRA=7:TP=-1.5,alimiter=limit=0.95[final_audio]")
            a_head = "final_audio"
    elif has_audio:
        filter_complex.append(f"[{a_head}]loudnorm=I=-14:LRA=7:TP=-1.5,alimiter=limit=0.95[final_audio]")
        a_head = "final_audio"

    # Scale and Subtitles (Always 100% crisp HD, zero random blur)
    if safe_sub_path:
        filter_complex.append(f"[{v_head}]scale=1080:1920,ass='{safe_sub_path}'[v_final]")
    else:
        filter_complex.append(f"[{v_head}]scale=1080:1920[v_final]")

    filter_str = ";".join(filter_complex)
    
    use_nvenc = check_nvenc_available() if encoder == "auto" else (encoder == "h264_nvenc")
    enc_args = ["-c:v", "h264_nvenc", "-preset", NVENC_PRESET, "-cq", NVENC_CQ, "-r", "60", "-fps_mode", "cfr"] if use_nvenc else ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-r", "60", "-fps_mode", "cfr"]

    is_direct_stream = (a_head == "0:a" or a_head == f"{silent_audio_idx}:a")
    mapped_audio = a_head if is_direct_stream else f"[{a_head}]"

    command += [
        "-filter_complex", filter_str,
        "-map", "[v_final]",
        "-map", mapped_audio,
    ] + enc_args + [
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path
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

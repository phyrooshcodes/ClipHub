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

    # AI Audio Inputs & Mouse Click SFX
    ai_inputs = []
    for ev in ai_audio_events:
        if os.path.exists(ev["audio_path"]):
            command += ["-i", ev["audio_path"]]
            ev["input_idx"] = input_idx
            ai_inputs.append(ev)
            input_idx += 1

    click_sfx_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "sfx", "mouse_click.mp3"))
    has_click_sfx = os.path.exists(click_sfx_path)
    click_sfx_idx = -1
    if has_click_sfx and ai_inputs:
        command += ["-i", click_sfx_path]
        click_sfx_idx = input_idx
        input_idx += 1

    avatar_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "avatars", "anime_presenter.png"))
    has_avatar = os.path.exists(avatar_path)
    avatar_input_idx = -1
    if has_avatar and ai_inputs:
        command += ["-i", avatar_path]
        avatar_input_idx = input_idx
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
        
        hook_ev = next((ev for ev in ai_inputs if ev.get("type") == "hook"), None)
        comm_events = [ev for ev in ai_inputs if ev.get("type") == "commentary"]
        comm_events.sort(key=lambda x: x.get("source_time", 0.0))
        
        # Calculate branches needed for video and audio splits
        num_v_splits = (1 if hook_ev else 0) + (len(comm_events) * 2) + 1
        num_a_splits = len(comm_events) + 1
        
        v_split_tags = [f"v_sp_{i}" for i in range(num_v_splits)]
        a_split_tags = [f"a_sp_{i}" for i in range(num_a_splits)]
        
        filter_complex.append(f"[{v_head}]split={num_v_splits}{''.join(f'[{tag}]' for tag in v_split_tags)}")
        filter_complex.append(f"[{a_head}]asplit={num_a_splits}{''.join(f'[{tag}]' for tag in a_split_tags)}")
        
        v_idx = 0
        a_idx = 0
        
        # 1. AI Intro Hook (Video holds opening frame while Sarah introduces the clip)
        if hook_ev:
            filter_complex.append(
                f"[{v_split_tags[v_idx]}]trim=start=0:end=0.1,setpts=PTS-STARTPTS,"
                f"tpad=stop_mode=clone:stop_duration={hook_ev['duration']:.3f},scale=1080:1920[v_seg_hook]"
            )
            v_segments.append("[v_seg_hook]")
            v_idx += 1
            
            filter_complex.append(f"[{hook_ev['input_idx']}:a]asetpts=PTS-STARTPTS[a_seg_hook]")
            a_segments.append("[a_seg_hook]")

        # 2. Source Speech and Mid-Clip Commentary Segments (Anime Presenter Explains)
        last_src_t = 0.0
        for c_idx, cev in enumerate(comm_events):
            t_insert = min(duration_s, max(last_src_t + 0.1, cev.get("source_time", duration_s * 0.4)))
            comm_dur = cev["duration"]
            
            # Source speech segment before commentary (Host speaks at full volume, AI is silent)
            filter_complex.append(
                f"[{v_split_tags[v_idx]}]trim=start={last_src_t:.3f}:end={t_insert:.3f},setpts=PTS-STARTPTS,scale=1080:1920[v_src_{c_idx}]"
            )
            v_segments.append(f"[v_src_{c_idx}]")
            v_idx += 1
            
            filter_complex.append(
                f"[{a_split_tags[a_idx]}]atrim=start={last_src_t:.3f}:end={t_insert:.3f},asetpts=PTS-STARTPTS[a_src_{c_idx}]"
            )
            a_segments.append(f"[a_src_{c_idx}]")
            a_idx += 1
            
            # Freeze-frame pause during commentary:
            # Whole background clip blurs, and Anime Girl slides up smoothly, floats, and slides down
            freeze_start = max(0.0, t_insert - 0.05)
            
            if has_avatar and avatar_input_idx >= 0:
                t_in = 0.45
                t_out = 0.45
                t_exit = max(t_in + 0.1, comm_dur - t_out)
                
                w_av = 932
                h_av = 1400
                x_pos = (1080 - w_av) // 2
                y_rest = 1920 - h_av + 100
                y_off = 1920
                travel = y_off - y_rest
                
                y_expr = (
                    f"if(lt(t,{t_in:.3f}), "
                    f"{y_off} - {travel} * sin(t/{t_in:.3f}*1.570796), "
                    f"if(lt(t,{t_exit:.3f}), "
                    f"{y_rest} + 16 * sin(4.712389*(t-{t_in:.3f})), "
                    f"{y_rest} + {travel} * (1 - cos((t-{t_exit:.3f})/{t_out:.3f}*1.570796))"
                    f"))"
                )
                
                filter_complex.append(
                    f"[{v_split_tags[v_idx]}]trim=start={freeze_start:.3f}:end={t_insert:.3f},setpts=PTS-STARTPTS,"
                    f"tpad=stop_mode=clone:stop_duration={comm_dur:.3f},scale=1080:1920[v_frz_raw_{c_idx}]"
                )
                filter_complex.append(
                    f"[v_frz_raw_{c_idx}]boxblur=20:5,eq=brightness=-0.08:contrast=1.05[v_frz_bg_{c_idx}]"
                )
                filter_complex.append(
                    f"[{avatar_input_idx}:v]scale={w_av}:{h_av}:flags=lanczos[v_avatar_{c_idx}]"
                )
                filter_complex.append(
                    f"[v_frz_bg_{c_idx}][v_avatar_{c_idx}]overlay=x={x_pos}:y='{y_expr}':eval=frame[v_frz_{c_idx}]"
                )
            else:
                filter_complex.append(
                    f"[{v_split_tags[v_idx]}]trim=start={freeze_start:.3f}:end={t_insert:.3f},setpts=PTS-STARTPTS,"
                    f"tpad=stop_mode=clone:stop_duration={comm_dur:.3f},scale=1080:1920[v_frz_{c_idx}]"
                )
            v_segments.append(f"[v_frz_{c_idx}]")
            v_idx += 1
            
            # Play gentle mouse click right as the pause triggers
            if has_click_sfx and click_sfx_idx >= 0:
                filter_complex.append(f"[{click_sfx_idx}:a]volume=0.30[a_sfx_click_{c_idx}]")
                filter_complex.append(
                    f"[{cev['input_idx']}:a][a_sfx_click_{c_idx}]amix=inputs=2:duration=first:dropout_transition=0,asetpts=PTS-STARTPTS[a_comm_{c_idx}]"
                )
            else:
                filter_complex.append(f"[{cev['input_idx']}:a]asetpts=PTS-STARTPTS[a_comm_{c_idx}]")
            a_segments.append(f"[a_comm_{c_idx}]")
            
            last_src_t = t_insert
            
        # 3. Final Source Speech segment to end of clip
        if last_src_t < duration_s and v_idx < num_v_splits and a_idx < num_a_splits:
            filter_complex.append(
                f"[{v_split_tags[v_idx]}]trim=start={last_src_t:.3f}:end={duration_s:.3f},setpts=PTS-STARTPTS,scale=1080:1920[v_src_tail]"
            )
            v_segments.append("[v_src_tail]")
            
            filter_complex.append(
                f"[{a_split_tags[a_idx]}]atrim=start={last_src_t:.3f}:end={duration_s:.3f},asetpts=PTS-STARTPTS[a_src_tail]"
            )
            a_segments.append("[a_src_tail]")
            
        if len(v_segments) > 1:
            filter_complex.append(f"{''.join(v_segments)}concat=n={len(v_segments)}:v=1:a=0[v_sequenced]")
            v_head = "v_sequenced"
        elif len(v_segments) == 1:
            v_head = v_segments[0].strip("[]")
            
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

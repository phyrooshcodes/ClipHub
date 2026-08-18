import os
import re
import subprocess
import logging
from typing import Any, Dict, Optional, List
import platform

logger = logging.getLogger(__name__)

NVENC_PRESET   = "p5"
NVENC_CQ       = "19"
AUDIO_BITRATE  = "320k"
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
    use_nvenc = check_nvenc_available() if encoder == "auto" else (encoder == "h264_nvenc")
    enc_args = ["-c:v", "h264_nvenc", "-preset", NVENC_PRESET, "-cq", NVENC_CQ, "-b:v", "10M", "-maxrate", "14M", "-bufsize", "20M", "-r", "60", "-fps_mode", "cfr"] if use_nvenc else ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", "60", "-fps_mode", "cfr"]

    safe_sub_path = None
    if subtitle_path and os.path.exists(subtitle_path):
        rel_sub = os.path.relpath(subtitle_path).replace("\\", "/")
        if platform.system() == "Windows":
            rel_sub = re.sub(r'^([A-Za-z]):', r'\1\\:', rel_sub)
        safe_sub_path = rel_sub.replace("'", "'\\''")

    click_sfx_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "sfx", "mouse_click.mp3"))
    has_click_sfx = os.path.exists(click_sfx_path)

    avatar_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "avatars", "anime_presenter.png"))
    has_avatar = os.path.exists(avatar_path)

    # Helper to generate smooth 2D balloon floating drift expressions
    def make_balloon_floating_expr(duration: float, is_intro: bool = False, w_av: int = 932, h_av: int = 1400):
        t_in = 0.45
        t_out = 0.45
        t_exit = max(t_in + 0.1, duration - t_out)
        x_pos_base = (1080 - w_av) // 2
        y_rest = 1920 - h_av + 100
        y_off = 1920
        travel = y_off - y_rest

        if is_intro:
            # Starts on screen at Frame 0 (0.0s) so video thumbnail is guaranteed to show the teacher!
            x_expr = (
                f"if(lt(t,{t_exit:.3f}), "
                f"{x_pos_base} + 14 * sin(1.4 * t) + 8 * cos(0.8 * t), "
                f"{x_pos_base}"
                f")"
            )
            y_expr = (
                f"if(lt(t,{t_exit:.3f}), "
                f"{y_rest} + 10 * sin(1.1 * t) + 6 * sin(2.1 * t + 0.8), "
                f"{y_rest} + {travel} * (1 - cos((t-{t_exit:.3f})/{t_out:.3f}*1.570796))"
                f")"
            )
        else:
            # Mid-clip commentary: slides up smoothly from bottom, floats during explanation, slides down
            x_expr = (
                f"if(lt(t,{t_in:.3f}), {x_pos_base}, "
                f"if(lt(t,{t_exit:.3f}), "
                f"{x_pos_base} + 14 * sin(1.4 * (t - {t_in:.3f})) + 8 * cos(0.8 * (t - {t_in:.3f})), "
                f"{x_pos_base}"
                f"))"
            )
            y_expr = (
                f"if(lt(t,{t_in:.3f}), "
                f"{y_off} - {travel} * sin(t/{t_in:.3f}*1.570796), "
                f"if(lt(t,{t_exit:.3f}), "
                f"{y_rest} + 10 * sin(1.1 * (t - {t_in:.3f})) + 6 * sin(2.1 * (t - {t_in:.3f}) + 0.8), "
                f"{y_rest} + {travel} * (1 - cos((t-{t_exit:.3f})/{t_out:.3f}*1.570796))"
                f"))"
            )
        return x_expr, y_expr

    # If Explainer AI Events present, use High-Performance Segmented Render
    if ai_audio_events:
        temp_segs_dir = os.path.join(os.path.dirname(output_path), f"temp_segs_{start_ms}")
        os.makedirs(temp_segs_dir, exist_ok=True)
        segment_files = []
        seg_idx = 0

        hook_ev = next((ev for ev in ai_audio_events if ev.get("type") == "hook"), None)
        comm_events = [ev for ev in ai_audio_events if ev.get("type") == "commentary"]
        comm_events.sort(key=lambda x: x.get("source_time", 0.0))

        # Helper to render cropped host segment
        def render_host_segment(t_from: float, t_to: float, out_file: str):
            seg_dur = t_to - t_from
            if seg_dur <= 0.01:
                return
            cmd = ["ffmpeg", "-y", "-ss", f"{start_s + t_from:.3f}", "-t", f"{seg_dur:.3f}", "-i", input_video]
            if use_dynamic:
                from_idx = int(t_from * fps)
                to_idx = int(t_to * fps)
                sub_cx = dynamic_crop_x[from_idx:to_idx+1]
                crop_x = int(sum(sub_cx) / len(sub_cx)) if sub_cx else crop_coords.get("crop_x", 0)
            else:
                crop_x = crop_coords.get("crop_x", 0)
                
            filter_str = (
                f"[0:v]crop={crop_w}:{crop_h}:{crop_x}:0,scale=1080:1920:flags=lanczos,setsar=1,fps=60,setpts=PTS-STARTPTS[v];"
                f"[0:a]aformat=channel_layouts=stereo:sample_rates=48000,asetpts=PTS-STARTPTS[a]"
            )
            cmd += [
                "-filter_complex", filter_str,
                "-map", "[v]", "-map", "[a]",
            ] + enc_args + [
                "-t", f"{seg_dur:.3f}",
                "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000", "-pix_fmt", "yuv420p", out_file
            ]
            _run_ffmpeg(cmd)

        # Helper to render avatar freeze segment
        def render_avatar_segment(freeze_t: float, audio_path: str, duration: float, out_file: str, is_intro: bool = False):
            cmd = ["ffmpeg", "-y", "-ss", f"{start_s + freeze_t:.3f}", "-i", input_video, "-i", audio_path]
            clk_idx = -1
            av_idx = -1
            inp_cnt = 2
            if has_click_sfx:
                cmd += ["-i", click_sfx_path]
                clk_idx = inp_cnt
                inp_cnt += 1
            if has_avatar:
                cmd += ["-i", avatar_path]
                av_idx = inp_cnt
                inp_cnt += 1
            
            x_expr, y_expr = make_balloon_floating_expr(duration, is_intro=is_intro)
            if is_intro:
                # Universal Black Background for Intro & Thumbnails
                fc = [
                    f"color=c=0x070709:s=1080x1920:d={duration:.3f},fps=60,setpts=PTS-STARTPTS[bg]"
                ]
            else:
                # Freeze & blur host video during mid-clip commentary breakdown
                fc = [
                    f"[0:v]trim=start=0:end=0.04,scale=1080:1920:flags=lanczos,setsar=1,boxblur=15:3,eq=brightness=-0.08:contrast=1.05,tpad=stop_mode=clone:stop_duration={duration:.3f},trim=start=0:end={duration:.3f},fps=60,setpts=PTS-STARTPTS[bg]"
                ]
            if has_avatar and av_idx >= 0:
                fc.append(f"[{av_idx}:v]scale=932:1400:flags=lanczos[av]")
                fc.append(f"[bg][av]overlay=x='{x_expr}':y='{y_expr}':eval=frame,scale=1080:1920:flags=lanczos,setsar=1,fps=60,setpts=PTS-STARTPTS[v]")
            else:
                fc.append(f"[bg]null,scale=1080:1920:flags=lanczos,setsar=1,fps=60,setpts=PTS-STARTPTS[v]")

            if has_click_sfx and clk_idx >= 0:
                fc.append(f"[{clk_idx}:a]volume=0.30[clk]")
                fc.append(f"[1:a][clk]amix=inputs=2:duration=first:dropout_transition=0,aformat=channel_layouts=stereo:sample_rates=48000,asetpts=PTS-STARTPTS[a]")
            else:
                fc.append(f"[1:a]aformat=channel_layouts=stereo:sample_rates=48000,asetpts=PTS-STARTPTS[a]")

            cmd += [
                "-filter_complex", ";".join(fc),
                "-map", "[v]", "-map", "[a]",
            ] + enc_args + [
                "-t", f"{duration:.3f}",
                "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000", "-pix_fmt", "yuv420p", out_file
            ]
            _run_ffmpeg(cmd)

        logger.info(f"[Renderer] Rendering {len(ai_audio_events)} explainer segments (NVENC={use_nvenc}) ...")
        # 1. Render Hook
        if hook_ev and os.path.exists(hook_ev["audio_path"]):
            hook_file = os.path.join(temp_segs_dir, f"seg_{seg_idx:02d}_hook.mp4")
            render_avatar_segment(0.0, hook_ev["audio_path"], hook_ev["duration"], hook_file, is_intro=True)
            segment_files.append(hook_file)
            seg_idx += 1

        # 2. Render Commentary Segments
        last_t = 0.0
        for c_idx, cev in enumerate(comm_events):
            t_ins = min(duration_s, max(last_t + 0.1, cev.get("source_time", duration_s * 0.4)))
            # Host Part
            host_file = os.path.join(temp_segs_dir, f"seg_{seg_idx:02d}_host.mp4")
            render_host_segment(last_t, t_ins, host_file)
            if os.path.exists(host_file):
                segment_files.append(host_file)
                seg_idx += 1
            # Commentary Part
            if os.path.exists(cev["audio_path"]):
                comm_file = os.path.join(temp_segs_dir, f"seg_{seg_idx:02d}_comm.mp4")
                freeze_t = max(0.0, t_ins - 0.05)
                render_avatar_segment(freeze_t, cev["audio_path"], cev["duration"], comm_file, is_intro=False)
                segment_files.append(comm_file)
                seg_idx += 1
            last_t = t_ins

        # 3. Render Host Tail
        if last_t < duration_s:
            tail_file = os.path.join(temp_segs_dir, f"seg_{seg_idx:02d}_tail.mp4")
            render_host_segment(last_t, duration_s, tail_file)
            if os.path.exists(tail_file):
                segment_files.append(tail_file)
                seg_idx += 1

        # 4. Concat all segments and apply subtitles
        list_file = os.path.join(temp_segs_dir, "concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for sfile in segment_files:
                clean_sfile = os.path.abspath(sfile).replace("\\", "/")
                f.write(f"file '{clean_sfile}'\n")

        logger.info(f"[Renderer] Assembling {len(segment_files)} segments with subtitles -> {output_path}")
        concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file]
        if safe_sub_path:
            concat_cmd += [
                "-vf", f"ass='{safe_sub_path}'",
            ] + enc_args + [
                "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000", "-movflags", "+faststart", output_path
            ]
        else:
            concat_cmd += [
                "-c", "copy", "-movflags", "+faststart", output_path
            ]
        _run_ffmpeg(concat_cmd)

        # 5. Generate pristine clean 1080x1920 cover thumbnail image
        try:
            thumb_path = f"{os.path.splitext(output_path)[0]}_thumb.jpg"
            if has_avatar:
                cmd_thumb = [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "color=c=0x070709:s=1080x1920:d=1",
                    "-i", avatar_path,
                    "-filter_complex", "[1:v]scale=932:1400:flags=lanczos[av];[0:v][av]overlay=(1080-932)/2:(1920-1400+100)",
                    "-vframes", "1", "-q:v", "1",
                    thumb_path
                ]
                _run_ffmpeg(cmd_thumb)
                logger.info(f"[Renderer] 📸 Saved clean cover thumbnail: {thumb_path}")
            else:
                cmd_thumb = [
                    "ffmpeg", "-y", "-ss", "0.0", "-i", output_path,
                    "-vframes", "1", "-q:v", "1", thumb_path
                ]
                _run_ffmpeg(cmd_thumb)
        except Exception as e:
            logger.warning(f"[Renderer] Could not generate cover thumbnail: {e}")

        # Cleanup segments
        try:
            for sfile in segment_files:
                if os.path.exists(sfile):
                    os.remove(sfile)
            if os.path.exists(list_file):
                os.remove(list_file)
            os.rmdir(temp_segs_dir)
        except Exception:
            pass

        logger.info(f"[Renderer] ✅ Explainer Clip {clip_index + 1} rendered successfully → {output_path}")
        return output_path

    # Standard single-pass render (for clips without AI events)
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

    filter_complex = []
    v_head = "0:v"
    if use_dynamic:
        filter_complex.append(f"[{canvas_idx}:v]sendcmd=f='{sendcmd_ffmpeg}'[v_cmd]")
        filter_complex.append(f"[v_cmd][0:v]overlay[over_out]")
        v_head = "over_out"
    else:
        crop_x = crop_coords.get("crop_x", 0)
        filter_complex.append(f"[0:v]crop={crop_w}:{crop_h}:{crop_x}:0[crop_out]")
        v_head = "crop_out"

    a_head = f"{silent_audio_idx}:a" if not has_audio else "0:a"
    if has_audio:
        filter_complex.append(f"[{a_head}]loudnorm=I=-14:LRA=7:TP=-1.5,alimiter=limit=0.95[final_audio]")
        a_head = "final_audio"

    if safe_sub_path:
        filter_complex.append(f"[{v_head}]scale=1080:1920,ass='{safe_sub_path}'[v_final]")
    else:
        filter_complex.append(f"[{v_head}]scale=1080:1920[v_final]")

    filter_str = ";".join(filter_complex)
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

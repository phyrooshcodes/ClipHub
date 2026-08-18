# ============================================================
# audio_demux.py — Module 1: Audio Extraction
# Hardware Target: CPU Thread Pool
# Purpose: Rip the audio track from the input video to a
#          16kHz mono WAV file — the ideal format for Whisper.
# ============================================================

import subprocess
import os
import logging

logger = logging.getLogger(__name__)


def extract_audio(input_video: str, output_audio: str = "temp/audio.wav") -> str:
    """
    Extract audio from a video file using FFmpeg.
    If the video has no audio streams, synthesizes a clean silent WAV file matching duration.
    """
    if not os.path.isfile(input_video):
        raise FileNotFoundError(f"Input video not found: {input_video}")

    os.makedirs(os.path.dirname(output_audio) or ".", exist_ok=True)
    logger.info(f"[AudioDemux] Extracting audio from: {input_video}")

    command = [
        "ffmpeg",
        "-y",
        "-i", input_video,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_audio
    ]

    try:
        subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        logger.info(f"[AudioDemux] ✅ Audio extracted → {output_audio}")
        return output_audio
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode("utf-8", errors="ignore")
        # Check if the error is due to missing audio stream
        if "does not contain any stream" in error_msg.lower() or "matches no streams" in error_msg.lower() or "no audio" in error_msg.lower():
            logger.warning("[AudioDemux] Source video contains no audio stream. Generating silent audio fallback...")
            dur = get_video_duration(input_video)
            silent_dur = max(1.0, dur if dur > 0 else 5.0)
            silent_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono",
                "-t", f"{silent_dur:.3f}",
                "-acodec", "pcm_s16le",
                output_audio
            ]
            subprocess.run(silent_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            logger.info(f"[AudioDemux] ✅ Generated silent audio track ({silent_dur:.1f}s) → {output_audio}")
            return output_audio
        raise RuntimeError(f"[AudioDemux] FFmpeg failed:\n{error_msg}") from e


def get_video_duration(input_video: str) -> float:
    """
    Use FFprobe to get the duration of a video in seconds.
    Falls back gracefully if format headers are missing.
    """
    if not os.path.isfile(input_video):
        return 0.0

    # 1. Probe format duration
    try:
        command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_video
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10.0)
        dur_str = result.stdout.decode().strip()
        if dur_str:
            dur = float(dur_str)
            if dur > 0:
                logger.info(f"[AudioDemux] Video duration: {dur:.2f}s")
                return dur
    except Exception:
        pass

    # 2. Fallback: probe video stream duration
    try:
        command = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_video
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10.0)
        dur_str = result.stdout.decode().strip()
        if dur_str:
            dur = float(dur_str)
            if dur > 0:
                return dur
    except Exception:
        pass

    return 0.0

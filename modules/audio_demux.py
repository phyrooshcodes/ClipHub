# ============================================================
# audio_demux.py — Module 1: Audio Extraction
# Hardware Target: CPU Thread Pool (Ryzen 7)
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

    Args:
        input_video: Absolute or relative path to the source MP4.
        output_audio: Destination path for the extracted WAV file.

    Returns:
        Path to the extracted WAV file.

    Raises:
        FileNotFoundError: If the input video does not exist.
        RuntimeError: If FFmpeg fails during extraction.
    """
    if not os.path.isfile(input_video):
        raise FileNotFoundError(f"Input video not found: {input_video}")

    # Ensure temp directory exists
    os.makedirs(os.path.dirname(output_audio), exist_ok=True)

    logger.info(f"[AudioDemux] Extracting audio from: {input_video}")

    command = [
        "ffmpeg",
        "-y",                   # Overwrite output without asking
        "-i", input_video,      # Input video
        "-vn",                  # No video stream
        "-acodec", "pcm_s16le", # 16-bit PCM — lossless, Whisper-compatible
        "-ar", "16000",         # 16kHz sample rate (Whisper optimal)
        "-ac", "1",             # Mono channel (Whisper optimal)
        output_audio
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        logger.info(f"[AudioDemux] ✅ Audio extracted → {output_audio}")
        return output_audio

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"[AudioDemux] FFmpeg failed:\n{error_msg}") from e


def get_video_duration(input_video: str) -> float:
    """
    Use FFprobe to get the duration of a video in seconds.

    Args:
        input_video: Path to the video file.

    Returns:
        Duration in seconds as a float.
    """
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_video
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    duration = float(result.stdout.decode().strip())
    logger.info(f"[AudioDemux] Video duration: {duration:.2f}s")
    return duration

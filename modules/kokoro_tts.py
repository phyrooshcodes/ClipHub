import os
import sys
import urllib.request
from pathlib import Path
import soundfile as sf
import logging

logger = logging.getLogger("ClipHub.KokoroTTS")

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

_kokoro_instance = None

def _download_file(url, dest_path):
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    logger.info(f"Downloading {url} to {dest_path}...")
    try:
        with urllib.request.urlopen(url, context=ctx) as response, open(dest_path, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        logger.info(f"Successfully downloaded {dest_path}.")
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        raise

def get_kokoro_instance():
    """Initializes and caches the Kokoro ONNX model."""
    global _kokoro_instance
    if _kokoro_instance is not None:
        return _kokoro_instance

    base_dir = Path(__file__).parent.parent
    models_dir = base_dir / "models" / "kokoro"
    models_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = models_dir / "kokoro-v1.0.onnx"
    voices_path = models_dir / "voices-v1.0.bin"

    if not model_path.exists():
        _download_file(MODEL_URL, str(model_path))
    
    if not voices_path.exists():
        _download_file(VOICES_URL, str(voices_path))

    from kokoro_onnx import Kokoro
    try:
        logger.info("Initializing Kokoro ONNX model...")
        _kokoro_instance = Kokoro(str(model_path), str(voices_path))
        logger.info("Kokoro ONNX model initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Kokoro model: {e}")
        raise

    return _kokoro_instance

def generate_speech(text: str, output_path: str, voice: str = "af_sarah", speed: float = 1.0):
    """
    Synthesizes speech from text using the specified voice.
    Saves the output as a WAV file.
    """
    kokoro = get_kokoro_instance()
    
    try:
        logger.info(f"Synthesizing speech: '{text[:30]}...' with voice '{voice}'")
        audio, sample_rate = kokoro.create(
            text, voice=voice, speed=speed, lang="en-us"
        )
        sf.write(output_path, audio, sample_rate)
        logger.info(f"Speech saved to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error during speech generation: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_text = "This is a test of the ClipHub local AI commentary engine."
    out_file = "test_kokoro_output.wav"
    generate_speech(test_text, out_file)
    print(f"Test generated at {out_file}")

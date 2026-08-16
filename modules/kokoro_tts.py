import os
import sys
import urllib.request
from pathlib import Path
import soundfile as sf
import logging

logger = logging.getLogger("ClipHub.KokoroTTS")

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.fp16.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

import asyncio
import threading

_kokoro_instance = None
_kokoro_lock = threading.Lock()

def _download_file(url, dest_path):
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    logger.info(f"Downloading {url} to {dest_path}...")
    temp_path = dest_path + ".tmp"
    try:
        with urllib.request.urlopen(url, context=ctx) as response, open(temp_path, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(temp_path, dest_path)
        logger.info(f"Successfully downloaded {dest_path}.")
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        logger.error(f"Failed to download {url}: {e}")
        raise

def get_kokoro_instance():
    """Initializes and caches the Kokoro ONNX model thread-safely."""
    global _kokoro_instance
    with _kokoro_lock:
        if _kokoro_instance is not None:
            return _kokoro_instance

        base_dir = Path(__file__).parent.parent
        models_dir = base_dir / "models" / "kokoro"
        models_dir.mkdir(parents=True, exist_ok=True)
        
        # Check for existing kokoro-v1.0.onnx or fp16 variant with valid size (>1000 bytes)
        model_path = models_dir / "kokoro-v1.0.onnx"
        if not model_path.exists() or model_path.stat().st_size < 1000:
            model_path = models_dir / "kokoro-v1.0.fp16.onnx"
            if not model_path.exists() or model_path.stat().st_size < 1000:
                _download_file(MODEL_URL, str(model_path))
        
        voices_path = models_dir / "voices-v1.0.bin"
        if not voices_path.exists() or voices_path.stat().st_size < 1000:
            _download_file(VOICES_URL, str(voices_path))

        from kokoro_onnx import Kokoro
        try:
            import onnxruntime as rt
            available_providers = rt.get_available_providers()
            logger.info(f"Available ONNX providers: {available_providers}")
            
            logger.info("Initializing Kokoro ONNX model...")
            _kokoro_instance = Kokoro(str(model_path), str(voices_path))
            if hasattr(_kokoro_instance, "sess"):
                logger.info(f"Kokoro ONNX model initialized successfully. Active providers: {_kokoro_instance.sess.get_providers()}")
        except Exception as e:
            logger.error(f"Failed to initialize Kokoro model: {e}")
            raise

        return _kokoro_instance

def generate_speech(text: str, output_path: str, voice: str = "af_sarah", speed: float = 1.0, lang: str = "en-us") -> str:
    """
    Synthesizes speech from text using the specified voice.
    Saves the output as a WAV file.
    """
    kokoro = get_kokoro_instance()
    
    try:
        logger.info(f"Synthesizing speech: '{text[:30]}...' with voice '{voice}'")
        audio, sample_rate = kokoro.create(
            text, voice=voice, speed=speed, lang=lang
        )
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        sf.write(output_path, audio, sample_rate)
        logger.info(f"Speech saved to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error during speech generation: {e}")
        raise

def generate_tts_sync(text: str, voice_id: str, output_path: str, speed: float = 1.0, lang: str = "en-us") -> float:
    """
    Synchronous TTS generation that returns audio duration in seconds.
    Safe to call from sync functions without event loop conflicts.
    """
    kokoro = get_kokoro_instance()
    try:
        logger.info(f"Generating TTS (duration probe): '{text[:30]}...' (voice: {voice_id})")
        audio, sample_rate = kokoro.create(
            text, voice=voice_id, speed=speed, lang=lang
        )
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        sf.write(output_path, audio, sample_rate)
        duration = float(len(audio)) / float(sample_rate)
        logger.info(f"TTS generated: {duration:.2f}s -> {output_path}")
        return duration
    except Exception as e:
        logger.error(f"Error in generate_tts_sync: {e}")
        return 0.0

async def generate_tts(text: str, voice_id: str, output_path: str, speed: float = 1.0, lang: str = "en-us") -> float:
    """
    Non-blocking async wrapper that offloads TTS compute to a worker thread.
    """
    return await asyncio.to_thread(generate_tts_sync, text, voice_id, output_path, speed, lang)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_text = "This is a test of the ClipHub local AI commentary engine."
    out_file = "test_kokoro_output.wav"
    generate_speech(test_text, out_file)
    print(f"Test generated at {out_file}")
    print(f"Test generated at {out_file}")

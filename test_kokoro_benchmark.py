import time
import psutil
import pynvml
import logging
from modules.kokoro_tts import get_kokoro_instance, generate_speech

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Benchmark")

def get_vram_usage():
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return info.used / (1024 * 1024)
    except Exception:
        return -1
    finally:
        try:
            pynvml.nvmlShutdown()
        except:
            pass

def main():
    print("--- Kokoro TTS CUDA Benchmark ---")
    
    vram_before = get_vram_usage()
    print(f"VRAM Usage Before Load: {vram_before:.2f} MB")
    
    t0 = time.time()
    kokoro = get_kokoro_instance()
    t1 = time.time()
    print(f"Model Load Time: {t1 - t0:.2f} s")
    
    providers = kokoro.sess.get_providers()
    print(f"Selected Providers: {providers}")
    # We should know from logs what available providers were, but let's recheck
    import onnxruntime as rt
    print(f"Available Providers: {rt.get_available_providers()}")
    
    # We don't have access to the exact model path in the instance directly easily, but we know what we passed
    # Actually kokoro_onnx saves it? We'll just read from our script logic.
    print("Model loaded successfully.")
    
    vram_after_load = get_vram_usage()
    print(f"VRAM Usage After Load: {vram_after_load:.2f} MB")
    if vram_before > 0:
        print(f"Estimated VRAM used by Kokoro: {vram_after_load - vram_before:.2f} MB")
    
    test_text = "This is a comprehensive standalone benchmark test to evaluate the performance of Kokoro TTS running with CUDA Execution Provider using half precision."
    
    print("\nStarting Synthesis...")
    t2 = time.time()
    generate_speech(test_text, "temp/benchmark_kokoro.wav", voice="af_sarah", speed=1.0)
    t3 = time.time()
    
    print(f"Synthesis Time: {t3 - t2:.2f} s")
    print(f"Text Length: {len(test_text)} characters")

if __name__ == "__main__":
    main()

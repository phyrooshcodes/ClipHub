# ✦ Obscura Clips
### Zero-Strain Local-Hybrid AI Video Clipper
> GPU-Accelerated & Thermally Optimized

---

## What It Does

Obscura Clips takes any long-form video (such as podcasts, interviews, or lectures) and automatically produces viral-ready **9:16 vertical clips** with:

- 🎙️ **GPU AI Transcription** — `faster-whisper` (runs on CUDA with float16 fallback to CPU INT8)
- 🧠 **Viral Hook Detection** — Llama 3.3 70B (with Llama 3.1 405B / Qwen 2.5 72B fallback) via NVIDIA NIM cloud API (evaluates transcription chunks, finds standalone viral loops)
- 👁️ **Face-Tracked Cropping** — OpenCV Haar Cascades (keeps the speaker centered in the 9:16 crop)
- 💬 **Kinetic Subtitles** — TikTok-style word-sliding opacity animation
- 🎵 **Curated Background Music** — Intelligent ambient/lofi/synth music selection with automated speech-ducking sidechain compression
- 🚀 **NVENC GPU Encoding** — Offloads video rendering completely to the RTX GPU hardware encoding block

---

## Hardware & System Requirements

| Stage | Hardware Target | Details |
|---|---|---|
| Audio Demux | CPU (disk I/O) | Extremely fast audio extraction |
| ASR Transcription | **GPU (CUDA)** | Uses `faster-whisper` with local CUDA DLL runtime injection |
| Hook Detection | **☁ NVIDIA NIM** | Llama 3.3 70B (with Llama 3.1 405B / Qwen 2.5 72B fallback) runs in the cloud to select premium clips |
| Face Tracking | CPU MediaPipe | Auto-tracks speaker movement to keep them centered |
| Audio Mixing | CPU FFmpeg | Loops, fades, and ducks background music behind vocals |
| Final Render | **GPU NVENC** | GPU-accelerated video encoding (100+ FPS, keeps shaders cool) |

---

## Setup Instructions

### Personal Instagram Reel uploads (Playwright)

Obscura Clips uses your local Instagram browser session for personal desktop
uploads. No Meta app, OAuth token, Business account, or public media hosting is
required. In **Settings → Instagram → Connect**, complete login in the browser
window once; subsequent uploads reuse the saved session automatically. If it
expires, a login window opens during the next queued upload.

Uploads are placed in a single-file SQLite queue and have states: queued,
uploading, retrying, completed, failed, or needs manual verification. The same
video is hash-protected against accidental duplicate uploads; confirm the UI
prompt only when you deliberately want to post it again.

Manual Publish is the default. Choose **Auto Publish** in Settings to queue a
clip after each render. Uploads stay on one background worker, in FIFO order;
the generator never waits for Instagram and upload failures never stop clip
generation. Browser/network failures receive at most three total attempts.
Login, security challenges, rate limits, rejections, duplicates, and uncertain
post-Share outcomes are terminal and never retry automatically.

The **Upload Center** is the publishing dashboard. It shows the active upload,
FIFO queue, completed work, failures, manual-verification items, elapsed
progress state, and per-upload event timeline. It can pause/resume the worker,
retry terminal items, mark manually verified Reels complete, clear failures,
and safely reorder or cancel uploads that have not started. The status pill in
the lower-right corner opens it at any time.

Session cookies, queue history, screenshots, HTML, console/network logs, and
Playwright traces are stored outside this repository under
`~/.local/state/obscura-clips/instagram/` on Linux (or `LOCALAPPDATA` on
Windows). Failed runs save diagnostics there. Set `OBSCURA_INSTAGRAM_HEADLESS=0`
in `.env` if a visible browser works better on your machine.

An upload is only marked completed after Instagram displays a share-confirmation
signal. If Share was clicked but confirmation cannot be observed, it is marked
**Needs Manual Verification** and is never auto-retried, avoiding duplicates.

Troubleshooting:

- **Login browser does not appear:** run `playwright install chromium` in the
  project virtual environment, then use the Instagram Connect button again.
- **Session expired:** queue the clip again; a visible browser opens once so
  you can complete Instagram's login or security check. The queue then resumes.
- **Failed:** hover the Publish button for the complete error. Inspect the
  latest folder under the state directory for `failure.png`, `page.html`,
  `console.log`, and `trace.zip`.
- **Needs Manual Verification:** inspect your Instagram profile before taking
  any further action. Do not retry unless the Reel is definitely absent.
- **Duplicate warning:** choose the confirmation only when reposting the same
  video is intentional.

Run the offline queue tests with:

```bash
venv/bin/python -m unittest tests/test_instagram_queue.py
```

### Native acceleration (Linux, optional but recommended)

The application remains Python-first. The optional `_obscura_native` extension
only accelerates small CPU kernels used by adaptive face tracking; FastAPI,
FFmpeg, Whisper, OpenCV, and the UI keep their existing integrations.

Install a C++17 compiler, CMake, and Python's development headers using your
distribution's packages (for example, `build-essential cmake python3-dev` on
Debian/Ubuntu). Then create/activate a virtual environment and install in
editable mode:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

`pip install -e .` installs the normal Python requirements and builds the
pybind11 extension reproducibly through CMake. A source checkout still works
without the extension: `modules.native_accel` falls back to NumPy.

To compare the kernel used for adaptive face tracking with its NumPy fallback:

```bash
python benchmarks/benchmark_native_accel.py
# End-to-end comparison on a representative segment
python benchmarks/benchmark_face_tracking.py input.mp4 --end-ms 30000
```

On a static talking-head clip, opt into the activity gate from Python to avoid
repeating Haar detection for visually unchanged sampled frames:

```python
compute_crop_coords(video, start_ms, end_ms, adaptive_sampling=True)
```

It is deliberately disabled by default, so existing CLI and UI output remains
unchanged. Tune `activity_threshold` only after checking representative clips;
rapid cuts, camera motion, and compression noise may require a higher value.

### 1. External System Prerequisites
1. **FFmpeg**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add `C:\ffmpeg\bin` to your system `PATH`.
2. **NVIDIA GPU Drivers**: Ensure your Nvidia drivers are updated. The pipeline auto-configures and runs Whisper and NVENC on CUDA.
3. **NVIDIA NIM API Key**: 
   * Sign up for a free account at [NVIDIA build](https://build.nvidia.com/) to get free API credits.
   * Rename `.env.example` in this folder to `.env`.
   * Add your API key:
     ```env
     NVIDIA_API_KEY=nvapi-XXXXXX
     ```

### 2. How to Run (One-Click)
Simply double-click **`run_windows.bat`**. The script will automatically:
1. Detect Python and FFmpeg.
2. Initialize the Python virtual environment (`venv`) if it's the first run and install all libraries (including CUDA runtime packages).
3. Start the Web Dashboard server.
4. Open the app automatically in your browser at **`http://localhost:7842`**.

---

## Command Line Usage (Advanced)

If you prefer to run it via CLI:

```bash
# Activate venv
venv\Scripts\activate

# Basic run (takes defaults: small Whisper model, max 10 clips)
python local_clipping_pipeline.py --input video.mp4

# Run with custom max clips (up to 30) and custom background music
python local_clipping_pipeline.py --input video.mp4 --max-clips 15 --music lofi
```

### All Flags

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | *(required)* | Path to input video |
| `--output-dir` / `-o` | `output/` | Where rendered clips are saved |
| `--model` / `-m` | `small` | Whisper model: `tiny`, `base`, `small` (default) |
| `--language` / `-l` | auto | ISO 639-1 language code |
| `--max-clips` | `10` | Max number of clips to generate (1-30) |
| `--music` | `none` | Music vibe: `none`, `auto`, `ambient`, `lofi`, `focus` |
| `--keep-temp` | false | Keep `temp/` folder (useful for debugging) |

---

## Project Structure

```
Obscura Clips/
├── run_windows.bat          ← Double click to run the app
├── .env.example             ← Rename to .env and enter NVIDIA key
├── requirements.txt
├── README.md
├── modules/
│   ├── audio_demux.py       ← Stage 1: Demux audio
│   ├── transcriber.py       ← Stage 2: GPU/CPU Whisper Transcription
│   ├── hook_detector.py     ← Stage 3: Llama & Qwen NIM Hook Detection
│   ├── face_tracker.py      ← Stage 4: OpenCV face tracking
│   ├── subtitle_engine.py   ← Stage 5: TikTok sliding-opacity ASS subtitle gen
│   └── renderer.py          ← Stage 6: FFmpeg NVENC render & Audio sidechain
├── native/obscura_native.cpp ← Optional pybind11 C++ kernels
├── benchmarks/benchmark_native_accel.py
├── benchmarks/benchmark_face_tracking.py
├── pyproject.toml            ← Editable native/Python build configuration
├── output/                  ← Final clips saved here (auto-created)
└── temp/                    ← Temporary audio/word cache (auto-cleaned)
```

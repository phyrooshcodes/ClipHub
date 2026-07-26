<div align="center">
  <h1>✦ Obscura Clips ✦</h1>
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=24&pause=1000&color=FF9900&center=true&vCenter=true&width=600&height=60&lines=Zero-Strain+Local-Hybrid+AI+Clipper;GPU-Accelerated+%26+Thermally+Optimized;Powered+by+Rust+%26+NVIDIA+NIM;Fully+Automated+Social+Pipeline" alt="Typing SVG" />
  <p><b>An advanced AI video pipeline that extracts viral clips, tracks faces, and automates YouTube & Instagram uploads.</b></p>

  [![Python](https://img.shields.io/badge/Python-3.12-blue.svg?style=for-the-badge&logo=python)](https://python.org)
  [![Rust](https://img.shields.io/badge/Rust-Blazing_Fast-orange.svg?style=for-the-badge&logo=rust)](https://rust-lang.org)
  [![CUDA](https://img.shields.io/badge/CUDA-Accelerated-76B900.svg?style=for-the-badge&logo=nvidia)](https://developer.nvidia.com/cuda-toolkit)
</div>

<br/>

## 🚀 Quickstart: Install & Run

Get the project up and running in minutes.

### Prerequisites
1. **FFmpeg**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add it to your system `PATH`.
2. **NVIDIA GPU Drivers**: Ensure your drivers are updated for CUDA/NVENC support.
3. **Rust Compiler**: Install Rust via [rustup.rs](https://rustup.rs/) (required for native engine).
4. **NVIDIA NIM API Key**: Sign up at [build.nvidia.com](https://build.nvidia.com/) for a free key, rename `.env.example` to `.env`, and add it: `NVIDIA_API_KEY=nvapi-XXXXXX`.

### Installation & Launch

```bash
# 1. Clone the repository
git clone https://github.com/phyrooshcodes/Obscura-Clips.git
cd Obscura-Clips

# 2. Create and activate a virtual environment
python -m venv venv
# On Windows: venv\Scripts\activate
# On Linux/Mac: source venv/bin/activate

# 3. Install Python dependencies and Maturin
pip install -r requirements.txt
pip install maturin

# 4. Compile the Rust acceleration engine
maturin develop --release --manifest-path clip_engine_core/Cargo.toml

# 5. Start the Web Dashboard
python server.py
```
*Open your browser to **`http://localhost:7842`** to access the Obscura UI!*

*(Windows users can also just double-click **`run_windows.bat`** for a one-click automated startup).*

---

## 🛠️ Technical Details & Features

### What It Does
Obscura Clips takes any long-form video (such as podcasts, interviews, or lectures) and automatically produces viral-ready **9:16 vertical clips** with:
- 🎙️ **GPU AI Transcription** — `faster-whisper` (runs on CUDA with float16 fallback to CPU INT8)
- 🧠 **Viral Hook Detection** — Llama 3.3 70B (with Llama 3.1 405B fallback) via NVIDIA NIM cloud API (evaluates transcription chunks, finds standalone viral loops, and outputs **Amazon Product Recommendations**)
- 👁️ **Face-Tracked Cropping** — OpenCV Haar Cascades (keeps the speaker centered in the 9:16 crop)
- 💬 **Kinetic Subtitles** — TikTok-style word-sliding opacity animation
- 🎵 **Curated Background Music** — Intelligent ambient/lofi/synth music selection with automated speech-ducking sidechain compression
- 🚀 **NVENC GPU Encoding** — Offloads video rendering completely to the RTX GPU hardware encoding block

### Hardware & System Targeting
| Stage | Hardware Target | Details |
|---|---|---|
| Audio Demux | CPU (disk I/O) | Extremely fast audio extraction |
| ASR Transcription | **GPU (CUDA)** | Uses `faster-whisper` with local CUDA DLL runtime injection |
| Hook Detection | **☁ NVIDIA NIM** | Llama 3.3 70B runs in the cloud to select premium clips |
| Face Tracking | CPU MediaPipe | Auto-tracks speaker movement to keep them centered |
| Heavy Computation | **🦀 Rust Native** | Core matrix processing and bounding boxes processed in Rust (`clip_engine_core`) |
| Final Render | **GPU NVENC** | GPU-accelerated video encoding (100+ FPS, keeps shaders cool) |

### Automated Social Publishing
Obscura Clips features an entirely automated publish pipeline for YouTube and Instagram:
- **Instagram Reels**: Uses an automated Playwright session tied to your local browser. It manages a persistent local login without needing the Meta Graph API or Business Accounts.
- **YouTube Shorts**: Automates posting to YouTube via standard uploads or authenticated browser sessions.
- Uploads are queued via SQLite. Errors, duplicates, and terminal rejects are handled cleanly in the background while video generation continues unaffected.
- **Auto-Publish Mode**: Turn this on in settings, and clips will be uploaded automatically as soon as NVENC finishes rendering.

### Advanced Command Line Usage
If you prefer to run it via CLI without the UI:
```bash
# Basic run (takes defaults: small Whisper model, max 10 clips)
python local_clipping_pipeline.py --input video.mp4

# Run with custom max clips and ambient background music
python local_clipping_pipeline.py --input video.mp4 --max-clips 15 --music lofi
```

**CLI Flags:**
| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | *(required)* | Path to input video |
| `--output-dir` / `-o` | `output/` | Where rendered clips are saved |
| `--model` / `-m` | `small` | Whisper model: `tiny`, `base`, `small` (default) |
| `--max-clips` | `10` | Max number of clips to generate (1-30) |
| `--music` | `none` | Music vibe: `none`, `auto`, `ambient`, `lofi`, `focus` |

---

## 📁 Project Structure

```text
Obscura Clips/
├── run_windows.bat          ← Double click to run the app
├── clip_engine_core/        ← Rust Native Acceleration backend
├── api/                     ← FastAPI backend routers (Jobs, Social)
├── ui/                      ← Vanilla JS & CSS Frontend (Web Dashboard)
├── modules/
│   ├── audio_demux.py       ← Stage 1: Demux audio
│   ├── transcriber.py       ← Stage 2: GPU/CPU Whisper Transcription
│   ├── hook_detector.py     ← Stage 3: Llama & Qwen NIM Hook Detection
│   ├── face_tracker.py      ← Stage 4: OpenCV face tracking
│   ├── subtitle_engine.py   ← Stage 5: Kinetic TikTok subtitle generation
│   └── renderer.py          ← Stage 6: FFmpeg NVENC render
├── output/                  ← Final clips saved here
└── temp/                    ← Temporary caches (auto-cleaned)
```

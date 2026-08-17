<div align="center">

  <h1>✦ ClipHub ✦</h1>
  
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=24&pause=1000&color=FF9900&center=true&vCenter=true&width=600&height=60&lines=Zero-Strain+Local-Hybrid+AI+Clipper;GPU-Accelerated+%26+Thermally+Optimized;Powered+by+Rust+%26+NVIDIA+NIM;Fully+Automated+Social+Pipeline" alt="Typing SVG" />
  
  <p><b>An advanced AI video pipeline that extracts viral clips, tracks faces, and automates YouTube & Instagram uploads.</b></p>

  [![Python](https://img.shields.io/badge/Python-3.12-blue.svg?style=for-the-badge&logo=python)](https://python.org)
  [![Rust](https://img.shields.io/badge/Rust-Blazing_Fast-orange.svg?style=for-the-badge&logo=rust)](https://rust-lang.org)
  [![CUDA](https://img.shields.io/badge/CUDA-Accelerated-76B900.svg?style=for-the-badge&logo=nvidia)](https://developer.nvidia.com/cuda-toolkit)

</div>

<br/>

## 🚀 Quickstart: Install & Run

Get the project up and running in minutes!

### Prerequisites
1. **FFmpeg**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add it to your system `PATH`.
2. **NVIDIA GPU Drivers**: Ensure your drivers are updated for CUDA/NVENC support.
3. **Rust Compiler**: Install Rust via [rustup.rs](https://rustup.rs/) (required for native engine).
4. **NVIDIA NIM API Key**: Sign up at [build.nvidia.com](https://build.nvidia.com/) for a free key.

### Installation & Launch

> ⚡ **Zero-Click Installation!** The provided scripts automatically clone your `.env` file, build your virtual environment, fetch Playwright chromium dependencies, and compile the native Rust backend engine completely out-of-the-box.

1. **Clone the repository**
   ```bash
   git clone https://github.com/phyrooshcodes/ClipHub.git
   cd ClipHub
   ```

2. **Launch the Engine**
   - 🪟 **Windows:** Double-click `run_windows.bat`
   - 🐧 **Linux / Mac:** Run `./run_linux.sh`

*That's it! The UI will automatically compile the Rust backend on first boot and open directly. You can paste your NVIDIA key directly into the UI Settings.*

---

<br/>

## 🛠️ Technical Details & Features

### What It Does
ClipHub takes any long-form video (such as podcasts, interviews, or lectures) and automatically produces viral-ready **9:16 vertical clips** with:

- 🎙️ **GPU AI Transcription** — `faster-whisper` (runs on CUDA with float16 fallback to CPU INT8)
- 🧠 **Viral Hook Detection** — Llama 3.3 70B (with Llama 3.1 405B fallback) via NVIDIA NIM cloud API (evaluates transcription chunks, finds standalone viral loops, and outputs **Amazon Product Recommendations**)
- 👁️ **Face-Tracked Cropping** — OpenCV Haar Cascades (keeps the speaker centered in the 9:16 crop)
- 💬 **Kinetic Subtitles** — TikTok-style word-sliding opacity animation
- 🎵 **Curated Background Music** — Intelligent ambient/lofi/synth music selection with automated speech-ducking sidechain compression
- 🚀 **NVENC GPU Encoding** — Offloads video rendering completely to the RTX GPU hardware encoding block

<br/>

### ⚙️ Hardware & System Targeting
> We meticulously optimized the architecture to map specific workloads to your machine's ideal hardware blocks, preventing thermal throttling during massive batch operations.

| Stage | Hardware Target | Details |
| :--- | :--- | :--- |
| **Audio Demux** | `CPU (Disk I/O)` | Extremely fast audio extraction via FFmpeg |
| **ASR Transcription** | `GPU (CUDA)` | Uses `faster-whisper` with local CUDA DLL runtime injection |
| **Hook Detection** | `☁️ NVIDIA NIM` | Llama 3.3 70B runs in the cloud to select premium clips |
| **Face Tracking** | `CPU (MediaPipe)` | Auto-tracks speaker movement to keep them centered |
| **Heavy Math** | `🦀 Rust Native` | Core matrix processing and bounding boxes processed in Rust (`clip_engine_core`) |
| **Final Render** | `GPU (NVENC)` | Hardware-accelerated video encoding (100+ FPS, keeps shaders cool) |

<br/>

### 📱 Automated Social Publishing
ClipHub features an entirely automated publish pipeline for YouTube and Instagram:
- **Instagram Reels**: Uses an automated Playwright session tied to your local browser. It manages a persistent local login without needing the Meta Graph API or Business Accounts.
- **YouTube Shorts**: Automates posting to YouTube via standard uploads or authenticated browser sessions.
- **Queue System**: Uploads are queued via SQLite. Errors, duplicates, and terminal rejects are handled cleanly in the background while video generation continues unaffected.
- **Auto-Publish Mode**: Turn this on in settings, and clips will be uploaded automatically as soon as NVENC finishes rendering.

---

<br/>

## 💻 Advanced Command Line Usage
If you prefer to run it via CLI without the UI:
```bash
# Basic run (takes defaults: small Whisper model, max 10 clips)
python local_clipping_pipeline.py --input video.mp4

# Run with custom max clips and ambient background music
python local_clipping_pipeline.py --input video.mp4 --max-clips 15 --music lofi
```

**CLI Flags:**
| Flag | Default | Description |
| :--- | :--- | :--- |
| `--input` / `-i` | *(required)* | Path to input video |
| `--output-dir` / `-o` | `output/` | Where rendered clips are saved |
| `--model` / `-m` | `small` | Whisper model: `tiny`, `base`, `small` (default) |
| `--max-clips` | `10` | Max number of clips to generate (1-30) |
| `--music` | `none` | Music vibe: `none`, `auto`, `ambient`, `lofi`, `focus` |

---

<br/>

## 📁 Project Structure

```text
ClipHub/
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

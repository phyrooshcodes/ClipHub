<div align="center">

  <h1>✦ ClipHub ✦</h1>
  
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=24&pause=1000&color=FF9900&center=true&vCenter=true&width=700&height=60&lines=AI+Viral+Clip+Extraction+%26+Social+Automation;Animated+Explainer+Presenter+with+2D+Balloon+Drift;High-Performance+Segmented+NVENC+Rendering;Powered+by+Llama+3.3+70B+%26+Kokoro+TTS" alt="Typing SVG" />
  
  <p><b>An enterprise-grade, GPU-accelerated AI video engine that transforms long-form videos into viral vertical explainer clips with animated presenters, dynamic face tracking, kinetic subtitles, and automated social publishing.</b></p>

  [![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
  [![NVIDIA](https://img.shields.io/badge/CUDA_%26_NVENC-Accelerated-76B900.svg?style=for-the-badge&logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-toolkit)
  [![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
  [![FFmpeg](https://img.shields.io/badge/FFmpeg-60fps_CFR-007808.svg?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)

</div>

<br/>

---

## 🌟 What Makes ClipHub Unique?

ClipHub goes beyond basic clipping. It creates **Viral Explainer Videos** engineered for maximum viewer retention on Instagram Reels, TikTok, and YouTube Shorts:

1. 👩‍🏫 **Animated Explainer Presenter**
   - Introduces the problem/insight during the opening hook ($t=0.0$).
   - Re-appears during a freeze-frame pause mid-clip to break down complex concepts into simple terms.
   - Smooth sinusoidal slide-in/out easing ($0.45\text{s}$) with gentle mouse-click sound effects.
   - Half-speed organic **2D balloon floating drift** in all directions over a beautifully blurred background.
2. 🎙️ **Kokoro-82M Local Neural TTS**
   - High-fidelity natural voiceover (`af_sarah`, `am_adam`) powered by ONNX Runtime.
   - Zero voice collisions: host and presenter audio are sequenced with mathematical precision.
3. 👁️ **DNN Face Tracking (YuNet & MediaPipe)**
   - Automatically tracks the active speaker and crops 16:9 landscape video into pristine 9:16 vertical video using 1-Euro smoothing filters.
4. 💬 **Kinetic Word-Level Subtitles**
   - Rapid-fire word highlighting in popular styles: *TikTok Bold, Alex Hormozi, Developer Cyan, Minimal, Cyberpunk*.
   - Dynamic timeline shifting guarantees captions display continuously from second 0 to the very last millisecond.
5. ⚡ **High-Speed Segmented NVENC Engine**
   - Slices video into independent micro-segments rendered at **400+ FPS** via hardware NVENC.
   - Strict **9:16 vertical resolution**, **Square Pixels (`SAR 1:1`)**, **60 FPS Constant Frame Rate (`CFR`)**, and **48,000 Hz Stereo Audio**.
   - Zero memory leaks: RAM consumption is locked under **30 MB** even during hours-long batch operations.

---

<br/>

## 🚀 Quickstart: Install & Run

### Prerequisites
1. **FFmpeg**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to system `PATH`.
2. **NVIDIA GPU**: RTX / GTX series GPU with updated drivers for CUDA & NVENC acceleration.
3. **NVIDIA NIM API Key**: Free API key from [build.nvidia.com](https://build.nvidia.com/) (for Llama 3.3 70B viral hook detection).

### One-Click Launch

- 🪟 **Windows**: Double-click `run_windows.bat`
- 🐧 **Linux / macOS**: Run `./run_linux.sh`

*The Web Dashboard will launch automatically at **`http://localhost:7842`**.*

---

<br/>

## 🛠️ Architecture & Pipeline Overview

```text
[ Long Video (16:9) ]
         │
         ▼
[ Stage 1: Audio Demux ] ──> Fast stream copy via FFmpeg
         │
         ▼
[ Stage 2: GPU Transcription ] ──> faster-whisper (CUDA float16)
         │
         ▼
[ Stage 3: AI Viral Hook & Script Gen ] ──> Llama 3.3 70B (NVIDIA NIM)
         │                                   ├── Hook problem statement
         │                                   └── Mid-clip plain-English breakdown
         ▼
[ Stage 4: Face Tracking & Cropping ] ──> OpenCV YuNet DNN (9:16 vertical)
         │
         ▼
[ Stage 4.5: Local Neural TTS & Timeline Alignment ] ──> Kokoro-82M ONNX
         │                                               ├── Hook WAV & Transcripts
         │                                               └── Commentary WAV & Transcripts
         ▼
[ Stage 5: Kinetic Subtitle Generation ] ──> Advanced ASS formatting with dynamic shift
         │
         ▼
[ Stage 6: Segmented NVENC Video Render ] ──> Multi-segment 60fps CFR render & assembly
         │
         ▼
[ Final Viral Clip (9:16 Vertical HD) ]
```

---

<br/>

## 💻 CLI Usage

You can also run the full pipeline or individual phases directly from the terminal:

```bash
# End-to-end processing with AI Commentary & Anime Presenter
python local_clipping_pipeline.py --input "path/to/podcast.mp4" --output-dir "output/my_clips"

# Run with custom caption style and voice
python local_clipping_pipeline.py --input "video.mp4" --caption-style hormozi --commentary-voice af_sarah

# Two-Phase Workflow:
# Phase 1: Transcribe & generate AI scripts without rendering video
python local_clipping_pipeline.py --input "video.mp4" --output-dir "output/run1" --phase 1

# Phase 2: Render clips using cached Phase 1 metadata
python local_clipping_pipeline.py --input "video.mp4" --output-dir "output/run1" --phase 2
```

### CLI Options

| Argument | Default | Description |
| :--- | :--- | :--- |
| `--input`, `-i` | *(required)* | Path to the source video file |
| `--output-dir`, `-o` | `output/` | Directory where rendered MP4 clips are saved |
| `--phase` | `all` | Execution phase: `all`, `1` (analysis only), `2` (render only) |
| `--caption-style` | `tiktok` | Subtitle preset: `tiktok`, `hormozi`, `dev`, `minimal`, `neon` |
| `--commentary-voice` | `af_sarah` | Kokoro voice: `af_sarah` (female), `am_adam` (male) |
| `--commentary-mode` | `auto` | Explainer insertion: `auto`, `hook_only`, `breakdown_only`, `off` |
| `--max-clips` | `10` | Maximum number of viral clips to extract |
| `--music` | `none` | Background music vibe: `none`, `ambient`, `lofi`, `focus` |

---

<br/>

## 📁 Repository Structure

```text
ClipHub/
├── run_windows.bat                  ← One-click Windows runner
├── local_clipping_pipeline.py       ← Core standalone execution pipeline
├── server.py                        ← FastAPI REST API & WebSocket server
├── assets/
│   ├── avatars/                     ← Presenter character graphics (PNG cutouts)
│   ├── sfx/                         ← Transition sound effects (mouse clicks, whooshes)
│   └── music/                       ← Curated background audio tracks
├── modules/
│   ├── audio_demux.py               ← FFmpeg audio extraction
│   ├── transcriber.py               ← GPU Whisper ASR
│   ├── hook_detector.py             ← Llama 3.3 70B viral clip selector
│   ├── face_tracker.py              ← OpenCV YuNet DNN face detection
│   ├── kokoro_tts.py                ← Local Kokoro-82M neural TTS
│   ├── editorial_compositor.py      ← Plain-English script alignment
│   ├── subtitle_engine.py           ← Kinetic ASS subtitle generator
│   └── renderer.py                  ← Segmented NVENC video rendering engine
├── ui/                              ← Interactive Web Dashboard
└── output/                          ← Rendered MP4 viral explainer clips
```

---

<br/>

---

<br/>

## 🌐 Social Media Auto-Publishing (YouTube Shorts & Instagram Reels)

ClipHub features fully automated, 1-click social media publishing with automated 12:00 AM scheduling and Amazon affiliate product tagging.

### 📺 YouTube Shorts Setup (Official Google OAuth 2.0)

ClipHub uses the **Official YouTube Data API v3** for 100% reliable background uploads without browser popups, CAPTCHAs, or 2FA session interruptions.

#### 1. Setup Google Cloud Credentials (2 minutes):
1. Visit the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project named **ClipHub**.
3. Go to **APIs & Services > Library** $\rightarrow$ Search for **YouTube Data API v3** $\rightarrow$ Click **Enable**.
4. Go to **APIs & Services > Credentials** $\rightarrow$ Click **Create Credentials** $\rightarrow$ **OAuth client ID**.
5. Select Application Type: **Desktop App** (or Web Application with redirect URI `http://localhost:7842/api/social/youtube/callback`).
6. Click **Create** and **Download JSON** $\rightarrow$ Save file as:
   ```
   credentials/client_secrets.json
   ```
   *(Or simply upload this file directly from the ClipHub Web UI by clicking **Connect YouTube**)*.

#### 2. Authorize & Choose Your Channel:
1. Click **Connect YouTube** in the ClipHub dashboard $\rightarrow$ Click **Authorize with Google**.
2. **Selecting between Multiple Channels (e.g. *Right Pull*):**
   - When Google's authorization window opens in your browser, Google displays all channels and Brand Accounts under your email.
   - Select your intended channel (e.g., **Right Pull**).
   - Click **Allow**.
3. Google grants a secure `refresh_token` locked specifically to that channel.
4. ClipHub displays the connected channel name and avatar on the dashboard. All future uploads will publish directly to **Right Pull**!

---

<br/>

## 📜 License & Credits

- Built with ❤️ for content creators and educators.
- Powered by [Faster Whisper](https://github.com/SYSTRAN/faster-whisper), [Kokoro TTS](https://huggingface.co/hexgrad/Kokoro-82M), [NVIDIA NIM](https://build.nvidia.com/), and [FFmpeg](https://ffmpeg.org/).

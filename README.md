# 🎙️ Voxa — Local Voice Typing for Windows

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](#)
[![Engine](https://img.shields.io/badge/Engine-faster--whisper%20(CTranslate2)-22c55e)](#)
[![GPU](https://img.shields.io/badge/CUDA-FP16%20Accelerated-76B900?logo=nvidia&logoColor=white)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Voxa** is a lightweight, 100% local push-to-talk voice dictation app for Windows inspired by **Wispr Flow**.

Hold down **`Left Ctrl`** (or any customizable hotkey), speak naturally, and release — your speech is transcribed in under a second on your local GPU (or CPU) using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and typed directly into whatever window or application is active.

No cloud servers. No monthly subscription. No telemetry. Completely offline after the initial model download.

---

## ✨ Key Features

- **⚡ Hold-to-Talk, Release-to-Type**: Works universally across any Windows application — VS Code, Cursor, Chrome, WhatsApp, Discord, Notion, Word, Slack, or terminal windows.
- **🔒 100% Local & Private**: Audio never leaves your machine. Powered by CTranslate2 (`faster-whisper`) running locally on your NVIDIA GPU (`float16`) with automatic fallback to CPU (`int8`).
- **💊 Non-Intrusive Floating Status Pill**: A sleek Wispr Flow-style floating indicator at the bottom center of your screen shows real-time state (`● Listening...` → `● Transcribing...` → `✓ Typed`) using Win32 `WS_EX_NOACTIVATE` so it **never steals keyboard focus** from your active window.
- **🧠 Smart Modifier & Shortcut Passthrough**:
  - Ignores quick taps shorter than `0.3s`.
  - Automatically cancels recording if you press another key while holding `Ctrl` (so `Ctrl+C`, `Ctrl+V`, `Ctrl+Z`, `Ctrl+A`, etc. work normally without interruption).
- **⏪ Zero-Clipping Audio Pre-Roll Buffer**: Continuously maintains a rolling `300ms` audio pre-roll buffer in memory so the very first syllable you speak is never cut off.
- **🔇 Built-in Voice Activity Detection (Silero VAD)**: Filters out background noise and silence automatically so coughing or empty holds don't produce hallucinated text.
- **🎛️ Live System Tray Controls**: Runs silently in the Windows System Tray with a color-coded microphone icon and right-click menu to switch hotkeys, switch languages, toggle **Start with Windows**, or toggle audio cues on the fly.
- **🔌 Automatic CUDA DLL Discovery**: Automatically locates pip-installed NVIDIA `cuBLAS` and `cuDNN` runtime wheels — no manual CUDA Toolkit installation or system `PATH` editing required.

---

## 🆚 Why Voxa?

| Feature | **Voxa** | Cloud Dictation Apps (e.g., Wispr Flow) | Windows Built-in (`Win+H`) |
|---|---|---|---|
| **Cost** | **Free & Open Source** | $10–$15 / month | Free |
| **Privacy** | **100% Local & Offline** | Audio sent to cloud servers | Often cloud-dependent |
| **Model Accuracy** | **Whisper `large-v3-turbo`** | Proprietary cloud ASR | Basic OS speech model |
| **Interaction** | **Hold key to talk, release to type** | Hold key to talk, release to type | Toggle on/off UI box |
| **Custom Vocabulary** | **Yes (`initial_prompt`)** | Yes | No |

---

## 🏗️ How It Works

```text
[Always-On Mic Stream (16 kHz Mono)]
        │
        ▼
[300ms Rolling Pre-Roll Buffer] ◄── Prevents clipping the first word
        │
  (Hold Left Ctrl > 0.3s)
        │  ──► Floating Pill: "● Listening..." + High Beep (880 Hz)
        ▼
[Accumulate Audio Frames] ──► (If another key pressed, e.g. Ctrl+C: Cancel & Ignore)
        │
  (Release Left Ctrl)
        │  ──► Floating Pill: "● Transcribing..." + Low Beep (440 Hz)
        ▼
[Silero VAD Filter + faster-whisper (CUDA FP16 / CPU INT8)]
        │
        ▼
[Win32 Unicode SendInput] ──► Types text into active window + Floating Pill: "✓ Typed"
```

---

## 💻 System Requirements

- **OS**: Windows 10 or Windows 11 (64-bit)
- **Python**: Python 3.10 – 3.14
- **Microphone**: Any built-in or external microphone
- **Hardware**:
  - **Recommended**: NVIDIA GPU with 4 GB+ VRAM (RTX 20/30/40/50 series or GTX 16+ series) for ~0.4s–0.7s transcriptions with `large-v3-turbo`.
  - **CPU-Only**: Any modern multi-core Intel/AMD CPU (use `"model": "small"` or `"base"` in `config.json` for fast CPU response).

### 📊 Whisper Model Comparison

You can choose any of the following models in `config.json`:

| Model Name | Disk / VRAM Size | Relative Speed | Accuracy | Best For |
|---|---|---|---|---|
| `large-v3-turbo` *(default)* | ~1.6 GB | ⚡⚡⚡⚡ Fast (GPU) | ⭐⭐⭐⭐⭐ Best | Modern GPUs (4 GB+ VRAM) |
| `large-v3` | ~3.1 GB | ⚡⚡ Moderate (GPU) | ⭐⭐⭐⭐⭐ Maximum | Maximum multilingual accuracy |
| `medium` | ~1.5 GB | ⚡⚡⚡ Fast | ⭐⭐⭐⭐ High | Mid-range GPUs |
| `small` | ~480 MB | ⚡⚡⚡⚡ Very Fast | ⭐⭐⭐⭐ Good | Fast CPU or entry-level GPU |
| `base` | ~145 MB | ⚡⚡⚡⚡⚡ Instant | ⭐⭐⭐ Decent | Lightweight CPU laptops |
| `tiny` | ~75 MB | ⚡⚡⚡⚡⚡ Instant | ⭐⭐ Basic | Ultra-low-resource machines |

---

## 🚀 Installation & Setup

### 1. Clone or Download the Repository
```bash
git clone https://github.com/<your-username>/voxa.git
cd voxa
```
*(Or download the ZIP from GitHub and extract it to any folder.)*

### 2. Run One-Time Setup
Double-click **`setup.bat`**.

What `setup.bat` does automatically:
1. Creates an isolated Python virtual environment (`.venv`).
2. Installs `faster-whisper`, `sounddevice`, `pynput`, `pystray`, `pillow`, and NVIDIA CUDA 12 runtime libraries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`).
3. Generates the application icon (`app.ico`) and compiles the native windowless launcher (`WhisperType.exe`).
4. Creates **Desktop** and **Start Menu** shortcuts.

### 3. Launch the App
- Double-click **`WhisperType.exe`** in the folder (or launch it from your **Desktop** or **Start Menu**).
- **First Launch Note**: On the very first run, Voxa downloads the `large-v3-turbo` model (~1.6 GB) from Hugging Face into your local cache (`~/.cache/huggingface/hub`). Subsequent launches load **100% offline in ~4 seconds**.

---

## 🎯 How to Use

1. **Wait for the Green Pill / Green Tray Icon**:
   When launched, a floating pill at the bottom of your screen says `Loading large-v3-turbo...` and then turns green: `Ready — Hold [ctrl_l] to talk`.
2. **Dictate Anywhere**:
   - Click into any text box (browser, code editor, chat app, document).
   - **Hold down `Left Ctrl`** for at least `0.3s` — you will hear a short high beep and see the red **`● Listening...`** pill.
   - **Speak naturally**.
   - **Release `Left Ctrl`** — you will hear a low beep, the pill turns amber (**`● Transcribing...`**), and your transcribed text is immediately typed into the active window.
3. **Customize via System Tray**:
   Look in the bottom-right Windows system tray (near the clock) for the microphone icon. **Right-click** it to:
   - Switch **Hotkey** (`Left Ctrl`, `Right Ctrl`, `Right Alt`, `Caps Lock`, `F8`, `F9`)
   - Switch **Language** (`English`, `Auto-detect`, `Nepali`, `Hindi`)
   - Toggle **Show Floating Pill**
   - Toggle **Sound Beeps**
   - Toggle **Start with Windows**
   - Open **`config.json`** or **Quit**

---

## ⚙️ Configuration Reference (`config.json`)

All settings are stored in `config.json` next to `whisper_type.py`:

```json
{
  "hotkey": "ctrl_l",
  "model": "large-v3-turbo",
  "device": "auto",
  "compute_type": "auto",
  "language": "en",
  "beam_size": 5,
  "initial_prompt": "",
  "min_hold_seconds": 0.3,
  "trailing_space": true,
  "beep": true,
  "show_overlay": true
}
```

### Detailed Option Guide

- **`hotkey`** *(string)*: Push-to-talk key. Supported values include:
  - Modifiers: `"ctrl_l"`, `"ctrl_r"`, `"alt_l"`, `"alt_r"`, `"shift_l"`, `"shift_r"`
  - Lock / Function keys: `"caps_lock"`, `"scroll_lock"`, `"pause"`, `"insert"`, `"f1"` through `"f12"`
- **`model`** *(string)*: Any Whisper model size (`"tiny"`, `"base"`, `"small"`, `"medium"`, `"large-v3"`, `"large-v3-turbo"`, `"distil-large-v3"`) or a local path to a CTranslate2 model directory.
- **`device`** *(string)*: `"auto"` (tries `"cuda"` first, falls back to `"cpu"`), `"cuda"`, or `"cpu"`.
- **`compute_type`** *(string)*: `"auto"` (uses `"float16"` on CUDA, `"int8"` on CPU), `"float16"`, `"int8_float16"`, `"int8"`, or `"float32"`.
- **`language`** *(string or null)*: ISO-639-1 language code such as `"en"` (English), `"ne"` (Nepali), `"hi"` (Hindi), `"es"` (Spanish), `"fr"` (French), `"de"` (German), `"ja"` (Japanese), `"zh"` (Chinese), or `null` for automatic language detection.
- **`beam_size`** *(integer)*: Beam search width for decoding (default `5`). Lowering to `1` increases speed slightly on slower CPUs.
- **`initial_prompt`** *(string)*: Optional context prompt to bias spelling of proper nouns, names, or technical vocabulary (e.g. `"Gaurav, FastAPI, PyTorch, Kubernetes, Kathmandu"`).
- **`min_hold_seconds`** *(float)*: Minimum hold time in seconds before recording starts (default `0.3`). Prevents accidental triggers on quick taps.
- **`trailing_space`** *(boolean)*: Appends a trailing space after each dictated segment so consecutive sentences flow naturally (default `true`).
- **`beep`** *(boolean)*: Plays subtle audio tones when recording starts and stops (default `true`).
- **`show_overlay`** *(boolean)*: Displays the floating bottom status pill (default `true`).

---

## 📁 Project Structure

```text
voxa/
├── whisper_type.py     # Core application (audio pre-roll, faster-whisper engine, tray icon & floating pill UI)
├── launcher.cs         # Native C# Win32 windowless executable launcher source
├── WhisperType.exe     # Compiled native Windows background launcher (zero console window)
├── config.json         # User configuration (hotkey, model, language, overlay, audio cues)
├── requirements.txt    # Python dependencies (faster-whisper, sounddevice, pynput, pystray, pillow, CUDA libs)
├── setup.bat           # One-click environment installer, .exe compiler, and shortcut creator
├── run.bat             # Quick launcher script
├── app.ico             # Generated multi-resolution microphone application icon
├── .gitignore          # Excludes .venv, logs, and build artifacts from Git
├── LICENSE             # MIT License
└── README.md           # Project documentation
```

---

## 🛠️ Troubleshooting & FAQ

### 1. It doesn't type into a window running as Administrator (e.g., elevated Command Prompt / Task Manager)
Windows User Interface Privilege Isolation (UIPI) blocks standard-privilege apps from sending synthetic keystrokes to elevated Administrator windows. To dictate into an Administrator window, right-click `WhisperType.exe` and select **Run as administrator**.

### 2. First launch stays on "Loading model..." for a long time
On the very first launch, Voxa downloads the selected model (`~1.6 GB` for `large-v3-turbo`) from Hugging Face. Depending on your internet speed, this one-time download can take several minutes. Once cached in `C:\Users\<you>\.cache\huggingface\hub`, all future startups load offline in ~4 seconds.

### 3. I don't have an NVIDIA GPU (or want lower memory usage)
Open `config.json` and change `"model": "large-v3-turbo"` to `"model": "small"` or `"model": "base"`. Voxa will automatically detect that CUDA is unavailable and run on your CPU using fast `int8` quantization.

### 4. Where are error logs saved when running in the background?
When running windowlessly via `WhisperType.exe`, all startup messages and errors are logged to `whisper_type.log` in the application folder.

---

## 📄 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for full details.

<div align="center">

# 🎵 Audio Sync Tool

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)](https://github.com/blast1see/AudioSyncTool)
[![Release](https://img.shields.io/badge/Release-v2.1.0-orange?style=flat-square)](https://github.com/blast1see/AudioSyncTool/releases)

**A robust audio delay detection and synchronization tool with a modern dark-themed GUI.**

[🌐 Language Selection](README.md) · [🇹🇷 Türkçe](README_TR.md)

</div>

---

## 📖 About

**Audio Sync Tool** is a robust audio delay detection and synchronization tool with a modern dark-themed GUI. It analyzes two audio files, detects the time offset between them using cross-correlation, and produces a perfectly synchronized output. Whether you're dealing with out-of-sync dubs, misaligned audio tracks, or FPS-converted content, Audio Sync Tool handles it all with precision.

## 📸 Screenshots

![Audio Sync Tool - English UI](https://github.com/user-attachments/assets/a1c300d1-c5e5-44ff-b86f-73d17aa0bd23)

## ✨ Key Features

- **Cross-correlation based delay detection** — robust & accurate offset calculation
- **6 synchronization modes** — adelay+amix, aresample, atempo, rubberband, apad+atrim, asyncts
- **MKV/MP4 container support** — auto-detect and extract audio streams
- **Drag & drop file support** — seamless file loading with tkinterdnd2
- **Dolby Digital (AC3) and Dolby Digital Plus (EAC3) encoding** — via [deew](https://github.com/pcroland/deew) / DEE
- **FPS conversion** — 23.976 ↔ 25 ↔ 29.97 etc.
- **Bilingual UI** — English / Turkish
- **Dark-themed modern interface** — easy on the eyes
- **Preserves original audio quality** — bit depth, sample rate, channels

## 💻 System Requirements

| Requirement | Details |
|---|---|
| **Python** | 3.10 or higher |
| **FFmpeg** | Required — must be in system PATH |
| **deew + DEE** | Optional — for Dolby Digital / Dolby Digital Plus encoding |

## 📦 Installation

### Option 1: Pre-built Windows Executable

Download the latest pre-built `.exe` from the [Releases](https://github.com/blast1see/AudioSyncTool/releases) page. No Python installation required.

### Option 2: Run from Source

```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

### Optional: Drag & Drop Support

```bash
pip install tkinterdnd2
```

> **Note:** `tkinterdnd2` enables drag & drop functionality in the GUI. The application works without it, but file selection will be limited to the file browser dialog.

## 📋 Usage Guide

1. **Select Source Audio** — Click "Browse" or drag & drop the audio file that needs to be synchronized (the one with the delay).
2. **Select Sync Target** — Click "Browse" or drag & drop the reference audio file (the correctly timed one).
3. **Configure Settings:**
   - Choose the synchronization mode
   - Set output format and encoding options
   - Optionally enable Dolby encoding or FPS conversion
4. **Start Sync** — Click the "Start Sync" button. The tool will analyze the delay and produce the synchronized output.

## 🎵 Supported Formats

### Audio Formats

| Format | Extension |
|---|---|
| Waveform Audio | `.wav` |
| MP3 | `.mp3` |
| FLAC | `.flac` |
| AAC | `.aac` |
| Ogg Vorbis | `.ogg` |
| MPEG-4 Audio | `.m4a` |
| Dolby Digital | `.ac3` |
| Dolby Digital Plus | `.eac3` |
| DTS | `.dts` |
| Matroska Audio | `.mka` |
| Opus | `.opus` |
| Windows Media Audio | `.wma` |

### Container Formats (audio extraction)

| Format | Extension |
|---|---|
| Matroska Video | `.mkv` |
| MPEG-4 Video | `.mp4` |
| MPEG-4 Video | `.m4v` |
| WebM | `.webm` |
| MPEG Transport Stream | `.ts` |
| MPEG Transport Stream | `.mts` |

## 🔄 Synchronization Modes

| Mode | Description |
|---|---|
| **adelay + amix** | Applies a delay filter and mixes audio streams. Best general-purpose mode. |
| **aresample** | Resamples audio to adjust timing. Good for minor drift corrections. |
| **atempo** | Changes audio tempo without altering pitch. Useful for speed-based sync. |
| **rubberband** | High-quality time-stretching using the Rubber Band library. Best for quality-sensitive work. |
| **apad + atrim** | Pads and trims audio to match target duration. Simple and effective. |
| **asyncts** | Asynchronous timestamp correction. Good for streams with variable timing. |

## 🔊 Dolby Encoding (DEE / deew)

Audio Sync Tool integrates with **[deew](https://github.com/pcroland/deew)** to provide Dolby Digital (AC3) and Dolby Digital Plus (EAC3) encoding capabilities.

### Requirements

- **[deew](https://github.com/pcroland/deew)** — A Dolby Encoding Engine wrapper (install via `pip install deew`)
- **DEE (Dolby Encoding Engine)** — The proprietary Dolby encoder binary (required by deew)

### How it works

1. Audio Sync Tool first synchronizes the audio using FFmpeg
2. The synchronized output is then passed to deew for Dolby encoding
3. The final output is a properly encoded AC3 or EAC3 file

> **Important:** DEE (Dolby Encoding Engine) is a proprietary tool required by deew. Please refer to the [deew documentation](https://github.com/pcroland/deew) for setup instructions.

## 🎬 FPS Conversion

Audio Sync Tool can compensate for frame rate differences between video sources. When audio is extracted from a video with a different frame rate than the target, the tool adjusts the audio duration accordingly.

Common conversions:
- 23.976 fps ↔ 25 fps (PAL ↔ NTSC Film)
- 23.976 fps ↔ 29.97 fps
- 25 fps ↔ 29.97 fps

## 🏗️ Building EXE

To build a standalone Windows executable:

```bash
python setup.py
```

This uses PyInstaller to create a single `.exe` file in the `dist/` directory.

## 📁 Project Structure

```
AudioSyncTool/
├── audio_sync.py            # Entry point
├── setup.py                 # PyInstaller build script
├── create_icon.py           # Icon generator
├── requirements.txt         # Python dependencies
├── LICENSE                  # MIT License
├── README.md                # Language selector
├── README_EN.md             # English documentation
├── README_TR.md             # Turkish documentation
├── audio_sync/
│   ├── __init__.py          # Package init & version
│   ├── __main__.py          # Module entry point
│   ├── config.py            # Configuration management
│   ├── i18n.py              # Internationalization (EN/TR)
│   ├── utils.py             # Utility functions
│   ├── core/
│   │   ├── __init__.py
│   │   ├── analyzer.py      # Audio analysis & cross-correlation
│   │   ├── deew_encoder.py  # Dolby encoding integration
│   │   ├── ffmpeg_wrapper.py# FFmpeg command builder
│   │   └── models.py        # Data models
│   └── ui/
│       ├── __init__.py
│       ├── app.py           # Main application window
│       ├── drop_zone.py     # Drag & drop widget
│       └── stream_dialog.py # Audio stream selection dialog
```

## 📚 Dependencies

### Required

| Package | Purpose |
|---|---|
| **numpy** | Numerical operations for audio analysis |
| **scipy** | Cross-correlation and signal processing |
| **FFmpeg** | Audio decoding, encoding, and processing (system binary) |

### Optional

| Package | Purpose |
|---|---|
| **tkinterdnd2** | Drag & drop support in the GUI |
| **deew** | Dolby Digital / Dolby Digital Plus encoding |

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

Please make sure your code follows the existing style and includes appropriate documentation.

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

Made with ❤️ by [blast1see](https://github.com/blast1see)

</div>

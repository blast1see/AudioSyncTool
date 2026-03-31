# 🎵 Audio Sync Tool

<div align="center">

**Sağlam gecikme tespiti & senkronizasyon aracı**
**Robust delay detection & synchronization tool**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![Release](https://img.shields.io/github/v/release/blast1see/AudioSyncTool?include_prereleases)](https://github.com/blast1see/AudioSyncTool/releases)

</div>

> **⬇️ Windows kullanıcıları**: [Releases](https://github.com/blast1see/AudioSyncTool/releases) sayfasından `AudioSyncTool-v2.0.0-win64.zip` dosyasını indirin, çıkartın ve çalıştırın. Python kurulumu gerekmez!
>
> **⬇️ Windows users**: Download `AudioSyncTool-v2.0.0-win64.zip` from the [Releases](https://github.com/blast1see/AudioSyncTool/releases) page, extract and run. No Python installation needed!

---

## 🇹🇷 Türkçe

### 📖 Hakkında

Audio Sync Tool, iki ses dosyası arasındaki gecikmeyi otomatik olarak tespit eden ve senkronize eden profesyonel bir araçtır. Film/dizi post-prodüksiyonunda, dublaj çalışmalarında ve ses mühendisliğinde kullanılmak üzere tasarlanmıştır.

### ✨ Özellikler

- **🔍 Sağlam Gecikme Tespiti**: İki aşamalı analiz (kaba + ince) ile milisaniye hassasiyetinde gecikme tespiti
- **🔄 Çoklu Senkronizasyon Modları**: 6 farklı FFmpeg filtre modu
  - `adelay + amix` — Varsayılan, en güvenilir yöntem
  - `aresample` — Örnekleme oranı tabanlı senkronizasyon
  - `atempo` — Tempo tabanlı ince ayar
  - `rubberband` — Yüksek kaliteli zaman uzatma (librubberband)
  - `apad + atrim` — Sessizlik ekleme/kırpma tabanlı
  - `asyncts` — Eski FFmpeg otomatik senkronizasyon
- **🎬 FPS Dönüşümü**: 23.976, 24, 25 FPS arası dönüşüm desteği
- **🔊 Dolby Encoding**: AC3/EAC3 çıktı desteği (FFmpeg veya DEE ile)
- **📏 Bit Derinliği Koruma**: 16-bit, 24-bit, 32-bit float orijinal kalite korunur
- **📦 RF64 Desteği**: 4 GB üzeri WAV dosyaları için otomatik RF64 formatı
- **🌍 Çok Dilli Arayüz**: Türkçe ve İngilizce dil desteği
- **🎯 Drift Tespiti**: Zaman içinde oluşan kayma analizi
- **📊 Detaylı Log**: İşlem adımlarının gerçek zamanlı takibi

### 🖥️ Ekran Görüntüsü

```
┌──────────────────────────────────────────┐
│  AUDIO SYNC                         🌐  │
│  Sağlam gecikme tespiti & senkronizasyon │
│──────────────────────────────────────────│
│  ● KAYNAK SES (referans)                 │
│    film_audio_original.wav               │
│           [DOSYA SEÇ]                    │
│──────────────────────────────────────────│
│  ● SENKRONİZE EDİLECEK SES              │
│    dubbed_audio_v2.wav                   │
│           [DOSYA SEÇ]                    │
│──────────────────────────────────────────│
│  TESPİT AYARLARI                         │
│  İlk farklı kısmı atla: [120] sn        │
│  Tarama penceresi sayısı: [12]           │
│──────────────────────────────────────────│
│  SENKRONİZASYON MODU                     │
│  MOD: [adelay + amix (Varsayılan)]       │
│──────────────────────────────────────────│
│  ⚡ SENKRONİZASYONU BAŞLAT               │
└──────────────────────────────────────────┘
```

### 📋 Sistem Gereksinimleri

| Gereksinim | Minimum | Önerilen |
|-----------|---------|----------|
| **İşletim Sistemi** | Windows 10 / macOS 10.15 / Ubuntu 20.04 | Windows 11 / macOS 13+ |
| **Python** | 3.10 | 3.11+ |
| **RAM** | 4 GB | 8 GB+ |
| **FFmpeg** | 4.0+ | 6.0+ |
| **Disk** | 500 MB boş alan | 2 GB+ (büyük dosyalar için) |

### 🚀 Kurulum

#### Yöntem 1: Kaynak Koddan

```bash
# Depoyu klonlayın
git clone https://github.com/blast1see/AudioSyncTool.git
cd audio-sync-tool

# Bağımlılıkları yükleyin
pip install -r requirements.txt

# Uygulamayı çalıştırın
python -m audio_sync
# veya
python audio_sync.py
```

#### Yöntem 2: EXE Dosyası (Windows)

1. [Releases](https://github.com/blast1see/AudioSyncTool/releases) sayfasından `AudioSyncTool-v2.0.0-win64.zip` dosyasını indirin
2. FFmpeg'in sisteminizde kurulu olduğundan emin olun:
   ```bash
   winget install ffmpeg
   ```
3. `AudioSyncTool.exe` dosyasını çalıştırın

#### FFmpeg Kurulumu

```bash
# Windows
winget install ffmpeg

# macOS
brew install ffmpeg

# Linux (Ubuntu/Debian)
sudo apt install ffmpeg
```

#### Dolby Encoding (DEE / deew)

Dolby ses kodlaması (Dolby Audio Encoding) yapmak istiyorsanız, FFmpeg'e ek olarak **deew** kullanabilirsiniz. `deew`, Dolby Encoding Engine (DEE) için açık kaynaklı bir Python sarmalayıcısıdır.
- **deew Projesi:** [https://github.com/pcroland/deew](https://github.com/pcroland/deew)

Kurulum ve kullanım detayları için ilgili depoyu inceleyebilirsiniz.

### 📖 Kullanım Kılavuzu

1. **Kaynak Ses Seçimi**: "DOSYA SEÇ" butonuyla referans ses dosyasını seçin
2. **Senkronize Edilecek Ses**: İkinci dosyayı seçin
3. **Ayarları Yapılandırın**:
   - İlk farklı kısmı atlama süresi (varsayılan: 120 sn)
   - Tarama penceresi sayısı (varsayılan: 12)
   - Senkronizasyon modu seçimi
4. **İsteğe Bağlı**: FPS dönüşümü veya Dolby encoding etkinleştirin
5. **Başlat**: "SENKRONİZASYONU BAŞLAT" butonuna tıklayın
6. **Çıktı**: Kaydetmek istediğiniz konumu seçin

### 🔧 Desteklenen Formatlar

**Giriş**: WAV, MP3, FLAC, AAC, OGG, M4A, AC3, EAC3, DTS, MKA, OPUS, WMA

**Çıkış**: WAV (PCM 16/24/32-bit), AC3 (Dolby Digital), EAC3 (Dolby Digital Plus)

### 🔄 Senkronizasyon Modları

| Mod | Açıklama | Kullanım Durumu |
|-----|----------|-----------------|
| **adelay + amix** | Gecikme uygulama ve karıştırma | Genel kullanım (varsayılan) |
| **aresample** | Örnekleme oranı tabanlı | Örnekleme uyumsuzluğu durumunda |
| **atempo** | Tempo tabanlı ince ayar | Küçük hız farkları için |
| **rubberband** | Yüksek kaliteli zaman uzatma | Profesyonel kalite gerektiğinde |
| **apad + atrim** | Sessizlik ekleme/kırpma | Basit gecikme düzeltmesi |
| **asyncts** | Otomatik senkronizasyon (eski) | Eski FFmpeg uyumluluğu |

### 🏗️ EXE Derleme

```bash
pip install pyinstaller
python setup.py
```

Çıktı: `dist/AudioSyncTool.exe`

---

## 🇬🇧 English

### 📖 About

Audio Sync Tool is a professional tool that automatically detects and synchronizes the delay between two audio files. It is designed for use in film/TV post-production, dubbing work, and audio engineering.

### ✨ Features

- **🔍 Robust Delay Detection**: Two-stage analysis (coarse + fine) with millisecond precision
- **🔄 Multiple Sync Modes**: 6 different FFmpeg filter modes
  - `adelay + amix` — Default, most reliable method
  - `aresample` — Sample rate based synchronization
  - `atempo` — Tempo based fine-tuning
  - `rubberband` — High quality time stretching (librubberband)
  - `apad + atrim` — Silence padding/trimming based
  - `asyncts` — Legacy FFmpeg automatic sync
- **🎬 FPS Conversion**: Support for 23.976, 24, 25 FPS conversions
- **🔊 Dolby Encoding**: AC3/EAC3 output support (via FFmpeg or DEE)
- **📏 Bit Depth Preservation**: Original quality maintained (16-bit, 24-bit, 32-bit float)
- **📦 RF64 Support**: Automatic RF64 format for WAV files over 4 GB
- **🌍 Multi-language UI**: Turkish and English language support
- **🎯 Drift Detection**: Time drift analysis over duration
- **📊 Detailed Logging**: Real-time tracking of processing steps

### 🖥️ Screenshot

```
┌──────────────────────────────────────────┐
│  AUDIO SYNC                         🌐  │
│  Robust delay detection & sync           │
│──────────────────────────────────────────│
│  ● SOURCE AUDIO (reference)              │
│    film_audio_original.wav               │
│           [SELECT FILE]                  │
│──────────────────────────────────────────│
│  ● AUDIO TO SYNCHRONIZE                  │
│    dubbed_audio_v2.wav                   │
│           [SELECT FILE]                  │
│──────────────────────────────────────────│
│  DETECTION SETTINGS                      │
│  Skip intro section: [120] sec           │
│  Scan window count: [12]                 │
│──────────────────────────────────────────│
│  SYNCHRONIZATION MODE                    │
│  MODE: [adelay + amix (Default)]         │
│──────────────────────────────────────────│
│  ⚡ START SYNCHRONIZATION                │
└──────────────────────────────────────────┘
```

### 📋 System Requirements

| Requirement | Minimum | Recommended |
|------------|---------|-------------|
| **OS** | Windows 10 / macOS 10.15 / Ubuntu 20.04 | Windows 11 / macOS 13+ |
| **Python** | 3.10 | 3.11+ |
| **RAM** | 4 GB | 8 GB+ |
| **FFmpeg** | 4.0+ | 6.0+ |
| **Disk** | 500 MB free | 2 GB+ (for large files) |

### 🚀 Installation

#### Method 1: From Source

```bash
# Clone the repository
git clone https://github.com/blast1see/AudioSyncTool.git
cd audio-sync-tool

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m audio_sync
# or
python audio_sync.py
```

#### Method 2: EXE File (Windows)

1. Download `AudioSyncTool-v2.0.0-win64.zip` from the [Releases](https://github.com/blast1see/AudioSyncTool/releases) page
2. Make sure FFmpeg is installed on your system:
   ```bash
   winget install ffmpeg
   ```
3. Run `AudioSyncTool.exe`

#### FFmpeg Installation

```bash
# Windows
winget install ffmpeg

# macOS
brew install ffmpeg

# Linux (Ubuntu/Debian)
sudo apt install ffmpeg
```
#### Dolby Encoding (DEE / deew)

If you want to perform Dolby Audio Encoding, you can use **deew** in addition to FFmpeg. `deew` is an open-source Python wrapper for the Dolby Encoding Engine (DEE).
- **deew Project:** [https://github.com/pcroland/deew](https://github.com/pcroland/deew)

Please visit the official repository for more details on installation and usage.

### 📖 Usage Guide

1. **Select Source Audio**: Click "SELECT FILE" to choose the reference audio file
2. **Select Audio to Sync**: Choose the second file
3. **Configure Settings**:
   - Skip intro duration (default: 120 sec)
   - Scan window count (default: 12)
   - Synchronization mode selection
4. **Optional**: Enable FPS conversion or Dolby encoding
5. **Start**: Click "START SYNCHRONIZATION"
6. **Output**: Choose where to save the output

### 🔧 Supported Formats

**Input**: WAV, MP3, FLAC, AAC, OGG, M4A, AC3, EAC3, DTS, MKA, OPUS, WMA

**Output**: WAV (PCM 16/24/32-bit), AC3 (Dolby Digital), EAC3 (Dolby Digital Plus)

### 🔄 Synchronization Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **adelay + amix** | Delay application and mixing | General use (default) |
| **aresample** | Sample rate based | Sample rate mismatch |
| **atempo** | Tempo based fine-tuning | Small speed differences |
| **rubberband** | High quality time stretching | Professional quality needed |
| **apad + atrim** | Silence padding/trimming | Simple delay correction |
| **asyncts** | Automatic sync (legacy) | Legacy FFmpeg compatibility |

### 🏗️ Building EXE

```bash
pip install pyinstaller
python setup.py
```

Output: `dist/AudioSyncTool.exe`

---

## 📁 Project Structure / Proje Yapısı

```
audio-sync-tool/
├── audio_sync/                 # Ana paket / Main package
│   ├── __init__.py
│   ├── __main__.py             # Giriş noktası / Entry point
│   ├── config.py               # Yapılandırma / Configuration
│   ├── i18n.py                 # Çok dilli destek / Internationalization
│   ├── utils.py                # Yardımcı fonksiyonlar / Utilities
│   ├── core/                   # İş mantığı / Business logic
│   │   ├── __init__.py
│   │   ├── analyzer.py         # Ses analizi / Audio analysis
│   │   ├── ffmpeg_wrapper.py   # FFmpeg arayüzü / FFmpeg interface
│   │   ├── deew_encoder.py     # Dolby encoding
│   │   └── models.py           # Veri modelleri / Data models
│   └── ui/                     # Kullanıcı arayüzü / User interface
│       ├── __init__.py
│       ├── app.py              # Ana pencere / Main window
│       └── drop_zone.py        # Dosya seçim widget'ı / File picker widget
├── tools/                      # Harici araçlar / External tools
├── audio_sync.py               # Geriye uyumluluk / Backward compatibility
├── audio_sync.ico              # Uygulama ikonu / Application icon
├── setup.py                    # EXE derleme / EXE build script
├── requirements.txt            # Bağımlılıklar / Dependencies
├── .gitignore
└── README.md
```

## 📄 License / Lisans

MIT License — Detaylar için [LICENSE](LICENSE) dosyasına bakın.

## 🤝 Contributing / Katkıda Bulunma

1. Fork yapın / Fork the repository
2. Feature branch oluşturun / Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Değişikliklerinizi commit edin / Commit your changes (`git commit -m 'Add amazing feature'`)
4. Branch'i push edin / Push to the branch (`git push origin feature/amazing-feature`)
5. Pull Request açın / Open a Pull Request

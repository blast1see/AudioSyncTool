<div align="center">

# Audio Sync Tool

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)](https://github.com/blast1see/AudioSyncTool)
[![Release](https://img.shields.io/badge/Release-v2.2.0-orange?style=flat-square)](https://github.com/blast1see/AudioSyncTool/releases)

**A robust audio delay detection and synchronization tool with a modern dark-themed GUI.**

[English](#english) | [Turkce](#turkce)

</div>

---

<!-- ============================================================ -->
<!-- ENGLISH                                                       -->
<!-- ============================================================ -->

<a id="english"></a>

## English

### About

**Audio Sync Tool** is a robust audio delay detection and synchronization tool with a modern dark-themed GUI. It analyzes two audio files, detects the time offset between them using cross-correlation, and produces a perfectly synchronized output. Whether you're dealing with out-of-sync dubs, misaligned audio tracks, or FPS-converted content, Audio Sync Tool handles it all with precision.

### Screenshots

![Audio Sync Tool - English UI](https://github.com/user-attachments/assets/a1c300d1-c5e5-44ff-b86f-73d17aa0bd23)

### Key Features

- **Cross-correlation based delay detection** — robust & accurate offset calculation
- **6 synchronization modes** — adelay+amix, aresample, atempo, rubberband, apad+atrim, asyncts
- **MKV/MP4 container support** — auto-detect and extract audio streams
- **Drag & drop file support** — seamless file loading with tkinterdnd2
- **Dolby Digital (AC3) and Dolby Digital Plus (EAC3) encoding** — via FFmpeg or [deew](https://github.com/pcroland/deew) / DEE
- **AAC encoding** — via FFmpeg or [qaac](https://github.com/nu774/qaac) (Apple AAC)
- **FLAC & Opus encoding** — via FFmpeg
- **FPS conversion** — 23.976 <-> 25 <-> 29.97 etc.
- **Bilingual UI** — English / Turkish
- **Dark-themed modern interface** — easy on the eyes
- **Preserves original audio quality** — bit depth, sample rate, channels
- **Tool Paths** — optional custom paths for ffmpeg, ffprobe, qaac, deew (falls back to system PATH)

### System Requirements

| Requirement | Details |
|---|---|
| **Python** | 3.10 or higher |
| **FFmpeg** | Required — must be in system PATH or set via Tool Paths |
| **deew + DEE** | Optional — for Dolby Digital / Dolby Digital Plus encoding via DEE |
| **qaac** | Optional — for Apple AAC encoding |

### Installation

#### Option 1: Pre-built Windows Executable

Download the latest pre-built `.exe` from the [Releases](https://github.com/blast1see/AudioSyncTool/releases) page. No Python installation required.

#### Option 2: Run from Source

```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

#### Optional: Drag & Drop Support

```bash
pip install tkinterdnd2
```

> **Note:** `tkinterdnd2` enables drag & drop functionality in the GUI. The application works without it, but file selection will be limited to the file browser dialog.

### Usage Guide

1. **Select Source Audio** — Click "Browse" or drag & drop the audio file that needs to be synchronized (the one with the delay).
2. **Select Sync Target** — Click "Browse" or drag & drop the reference audio file (the correctly timed one).
3. **Configure Settings:**
   - Choose the synchronization mode
   - Set output format and encoding options
   - Optionally enable Dolby encoding or FPS conversion
4. **Start Sync** — Click the "Start Sync" button. The tool will analyze the delay and produce the synchronized output.

### Supported Formats

#### Audio Formats

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

#### Container Formats (audio extraction)

| Format | Extension |
|---|---|
| Matroska Video | `.mkv` |
| MPEG-4 Video | `.mp4` |
| MPEG-4 Video | `.m4v` |
| WebM | `.webm` |
| MPEG Transport Stream | `.ts` |
| MPEG Transport Stream | `.mts` |

### Synchronization Modes

| Mode | Description |
|---|---|
| **adelay + amix** | Applies a delay filter and mixes audio streams. Best general-purpose mode. |
| **aresample** | Resamples audio to adjust timing. Good for minor drift corrections. |
| **atempo** | Changes audio tempo without altering pitch. Useful for speed-based sync. |
| **rubberband** | High-quality time-stretching using the Rubber Band library. Best for quality-sensitive work. |
| **apad + atrim** | Pads and trims audio to match target duration. Simple and effective. |
| **asyncts** | Asynchronous timestamp correction. Good for streams with variable timing. |

### Dolby Encoding (DEE / deew)

Audio Sync Tool integrates with **[deew](https://github.com/pcroland/deew)** to provide Dolby Digital (AC3) and Dolby Digital Plus (EAC3) encoding capabilities.

#### Requirements

- **[deew](https://github.com/pcroland/deew)** — A Dolby Encoding Engine wrapper (install via `pip install deew`)
- **DEE (Dolby Encoding Engine)** — The proprietary Dolby encoder binary (required by deew)

#### How it works

1. Audio Sync Tool first synchronizes the audio using FFmpeg
2. The synchronized output is then passed to deew for Dolby encoding
3. The final output is a properly encoded AC3 or EAC3 file

> **Important:** DEE (Dolby Encoding Engine) is a proprietary tool required by deew. Please refer to the [deew documentation](https://github.com/pcroland/deew) for setup instructions.

### FPS Conversion

Audio Sync Tool can compensate for frame rate differences between video sources. When audio is extracted from a video with a different frame rate than the target, the tool adjusts the audio duration accordingly.

Common conversions:
- 23.976 fps <-> 25 fps (PAL <-> NTSC Film)
- 23.976 fps <-> 29.97 fps
- 25 fps <-> 29.97 fps

### Building EXE

To build a standalone Windows executable:

```bash
python setup.py
```

This uses PyInstaller to create a single `.exe` file in the `dist/` directory.

### Project Structure

```
AudioSyncTool/
├── audio_sync.py            # Entry point
├── setup.py                 # PyInstaller build script
├── create_icon.py           # Icon generator
├── requirements.txt         # Python dependencies
├── LICENSE                  # MIT License
├── README.md                # Documentation (EN + TR)
├── CHANGELOG.md             # Version history
├── RELEASE_NOTES.md         # Release notes
├── audio_sync/
│   ├── __init__.py          # Package init & version
│   ├── __main__.py          # Module entry point
│   ├── config.py            # Configuration management
│   ├── i18n.py              # Internationalization (EN/TR)
│   ├── utils.py             # Utility functions
│   ├── core/
│   │   ├── __init__.py
│   │   ├── analyzer.py      # Audio analysis & cross-correlation
│   │   ├── encoder.py       # Unified encoding interface
│   │   ├── deew_encoder.py  # Dolby encoding integration
│   │   ├── ffmpeg_wrapper.py# FFmpeg command builder
│   │   └── models.py        # Data models
│   └── ui/
│       ├── __init__.py
│       ├── app.py           # Main application window
│       ├── drop_zone.py     # Drag & drop widget
│       └── stream_dialog.py # Audio stream selection dialog
```

### Dependencies

#### Required

| Package | Purpose |
|---|---|
| **numpy** | Numerical operations for audio analysis |
| **scipy** | Cross-correlation and signal processing |
| **FFmpeg** | Audio decoding, encoding, and processing (system binary) |

#### Optional

| Package | Purpose |
|---|---|
| **tkinterdnd2** | Drag & drop support in the GUI |
| **deew** | Dolby Digital / Dolby Digital Plus encoding via DEE |
| **qaac** | Apple AAC encoding |

### Contributing

Contributions are welcome! Here's how you can help:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

Please make sure your code follows the existing style and includes appropriate documentation.

### License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

### Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed list of changes in each version.

---

<!-- ============================================================ -->
<!-- TURKCE                                                        -->
<!-- ============================================================ -->

<a id="turkce"></a>

## Turkce

### Hakkinda

**Audio Sync Tool**, modern karanlik temali bir arayuze sahip, saglam bir ses gecikme tespiti ve senkronizasyon aracidir. Iki ses dosyasini analiz eder, aralarindaki zaman farkini capraz korelasyon kullanarak tespit eder ve mukemmel sekilde senkronize edilmis bir cikti uretir. Senkronize olmayan dublajlar, hizalanmamis ses parcalari veya FPS donusturulmus iceriklerle ugrasıyor olun, Audio Sync Tool hepsini hassasiyetle halleder.

### Ekran Goruntusu

![Audio Sync Tool - Turkce Arayuz](https://github.com/user-attachments/assets/c2551a54-b1ae-4bb1-a7b4-7e632b21362d)

### Temel Ozellikler

- **Capraz korelasyon tabanli gecikme tespiti** — saglam ve dogru ofset hesaplama
- **6 senkronizasyon modu** — adelay+amix, aresample, atempo, rubberband, apad+atrim, asyncts
- **MKV/MP4 konteyner destegi** — otomatik algilama ve ses akisi cikarma
- **Surukle & birak dosya destegi** — tkinterdnd2 ile sorunsuz dosya yukleme
- **Dolby Digital (AC3) ve Dolby Digital Plus (EAC3) kodlama** — FFmpeg veya [deew](https://github.com/pcroland/deew) / DEE araciligiyla
- **AAC kodlama** — FFmpeg veya [qaac](https://github.com/nu774/qaac) (Apple AAC) araciligiyla
- **FLAC & Opus kodlama** — FFmpeg araciligiyla
- **FPS donusumu** — 23.976 <-> 25 <-> 29.97 vb.
- **Iki dilli arayuz** — Ingilizce / Turkce
- **Karanlik temali modern arayuz** — goz yormayan tasarim
- **Orijinal ses kalitesini korur** — bit derinligi, ornekleme hizi, kanal sayisi
- **Tool Paths** — ffmpeg, ffprobe, qaac, deew icin istege bagli ozel yollar (yoksa sistem PATH kullanilir)

### Sistem Gereksinimleri

| Gereksinim | Detaylar |
|---|---|
| **Python** | 3.10 veya uzeri |
| **FFmpeg** | Gerekli — sistem PATH'inde bulunmali veya Tool Paths ile ayarlanmali |
| **deew + DEE** | Istege bagli — DEE ile Dolby Digital / Dolby Digital Plus kodlama icin |
| **qaac** | Istege bagli — Apple AAC kodlama icin |

### Kurulum

#### Secenek 1: Hazir Windows Calistirilabilir Dosyasi

[Releases](https://github.com/blast1see/AudioSyncTool/releases) sayfasindan en son `.exe` dosyasini indirin. Python kurulumu gerekmez.

#### Secenek 2: Kaynak Koddan Calistirma

```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

#### Istege Bagli: Surukle & Birak Destegi

```bash
pip install tkinterdnd2
```

> **Not:** `tkinterdnd2`, arayuzde surukle & birak islevselligini etkinlestirir. Uygulama bu paket olmadan da calisir, ancak dosya secimi yalnizca dosya tarayici diyalogu ile sinirli kalir.

### Kullanim Kilavuzu

1. **Kaynak Sesi Secin** — "Gozat" dugmesine tiklayin veya senkronize edilmesi gereken ses dosyasini (gecikmeli olan) surukleyip birakin.
2. **Senkronizasyon Hedefini Secin** — "Gozat" dugmesine tiklayin veya referans ses dosyasini (dogru zamanlamali olan) surukleyip birakin.
3. **Ayarlari Yapilandirin:**
   - Senkronizasyon modunu secin
   - Cikti formatini ve kodlama seceneklerini ayarlayin
   - Istege bagli olarak Dolby kodlama veya FPS donusumunu etkinlestirin
4. **Senkronizasyonu Baslatin** — "Senkronizasyonu Baslat" dugmesine tiklayin. Arac gecikmeyi analiz edecek ve senkronize edilmis ciktiyi uretecektir.

### Desteklenen Formatlar

#### Ses Formatlari

| Format | Uzanti |
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

#### Konteyner Formatlari (ses cikarma)

| Format | Uzanti |
|---|---|
| Matroska Video | `.mkv` |
| MPEG-4 Video | `.mp4` |
| MPEG-4 Video | `.m4v` |
| WebM | `.webm` |
| MPEG Transport Stream | `.ts` |
| MPEG Transport Stream | `.mts` |

### Senkronizasyon Modlari

| Mod | Aciklama |
|---|---|
| **adelay + amix** | Gecikme filtresi uygular ve ses akislarini karistirir. En iyi genel amacli mod. |
| **aresample** | Zamanlamayi ayarlamak icin sesi yeniden ornekler. Kucuk kayma duzeltmeleri icin uygundur. |
| **atempo** | Perde degistirmeden ses temposunu degistirir. Hiz tabanli senkronizasyon icin kullanislidir. |
| **rubberband** | Rubber Band kutuphanesi ile yuksek kaliteli zaman uzatma. Kalite hassasiyeti gereken isler icin en iyisi. |
| **apad + atrim** | Hedef sureye uymasi icin sesi doldurur ve kirpar. Basit ve etkili. |
| **asyncts** | Asenkron zaman damgasi duzeltmesi. Degisken zamanlama iceren akislar icin uygundur. |

### Dolby Kodlama (DEE / deew)

Audio Sync Tool, Dolby Digital (AC3) ve Dolby Digital Plus (EAC3) kodlama yetenekleri saglamak icin **[deew](https://github.com/pcroland/deew)** ile entegre calisir.

#### Gereksinimler

- **[deew](https://github.com/pcroland/deew)** — Dolby Encoding Engine sarmalayicisi (`pip install deew` ile kurulabilir)
- **DEE (Dolby Encoding Engine)** — Tescilli Dolby kodlayici ikili dosyasi (deew tarafindan gereklidir)

#### Nasil Calisir

1. Audio Sync Tool once FFmpeg kullanarak sesi senkronize eder
2. Senkronize edilmis cikti daha sonra Dolby kodlama icin deew'e aktarilir
3. Son cikti, duzgun sekilde kodlanmis bir AC3 veya EAC3 dosyasidir

> **Onemli:** DEE (Dolby Encoding Engine), deew tarafindan gerekli olan tescilli bir aractir. Kurulum talimatlari icin lutfen [deew dokumantasyonuna](https://github.com/pcroland/deew) basvurun.

### FPS Donusumu

Audio Sync Tool, video kaynaklari arasindaki kare hizi farkliliklarini telafi edebilir. Ses, hedeften farkli bir kare hizina sahip bir videodan cikarildiginda, arac ses suresini buna gore ayarlar.

Yaygin donusumler:
- 23.976 fps <-> 25 fps (PAL <-> NTSC Film)
- 23.976 fps <-> 29.97 fps
- 25 fps <-> 29.97 fps

### EXE Derleme

Bagimsiz bir Windows calistirilabilir dosyasi olusturmak icin:

```bash
python setup.py
```

Bu komut, PyInstaller kullanarak `dist/` dizininde tek bir `.exe` dosyasi olusturur.

### Proje Yapisi

```
AudioSyncTool/
├── audio_sync.py            # Giris noktasi
├── setup.py                 # PyInstaller derleme betigi
├── create_icon.py           # Ikon olusturucu
├── requirements.txt         # Python bagimliliklari
├── LICENSE                  # MIT Lisansi
├── README.md                # Dokumantasyon (EN + TR)
├── CHANGELOG.md             # Surum gecmisi
├── RELEASE_NOTES.md         # Surum notlari
├── audio_sync/
│   ├── __init__.py          # Paket baslatma & surum
│   ├── __main__.py          # Modul giris noktasi
│   ├── config.py            # Yapilandirma yonetimi
│   ├── i18n.py              # Uluslararasilastirma (EN/TR)
│   ├── utils.py             # Yardimci fonksiyonlar
│   ├── core/
│   │   ├── __init__.py
│   │   ├── analyzer.py      # Ses analizi & capraz korelasyon
│   │   ├── encoder.py       # Birlesmis kodlama arayuzu
│   │   ├── deew_encoder.py  # Dolby kodlama entegrasyonu
│   │   ├── ffmpeg_wrapper.py# FFmpeg komut olusturucu
│   │   └── models.py        # Veri modelleri
│   └── ui/
│       ├── __init__.py
│       ├── app.py           # Ana uygulama penceresi
│       ├── drop_zone.py     # Surukle & birak bileseni
│       └── stream_dialog.py # Ses akisi secim diyalogu
```

### Bagimliliklar

#### Gerekli

| Paket | Amac |
|---|---|
| **numpy** | Ses analizi icin sayisal islemler |
| **scipy** | Capraz korelasyon ve sinyal isleme |
| **FFmpeg** | Ses cozme, kodlama ve isleme (sistem ikili dosyasi) |

#### Istege Bagli

| Paket | Amac |
|---|---|
| **tkinterdnd2** | Arayuzde surukle & birak destegi |
| **deew** | DEE ile Dolby Digital / Dolby Digital Plus kodlama |
| **qaac** | Apple AAC kodlama |

### Katkida Bulunma

Katkilarinizi bekliyoruz! Iste nasil yardimci olabilirsiniz:

1. Depoyu **fork** edin
2. Bir ozellik dali **olusturun** (`git checkout -b feature/harika-ozellik`)
3. Degisikliklerinizi **commit** edin (`git commit -m 'Harika ozellik ekle'`)
4. Dali **push** edin (`git push origin feature/harika-ozellik`)
5. Bir **Pull Request** acin

Lutfen kodunuzun mevcut stile uygun oldugundan ve uygun dokumantasyon icerdiginden emin olun.

### Lisans

Bu proje **MIT Lisansi** altinda lisanslanmistir — detaylar icin [LICENSE](LICENSE) dosyasina bakin.

### Degisiklik Gunlugu

Her surumdeki degisikliklerin detayli listesi icin [CHANGELOG.md](CHANGELOG.md) dosyasina bakin.

---

<div align="center">

Made with love by [blast1see](https://github.com/blast1see)

</div>

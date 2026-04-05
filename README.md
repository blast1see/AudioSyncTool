<div align="center">

# Audio Sync Tool

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)](https://github.com/blast1see/AudioSyncTool)
[![Release](https://img.shields.io/badge/Release-v2.2.0-orange?style=flat-square)](https://github.com/blast1see/AudioSyncTool/releases)

**A robust audio delay detection and synchronization tool with a modern dark-themed GUI.**

[English](#english) | [Türkçe](#turkce)

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

<img width="802" height="1392" alt="2026-04-02 19_26_56-Audio Sync Tool" src="https://github.com/user-attachments/assets/89009109-7947-4d85-b0f7-8fa21c4a64f7" />

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
| DTS-HD | `.dtshd` |
| Dolby TrueHD | `.thd` |
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

## Türkçe

### Hakkında

**Audio Sync Tool**, modern karanlık temalı bir arayüze sahip, sağlam bir ses gecikme tespiti ve senkronizasyon aracıdır. İki ses dosyasını analiz eder, aralarındaki zaman farkını çapraz korelasyon kullanarak tespit eder ve mükemmel şekilde senkronize edilmiş bir çıktı üretir. Senkronize olmayan dublajlar, hizalanmamış ses parçaları veya FPS dönüştürülmüş içeriklerle uğraşıyor olun, Audio Sync Tool hepsini hassasiyetle halleder.

### Ekran Görüntüsü

<img width="802" height="1392" alt="2026-04-02 19_27_06-Audio Sync Tool-TR" src="https://github.com/user-attachments/assets/106d8021-baec-4f75-9e2a-2f46f347c6be" />

### Temel Özellikler

- **Çapraz korelasyon tabanlı gecikme tespiti** — sağlam ve doğru ofset hesaplama
- **6 senkronizasyon modu** — adelay+amix, aresample, atempo, rubberband, apad+atrim, asyncts
- **MKV/MP4 konteyner desteği** — otomatik algılama ve ses akışı çıkarma
- **Sürükle & bırak dosya desteği** — tkinterdnd2 ile sorunsuz dosya yükleme
- **Dolby Digital (AC3) ve Dolby Digital Plus (EAC3) kodlama** — FFmpeg veya [deew](https://github.com/pcroland/deew) / DEE aracılığıyla
- **AAC kodlama** — FFmpeg veya [qaac](https://github.com/nu774/qaac) (Apple AAC) aracılığıyla
- **FLAC & Opus kodlama** — FFmpeg aracılığıyla
- **FPS dönüşümü** — 23.976 <-> 25 <-> 29.97 vb.
- **İki dilli arayüz** — İngilizce / Türkçe
- **Karanlık temalı modern arayüz** — göz yormayan tasarım
- **Orijinal ses kalitesini korur** — bit derinliği, örnekleme hızı, kanal sayısı
- **Tool Paths** — ffmpeg, ffprobe, qaac, deew için isteğe bağlı özel yollar (yoksa sistem PATH'i kullanılır)

### Sistem Gereksinimleri

| Gereksinim | Detaylar |
|---|---|
| **Python** | 3.10 veya üzeri |
| **FFmpeg** | Gerekli — sistem PATH'inde bulunmalı veya Tool Paths ile ayarlanmalı |
| **deew + DEE** | İsteğe bağlı — DEE ile Dolby Digital / Dolby Digital Plus kodlama için |
| **qaac** | İsteğe bağlı — Apple AAC kodlama için |

### Kurulum

#### Seçenek 1: Hazır Windows Çalıştırılabilir Dosyası

[Releases](https://github.com/blast1see/AudioSyncTool/releases) sayfasından en son `.exe` dosyasını indirin. Python kurulumu gerekmez.

#### Seçenek 2: Kaynak Koddan Çalıştırma

```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

#### İsteğe Bağlı: Sürükle & Bırak Desteği

```bash
pip install tkinterdnd2
```

> **Not:** `tkinterdnd2`, arayüzde sürükle & bırak işlevselliğini etkinleştirir. Uygulama bu paket olmadan da çalışır, ancak dosya seçimi yalnızca dosya tarayıcı diyalogu ile sınırlı kalır.

### Kullanım Kılavuzu

1. **Kaynak Sesi Seçin** — "Gözat" düğmesine tıklayın veya senkronize edilmesi gereken ses dosyasını (gecikmeli olan) sürükleyip bırakın.
2. **Senkronizasyon Hedefini Seçin** — "Gözat" düğmesine tıklayın veya referans ses dosyasını (doğru zamanlamalı olan) sürükleyip bırakın.
3. **Ayarları Yapılandırın:**
   - Senkronizasyon modunu seçin
   - Çıktı formatını ve kodlama seçeneklerini ayarlayın
   - İsteğe bağlı olarak Dolby kodlama veya FPS dönüşümünü etkinleştirin
4. **Senkronizasyonu Başlatın** — "Senkronizasyonu Başlat" düğmesine tıklayın. Araç gecikmeyi analiz edecek ve senkronize edilmiş çıktıyı üretecektir.

### Desteklenen Formatlar

#### Ses Formatları

| Format | Uzantı |
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
| DTS-HD | `.dtshd` |
| Dolby TrueHD | `.thd` |
| Matroska Audio | `.mka` |
| Opus | `.opus` |
| Windows Media Audio | `.wma` |

#### Konteyner Formatları (ses çıkarma)

| Format | Uzantı |
|---|---|
| Matroska Video | `.mkv` |
| MPEG-4 Video | `.mp4` |
| MPEG-4 Video | `.m4v` |
| WebM | `.webm` |
| MPEG Transport Stream | `.ts` |
| MPEG Transport Stream | `.mts` |

### Senkronizasyon Modları

| Mod | Açıklama |
|---|---|
| **adelay + amix** | Gecikme filtresi uygular ve ses akışlarını karıştırır. En iyi genel amaçlı mod. |
| **aresample** | Zamanlamayı ayarlamak için sesi yeniden örnekler. Küçük kayma düzeltmeleri için uygundur. |
| **atempo** | Perde değiştirmeden ses temposunu değiştirir. Hız tabanlı senkronizasyon için kullanışlıdır. |
| **rubberband** | Rubber Band kütüphanesi ile yüksek kaliteli zaman uzatma. Kalite hassasiyeti gerektiren işler için en iyisi. |
| **apad + atrim** | Hedef süreye uyması için sesi doldurur ve kırpar. Basit ve etkili. |
| **asyncts** | Asenkron zaman damgası düzeltmesi. Değişken zamanlama içeren akışlar için uygundur. |

### Dolby Kodlama (DEE / deew)

Audio Sync Tool, Dolby Digital (AC3) ve Dolby Digital Plus (EAC3) kodlama yetenekleri sağlamak için **[deew](https://github.com/pcroland/deew)** ile entegre çalışır.

#### Gereksinimler

- **[deew](https://github.com/pcroland/deew)** — Dolby Encoding Engine sarmalayıcısı (`pip install deew` ile kurulabilir)
- **DEE (Dolby Encoding Engine)** — Tescilli Dolby kodlayıcı ikili dosyası (deew tarafından gereklidir)

#### Nasıl Çalışır

1. Audio Sync Tool önce FFmpeg kullanarak sesi senkronize eder
2. Senkronize edilmiş çıktı daha sonra Dolby kodlama için deew'e aktarılır
3. Son çıktı, düzgün şekilde kodlanmış bir AC3 veya EAC3 dosyasıdır

> **Önemli:** DEE (Dolby Encoding Engine), deew tarafından gerekli olan tescilli bir araçtır. Kurulum talimatları için lütfen [deew dokümantasyonuna](https://github.com/pcroland/deew) başvurun.

### FPS Dönüşümü

Audio Sync Tool, video kaynakları arasındaki kare hızı farklılıklarını telafi edebilir. Ses, hedeften farklı bir kare hızına sahip bir videodan çıkarıldığında, araç ses süresini buna göre ayarlar.

Yaygın dönüşümler:
- 23.976 fps <-> 25 fps (PAL <-> NTSC Film)
- 23.976 fps <-> 29.97 fps
- 25 fps <-> 29.97 fps

### EXE Derleme

Bağımsız bir Windows çalıştırılabilir dosyası oluşturmak için:

```bash
python setup.py
```

Bu komut, PyInstaller kullanarak `dist/` dizininde tek bir `.exe` dosyası oluşturur.

### Proje Yapısı

```
AudioSyncTool/
├── audio_sync.py            # Giriş noktası
├── setup.py                 # PyInstaller derleme betiği
├── create_icon.py           # İkon oluşturucu
├── requirements.txt         # Python bağımlılıkları
├── LICENSE                  # MIT Lisansı
├── README.md                # Dokümantasyon (EN + TR)
├── CHANGELOG.md             # Sürüm geçmişi
├── RELEASE_NOTES.md         # Sürüm notları
├── audio_sync/
│   ├── __init__.py          # Paket başlatma & sürüm
│   ├── __main__.py          # Modül giriş noktası
│   ├── config.py            # Yapılandırma yönetimi
│   ├── i18n.py              # Uluslararasılaştırma (EN/TR)
│   ├── utils.py             # Yardımcı fonksiyonlar
│   ├── core/
│   │   ├── __init__.py
│   │   ├── analyzer.py      # Ses analizi & çapraz korelasyon
│   │   ├── encoder.py       # Birleşik kodlama arayüzü
│   │   ├── deew_encoder.py  # Dolby kodlama entegrasyonu
│   │   ├── ffmpeg_wrapper.py# FFmpeg komut oluşturucu
│   │   └── models.py        # Veri modelleri
│   └── ui/
│       ├── __init__.py
│       ├── app.py           # Ana uygulama penceresi
│       ├── drop_zone.py     # Sürükle & bırak bileşeni
│       └── stream_dialog.py # Ses akışı seçim diyalogu
```

### Bağımlılıklar

#### Gerekli

| Paket | Amaç |
|---|---|
| **numpy** | Ses analizi için sayısal işlemler |
| **scipy** | Çapraz korelasyon ve sinyal işleme |
| **FFmpeg** | Ses çözme, kodlama ve işleme (sistem ikili dosyası) |

#### İsteğe Bağlı

| Paket | Amaç |
|---|---|
| **tkinterdnd2** | Arayüzde sürükle & bırak desteği |
| **deew** | DEE ile Dolby Digital / Dolby Digital Plus kodlama |
| **qaac** | Apple AAC kodlama |

### Katkıda Bulunma

Katkılarınızı bekliyoruz! İşte nasıl yardımcı olabilirsiniz:

1. Depoyu **fork** edin
2. Bir özellik dalı **oluşturun** (`git checkout -b feature/harika-ozellik`)
3. Değişikliklerinizi **commit** edin (`git commit -m 'Harika ozellik ekle'`)
4. Dalı **push** edin (`git push origin feature/harika-ozellik`)
5. Bir **Pull Request** açın

Lütfen kodunuzun mevcut stile uygun olduğundan ve uygun dokümantasyon içerdiğinden emin olun.

### Lisans

Bu proje **MIT Lisansı** altında lisanslanmıştır — detaylar için [LICENSE](LICENSE) dosyasına bakın.

### Değişiklik Günlüğü

Her sürümdeki değişikliklerin detaylı listesi için [CHANGELOG.md](CHANGELOG.md) dosyasına bakın.

---

<div align="center">

Made with love by [blast1see](https://github.com/blast1see)

</div>

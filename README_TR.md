<div align="center">

# 🎵 Audio Sync Tool

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Lisans: MIT](https://img.shields.io/badge/Lisans-MIT-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)](https://github.com/blast1see/AudioSyncTool)
[![Sürüm](https://img.shields.io/badge/S%C3%BCr%C3%BCm-v2.1.0-orange?style=flat-square)](https://github.com/blast1see/AudioSyncTool/releases)

**Modern karanlık temalı arayüze sahip, güçlü bir ses gecikme tespiti ve senkronizasyon aracı.**

[🌐 Dil Seçimi](README.md) · [🇬🇧 English](README_EN.md)

</div>

---

## 📖 Hakkında

**Audio Sync Tool**, modern karanlık temalı bir arayüze sahip, sağlam bir ses gecikme tespiti ve senkronizasyon aracıdır. İki ses dosyasını analiz eder, aralarındaki zaman farkını çapraz korelasyon kullanarak tespit eder ve mükemmel şekilde senkronize edilmiş bir çıktı üretir. Senkronize olmayan dublajlar, hizalanmamış ses parçaları veya FPS dönüştürülmüş içeriklerle uğraşıyor olun, Audio Sync Tool hepsini hassasiyetle halleder.

## 📸 Ekran Görüntüsü

![Audio Sync Tool - Türkçe Arayüz](https://github.com/user-attachments/assets/c2551a54-b1ae-4bb1-a7b4-7e632b21362d)

## ✨ Temel Özellikler

- **Çapraz korelasyon tabanlı gecikme tespiti** — sağlam ve doğru ofset hesaplama
- **6 senkronizasyon modu** — adelay+amix, aresample, atempo, rubberband, apad+atrim, asyncts
- **MKV/MP4 konteyner desteği** — otomatik algılama ve ses akışı çıkarma
- **Sürükle & bırak dosya desteği** — tkinterdnd2 ile sorunsuz dosya yükleme
- **Dolby Digital (AC3) ve Dolby Digital Plus (EAC3) kodlama** — [deew](https://github.com/pcroland/deew) / DEE aracılığıyla
- **FPS dönüşümü** — 23.976 ↔ 25 ↔ 29.97 vb.
- **İki dilli arayüz** — İngilizce / Türkçe
- **Karanlık temalı modern arayüz** — göz yormayan tasarım
- **Orijinal ses kalitesini korur** — bit derinliği, örnekleme hızı, kanal sayısı

## 💻 Sistem Gereksinimleri

| Gereksinim | Detaylar |
|---|---|
| **Python** | 3.10 veya üzeri |
| **FFmpeg** | Gerekli — sistem PATH'inde bulunmalıdır |
| **deew + DEE** | İsteğe bağlı — Dolby Digital / Dolby Digital Plus kodlama için |

## 📦 Kurulum

### Seçenek 1: Hazır Windows Çalıştırılabilir Dosyası

[Releases](https://github.com/blast1see/AudioSyncTool/releases) sayfasından en son `.exe` dosyasını indirin. Python kurulumu gerekmez.

### Seçenek 2: Kaynak Koddan Çalıştırma

```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

### İsteğe Bağlı: Sürükle & Bırak Desteği

```bash
pip install tkinterdnd2
```

> **Not:** `tkinterdnd2`, arayüzde sürükle & bırak işlevselliğini etkinleştirir. Uygulama bu paket olmadan da çalışır, ancak dosya seçimi yalnızca dosya tarayıcı diyaloğu ile sınırlı kalır.

## 📋 Kullanım Kılavuzu

1. **Kaynak Sesi Seçin** — "Gözat" düğmesine tıklayın veya senkronize edilmesi gereken ses dosyasını (gecikmeli olan) sürükleyip bırakın.
2. **Senkronizasyon Hedefini Seçin** — "Gözat" düğmesine tıklayın veya referans ses dosyasını (doğru zamanlamalı olan) sürükleyip bırakın.
3. **Ayarları Yapılandırın:**
   - Senkronizasyon modunu seçin
   - Çıktı formatını ve kodlama seçeneklerini ayarlayın
   - İsteğe bağlı olarak Dolby kodlama veya FPS dönüşümünü etkinleştirin
4. **Senkronizasyonu Başlatın** — "Senkronizasyonu Başlat" düğmesine tıklayın. Araç gecikmeyi analiz edecek ve senkronize edilmiş çıktıyı üretecektir.

## 🎵 Desteklenen Formatlar

### Ses Formatları

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
| Matroska Audio | `.mka` |
| Opus | `.opus` |
| Windows Media Audio | `.wma` |

### Konteyner Formatları (ses çıkarma)

| Format | Uzantı |
|---|---|
| Matroska Video | `.mkv` |
| MPEG-4 Video | `.mp4` |
| MPEG-4 Video | `.m4v` |
| WebM | `.webm` |
| MPEG Transport Stream | `.ts` |
| MPEG Transport Stream | `.mts` |

## 🔄 Senkronizasyon Modları

| Mod | Açıklama |
|---|---|
| **adelay + amix** | Gecikme filtresi uygular ve ses akışlarını karıştırır. En iyi genel amaçlı mod. |
| **aresample** | Zamanlamayı ayarlamak için sesi yeniden örnekler. Küçük kayma düzeltmeleri için uygundur. |
| **atempo** | Perde değiştirmeden ses temposunu değiştirir. Hız tabanlı senkronizasyon için kullanışlıdır. |
| **rubberband** | Rubber Band kütüphanesi ile yüksek kaliteli zaman uzatma. Kalite hassasiyeti gereken işler için en iyisi. |
| **apad + atrim** | Hedef süreye uyması için sesi doldurur ve kırpar. Basit ve etkili. |
| **asyncts** | Asenkron zaman damgası düzeltmesi. Değişken zamanlama içeren akışlar için uygundur. |

## 🔊 Dolby Kodlama (DEE / deew)

Audio Sync Tool, Dolby Digital (AC3) ve Dolby Digital Plus (EAC3) kodlama yetenekleri sağlamak için **[deew](https://github.com/pcroland/deew)** ile entegre çalışır.

### Gereksinimler

- **[deew](https://github.com/pcroland/deew)** — Dolby Encoding Engine sarmalayıcısı (`pip install deew` ile kurulabilir)
- **DEE (Dolby Encoding Engine)** — Tescilli Dolby kodlayıcı ikili dosyası (deew tarafından gereklidir)

### Nasıl Çalışır

1. Audio Sync Tool önce FFmpeg kullanarak sesi senkronize eder
2. Senkronize edilmiş çıktı daha sonra Dolby kodlama için deew'e aktarılır
3. Son çıktı, düzgün şekilde kodlanmış bir AC3 veya EAC3 dosyasıdır

> **Önemli:** DEE (Dolby Encoding Engine), deew tarafından gerekli olan tescilli bir araçtır. Kurulum talimatları için lütfen [deew dokümantasyonuna](https://github.com/pcroland/deew) başvurun.

## 🎬 FPS Dönüşümü

Audio Sync Tool, video kaynakları arasındaki kare hızı farklılıklarını telafi edebilir. Ses, hedeften farklı bir kare hızına sahip bir videodan çıkarıldığında, araç ses süresini buna göre ayarlar.

Yaygın dönüşümler:
- 23.976 fps ↔ 25 fps (PAL ↔ NTSC Film)
- 23.976 fps ↔ 29.97 fps
- 25 fps ↔ 29.97 fps

## 🏗️ EXE Derleme

Bağımsız bir Windows çalıştırılabilir dosyası oluşturmak için:

```bash
python setup.py
```

Bu komut, PyInstaller kullanarak `dist/` dizininde tek bir `.exe` dosyası oluşturur.

## 📁 Proje Yapısı

```
AudioSyncTool/
├── audio_sync.py            # Giriş noktası
├── setup.py                 # PyInstaller derleme betiği
├── create_icon.py           # İkon oluşturucu
├── requirements.txt         # Python bağımlılıkları
├── LICENSE                  # MIT Lisansı
├── README.md                # Dil seçici
├── README_EN.md             # İngilizce dokümantasyon
├── README_TR.md             # Türkçe dokümantasyon
├── audio_sync/
│   ├── __init__.py          # Paket başlatma & sürüm
│   ├── __main__.py          # Modül giriş noktası
│   ├── config.py            # Yapılandırma yönetimi
│   ├── i18n.py              # Uluslararasılaştırma (EN/TR)
│   ├── utils.py             # Yardımcı fonksiyonlar
│   ├── core/
│   │   ├── __init__.py
│   │   ├── analyzer.py      # Ses analizi & çapraz korelasyon
│   │   ├── deew_encoder.py  # Dolby kodlama entegrasyonu
│   │   ├── ffmpeg_wrapper.py# FFmpeg komut oluşturucu
│   │   └── models.py        # Veri modelleri
│   └── ui/
│       ├── __init__.py
│       ├── app.py           # Ana uygulama penceresi
│       ├── drop_zone.py     # Sürükle & bırak bileşeni
│       └── stream_dialog.py # Ses akışı seçim diyaloğu
```

## 📚 Bağımlılıklar

### Gerekli

| Paket | Amaç |
|---|---|
| **numpy** | Ses analizi için sayısal işlemler |
| **scipy** | Çapraz korelasyon ve sinyal işleme |
| **FFmpeg** | Ses çözme, kodlama ve işleme (sistem ikili dosyası) |

### İsteğe Bağlı

| Paket | Amaç |
|---|---|
| **tkinterdnd2** | Arayüzde sürükle & bırak desteği |
| **deew** | Dolby Digital / Dolby Digital Plus kodlama |

## 🤝 Katkıda Bulunma

Katkılarınızı bekliyoruz! İşte nasıl yardımcı olabilirsiniz:

1. Depoyu **fork** edin
2. Bir özellik dalı **oluşturun** (`git checkout -b feature/harika-ozellik`)
3. Değişikliklerinizi **commit** edin (`git commit -m 'Harika özellik ekle'`)
4. Dalı **push** edin (`git push origin feature/harika-ozellik`)
5. Bir **Pull Request** açın

Lütfen kodunuzun mevcut stile uygun olduğundan ve uygun dokümantasyon içerdiğinden emin olun.

## 📄 Lisans

Bu proje **MIT Lisansı** altında lisanslanmıştır — detaylar için [LICENSE](LICENSE) dosyasına bakın.

## 📋 Değişiklik Günlüğü

Her sürümdeki değişikliklerin detaylı listesi için [CHANGELOG.md](CHANGELOG.md) dosyasına bakın.

---

<div align="center">

❤️ ile [blast1see](https://github.com/blast1see) tarafından yapılmıştır

</div>

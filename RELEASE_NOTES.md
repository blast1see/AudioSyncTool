# Audio Sync Tool v2.3.0

## What's New / Yenilikler

### Security
- **External tools are no longer resolved from the working directory.** On Windows `shutil.which()` searches the current directory before PATH, so launching the app from a folder that contained a planted `ffmpeg.exe` or `ffprobe.exe` executed that binary instead of the installed one. Tool lookup now only accepts absolute PATH entries, and relative PATH entries are skipped too.
- Deew runtime probes write to a per-user directory instead of the installation tree, which is read-only for system-wide installs and ephemeral inside a PyInstaller bundle.
- Media paths are made absolute before reaching FFmpeg, so a relative path such as `sample:track.wav` can no longer be read as an FFmpeg protocol specifier.

### Performance
- Tool locations and the FFmpeg/FFprobe availability probe are cached, removing four process spawns per synchronization run
- Analysis reads the decoded PCM once instead of twice; the measured peak stays bit-identical
- qaac encoding scales its timeout with the input size instead of always aborting at 600 seconds

### Interface
- The window no longer freezes for up to 15 seconds at startup or on the first run — the Deew badge and the Start button's tool checks moved to worker threads
- The progress bar now reports the current stage and completion percentage
- The mouse wheel scrolls the log box when the pointer is over it, instead of always scrolling the page
- Background probes that finish after the window closes no longer call into a destroyed Tcl interpreter

---

## Türkçe

### Güvenlik
- **Dış araçlar artık çalışma dizininden çözülmüyor.** Windows'ta `shutil.which()` PATH'ten önce bulunduğu dizine bakıyor; bu yüzden içinde sahte bir `ffmpeg.exe` veya `ffprobe.exe` bulunan bir klasörden başlatılan uygulama kurulu olan yerine o dosyayı çalıştırıyordu. Araç araması artık yalnızca mutlak PATH girdilerini kabul ediyor, göreli PATH girdileri de atlanıyor.
- Deew çalışma zamanı denetimleri kurulum dizini yerine kullanıcıya özel bir dizine yazıyor; kurulum dizini sistem geneli kurulumlarda salt okunur, PyInstaller paketinde ise geçiciydi.
- Medya yolları FFmpeg'e ulaşmadan önce mutlak hale getiriliyor; böylece `sample:track.wav` gibi göreli bir yol FFmpeg protokol öneki olarak okunamıyor.

### Performans
- Araç konumları ve FFmpeg/FFprobe erişilebilirlik denetimi önbelleğe alınıyor; her senkronizasyon çalıştırmasından dört süreç başlatma kalkıyor
- Analiz, decode edilmiş PCM'i iki kez yerine bir kez okuyor; ölçülen tepe değeri bit düzeyinde aynı kalıyor
- qaac kodlaması her zaman 600 saniyede iptal etmek yerine zaman aşımını girdi boyutuna göre ölçekliyor

### Arayüz
- Pencere artık açılışta veya ilk çalıştırmada 15 saniyeye kadar donmuyor — Deew rozeti ve Başlat düğmesinin araç denetimleri worker thread'lere taşındı
- İlerleme çubuğu artık mevcut aşamayı ve tamamlanma yüzdesini gösteriyor
- Fare tekerleği, imleç log kutusunun üzerindeyken sayfayı değil log kutusunu kaydırıyor
- Pencere kapandıktan sonra biten arka plan denetimleri artık yok edilmiş Tcl yorumlayıcısına çağrı yapmıyor

---

## Installation / Kurulum

**Windows**: Download `AudioSyncTool-v2.3.0-win64.zip` from the assets below.

**From source**:
```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
python -m pip install .
python -m audio_sync
```

**Full changelog**: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)

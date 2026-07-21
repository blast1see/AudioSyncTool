# Audio Sync Tool v2.2.6

## What's New / Yenilikler

### Reliability and data safety
- Outputs are now written to a temporary file and committed atomically only after validation
- Existing outputs and input files remain protected when a job fails or is cancelled
- Failed final encodes report an error and preserve a collision-free `*.sync-fallback.wav`
- FFmpeg, FFprobe, qaac, and Deew failures can no longer be reported as successful completion

### Synchronization correctness
- The synchronized track keeps its original sample rate unless 48 kHz is explicitly forced
- Constant offsets now use exact delay/trim behavior in both directions
- The compatibility `atempo` mode no longer distorts the first ten seconds for tiny offsets
- FFprobe metadata and configured FFmpeg tool paths are validated strictly

### Engineering quality
- Added the testable `SyncPipeline` orchestration layer
- Added unit, synthetic-audio, real FFmpeg, GUI smoke, coverage, and Windows build checks
- Added Python 3.10, 3.12, and 3.14 CI coverage on Linux, Windows, and macOS
- Added weekly Dependabot updates and project metadata in `pyproject.toml`

---

## Türkçe

### Güvenilirlik ve veri güvenliği
- Çıktılar artık önce geçici dosyaya yazılıyor ve yalnızca doğrulamadan sonra atomik olarak tamamlanıyor
- Hata veya iptal durumunda mevcut çıktılar ve girdi dosyaları korunuyor
- Son kodlama başarısız olursa hata bildiriliyor ve çakışmayan `*.sync-fallback.wav` dosyası saklanıyor
- FFmpeg, FFprobe, qaac ve Deew hataları artık başarılı işlem olarak gösterilemiyor

### Senkronizasyon doğruluğu
- 48 kHz açıkça zorlanmadıkça senkronize edilen sesin örnekleme oranı korunuyor
- Sabit ofsetler iki yönde de kesin gecikme/kırpma olarak uygulanıyor
- Geriye uyumlu `atempo` modu küçük ofsetlerde ilk on saniyeyi artık bozmuyor
- FFprobe metadata bilgileri ile yapılandırılmış FFmpeg araç yolları sıkı biçimde doğrulanıyor

### Mühendislik kalitesi
- Test edilebilir `SyncPipeline` iş akışı katmanı eklendi
- Birim, sentetik ses, gerçek FFmpeg, GUI smoke, coverage ve Windows build kontrolleri eklendi
- Linux, Windows ve macOS üzerinde Python 3.10, 3.12 ve 3.14 CI matrisi eklendi
- Haftalık Dependabot güncellemeleri ve `pyproject.toml` proje metadata bilgileri eklendi

---

## Installation / Kurulum

**Windows**: Download `AudioSyncTool-v2.2.6-win64.zip` from the assets below.

**From source**:
```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
python -m pip install .
python -m audio_sync
```

**Full changelog**: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)

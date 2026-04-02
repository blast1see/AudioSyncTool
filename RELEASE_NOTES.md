# Audio Sync Tool v2.2.0

## What's New / Yenilikler

### Encoding Engine Overhaul
- **Unified encoder module** — New `encoder.py` abstraction for all encoding operations
- **FFmpeg-native Dolby encoding** — AC3/EAC3 encoding directly via FFmpeg (no deew/DEE required)
- **AAC encoding via qaac** — Apple AAC (TVBR/CVBR/ABR/CBR) support
- **FLAC encoding** — Lossless FLAC with configurable compression (0-12)
- **Opus encoding** — Opus with configurable bitrate

### Tool Paths (Optional)
- Configure custom paths for ffmpeg, ffprobe, qaac, and deew
- All tools default to system PATH — Tool Paths is entirely optional
- Fixed: `dee` was incorrectly resolved instead of `deew`, causing encoding failures

### Bug Fixes
- Fixed cross-platform crash: `creationflags` parameter no longer passed on Linux/macOS
- Fixed Deew encoding error: tool path now correctly resolves `deew` instead of raw `dee.exe`
- Fixed UI button state: analyze button properly disabled during processing
- Removed fragile `locals().get()` pattern for safer variable scoping
- `save_tool_paths()` now returns success/failure with UI feedback

### Documentation
- Merged `README_EN.md` and `README_TR.md` into a single `README.md` (English on top, Turkish on bottom)
- Updated project structure documentation

---

## Turkce

### Kodlama Motoru Yeniligi
- **Birlesik encoder modulu** — Tum kodlama islemleri icin yeni `encoder.py` soyutlama katmani
- **FFmpeg-yerel Dolby kodlama** — deew/DEE gerektirmeden dogrudan FFmpeg ile AC3/EAC3 kodlama
- **qaac ile AAC kodlama** — Apple AAC (TVBR/CVBR/ABR/CBR) destegi
- **FLAC kodlama** — Yapilandrilabilir sikistirma ile kayipsiz FLAC (0-12)
- **Opus kodlama** — Yapilandrilabilir bit hizi ile Opus

### Tool Paths (Istege Bagli)
- ffmpeg, ffprobe, qaac ve deew icin ozel yollar yapilandirilabilir
- Tum araclar varsayilan olarak sistem PATH kullanir — Tool Paths tamamen istege baglidir
- Duzeltildi: `dee`, `deew` yerine yanlis sekilde cozumleniyordu ve kodlama hatalirina neden oluyordu

### Hata Duzeltmeleri
- Platformlar arasi cokme duzeltildi: `creationflags` parametresi artik Linux/macOS'ta gecilmiyor
- Deew kodlama hatasi duzeltildi: arac yolu artik ham `dee.exe` yerine dogru sekilde `deew` cozumluyor
- UI buton durumu duzeltildi: analiz butonu islem sirasinda duzgun sekilde devre disi birakiliyor
- Daha guvenli degisken kapsami icin kirilgan `locals().get()` kalibi kaldirildi
- `save_tool_paths()` artik UI geri bildirimi ile basari/basarisizlik donduruyor

### Dokumantasyon
- `README_EN.md` ve `README_TR.md` tek bir `README.md` dosyasinda birlestirildi (Ingilizce ustte, Turkce altta)
- Proje yapisi dokumantasyonu guncellendi

---

## Installation / Kurulum

**Windows**: Download `AudioSyncTool-v2.2.0-win64.zip` from the assets below.

**From source**:
```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

**Full changelog**: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)

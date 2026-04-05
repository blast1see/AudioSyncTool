# Audio Sync Tool v2.2.1

## What's New / Yenilikler

### Added format support
- **DTS-HD input support** for `.dtshd` files
- **Dolby TrueHD input support** for `.thd` files
- Container stream probing now exposes richer codec metadata for stream selection

### Improved stream extraction
- DTS-HD streams are detected more accurately from FFmpeg metadata
- Stream picker now shows a clearer codec/profile label
- Extracted container streams use safer output extensions during temporary processing

### Build and packaging
- PyInstaller build excludes a large set of unrelated Conda packages
- Windows EXE builds complete much faster and avoid bundling many unnecessary modules
- Release package refreshed with the rebuilt `AudioSyncTool.exe`

---

## Turkce

### Eklenen format destegi
- `.dtshd` uzantili **DTS-HD** dosyalari destekleniyor
- `.thd` uzantili **Dolby TrueHD** dosyalari destekleniyor
- Container stream taramasi artik daha zengin codec metadata bilgisi uretiyor

### Iyilestirilen stream cikarma
- DTS-HD stream'leri FFmpeg metadata bilgisinden daha dogru algilaniyor
- Stream secim penceresi daha acik codec/profile etiketi gosteriyor
- Container icinden cikarilan gecici ses dosyalari daha guvenli uzantilarla olusturuluyor

### Derleme ve paketleme
- PyInstaller derlemesi, ilgisiz Conda paketlerini disarida birakacak sekilde daraltildi
- Windows EXE derlemesi daha hizli tamamlaniyor ve gereksiz moduller daha az paketleniyor
- Release paketi, yeniden olusturulan `AudioSyncTool.exe` ile yenilendi

---

## Installation / Kurulum

**Windows**: Download `AudioSyncTool-v2.2.1-win64.zip` from the assets below.

**From source**:
```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

**Full changelog**: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)

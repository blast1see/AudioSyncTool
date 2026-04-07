# Audio Sync Tool v2.2.3

## What's New / Yenilikler

### Encoding pipeline cleanup
- Deew is now a Deew-only pipeline with no FFmpeg encoder switch inside that panel
- AC3 and EAC3 output options were moved into the FFmpeg pipeline
- FFmpeg AC3/EAC3 output now has bitrate and channel layout controls in the correct place

### Verification
- UI smoke test confirmed the old Deew-side encoder selector is gone
- UI smoke test confirmed AC3/EAC3 controls now appear under the FFmpeg pipeline
- FFmpeg AC3 and EAC3 output creation was smoke-tested successfully after the refactor

### Release contents
- Updated Windows executable for v2.2.3
- Refreshed changelog, release notes, and README release badge

---

## Turkce

### Kodlama pipeline temizligi
- Deew artik kendi panelinde yalnizca Deew kullanan bir pipeline; bu panelde FFmpeg encoder secimi kaldirildi
- AC3 ve EAC3 cikti secenekleri FFmpeg pipeline altina tasindi
- FFmpeg AC3/EAC3 ciktilarina dogru yerde bitrate ve kanal duzeni kontrolleri eklendi

### Dogrulama
- UI smoke testi, Deew tarafindaki eski encoder seciminin kalktigini dogruladi
- UI smoke testi, AC3/EAC3 kontrollerinin artik FFmpeg pipeline altinda gorundugunu dogruladi
- FFmpeg AC3 ve EAC3 ciktilari refactor sonrasinda basariyla smoke test edildi

### Release icerigi
- Windows `exe` dosyasi v2.2.3 icin guncellendi
- Changelog, release notes ve README release badge yenilendi

---

## Installation / Kurulum

**Windows**: Download `AudioSyncTool-v2.2.3-win64.zip` from the assets below.

**From source**:
```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

**Full changelog**: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)

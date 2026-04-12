# Audio Sync Tool v2.2.4

## What's New / Yenilikler

### Performance and reliability improvements
- Analysis startup is lighter thanks to a lazier analyzer import path
- Long-running FFmpeg, qaac, and Deew jobs now share a safer cancellation/process runner path
- The analysis flow reuses more work and avoids unnecessary PCM copying during mono decode
- The app now validates that Deew can actually start before a Deew job begins

### Verification
- `python -m compileall audio_sync` passed
- Real Windows-environment Deew runtime probe passed
- Real Windows-environment short `.wav -> .eac3` Deew smoke encode passed

### Release contents
- Updated Windows executable for v2.2.4
- Refreshed changelog, release notes, and README release badge

---

## Turkce

### Performans ve guvenilirlik iyilestirmeleri
- Analyzer import yolu daha tembel hale getirilerek acilis yukü hafifletildi
- Uzun suren FFmpeg, qaac ve Deew islemleri daha guvenli ortak bir iptal/process runner akisini kullaniyor
- Analiz akisi mono decode sirasinda gereksiz PCM kopyalarini azaltacak sekilde iyilestirildi
- Deew isleri baslamadan once Deew'in gercekten calisabildigi dogrulaniyor

### Dogrulama
- `python -m compileall audio_sync` basariyla gecti
- Gercek Windows ortaminda Deew runtime probe basariyla gecti
- Gercek Windows ortaminda kisa `.wav -> .eac3` Deew smoke encode basariyla gecti

### Release icerigi
- Windows `exe` dosyasi v2.2.4 icin guncellendi
- Changelog, release notes ve README release badge yenilendi

---

## Installation / Kurulum

**Windows**: Download `AudioSyncTool-v2.2.4-win64.zip` from the assets below.

**From source**:
```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

**Full changelog**: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)

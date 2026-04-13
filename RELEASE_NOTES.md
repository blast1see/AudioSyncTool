# Audio Sync Tool v2.2.5

## What's New / Yenilikler

### Sync analysis improvements
- Added fingerprint anchor matching and a local offset-map refinement pass
- Fixed a bad final-delay aggregation case where weak windows could drag the result away from the dominant sync cluster
- The app now runs analysis on disk-backed mono PCM buffers, which keeps RAM usage much lower on long inputs
- Sync-point selection is now more stable on difficult matches and less sensitive to weak outlier windows

### Release contents
- Updated Windows executable for v2.2.5
- Refreshed changelog, release notes, and README release badge

---

## Turkce

### Senkron analiz iyilestirmeleri
- Fingerprint anchor eslestirme ve yerel offset-haritasi refinement katmani eklendi
- Zayif pencerelerin baskin senkron kumesini asagi cekebildigi hatali final-delay toplama durumu duzeltildi
- Uygulama artik analizi diskteki mono PCM tamponlari uzerinde yurutuyor; boylece uzun girdilerde RAM kullanimi daha dusuk kaliyor
- Senkron noktasi secimi artik zor eslesmelerde daha kararlı ve zayif aykiri pencerelere daha az duyarlı

### Release icerigi
- Windows `exe` dosyasi v2.2.5 icin guncellendi
- Changelog, release notes ve README release badge yenilendi

---

## Installation / Kurulum

**Windows**: Download `AudioSyncTool-v2.2.5-win64.zip` from the assets below.

**From source**:
```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

**Full changelog**: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)

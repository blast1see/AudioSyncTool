# Audio Sync Tool v2.2.5

## What's New / Yenilikler

### Sync analysis improvements
- Added AudioAlign-inspired fingerprint anchor matching and a local offset-map refinement pass
- Fixed a bad final-delay aggregation case where weak windows could drag the result away from the dominant sync cluster
- The app now runs analysis on disk-backed mono PCM buffers, which keeps RAM usage much lower on long inputs
- Real-world Devil's Advocate testing now lands at about `+1990.37 ms`, closely matching AudioAlign's `+1996 ms`

### Verification
- `python -m compileall audio_sync` passed
- `THD` self-self analysis returned `0.0 ms`
- `DTS-HD` self-self analysis returned `0.0 ms`
- A separate John Wick TR/EN excerpt smoke test stayed stable at about `+192.73 ms`

### Release contents
- Updated Windows executable for v2.2.5
- Refreshed changelog, release notes, and README release badge

---

## Turkce

### Senkron analiz iyilestirmeleri
- AudioAlign'den ilham alan fingerprint anchor eslestirme ve yerel offset-haritasi refinement katmani eklendi
- Zayif pencerelerin baskin senkron kumesini asagi cekebildigi hatali final-delay toplama durumu duzeltildi
- Uygulama artik analizi diskteki mono PCM tamponlari uzerinde yurutuyor; boylece uzun girdilerde RAM kullanimi daha dusuk kaliyor
- Gercek Devil's Advocate testinde sonuc artik yaklasik `+1990.37 ms` cikiyor; bu deger AudioAlign'deki `+1996 ms` sonucuna cok yakin

### Dogrulama
- `python -m compileall audio_sync` basariyla gecti
- `THD` self-self analiz sonucu `0.0 ms` oldu
- `DTS-HD` self-self analiz sonucu `0.0 ms` oldu
- Ayrica John Wick TR/EN excerpt smoke testinde sonuc yaklasik `+192.73 ms` olarak stabil kaldi

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

# Audio Sync Tool v2.2.2

## What's New / Yenilikler

### Synchronization fixes
- Fixed the `atempo` mode for tiny offsets so small positive and negative delays now settle correctly
- Corrected FPS slowdown/speedup indicator text to match the real conversion direction
- Renamed sync modes so the UI now reflects the actual filters used by each mode

### Verification
- All sync modes were smoke-tested with controlled offsets on Windows
- FPS conversion outputs were checked against expected duration ratios
- FFmpeg AC3/EAC3 output and Deew AC3/EAC3 output were both smoke-tested successfully
- Direct `.thd` and `.dtshd` input decoding was verified with real sample files

### Documentation and wording
- Removed `Dolby` / `DEE` wording from app-facing text and repository docs
- Updated README and changelog terminology to stay aligned with the current UI

---

## Turkce

### Senkronizasyon duzeltmeleri
- `atempo` modu kucuk ofsetlerde duzeltildi; artik kucuk pozitif ve negatif gecikmeler dogru sekilde sifirlaniyor
- FPS yavaslatma/hizlandirma gosterge metni gercek donusum yonu ile uyumlu hale getirildi
- Senkron mod adlari, UI'da kullanilan gercek filtrelerle uyumlu olacak sekilde guncellendi

### Dogrulama
- Tum senkron modlari Windows uzerinde kontrollu ofsetlerle smoke testten gecirildi
- FPS donusumu ciktilari beklenen sure oranlari ile karsilastirildi
- FFmpeg AC3/EAC3 ciktilari ve Deew AC3/EAC3 ciktilari basariyla smoke test edildi
- Gercek ornek dosyalarla dogrudan `.thd` ve `.dtshd` decode dogrulamasi yapildi

### Dokumantasyon ve metinler
- Uygulama metinlerinden ve repo dokumantasyonundan `Dolby` / `DEE` ifadeleri kaldirildi
- README ve changelog terminolojisi guncel UI ile uyumlu hale getirildi

---

## Installation / Kurulum

**Windows**: Download `AudioSyncTool-v2.2.2-win64.zip` from the assets below.

**From source**:
```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

**Full changelog**: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)

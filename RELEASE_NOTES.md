# Audio Sync Tool v2.1.0

## What's New / Yenilikler

### 🎬 MKV/MP4 Container Support
Drop MKV, MP4, or other container files directly — Audio Sync Tool will automatically detect audio streams and let you choose which one to use.

### 🖱️ Drag & Drop
Drag audio or video files directly onto the application window. Requires optional `tkinterdnd2` package.

### 🔧 Improved Deew/DEE Integration
- Better output file detection (searches multiple directories and alternate extensions)
- Enhanced error messages with directory contents for debugging
- stderr logging for better troubleshooting

### 🌐 English as Default Language
The UI now defaults to English. Turkish is still fully supported and can be switched at runtime.

### 🐛 Bug Fixes
- Temporary files from container extraction are cleaned up on exit
- Race condition guard for concurrent container operations
- File extension validation for drag & drop

---

## Türkçe

### 🎬 MKV/MP4 Container Desteği
MKV, MP4 veya diğer container dosyalarını doğrudan bırakın — Audio Sync Tool ses akışlarını otomatik tespit eder ve hangisini kullanacağınızı seçmenizi sağlar.

### 🖱️ Sürükle & Bırak
Ses veya video dosyalarını doğrudan uygulama penceresine sürükleyin. Opsiyonel `tkinterdnd2` paketi gerektirir.

### 🔧 Geliştirilmiş Deew/DEE Entegrasyonu
- Daha iyi çıktı dosyası tespiti (birden fazla dizin ve alternatif uzantı taraması)
- Hata ayıklama için dizin içeriği listeli geliştirilmiş hata mesajları
- Daha iyi sorun giderme için stderr günlüğü

### 🌐 Varsayılan Dil İngilizce
Arayüz artık varsayılan olarak İngilizce açılıyor. Türkçe tam olarak desteklenmeye devam ediyor ve çalışma zamanında değiştirilebilir.

### 🐛 Hata Düzeltmeleri
- Container çıkarma geçici dosyaları çıkışta temizleniyor
- Eşzamanlı container işlemleri için yarış durumu koruması
- Sürükle-bırak için dosya uzantısı doğrulaması

---

## Installation / Kurulum

**Windows**: Download `AudioSyncTool-v2.1.0-win64.zip` from the assets below.

**From source**:
```bash
git clone https://github.com/blast1see/AudioSyncTool.git
cd AudioSyncTool
pip install -r requirements.txt
python -m audio_sync
```

**Full changelog**: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)

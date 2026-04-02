# Changelog / Değişiklik Günlüğü

> [🇬🇧 English](#english) | [🇹🇷 Türkçe](#türkçe)

---

## English

### [2.2.0] - 2026-04-02

#### Added
- **Unified encoder module** (`audio_sync/core/encoder.py`): New abstraction layer for encoding operations (AAC via qaac/FFmpeg, FLAC, Opus, Dolby DD/DDP via FFmpeg)
- **FFmpeg-native Dolby encoding**: AC3 and EAC3 encoding directly via FFmpeg as an alternative to deew/DEE
- **AAC encoding via qaac**: Apple AAC (TVBR/CVBR/ABR/CBR) encoding support through qaac
- **FLAC encoding**: Lossless FLAC encoding with configurable compression level (0-12)
- **Opus encoding**: Opus encoding with configurable bitrate
- **Tool Paths configuration**: Optional custom paths for ffmpeg, ffprobe, qaac, and deew — falls back to system PATH when empty
- **save_tool_paths() return value**: Now returns `bool` for success/failure with UI warning on save error

#### Changed
- **Renamed `ToolPaths.dee` to `ToolPaths.deew`**: The tool path field now correctly references the `deew` wrapper instead of the raw DEE binary, preventing `resolve_tool("dee")` from finding the wrong executable
- **Cross-platform subprocess fix**: `encoder.py` uses `_PLATFORM_SUBPROCESS_KWARGS` dict instead of `creationflags` constant, preventing `TypeError` on Linux/macOS
- **UI button state management**: `analyze_btn` is now disabled during processing and re-enabled in the `_process()` finally block alongside `run_btn`
- **Removed fragile `locals().get()` pattern**: `needs_encoding` variable is now properly scoped before the try block
- **Removed redundant pipeline assignment**: Eliminated duplicate `pipeline = self._encoding_pipeline_var.get()` call
- **Merged README files**: Combined `README_EN.md` and `README_TR.md` into a single `README.md` with English on top and Turkish on bottom
- Encoding pipeline parameters expanded with format-specific options (bitrate, quality, compression level)

#### Fixed
- **Deew/DEE tool resolution bug**: `resolve_tool("dee")` was finding `dee.exe` (raw Dolby Encoding Engine) instead of `deew` wrapper, causing "Unknown option: -i" errors
- **Cross-platform crash**: `creationflags=0` passed to `subprocess.run()` on non-Windows systems now prevented
- **Button state race condition**: Analyze button could remain enabled while processing was running

#### Documentation
- Merged bilingual README into single `README.md` with anchor-based language navigation
- Removed `README_EN.md` and `README_TR.md`
- Updated project structure to reflect new `encoder.py` module
- Added qaac and Tool Paths documentation

### [2.1.0] - 2026-04-01

#### Added
- **MKV/MP4 Container Support**: Automatically detect and extract audio streams from container files (MKV, MP4, M4V, WEBM, TS, MTS)
- **Audio Stream Selection Dialog**: When a container has multiple audio streams, a dialog lets you choose which stream to use (shows codec, channels, sample rate, language, bitrate)
- **Drag & Drop Support**: Native file drag & drop via tkinterdnd2 (optional dependency) with visual feedback on hover
- **Drop zone hint labels**: "or drag & drop file here" text shown in file selection areas
- `.ec3` extension support as alternate for EAC3 (Dolby Digital Plus)
- `CODEC_EXTENSION_MAP` configuration constant for codec-to-extension mapping
- `ALL_SUPPORTED_EXTENSIONS_LIST` combining audio and container extensions
- New i18n keys for MKV/container handling, drag & drop, and common buttons (OK/Cancel)

#### Changed
- Default UI language changed from Turkish to English
- SyncMode display labels translated to English (e.g., "adelay + amix (Default)", "atempo (trim + fine-tune)")
- DeewDRC default label changed to "Music Light (default)"
- All error messages and progress callbacks translated from Turkish to English
- File selection dialog now accepts container formats alongside audio files
- Improved Deew output file search: searches input directory, subdirectories, and tries alternate extensions (.ec3/.eac3)
- Enhanced error messages with directory contents listing for debugging Deew output issues
- Deew encoder now logs stderr output for better debugging
- Updated `requirements.txt` with optional `tkinterdnd2` dependency
- Application base class uses `TkinterDnD.Tk` when available for drag & drop support

#### Fixed
- Temporary files from container extraction are now cleaned up on application exit
- Race condition guard added for concurrent container extraction operations
- Drop zone validates file extensions before accepting dropped files
- Deew output file search now handles DEE writing to input directory instead of output directory

#### Documentation
- Complete bilingual README system: `README.md` (language selector), `README_EN.md`, `README_TR.md`
- Added `CHANGELOG.md` (this file)
- Added `RELEASE_NOTES.md` for GitHub release descriptions
- Cross-linked CHANGELOG from all README files

#### Build
- Added missing `audio_sync.ui.stream_dialog` hidden import to PyInstaller build script

### [2.0.0] - 2026-03-30

#### Added
- Initial public release
- Cross-correlation based audio delay detection
- 6 synchronization modes: adelay+amix, aresample, atempo, rubberband, apad+atrim, asyncts
- Dolby Digital (AC3) and Dolby Digital Plus (EAC3) encoding via deew/DEE integration
- FPS conversion support (23.976 ↔ 25 ↔ 29.97 etc.)
- Bilingual UI (Turkish / English) with runtime language switching
- Dark-themed modern tkinter interface
- Preserves original audio quality (bit depth, sample rate, channels)
- Pre-built Windows EXE distribution
- MIT License

---

## Türkçe

### [2.2.0] - 2026-04-02

#### Eklenenler
- **Birleşik encoder modülü** (`audio_sync/core/encoder.py`): Kodlama işlemleri için yeni soyutlama katmanı (qaac/FFmpeg ile AAC, FLAC, Opus, FFmpeg ile Dolby DD/DDP)
- **FFmpeg-yerel Dolby kodlama**: deew/DEE alternatifi olarak doğrudan FFmpeg ile AC3 ve EAC3 kodlama
- **qaac ile AAC kodlama**: qaac aracılığıyla Apple AAC (TVBR/CVBR/ABR/CBR) kodlama desteği
- **FLAC kodlama**: Yapılandırılabilir sıkıştırma seviyesi (0-12) ile kayıpsız FLAC kodlama
- **Opus kodlama**: Yapılandırılabilir bit hızı ile Opus kodlama
- **Tool Paths yapılandırması**: ffmpeg, ffprobe, qaac ve deew için isteğe bağlı özel yollar — boş bırakıldığında sistem PATH'ine geri döner
- **save_tool_paths() dönüş değeri**: Başarı/başarısızlık için `bool` döndürür, kaydetme hatasında UI uyarısı gösterir

#### Değişenler
- **`ToolPaths.dee` → `ToolPaths.deew` olarak yeniden adlandırıldı**: Tool path alanı artık ham DEE ikili dosyası yerine doğru şekilde `deew` sarmalayıcısına referans veriyor
- **Platformlar arası subprocess düzeltmesi**: `encoder.py` artık `creationflags` sabiti yerine `_PLATFORM_SUBPROCESS_KWARGS` sözlüğü kullanıyor, Linux/macOS'ta `TypeError` önleniyor
- **UI buton durum yönetimi**: `analyze_btn` artık işlem sırasında devre dışı bırakılıyor ve `_process()` finally bloğunda `run_btn` ile birlikte yeniden etkinleştiriliyor
- **Kırılgan `locals().get()` kalıbı kaldırıldı**: `needs_encoding` değişkeni artık try bloğundan önce düzgün şekilde tanımlanıyor
- **Gereksiz pipeline ataması kaldırıldı**: Tekrarlanan `pipeline = self._encoding_pipeline_var.get()` çağrısı silindi
- **README dosyaları birleştirildi**: `README_EN.md` ve `README_TR.md` tek bir `README.md` dosyasında birleştirildi (İngilizce üstte, Türkçe altta)

#### Düzeltilenler
- **Deew/DEE araç çözümleme hatası**: `resolve_tool("dee")`, `deew` sarmalayıcısı yerine `dee.exe` (ham Dolby Encoding Engine) buluyordu, "Unknown option: -i" hatalarına neden oluyordu
- **Platformlar arası çökme**: Windows dışı sistemlerde `subprocess.run()` için `creationflags=0` geçilmesi engellendi
- **Buton durumu yarış koşulu**: İşlem devam ederken Analyze butonunun etkin kalabilmesi düzeltildi

#### Dokümantasyon
- İki dilli README tek `README.md` dosyasında çapa tabanlı dil navigasyonu ile birleştirildi
- `README_EN.md` ve `README_TR.md` silindi
- Proje yapısı yeni `encoder.py` modülünü yansıtacak şekilde güncellendi
- qaac ve Tool Paths dokümantasyonu eklendi

### [2.1.0] - 2026-04-01

#### Eklenenler
- **MKV/MP4 Container Desteği**: Container dosyalarından (MKV, MP4, M4V, WEBM, TS, MTS) ses akışlarını otomatik tespit ve çıkarma
- **Ses Akışı Seçim Diyaloğu**: Birden fazla ses akışı olan container dosyalarında codec, kanal, örnekleme hızı, dil ve bitrate bilgileriyle akış seçimi
- **Sürükle & Bırak Desteği**: tkinterdnd2 ile yerel dosya sürükle-bırak desteği ve görsel geri bildirim
- **Bırakma alanı ipucu etiketleri**: Dosya seçim alanlarında "veya dosyayı buraya sürükleyin" metni
- EAC3 (Dolby Digital Plus) için alternatif `.ec3` uzantı desteği
- Codec-uzantı eşleme için `CODEC_EXTENSION_MAP` yapılandırma sabiti
- Ses ve container uzantılarını birleştiren `ALL_SUPPORTED_EXTENSIONS_LIST`
- MKV/container işleme, sürükle-bırak ve ortak butonlar (Tamam/İptal) için yeni i18n anahtarları

#### Değişenler
- Varsayılan arayüz dili Türkçe'den İngilizce'ye değiştirildi
- SyncMode görüntüleme etiketleri İngilizce'ye çevrildi
- Tüm hata mesajları ve ilerleme geri bildirimleri İngilizce'ye çevrildi
- Dosya seçim diyaloğu artık container formatlarını da kabul ediyor
- Deew çıktı dosyası araması iyileştirildi: giriş dizini, alt dizinler ve alternatif uzantılar taranıyor
- Deew hata mesajları dizin içeriği listesiyle zenginleştirildi
- Deew encoder artık hata ayıklama için stderr çıktısını günlüğe kaydediyor
- `requirements.txt` opsiyonel `tkinterdnd2` bağımlılığıyla güncellendi
- Uygulama temel sınıfı sürükle-bırak için `TkinterDnD.Tk` kullanıyor (mevcut olduğunda)

#### Düzeltilenler
- Container çıkarma geçici dosyaları artık uygulama kapanışında temizleniyor
- Eşzamanlı container çıkarma işlemleri için yarış durumu koruması eklendi
- Bırakma alanı, dosya uzantılarını kabul etmeden önce doğruluyor
- Deew çıktı dosyası araması, DEE'nin çıktıyı giriş dizinine yazması durumunu ele alıyor

#### Dokümantasyon
- Tam iki dilli README sistemi: `README.md` (dil seçici), `README_EN.md`, `README_TR.md`
- `CHANGELOG.md` eklendi (bu dosya)
- GitHub sürüm açıklamaları için `RELEASE_NOTES.md` eklendi
- Tüm README dosyalarından CHANGELOG'a çapraz bağlantı eklendi

#### Derleme
- PyInstaller derleme betiğine eksik `audio_sync.ui.stream_dialog` hidden import eklendi

### [2.0.0] - 2026-03-30

#### Eklenenler
- İlk genel sürüm
- Çapraz korelasyon tabanlı ses gecikme tespiti
- 6 senkronizasyon modu: adelay+amix, aresample, atempo, rubberband, apad+atrim, asyncts
- deew/DEE entegrasyonu ile Dolby Digital (AC3) ve Dolby Digital Plus (EAC3) kodlama
- FPS dönüşüm desteği (23.976 ↔ 25 ↔ 29.97 vb.)
- Çalışma zamanında dil değiştirmeli iki dilli arayüz (Türkçe / İngilizce)
- Karanlık temalı modern tkinter arayüzü
- Orijinal ses kalitesini koruma (bit derinliği, örnekleme hızı, kanallar)
- Önceden derlenmiş Windows EXE dağıtımı
- MIT Lisansı

[2.2.0]: https://github.com/blast1see/AudioSyncTool/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/blast1see/AudioSyncTool/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/blast1see/AudioSyncTool/releases/tag/v2.0.0

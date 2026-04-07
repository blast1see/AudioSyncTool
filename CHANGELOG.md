# Changelog / Degisiklik Gunlugu

> [English](#english) | [Turkce](#turkce)

---

## English

### [2.2.3] - 2026-04-07

#### Changed
- **Encoding pipeline separation**: the Deew pipeline is now Deew-only and no longer exposes an FFmpeg encoder switch
- **FFmpeg AC3/EAC3 outputs moved**: AC3 and EAC3 output options now live under the FFmpeg pipeline where they belong
- **FFmpeg surround controls**: AC3/EAC3 encoding in the FFmpeg pipeline now includes bitrate and channel layout controls

#### Verified
- **UI smoke test**: confirmed the old Deew-side encoder selector is gone and AC3/EAC3 controls appear under FFmpeg
- **FFmpeg encode smoke test**: verified successful AC3 and EAC3 output creation after the pipeline refactor

### [2.2.2] - 2026-04-05

#### Fixed
- **`atempo` micro-offset synchronization**: tiny positive and negative delays now converge correctly instead of drifting further away
- **FPS conversion indicator text**: slowdown/speedup direction labels now match the actual `atempo` behavior
- **Sync mode naming**: UI and docs now reflect the real filters and behavior used by each mode

#### Changed
- **Deew-only wording cleanup**: removed `Dolby` / `DEE` mentions from the app text and public docs to reduce branding/licensing risk
- **Verified encode paths**: FFmpeg AC3/EAC3 output and Deew AC3/EAC3 output were smoke-tested on Windows

### [2.2.1] - 2026-04-05

#### Added
- **DTS-HD input support**: `.dtshd` files are now accepted as direct audio inputs
- **TrueHD input support**: `.thd` files are now accepted as direct audio inputs
- **Richer container stream metadata**: stream probing now reads codec profile and long codec name for improved labeling

#### Changed
- **Smarter temporary extraction extensions**: DTS-HD container streams now use a safer temporary `.dts` extension during extraction
- **Improved stream picker labels**: codec display now shows DTS-HD and TrueHD details more clearly
- **Lean PyInstaller build**: build script now excludes a large set of unrelated Conda and data-science modules to reduce packaging overhead

#### Documentation
- Updated README supported format tables with DTS-HD and TrueHD entries
- Refreshed release notes and release badge for v2.2.1

### [2.2.0] - 2026-04-02

#### Added
- **Unified encoder module** (`audio_sync/core/encoder.py`): New abstraction layer for encoding operations (AAC via qaac/FFmpeg, FLAC, Opus, AC3/EAC3 via FFmpeg)
- **FFmpeg-native AC3/EAC3 encoding**: AC3 and EAC3 encoding directly via FFmpeg as an alternative to deew
- **AAC encoding via qaac**: Apple AAC (TVBR/CVBR/ABR/CBR) encoding support through qaac
- **FLAC encoding**: Lossless FLAC encoding with configurable compression level (0-12)
- **Opus encoding**: Opus encoding with configurable bitrate
- **Tool Paths configuration**: Optional custom paths for ffmpeg, ffprobe, qaac, and deew; falls back to system PATH when empty
- **save_tool_paths() return value**: Now returns `bool` for success/failure with UI warning on save error

#### Changed
- **Renamed legacy `ToolPaths.dee` to `ToolPaths.deew`**: The tool path field now correctly references `deew`
- **Cross-platform subprocess fix**: `encoder.py` uses `_PLATFORM_SUBPROCESS_KWARGS` instead of a Windows-only `creationflags` constant
- **UI button state management**: `analyze_btn` is now disabled during processing and re-enabled in the `_process()` finally block alongside `run_btn`
- **Removed fragile `locals().get()` pattern**: `needs_encoding` is now properly scoped before the try block
- **Removed redundant pipeline assignment**: Eliminated duplicate `pipeline = self._encoding_pipeline_var.get()` call
- **Merged README files**: Combined `README_EN.md` and `README_TR.md` into a single `README.md`
- Encoding pipeline parameters expanded with format-specific options (bitrate, quality, compression level)

#### Fixed
- **Deew tool resolution bug**: legacy `dee.exe` detection could shadow the `deew` wrapper
- **Cross-platform crash**: prevented `creationflags=0` from being passed to `subprocess.run()` on non-Windows systems
- **Button state race condition**: Analyze button could remain enabled while processing was running

#### Documentation
- Merged bilingual README into single `README.md` with anchor-based language navigation
- Removed `README_EN.md` and `README_TR.md`
- Updated project structure to reflect the new `encoder.py` module
- Added qaac and Tool Paths documentation

### [2.1.0] - 2026-04-01

#### Added
- **MKV/MP4 Container Support**: Automatically detect and extract audio streams from container files (MKV, MP4, M4V, WEBM, TS, MTS)
- **Audio Stream Selection Dialog**: Lets you choose a stream when a container has multiple audio tracks
- **Drag & Drop Support**: Native file drag and drop via tkinterdnd2 with visual feedback on hover
- **Drop zone hint labels**: "or drag & drop file here" text shown in file selection areas
- `.ec3` extension support as an alternate for EAC3
- `CODEC_EXTENSION_MAP` configuration constant for codec-to-extension mapping
- `ALL_SUPPORTED_EXTENSIONS_LIST` combining audio and container extensions
- New i18n keys for MKV/container handling, drag and drop, and common buttons

#### Changed
- Default UI language changed from Turkish to English
- SyncMode display labels translated to English
- DeewDRC default label changed to "Music Light (default)"
- All error messages and progress callbacks translated from Turkish to English
- File selection dialog now accepts container formats alongside audio files
- Improved Deew output file search: searches input directory, subdirectories, and alternate extensions (`.ec3` / `.eac3`)
- Enhanced error messages with directory contents listing for debugging Deew output issues
- Deew encoder now logs stderr output for better debugging
- Updated `requirements.txt` with optional `tkinterdnd2` dependency
- Application base class uses `TkinterDnD.Tk` when available

#### Fixed
- Temporary files from container extraction are now cleaned up on application exit
- Race condition guard added for concurrent container extraction operations
- Drop zone validates file extensions before accepting dropped files
- Deew output file search now handles output files being written to the input directory instead of the output directory

#### Documentation
- Complete bilingual README system: `README.md`, `README_EN.md`, `README_TR.md`
- Added `CHANGELOG.md`
- Added `RELEASE_NOTES.md` for GitHub release descriptions
- Cross-linked CHANGELOG from all README files

#### Build
- Added missing `audio_sync.ui.stream_dialog` hidden import to the PyInstaller build script

### [2.0.0] - 2026-03-30

#### Added
- Initial public release
- Cross-correlation based audio delay detection
- 6 synchronization modes: adelay/atrim, aresample, atempo, rubberband, delay/trim, async resample
- AC3 and EAC3 encoding via deew integration
- FPS conversion support (23.976 <-> 25 <-> 29.97 etc.)
- Bilingual UI (Turkish / English) with runtime language switching
- Dark-themed modern tkinter interface
- Preserves original audio quality (bit depth, sample rate, channels)
- Pre-built Windows EXE distribution
- MIT License

---

## Turkce

### [2.2.3] - 2026-04-07

#### Degisenler
- **Kodlama pipeline ayrimi**: Deew pipeline artik yalnizca Deew kullaniyor ve FFmpeg encoder secimi gostermiyor
- **FFmpeg AC3/EAC3 ciktilari tasindi**: AC3 ve EAC3 cikti secenekleri artik dogru yerde, FFmpeg pipeline altinda bulunuyor
- **FFmpeg surround kontrolleri**: FFmpeg pipeline icindeki AC3/EAC3 kodlamasina bitrate ve kanal duzeni kontrolleri eklendi

#### Dogrulama
- **UI smoke testi**: Deew tarafindaki eski encoder seciminin kalktigi ve AC3/EAC3 kontrollerinin FFmpeg altinda gorundugu dogrulandi
- **FFmpeg encode smoke testi**: pipeline refactor sonrasi AC3 ve EAC3 ciktilarinin basariyla uretildigi dogrulandi

### [2.2.2] - 2026-04-05

#### Duzeltilenler
- **`atempo` kucuk ofset senkronizasyonu**: kucuk pozitif ve negatif gecikmeler artik ters yone kaymak yerine dogru sekilde sifira yaklasiyor
- **FPS donusumu gosterge metni**: yavaslatma/hizlandirma etiketleri artik gercek `atempo` davranisi ile uyumlu
- **Senkron mod isimleri**: UI ve dokumantasyon, her modun gercekte kullandigi filtre ve davranisla uyumlu hale getirildi

#### Degisenler
- **Yalnizca Deew odakli metin temizligi**: uygulama metinlerinden ve dokumantasyondan `Dolby` / `DEE` ifadeleri kaldirilarak marka/lisans riski azaltildi
- **Kodlama yollarinin dogrulanmasi**: Windows uzerinde FFmpeg AC3/EAC3 ciktilari ve Deew AC3/EAC3 ciktilari smoke test ile dogrulandi

### [2.2.1] - 2026-04-05

#### Eklenenler
- **DTS-HD giris destegi**: `.dtshd` dosyalari dogrudan ses girdisi olarak kabul ediliyor
- **TrueHD giris destegi**: `.thd` dosyalari dogrudan ses girdisi olarak kabul ediliyor
- **Daha zengin container stream metadata bilgisi**: stream taramasi codec profile ve long codec name alanlarini okuyarak daha net etiketleme sagliyor

#### Degisenler
- **Daha guvenli gecici cikarma uzantilari**: container icindeki DTS-HD stream'leri cikarma sirasinda gecici olarak `.dts` uzantisi kullaniliyor
- **Iyilestirilmis stream secim etiketleri**: codec gosterimi DTS-HD ve TrueHD ayrimini daha net veriyor
- **Daha hafif PyInstaller derlemesi**: build betigi, ilgisiz Conda ve veri bilimi modullerini dislayarak paketleme yukunu azaltiyor

#### Dokumantasyon
- README desteklenen format tablolarina DTS-HD ve TrueHD eklendi
- v2.2.1 icin release notlari ve release badge guncellendi

### [2.2.0] - 2026-04-02

#### Eklenenler
- **Birlesik encoder modulu** (`audio_sync/core/encoder.py`): Kodlama islemleri icin yeni soyutlama katmani
- **FFmpeg-yerel AC3/EAC3 kodlama**: deew alternatifi olarak dogrudan FFmpeg ile AC3 ve EAC3 kodlama
- **qaac ile AAC kodlama**: qaac araciligiyla Apple AAC (TVBR/CVBR/ABR/CBR) destegi
- **FLAC kodlama**: Yapilandirilabilir sikistirma seviyesi (0-12) ile kayipsiz FLAC
- **Opus kodlama**: Yapilandirilabilir bit hizi ile Opus
- **Tool Paths yapilandirmasi**: ffmpeg, ffprobe, qaac ve deew icin istege bagli ozel yollar; bos oldugunda sistem PATH kullanilir
- **save_tool_paths() donus degeri**: Basari ve basarisizlik icin `bool` dondurur

#### Degisenler
- **`ToolPaths.dee` yerine `ToolPaths.deew`**: Tool path alani artik dogru sekilde `deew` sarmalayicisini hedefliyor
- **Platformlar arasi subprocess duzeltmesi**: `encoder.py` artik Windows'a ozel `creationflags` yerine platforma uygun argumanlar kullaniyor
- **UI buton durum yonetimi**: `analyze_btn` islem sirasinda devre disi birakiliyor ve finally blogunda geri aciliyor
- **Kirigan `locals().get()` kalibi kaldirildi**: `needs_encoding` artik daha guvenli sekilde kapsamlanmis durumda
- **Gereksiz pipeline atamasi kaldirildi**
- **README dosyalari birlestirildi**: `README_EN.md` ve `README_TR.md`, tek `README.md` altinda toplandi
- Kodlama pipeline parametreleri format bazli seceneklerle genisletildi

#### Duzeltilenler
- **Deew arac cozumleme hatasi**: eski `dee` yolu bazen `deew` wrapper'ini kacirabiliyordu
- **Platformlar arasi cokme**: Windows disinda `creationflags=0` gecilmesi onlendi
- **Buton durumu yaris kosulu**: Analyze butonu islem surerken aktif kalabiliyordu

#### Dokumantasyon
- Iki dilli README tek `README.md` dosyasinda cipa tabanli dil navigasyonu ile birlestirildi
- `README_EN.md` ve `README_TR.md` kaldirildi
- Proje yapisi yeni `encoder.py` modulunu yansitacak sekilde guncellendi
- qaac ve Tool Paths dokumantasyonu eklendi

### [2.1.0] - 2026-04-01

#### Eklenenler
- **MKV/MP4 container destegi**: MKV, MP4, M4V, WEBM, TS ve MTS gibi container dosyalarindan ses akisi secimi ve cikarma
- **Ses akisi secim diyalogu**: Birden fazla ses akisi olan dosyalarda codec, kanal, ornekleme hizi, dil ve bitrate bilgileriyle secim
- **Surukle ve birak destegi**: tkinterdnd2 ile yerel dosya surukle birak destegi
- **Birakma alani ipucu etiketleri**
- EAC3 icin alternatif `.ec3` uzanti destegi
- `CODEC_EXTENSION_MAP` sabiti
- `ALL_SUPPORTED_EXTENSIONS_LIST`
- MKV/container isleme, surukle birak ve ortak butonlar icin yeni i18n anahtarlari

#### Degisenler
- Varsayilan arayuz dili Turkce'den Ingilizce'ye degisti
- SyncMode etiketleri Ingilizce'ye cevrildi
- DeewDRC varsayilan etiketi "Music Light (default)" oldu
- Hata mesajlari ve ilerleme bildirimleri Ingilizce'ye cevrildi
- Dosya secim diyalogu artik container formatlarini da kabul ediyor
- Deew cikti dosyasi aramasi iyilestirildi
- Deew encoder artik stderr ciktilarini da gunluyor
- `requirements.txt`, opsiyonel `tkinterdnd2` ile guncellendi
- Temel uygulama sinifi mevcutsa `TkinterDnD.Tk` kullaniyor

#### Duzeltilenler
- Container cikarma gecici dosyalari cikista temizleniyor
- Eszamanli container cikarma islemleri icin yaris durumu korumasi eklendi
- Birakma alani, dosya uzantilarini kabul etmeden once dogruluyor
- Deew cikti aramasi, cikti dosyasinin giris dizinine yazilmasi durumunu ele aliyor

#### Dokumantasyon
- Tam iki dilli README sistemi: `README.md`, `README_EN.md`, `README_TR.md`
- `CHANGELOG.md` eklendi
- GitHub surum aciklamalari icin `RELEASE_NOTES.md` eklendi
- Tum README dosyalarindan CHANGELOG'a baglanti eklendi

#### Derleme
- PyInstaller betigine eksik `audio_sync.ui.stream_dialog` hidden import eklendi

### [2.0.0] - 2026-03-30

#### Eklenenler
- Ilk genel surum
- Capraz korelasyon tabanli ses gecikme tespiti
- 6 senkronizasyon modu
- deew entegrasyonu ile AC3 ve EAC3 kodlama
- FPS donusum destegi
- Calisma zamaninda dil degistirmeli iki dilli arayuz
- Karanlik temali modern tkinter arayuzu
- Orijinal ses kalitesini koruma
- Onceden derlenmis Windows EXE dagitimi
- MIT Lisansi

[2.2.3]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.2...v2.2.3
[2.2.2]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/blast1see/AudioSyncTool/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/blast1see/AudioSyncTool/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/blast1see/AudioSyncTool/releases/tag/v2.0.0

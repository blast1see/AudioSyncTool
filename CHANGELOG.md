# Changelog / Degisiklik Gunlugu

> [English](#english) | [Turkce](#turkce)

---

## English

### [2.4.1] - 2026-08-06

An interface audit. v2.4.0 rebuilt the window and added several panels, and the
translation table did not keep pace with them — this release closes that gap and
adds tests that fail when it opens again.

#### Fixed
- **Five dropdowns showed the internal value instead of the option's name.** The DRC profile read `music_light`, the qaac mode read `--tvbr`, the deew format read `ddp`, the FFmpeg format read `aac`, and the pipeline selector read `none`. Tk ties an `OptionMenu`'s caption to its variable, so displaying a name meant giving the button its own display variable while the original keeps the value every caller reads — the enums have carried proper display names all along, and the pipeline selector even built a list of (value, label) pairs and then discarded the labels. A trace drives the caption, so a value assigned from code shows through too, and the menus rebuild on a language change because some labels are translated.
- **The pipeline logged in English into a Turkish log box.** All sixteen of its progress messages, and deew's, bypassed the translation table; a language switch left the running commentary in whichever language it happened to be written in. Both now go through `t()`.
- **A missing key rendered as the key itself.** `t()` returns its argument when it cannot find a translation, so an undefined key became the caption — one button read `cancel`. The keys that reached the user without a definition are now defined, and a test fails on any `t()` call whose key is not in the table.
- **31 translation entries no longer had a use.** Most were left behind by features that changed shape, but the same audit found the opposite case — deew's start and completion messages were dead because the code had quietly replaced them with hard-coded English, which is invisible until someone switches language and looks exactly like harmless dead weight until you check. The dead entries are gone, and a test fails when an entry stops being referenced.
- **The AC3/E-AC3 encode summary printed a command line.** It logged a partial ffmpeg invocation ending in the staged temporary filename; the other formats report `AAC 192 kbps`, and this one now reads `AC3 448 kbps`.

#### Added
- `tests/test_i18n_completeness.py` — every key present in both languages, every key used in code defined, every defined key referenced, placeholders matching across languages, every string formattable, and nothing user-facing bypassing the table.
- Two GUI tests covering the dropdowns: the caption is a label rather than the value even after a code-side assignment, and it follows a language change without losing the selection.

#### Verified
- All twelve encoding pipelines re-run end to end (FFmpeg AAC / FLAC-16 / FLAC-24 / Opus / AC3 / E-AC3 / 1-channel, deew DD and DDP, qaac TVBR, plain WAV): correct codec, channel count and duration, residual offset −7 to −13 ms.
- Both languages swept widget by widget — no raw translation key and no raw internal value reaches the screen.
- Layout geometry is unchanged from v2.4.0 (1236 px content width; per-panel heights identical).

### [2.4.0] - 2026-08-05

Validated end to end against eight feature-length film pairs (Turkish dubs
against their BluRay/UHD remuxes), with every measurement cross-checked by an
independent correlation that shares no code with the analyzer.

#### Fixed
- **Choosing a downmix the track already had aborted the deew encode.** deew rejects `-dm` unless the target is *fewer* channels than the input, so asking a stereo track for a stereo downmix failed with "downmix value has to be lower than the number of input channels" — after the synchronization had already succeeded. Picking "Stereo" for a stereo source is a reasonable way to say "leave it alone", so the flag is now omitted instead, and the log says why.
- **The preserved WAV was left on disk without saying how big it was.** When encoding fails the synchronized audio is kept deliberately, so the analysis does not have to be repeated — but it is uncompressed and as long as the film, several GB for a feature. The message now reports its size and says to delete it when it is no longer needed. Verified that nothing else survives: a successful run, an FPS conversion, a deew or FFmpeg encode, and a cancellation each leave zero bytes behind in the output folder and the system temp directory.
- **A single high-scoring window could decide the delay for a whole film.** Correlation scores are peak-to-noise-floor ratios, so a window aligning two stretches of near-silence (end credits, a reel gap) scored far above windows carrying dialogue, and the linear weighting let it overrule everything else. On a 138-minute cross-language pair, 23 of 27 windows agreed on -9490 ms and *all* of them were discarded in favour of two outliers — putting roughly two hours of the film 135 ms out of sync, well past the threshold where lip-sync reads as broken. Window weights are now capped at 4x the median, which preserves the ordering while making it impossible for one window to outvote a consistent majority. Measured on the same pair, the reported delay moved from -9620.0 ms to -9498.6 ms and the windows kept rose from 2/27 to 49/71.
- Progress percentage was hard-coded in the Turkish `%42` form and leaked into the English UI; it now follows the active language.
- `used_segments` could exceed `total_segments` once the refinement pass added windows, so the UI reported impossible counts such as "63/12".

#### Added
- **A detected frame-rate mismatch is corrected without being asked.** Detection alone still left the user with a broken file until they noticed the log, opened the FPS panel and ran the whole job again. The pipeline now converts and re-analyzes on its own, then keeps the result only if the validated windows agree more closely than they did before — so a wrong guess cannot make a correct pair worse. On the 132-minute pair this took the default-settings result from **4.0 s of error down to 352 ms** with no user action, and the windows exceeding 45 ms from 11 of 11 to 4 of 12. The second pass only runs when a mismatch was actually found. Turn it off with **Detect and correct a frame-rate mismatch automatically**.
- `SyncRequest.auto_fps_conversion`, `SyncOutcome.fps_conversion_applied`.
- **Frame-rate mismatches are now identified, not just endured.** A dub mastered at the wrong rate is a fixed-ratio speed error, and the tool now tests for it directly: the coarse feature stream is resampled by each standard ratio and scored, so a mismatch is found even when it is far too large for the segment search to measure. Verified against eight real film pairs — it named the two that were mismatched (23.976↔24 in both directions) and stayed silent on the other six. This matters because FPS conversion runs *before* analysis: on a 132-minute pair whose offset slid from +40.3 s to +32.5 s, correcting after the fact left 4.0 s of error, while enabling the conversion the tool now suggests brought it to 375 ms with most of the film inside ±30 ms.
- `AnalysisResult.suspected_fps_conversion`, `AudioAnalyzer.detect_rate_mismatch()`, `FpsConversion.corrects_drift_ms_per_min`, `config.match_drift_to_fps()`, `SyncPipeline.suspected_fps_conversion()`.
- **A readable explanation when deew dies on a non-UTF-8 locale.** deew draws a logo through `rich` before encoding; on Windows the child inherits the system code page, and on Turkish cp1254 — and every other page that cannot represent the logo's block characters — it exits with a Python traceback and no output. `PYTHONIOENCODING`, `PYTHONUTF8`, `TERM` and `chcp 65001` were each verified not to change it, so the crash is now recognised and replaced with the one line that fixes it (`logo = 0`) plus the config paths to edit.
- **The tool now says when its own answer cannot be trusted.** A high confidence score only means each window matched something convincingly; it says nothing about whether the windows agree with *each other*, which is what decides whether one delay holds across a film. `AnalysisResult.windows_disagree_ms` reports that spread, and above 100 ms the log warns and the readout is marked weak regardless of score. Found by testing a 132-minute cross-language pair whose true offset slid from +40.3 s to +32.5 s: the windows disagreed by 200 ms and the output was seconds out at the ends, while the old UI called it a "fair" match.
- **A coarse drift bracket for sources that slide further than the search window.** Segment validation only searches `local_search_sec` around one coarse lag, so when two encodes run at different clock rates most of a feature film falls outside it and never validates. The first and last thirds are now correlated separately and, when they disagree by more than the search window, are fed in as a pair of anchors so validation follows the slope — reusing the interpolation the fingerprint path already had.
- **Piecewise offset correction for tracks cut differently.** Broadcast and streaming dubs are often edited differently from the disc — an ad break trimmed out, a reel change — which moves the offset by a fixed amount partway through and leaves it there. A single delay cannot follow that, and neither can a straight line. The offset is now modelled as a series of regions: genuine steps are detected in the measured windows, each boundary is then located by bisecting the audio itself (whichever candidate offset aligns the tracks better at a moment says which side of the edit that moment is on), and the track is spliced with a short fade across every join. On a two-hour Turkish dub against its BluRay remux the worst error fell from 660 ms to 63 ms, and windows exceeding 45 ms from 20/27 to 1/28. Splicing requires a step of at least 40 ms, two minutes and four convincing windows on each side, a jump at least 4x the scatter the windows already show, and a clearly better fit than a straight line — that last test is what stops a smooth drift being chopped into a staircase. Toggle with **Correct offset jumps from different edits**.
- `AnalysisResult.offset_regions`, `has_step_discontinuity`, `step_span_ms`; `SyncRequest.correct_steps`; `SyncOutcome.offset_regions_applied`; `FFmpegWrapper.build_piecewise_filter()`.
- **Progressive drift correction.** Two encodes of the same soundtrack often run at slightly different clock rates, and a constant offset cannot fix that — aligning the middle leaves both ends wrong. The analyzer already measured the slope but nothing acted on it. The fitted line's slope is now cancelled with a tempo correction, and the constant offset is taken from the line's intercept rather than the median (which describes the middle of the content). On a five-minute clip with 0.1 % drift the residual error fell from 228 ms of swing to 7 ms. The correction is skipped, with a log line, when the fit is weak (R² < 0.80), fewer than six windows validated, they span under a minute, or the slope is below 1 ms/min. Toggle it with **Correct progressive drift automatically**.
- `AnalysisResult` gains `drift_intercept_ms`, `drift_r2`, `drift_span_sec` and `has_drift_measurement`; the thresholds that decide whether to act on a drift live in `SyncConfig` rather than being split between the model and the config.
- `SyncRequest.correct_drift`; `SyncOutcome.drift_applied_ms_per_min`.

#### Changed
- **Six synchronization modes became three.** Five of the six produced byte-identical output: the distinguishing filters were either never added or were no-ops such as `rubberband=tempo=1.0`, which re-encoded the audio for no benefit. The surviving modes are Precise offset, Repair timestamps (`aresample=async=1`, for inputs whose own timestamps are broken) and Rubber Band stretch (now used as the drift-correction engine, and only inserted when there is drift to correct). Code naming a retired mode (`ATEMPO`, `APAD`, `ASYNCTS`) keeps working through `config.sync_mode_from_name()`, which maps each to the surviving mode that reproduces its old behaviour.
- The six near-duplicate command builders collapsed into one composable `build_sync_command()`.
- **The window no longer opens taller than the screen.** The single-column layout needed about 1460 px of height, so on a 1080p display the primary action always sat below the fold behind a scrollbar that was #2a2a3a on a #0f0f13 trough — effectively invisible. Panels are now laid out in two columns, the initial size is derived from the content and clamped to the work area, and the scrollbar is visible when it is needed.
- The action bar is a single row instead of three stacked full-width buttons that consumed a quarter of the window; Cancel appears only while there is something to cancel.
- The detected delay is presented as a measurement readout with its confidence and drift, rather than as one of four identical metadata rows.
- Interface text uses the platform UI face (Segoe UI / SF Pro / DejaVu Sans); the monospace face is reserved for measurements, paths and the log, instead of Courier New everywhere.
- File pickers put the name and the button on one row, halving each zone's height and removing the fixed 54-character width that was stretching the window.

### [2.3.0] - 2026-08-02

#### Security
- **External tools are no longer resolved from the working directory.** On Windows `shutil.which()` searches the current directory before PATH, so launching the app from a folder containing a planted `ffmpeg.exe` or `ffprobe.exe` ran that binary. Tool lookup now only considers absolute PATH entries, and relative PATH entries are ignored as well.
- Deew runtime probes write to a per-user directory instead of the installation tree, which is read-only for system-wide installs and ephemeral inside a PyInstaller bundle.
- Media paths are made absolute before reaching FFmpeg, so a relative path such as `sample:track.wav` can no longer be interpreted as an FFmpeg protocol specifier.

#### Added
- Progress bar now reports the current stage and completion percentage.
- `DropZone.show_status()` / `clear_selection()` for callers that need to change the zone caption.

#### Changed
- Tool locations and the FFmpeg/FFprobe availability probe are memoized, removing four process spawns per synchronization run; both are invalidated when tool paths change.
- The Deew availability badge and the Start button's tool checks run on worker threads, so the window no longer freezes for up to 15 seconds at startup or on the first run.
- Analysis reads the decoded PCM once instead of twice by deriving the peak from a running min/max — the result is bit-identical.
- qaac encoding scales its timeout with the input size instead of always aborting at 600 seconds.

#### Fixed
- Background probes that finish after the window closes no longer call into a destroyed Tcl interpreter; pending timers are cancelled on exit.
- The mouse wheel now scrolls the log box when the pointer is over it, instead of always scrolling the page.
- FLAC output snaps unsupported bit depths to the nearest supported one rather than silently ignoring the setting.

### [2.2.6] - 2026-07-21

#### Added
- Testable `SyncPipeline` orchestration with atomic output commits and synchronized WAV recovery on encoding failure
- Automated unit, integration, GUI smoke, lint, coverage, dependency, and Windows build checks

#### Changed
- FFmpeg and FFprobe paths are now validated by actually starting each tool
- Synchronized audio keeps its own sample rate unless 48 kHz conversion is explicitly requested
- Fixed offsets use exact delay/trim behavior in every direction; the compatibility `atempo` mode no longer distorts the first ten seconds

#### Fixed
- Existing outputs and input files are protected from failed, cancelled, or unsafe writes
- FFprobe, qaac, Deew, and final encoding failures can no longer be reported as successful
- Tool-path settings are committed atomically and remain unchanged in memory after a disk-write failure

### [2.2.5] - 2026-04-13

#### Changed
- **Fingerprint anchor-based sync refinement**: fingerprint anchors now guide a local offset-map refinement pass instead of relying on a single coarse lag guess
- **Stronger final lag selection**: weak windows no longer drag the final sync point away from the dominant lag cluster
- **Lower-RAM analysis path**: the GUI analysis flow now runs against disk-backed mono PCM buffers rather than loading full decoded arrays into memory
- **More stable difficult-match handling**: final sync-point selection is now less sensitive to weak outlier windows

### [2.2.4] - 2026-04-13

#### Changed
- **Lighter analysis startup**: analyzer imports are deferred so app startup avoids loading heavy analysis code too early
- **Shared process runner**: FFmpeg, qaac, and Deew jobs now use a common cancellation-aware subprocess path
- **Lower analysis overhead**: mono decode and analyzer preparation now avoid some unnecessary copies and repeated work
- **Deew runtime preflight**: the app checks whether Deew can actually start before launching a Deew encode job
- **Build config cleanup**: PyInstaller build settings are now centralized in `build_support.py`

### [2.2.3] - 2026-04-07

#### Changed
- **Encoding pipeline separation**: the Deew pipeline is now Deew-only and no longer exposes an FFmpeg encoder switch
- **FFmpeg AC3/EAC3 outputs moved**: AC3 and EAC3 output options now live under the FFmpeg pipeline where they belong
- **FFmpeg surround controls**: AC3/EAC3 encoding in the FFmpeg pipeline now includes bitrate and channel layout controls

### [2.2.2] - 2026-04-05

#### Fixed
- **`atempo` micro-offset synchronization**: tiny positive and negative delays now converge correctly instead of drifting further away
- **FPS conversion indicator text**: slowdown/speedup direction labels now match the actual `atempo` behavior
- **Sync mode naming**: UI and docs now reflect the real filters and behavior used by each mode

#### Changed
- **Deew-only wording cleanup**: removed `Dolby` / `DEE` mentions from the app text and public docs to reduce branding/licensing risk

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
- FPS conversion support (23.976 <-> 24 <-> 25)
- Bilingual UI (Turkish / English) with runtime language switching
- Dark-themed modern tkinter interface
- Preserves original audio quality (bit depth, sample rate, channels)
- Pre-built Windows EXE distribution
- MIT License

---

## Turkce

### [2.4.1] - 2026-08-06

Bir arayuz denetimi. v2.4.0 pencereyi bastan kurdu ve birkac panel ekledi;
ceviri tablosu bunlara yetisemedi. Bu surum o bosluğu kapatiyor ve bosluk yeniden
acildiginda basarisiz olacak testler ekliyor.

#### Duzeltildi
- **Bes acilir menu, secenegin adi yerine ic degeri gosteriyordu.** DRC profili `music_light`, qaac modu `--tvbr`, deew formati `ddp`, FFmpeg formati `aac`, kodlama yontemi ise `none` yaziyordu. Tk bir `OptionMenu`'nun buton yazisini degiskenine baglar; bu yuzden ad gosterebilmek icin butona kendi goruntu degiskeni verildi, orijinal degisken her cagiranin okudugu degeri tutmaya devam ediyor — enum'lar bu adlari en bastan tasiyordu, kodlama yontemi secicisi (deger, etiket) ciftlerinden bir liste bile kuruyor sonra etiketleri atiyordu. Yaziyi bir `trace` suruyor, boylece koddan atanan bir deger de dogru etiketi gosteriyor; bazi etiketler cevrildigi icin menuler dil degisiminde yeniden kuruluyor.
- **Sureç, Turkce log kutusuna Ingilizce yaziyordu.** On alti ilerleme mesajinin tamami ve deew'inkiler ceviri tablosunu atliyordu; dil degistirmek, akan aciklamalari yazildiklari dilde birakiyordu. Ikisi de artik `t()` uzerinden geciyor.
- **Eksik bir anahtar, anahtarin kendisi olarak goruntuleniyordu.** `t()` ceviri bulamazsa argumanini dondurur; bu yuzden tanimsiz bir anahtar dogrudan buton yazisi oluyordu — bir buton `cancel` yaziyordu. Kullaniciya ulasip da tanimsiz olan anahtarlar tanimlandi ve artik tabloda olmayan bir anahtarla yapilan her `t()` cagrisinda bir test basarisiz oluyor.
- **31 ceviri girdisinin artik bir kullanimi yoktu.** Cogu, sekil degistiren ozelliklerden arta kalmisti; ama ayni denetim bunun tersini de buldu — deew'in baslangic ve bitis mesajlari oluydu, cunku kod onlarin yerine sessizce sabit Ingilizce metin koymustu. Bu, biri dili degistirene kadar gorunmez ve kontrol edene kadar zararsiz olu agirliga birebir benzer. Olu girdiler kaldirildi ve bir girdi artik hicbir yerden erisilmez hale geldiginde test basarisiz oluyor.
- **AC3/E-AC3 kodlama ozeti komut satiri yaziyordu.** Loga, geçici dosya adiyla biten eksik bir ffmpeg cagrisi dusuyordu; diger formatlar `AAC 192 kbps` diyor, bu da artik `AC3 448 kbps` diyor.

#### Eklendi
- `tests/test_i18n_completeness.py` — her anahtar iki dilde de var mi, kodda kullanilan her anahtar tanimli mi, tanimli her anahtara erisiliyor mu, yer tutucular diller arasinda uyusuyor mu, her metin bicimlendirilebiliyor mu ve kullaniciya ulasan hicbir metin tabloyu atliyor mu.
- Acilir menuler icin iki GUI testi: buton yazisi, koddan yapilan bir atamadan sonra bile deger degil etiket oluyor ve dil degisiminde secimi kaybetmeden onu izliyor.

#### Dogrulandi
- On iki kodlama hattinin tamami uctan uca yeniden calistirildi (FFmpeg AAC / FLAC-16 / FLAC-24 / Opus / AC3 / E-AC3 / 1-kanal, deew DD ve DDP, qaac TVBR, duz WAV): dogru kodek, kanal sayisi ve sure, kalinti gecikme −7 ile −13 ms.
- Iki dil de widget widget tarandi — ekrana ne ham ceviri anahtari ne de ham ic deger ulasiyor.
- Yerlesim olculeri v2.4.0 ile ayni (1236 px icerik genisligi; panel basina yukseklikler birebir).

### [2.4.0] - 2026-08-05

Sekiz uzun metraj film ciftiyle (Turkce dublajlar ile BluRay/UHD remux'lari)
uctan uca dogrulandi; her olcum, analizorle hicbir kod paylasmayan bagimsiz bir
korelasyonla capraz kontrol edildi.

#### Duzeltildi
- **Parcanin zaten sahip oldugu kanal duzenini secmek deew kodlamasini oldururdu.** deew `-dm` bayragini yalnizca hedef kanal sayisi girdiden *az* ise kabul ediyor; bu yuzden stereo bir parcaya stereo downmix istemek, senkronizasyon zaten bittikten sonra "downmix value has to be lower than the number of input channels" hatasiyla tum isi cope atiyordu. Stereo bir kaynak icin "Stereo" secmek "dokunma" demenin makul bir yolu oldugundan, bayrak artik atlaniyor ve loga nedeni yaziliyor.
- **Saklanan WAV, boyutu soylenmeden diskte birakiliyordu.** Kodlama basarisiz olursa senkronize ses bilincli olarak saklanir; boylece analiz tekrarlanmaz. Ancak bu dosya sikistirilmamis ve film uzunlugundadir — uzun metrajda birkac GB. Mesaj artik boyutu bildiriyor ve isi bitince silinmesini soyluyor. Baska hicbir seyin kalmadigi dogrulandi: basarili bir calisma, FPS donusumu, deew veya FFmpeg kodlamasi ve iptal — her biri cikti klasorunde ve sistem gecici dizininde sifir bayt birakiyor.
- **Tek bir yuksek skorlu pencere tum filmin gecikmesini belirleyebiliyordu.** Korelasyon skoru tepe/gurultu tabani oranidir; bu yuzden iki sessizlik parcasini (jenerik, makara bosluğu) hizalayan bir pencere, diyalog tasiyan pencerelerden cok daha yuksek skor aliyor ve dogrusal agirliklandirma onu tek basina galip getiriyordu. 138 dakikalik iki dilli bir ciftte 27 pencerenin 23'u -9490 ms'de birlesiyordu ve *hepsi* iki aykiri deger ugruna atildi — filmin yaklasik iki saatini 135 ms kaydirarak, dudak senkronunun bozuk okundugu esigin cok otesine. Pencere agirliklari artik medyanin 4 katiyla sinirli; bu, siralamayi korurken tek bir pencerenin tutarli bir cogunlugu ezmesini imkansiz kiliyor. Ayni ciftte olculdu: bildirilen gecikme -9620,0 ms'den -9498,6 ms'ye, tutulan pencere 2/27'den 49/71'e cikti.
- Ilerleme yuzdesi Turkce `%42` bicimiyle sabit kodlanmisti ve Ingilizce arayuze sizıyordu; artik etkin dile uyuyor.
- Iyilestirme gecisi pencere ekleyince `used_segments`, `total_segments`'i asabiliyordu; arayuz "63/12" gibi imkansiz sayilar bildiriyordu.

#### Eklendi
- **Tespit edilen kare hizi uyusmazligi sorulmadan duzeltiliyor.** Yalnizca tespit etmek, kullaniciyi logu fark edip FPS panelini acana ve tum isi bastan calistirana kadar bozuk bir dosyayla birakiyordu. Sureç artik kendisi donusturup yeniden analiz ediyor, sonucu ise yalnizca dogrulanan pencereler oncekinden daha uyumlu cikarsa sakliyor — boylece yanlis bir tahmin dogru bir cifti bozamiyor. 132 dakikalik ciftte bu, varsayilan ayarlarla alinan sonucu **4,0 s hatadan 352 ms'ye** indirdi ve 45 ms'yi asan pencere sayisini 11/11'den 4/12'ye dusurdu; kullanicidan hicbir sey istenmeden. Ikinci gecis yalnizca gercekten bir uyusmazlik bulundugunda calisiyor. **Kare hizi uyusmazligini kendiliginden bul ve duzelt** ile kapatilir.
- **Kare hizi uyusmazliklari artik katlanilmiyor, teshis ediliyor.** Yanlis hizda hazirlanmis bir dublaj sabit oranli bir hiz hatasidir; arac bunu artik dogrudan siniyor: kaba oznitelik akisi standart oranlarin her biriyle yeniden orneklenip skorlaniyor. Boylece segment aramasinin olcemeyecegi kadar buyuk bir uyusmazlik bile bulunuyor. Sekiz gercek film ciftinde dogrulandi — uyusmazligi olan ikisini adlandirdi (her iki yonde 23.976↔24), diger altisinda sessiz kaldi.
- **deew, UTF-8 olmayan bir yerel ayarda oldugunde okunabilir bir aciklama.** deew kodlamadan once `rich` ile bir logo ciziyor; Windows'ta cocuk surec sistemin kod sayfasini miras aliyor ve Turkce cp1254 — ile logonun blok karakterlerini temsil edemeyen her kod sayfasi — icin Python traceback'i ile ve hicbir cikti uretmeden cikiyor. `PYTHONIOENCODING`, `PYTHONUTF8`, `TERM` ve `chcp 65001` tek tek denendi, hicbiri degistirmiyor; bu yuzden cokme artik taniniyor ve yerine sorunu cozen tek satir (`logo = 0`) ile duzenlenecek yapilandirma yollari gosteriliyor.
- **Arac artik kendi cevabina guvenilmedigini soyluyor.** Yuksek bir guven skoru yalnizca her pencerenin bir seye ikna edici bicimde eslestigini soyler; pencerelerin *birbiriyle* uyusup uyusmadigi hakkinda hicbir sey soylemez — oysa tek bir gecikmenin tum filmde gecerli olup olmayacagini belirleyen budur. `AnalysisResult.windows_disagree_ms` bu ayrismayi bildiriyor; 100 ms'yi asinca log uyariyor ve okuma skordan bagimsiz "zayif" isaretleniyor.
- **Arama penceresinden daha fazla kayan kaynaklar icin kaba drift kancasi.** Segment dogrulamasi tek bir kaba gecikmenin `local_search_sec` cevresinde ariyor; iki kodlama farkli saat hizlarinda calistiginda uzun metrajin cogu bu pencerenin disina dusup hic dogrulanmiyordu. Ilk ve son ucte birlik dilimler artik ayri korele ediliyor ve arama penceresinden fazla ayrisirlarsa bir cift capa olarak besleniyor.
- **Farkli kurgulanmis parcalar icin parcali ofset duzeltmesi.** Yayin ve dijital platform dublajlari cogu zaman diskten farkli kurgulanir — cikarilmis bir reklam arasi, makara degisimi — ve bu, ofseti filmin ortasinda sabit bir miktar kaydirip orada birakir. Ne tek bir gecikme ne de bir dogru bunu izleyebilir. Ofset artik bir dizi bolge olarak modelleniyor: olculen pencerelerde gercek basamaklar araniyor, her sinir sesin kendisinde ikili aramayla yerine oturtuluyor ve parca her ek yerine kisa bir sonumleme uygulanarak bolunuyor. Iki saatlik bir Turkce dublajda en kotu hata 660 ms'den 63 ms'ye, 45 ms'yi asan pencere sayisi 20/27'den 1/28'e dustu. **Kurgu farkindan dogan ofset sicramalarini duzelt** ile kapatilir.
- **Ilerleyen drift duzeltmesi.** Ayni ses bandinin iki kodlamasi cogu zaman hafifce farkli saat hizlariyla ilerler; sabit bir ofset bunu duzeltemez — ortayi hizalamak iki ucu da yanlis birakir. Analizor egimi zaten olcuyordu ama hicbir sey onu kullanmiyordu. Uydurulan dogrunun egimi artik bir tempo duzeltmesiyle gideriliyor ve sabit ofset medyan yerine dogrunun kesisiminden aliniyor. %0,1 drift iceren bes dakikalik bir klipte kalinti hata 228 ms salinimdan 7 ms'ye dustu. **Zaman kaymasini (drift) otomatik duzelt** ile kapatilir.

#### Degistirildi
- **Alti senkronizasyon modu uce indi.** Altisindan besi bayt bayt ayni ciktiyi uretiyordu: ayirt edici filtreler ya hic eklenmiyor ya da `rubberband=tempo=1.0` gibi sesi bosuna yeniden kodlayan islevsiz asamalardi. Hayatta kalan modlar: Kesin ofset, Zaman damgasi onarimi (`aresample=async=1`) ve Rubber Band germe (artik drift duzeltme motoru olarak ve yalnizca duzeltilecek bir drift varken devrede). Emekliye ayrilan adlari (`ATEMPO`, `APAD`, `ASYNCTS`) kullanan kodlar `config.sync_mode_from_name()` uzerinden calismaya devam eder.
- **Pencere artik ekrandan uzun acilmiyor.** Tek sutunlu duzen yaklasik 1460 piksel yukseklik gerektiriyordu; 1080p bir ekranda asil eylem her zaman kivrimin altinda, #0f0f13 zemin uzerinde #2a2a3a olan — yani pratikte gorunmez — bir kaydirma cubugunun arkasinda kaliyordu. Paneller artik iki sutuna yerlesiyor, baslangic boyutu icerikten turetilip calisma alanina sigdiriliyor ve kaydirma cubugu gerektiginde gorunur oluyor.
- Eylem cubugu, pencerenin dortte birini yiyen uc yigilmis tam genislikte dugme yerine tek satir; Iptal yalnizca iptal edilecek bir sey varken goruniyor.
- Tespit edilen gecikme, dort ayni meta veri satirindan biri yerine guven ve drift bilgisiyle birlikte bir olcum ekrani olarak sunuluyor.
- Arayuz metni platformun yerel arayuz fontunu kullaniyor (Segoe UI / SF Pro / DejaVu Sans); esaralikli font her yerde Courier New yerine olcumler, yollar ve log icin ayrildi.
- Dosya seciciler ad ve dugmeyi tek satira aliyor; her alanin yuksekligi yariya indi ve pencereyi geren sabit 54 karakterlik genislik kalkti.

### [2.3.0] - 2026-08-02

#### Guvenlik
- **Dis araclar artik calisma dizininden cozulmuyor.** Windows'ta `shutil.which()` PATH'ten once bulundugu dizine bakiyor; bu yuzden icinde sahte bir `ffmpeg.exe` veya `ffprobe.exe` bulunan bir klasorden baslatilan uygulama o dosyayi calistiriyordu. Arac aramasi artik yalnizca mutlak PATH girdilerini dikkate aliyor, goreli PATH girdileri de yok sayiliyor.
- Deew calisma zamani denetimleri kurulum dizini yerine kullaniciya ozel bir dizine yaziyor; kurulum dizini sistem geneli kurulumlarda salt okunur, PyInstaller paketinde ise geciciydi.
- Medya yollari FFmpeg'e ulasmadan once mutlak hale getiriliyor; boylece `sample:track.wav` gibi goreli bir yol FFmpeg protokol oneki olarak yorumlanamiyor.

#### Eklenenler
- Ilerleme cubugu artik mevcut asamayi ve tamamlanma yuzdesini gosteriyor.
- Bolge basligini degistirmesi gereken cagiranlar icin `DropZone.show_status()` / `clear_selection()`.

#### Degisenler
- Arac konumlari ve FFmpeg/FFprobe erisilebilirlik denetimi onbellege aliniyor; her senkronizasyon calistirmasindan dort surec baslatma kalkiyor. Arac yollari degisince ikisi de gecersiz kiliniyor.
- Deew durum rozeti ve Baslat dugmesinin arac denetimleri worker thread'lerde calisiyor; pencere artik acilista veya ilk calistirmada 15 saniyeye kadar donmuyor.
- Analiz, tepe degerini calisan min/max uzerinden turetip decode edilmis PCM'i iki kez yerine bir kez okuyor — sonuc bit duzeyinde ayni.
- qaac kodlamasi her zaman 600 saniyede iptal etmek yerine zaman asimini girdi boyutuna gore olcekliyor.

#### Duzeltilenler
- Pencere kapandiktan sonra biten arka plan denetimleri artik yok edilmis Tcl yorumlayicisina cagri yapmiyor; bekleyen zamanlayicilar cikista iptal ediliyor.
- Fare tekerlegi, imlec log kutusunun uzerindeyken sayfayi degil log kutusunu kaydiriyor.
- FLAC ciktisi desteklenmeyen bit derinliklerini sessizce yok saymak yerine en yakin desteklenen degere yuvarliyor.

### [2.2.6] - 2026-07-21

#### Eklenenler
- Atomik cikti tamamlama ve kodlama hatasinda senkron WAV kurtarma destekli, test edilebilir `SyncPipeline` is akisi
- Otomatik birim, entegrasyon, GUI smoke, lint, coverage, bagimlilik ve Windows build kontrolleri

#### Degisenler
- FFmpeg ve FFprobe yollari artik her araci gercekten baslatarak dogrulaniyor
- Senkronize edilen ses, 48 kHz donusumu acikca istenmedikce kendi ornekleme oranini koruyor
- Sabit ofsetler iki yonde de kesin gecikme/kirpma ile uygulaniyor; geriye uyumlu `atempo` modu ilk on saniyeyi artik bozmuyor

#### Duzeltilenler
- Mevcut ciktilar ve girdi dosyalari basarisiz, iptal edilen veya guvensiz yazma islemlerinden korunuyor
- FFprobe, qaac, Deew ve son kodlama hatalari artik basarili olarak gosterilemiyor
- Arac yolu ayarlari atomik kaydediliyor; disk yazma hatasinda bellekteki ayarlar degismiyor

### [2.2.5] - 2026-04-13

#### Degisenler
- **Fingerprint anchor tabanli senkron refinement**: fingerprint anchor'lar artik tek bir kaba lag tahmini yerine yerel offset-haritasi refinement gecisine yol gosteriyor
- **Daha guclu final lag secimi**: zayif pencereler artik nihai senkron noktasini baskin lag kumesinden uzaklastiramiyor
- **Daha dusuk RAM kullanan analiz yolu**: GUI analiz akisi tam decode edilmis dizileri bellekte tutmak yerine diskteki mono PCM tamponlari uzerinden calisiyor
- **Zor eslesmelerde daha kararlı secim**: nihai senkron noktasi secimi artik zayif aykiri pencerelere daha az duyarlı

### [2.2.4] - 2026-04-13

#### Degisenler
- **Daha hafif analiz acilisi**: analyzer importlari ertelenerek uygulama acilisinda agir analiz kodlarinin erkenden yuklenmesi engellendi
- **Ortak process runner**: FFmpeg, qaac ve Deew isleri artik iptal farkindalikli ortak bir subprocess yolunu kullaniyor
- **Daha dusuk analiz yuku**: mono decode ve analyzer hazirligi sirasinda gereksiz kopyalar ve tekrar eden isler azaltildi
- **Deew runtime on kontrolu**: uygulama, Deew encode isi baslamadan once Deew'in gercekten calisabildigini denetliyor
- **Build ayari temizligi**: PyInstaller derleme ayarlari `build_support.py` altinda merkezilestirildi

### [2.2.3] - 2026-04-07

#### Degisenler
- **Kodlama pipeline ayrimi**: Deew pipeline artik yalnizca Deew kullaniyor ve FFmpeg encoder secimi gostermiyor
- **FFmpeg AC3/EAC3 ciktilari tasindi**: AC3 ve EAC3 cikti secenekleri artik dogru yerde, FFmpeg pipeline altinda bulunuyor
- **FFmpeg surround kontrolleri**: FFmpeg pipeline icindeki AC3/EAC3 kodlamasina bitrate ve kanal duzeni kontrolleri eklendi

### [2.2.2] - 2026-04-05

#### Duzeltilenler
- **`atempo` kucuk ofset senkronizasyonu**: kucuk pozitif ve negatif gecikmeler artik ters yone kaymak yerine dogru sekilde sifira yaklasiyor
- **FPS donusumu gosterge metni**: yavaslatma/hizlandirma etiketleri artik gercek `atempo` davranisi ile uyumlu
- **Senkron mod isimleri**: UI ve dokumantasyon, her modun gercekte kullandigi filtre ve davranisla uyumlu hale getirildi

#### Degisenler
- **Yalnizca Deew odakli metin temizligi**: uygulama metinlerinden ve dokumantasyondan `Dolby` / `DEE` ifadeleri kaldirilarak marka/lisans riski azaltildi

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

[Unreleased]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.6...HEAD
[2.2.6]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.5...v2.2.6
[2.2.5]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.4...v2.2.5
[2.2.4]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.3...v2.2.4
[2.2.3]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.2...v2.2.3
[2.2.2]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/blast1see/AudioSyncTool/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/blast1see/AudioSyncTool/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/blast1see/AudioSyncTool/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/blast1see/AudioSyncTool/releases/tag/v2.0.0

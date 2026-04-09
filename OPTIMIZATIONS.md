### 1) Optimization Summary

- Current optimization health is mixed: the branch is functionally improving, but the runtime path is still dominated by full-file decode plus full-array DSP, and the Windows packaging path is significantly oversized for the amount of application code being shipped.
- Top 3 highest-impact improvements:
  - Replace full-buffer, full-duration analysis with bounded or progressive windowed analysis.
  - Unify external process execution so `ffmpeg`, `deew`, and `qaac` all support the same cancellation, timeout, and cleanup behavior.
  - Rebuild the executable from a slim CPython virtual environment and simplify PyInstaller inputs to reduce package size and startup cost.
- Biggest risk if no changes are made: very large `thd`, `dtshd`, and container-backed jobs will continue to behave like user-triggerable resource spikes, with high latency, high peak memory, and encode phases that can remain effectively uninterruptible once they leave the FFmpeg path.

### 2) Findings (Prioritized)

#### Finding 1
- **Title:** Full-buffer PCM decode plus float64 DSP amplifies memory usage on long-form audio
- **Category:** Memory
- **Severity:** Critical
- **Impact:** Peak RSS, long-job stability, large-file success rate, and analysis latency
- **Evidence:** `audio_sync/core/ffmpeg_wrapper.py:292-341` decodes entire mono PCM into `stdout`, then copies it into NumPy. `audio_sync/core/analyzer.py:167-200` converts input to `float64`, and `audio_sync/core/analyzer.py:123-149` builds filtered full-length arrays plus coarse/fine feature vectors. Measured evidence on the current branch: `decode_mono_pcm()` took about `62.1s` on the sample `.thd` and about `86.5s` on the sample `.dtshd`. On the sample `.thd`, analyzer RSS increased from about `164 MB` to about `442 MB` during analysis.
- **Why it's inefficient:** The pipeline keeps multiple full-length representations of the same signal in memory: raw PCM bytes, copied `int16`, normalized `float64`, filtered arrays, and derived feature arrays. The `float64` conversion alone doubles memory versus `float32`, and full-length filtering/convolution scales poorly for multi-hour content.
- **Recommended fix:** Move analysis to bounded windows and progressive feature extraction. Keep analysis buffers in `float32` unless a specific numeric instability is proven. If full-buffer decode is still needed as a fallback, write PCM to a temp raw file or memory map instead of holding Python byte strings plus copied arrays in memory.
- **Tradeoffs / Risks:** Chunked DSP and windowed correlation are more complex than the current straightforward full-array approach. Accuracy on low-energy or drift-heavy content must be verified against the current baseline before making it the default.
- **Expected impact estimate:** Peak analysis memory reduction of roughly `2x-4x`; materially lower OOM risk on large files; likely `20-50%` lower CPU time in the common large-file path once redundant full-array work is removed.
- **Removal Safety:** Needs Verification
- **Reuse Scope:** Service-wide

#### Finding 2
- **Title:** The analysis algorithm still processes full program duration even though it only needs sparse evidence
- **Category:** Algorithm
- **Severity:** High
- **Impact:** End-to-end latency, throughput for batch work, and user wait time
- **Evidence:** The UI only needs one delay result, but `audio_sync/ui/app.py:1942-1973` and `audio_sync/ui/app.py:2283-2308` decode both full inputs before calling analyzer. Inside analyzer, `audio_sync/core/analyzer.py:115-162` computes full filtered signals before segment validation. The existing `skip_intro_sec`, `segment_count`, and segment validation logic limit only the decision stage, not the ingest cost.
- **Why it's inefficient:** The pipeline pays the full decode and full-feature cost for the entire program even when a coarse delay can often be established from a small subset of the signal. This makes long-form content behave as if the whole file is hot-path data.
- **Recommended fix:** Split analysis into two explicit stages:
  - coarse scan on short extracted windows using `ffmpeg -ss/-t`
  - fine validation only around the best candidate offsets
  Add an early-stop rule once confidence crosses a threshold and drift remains below a defined tolerance.
- **Tradeoffs / Risks:** Progressive analysis can miss difficult intros or sparse dialogue if the sampling policy is too aggressive. The fallback path should remain available for edge cases.
- **Expected impact estimate:** Likely `40-80%` shorter analysis wall-clock time on long movie-length inputs, with the highest gains on TrueHD and DTS-HD sources.
- **Removal Safety:** Needs Verification
- **Reuse Scope:** Module

#### Finding 3
- **Title:** Cancellation and timeout behavior is inconsistent across FFmpeg, deew, and qaac
- **Category:** Reliability
- **Severity:** High
- **Impact:** User control, stuck-job recovery, and cleanup reliability
- **Evidence:** `audio_sync/core/ffmpeg_wrapper.py:1001-1145` implements cancellable polling for FFmpeg-backed commands. In contrast, `audio_sync/core/deew_encoder.py:273-305` and `audio_sync/core/encoder.py:104-118` still use plain `subprocess.run(..., timeout=600)` with no shared cancellation path. `audio_sync/ui/app.py:2350-2469` checks cancellation before these encodes start, but not while they are running.
- **Why it's inefficient:** Long encode jobs consume compute even after the user has already requested cancellation. This wastes CPU time, extends lock contention on output paths, and forces the UI into uneven behavior depending on which backend is active.
- **Recommended fix:** Extract a shared external-process runner that supports:
  - polling cancellation
  - consistent timeout handling
  - process-tree termination
  - standardized stdout/stderr capture
  Use it in FFmpeg, `deew`, and `qaac`.
- **Tradeoffs / Risks:** Unifying process handling changes error timing and message content. Cross-platform termination behavior must be tested carefully on Windows.
- **Expected impact estimate:** High qualitative reliability improvement; significant reduction in wasted compute for canceled encode jobs; much lower chance of "hung" long-running external processes from the user's perspective.
- **Removal Safety:** Likely Safe
- **Reuse Scope:** Service-wide

#### Finding 4
- **Title:** Analyze-only and full-process orchestration duplicate the same expensive preparation flow
- **Category:** Reliability
- **Severity:** Medium
- **Impact:** Maintenance cost, bug surface area, and future optimization velocity
- **Evidence:** `audio_sync/ui/app.py:1881-2038` and `audio_sync/ui/app.py:2219-2504` both perform nearly the same sequence: probe, optional FPS conversion, mono decode, timing logs, analysis, cancellation checks, and cleanup. The branches differ only after analysis, when one stops and the other continues to sync and encode.
- **Why it's inefficient:** Duplicate orchestration means every performance or reliability improvement must be applied twice. This increases drift risk and makes it harder to land more ambitious optimizations such as progressive analysis, caching, or shared telemetry.
- **Recommended fix:** Extract a single analysis-preparation routine that returns:
  - effective sync path
  - probed metadata
  - decoded PCM or analysis result
  - cleanup handles
  Then let analyze-only and full-process flows consume the same object. This is a clear `Reuse Opportunity`.
- **Tradeoffs / Risks:** Refactoring thread/UI code can accidentally change progress ordering or cleanup behavior. It should be covered by smoke tests and a small cancellation regression test.
- **Expected impact estimate:** Low direct runtime gain, but medium-to-high engineering ROI because it removes drift and shortens future optimization work.
- **Removal Safety:** Likely Safe
- **Reuse Scope:** Module

#### Finding 5
- **Title:** Packaging from the current environment produces an oversized executable and bloated release artifacts
- **Category:** Build
- **Severity:** High
- **Impact:** Download size, startup time, CI build time, local storage cost, and release hygiene
- **Evidence:** Current artifacts show `dist/AudioSyncTool.exe` at about `194 MB`, while release zips in `dist/` range from about `192 MB` to `424 MB`. Local `dist/` totals about `2.04 GB`, and `build/` totals about `208 MB`. `setup.py:26-93` drives PyInstaller from `sys.executable`, and this workspace is clearly using an Anaconda interpreter. `AudioSyncTool.spec:4-15` also carries a long manual `hiddenimports` list and `optimize=0`. `build/AudioSyncTool/warn-AudioSyncTool.txt` shows very broad optional import reach from the current environment.
- **Why it's inefficient:** Building from a fat base environment causes PyInstaller analysis to traverse far more packages than the app logically needs. The current approach also duplicates build configuration between `setup.py` and `AudioSyncTool.spec`, which encourages drift rather than minimal packaging.
- **Recommended fix:** Build from a clean CPython virtual environment dedicated to packaging. Make one source of truth for PyInstaller configuration, prefer spec-driven packaging, and re-measure whether `onedir` is a better tradeoff than `onefile` for startup and size. Trim hidden imports to only those that are empirically required from the clean environment.
- **Tradeoffs / Risks:** A slimmer build environment may initially miss a runtime dependency that the fat environment was masking. This needs an explicit packaging smoke test on a clean machine.
- **Expected impact estimate:** Roughly `30-60%` smaller packaged output is realistic from environment cleanup alone; startup may also improve noticeably because `onefile` self-extraction and bundled payload size both shrink.
- **Removal Safety:** Needs Verification
- **Reuse Scope:** Service-wide

#### Finding 6
- **Title:** Startup path eagerly imports heavy scientific dependencies before the user does any analysis
- **Category:** Build
- **Severity:** Medium
- **Impact:** Launch latency and perceived responsiveness
- **Evidence:** `audio_sync/__main__.py:13-40` performs eager dependency checks by importing `numpy` and `scipy` before creating the UI. Measured import timing on the current branch shows `audio_sync.core.analyzer` alone costs about `747 ms` to import.
- **Why it's inefficient:** The app pays the scientific stack startup cost on every launch, including sessions where the user is only selecting files, configuring tool paths, or inspecting the UI. This front-loads heavy work before it is actually needed.
- **Recommended fix:** Defer the scientific dependency check until the first analysis or sync operation, or lazily import the analyzer module the first time it is needed. If proactive validation is still desired, perform it asynchronously after the UI is already visible.
- **Tradeoffs / Risks:** Deferred import moves dependency failures from startup to first-use. The UI must present a clear error message if the lazy import fails.
- **Expected impact estimate:** Likely `500-1000 ms` faster cold start on the current environment, plus improved perceived responsiveness because the window can appear earlier.
- **Removal Safety:** Likely Safe
- **Reuse Scope:** Local file

#### Finding 7
- **Title:** There are low-value leftovers that add maintenance and storage cost without helping runtime
- **Category:** Cost
- **Severity:** Low
- **Impact:** Repo hygiene, audit clarity, and local build/storage waste
- **Evidence:** `audio_sync/utils.py:135-164` defines `temporary_wav_files()`, but the only current matches are the helper itself and its docstring example; the active UI path no longer uses it. Build configuration is duplicated across `setup.py` and `AudioSyncTool.spec`. Local `dist/` retains multiple old release archives totaling over `2 GB`.
- **Why it's inefficient:** Dead or stale helpers keep mental overhead high and make it harder to see the real hot path. Duplicated build config encourages drift. Large leftover artifacts waste local disk and slow manual inspection.
- **Recommended fix:** Mark `temporary_wav_files()` as a `Dead Code` candidate and remove it once no external usage remains. Consolidate build config to a single source of truth. Add a release-cleanup step so local `dist/` keeps only the current build or explicitly archived versions.
- **Tradeoffs / Risks:** `temporary_wav_files()` might still be used by external callers if this package is imported outside the app. Verify public usage before removal.
- **Expected impact estimate:** Negligible runtime gain; low-but-real maintenance and storage savings; better signal-to-noise for future optimization work.
- **Removal Safety:** Needs Verification
- **Reuse Scope:** Local file

### 3) Quick Wins (Do First)

- Build the exe from a clean CPython venv instead of the current Anaconda interpreter, then re-measure `dist/AudioSyncTool.exe` and startup time.
- Defer the eager SciPy import in `audio_sync/__main__.py` so the UI can appear before analysis dependencies load.
- Create one shared subprocess runner and migrate `deew` and `qaac` onto it so cancellation and timeout behavior match FFmpeg.
- Extract shared analysis preparation from `_analyze_only()` and `_process()` before attempting deeper runtime changes.
- Mark `temporary_wav_files()` and duplicated build config as cleanup candidates so future optimization work has less drift risk.

### 4) Deeper Optimizations (Do Next)

- Redesign the analysis path around progressive windows:
  - coarse scan using short `ffmpeg -ss/-t` windows
  - fine validation only near best candidates
  - full-file fallback only when confidence stays low
- Replace full-length `float64` DSP with a memory-aware pipeline:
  - `float32` normalization
  - chunked feature extraction
  - optional memory-mapped raw PCM fallback for extreme file sizes
- Add a bounded concurrency strategy for analysis preparation:
  - allow source and sync decode overlap only when CPU and disk headroom permit
  - keep the default safe on lower-end systems
- Rework packaging into a single, testable build definition with a clean environment, then evaluate `onefile` vs `onedir` using actual startup and distribution metrics.

### 5) Validation Plan

- Benchmarks:
  - Measure `probe`, `decode`, `analyze`, `apply_sync`, and encode phases separately with `time.perf_counter()`.
  - Use the provided `.thd` and `.dtshd` files plus a synthetic delayed WAV pair as the baseline benchmark set.
  - Capture cold-start import time for `audio_sync.__main__`, `audio_sync.core.analyzer`, and full UI startup.
- Profiling strategy:
  - Use `psutil` to record RSS before decode, after decode, after analysis, and after encode.
  - Use `cProfile` or `py-spy` on analysis runs to confirm whether filtering, convolution, or normalization dominate CPU.
  - Use PyInstaller `xref` and `warn` outputs from a clean build environment to prove packaging reductions.
- Metrics to compare before/after:
  - decode seconds per file
  - analysis seconds per file
  - peak RSS
  - time-to-first-window-visible
  - exe size
  - zip size
  - cancel-to-stop latency for FFmpeg, `deew`, and `qaac`
- Test cases to ensure correctness is preserved:
  - synthetic fixed-delay WAV pair should still return the same delay within a narrow tolerance
  - real `.thd` and `.dtshd` jobs should stay within an agreed delay tolerance versus the current branch
  - cancellation should leave no partial output and should not deadlock the UI
  - packaging smoke test should run on a clean Windows machine without the build environment installed

### 6) Optimized Code / Patch (when possible)

Suggested runtime shape for bounded analysis:

```python
class AnalysisWindowPlan(NamedTuple):
    coarse_windows: list[tuple[float, float]]
    fine_windows: list[tuple[float, float]]


def analyze_progressive(src_path: str, sync_path: str, plan: AnalysisWindowPlan) -> AnalysisResult:
    coarse_candidates = []
    for start_sec, dur_sec in plan.coarse_windows:
        src_rate, src_pcm = ffmpeg.decode_window(src_path, start_sec, dur_sec)
        sync_rate, sync_pcm = ffmpeg.decode_window(sync_path, start_sec, dur_sec)
        coarse_candidates.append(analyzer.coarse_delay(src_rate, src_pcm, sync_pcm, sync_rate))

    best = select_best_candidate(coarse_candidates)
    fine_src = ffmpeg.decode_window(src_path, best.src_start, best.duration)
    fine_sync = ffmpeg.decode_window(sync_path, best.sync_start, best.duration)
    return analyzer.refine_delay(*fine_src, *fine_sync)
```

Suggested shared external-process runner for all backends:

```python
class ExternalProcessRunner:
    def run(
        self,
        cmd: list[str],
        *,
        text: bool,
        timeout: int | None,
        cancel_event: threading.Event | None,
    ) -> subprocess.CompletedProcess[str | bytes]:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            **platform_kwargs(),
        ) as process:
            return wait_with_cancel(process, cmd, timeout=timeout, cancel_event=cancel_event)
```

Suggested startup simplification:

```python
def main() -> None:
    from audio_sync.ui.app import AudioSyncApp

    app = AudioSyncApp()
    app.mainloop()


def require_analysis_dependencies() -> None:
    import numpy  # noqa: F401
    from scipy.io import wavfile  # noqa: F401
    from scipy.signal import butter, correlate, sosfiltfilt  # noqa: F401
```

Suggested packaging cleanup approach:

```python
# build.ps1 or CI step
py -3.11 -m venv .venv-build
.venv-build\\Scripts\\python -m pip install -U pip pyinstaller numpy scipy
.venv-build\\Scripts\\python -m PyInstaller AudioSyncTool.spec --clean --noconfirm
```

Suggested build-config consolidation:

```python
# setup.py should not re-declare the full hidden import/exclude matrix.
# Call the spec instead, or remove setup.py entirely in favor of one spec/CI path.
subprocess.run([sys.executable, "-m", "PyInstaller", "AudioSyncTool.spec", "--clean", "--noconfirm"])
```

# Working on Audio Sync Tool

Notes for anyone — human or agent — picking this codebase up.

## What the tool actually does

It measures the time offset between two audio tracks of the same content and
writes the second one back in sync with the first. The usual job is aligning a
dubbed track against a BluRay/UHD remux.

The offset is **not** a single number. Real material needs one of three models,
and choosing the wrong one produces a file that sounds fine for ten minutes and
then drifts:

| Model | When | Applied as |
|---|---|---|
| Constant offset | The normal case | `adelay` / `atrim` |
| Constant + linear drift | The two encodes ran at different clock rates | `atempo` + offset from the fitted line's **intercept**, not its median |
| Piecewise regions | The dub was cut differently (ad break, reel change) | `asplit` → per-region `atrim` → `concat`, with a short fade at each join |

A frame-rate mismatch is a fourth case that is better removed *before* analysis
than corrected after it — see `detect_rate_mismatch`.

## Where the logic lives

```
audio_sync/core/analyzer.py     measurement: features, correlation, drift fit,
                                step detection, rate-mismatch probe
audio_sync/core/pipeline.py     policy: which model to apply, and the gates
audio_sync/core/ffmpeg_wrapper  execution: builds one composable filter chain
audio_sync/core/models.py       results — reports measurements, never verdicts
audio_sync/config.py            every threshold, so gates are tunable in one place
```

The split matters: `AnalysisResult` says what was measured, `SyncPipeline`
decides what to do about it. If you find yourself putting a threshold in
`models.py`, it belongs in `SyncConfig` and the decision belongs in the pipeline.

## Testing it properly

**Unit tests are necessary and not sufficient.** Every serious bug found in this
codebase passed the unit tests. They were found by running real films through
the pipeline and measuring the output with an independent correlation that
shares no code with the analyzer.

```bash
python -m ruff check .
python -m pytest -m "not integration and not gui"
python -m pytest -m integration   # needs FFmpeg
python -m pytest -m gui           # xvfb-run -a ... on Linux
```

If you change anything in the measurement path, that is not enough. You need
feature-length material — a dub and its remux — and you need to check the
residual offset *across the whole runtime*, not globally. A global measurement
averages a drift to nearly zero and hides it completely.

Two failure modes to watch for when writing such a harness:

- **Sign conventions.** `delay_ms > 0` means the track runs *early* and gets
  delayed; negative means it runs late and its head is trimmed. Verify your
  measurement against a synthetic known shift before trusting it on real files.
- **False correlation peaks.** Repetitive scores (electronic, minimalist) lock
  onto the wrong period. An isolated bad window whose neighbours are clean is
  almost always the measurement, not the tool. Check the peak-to-floor ratio.

## Things that look like bugs and are not

- **The three sync modes produce identical output on a clean file.** That is
  correct. `aresample=async=1` only does something when the input's own
  timestamps are broken, and Rubber Band only engages when there is drift to
  correct. v2.3 had six modes, five of which were byte-identical; that was the
  bug, and it is fixed.
- **`windows_disagree_ms` above 100 ms downgrades a high confidence score.** A
  high score means each window matched *something* well. It says nothing about
  whether the windows agree with *each other*, and that is what decides whether
  one delay can hold across a film.
- **The preserved `.sync-fallback.wav` after an encoding failure.** Deliberate —
  synchronization already succeeded and re-analyzing a feature is expensive. The
  error message reports its size so it does not sit unnoticed.

## A trap worth not re-entering

`build_piecewise_filter` opens the source **once per region** rather than
fanning one decoder out with `asplit`. That looks wasteful and it is tempting to
"optimise" — don't.

Splitting one decoder couples the branches: `concat` drains the first piece
while the later branches are handed frames they cannot use yet, and whether that
resolves depends on the FFmpeg build. The `asplit` version ran in under a second
against a 2026 git build and **hung for over half an hour** on the FFmpeg that
ships with Ubuntu, on a CI job that normally finishes in forty seconds. The
integration test `test_each_region_reads_its_own_input` exists to catch a
regression here.

If the extra decoding ever does become a problem, the safe direction is an input
level `-ss` per region so each input only reads its own slice — not going back
to a shared decoder.

## External tools

`ffmpeg` and `ffprobe` are required; `deew` and `qaac` are optional. They are
resolved from absolute `PATH` entries only — never the working directory, so a
planted `ffmpeg.exe` next to someone's media cannot be executed. Use **Tool
Paths** for binaries outside `PATH`.

**deew on a non-UTF-8 Windows locale:** deew draws a start-up logo through
`rich`, and on any code page that cannot represent its block characters (Turkish
cp1254, Greek cp1253, …) it raises `UnicodeEncodeError` and dies before touching
the audio. Nothing outside deew changes this — `PYTHONIOENCODING`, `PYTHONUTF8`,
`TERM` and `chcp 65001` were all tested against deew 3.2.2 and none help. The
fix is `logo = 0` in deew's config; `describe_deew_failure()` recognises the
crash and says so.

## House style

Comments explain *why*, not *what*, and the reason is usually a measurement.
When a threshold or a rule exists because of something observed on real
material, say what was observed — those numbers are why the gate is where it is,
and without them the next person cannot tell a tuned constant from an arbitrary
one.

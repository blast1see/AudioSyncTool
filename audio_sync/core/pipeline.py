"""Testable orchestration for the complete audio synchronization workflow."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import numpy as np

from audio_sync.config import (
    SYNC_CONFIG,
    DeewConfig,
    DeewFormat,
    EncodingPipeline,
    FFmpegEncodeConfig,
    FFmpegOutputFormat,
    FpsConversion,
    QaacConfig,
    SyncConfig,
    SyncMode,
    match_drift_to_fps,
)
from audio_sync.core.deew_encoder import encode_wav_with_deew, resolve_deew_backend
from audio_sync.core.encoder import QaacEncoder
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper
from audio_sync.core.models import (
    AnalysisResult,
    AudioInfo,
    EncodingError,
    MatchVerdict,
    NoMatchError,
    OffsetRegion,
    OperationCancelledError,
    OutputSampleRate,
    UnsafeOutputPathError,
)
from audio_sync.i18n import t
from audio_sync.utils import validate_file

if TYPE_CHECKING:
    from audio_sync.core.analyzer import AudioAnalyzer


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int], None]


@dataclass(frozen=True)
class EncodingRequest:
    """Final encoding settings for a synchronization request."""

    pipeline: EncodingPipeline = EncodingPipeline.NONE
    ffmpeg: FFmpegEncodeConfig = FFmpegEncodeConfig()
    qaac: QaacConfig = QaacConfig()
    deew: DeewConfig = DeewConfig()
    ffmpeg_channels: int | None = None


@dataclass(frozen=True)
class SyncRequest:
    """All inputs required for one complete synchronization operation."""

    source_path: str
    sync_path: str
    output_path: str
    skip_intro_sec: float = 120.0
    total_segments: int = 12
    force_48k: bool = False
    fps_conversion: FpsConversion | None = None
    sync_mode: SyncMode = SyncMode.ADELAY_AMIX
    encoding: EncodingRequest = EncodingRequest()
    correct_drift: bool = True
    correct_steps: bool = True
    auto_fps_conversion: bool = True
    # Writing a track from a measurement the analyzer itself rejects produces a
    # file that is silently minutes out of sync and carries no trace of the
    # mistake.  The caller has to say so explicitly.
    allow_no_match: bool = False


@dataclass(frozen=True)
class SyncOutcome:
    """Successful result of a synchronization operation."""

    output_path: str
    analysis: AnalysisResult
    source_info: AudioInfo
    sync_info: AudioInfo
    output_sample_rate: OutputSampleRate
    sync_summary: str
    encoding_summary: str | None = None
    drift_applied_ms_per_min: float | None = None
    offset_regions_applied: tuple[OffsetRegion, ...] = ()
    fps_conversion_applied: FpsConversion | None = None
    # Measured on the file that was actually written, not predicted from the
    # analysis: how far it still sits from the reference, and over how many
    # independent probes.  ``None`` when the check could not run.
    verified_residual_ms: float | None = None
    verified_probes: int = 0


class SyncPipeline:
    """Coordinate probe, analysis, synchronization, encoding, and atomic commit."""

    def __init__(
        self,
        config: SyncConfig = SYNC_CONFIG,
        ffmpeg: FFmpegWrapper | None = None,
        analyzer: AudioAnalyzer | None = None,
    ) -> None:
        self._config = config
        self._ffmpeg = ffmpeg or FFmpegWrapper(config=config)
        self._analyzer = analyzer

    def run(
        self,
        request: SyncRequest,
        *,
        cancel_event: threading.Event | None = None,
        on_log: LogCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> SyncOutcome:
        """Run one request while preserving existing files until final success."""
        cancel_event = cancel_event or threading.Event()
        log = on_log or (lambda _message: None)
        progress = on_progress or (lambda _percent: None)

        request = self.normalize_request(request)
        self.validate_request(request)
        FFmpegWrapper.check_availability()
        self._check_cancelled(cancel_event)

        output_path = Path(request.output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        staged_output = self._reserve_staged_output(output_path)

        try:
            with tempfile.TemporaryDirectory(
                prefix="audiosync_work_",
                dir=output_path.parent,
            ) as work_dir_text:
                work_dir = Path(work_dir_text)
                log(t("pipe_reading_metadata"))
                progress(5)
                source_info = self._ffmpeg.probe_audio(request.source_path)
                sync_info = self._ffmpeg.probe_audio(request.sync_path)
                output_sr = OutputSampleRate.decide(
                    source_info.sample_rate,
                    sync_info.sample_rate,
                    request.force_48k,
                )
                self._check_cancelled(cancel_event)

                effective_sync = request.sync_path
                if request.fps_conversion is not None:
                    log(t("pipe_fps_applying", name=request.fps_conversion.display_name))
                    progress(15)
                    fps_path = work_dir / "fps-converted.wav"
                    self._ffmpeg.apply_fps_conversion(
                        request.sync_path,
                        str(fps_path),
                        request.fps_conversion,
                        sync_info,
                        cancel_event=cancel_event,
                    )
                    effective_sync = str(fps_path)
                    sync_info = self._ffmpeg.probe_audio(effective_sync)

                log(t("pipe_decoding"))
                progress(25)
                source_rate, source_pcm, _ = self._ffmpeg.decode_mono_pcm_to_file(
                    request.source_path,
                    cancel_event=cancel_event,
                    prefix="source-",
                    temp_dir=str(work_dir),
                )
                progress(35)
                sync_rate, sync_pcm, _ = self._ffmpeg.decode_mono_pcm_to_file(
                    effective_sync,
                    cancel_event=cancel_event,
                    prefix="sync-",
                    temp_dir=str(work_dir),
                )
                self._check_cancelled(cancel_event)

                log(t("pipe_analyzing"))
                progress(48)
                analysis = self._get_analyzer().calculate_delay_from_pcm_files(
                    source_rate,
                    source_pcm,
                    sync_pcm,
                    sync_rate=sync_rate,
                    skip_intro_sec=request.skip_intro_sec,
                    total_segments=request.total_segments,
                )
                self._check_cancelled(cancel_event)

                applied_fps = request.fps_conversion
                if applied_fps is None and request.auto_fps_conversion:
                    detected = self.suspected_fps_conversion(analysis)
                    if detected is not None:
                        # Correcting a rate mismatch afterwards is second best:
                        # by the end of a feature the two tracks are seconds
                        # apart, which is further than the segment search can
                        # follow, so the measurement degrades exactly where it
                        # matters.  Converting first removes the difference
                        # before anything tries to measure around it — worth a
                        # second analysis pass, which only happens when a
                        # mismatch was actually found.
                        log(t("pipe_fps_detected", name=detected.display_name))
                        progress(52)
                        fps_path = work_dir / "auto-fps-converted.wav"
                        self._ffmpeg.apply_fps_conversion(
                            request.sync_path,
                            str(fps_path),
                            detected,
                            sync_info,
                            cancel_event=cancel_event,
                        )
                        effective_sync = str(fps_path)
                        sync_info = self._ffmpeg.probe_audio(effective_sync)
                        sync_rate, sync_pcm, _ = self._ffmpeg.decode_mono_pcm_to_file(
                            effective_sync,
                            cancel_event=cancel_event,
                            prefix="sync-fps-",
                            temp_dir=str(work_dir),
                        )
                        retried = self._get_analyzer().calculate_delay_from_pcm_files(
                            source_rate,
                            source_pcm,
                            sync_pcm,
                            sync_rate=sync_rate,
                            skip_intro_sec=request.skip_intro_sec,
                            total_segments=request.total_segments,
                        )
                        analysis, applied_fps = self._better_analysis(
                            analysis, retried, detected, log
                        )
                        if applied_fps is None:
                            effective_sync = request.sync_path
                            sync_info = self._ffmpeg.probe_audio(effective_sync)
                        self._check_cancelled(cancel_event)

                self._report_verdict(analysis, log)
                if (
                    analysis.verdict is MatchVerdict.NO_MATCH
                    and not request.allow_no_match
                ):
                    raise NoMatchError(
                        t(
                            "err_no_match",
                            delay=analysis.delay_ms,
                            confidence=analysis.confidence,
                        )
                    )

                regions_to_apply = self.resolve_offset_regions(
                    analysis,
                    enabled=request.correct_steps,
                )
                if regions_to_apply:
                    log(t(
                        "pipe_steps_header",
                        span=analysis.step_span_ms,
                        count=len(regions_to_apply),
                    ))
                    for region in regions_to_apply:
                        start, end = region.bounds_in_minutes()
                        log(t(
                            "pipe_steps_region",
                            start=start,
                            end=end,
                            lag=region.lag_ms,
                            windows=region.window_count,
                        ))

                # A frame-rate mismatch is a fixed-ratio speed error, so it shows
                # up as a very specific slope.  Naming it turns "your audio
                # drifts" into a setting the user can pick — and the FPS path
                # removes the slide *before* analysis, which is the only way to
                # handle a mismatch too large for the segment search to follow.
                if applied_fps is None and not request.auto_fps_conversion:
                    suspected = self.suspected_fps_conversion(analysis)
                    if suspected is not None:
                        log(t(
                            "pipe_fps_suggestion", name=suspected.display_name
                        ))

                if analysis.windows_disagree_ms >= self._config.window_disagreement_warn_ms:
                    log(t(
                        "pipe_windows_disagree",
                        spread=analysis.windows_disagree_ms,
                    ))

                drift_to_apply, delay_to_apply = self.resolve_drift_correction(
                    analysis,
                    enabled=request.correct_drift and not regions_to_apply,
                    config=self._config,
                )
                if drift_to_apply is not None:
                    log(t(
                        "pipe_drift_correcting",
                        drift=drift_to_apply,
                        r2=analysis.drift_r2,
                    ))
                elif analysis.drift_ms_per_min is not None and abs(
                    analysis.drift_ms_per_min
                ) >= self._config.drift_warning_threshold:
                    log(t(
                        "pipe_drift_warning",
                        drift=analysis.drift_ms_per_min,
                    ))

                needs_encoding = request.encoding.pipeline is not EncodingPipeline.NONE
                synced_wav = work_dir / "synchronized.wav" if needs_encoding else staged_output
                log(t("pipe_applying_sync"))
                progress(60)
                sync_summary = self._ffmpeg.apply_sync(
                    request.source_path,
                    effective_sync,
                    delay_to_apply,
                    sync_info,
                    output_sr,
                    str(synced_wav),
                    sync_mode=request.sync_mode,
                    cancel_event=cancel_event,
                    drift_ms_per_min=drift_to_apply,
                    offset_regions=regions_to_apply,
                )
                self._require_nonempty_file(synced_wav, "synchronized WAV")

                encoding_summary: str | None = None
                if needs_encoding:
                    log(t("pipe_encoding"))
                    progress(78)
                    try:
                        encoding_summary = self._encode(
                            request.encoding,
                            synced_wav,
                            staged_output,
                            cancel_event,
                            log,
                        )
                        self._require_nonempty_file(staged_output, "final output")
                        self._ffmpeg.probe_audio(str(staged_output))
                    except OperationCancelledError:
                        raise
                    except Exception as exc:
                        fallback = self._preserve_fallback(synced_wav, output_path)
                        # Keeping the WAV saves repeating the analysis, but it is
                        # uncompressed and as long as the film — several GB for a
                        # feature.  Say how big it is, or it sits on the disk
                        # unnoticed until something runs out of space.
                        raise EncodingError(
                            t(
                                "err_encoding_failed",
                                error=exc,
                                path=fallback,
                                size=self._describe_size(fallback),
                            ),
                            fallback_path=str(fallback),
                        ) from exc
                else:
                    self._require_nonempty_file(staged_output, "final output")
                    self._ffmpeg.probe_audio(str(staged_output))

                self._check_cancelled(cancel_event)
                os.replace(staged_output, output_path)
                progress(95)

                residual, probes = self._verify_output(
                    request.source_path,
                    str(output_path),
                    log=log,
                    cancel_event=cancel_event,
                )

                progress(100)
                log(t("pipe_completed", name=output_path.name))

                return SyncOutcome(
                    output_path=str(output_path),
                    analysis=analysis,
                    source_info=source_info,
                    sync_info=sync_info,
                    output_sample_rate=output_sr,
                    sync_summary=sync_summary,
                    encoding_summary=encoding_summary,
                    drift_applied_ms_per_min=drift_to_apply,
                    offset_regions_applied=regions_to_apply,
                    fps_conversion_applied=applied_fps,
                    verified_residual_ms=residual,
                    verified_probes=probes,
                )
        finally:
            staged_output.unlink(missing_ok=True)

    def _verify_output(
        self,
        source_path: str,
        output_path: str,
        *,
        log: LogCallback,
        cancel_event: threading.Event | None = None,
    ) -> tuple[float | None, int]:
        """Measure the file that was written against the reference it targets.

        Every stage before this one reports what it *intended* to do.  Nothing
        reported what came out, so a wrong measurement, a filter that silently
        did nothing, or an encoder that shifted the track by its own lookahead
        all produced a confident success message and a file nobody had checked.

        A few short probes at matching timestamps answer it directly: a track
        that landed reports a residual near zero, and one that did not says so
        in milliseconds.
        """
        cfg = self._config
        if not cfg.verify_output_enabled or cfg.verify_probe_count < 1:
            return None, 0

        try:
            duration = self._probe_duration_sec(output_path)
            if duration <= cfg.verify_probe_sec * 2:
                return None, 0

            log(t("pipe_verifying"))
            analyzer = self._get_analyzer()
            rate = cfg.analysis_sample_rate
            margin = min(duration * 0.05, 120.0)
            positions = np.linspace(
                margin,
                max(margin, duration - margin - cfg.verify_probe_sec),
                max(2, cfg.verify_probe_count),
            )

            measured: list[float] = []
            for at_sec in positions:
                if cancel_event is not None and cancel_event.is_set():
                    return None, 0
                reference = self._ffmpeg.decode_probe_mono_pcm(
                    source_path, float(at_sec), cfg.verify_probe_sec,
                    sample_rate=rate, cancel_event=cancel_event,
                )
                produced = self._ffmpeg.decode_probe_mono_pcm(
                    output_path,
                    float(at_sec) - cfg.verify_search_sec,
                    cfg.verify_probe_sec + (2.0 * cfg.verify_search_sec),
                    sample_rate=rate,
                    cancel_event=cancel_event,
                )
                found = analyzer.residual_offset_ms(
                    rate, reference, produced, search_sec=cfg.verify_search_sec,
                )
                if found is not None and found[1] >= cfg.verify_min_sharpness:
                    measured.append(found[0])

            if len(measured) < 2:
                log(t("pipe_verify_inconclusive"))
                return None, 0

            residual = float(np.median(measured))
            if abs(residual) >= cfg.verify_warn_ms:
                log(t("pipe_verify_off", residual=residual, probes=len(measured)))
            else:
                log(t("pipe_verify_ok", residual=residual, probes=len(measured)))
            return residual, len(measured)
        except Exception:
            # A check that fails must never fail the run it was checking.
            log(t("pipe_verify_inconclusive"))
            return None, 0

    def _probe_duration_sec(self, path: str) -> float:
        probe = self._ffmpeg.probe_duration_sec(path)
        return float(probe or 0.0)

    @staticmethod
    def _report_verdict(analysis: AnalysisResult, log: LogCallback) -> None:
        """Say out loud how much of the measurement can be trusted, and why."""
        if analysis.verdict is MatchVerdict.NO_MATCH:
            log(t("verdict_no_match"))
        elif analysis.verdict is MatchVerdict.UNCERTAIN:
            log(t("verdict_uncertain"))

        for reason in analysis.verdict_reasons:
            log(t("verdict_reason", reason=t(reason)))

        if analysis.phat_probes:
            log(t(
                "verdict_sample_confirmed",
                probes=analysis.phat_probes,
                sharpness=analysis.phat_sharpness,
            ))

    @staticmethod
    def _better_analysis(
        original: AnalysisResult,
        converted: AnalysisResult,
        conversion: FpsConversion,
        log: LogCallback,
    ) -> tuple[AnalysisResult, FpsConversion | None]:
        """Keep the frame-rate conversion only if it actually read better.

        Detection has been right on everything tested, but acting on it changes
        the audio, so the claim is checked rather than trusted: the conversion
        stays only when the windows agree more closely than they did without it.
        Window agreement is the right measure — a rate mismatch is precisely
        what makes windows from different parts of the file disagree.
        """
        before = original.windows_disagree_ms
        after = converted.windows_disagree_ms

        if after < before or (after == before and converted.used_segments > original.used_segments):
            log(t("pipe_fps_kept", before=before, after=after))
            return converted, conversion

        log(t("pipe_fps_rejected", before=before, after=after))
        return original, None

    @staticmethod
    def suspected_fps_conversion(analysis: AnalysisResult) -> FpsConversion | None:
        """The frame-rate conversion these two tracks appear to need.

        Two independent signals point at the same answer, and either alone is
        incomplete.  Resampling the coarse features by each standard ratio finds
        a mismatch even when it is too large for the segment search to measure —
        which is precisely the case that needs the hint most.  Matching the
        measured slope catches the milder cases where the analysis succeeded but
        the cause is still a frame rate.
        """
        if analysis.suspected_fps_conversion:
            try:
                return FpsConversion[analysis.suspected_fps_conversion]
            except KeyError:  # pragma: no cover - defensive
                pass
        if analysis.drift_ms_per_min is not None:
            return match_drift_to_fps(analysis.drift_ms_per_min)
        return None

    @staticmethod
    def resolve_offset_regions(
        analysis: AnalysisResult,
        *,
        enabled: bool,
    ) -> tuple[OffsetRegion, ...]:
        """Return the regions to splice, or an empty tuple to use one offset.

        Splicing cuts the audio, so it is only worth doing when the analyzer
        genuinely found more than one offset in the file.  Everything that
        decides *whether* a step is real lives in the detector; this is the
        switch the caller controls.
        """
        if not enabled or not analysis.has_step_discontinuity:
            return ()
        return analysis.offset_regions

    @staticmethod
    def resolve_drift_correction(
        analysis: AnalysisResult,
        *,
        enabled: bool,
        config: SyncConfig = SYNC_CONFIG,
    ) -> tuple[float | None, float]:
        """Decide whether to retime the track, and with which offset.

        Returns ``(drift_ms_per_min_or_None, delay_ms_to_apply)``.

        When a drift correction is applied the offset must come from the fitted
        line's intercept rather than ``delay_ms``: the latter is a median across
        segments, so it describes the middle of the content and would leave the
        track half the total drift out of sync at both ends.

        A correction is only worth its resampling cost when the slope is both
        large enough to matter and well enough supported by the data.  Every
        threshold lives in :class:`SyncConfig` so the whole gate can be tuned
        from one place; refusing a real drift merely leaves the previous
        behaviour, while applying a phantom one damages a correct track.

        A file whose offset *steps* is excluded here rather than in the result
        object: a line fitted through a step has a slope, but it does not mean
        anything, and the piecewise path handles that case instead.
        """
        if not enabled or analysis.has_step_discontinuity:
            return None, analysis.delay_ms
        if not analysis.has_drift_measurement:
            return None, analysis.delay_ms

        drift = float(analysis.drift_ms_per_min or 0.0)
        if (
            abs(drift) < config.drift_correction_min_ms_per_min
            or (analysis.drift_r2 or 0.0) < config.drift_correction_min_r2
            or analysis.used_segments < config.drift_correction_min_segments
            or analysis.drift_span_sec < config.drift_correction_min_span_sec
        ):
            return None, analysis.delay_ms

        return drift, float(analysis.drift_intercept_ms or 0.0)

    @staticmethod
    def normalize_request(request: SyncRequest) -> SyncRequest:
        """Return a request whose media paths are absolute.

        FFmpeg reads a leading ``name:`` on a *relative* path as a protocol
        specifier, so ``sample:track.wav`` would be routed to the ``sample``
        protocol instead of the file. Absolute paths also make the
        output-overwrites-input check reliable regardless of the working
        directory the app happens to be launched from.
        """
        return replace(
            request,
            source_path=SyncPipeline._absolute_path(request.source_path),
            sync_path=SyncPipeline._absolute_path(request.sync_path),
            output_path=SyncPipeline._absolute_path(request.output_path),
        )

    @staticmethod
    def _absolute_path(path: str) -> str:
        return str(Path(path).expanduser().absolute())

    @staticmethod
    def validate_request(request: SyncRequest) -> None:
        """Validate inputs and reject output paths that could destroy source data."""
        validate_file(request.source_path, "Source audio")
        validate_file(request.sync_path, "Sync audio")
        if request.total_segments < 1:
            raise ValueError("total_segments must be at least 1")
        if request.skip_intro_sec < 0:
            raise ValueError("skip_intro_sec cannot be negative")

        output = Path(request.output_path).expanduser().resolve()
        for label, input_path in (
            ("source", request.source_path),
            ("sync", request.sync_path),
        ):
            if SyncPipeline._same_path(output, Path(input_path)):
                raise UnsafeOutputPathError(
                    f"Output path cannot overwrite the {label} input file: {output}"
                )

    def _get_analyzer(self) -> AudioAnalyzer:
        if self._analyzer is None:
            from audio_sync.core.analyzer import AudioAnalyzer

            self._analyzer = AudioAnalyzer(config=self._config)
        return self._analyzer

    def _encode(
        self,
        request: EncodingRequest,
        input_wav: Path,
        staged_output: Path,
        cancel_event: threading.Event,
        log: LogCallback,
    ) -> str:
        if request.pipeline is EncodingPipeline.DEEW:
            resolve_deew_backend()
            result = encode_wav_with_deew(
                input_wav=str(input_wav),
                final_output_path=str(staged_output),
                fmt=request.deew.format,
                bitrate=request.deew.bitrate,
                downmix=request.deew.downmix,
                drc=request.deew.drc,
                dialnorm=request.deew.dialnorm,
                delete_wav=False,
                progress_callback=log,
                cancel_event=cancel_event,
            )
            self._require_nonempty_file(Path(result), "Deew output")
            return f"Deew {request.deew.format.display_name}"

        if request.pipeline is EncodingPipeline.QAAC:
            ok, detail = QaacEncoder.check_availability()
            if not ok:
                raise RuntimeError(detail)
            return QaacEncoder.encode(
                str(input_wav),
                str(staged_output),
                request.qaac,
                cancel_event=cancel_event,
            )

        if request.pipeline is not EncodingPipeline.FFMPEG:
            raise ValueError(f"Unsupported encoding pipeline: {request.pipeline.value}")

        config = request.ffmpeg
        if config.format is FFmpegOutputFormat.AAC:
            return self._ffmpeg.encode_to_aac(
                str(input_wav),
                str(staged_output),
                bitrate=config.aac_bitrate,
                channels=request.ffmpeg_channels,
                cancel_event=cancel_event,
            )
        if config.format is FFmpegOutputFormat.FLAC:
            return self._ffmpeg.encode_to_flac(
                str(input_wav),
                str(staged_output),
                compression=config.flac_compression,
                bit_depth=config.flac_bit_depth,
                channels=request.ffmpeg_channels,
                cancel_event=cancel_event,
            )
        if config.format is FFmpegOutputFormat.OPUS:
            return self._ffmpeg.encode_to_opus(
                str(input_wav),
                str(staged_output),
                bitrate=config.opus_bitrate,
                channels=request.ffmpeg_channels,
                cancel_event=cancel_event,
            )
        if config.format is FFmpegOutputFormat.AC3:
            return self._ffmpeg.encode_to_ac3_eac3(
                str(input_wav),
                str(staged_output),
                fmt=DeewFormat.DD,
                bitrate=config.ac3_bitrate,
                channels=request.ffmpeg_channels,
                cancel_event=cancel_event,
            )
        if config.format is FFmpegOutputFormat.EAC3:
            return self._ffmpeg.encode_to_ac3_eac3(
                str(input_wav),
                str(staged_output),
                fmt=DeewFormat.DDP,
                bitrate=config.eac3_bitrate,
                channels=request.ffmpeg_channels,
                cancel_event=cancel_event,
            )
        raise ValueError(f"Unsupported FFmpeg format: {config.format}")

    @staticmethod
    def _reserve_staged_output(output_path: Path) -> Path:
        descriptor, path = tempfile.mkstemp(
            prefix=f".{output_path.stem}.staged-",
            suffix=output_path.suffix,
            dir=output_path.parent,
        )
        os.close(descriptor)
        return Path(path)

    @staticmethod
    def _describe_size(path: Path) -> str:
        """Human-readable file size, for messages about disk usage."""
        try:
            size = float(path.stat().st_size)
        except OSError:  # pragma: no cover - defensive
            return "size unknown"

        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024.0 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024.0
        return f"{size:.1f} GB"  # pragma: no cover - unreachable

    @staticmethod
    def _preserve_fallback(synced_wav: Path, output_path: Path) -> Path:
        candidate = output_path.with_name(f"{output_path.stem}.sync-fallback.wav")
        counter = 2
        while candidate.exists():
            candidate = output_path.with_name(
                f"{output_path.stem}.sync-fallback-{counter}.wav"
            )
            counter += 1
        shutil.move(str(synced_wav), str(candidate))
        return candidate

    @staticmethod
    def _same_path(first: Path, second: Path) -> bool:
        try:
            if first.exists() and second.exists():
                return os.path.samefile(first, second)
        except OSError:
            pass
        return os.path.normcase(str(first.resolve())) == os.path.normcase(str(second.resolve()))

    @staticmethod
    def _require_nonempty_file(path: Path, label: str) -> None:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise RuntimeError(f"{label} was not created: {path}") from exc
        if size <= 0:
            raise RuntimeError(f"{label} is empty: {path}")

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            raise OperationCancelledError("Processing cancelled by user.")

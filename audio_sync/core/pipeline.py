"""Testable orchestration for the complete audio synchronization workflow."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

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
)
from audio_sync.core.deew_encoder import encode_wav_with_deew, resolve_deew_backend
from audio_sync.core.encoder import QaacEncoder
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper
from audio_sync.core.models import (
    AnalysisResult,
    AudioInfo,
    EncodingError,
    OperationCancelledError,
    OutputSampleRate,
    UnsafeOutputPathError,
)
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
                log("Reading audio metadata…")
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
                    log(f"Applying FPS conversion: {request.fps_conversion.display_name}")
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

                log("Decoding analysis PCM…")
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

                log("Analyzing delay…")
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

                needs_encoding = request.encoding.pipeline is not EncodingPipeline.NONE
                synced_wav = work_dir / "synchronized.wav" if needs_encoding else staged_output
                log("Applying synchronization…")
                progress(60)
                sync_summary = self._ffmpeg.apply_sync(
                    request.source_path,
                    effective_sync,
                    analysis.delay_ms,
                    sync_info,
                    output_sr,
                    str(synced_wav),
                    sync_mode=request.sync_mode,
                    cancel_event=cancel_event,
                )
                self._require_nonempty_file(synced_wav, "synchronized WAV")

                encoding_summary: str | None = None
                if needs_encoding:
                    log("Encoding final output…")
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
                        raise EncodingError(
                            f"Final encoding failed. Synchronized WAV preserved at "
                            f"'{fallback}': {exc}",
                            fallback_path=str(fallback),
                        ) from exc
                else:
                    self._require_nonempty_file(staged_output, "final output")
                    self._ffmpeg.probe_audio(str(staged_output))

                self._check_cancelled(cancel_event)
                os.replace(staged_output, output_path)
                progress(100)
                log(f"Completed: {output_path.name}")

                return SyncOutcome(
                    output_path=str(output_path),
                    analysis=analysis,
                    source_info=source_info,
                    sync_info=sync_info,
                    output_sample_rate=output_sr,
                    sync_summary=sync_summary,
                    encoding_summary=encoding_summary,
                )
        finally:
            staged_output.unlink(missing_ok=True)

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

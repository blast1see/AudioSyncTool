"""FFmpeg/FFprobe komut satırı arayüzü.

Bu modül dış süreç çağrılarını soyutlayarak:
  - Timeout desteği sağlar
  - FFmpeg varlık kontrolü yapar
  - Test'te mock edilebilir ``CommandRunner`` protokolü sunar
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import tempfile
import threading
from typing import Protocol, Sequence

import numpy as np

from audio_sync.config import (
    CODEC_EXTENSION_MAP,
    SYNC_CONFIG,
    DeewFormat,
    FpsConversion,
    PcmCodec,
    SyncConfig,
    SyncMode,
    resolve_tool,
)
from audio_sync.core.models import (
    AudioInfo,
    AudioProbeError,
    OffsetRegion,
    OutputSampleRate,
)
from audio_sync.core.process_runner import run_binary_process, run_text_process
from audio_sync.i18n import t
from audio_sync.utils import scale_timeout_for_size

# Cached ``ffmpeg``/``ffprobe`` locations that already answered ``-version``.
_AVAILABILITY_LOCK = threading.Lock()
_AVAILABILITY_VERIFIED: tuple[str | None, str | None] | None = None

# ── Komut Çalıştırıcı Protokolü ─────────────────────────────────────────────


class CommandRunner(Protocol):
    """``subprocess.run`` için soyutlama — test'te mock edilebilir."""

    def run(
        self,
        cmd: list[str],
        *,
        capture_output: bool = True,
        text: bool = True,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Komutu çalıştırır ve sonucu döndürür."""
        ...


class SubprocessRunner:
    """Gerçek ``subprocess.run`` çağrısı yapan runner."""

    def run(
        self,
        cmd: list[str],
        *,
        capture_output: bool = True,
        text: bool = True,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Komutu subprocess ile çalıştırır.

        Windows'ta konsol penceresi açılmasını engeller.
        """
        kwargs: dict = dict(
            capture_output=capture_output,
            text=text,
            timeout=timeout,
        )
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        return subprocess.run(cmd, **kwargs)


# ── FFmpeg Wrapper ───────────────────────────────────────────────────────────


class FFmpegWrapper:
    """FFmpeg ve FFprobe komut satırı arayüzü.

    Args:
        config: Senkronizasyon yapılandırması (timeout değerleri için).
        runner: Komut çalıştırıcı.  ``None`` ise gerçek subprocess kullanılır.

    Raises:
        OSError: FFmpeg veya FFprobe sistemde bulunamazsa.
    """

    def __init__(
        self,
        config: SyncConfig = SYNC_CONFIG,
        runner: CommandRunner | None = None,
    ) -> None:
        self._config = config
        self._runner = runner or SubprocessRunner()

    # ── Bağımlılık Kontrolü ──────────────────────────────────────────────

    @staticmethod
    def reset_availability_cache() -> None:
        """Forget the cached probe so the next check re-runs the binaries."""
        global _AVAILABILITY_VERIFIED
        with _AVAILABILITY_LOCK:
            _AVAILABILITY_VERIFIED = None

    @staticmethod
    def check_availability() -> None:
        """FFmpeg ve FFprobe'un sistemde kurulu olduğunu doğrular.

        Her çağrı iki alt süreç başlattığından, başarılı sonuç önbelleğe
        alınır; araç yolları değişince :func:`reset_availability_cache`
        ile geçersiz kılınır.

        Raises:
            OSError: Araçlardan biri bulunamazsa.
        """
        global _AVAILABILITY_VERIFIED

        signature = FFmpegWrapper._availability_signature()
        with _AVAILABILITY_LOCK:
            if _AVAILABILITY_VERIFIED == signature:
                return

        for tool in ("ffmpeg", "ffprobe"):
            try:
                binary = resolve_tool(tool)
                result = run_text_process(
                    [binary, "-version"],
                    timeout=10,
                    not_found_message=f"'{tool}' could not be executed.",
                    timeout_message=f"'{tool} -version' timed out.",
                )
                if result.returncode != 0:
                    detail = (result.stderr or result.stdout or "").strip()
                    raise OSError(detail or f"exit code {result.returncode}")
            except (OSError, RuntimeError) as exc:
                raise OSError(
                    f"'{tool}' not found. Please install FFmpeg:\n"
                    f"  https://ffmpeg.org/download.html\n"
                    f"  Windows: winget install ffmpeg\n"
                    f"  macOS:   brew install ffmpeg\n"
                    f"  Linux:   sudo apt install ffmpeg\n"
                    f"Details: {exc}"
                ) from exc

        with _AVAILABILITY_LOCK:
            _AVAILABILITY_VERIFIED = signature

    @staticmethod
    def _availability_signature() -> tuple[str | None, str | None]:
        """Identify the exact binaries a cached success belongs to."""
        signature: list[str | None] = []
        for tool in ("ffmpeg", "ffprobe"):
            try:
                signature.append(resolve_tool(tool))
            except OSError:
                signature.append(None)
        return signature[0], signature[1]

    # ── Ses Bilgisi Okuma ────────────────────────────────────────────────

    def probe_audio(self, path: str) -> AudioInfo:
        """FFprobe ile ses dosyasının meta verisini okur.

        Args:
            path: Ses dosyasının yolu.

        Returns:
            Güvenilir ``AudioInfo`` nesnesi.

        Raises:
            AudioProbeError: FFprobe başarısızsa veya gerekli alanlar eksikse.
        """
        try:
            ffprobe = resolve_tool("ffprobe")
        except OSError as exc:
            raise AudioProbeError(f"FFprobe is unavailable: {exc}") from exc

        cmd = [
            ffprobe,
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries",
            "stream=channels,codec_name,sample_fmt,bits_per_raw_sample,sample_rate",
            "-of", "default=noprint_wrappers=1",
            path,
        ]

        try:
            result = self._run_command(cmd, timeout=self._config.ffprobe_timeout_sec)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise AudioProbeError(
                f"FFprobe could not read audio metadata for '{path}': {exc}"
            ) from exc

        if result.returncode != 0:
            detail = (result.stderr or "").strip()[-600:] or "no diagnostic output"
            raise AudioProbeError(
                f"FFprobe could not read audio metadata for '{path}': {detail}"
            )

        info = self._parse_ffprobe_output(result.stdout)
        if not info.get("channels") or not info.get("sample_rate"):
            raise AudioProbeError(
                f"FFprobe returned incomplete audio metadata for '{path}'. "
                "The file may not contain a readable audio stream."
            )

        channels = self._safe_int(info.get("channels"), default=2, minimum=1)
        sample_rate = self._safe_int(info.get("sample_rate"), default=48000, minimum=8000)
        bits = self._determine_bit_depth(info)
        codec = PcmCodec.from_bits(bits)

        return AudioInfo(
            channels=channels,
            codec=codec,
            bits=bits,
            sample_rate=sample_rate,
        )

    # ── Container / MKV Stream Probing ───────────────────────────────────

    def probe_audio_streams(self, path: str) -> list[dict[str, str]]:
        """Probe all audio streams in a container file (MKV, MP4, etc.).

        Args:
            path: Path to the container file.

        Returns:
            List of dicts with keys: index, codec_name, channels,
            sample_rate, bit_rate, tags/language, tags/title.
        """
        import json as _json

        cmd = [
            resolve_tool("ffprobe"),
            "-v", "error",
            "-select_streams", "a",
            "-show_entries",
            "stream=index,codec_name,codec_long_name,profile,channels,sample_rate,bit_rate,bits_per_raw_sample",
            "-show_entries", "stream_tags=language,title",
            "-of", "json",
            path,
        ]

        result = self._run_command(cmd, timeout=self._config.ffprobe_timeout_sec)
        if result.returncode != 0:
            return []

        try:
            data = _json.loads(result.stdout)
        except (ValueError, KeyError):
            return []

        streams: list[dict[str, str]] = []
        for s in data.get("streams", []):
            tags = s.get("tags", {})
            stream_info = {
                "index": str(s.get("index", 0)),
                "codec_name": s.get("codec_name", "unknown"),
                "codec_long_name": s.get("codec_long_name", ""),
                "profile": s.get("profile", ""),
                "channels": str(s.get("channels", 0)),
                "sample_rate": str(s.get("sample_rate", 0)),
                "bit_rate": str(s.get("bit_rate", "N/A")),
                "language": tags.get("language", "und"),
                "title": tags.get("title", ""),
            }
            stream_info["codec_display"] = self._get_stream_codec_display(stream_info)
            stream_info["suggested_ext"] = self._get_stream_extension(stream_info)
            streams.append(stream_info)
        return streams

    def extract_audio_stream(
        self,
        input_path: str,
        output_path: str,
        stream_index: int,
    ) -> None:
        """Extract a specific audio stream from a container file.

        Args:
            input_path: Path to the container file.
            output_path: Path for the extracted audio file.
            stream_index: FFmpeg stream index to extract.

        Raises:
            RuntimeError: If extraction fails.
        """
        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-y",
            "-i", input_path,
            "-map", f"0:{stream_index}",
            "-c", "copy",
            output_path,
        ]
        result = self._run_command(
            cmd,
            timeout=self._get_ffmpeg_timeout(input_path),
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"Audio stream extraction error:\n{stderr_tail}")

    # ── Mono WAV Conversion ──────────────────────────────────────────────

    def to_wav_mono(
        self,
        src: str,
        out_path: str,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Senkron analizi için tek kanallı, düşük örneklemeli WAV hazırlar.

        Args:
            src: Kaynak ses dosyasının yolu.
            out_path: Çıktı WAV dosyasının yolu.

        Raises:
            RuntimeError: FFmpeg dönüşüm hatası.
        """
        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-y",
            "-i", src,
            "-ar", str(self._config.analysis_sample_rate),
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-f", "wav",
            out_path,
        ]
        result = self._run_command(
            cmd,
            timeout=self._get_ffmpeg_timeout(src),
            cancel_event=cancel_event,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-400:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"Mono conversion error:\n{stderr_tail}")

    def decode_mono_pcm(
        self,
        src: str,
        sample_rate: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> tuple[int, np.ndarray]:
        """Decode audio to mono 16-bit PCM in memory for analysis."""
        analysis_rate = sample_rate or self._config.analysis_sample_rate
        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-i", src,
            "-vn",
            "-sn",
            "-dn",
            "-ar", str(analysis_rate),
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-f", "s16le",
            "-",
        ]
        result = self._run_binary_command(
            cmd,
            timeout=self._get_ffmpeg_timeout(src),
            cancel_event=cancel_event,
        )
        if result.returncode != 0:
            stderr_tail = (
                result.stderr.decode("utf-8", errors="replace")[-400:]
                if result.stderr else "(stderr empty)"
            )
            raise RuntimeError(f"Mono decode error:\n{stderr_tail}")

        pcm_bytes = result.stdout or b""
        if not pcm_bytes:
            raise RuntimeError("Mono decode returned no audio samples.")

        if len(pcm_bytes) % 2 != 0:
            pcm_bytes = pcm_bytes[:-1]

        pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
        if pcm.size == 0:
            raise RuntimeError("Mono decode returned an empty PCM buffer.")

        return analysis_rate, pcm

    def decode_mono_pcm_to_file(
        self,
        src: str,
        sample_rate: int | None = None,
        cancel_event: threading.Event | None = None,
        *,
        prefix: str = "audiosync_pcm_",
        temp_dir: str | None = None,
    ) -> tuple[int, str, int]:
        """Decode audio to mono 16-bit PCM on disk for lower-RAM analysis."""
        analysis_rate = sample_rate or self._config.analysis_sample_rate
        fd, out_path = tempfile.mkstemp(
            suffix=".s16le",
            prefix=prefix,
            dir=temp_dir,
        )
        os.close(fd)

        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-y",
            "-i", src,
            "-vn",
            "-sn",
            "-dn",
            "-ar", str(analysis_rate),
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-f", "s16le",
            out_path,
        ]
        try:
            result = self._run_command(
                cmd,
                timeout=self._get_ffmpeg_timeout(src),
                cancel_event=cancel_event,
            )
            if result.returncode != 0:
                stderr_tail = result.stderr[-400:] if result.stderr else "(stderr empty)"
                raise RuntimeError(f"Mono decode error:\n{stderr_tail}")

            byte_count = os.path.getsize(out_path)
            sample_count = byte_count // np.dtype(np.int16).itemsize
            if sample_count <= 0:
                raise RuntimeError("Mono decode returned no audio samples.")

            return analysis_rate, out_path, sample_count
        except Exception:
            if os.path.isfile(out_path):
                try:
                    os.remove(out_path)
                except OSError:
                    pass
            raise

    # ── FPS Dönüşümü ────────────────────────────────────────────────────

    def apply_fps_conversion(
        self,
        src: str,
        out_path: str,
        conversion: FpsConversion,
        audio_info: AudioInfo,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Ses dosyasının frame rate'ini dönüştürür (tempo değişikliği).

        FPS dönüşümü, sesin hızını ``source_fps / target_fps`` oranında
        değiştirerek gerçekleştirilir.  FFmpeg ``atempo`` filtresi kullanılır;
        bu filtre ses kalitesini koruyarak yalnızca hızı ayarlar.

        ``atempo`` filtresi 0.5–100.0 aralığında çalışır.  Desteklenen tüm
        FPS dönüşüm senaryoları bu aralıkta olduğundan ek zincirleme gerekmez.

        Args:
            src: Kaynak ses dosyasının yolu.
            out_path: Çıktı dosyasının yolu.
            conversion: FPS dönüşüm senaryosu.
            audio_info: Kaynak sesin meta verisi (codec, kanal, bit derinliği).

        Returns:
            Uygulanan dönüşümün özet açıklaması (log için).

        Raises:
            RuntimeError: FFmpeg dönüşüm hatası.
        """
        ratio = conversion.tempo_ratio

        # atempo filtresi: <1.0 sesi uzatır (yavaşlatır), >1.0 kısaltır (hızlandırır)
        # FPS dönüşümünde kaynak FPS > hedef FPS ise ses uzamalı → atempo = 1/ratio
        # Kaynak FPS < hedef FPS ise ses kısalmalı → atempo = 1/ratio
        # Genel formül: atempo = 1 / ratio = target_fps / source_fps
        atempo_value = 1.0 / ratio

        pcm_codec = audio_info.codec.codec_name
        channels = audio_info.channels
        sample_rate = audio_info.sample_rate

        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-y",
            "-i", src,
            "-af", f"atempo={atempo_value:.15f}",
            "-ac", str(channels),
            "-ar", str(sample_rate),
            "-acodec", pcm_codec,
            "-rf64", "auto",
            out_path,
        ]

        cmd_summary = t(
            "log_fps_summary",
            name=conversion.display_name,
            tempo=atempo_value,
            ratio=ratio,
            bits=audio_info.bits,
            rate=sample_rate,
        )

        result = self._run_command(
            cmd,
            timeout=self._get_ffmpeg_timeout(src),
            cancel_event=cancel_event,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"FPS conversion error:\n{stderr_tail}")

        return cmd_summary

    # ── Senkronizasyon Uygulama ──────────────────────────────────────────

    @staticmethod
    def drift_tempo_factor(drift_ms_per_min: float) -> float:
        """Convert a measured drift into the tempo factor that cancels it.

        A drift of ``D`` ms/min means the lag between the two tracks grows by
        ``D/60`` ms per second of reference time — the track being synchronized
        is running slow by that fraction.  Speeding it up by ``1 - D/60000``
        removes the growth and leaves a constant offset behind.
        """
        return 1.0 - (drift_ms_per_min / 60_000.0)

    def apply_sync(
        self,
        src_orig: str,
        sync_orig: str,
        delay_ms: float,
        audio_info: AudioInfo,
        output_sr: OutputSampleRate,
        out_path: str,
        sync_mode: SyncMode = SyncMode.ADELAY_AMIX,
        cancel_event: threading.Event | None = None,
        drift_ms_per_min: float | None = None,
        offset_regions: Sequence[OffsetRegion] | None = None,
    ) -> str:
        """Orijinal dosyaları senkronize eder, karıştırır ve WAV olarak yazar.

        Args:
            src_orig: Kaynak (referans) ses dosyası yolu.
            sync_orig: Senkronize edilecek ses dosyası yolu.
            delay_ms: Hesaplanan gecikme (ms).
                Pozitif → sync ses erkende, sync ses geciktirilir.
                Negatif → sync ses geçte, sync sesin başı kırpılır.
            audio_info: Senkronize edilecek sesin bilgileri.
            output_sr: Çıktı örnekleme oranı kararı.
            out_path: Çıktı dosyası yolu.
            sync_mode: Senkronizasyon filtre modu.
            drift_ms_per_min: Giderilecek ilerleyen drift (ms/dk).  ``None``
                veya sıfır ise yalnızca sabit ofset uygulanır.

        Returns:
            Oluşturulan FFmpeg komutunun özet açıklaması (log için).

        Raises:
            RuntimeError: FFmpeg senkronizasyon hatası.
        """
        cmd, cmd_summary = self.build_sync_command(
            sync_orig,
            delay_ms,
            audio_info,
            output_sr,
            out_path,
            sync_mode=sync_mode,
            drift_ms_per_min=drift_ms_per_min,
            offset_regions=offset_regions,
        )

        result = self._run_command(
            cmd,
            timeout=self._get_ffmpeg_timeout(src_orig, sync_orig),
            cancel_event=cancel_event,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"FFmpeg synchronization error:\n{stderr_tail}")

        return cmd_summary

    # ── Senkronizasyon Filtre Zinciri ────────────────────────────────────

    def build_piecewise_filter(
        self,
        regions: Sequence[OffsetRegion],
        channels: int,
    ) -> tuple[str, str]:
        """Build a filter graph that applies a different offset per region.

        Each region is cut straight out of the source at the position its own
        offset points to, then the pieces are concatenated.  Because the cuts
        are taken in *reference* time, every piece keeps the duration it is
        supposed to occupy, so the joins land exactly where the edit was.

        A short fade is applied on either side of every internal join.  The
        splice is a genuine discontinuity — that is the point — and without the
        fade the waveform steps instantly, which is audible as a click.

        Each region reads from its *own* input rather than from an ``asplit`` of
        one.  Splitting a single decoder couples the branches: ``concat`` drains
        the first piece while the later branches are handed frames they cannot
        use yet, and whether that resolves depends on the FFmpeg build.  It ran
        in well under a second locally and hung for over half an hour on the
        FFmpeg that ships with Ubuntu.  Separate inputs decode independently, so
        there is nothing to deadlock on; the cost is re-reading the file once per
        region, bounded by ``step_max_regions``.

        Returns:
            ``(filter_chain, summary)`` — the chain ends at ``[spliced]`` so the
            caller can still append the shared tail stages.
        """
        if len(regions) < 2:
            raise ValueError("piecewise sync needs at least two regions")

        fade = self._config.step_splice_fade_sec
        labels: list[str] = []
        parts: list[str] = []

        for index, region in enumerate(regions):
            lag_sec = region.lag_ms / 1000.0
            src_start = region.start_sec - lag_sec
            stages: list[str] = []

            # A negative source position means the reference starts before this
            # track does; the missing head is silence, not audio to seek to.
            head_pad = max(0.0, -src_start)
            trim = f"atrim=start={max(0.0, src_start):.6f}"
            if math.isfinite(region.end_sec):
                src_end = region.end_sec - lag_sec
                trim += f":end={max(0.0, src_end):.6f}"
            stages.append(trim)
            stages.append("asetpts=PTS-STARTPTS")

            if head_pad > 1e-6:
                pad_stage, _note = self._build_offset_stage(head_pad * 1000.0, channels)
                if pad_stage:
                    stages.append(pad_stage)

            duration = region.duration_sec
            if index > 0:
                stages.append(f"afade=t=in:st=0:d={fade:.4f}")
            if index < len(regions) - 1 and math.isfinite(duration) and duration > fade * 4:
                stages.append(
                    f"afade=t=out:st={duration - fade:.6f}:d={fade:.4f}"
                )

            parts.append(f"[{index}:a]" + ",".join(stages) + f"[p{index}]")
            labels.append(f"[p{index}]")

        parts.append("".join(labels) + f"concat=n={len(regions)}:v=0:a=1[spliced]")

        summary = "piecewise " + " | ".join(
            f"{start:.1f}–{end}m {region.lag_ms:+.0f}ms"
            for start, end, region in (
                (*region.bounds_in_minutes(), region) for region in regions
            )
        )
        return ";".join(parts), summary

    def build_sync_command(
        self,
        sync_path: str,
        delay_ms: float,
        audio_info: AudioInfo,
        output_sr: OutputSampleRate,
        out_path: str,
        *,
        sync_mode: SyncMode = SyncMode.ADELAY_AMIX,
        drift_ms_per_min: float | None = None,
        offset_regions: Sequence[OffsetRegion] | None = None,
    ) -> tuple[list[str], str]:
        """Compose the FFmpeg command that writes the synchronized track.

        Only the track being synchronized is written; the reference exists
        purely to measure the offset against.

        The filter chain is assembled in a fixed order — drift first, then the
        constant offset — because a tempo change rescales everything downstream
        of it.  Applying the offset first would shrink it by the tempo factor.

        Args:
            sync_path: Track to synchronize.
            delay_ms: Constant offset.  Positive means the track runs early and
                is delayed; negative means it runs late and its head is trimmed.
                When ``drift_ms_per_min`` is supplied this must already be the
                offset at ``t=0`` (``AnalysisResult.drift_intercept_ms``), not
                the median offset.
            audio_info: Metadata of the track being synchronized.
            output_sr: Output sample-rate decision.
            out_path: Destination path.
            sync_mode: Filter strategy.
            drift_ms_per_min: Progressive drift to cancel, or ``None``/0.
            offset_regions: Two or more regions to splice, each with its own
                offset.  Takes precedence over ``delay_ms`` and
                ``drift_ms_per_min``: a step is not something a single offset
                or a straight line can express.

        Returns:
            ``(command, summary)`` — the summary is what the UI logs.
        """
        channels = audio_info.channels
        pcm_codec = audio_info.codec.codec_name

        notes: list[str] = []
        head = ""
        entry = "[0:a]"
        input_count = 1

        if offset_regions and len(offset_regions) > 1:
            head, piecewise_note = self.build_piecewise_filter(offset_regions, channels)
            notes.append(piecewise_note)
            entry = "[spliced]"
            # One input per region: the graph reads each piece from its own
            # decoder rather than splitting one, which is what keeps it from
            # deadlocking on some FFmpeg builds.
            input_count = len(offset_regions)
            stages = []
        else:
            stages = []
            effective_delay_ms = float(delay_ms)
            drift = float(drift_ms_per_min or 0.0)
            if drift:
                tempo_filter, factor, drift_note = self._build_drift_stage(drift, sync_mode)
                stages.append(tempo_filter)
                notes.append(drift_note)
                # The offset is measured on the original timeline; once the
                # track is retimed by ``factor`` the same wall-clock gap sits at
                # a different position, so it has to be rescaled to match.
                if factor > 0:
                    effective_delay_ms /= factor

            offset_stage, offset_note = self._build_offset_stage(
                effective_delay_ms, channels
            )
            if offset_stage:
                stages.append(offset_stage)
            notes.append(offset_note)

        # The mode tail answers "my source has broken timestamps", which is
        # independent of how many offsets the file needs.  It used to be applied
        # only on the non-piecewise path, so choosing Repair timestamps on a
        # stepped file silently did nothing while the summary still claimed it.
        tail_stage = self._MODE_TAIL_FILTERS.get(sync_mode)
        if tail_stage:
            stages.append(tail_stage)
            notes.append(tail_stage)

        chain = ",".join(stages) if stages else "acopy"
        flt = f"{head};{entry}{chain}[out]" if head else f"[0:a]{chain}[out]"

        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-y",
        ]
        for _ in range(input_count):
            cmd.extend(["-i", sync_path])
        cmd.extend([
            "-filter_complex", flt,
            "-map", "[out]",
        ])

        if output_sr.needs_resample:
            cmd.extend(["-ar", str(output_sr.rate)])

        cmd.extend([
            "-ac", str(channels),
            "-acodec", pcm_codec,
            "-rf64", "auto",
            out_path,
        ])

        resample_part = f"-ar {output_sr.rate} " if output_sr.needs_resample else ""
        summary = (
            f"[{sync_mode.filter_name}] {' | '.join(notes)} | "
            f"{resample_part}-ac {channels} -acodec {pcm_codec} -rf64 auto"
        )
        return cmd, summary

    # Extra stage appended after the offset.  These only matter for inputs whose
    # timestamps are themselves broken (stream captures, VFR remuxes); on a
    # well-formed file they are no-ops, which is exactly why the modes that used
    # to differ only by a passthrough filter no longer exist.
    _MODE_TAIL_FILTERS: dict[SyncMode, str] = {
        SyncMode.ARESAMPLE: "aresample=async=1",
    }

    @staticmethod
    def _build_offset_stage(delay_ms: float, channels: int) -> tuple[str, str]:
        """Build the constant-offset stage of the chain."""
        abs_ms = abs(delay_ms)
        if abs_ms <= 0.01:
            return "", "offset 0 ms"

        if delay_ms > 0:
            # Track runs early → pad the head with silence.
            delay_str = "|".join([f"{abs_ms:.3f}"] * max(1, channels))
            return f"adelay={delay_str}:all=1", f"adelay {abs_ms:.1f} ms"

        # Track runs late → drop the head.
        trim_sec = abs_ms / 1000.0
        return (
            f"atrim=start={trim_sec:.6f},asetpts=PTS-STARTPTS",
            f"atrim {trim_sec:.3f} s",
        )

    @staticmethod
    def _build_drift_stage(
        drift_ms_per_min: float,
        sync_mode: SyncMode,
    ) -> tuple[str, float, str]:
        """Build the time-stretch stage that cancels a progressive drift.

        ``rubberband`` is offered as a genuine alternative engine here rather
        than as a passthrough: for a track that needs retiming it is the higher
        quality stretcher, and for a track that does not it is never inserted.

        ``atempo`` is the default because it takes the factor as a float.  An
        ``asetrate`` resample chain would have to round to an integer sample
        rate, leaving roughly 0.5 ms/min of uncorrected drift on a 0.1 %
        correction — enough for an hour of audio to still slide half a frame.
        """
        factor = FFmpegWrapper.drift_tempo_factor(drift_ms_per_min)
        if sync_mode is SyncMode.RUBBERBAND:
            return (
                f"rubberband=tempo={factor:.12f}:pitch=1.0"
                f":transients=smooth:detector=compound",
                factor,
                f"drift {drift_ms_per_min:+.2f} ms/min → rubberband tempo={factor:.9f}",
            )
        return (
            f"atempo={factor:.12f}",
            factor,
            f"drift {drift_ms_per_min:+.2f} ms/min → atempo={factor:.9f}",
        )

    # ── FFmpeg AC3/EAC3 Encoding ────────────────────────────────────────

    def encode_to_ac3_eac3(
        self,
        input_wav: str,
        output_path: str,
        fmt: DeewFormat,
        bitrate: int,
        channels: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """WAV dosyasını FFmpeg ile AC3 veya EAC3 formatına dönüştürür.

        Args:
            input_wav: Giriş WAV dosyasının yolu.
            output_path: Çıktı dosyasının yolu.
            fmt: Çıktı formatı (DD → ac3, DDP → eac3).
            bitrate: Bitrate (kbps).
            channels: Kanal sayısı.  ``None`` ise kaynak korunur.

        Returns:
            Oluşturulan FFmpeg komutunun özet açıklaması (log için).

        Raises:
            RuntimeError: FFmpeg encoding hatası.
        """
        # Codec seçimi: DD → ac3, DDP → eac3
        codec = "ac3" if fmt == DeewFormat.DD else "eac3"

        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-y",
            "-i", input_wav,
            "-acodec", codec,
            "-b:a", f"{bitrate}k",
        ]

        if channels is not None:
            cmd.extend(["-ac", str(channels)])

        cmd.append(output_path)

        cmd_summary = (
            f"ffmpeg … -acodec {codec} -b:a {bitrate}k"
            f"{f' -ac {channels}' if channels else ''}"
            f" → {os.path.basename(output_path)}"
        )

        result = self._run_command(
            cmd,
            timeout=self._get_ffmpeg_timeout(input_wav),
            cancel_event=cancel_event,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"FFmpeg AC3/EAC3 encoding error:\n{stderr_tail}")

        return cmd_summary

    # ── FFmpeg AAC / FLAC / Opus Encoding ─────────────────────────────────

    def encode_to_aac(
        self,
        input_path: str,
        output_path: str,
        bitrate: int = 256,
        channels: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Encode audio to AAC format using FFmpeg.

        Args:
            input_path: Path to input audio file
            output_path: Path to output .m4a file
            bitrate: Bitrate in kbps
            channels: Number of output channels (None = keep original)

        Returns:
            Summary string

        Raises:
            RuntimeError: If encoding fails
        """
        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-y",
            "-i", input_path,
            "-c:a", "aac",
            "-b:a", f"{bitrate}k",
        ]
        if channels is not None:
            cmd.extend(["-ac", str(channels)])
        cmd.append(output_path)

        result = self._run_command(
            cmd,
            timeout=self._get_ffmpeg_timeout(input_path),
            cancel_event=cancel_event,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"FFmpeg AAC encoding error:\n{stderr_tail}")

        return f"AAC {bitrate} kbps"

    def encode_to_flac(
        self,
        input_path: str,
        output_path: str,
        compression: int = 5,
        bit_depth: int = 24,
        channels: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Encode audio to FLAC format using FFmpeg.

        Args:
            input_path: Path to input audio file
            output_path: Path to output .flac file
            compression: Compression level 0-12
            bit_depth: Bit depth (16 or 24)
            channels: Number of output channels (None = keep original)

        Returns:
            Summary string

        Raises:
            RuntimeError: If encoding fails
        """
        compression = max(0, min(12, compression))
        # FFmpeg's FLAC encoder only accepts s16 and s32/24-bit output, so snap
        # anything else to the nearest supported depth instead of silently
        # dropping the flag and writing whatever the decoder produced.
        effective_bit_depth = 16 if bit_depth <= 20 else 24
        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-y",
            "-i", input_path,
            "-c:a", "flac",
            "-compression_level", str(compression),
        ]
        if channels is not None:
            cmd.extend(["-ac", str(channels)])

        # Add bit depth (sample format)
        if effective_bit_depth == 16:
            cmd.extend(["-sample_fmt", "s16"])
        else:
            cmd.extend(["-sample_fmt", "s32", "-bits_per_raw_sample", "24"])

        cmd.append(output_path)

        result = self._run_command(
            cmd,
            timeout=self._get_ffmpeg_timeout(input_path),
            cancel_event=cancel_event,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"FFmpeg FLAC encoding error:\n{stderr_tail}")

        return f"FLAC (compression={compression}, {effective_bit_depth}-bit)"

    def encode_to_opus(
        self,
        input_path: str,
        output_path: str,
        bitrate: int = 128,
        channels: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Encode audio to Opus format using FFmpeg.

        Args:
            input_path: Path to input audio file
            output_path: Path to output .opus file
            bitrate: Bitrate in kbps
            channels: Number of output channels (None = keep original)

        Returns:
            Summary string

        Raises:
            RuntimeError: If encoding fails
        """
        cmd = [
            resolve_tool("ffmpeg"),
            "-v", "error",
            "-nostdin",
            "-y",
            "-i", input_path,
            "-c:a", "libopus",
            "-b:a", f"{bitrate}k",
        ]
        if channels is not None:
            cmd.extend(["-ac", str(channels)])
        cmd.append(output_path)

        result = self._run_command(
            cmd,
            timeout=self._get_ffmpeg_timeout(input_path),
            cancel_event=cancel_event,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"FFmpeg Opus encoding error:\n{stderr_tail}")

        return f"Opus {bitrate} kbps"

    # ── Yardımcı Metotlar ────────────────────────────────────────────────

    def _run_command(
        self,
        cmd: list[str],
        timeout: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Komutu güvenli şekilde çalıştırır.

        Args:
            cmd: Çalıştırılacak komut ve argümanları.
            timeout: Zaman aşımı (saniye).

        Returns:
            ``CompletedProcess`` nesnesi.

        Raises:
            RuntimeError: Zaman aşımı durumunda.
            OSError: Komut bulunamazsa.
        """
        if cancel_event is None:
            try:
                return self._runner.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"'{cmd[0]}' command did not complete within {timeout} seconds. "
                    f"The file may be corrupted or inaccessible."
                ) from exc
            except FileNotFoundError as exc:
                raise OSError(
                    f"'{cmd[0]}' not found. Make sure FFmpeg is in your PATH."
                ) from exc

        return self._run_text_command(cmd, timeout=timeout, cancel_event=cancel_event)

    def _run_binary_command(
        self,
        cmd: list[str],
        timeout: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Run a command and capture binary stdout/stderr."""
        return run_binary_process(
            cmd,
            timeout=timeout,
            cancel_event=cancel_event,
            not_found_message=f"'{cmd[0]}' not found. Make sure FFmpeg is in your PATH.",
            timeout_message=(
                f"'{cmd[0]}' command did not complete within {timeout} seconds. "
                f"The file may be corrupted or inaccessible."
            ),
        )

    def _run_text_command(
        self,
        cmd: list[str],
        timeout: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command with cancellation support and capture text output."""
        return run_text_process(
            cmd,
            timeout=timeout,
            cancel_event=cancel_event,
            not_found_message=f"'{cmd[0]}' not found. Make sure FFmpeg is in your PATH.",
            timeout_message=(
                f"'{cmd[0]}' command did not complete within {timeout} seconds. "
                f"The file may be corrupted or inaccessible."
            ),
        )

    def _get_ffmpeg_timeout(self, *input_paths: str) -> int:
        """Scale FFmpeg timeout for large or slow-to-decode audio inputs."""
        complex_exts = {
            ".thd", ".dtshd", ".dts", ".mka",
            ".mkv", ".mp4", ".m4v", ".webm", ".ts", ".mts",
        }

        bonus_sec = sum(
            self._config.ffmpeg_complex_format_bonus_sec
            for path in input_paths
            if path and os.path.splitext(path)[1].lower() in complex_exts
        )

        return scale_timeout_for_size(
            self._config.ffmpeg_timeout_sec,
            *input_paths,
            per_gib_sec=self._config.ffmpeg_timeout_per_gib_sec,
            max_sec=self._config.ffmpeg_max_timeout_sec,
            extra_sec=bonus_sec,
        )

    @staticmethod
    def _parse_ffprobe_output(stdout: str) -> dict[str, str]:
        """FFprobe çıktısını anahtar-değer çiftlerine ayrıştırır."""
        info: dict[str, str] = {}
        for line in stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                info[key.strip()] = value.strip()
        return info

    @staticmethod
    def _get_stream_extension(stream: dict[str, str]) -> str:
        """Return the preferred file extension for an extracted stream."""
        codec_name = stream.get("codec_name", "unknown").lower()
        # FFmpeg can demux raw DTS-HD inputs, but common builds do not expose a
        # writable raw DTS-HD muxer. Keep extracted DTS-HD streams on the DTS
        # extension so container extraction remains copy-safe.
        if codec_name in {"dts", "dtshd"}:
            return ".dts"
        return CODEC_EXTENSION_MAP.get(codec_name, ".mka")

    @staticmethod
    def _get_stream_codec_display(stream: dict[str, str]) -> str:
        """Build a more descriptive codec label for the stream picker."""
        codec_name = stream.get("codec_name", "unknown")
        profile = stream.get("profile", "").strip()

        if codec_name.lower() == "dts" and FFmpegWrapper._is_dtshd_stream(stream):
            return profile or "DTS-HD"
        if codec_name.lower() == "truehd":
            return profile or "TrueHD"
        if profile:
            return f"{codec_name} ({profile})"
        return codec_name

    @staticmethod
    def _is_dtshd_stream(stream: dict[str, str]) -> bool:
        """Detect DTS-HD variants from ffprobe stream metadata."""
        if stream.get("codec_name", "").lower() != "dts":
            return False

        haystack = " ".join(
            filter(
                None,
                (
                    stream.get("profile", ""),
                    stream.get("codec_long_name", ""),
                ),
            )
        ).lower()
        markers = (
            "dts-hd",
            "dts hd",
            "master audio",
            "high resolution",
            "hra",
        )
        return any(marker in haystack for marker in markers)

    @staticmethod
    def _safe_int(value: str | None, default: int, minimum: int = 0) -> int:
        """String'i güvenli şekilde int'e çevirir."""
        if value is None:
            return default
        try:
            return max(minimum, int(value))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _determine_bit_depth(info: dict[str, str]) -> int:
        """FFprobe bilgilerinden bit derinliğini belirler.

        Önce ``bits_per_raw_sample`` kontrol edilir, yoksa ``sample_fmt``
        alanından çıkarım yapılır.

        Args:
            info: FFprobe anahtar-değer çiftleri.

        Returns:
            Bit derinliği (16, 24 veya 32).
        """
        # Önce doğrudan bit bilgisini dene
        raw_bits_str = info.get("bits_per_raw_sample", "0")
        try:
            raw_bits = int(raw_bits_str)
        except (ValueError, TypeError):
            raw_bits = 0

        if raw_bits > 0:
            return raw_bits

        # sample_fmt'den çıkarım yap
        sfmt = info.get("sample_fmt", "").lower()
        fmt_to_bits: dict[str, int] = {
            "s16": 16,
            "s24": 24,
            "s32": 32,
            "s64": 32,
            "flt": 32,
            "fltp": 32,
            "dbl": 32,
            "dblp": 32,
        }
        for fmt_key, bits in fmt_to_bits.items():
            if fmt_key in sfmt:
                return bits

        return 32  # Varsayılan

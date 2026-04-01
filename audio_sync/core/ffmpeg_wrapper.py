"""FFmpeg/FFprobe komut satırı arayüzü.

Bu modül dış süreç çağrılarını soyutlayarak:
  - Timeout desteği sağlar
  - FFmpeg varlık kontrolü yapar
  - Test'te mock edilebilir ``CommandRunner`` protokolü sunar
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import warnings
from typing import Protocol

from audio_sync.config import DeewFormat, FpsConversion, PcmCodec, SyncConfig, SyncMode, SYNC_CONFIG
from audio_sync.core.models import AudioInfo, OutputSampleRate


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
    def check_availability() -> None:
        """FFmpeg ve FFprobe'un sistemde kurulu olduğunu doğrular.

        Raises:
            OSError: Araçlardan biri bulunamazsa.
        """
        for tool in ("ffmpeg", "ffprobe"):
            if shutil.which(tool) is None:
                raise OSError(
                    f"'{tool}' not found. Please install FFmpeg:\n"
                    f"  https://ffmpeg.org/download.html\n"
                    f"  Windows: winget install ffmpeg\n"
                    f"  macOS:   brew install ffmpeg\n"
                    f"  Linux:   sudo apt install ffmpeg"
                )

    # ── Ses Bilgisi Okuma ────────────────────────────────────────────────

    def probe_audio(self, path: str) -> AudioInfo:
        """FFprobe ile ses dosyasının meta verisini okur.

        Args:
            path: Ses dosyasının yolu.

        Returns:
            ``AudioInfo`` nesnesi.  FFprobe başarısız olursa varsayılan değerler
            döndürülür ve uyarı bilgisi ``warnings`` listesine eklenir.
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries",
            "stream=channels,codec_name,sample_fmt,bits_per_raw_sample,sample_rate",
            "-of", "default=noprint_wrappers=1",
            path,
        ]

        result = self._run_command(cmd, timeout=self._config.ffprobe_timeout_sec)

        if result.returncode != 0:
            warnings.warn(
                f"FFprobe could not read audio info, using defaults "
                f"(32-bit, stereo, 48 kHz): {path}",
                RuntimeWarning,
                stacklevel=2,
            )
            return AudioInfo.default()

        info = self._parse_ffprobe_output(result.stdout)

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
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries",
            "stream=index,codec_name,channels,sample_rate,bit_rate,bits_per_raw_sample",
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
            streams.append({
                "index": str(s.get("index", 0)),
                "codec_name": s.get("codec_name", "unknown"),
                "channels": str(s.get("channels", 0)),
                "sample_rate": str(s.get("sample_rate", 0)),
                "bit_rate": str(s.get("bit_rate", "N/A")),
                "language": tags.get("language", "und"),
                "title": tags.get("title", ""),
            })
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
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-map", f"0:{stream_index}",
            "-c", "copy",
            output_path,
        ]
        result = self._run_command(cmd, timeout=self._config.ffmpeg_timeout_sec)
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"Audio stream extraction error:\n{stderr_tail}")

    # ── Mono WAV Conversion ──────────────────────────────────────────────

    def to_wav_mono(self, src: str, out_path: str) -> None:
        """Senkron analizi için tek kanallı, düşük örneklemeli WAV hazırlar.

        Args:
            src: Kaynak ses dosyasının yolu.
            out_path: Çıktı WAV dosyasının yolu.

        Raises:
            RuntimeError: FFmpeg dönüşüm hatası.
        """
        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-ar", str(self._config.analysis_sample_rate),
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-f", "wav",
            out_path,
        ]
        result = self._run_command(cmd, timeout=self._config.ffmpeg_timeout_sec)
        if result.returncode != 0:
            stderr_tail = result.stderr[-400:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"Mono conversion error:\n{stderr_tail}")

    # ── FPS Dönüşümü ────────────────────────────────────────────────────

    def apply_fps_conversion(
        self,
        src: str,
        out_path: str,
        conversion: FpsConversion,
        audio_info: AudioInfo,
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

        # atempo filtresi: >1.0 sesi uzatır (yavaşlatır), <1.0 kısaltır (hızlandırır)
        # FPS dönüşümünde kaynak FPS > hedef FPS ise ses uzamalı → atempo = 1/ratio
        # Kaynak FPS < hedef FPS ise ses kısalmalı → atempo = 1/ratio
        # Genel formül: atempo = 1 / ratio = target_fps / source_fps
        atempo_value = 1.0 / ratio

        pcm_codec = audio_info.codec.codec_name
        channels = audio_info.channels
        sample_rate = audio_info.sample_rate

        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-af", f"atempo={atempo_value:.15f}",
            "-ac", str(channels),
            "-ar", str(sample_rate),
            "-acodec", pcm_codec,
            "-rf64", "auto",
            out_path,
        ]

        cmd_summary = (
            f"FPS dönüşümü: {conversion.display_name}  |  "
            f"atempo={atempo_value:.6f}  |  "
            f"oran: {ratio:.6f}  |  "
            f"bit: {audio_info.bits}  |  sr: {sample_rate} Hz"
        )

        result = self._run_command(cmd, timeout=self._config.ffmpeg_timeout_sec)
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"FPS conversion error:\n{stderr_tail}")

        return cmd_summary

    # ── Senkronizasyon Uygulama ──────────────────────────────────────────

    def apply_sync(
        self,
        src_orig: str,
        sync_orig: str,
        delay_ms: float,
        audio_info: AudioInfo,
        output_sr: OutputSampleRate,
        out_path: str,
        sync_mode: SyncMode = SyncMode.ADELAY_AMIX,
    ) -> str:
        """Orijinal dosyaları senkronize eder, karıştırır ve WAV olarak yazar.

        Args:
            src_orig: Kaynak (referans) ses dosyası yolu.
            sync_orig: Senkronize edilecek ses dosyası yolu.
            delay_ms: Hesaplanan gecikme (ms).
                Pozitif → sync ses erkende, kaynak geciktirilir.
                Negatif → sync ses geçte, sync geciktirilir.
            audio_info: Senkronize edilecek sesin bilgileri.
            output_sr: Çıktı örnekleme oranı kararı.
            out_path: Çıktı dosyası yolu.
            sync_mode: Senkronizasyon filtre modu.

        Returns:
            Oluşturulan FFmpeg komutunun özet açıklaması (log için).

        Raises:
            RuntimeError: FFmpeg senkronizasyon hatası.
        """
        channels = audio_info.channels
        pcm_codec = audio_info.codec.codec_name
        abs_ms = abs(delay_ms)

        # Senkronizasyon moduna göre komut oluştur
        if sync_mode == SyncMode.ADELAY_AMIX:
            cmd, cmd_summary = self._build_sync_adelay_amix(
                src_orig, sync_orig, delay_ms, abs_ms, channels, pcm_codec, output_sr, out_path,
            )
        elif sync_mode == SyncMode.ARESAMPLE:
            cmd, cmd_summary = self._build_sync_aresample(
                src_orig, sync_orig, delay_ms, abs_ms, channels, pcm_codec, output_sr, out_path,
            )
        elif sync_mode == SyncMode.ATEMPO:
            cmd, cmd_summary = self._build_sync_atempo(
                src_orig, sync_orig, delay_ms, abs_ms, channels, pcm_codec, output_sr, out_path,
            )
        elif sync_mode == SyncMode.RUBBERBAND:
            cmd, cmd_summary = self._build_sync_rubberband(
                src_orig, sync_orig, delay_ms, abs_ms, channels, pcm_codec, output_sr, out_path,
            )
        elif sync_mode == SyncMode.APAD:
            cmd, cmd_summary = self._build_sync_apad(
                src_orig, sync_orig, delay_ms, abs_ms, channels, pcm_codec, output_sr, out_path,
            )
        elif sync_mode == SyncMode.ASYNCTS:
            cmd, cmd_summary = self._build_sync_asyncts(
                src_orig, sync_orig, delay_ms, abs_ms, channels, pcm_codec, output_sr, out_path,
            )
        else:
            # Fallback to default
            cmd, cmd_summary = self._build_sync_adelay_amix(
                src_orig, sync_orig, delay_ms, abs_ms, channels, pcm_codec, output_sr, out_path,
            )

        result = self._run_command(cmd, timeout=self._config.ffmpeg_timeout_sec)
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"FFmpeg synchronization error:\n{stderr_tail}")

        return cmd_summary

    # ── Senkronizasyon Mod Oluşturucuları ─────────────────────────────────

    def _build_sync_adelay_amix(
        self, src: str, sync: str, delay_ms: float, abs_ms: float,
        channels: int, pcm_codec: str, output_sr: OutputSampleRate, out_path: str,
    ) -> tuple[list[str], str]:
        """adelay + amix modu — varsayılan ve en güvenilir yöntem."""
        delay_str = "|".join([f"{abs_ms:.3f}"] * channels)

        if delay_ms >= 0:
            flt = (
                f"[0:a]adelay={delay_str}[delayed_src];"
                f"[delayed_src][1:a]amix=inputs=2:duration=longest:dropout_transition=0[out]"
            )
        else:
            flt = (
                f"[1:a]adelay={delay_str}[delayed_sync];"
                f"[0:a][delayed_sync]amix=inputs=2:duration=longest:dropout_transition=0[out]"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-i", sync,
            "-filter_complex", flt,
            "-map", "[out]",
        ]

        if output_sr.needs_resample:
            cmd.extend(["-ar", str(output_sr.rate)])

        cmd.extend([
            "-ac", str(channels),
            "-acodec", pcm_codec,
            "-rf64", "auto",
            out_path,
        ])

        resample_part = f"-ar {output_sr.rate} " if output_sr.needs_resample else ""
        summary = f"[adelay+amix] ffmpeg … {resample_part}-ac {channels} -acodec {pcm_codec} -rf64 auto"
        return cmd, summary

    def _build_sync_aresample(
        self, src: str, sync: str, delay_ms: float, abs_ms: float,
        channels: int, pcm_codec: str, output_sr: OutputSampleRate, out_path: str,
    ) -> tuple[list[str], str]:
        """aresample modu — örnekleme oranı tabanlı senkronizasyon.

        Sync dosyasına adelay uygulayıp aresample ile yüksek kaliteli
        resampling yapar.
        """
        delay_str = "|".join([f"{abs_ms:.3f}"] * channels)

        if delay_ms >= 0:
            flt = (
                f"[0:a]adelay={delay_str},aresample=async=1[delayed_src];"
                f"[delayed_src][1:a]amix=inputs=2:duration=longest:dropout_transition=0[out]"
            )
        else:
            flt = (
                f"[1:a]adelay={delay_str},aresample=async=1[delayed_sync];"
                f"[0:a][delayed_sync]amix=inputs=2:duration=longest:dropout_transition=0[out]"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-i", sync,
            "-filter_complex", flt,
            "-map", "[out]",
        ]

        if output_sr.needs_resample:
            cmd.extend(["-ar", str(output_sr.rate)])

        cmd.extend([
            "-ac", str(channels),
            "-acodec", pcm_codec,
            "-rf64", "auto",
            out_path,
        ])

        resample_part = f"-ar {output_sr.rate} " if output_sr.needs_resample else ""
        summary = f"[aresample] ffmpeg … {resample_part}-ac {channels} -acodec {pcm_codec} -rf64 auto"
        return cmd, summary

    def _build_sync_atempo(
        self, src: str, sync: str, delay_ms: float, abs_ms: float,
        channels: int, pcm_codec: str, output_sr: OutputSampleRate, out_path: str,
    ) -> tuple[list[str], str]:
        """atempo modu — kırpma tabanlı senkronizasyon (sessizlik ekleme yerine).

        ``adelay`` modundan farklı olarak, geç kalan akışa sessizlik eklemek
        yerine erken başlayan akışın başından ``atrim`` ile kırpma yapar.
        Bu sayede çıktıda sessizlik boşluğu oluşmaz.

        Küçük gecikmelerde (<50 ms) ek olarak ``atempo`` filtresi ile
        örnekleme-altı hassasiyette ince ayar yapılır.
        """
        delay_sec = abs_ms / 1000.0

        # Küçük gecikmelerde atempo ile ince ayar (50 ms eşiği)
        # atempo aralığı: 0.5–100.0; burada çok küçük sapmalar kullanıyoruz
        use_atempo_fine = abs_ms < 50.0 and abs_ms > 0.1
        ratio: float = 1.0  # varsayılan; use_atempo_fine True ise üzerine yazılır

        if delay_ms >= 0:
            # sync ses ileride → kaynağın başını kırp
            if use_atempo_fine:
                # Çok küçük gecikme: atempo ile ince ayar (kırpma yerine)
                # Kaynak sesi çok hafif hızlandırarak senkronize et
                # Yaklaşık 10 saniyelik pencerede delay_ms kadar telafi
                window_sec = 10.0
                ratio = 1.0 + (delay_sec / window_sec)
                ratio = max(0.5, min(2.0, ratio))
                flt = (
                    f"[0:a]atempo={ratio:.10f}[adj_src];"
                    f"[adj_src][1:a]amix=inputs=2:duration=longest:dropout_transition=0[out]"
                )
            else:
                flt = (
                    f"[0:a]atrim=start={delay_sec:.6f},asetpts=PTS-STARTPTS[trimmed_src];"
                    f"[trimmed_src][1:a]amix=inputs=2:duration=shortest:dropout_transition=0[out]"
                )
        else:
            # sync ses geride → sync'in başını kırp
            if use_atempo_fine:
                window_sec = 10.0
                ratio = 1.0 + (delay_sec / window_sec)
                ratio = max(0.5, min(2.0, ratio))
                flt = (
                    f"[1:a]atempo={ratio:.10f}[adj_sync];"
                    f"[0:a][adj_sync]amix=inputs=2:duration=longest:dropout_transition=0[out]"
                )
            else:
                flt = (
                    f"[1:a]atrim=start={delay_sec:.6f},asetpts=PTS-STARTPTS[trimmed_sync];"
                    f"[0:a][trimmed_sync]amix=inputs=2:duration=shortest:dropout_transition=0[out]"
                )

        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-i", sync,
            "-filter_complex", flt,
            "-map", "[out]",
        ]

        if output_sr.needs_resample:
            cmd.extend(["-ar", str(output_sr.rate)])

        cmd.extend([
            "-ac", str(channels),
            "-acodec", pcm_codec,
            "-rf64", "auto",
            out_path,
        ])

        resample_part = f"-ar {output_sr.rate} " if output_sr.needs_resample else ""
        mode_detail = f"atempo={ratio:.6f}" if use_atempo_fine else f"atrim={delay_sec:.3f}s"
        summary = f"[atempo] {mode_detail} | {resample_part}-ac {channels} -acodec {pcm_codec} -rf64 auto"
        return cmd, summary

    def _build_sync_rubberband(
        self, src: str, sync: str, delay_ms: float, abs_ms: float,
        channels: int, pcm_codec: str, output_sr: OutputSampleRate, out_path: str,
    ) -> tuple[list[str], str]:
        """rubberband modu — yüksek kaliteli pitch-korumalı zaman uzatma.

        librubberband tabanlı pitch-korumalı zaman uzatma kullanır.
        FFmpeg'in ``--enable-librubberband`` ile derlenmiş olması gerekir.

        Erken başlayan akışın başını ``atrim`` ile kırpar, ardından
        ``rubberband`` filtresi ile yüksek kaliteli yeniden örnekleme yapar.
        Bu, ``atempo`` modundan daha yüksek ses kalitesi sağlar.
        """
        delay_sec = abs_ms / 1000.0

        if delay_ms >= 0:
            # sync ses ileride → kaynağın başını kırp + rubberband kalite iyileştirme
            flt = (
                f"[0:a]atrim=start={delay_sec:.6f},asetpts=PTS-STARTPTS,"
                f"rubberband=tempo=1.0:pitch=1.0:transients=smooth:detector=compound[adj_src];"
                f"[adj_src][1:a]amix=inputs=2:duration=shortest:dropout_transition=0[out]"
            )
        else:
            # sync ses geride → sync'in başını kırp + rubberband kalite iyileştirme
            flt = (
                f"[1:a]atrim=start={delay_sec:.6f},asetpts=PTS-STARTPTS,"
                f"rubberband=tempo=1.0:pitch=1.0:transients=smooth:detector=compound[adj_sync];"
                f"[0:a][adj_sync]amix=inputs=2:duration=shortest:dropout_transition=0[out]"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-i", sync,
            "-filter_complex", flt,
            "-map", "[out]",
        ]

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
            f"[rubberband] atrim={delay_sec:.3f}s+rubberband | "
            f"{resample_part}-ac {channels} -acodec {pcm_codec} -rf64 auto"
        )
        return cmd, summary

    def _build_sync_apad(
        self, src: str, sync: str, delay_ms: float, abs_ms: float,
        channels: int, pcm_codec: str, output_sr: OutputSampleRate, out_path: str,
    ) -> tuple[list[str], str]:
        """apad + atrim modu — sessizlik ekleme/kırpma tabanlı senkronizasyon.

        Gecikme yönüne göre erken başlayan akışın başını kırpar (``atrim``)
        ve gerekirse sonuna sessizlik ekler (``apad``) böylece her iki akış
        aynı uzunlukta kalır.

        Not: ``apad`` filtresi sesin **sonuna** sessizlik ekler, başına değil.
        Bu nedenle zaman kaydırma ``atrim`` ile yapılır; ``apad`` yalnızca
        kırpılan akışın uzunluğunu korumak için kullanılır.
        """
        delay_sec = abs_ms / 1000.0

        if delay_ms >= 0:
            # sync ses ileride → kaynağın başını kırp + sonuna pad ekle
            flt = (
                f"[0:a]atrim=start={delay_sec:.6f},asetpts=PTS-STARTPTS,"
                f"apad=whole_dur=0[trimmed_src];"
                f"[trimmed_src][1:a]amix=inputs=2:duration=longest:dropout_transition=0[out]"
            )
        else:
            # sync ses geride → sync'in başını kırp + sonuna pad ekle
            flt = (
                f"[1:a]atrim=start={delay_sec:.6f},asetpts=PTS-STARTPTS,"
                f"apad=whole_dur=0[trimmed_sync];"
                f"[0:a][trimmed_sync]amix=inputs=2:duration=longest:dropout_transition=0[out]"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-i", sync,
            "-filter_complex", flt,
            "-map", "[out]",
        ]

        if output_sr.needs_resample:
            cmd.extend(["-ar", str(output_sr.rate)])

        cmd.extend([
            "-ac", str(channels),
            "-acodec", pcm_codec,
            "-rf64", "auto",
            out_path,
        ])

        resample_part = f"-ar {output_sr.rate} " if output_sr.needs_resample else ""
        summary = f"[apad+atrim] ffmpeg … {resample_part}-ac {channels} -acodec {pcm_codec} -rf64 auto"
        return cmd, summary

    def _build_sync_asyncts(
        self, src: str, sync: str, delay_ms: float, abs_ms: float,
        channels: int, pcm_codec: str, output_sr: OutputSampleRate, out_path: str,
    ) -> tuple[list[str], str]:
        """asyncts modu — eski FFmpeg otomatik ses senkronizasyonu.

        aresample=async=1000 ile agresif senkronizasyon yapar.
        Eski FFmpeg sürümleriyle uyumlu.
        """
        delay_str = "|".join([f"{abs_ms:.3f}"] * channels)

        if delay_ms >= 0:
            flt = (
                f"[0:a]adelay={delay_str},aresample=async=1000[delayed_src];"
                f"[delayed_src][1:a]amix=inputs=2:duration=longest:dropout_transition=0[out]"
            )
        else:
            flt = (
                f"[1:a]adelay={delay_str},aresample=async=1000[delayed_sync];"
                f"[0:a][delayed_sync]amix=inputs=2:duration=longest:dropout_transition=0[out]"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-i", sync,
            "-filter_complex", flt,
            "-map", "[out]",
        ]

        if output_sr.needs_resample:
            cmd.extend(["-ar", str(output_sr.rate)])

        cmd.extend([
            "-ac", str(channels),
            "-acodec", pcm_codec,
            "-rf64", "auto",
            out_path,
        ])

        resample_part = f"-ar {output_sr.rate} " if output_sr.needs_resample else ""
        summary = f"[asyncts] ffmpeg … {resample_part}-ac {channels} -acodec {pcm_codec} -rf64 auto"
        return cmd, summary

    # ── FFmpeg Dolby Encoding ────────────────────────────────────────────

    def encode_to_dolby(
        self,
        input_wav: str,
        output_path: str,
        fmt: DeewFormat,
        bitrate: int,
        channels: int | None = None,
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
            "ffmpeg", "-y",
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

        result = self._run_command(cmd, timeout=self._config.ffmpeg_timeout_sec)
        if result.returncode != 0:
            stderr_tail = result.stderr[-600:] if result.stderr else "(stderr empty)"
            raise RuntimeError(f"FFmpeg Dolby encoding error:\n{stderr_tail}")

        return cmd_summary

    # ── Yardımcı Metotlar ────────────────────────────────────────────────

    def _run_command(
        self,
        cmd: list[str],
        timeout: int | None = None,
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
        try:
            return self._runner.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"'{cmd[0]}' command did not complete within {timeout} seconds. "
                f"The file may be corrupted or inaccessible."
            )
        except FileNotFoundError:
            raise OSError(
                f"'{cmd[0]}' not found. Make sure FFmpeg is in your PATH."
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

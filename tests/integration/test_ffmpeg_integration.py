from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

from audio_sync.config import SYNC_CONFIG, DeewFormat, PcmCodec, SyncMode, resolve_tool
from audio_sync.core.analyzer import AudioAnalyzer
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper
from audio_sync.core.models import OutputSampleRate

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def wrapper() -> FFmpegWrapper:
    try:
        FFmpegWrapper.check_availability()
    except OSError as exc:
        pytest.skip(str(exc))
    return FFmpegWrapper()


def run_ffmpeg(*args: str) -> None:
    result = subprocess.run(
        [resolve_tool("ffmpeg"), "-v", "error", "-nostdin", "-y", *args],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr


def rich_signal(rate: int = 44_100, seconds: int = 12) -> np.ndarray:
    rng = np.random.default_rng(314159)
    time = np.arange(rate * seconds) / rate
    audio = rng.normal(0, 0.2, time.size)
    audio += 0.2 * np.sin(2 * np.pi * (220 + 18 * time) * time)
    audio *= 0.3 + 0.7 * np.sin(2 * np.pi * 0.61 * time) ** 2
    return np.asarray(np.clip(audio, -1, 1) * 30_000, dtype=np.int16)


def test_known_offset_reanalysis_and_sample_rate_policy(
    tmp_path: Path, wrapper: FFmpegWrapper
) -> None:
    rate = 44_100
    offset_samples = rate // 4
    source_data = rich_signal(rate)
    delayed_data = np.concatenate(
        (np.zeros(offset_samples, dtype=np.int16), source_data[:-offset_samples])
    )
    source = tmp_path / "source.wav"
    delayed = tmp_path / "delayed.wav"
    corrected = tmp_path / "corrected.wav"
    forced = tmp_path / "forced-48k.wav"
    wavfile.write(source, rate, source_data)
    wavfile.write(delayed, rate, delayed_data)

    analysis_config = replace(
        SYNC_CONFIG,
        fingerprint_enabled=False,
        min_audio_duration_sec=3,
        segment_duration_sec=2.0,
        local_search_sec=1.0,
    )
    analyzer = AudioAnalyzer(analysis_config)
    before = analyzer.calculate_delay_from_arrays(
        rate, source_data, delayed_data, skip_intro_sec=0, total_segments=8
    )
    assert before.delay_ms == pytest.approx(-250, abs=25)

    info = wrapper.probe_audio(str(delayed))
    wrapper.apply_sync(
        str(source),
        str(delayed),
        before.delay_ms,
        info,
        OutputSampleRate.decide(rate, rate, False),
        str(corrected),
        sync_mode=SyncMode.ADELAY_AMIX,
    )
    assert wrapper.probe_audio(str(corrected)).sample_rate == 44_100

    corrected_rate, corrected_pcm = wavfile.read(corrected)
    after = analyzer.calculate_delay_from_arrays(
        corrected_rate,
        source_data[: len(corrected_pcm)],
        corrected_pcm,
        skip_intro_sec=0,
        total_segments=8,
    )
    assert after.delay_ms == pytest.approx(0, abs=25)

    wrapper.apply_sync(
        str(source),
        str(delayed),
        before.delay_ms,
        info,
        OutputSampleRate.decide(rate, rate, True),
        str(forced),
    )
    assert wrapper.probe_audio(str(forced)).sample_rate == 48_000


def test_multi_stream_container_probe_and_extract(
    tmp_path: Path, wrapper: FFmpegWrapper
) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    container = tmp_path / "two-streams.mka"
    extracted = tmp_path / "extracted.wav"
    run_ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1:sample_rate=44100", str(first))
    run_ffmpeg("-f", "lavfi", "-i", "sine=frequency=880:duration=1:sample_rate=48000", str(second))
    run_ffmpeg(
        "-i", str(first), "-i", str(second), "-map", "0:a", "-map", "1:a",
        "-c:a", "pcm_s16le", str(container),
    )

    streams = wrapper.probe_audio_streams(str(container))
    assert len(streams) == 2
    assert {stream["sample_rate"] for stream in streams} == {"44100", "48000"}
    wrapper.extract_audio_stream(
        str(container), str(extracted), int(streams[1]["index"])
    )
    assert wrapper.probe_audio(str(extracted)).sample_rate == 48_000


@pytest.mark.parametrize(
    ("name", "encode"),
    [
        ("aac.m4a", lambda w, i, o: w.encode_to_aac(i, o, bitrate=96)),
        ("audio.flac", lambda w, i, o: w.encode_to_flac(i, o, compression=1, bit_depth=16)),
        ("audio.opus", lambda w, i, o: w.encode_to_opus(i, o, bitrate=64)),
        (
            "audio.ac3",
            lambda w, i, o: w.encode_to_ac3_eac3(i, o, DeewFormat.DD, bitrate=192),
        ),
        (
            "audio.eac3",
            lambda w, i, o: w.encode_to_ac3_eac3(i, o, DeewFormat.DDP, bitrate=192),
        ),
    ],
)
def test_basic_codec_smoke(tmp_path: Path, wrapper: FFmpegWrapper, name, encode) -> None:
    source = tmp_path / "codec-source.wav"
    if not source.exists():
        wavfile.write(source, 48_000, rich_signal(48_000, seconds=2))
    output = tmp_path / name
    encode(wrapper, str(source), str(output))
    assert output.stat().st_size > 0
    assert wrapper.probe_audio(str(output)).sample_rate == 48_000
    assert wrapper.probe_audio(str(output)).codec in {
        PcmCodec.S16LE,
        PcmCodec.S24LE,
        PcmCodec.S32LE,
    }

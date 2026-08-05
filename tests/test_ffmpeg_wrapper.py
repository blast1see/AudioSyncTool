from __future__ import annotations

import subprocess

import pytest

from audio_sync.config import PcmCodec, SyncMode
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper
from audio_sync.core.models import AudioInfo, AudioProbeError, OutputSampleRate


class FakeRunner:
    def __init__(self, result: subprocess.CompletedProcess[str]) -> None:
        self.result = result
        self.commands: list[list[str]] = []

    def run(self, cmd, **_kwargs):
        self.commands.append(cmd)
        return self.result


def completed(stdout: str = "", stderr: str = "", code: int = 0):
    return subprocess.CompletedProcess([], code, stdout, stderr)


def test_probe_audio_parses_metadata(monkeypatch) -> None:
    runner = FakeRunner(
        completed("channels=6\ncodec_name=pcm_s24le\nsample_fmt=s32\n"
                  "bits_per_raw_sample=24\nsample_rate=44100\n")
    )
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: name)
    info = FFmpegWrapper(runner=runner).probe_audio("input.wav")
    assert info == AudioInfo(6, PcmCodec.S24LE, 24, 44_100)
    assert "-select_streams" in runner.commands[0]


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (completed(stderr="invalid data", code=1), "invalid data"),
        (completed("codec_name=aac\n"), "incomplete"),
    ],
)
def test_probe_audio_never_uses_silent_defaults(monkeypatch, result, message) -> None:
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: name)
    with pytest.raises(AudioProbeError, match=message):
        FFmpegWrapper(runner=FakeRunner(result)).probe_audio("broken.audio")


def test_probe_audio_wraps_missing_ffprobe(monkeypatch) -> None:
    def missing(_name: str) -> str:
        raise OSError("configured binary is invalid")

    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", missing)
    with pytest.raises(AudioProbeError, match="configured binary is invalid"):
        FFmpegWrapper().probe_audio("input.wav")


def test_runtime_availability_requires_zero_exit(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return completed("version")

    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: name)
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.run_text_process", fake_run)
    FFmpegWrapper.check_availability()
    assert calls == [["ffmpeg", "-version"], ["ffprobe", "-version"]]

    monkeypatch.setattr(
        "audio_sync.core.ffmpeg_wrapper.run_text_process",
        lambda *_args, **_kwargs: completed(stderr="cannot start", code=2),
    )
    FFmpegWrapper.reset_availability_cache()
    with pytest.raises(OSError, match="cannot start"):
        FFmpegWrapper.check_availability()


def test_availability_is_cached_per_resolved_binary(monkeypatch) -> None:
    """Both the UI and the pipeline check availability; only probe once."""
    calls: list[list[str]] = []
    resolved = {"ffmpeg": "/opt/a/ffmpeg", "ffprobe": "/opt/a/ffprobe"}

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return completed("version")

    monkeypatch.setattr(
        "audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: resolved[name]
    )
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.run_text_process", fake_run)

    FFmpegWrapper.check_availability()
    FFmpegWrapper.check_availability()
    assert len(calls) == 2

    # Pointing at a different binary must re-probe rather than trust the cache.
    resolved["ffmpeg"] = "/opt/b/ffmpeg"
    FFmpegWrapper.check_availability()
    assert len(calls) == 4


@pytest.mark.parametrize(
    ("delay_ms", "expected"),
    [
        (12.5, "adelay=12.500|12.500"),
        (-12.5, "atrim=start=0.012500"),
        (0.0, "acopy"),
    ],
)
def test_offset_only_sync_never_stretches_time(monkeypatch, delay_ms, expected) -> None:
    """Without a measured drift, a constant offset must stay a constant offset."""
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: name)
    cmd, summary = FFmpegWrapper().build_sync_command(
        "sync.wav",
        delay_ms,
        AudioInfo(2, PcmCodec.S16LE, 16, 44_100),
        OutputSampleRate.decide(48_000, 44_100, False),
        "out.wav",
    )
    command = " ".join(cmd)
    assert expected in command
    assert "atempo=" not in command
    assert "rubberband" not in command
    assert "-ar" not in cmd
    assert summary


@pytest.mark.parametrize("mode", list(SyncMode))
def test_every_sync_mode_builds_and_runs(monkeypatch, mode: SyncMode) -> None:
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: name)
    runner = FakeRunner(completed())
    wrapper = FFmpegWrapper(runner=runner)
    summary = wrapper.apply_sync(
        "source.wav",
        "sync.wav",
        25.0,
        AudioInfo(2, PcmCodec.S16LE, 16, 44_100),
        OutputSampleRate.decide(48_000, 44_100, False),
        "out.wav",
        sync_mode=mode,
    )
    assert summary
    assert runner.commands
    assert "-ar" not in runner.commands[-1]


def test_forced_sample_rate_adds_ffmpeg_ar(monkeypatch) -> None:
    monkeypatch.setattr("audio_sync.core.ffmpeg_wrapper.resolve_tool", lambda name: name)
    runner = FakeRunner(completed())
    FFmpegWrapper(runner=runner).apply_sync(
        "source.wav",
        "sync.wav",
        -50,
        AudioInfo(1, PcmCodec.S16LE, 16, 44_100),
        OutputSampleRate.decide(44_100, 44_100, True),
        "out.wav",
    )
    command = runner.commands[-1]
    assert command[command.index("-ar") + 1] == "48000"

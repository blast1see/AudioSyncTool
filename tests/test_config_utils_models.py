from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_sync import config
from audio_sync.config import ToolPaths
from audio_sync.core.models import OutputSampleRate
from audio_sync.utils import parse_float, parse_int, short_name, validate_file


def test_numeric_parsing_and_clamping() -> None:
    assert parse_float(" 1,25 ", minimum=0, maximum=2) == 1.25
    assert parse_float("bad", default=3, maximum=2) == 2
    assert parse_int("4.9", minimum=2, maximum=4) == 4
    assert parse_int(None, default=7) == 7


def test_short_name_and_file_validation(tmp_path: Path) -> None:
    short = short_name("a" * 80 + ".wav", max_chars=30)
    assert len(short) <= 30
    assert short.endswith(".wav")

    audio = tmp_path / "audio.raw"
    with pytest.raises(FileNotFoundError):
        validate_file(str(audio), "Audio")
    audio.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        validate_file(str(audio), "Audio")
    audio.write_bytes(b"data")
    validate_file(str(audio), "Audio")


def test_output_sample_rate_preserves_synchronized_track() -> None:
    decision = OutputSampleRate.decide(48_000, 44_100, False)
    assert decision.rate is None
    assert not decision.needs_resample
    assert "44100" in decision.label

    forced = OutputSampleRate.decide(44_100, 44_100, True)
    assert forced.rate == 48_000
    assert forced.needs_resample


def test_tool_paths_round_trip_and_atomic_commit(tmp_path: Path, monkeypatch) -> None:
    settings_dir = tmp_path / "settings"
    settings_file = settings_dir / "tool_paths.json"
    monkeypatch.setattr(config, "_TOOL_PATHS_DIR", settings_dir)
    monkeypatch.setattr(config, "_TOOL_PATHS_FILE", settings_file)
    original = ToolPaths(ffmpeg="old")
    monkeypatch.setattr(config, "TOOL_PATHS", original)

    requested = ToolPaths(ffmpeg="ffmpeg-custom", ffprobe="ffprobe-custom")
    assert config.save_tool_paths(requested)
    assert config.TOOL_PATHS is requested
    payload = json.loads(settings_file.read_text(encoding="utf-8"))
    assert payload["tool_paths"] == requested.to_dict()
    assert config._load_tool_paths() == requested


def test_failed_tool_path_write_does_not_change_memory(tmp_path: Path, monkeypatch) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "_TOOL_PATHS_DIR", settings_dir)
    monkeypatch.setattr(config, "_TOOL_PATHS_FILE", settings_dir / "tool_paths.json")
    original = ToolPaths(ffmpeg="working")
    monkeypatch.setattr(config, "TOOL_PATHS", original)

    def fail_replace(_source, _target) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(config.os, "replace", fail_replace)
    assert not config.save_tool_paths(ToolPaths(ffmpeg="broken"))
    assert config.TOOL_PATHS is original
    assert not list(settings_dir.glob("*.tmp"))


def test_resolve_tool_prefers_custom_then_path(tmp_path: Path, monkeypatch) -> None:
    custom = tmp_path / "ffmpeg.exe"
    custom.write_bytes(b"binary")
    monkeypatch.setattr(config, "TOOL_PATHS", ToolPaths(ffmpeg=str(custom)))
    assert config.resolve_tool("ffmpeg") == str(custom)

    monkeypatch.setattr(config, "TOOL_PATHS", ToolPaths())
    monkeypatch.setattr(config.shutil, "which", lambda name: f"/tools/{name}")
    assert config.resolve_tool("ffprobe") == "/tools/ffprobe"


def test_resolve_missing_qaac_is_actionable(monkeypatch) -> None:
    monkeypatch.setattr(config, "TOOL_PATHS", ToolPaths())
    monkeypatch.setattr(config.shutil, "which", lambda _name: None)
    with pytest.raises(OSError, match="qaac not found"):
        config.resolve_tool("qaac")

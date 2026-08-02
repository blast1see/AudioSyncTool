from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from audio_sync import config
from audio_sync.config import ToolPaths
from audio_sync.core.models import OutputSampleRate
from audio_sync.utils import (
    parse_float,
    parse_int,
    scale_timeout_for_size,
    short_name,
    validate_file,
)


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
    monkeypatch.setattr(config, "which_on_path", lambda name: f"/tools/{name}")
    assert config.resolve_tool("ffprobe") == os.path.abspath("/tools/ffprobe")


def test_resolve_missing_qaac_is_actionable(monkeypatch) -> None:
    monkeypatch.setattr(config, "TOOL_PATHS", ToolPaths())
    monkeypatch.setattr(config, "which_on_path", lambda _name: None)
    with pytest.raises(OSError, match="qaac not found"):
        config.resolve_tool("qaac")


def test_resolve_tool_memoizes_lookups(monkeypatch) -> None:
    lookups: list[str] = []

    def counting_lookup(name: str) -> str:
        lookups.append(name)
        return f"/tools/{name}"

    monkeypatch.setattr(config, "TOOL_PATHS", ToolPaths())
    monkeypatch.setattr(config, "which_on_path", counting_lookup)

    first = config.resolve_tool("ffmpeg")
    monkeypatch.setattr(config, "_is_executable_file", lambda _path: True)
    assert config.resolve_tool("ffmpeg") == first
    assert lookups == ["ffmpeg"]

    config.invalidate_tool_cache()
    assert config.resolve_tool("ffmpeg") == first
    assert lookups == ["ffmpeg", "ffmpeg"]


def test_path_lookup_ignores_working_directory(tmp_path: Path, monkeypatch) -> None:
    """A planted binary in the CWD must never win over a real PATH entry."""
    planted_dir = tmp_path / "downloads"
    planted_dir.mkdir()
    real_dir = tmp_path / "bin"
    real_dir.mkdir()

    suffix = ".EXE" if sys.platform == "win32" else ""
    planted = planted_dir / f"ffmpeg{suffix}"
    planted.write_bytes(b"planted")
    planted.chmod(0o755)
    real = real_dir / f"ffmpeg{suffix}"
    real.write_bytes(b"real")
    real.chmod(0o755)

    monkeypatch.chdir(planted_dir)
    monkeypatch.setenv("PATH", str(real_dir))
    # Windows only skips the CWD when this guard is set; clear it so the test
    # exercises the configuration a double-clicked .exe actually runs under.
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setattr(config, "TOOL_PATHS", ToolPaths())

    assert config.which_on_path("ffmpeg") == str(real)
    assert config.resolve_tool("ffmpeg") == str(real)


def test_path_lookup_skips_relative_path_entries(tmp_path: Path, monkeypatch) -> None:
    """Relative PATH entries are attacker-controllable and must be ignored."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    suffix = ".EXE" if sys.platform == "win32" else ""
    planted = workdir / f"ffprobe{suffix}"
    planted.write_bytes(b"planted")
    planted.chmod(0o755)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", os.pathsep.join(("work", ".", "")))

    assert config.which_on_path("ffprobe") is None


def test_probe_cache_dir_lives_under_user_settings(tmp_path: Path, monkeypatch) -> None:
    """Runtime probes must not write inside the installation tree."""
    monkeypatch.setattr(config, "_TOOL_PATHS_DIR", tmp_path / "settings")
    monkeypatch.setattr(config, "_PROBE_CACHE_DIR", tmp_path / "settings" / "probe")

    probe_dir = config.probe_cache_dir()
    assert probe_dir.is_dir()
    assert probe_dir == tmp_path / "settings" / "probe"


def test_scale_timeout_grows_with_input_size(tmp_path: Path) -> None:
    small = tmp_path / "small.wav"
    small.write_bytes(b"\0" * 1024)

    assert scale_timeout_for_size(
        60, str(small), per_gib_sec=100, max_sec=600
    ) == 60
    assert scale_timeout_for_size(
        60, str(small), per_gib_sec=100, max_sec=600, extra_sec=90
    ) == 150
    assert scale_timeout_for_size(
        60, str(small), per_gib_sec=100, max_sec=600, extra_sec=10_000
    ) == 600
    # A missing file must not blow up or shrink the base budget.
    assert scale_timeout_for_size(
        60, str(tmp_path / "missing.wav"), per_gib_sec=100, max_sec=600
    ) == 60

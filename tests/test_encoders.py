from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from audio_sync.config import DeewFormat
from audio_sync.core.deew_encoder import DeewEncoder
from audio_sync.core.encoder import QaacEncoder


def test_qaac_nonzero_check_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("audio_sync.core.encoder.resolve_tool", lambda _name: "qaac")
    monkeypatch.setattr(
        "audio_sync.core.encoder.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 3, "", "CoreAudio missing"),
    )
    ok, detail = QaacEncoder.check_availability()
    assert not ok
    assert "CoreAudio missing" in detail


def test_qaac_zero_check_is_available(monkeypatch) -> None:
    monkeypatch.setattr("audio_sync.core.encoder.resolve_tool", lambda _name: "qaac")
    monkeypatch.setattr(
        "audio_sync.core.encoder.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )
    assert QaacEncoder.check_availability() == (True, "qaac is available.")


def test_deew_rejects_unrelated_recent_files(tmp_path: Path) -> None:
    input_wav = tmp_path / "work" / "synchronized.wav"
    input_wav.parent.mkdir()
    input_wav.write_bytes(b"wav")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "someone-elses-file.eac3").write_bytes(b"unrelated")

    with pytest.raises(RuntimeError, match="output file not found"):
        DeewEncoder._find_output_file(
            str(input_wav), str(output_dir), DeewFormat.DDP, previous={}
        )


def test_deew_accepts_only_expected_new_or_changed_output(tmp_path: Path) -> None:
    input_wav = tmp_path / "synchronized.wav"
    input_wav.write_bytes(b"wav")
    output_dir = tmp_path / "encoded"
    output_dir.mkdir()
    expected = output_dir / "synchronized.eac3"
    expected.write_bytes(b"old")
    snapshot = DeewEncoder._snapshot_output_files(
        str(input_wav), str(output_dir), DeewFormat.DDP
    )

    with pytest.raises(RuntimeError):
        DeewEncoder._find_output_file(
            str(input_wav), str(output_dir), DeewFormat.DDP, previous=snapshot
        )

    expected.write_bytes(b"fresh output")
    found = DeewEncoder._find_output_file(
        str(input_wav), str(output_dir), DeewFormat.DDP, previous=snapshot
    )
    assert Path(found) == expected.resolve()

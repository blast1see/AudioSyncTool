from __future__ import annotations

import sys
import threading

import pytest

from audio_sync.core.models import OperationCancelledError
from audio_sync.core.process_runner import run_text_process


def run_python(code: str, **kwargs):
    return run_text_process(
        [sys.executable, "-c", code],
        not_found_message="python missing",
        timeout_message="process timeout",
        **kwargs,
    )


def test_process_success() -> None:
    result = run_python("print('ready')", timeout=5)
    assert result.returncode == 0
    assert result.stdout.strip() == "ready"


def test_process_timeout_terminates_child() -> None:
    with pytest.raises(RuntimeError, match="process timeout"):
        run_python("import time; time.sleep(5)", timeout=1)


def test_process_cancellation_terminates_child() -> None:
    cancel = threading.Event()
    timer = threading.Timer(0.15, cancel.set)
    timer.start()
    try:
        with pytest.raises(OperationCancelledError):
            run_python("import time; time.sleep(5)", timeout=5, cancel_event=cancel)
    finally:
        timer.cancel()

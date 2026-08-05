"""Turning deew's start-up crash into an actionable message.

deew draws a logo through ``rich`` before encoding.  On Windows the child
inherits the system's legacy code page, and on any locale whose page cannot
represent the logo's block characters the run dies with a ``UnicodeEncodeError``
traceback and no output.  Reproduced on Turkish cp1254 against deew 3.2.2;
``PYTHONIOENCODING``, ``PYTHONUTF8``, ``TERM`` and ``chcp 65001`` were all
verified not to change it, so the only fix is a line in deew's own config.
"""

from __future__ import annotations

import pytest

from audio_sync.core.deew_encoder import (
    deew_config_locations,
    describe_deew_failure,
)

CRASH = (
    "Traceback (most recent call last):\n"
    '  File "deew\\__main__.py", line 565, in main\n'
    '  File "rich\\_win32_console.py", line 402, in write_text\n'
    '  File "encodings\\cp1254.py", line 19, in encode\n'
    "UnicodeEncodeError: 'charmap' codec can't encode characters in "
    "position 1-5: character maps to <undefined>\n"
    "[29404] Failed to execute script '__main__' due to unhandled exception!"
)


def test_the_logo_crash_is_recognised() -> None:
    message = describe_deew_failure(CRASH)
    assert message is not None


def test_the_message_names_the_setting_and_the_file() -> None:
    message = describe_deew_failure(CRASH)
    assert "logo = 0" in message
    assert "config.toml" in message
    # A traceback helps nobody here; the actionable line must replace it.
    assert "Traceback" not in message
    assert "cp1254" not in message, "the fix is the same on every code page"


def test_the_message_says_the_work_is_not_lost() -> None:
    """Encoding runs after synchronization, and that WAV is preserved."""
    assert "WAV" in describe_deew_failure(CRASH)


@pytest.mark.parametrize(
    "output",
    [
        "",
        "dee returned exit code 3",
        "ffmpeg: no such file or directory",
        "UnicodeDecodeError: something else entirely",
    ],
)
def test_unrelated_failures_are_left_alone(output: str) -> None:
    """Only this specific crash gets rewritten; everything else keeps its detail."""
    assert describe_deew_failure(output) is None


def test_config_locations_are_absolute_and_unique() -> None:
    import os

    locations = deew_config_locations()
    assert locations, "at least one search location must be reported"
    assert len(set(locations)) == len(locations)
    for path in locations:
        assert os.path.isabs(path)
        assert path.endswith("config.toml")

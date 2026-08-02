"""Shared fixtures — keep process-wide caches from leaking between tests."""

from __future__ import annotations

import pytest

from audio_sync import config
from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper


@pytest.fixture(autouse=True)
def _clear_tool_caches():
    """Reset memoized tool lookups around every test.

    ``resolve_tool`` and ``check_availability`` cache successful results for
    the lifetime of the process, so without this a test that resolves the real
    FFmpeg would poison the next test that patches the lookup.
    """
    config.invalidate_tool_cache()
    FFmpegWrapper.reset_availability_cache()
    yield
    config.invalidate_tool_cache()
    FFmpegWrapper.reset_availability_cache()

"""Encoder for qaac (AAC/ALAC) tool."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from typing import Tuple

from audio_sync.config import QaacConfig, QaacMode, resolve_tool
from audio_sync.core.process_runner import run_text_process
from audio_sync.utils import scale_timeout_for_size

logger = logging.getLogger(__name__)

# Platform-safe subprocess kwargs — creationflags is Windows-only
_PLATFORM_SUBPROCESS_KWARGS: dict = (
    {"creationflags": 0x0800_0000} if sys.platform == "win32" else {}
)


class QaacEncoder:
    """Encoder using qaac for AAC/M4A output.

    Supports both ``qaac64`` (preferred) and ``qaac`` binary names
    via :func:`audio_sync.config.resolve_tool`.
    """

    @staticmethod
    def check_availability() -> Tuple[bool, str]:
        """Check if qaac (or qaac64) is available in PATH."""
        try:
            binary = resolve_tool("qaac")
        except OSError as exc:
            return False, str(exc)

        try:
            result = subprocess.run(
                [binary, "--check"],
                capture_output=True,
                text=True,
                timeout=10,
                **_PLATFORM_SUBPROCESS_KWARGS,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                return False, detail or f"qaac check failed with exit code {result.returncode}."
            return True, f"{binary} is available."
        except FileNotFoundError:
            return False, (
                "qaac not found. Please install qaac and add it to PATH "
                "(expected at C:\\qaac)."
            )
        except subprocess.TimeoutExpired:
            return False, "qaac availability check timed out."
        except Exception as e:
            return False, f"qaac check failed: {e}"

    @staticmethod
    def encode(
        input_path: str,
        output_path: str,
        config: QaacConfig | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Encode audio file using qaac.

        Args:
            input_path: Path to input WAV file
            output_path: Path to output M4A file
            config: qaac configuration (uses defaults if None)

        Returns:
            Summary string describing the encoding

        Raises:
            RuntimeError: If encoding fails
        """
        if config is None:
            config = QaacConfig()

        try:
            binary = resolve_tool("qaac")
        except OSError as exc:
            raise RuntimeError(str(exc)) from exc

        cmd = [binary]

        # Add encoding mode and quality/bitrate
        if config.mode == QaacMode.TVBR:
            cmd.extend([config.mode.flag, str(config.tvbr_quality)])
        elif config.mode == QaacMode.CVBR:
            cmd.extend([config.mode.flag, str(config.cvbr_bitrate)])
        elif config.mode == QaacMode.ABR:
            cmd.extend([config.mode.flag, str(config.abr_bitrate)])
        elif config.mode == QaacMode.CBR:
            cmd.extend([config.mode.flag, str(config.cbr_bitrate)])

        # Optional flags
        if config.he_aac:
            cmd.append("--he")
        if config.no_delay:
            cmd.append("--no-delay")

        # Input and output
        cmd.extend(["-o", output_path, input_path])

        logger.info("qaac command: %s", " ".join(cmd))

        # A feature-length WAV needs far more than the base budget, so scale the
        # timeout with the actual input size instead of aborting a valid encode.
        timeout = scale_timeout_for_size(
            config.timeout_sec,
            input_path,
            per_gib_sec=config.timeout_per_gib_sec,
            max_sec=config.max_timeout_sec,
        )

        result = run_text_process(
            cmd,
            timeout=timeout,
            cancel_event=cancel_event,
            not_found_message=(
                f"'{binary}' could not be executed. Make sure qaac is installed correctly."
            ),
            timeout_message=f"qaac encoding timed out (>{timeout}s)",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"qaac encoding failed (exit code {result.returncode}):\n"
                f"{result.stderr}"
            )

        mode_label = config.mode.label
        if config.mode == QaacMode.TVBR:
            detail = f"quality={config.tvbr_quality}"
        elif config.mode == QaacMode.CVBR:
            detail = f"{config.cvbr_bitrate} kbps"
        elif config.mode == QaacMode.ABR:
            detail = f"{config.abr_bitrate} kbps"
        else:
            detail = f"{config.cbr_bitrate} kbps"

        return f"qaac {mode_label} ({detail})"

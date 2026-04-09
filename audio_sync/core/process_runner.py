"""Shared subprocess helpers for external audio tools."""

from __future__ import annotations

import subprocess
import sys
import threading
import time

from audio_sync.core.models import OperationCancelledError


def get_platform_popen_kwargs() -> dict:
    """Return platform-safe ``subprocess.Popen`` kwargs."""
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return kwargs


def terminate_process_tree(process: subprocess.Popen) -> None:
    """Terminate a subprocess and its children as safely as possible."""
    if process.poll() is not None:
        return

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                **get_platform_popen_kwargs(),
            )
        except Exception:
            pass

    try:
        process.terminate()
    except OSError:
        return

    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()


def run_process(
    cmd: list[str],
    *,
    text: bool,
    timeout: int | None = None,
    cancel_event: threading.Event | None = None,
    not_found_message: str,
    timeout_message: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    """Run a subprocess with shared timeout and cancellation behavior."""
    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            cwd=cwd,
            env=env,
            **get_platform_popen_kwargs(),
        ) as process:
            stdout, stderr = wait_for_process(
                process,
                timeout=timeout,
                cancel_event=cancel_event,
                timeout_message=timeout_message,
            )
            return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
    except FileNotFoundError as exc:
        raise OSError(not_found_message) from exc


def run_text_process(
    cmd: list[str],
    *,
    timeout: int | None = None,
    cancel_event: threading.Event | None = None,
    not_found_message: str,
    timeout_message: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture text output."""
    result = run_process(
        cmd,
        text=True,
        timeout=timeout,
        cancel_event=cancel_event,
        not_found_message=not_found_message,
        timeout_message=timeout_message,
        cwd=cwd,
        env=env,
    )
    return result


def run_binary_process(
    cmd: list[str],
    *,
    timeout: int | None = None,
    cancel_event: threading.Event | None = None,
    not_found_message: str,
    timeout_message: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run a subprocess and capture binary output."""
    result = run_process(
        cmd,
        text=False,
        timeout=timeout,
        cancel_event=cancel_event,
        not_found_message=not_found_message,
        timeout_message=timeout_message,
        cwd=cwd,
        env=env,
    )
    return result


def wait_for_process(
    process: subprocess.Popen,
    *,
    timeout: int | None = None,
    cancel_event: threading.Event | None = None,
    timeout_message: str,
) -> tuple[str | bytes, str | bytes]:
    """Wait for a subprocess while polling for timeout and cancellation."""
    deadline = None if timeout is None else time.monotonic() + timeout

    while True:
        if cancel_event is not None and cancel_event.is_set():
            terminate_process_tree(process)
            raise OperationCancelledError("Processing cancelled by user.")

        wait_timeout = 0.25
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate_process_tree(process)
                raise RuntimeError(timeout_message)
            wait_timeout = min(wait_timeout, max(0.05, remaining))

        try:
            return process.communicate(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            continue

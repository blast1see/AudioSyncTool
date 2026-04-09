"""General helper functions independent from UI and business logic."""

from __future__ import annotations

import os
from pathlib import PurePath


def short_name(name: str, max_chars: int = 52) -> str:
    """Shorten long filenames in ``start...end.ext`` form."""
    if len(name) <= max_chars:
        return name

    p = PurePath(name)
    ext = p.suffix[:10]
    stem = p.stem
    reserved = len(ext) + 3
    available = max(8, max_chars - reserved)
    head = max(4, int(available * 0.65))
    tail = max(4, available - head)
    return f"{stem[:head]}...{stem[-tail:]}{ext}"


def parse_float(
    value: str | None,
    default: float = 0.0,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Parse a float safely and clamp it when bounds are provided."""
    try:
        parsed = float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError):
        parsed = float(default)

    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def parse_int(
    value: str | None,
    default: int = 0,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Parse an integer safely and clamp it when bounds are provided."""
    try:
        parsed = int(float(str(value).strip().replace(",", ".")))
    except (ValueError, TypeError):
        parsed = int(default)

    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def validate_file(path: str, label: str) -> None:
    """Validate that a file exists, is readable, and is non-empty."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label} file not found: {path}")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"{label} file is not readable: {path}")
    if os.path.getsize(path) == 0:
        raise ValueError(f"{label} file is empty: {path}")

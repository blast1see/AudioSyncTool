"""Genel yardımcı fonksiyonlar — UI ve iş mantığından bağımsız."""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import PurePath
from typing import Generator


# ── Dosya Adı Kısaltma ──────────────────────────────────────────────────────


def short_name(name: str, max_chars: int = 52) -> str:
    """Uzun dosya adlarını ``başlangıç...son.ext`` formatında kısaltır.

    Args:
        name: Dosya adı (yol değil, sadece ad).
        max_chars: Maksimum karakter sayısı.

    Returns:
        Kısaltılmış dosya adı.  Zaten kısaysa olduğu gibi döner.

    Example::

        >>> short_name("very_long_filename_that_exceeds_limit.wav", max_chars=30)
        'very_long_filen...limit.wav'
    """
    if len(name) <= max_chars:
        return name

    p = PurePath(name)
    ext = p.suffix[:10]
    stem = p.stem
    reserved = len(ext) + 3  # "..." için
    available = max(8, max_chars - reserved)
    head = max(4, int(available * 0.65))
    tail = max(4, available - head)
    return f"{stem[:head]}...{stem[-tail:]}{ext}"


# ── Güvenli Değer Ayrıştırma ────────────────────────────────────────────────


def parse_float(
    value: str | None,
    default: float = 0.0,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """String'i güvenli şekilde float'a çevirir.

    Türkçe ondalık ayracı (virgül) desteklenir.

    Args:
        value: Ayrıştırılacak string.
        default: Ayrıştırma başarısız olursa kullanılacak değer.
        minimum: Alt sınır (dahil).
        maximum: Üst sınır (dahil).

    Returns:
        Ayrıştırılmış ve sınırlandırılmış float değer.
    """
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
    """String'i güvenli şekilde int'e çevirir.

    Ondalıklı girişler (ör. ``"3.7"``) önce float'a, sonra int'e çevrilir.

    Args:
        value: Ayrıştırılacak string.
        default: Ayrıştırma başarısız olursa kullanılacak değer.
        minimum: Alt sınır (dahil).
        maximum: Üst sınır (dahil).

    Returns:
        Ayrıştırılmış ve sınırlandırılmış int değer.
    """
    try:
        parsed = int(float(str(value).strip().replace(",", ".")))
    except (ValueError, TypeError):
        parsed = int(default)

    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


# ── Dosya Doğrulama ─────────────────────────────────────────────────────────


def validate_file(path: str, label: str) -> None:
    """Dosyanın var olduğunu, okunabilir olduğunu ve boş olmadığını doğrular.

    Args:
        path: Dosya yolu.
        label: Hata mesajlarında kullanılacak etiket (ör. "Kaynak").

    Raises:
        FileNotFoundError: Dosya bulunamazsa.
        PermissionError: Dosya okunamazsa.
        ValueError: Dosya boşsa.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label} file not found: {path}")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"{label} file is not readable: {path}")
    if os.path.getsize(path) == 0:
        raise ValueError(f"{label} file is empty: {path}")


# ── Geçici Dosya Yönetimi ───────────────────────────────────────────────────


@contextmanager
def temporary_wav_files(
    directory: str | None = None,
) -> Generator[tuple[str, str], None, None]:
    """Geçici WAV dosyaları oluşturur ve otomatik temizler.

    Context manager olarak kullanılır — blok sonunda dosyalar silinir.

    Args:
        directory: Geçici dizinin oluşturulacağı üst dizin.
            ``None`` ise sistem varsayılanı kullanılır.

    Yields:
        ``(src_mono_path, sync_mono_path)`` çifti.

    Example::

        with temporary_wav_files() as (tmp_src, tmp_sync):
            ffmpeg.to_wav_mono(source, tmp_src)
            ffmpeg.to_wav_mono(sync, tmp_sync)
            result = analyzer.calculate_delay(tmp_src, tmp_sync)
        # Dosyalar otomatik temizlenir
    """
    tmp_dir = tempfile.mkdtemp(prefix="audiosync_", dir=directory)
    try:
        src = os.path.join(tmp_dir, "src_mono.wav")
        sync = os.path.join(tmp_dir, "sync_mono.wav")
        yield src, sync
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

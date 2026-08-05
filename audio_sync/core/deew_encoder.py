"""Deew entegrasyonu.

Bu modül senkronizasyon sonrası WAV dosyalarını AC3/EAC3 formatına
dönüştürmek için deew aracını soyutlar.

Deew hakkında: https://github.com/pcroland/deew
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from audio_sync.config import (
    DEEW_CONFIG,
    DEEW_DEFAULT_BITRATES,
    DeewConfig,
    DeewDownmix,
    DeewDRC,
    DeewFormat,
    get_deew_bitrate_key,
    probe_cache_dir,
    resolve_tool,
    which_on_path,
)
from audio_sync.core.process_runner import run_text_process


@dataclass(frozen=True)
class DeewBackend:
    """Resolved deew backend command prefix and environment."""

    command_prefix: tuple[str, ...]
    display_name: str
    env: dict[str, str] | None = None


# ── Deew Yol Bulma ──────────────────────────────────────────────────────────


def _find_deew_executable() -> str | None:
    """Deew çalıştırılabilir dosyasını bulur.

    Arama sırası:
        1. ``resolve_tool("deew")`` — kullanıcı tanımlı yol veya sistem PATH'inde ``deew``
        2. Proje ``tools/`` dizinindeki ``deew.exe``
        3. Sistem PATH'indeki ``deew``

    Returns:
        Deew çalıştırılabilir dosyasının tam yolu veya ``None``.
    """
    # 1. resolve_tool ile kullanıcı tanımlı yol veya "deew" adıyla PATH araması
    try:
        return resolve_tool("deew")
    except OSError:
        pass

    # 2. Proje tools/ dizini
    project_root = Path(__file__).resolve().parent.parent.parent
    local_deew = project_root / "tools" / "deew.exe"
    if local_deew.is_file():
        return str(local_deew)

    # Windows'ta .exe uzantısız da dene
    local_deew_no_ext = project_root / "tools" / "deew"
    if local_deew_no_ext.is_file():
        return str(local_deew_no_ext)

    # 3. Sistem PATH
    return which_on_path("deew")


def _find_vendored_deew_module() -> str | None:
    """Return the optional vendored deew package root if present."""
    project_root = Path(__file__).resolve().parent.parent.parent
    vendor_root = project_root / "vendor" / "deew_pkg"
    if (vendor_root / "deew").is_dir():
        return str(vendor_root)
    return None


def _find_python_deew_backend() -> DeewBackend | None:
    """Return a Python-backed deew command if the module is importable."""
    vendored_root = _find_vendored_deew_module()
    if vendored_root is not None:
        vendored_launcher = Path(vendored_root) / "bin" / "deew.exe"
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{vendored_root}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath else vendored_root
        )
        return DeewBackend(
            command_prefix=((str(vendored_launcher),) if vendored_launcher.is_file()
                            else (sys.executable, "-m", "deew")),
            display_name=(
                str(vendored_launcher) if vendored_launcher.is_file()
                else "python -m deew (vendored)"
            ),
            env=env,
        )

    if importlib.util.find_spec("deew") is not None:
        return DeewBackend(
            command_prefix=(sys.executable, "-m", "deew"),
            display_name="python -m deew",
        )

    return None


def _build_temp_env(base_env: dict[str, str] | None, work_dir: str) -> dict[str, str]:
    """Build an environment with a forced writable temp directory."""
    env = os.environ.copy()
    if base_env:
        env.update(base_env)
    env.update({
        "TMP": work_dir,
        "TEMP": work_dir,
        "TMPDIR": work_dir,
    })
    return env


@lru_cache(maxsize=8)
def _probe_backend_runtime(
    command_prefix: tuple[str, ...],
    display_name: str,
    env_signature: tuple[tuple[str, str], ...] | None = None,
) -> tuple[bool, str]:
    """Return whether a deew backend can actually start."""
    try:
        probe_root = probe_cache_dir()
    except OSError as exc:
        return False, f"{display_name} probe directory is not writable: {exc}"

    try:
        result = run_text_process(
            [*command_prefix, "-c"],
            timeout=15,
            not_found_message=f"{display_name} not found.",
            timeout_message=f"{display_name} probe timed out.",
            cwd=str(probe_root),
            env=_build_temp_env(dict(env_signature) if env_signature else None, str(probe_root)),
        )
    except Exception as exc:
        return False, str(exc)

    if result.returncode == 0:
        return True, display_name

    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    detail = stderr or stdout or f"{display_name} returned exit code {result.returncode}."
    return False, detail


def resolve_deew_backend() -> DeewBackend:
    """Resolve the first deew backend that can actually start."""
    errors: list[str] = []

    deew_path = _find_deew_executable()
    if deew_path is not None:
        ok, detail = _probe_backend_runtime((deew_path,), deew_path)
        if ok:
            return DeewBackend(command_prefix=(deew_path,), display_name=deew_path)
        errors.append(f"standalone deew failed runtime probe: {detail}")

    python_backend = _find_python_deew_backend()
    if python_backend is not None:
        env_signature = (
            tuple(sorted(python_backend.env.items()))
            if python_backend.env is not None else None
        )
        ok, detail = _probe_backend_runtime(
            python_backend.command_prefix,
            python_backend.display_name,
            env_signature,
        )
        if ok:
            return python_backend
        errors.append(f"python deew failed runtime probe: {detail}")

    detail_block = "\n".join(f"  - {msg}" for msg in errors) if errors else "  - no backend found"
    raise OSError(
        "'deew' is configured but could not be started correctly.\n"
        "\n"
        "Tried backends:\n"
        f"{detail_block}\n"
        "\n"
        "Recommended fixes:\n"
        "  1. Install the Python package: pip install deew\n"
        "  2. Or replace the standalone deew.exe with a working release build\n"
        "  3. Then reopen the app so the runtime probe can pass"
    )


def deew_config_locations() -> tuple[str, ...]:
    """Where deew looks for ``config.toml``, most specific first.

    Reported back to the user when a setting in that file has to change; a
    message telling someone to edit a file they then have to hunt for is only
    half an answer.
    """
    candidates: list[str] = []

    try:
        executable = _find_deew_executable()
    except Exception:  # pragma: no cover - defensive
        executable = None
    if executable:
        candidates.append(os.path.join(os.path.dirname(executable), "config.toml"))

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            candidates.append(os.path.join(base, "deew", "config.toml"))
    else:
        candidates.append(
            os.path.join(
                os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                "deew",
                "config.toml",
            )
        )

    return tuple(dict.fromkeys(candidates))


def describe_deew_failure(output: str) -> str | None:
    """Turn a known deew crash into something the user can act on.

    deew draws an ASCII-art logo through ``rich`` before it encodes anything.
    On Windows the child process inherits the system's legacy code page, and on
    any locale whose code page cannot represent the logo's block characters —
    Turkish cp1254, Greek cp1253, and others — ``rich`` raises
    ``UnicodeEncodeError`` and deew dies before touching the audio.

    Nothing outside deew can prevent this: the logo is a config setting, and
    neither ``PYTHONIOENCODING``, ``PYTHONUTF8``, ``TERM`` nor ``chcp 65001``
    changes the encoding ``rich`` picks (all verified against deew 3.2.2).  So
    the honest response is to stop showing a Python traceback and name the one
    line that fixes it.
    """
    if not output:
        return None

    lowered = output.lower()
    if "unicodeencodeerror" not in lowered or "codec can't encode" not in lowered:
        return None

    locations = deew_config_locations()
    where = "\n".join(f"  {path}" for path in locations) or "  (config not found)"
    return (
        "Deew crashed while drawing its start-up logo: this system's code page "
        "cannot represent the characters it uses, so deew exits before encoding "
        "anything.\n"
        "Fix it by setting the logo off in deew's config:\n"
        f"{where}\n"
        "Change the line 'logo = 1' to 'logo = 0', then run the sync again.\n"
        "The synchronized WAV has been kept, so nothing needs re-analyzing."
    )


def reset_deew_probe_cache() -> None:
    """Forget cached runtime probes after the configured deew path changes."""
    _probe_backend_runtime.cache_clear()


def get_deew_runtime_status() -> tuple[bool, str]:
    """Return runtime availability plus a user-facing detail string."""
    try:
        backend = resolve_deew_backend()
        return True, backend.display_name
    except OSError as exc:
        return False, str(exc)


# ── Deew Encoder ─────────────────────────────────────────────────────────────


class DeewEncoder:
    """Deew komut satırı arayüzü — WAV → AC3/EAC3 dönüştürücü.

    Args:
        config: Deew encoder yapılandırması.

    Example::

        encoder = DeewEncoder()
        encoder.check_availability()
        output = encoder.encode(
            input_wav="synced_output.wav",
            output_dir="C:/output",
        )
        print(f"Encoded: {output}")
    """

    def __init__(self, config: DeewConfig = DEEW_CONFIG) -> None:
        self._config = config
        self._backend: DeewBackend | None = None

    # ── Bağımlılık Kontrolü ──────────────────────────────────────────────

    @staticmethod
    def check_availability() -> str:
        """Deew'in sistemde kurulu/erişilebilir olduğunu doğrular.

        Returns:
            Deew çalıştırılabilir dosyasının yolu.

        Raises:
            OSError: Deew bulunamazsa kurulum talimatlarıyla birlikte hata fırlatır.
        """
        deew_path = _find_deew_executable()
        if deew_path is None:
            raise OSError(
                "'deew' not found. Please install deew:\n"
                "\n"
                "  Method 1 — via pip:\n"
                "    pip install deew\n"
                "\n"
                "  Method 2 — Executable:\n"
                "    Download deew.exe from\n"
                "    https://github.com/pcroland/deew/releases\n"
                "    and place it in the tools/ folder.\n"
                "\n"
                "  Note:\n"
                "    Make sure deew is installed and configured correctly."
            )
        return deew_path

    @staticmethod
    def is_available() -> bool:
        """Deew'in erişilebilir olup olmadığını kontrol eder (hata fırlatmaz).

        Returns:
            ``True`` ise deew kullanılabilir.
        """
        return _find_deew_executable() is not None

    # ── Encoding ─────────────────────────────────────────────────────────

    def encode(
        self,
        input_wav: str,
        output_dir: str | None = None,
        fmt: DeewFormat | None = None,
        bitrate: int | None = None,
        downmix: DeewDownmix | None = None,
        drc: DeewDRC | None = None,
        dialnorm: int | None = None,
        progress_callback: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """WAV dosyasını deew ile AC3/EAC3 formatına dönüştürür.

        Args:
            input_wav: Giriş WAV dosyasının yolu.
            output_dir: Çıktı dizini.  ``None`` ise giriş dosyasının dizini.
            fmt: Çıktı formatı.  ``None`` ise config'den alınır.
            bitrate: Bitrate (kbps).  ``None`` ise config/varsayılan kullanılır.
            downmix: Kanal düzeni.  ``None`` ise config'den alınır.
            drc: DRC profili.  ``None`` ise config'den alınır.
            dialnorm: Dialnorm değeri.  ``None`` ise config'den alınır.
            progress_callback: İlerleme mesajları için callback.

        Returns:
            Oluşturulan çıktı dosyasının yolu.

        Raises:
            OSError: Deew bulunamazsa.
            FileNotFoundError: Giriş dosyası bulunamazsa.
            RuntimeError: Encoding hatası.
        """
        # Deew backend'ini çöz
        backend = resolve_deew_backend()

        # Giriş dosyasını doğrula
        if not os.path.isfile(input_wav):
            raise FileNotFoundError(f"Input WAV file not found: {input_wav}")

        # Parametreleri belirle (argüman > config > varsayılan)
        effective_fmt = fmt or self._config.format
        effective_downmix = downmix if downmix is not None else self._config.downmix
        effective_downmix = self._usable_downmix(
            effective_downmix, input_wav, progress_callback
        )
        effective_drc = drc or self._config.drc
        effective_dialnorm = dialnorm if dialnorm is not None else self._config.dialnorm

        # Bitrate belirleme
        if bitrate is not None:
            effective_bitrate = bitrate
        elif self._config.bitrate is not None:
            effective_bitrate = self._config.bitrate
        else:
            key = get_deew_bitrate_key(effective_fmt, effective_downmix)
            effective_bitrate = DEEW_DEFAULT_BITRATES.get(key, 448)

        # Çıktı dizini
        if output_dir is None:
            output_dir = os.path.dirname(input_wav) or "."

        output_snapshot = self._snapshot_output_files(
            input_wav,
            output_dir,
            effective_fmt,
        )

        # Komutu oluştur
        cmd = self._build_command(
            command_prefix=backend.command_prefix,
            input_wav=input_wav,
            output_dir=output_dir,
            fmt=effective_fmt,
            bitrate=effective_bitrate,
            downmix=effective_downmix,
            drc=effective_drc,
            dialnorm=effective_dialnorm,
        )

        if progress_callback:
            progress_callback(f"Deew komutu: {' '.join(shlex.quote(c) for c in cmd)}")

        # Komutu çalıştır
        result = self._run_deew(
            cmd,
            timeout=self._config.timeout_sec,
            cancel_event=cancel_event,
            work_dir=output_dir,
            base_env=backend.env,
        )

        if progress_callback:
            if result.stdout:
                for line in result.stdout.strip().splitlines()[-5:]:
                    progress_callback(f"deew: {line}")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[-3:]:
                    progress_callback(f"deew stderr: {line}")

        if result.returncode != 0:
            stderr_msg = result.stderr[-600:] if result.stderr else "(stderr empty)"
            stdout_msg = result.stdout[-600:] if result.stdout else ""
            error_detail = stderr_msg or stdout_msg

            hint = describe_deew_failure(result.stderr or result.stdout or "")
            if hint:
                raise RuntimeError(hint)

            raise RuntimeError(
                f"Deew encoding error (code: {result.returncode}):\n{error_detail}"
            )

        # Çıktı dosyasını bul
        output_path = self._find_output_file(
            input_wav,
            output_dir,
            effective_fmt,
            previous=output_snapshot,
        )

        if progress_callback:
            progress_callback(f"Deew encoding completed: {os.path.basename(output_path)}")

        return output_path

    # ── Komut Oluşturma ──────────────────────────────────────────────────

    @staticmethod
    def _usable_downmix(
        downmix: DeewDownmix | None,
        input_wav: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> DeewDownmix | None:
        """Drop a downmix that deew would reject.

        deew refuses ``-dm`` unless the target is *fewer* channels than the
        input — asking a stereo track for a stereo downmix aborts the encode
        with "downmix value has to be lower than the number of input channels".
        Choosing "Stereo" for a stereo source is a reasonable thing for someone
        to do, and it means "leave it alone", so the flag is simply omitted
        rather than failing the run after the synchronization already succeeded.
        """
        if downmix is None:
            return None

        # Imported here rather than at module scope: ffmpeg_wrapper pulls in
        # numpy, and this module is imported during UI start-up.
        from audio_sync.core.ffmpeg_wrapper import FFmpegWrapper

        try:
            info = FFmpegWrapper().probe_audio(input_wav)
        except Exception:  # pragma: no cover - probe failures handled downstream
            return downmix

        if downmix.channels < info.channels:
            return downmix

        if progress_callback:
            progress_callback(
                f"Ignoring the {downmix.display_name} downmix: the track already "
                f"has {info.channels} channel(s), so there is nothing to fold down."
            )
        return None

    @staticmethod
    def _build_command(
        command_prefix: tuple[str, ...],
        input_wav: str,
        output_dir: str,
        fmt: DeewFormat,
        bitrate: int,
        downmix: DeewDownmix | None,
        drc: DeewDRC,
        dialnorm: int,
    ) -> list[str]:
        """Deew komut satırı argümanlarını oluşturur.

        Returns:
            Komut ve argüman listesi.
        """
        cmd = [
            *command_prefix,
            "-i", input_wav,
            "-o", output_dir,
            "-f", fmt.cli_value,
            "-b", str(bitrate),
            "-r", drc.cli_value,
            "-np",  # Prompt'u devre dışı bırak (otomasyon için)
        ]

        if downmix is not None:
            cmd.extend(["-dm", str(downmix.channels)])

        if dialnorm != 0:
            cmd.extend(["-dn", str(dialnorm)])

        return cmd

    @staticmethod
    def _run_deew(
        cmd: list[str],
        *,
        timeout: int,
        cancel_event: threading.Event | None = None,
        work_dir: str | None = None,
        base_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Deew komutunu çalıştırır.

        Args:
            cmd: Çalıştırılacak komut ve argümanları.

        Returns:
            ``CompletedProcess`` nesnesi.

        Raises:
            RuntimeError: Zaman aşımı durumunda.
            OSError: Komut bulunamazsa.
        """
        env = _build_temp_env(base_env, work_dir) if work_dir else (base_env or None)

        return run_text_process(
            cmd,
            timeout=timeout,
            cancel_event=cancel_event,
            not_found_message=(
                f"'{cmd[0]}' could not be executed. Make sure the file exists "
                f"and you have execution permissions."
            ),
            timeout_message=(
                f"Deew encoding did not complete within {timeout} seconds. "
                f"The file may be too large or deew may not be configured correctly."
            ),
            cwd=work_dir,
            env=env,
        )

    @staticmethod
    def _find_output_file(
        input_wav: str,
        output_dir: str,
        fmt: DeewFormat,
        *,
        previous: dict[str, tuple[int, int]] | None = None,
    ) -> str:
        """Deew'in oluşturduğu çıktı dosyasını bulur.

        Yalnızca beklenen giriş kökü ve geçerli uzantıyla eşleşen, Deew
        çalıştırıldıktan sonra yeni oluşmuş veya değişmiş dosyalar kabul edilir.
        Böylece aynı klasördeki ilgisiz ve yakın zamanda oluşturulmuş bir ses
        dosyası yanlışlıkla sonuç olarak seçilemez.

        Args:
            input_wav: Giriş WAV dosyasının yolu.
            output_dir: Çıktı dizini.
            fmt: Çıktı formatı.

        Returns:
            Çıktı dosyasının tam yolu.

        Raises:
            RuntimeError: Çıktı dosyası bulunamazsa.
        """
        if not os.path.isdir(output_dir):
            raise RuntimeError(
                f"Deew output directory not found: {output_dir}"
            )

        previous = previous or {}
        input_stem = Path(input_wav).stem
        input_dir = str(Path(input_wav).parent)
        all_exts = fmt.all_extensions
        expected_output = os.path.join(output_dir, f"{input_stem}{fmt.extension}")
        current = DeewEncoder._snapshot_output_files(input_wav, output_dir, fmt)
        fresh = [
            path
            for path, signature in current.items()
            if previous.get(path) != signature
        ]
        if fresh:
            direct_names = {
                str((Path(output_dir) / f"{input_stem}{ext}").resolve())
                for ext in all_exts
            }
            fresh.sort(
                key=lambda path: (
                    path not in direct_names,
                    -current[path][0],
                    path,
                )
            )
            return fresh[0]

        dir_contents: list[str] = []
        search_dirs = [output_dir]
        if os.path.normcase(input_dir) != os.path.normcase(output_dir):
            search_dirs.append(input_dir)
        for search_dir in search_dirs:
            for root, _dirs, files in os.walk(search_dir):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), search_dir)
                    dir_contents.append(f"[{os.path.basename(search_dir)}] {rel}")

        contents_str = "\n  ".join(dir_contents[:30]) if dir_contents else "(empty)"

        raise RuntimeError(
            f"Deew output file not found.\n"
            f"Expected: {expected_output}\n"
            f"Searched extensions: {', '.join(all_exts)}\n"
            f"Output directory: {output_dir}\n"
            f"Input directory: {input_dir}\n"
            f"Directory contents:\n  {contents_str}"
        )

    @staticmethod
    def _snapshot_output_files(
        input_wav: str,
        output_dir: str,
        fmt: DeewFormat,
    ) -> dict[str, tuple[int, int]]:
        """Return signatures for only the output names Deew may legitimately create."""
        input_path = Path(input_wav)
        expected_names = {f"{input_path.stem}{ext}" for ext in fmt.all_extensions}
        candidates: set[Path] = set()

        output_root = Path(output_dir)
        if output_root.is_dir():
            for root, _dirs, files in os.walk(output_root):
                for filename in files:
                    if filename in expected_names:
                        candidates.add(Path(root) / filename)

        input_root = input_path.parent
        if input_root.resolve() != output_root.resolve():
            for filename in expected_names:
                candidates.add(input_root / filename)

        snapshot: dict[str, tuple[int, int]] = {}
        for candidate in candidates:
            try:
                stat = candidate.stat()
            except OSError:
                continue
            snapshot[str(candidate.resolve())] = (stat.st_mtime_ns, stat.st_size)
        return snapshot


# ── Yardımcı Fonksiyonlar ───────────────────────────────────────────────────


def encode_wav_with_deew(
    input_wav: str,
    final_output_path: str,
    fmt: DeewFormat = DeewFormat.DDP,
    bitrate: int | None = None,
    downmix: DeewDownmix | None = None,
    drc: DeewDRC = DeewDRC.MUSIC_LIGHT,
    dialnorm: int = 0,
    delete_wav: bool = True,
    progress_callback: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    """WAV dosyasını Deew ile dönüştürür ve istenen konuma taşır.

    Bu fonksiyon tam pipeline'ı yönetir:
        1. Deew ile encoding
        2. Çıktıyı istenen konuma taşıma
        3. İsteğe bağlı olarak ara WAV dosyasını silme

    Args:
        input_wav: Giriş WAV dosyasının yolu.
        final_output_path: Son çıktı dosyasının istenen yolu.
        fmt: Çıktı formatı.
        bitrate: Bitrate (kbps).
        downmix: Kanal düzeni.
        drc: DRC profili.
        dialnorm: Dialnorm değeri.
        delete_wav: Ara WAV dosyasını sil mi?
        progress_callback: İlerleme mesajları için callback.

    Returns:
        Son çıktı dosyasının yolu.

    Raises:
        OSError: Deew bulunamazsa.
        RuntimeError: Encoding veya dosya işlem hatası.
    """
    import shutil as _shutil
    import tempfile

    encoder = DeewEncoder()

    # Deew çıktısı için geçici dizin kullan (temiz çalışma)
    temp_parent = os.path.dirname(final_output_path) or os.path.dirname(input_wav) or "."
    if not os.path.isdir(temp_parent):
        os.makedirs(temp_parent, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="deew_", dir=temp_parent)

    try:
        if progress_callback:
            progress_callback(f"Starting {fmt.display_name} encoding with Deew…")

        # Encoding
        encoded_path = encoder.encode(
            input_wav=input_wav,
            output_dir=temp_dir,
            fmt=fmt,
            bitrate=bitrate,
            downmix=downmix,
            drc=drc,
            dialnorm=dialnorm,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

        # Çıktıyı istenen konuma taşı
        final_dir = os.path.dirname(final_output_path)
        if final_dir and not os.path.isdir(final_dir):
            os.makedirs(final_dir, exist_ok=True)

        _shutil.move(encoded_path, final_output_path)

        if progress_callback:
            progress_callback(f"Output file moved: {os.path.basename(final_output_path)}")

        # Ara WAV dosyasını sil
        if delete_wav and os.path.isfile(input_wav):
            try:
                os.remove(input_wav)
                if progress_callback:
                    progress_callback("Intermediate WAV file deleted.")
            except OSError:
                if progress_callback:
                    progress_callback("Warning: Could not delete intermediate WAV file.")

        return final_output_path

    finally:
        # Geçici dizini temizle
        _shutil.rmtree(temp_dir, ignore_errors=True)

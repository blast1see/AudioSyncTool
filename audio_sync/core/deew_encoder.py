"""Deew (Dolby Encoding Engine Wrapper) entegrasyonu.

Bu modül senkronizasyon sonrası WAV dosyalarını AC3/EAC3 formatına
dönüştürmek için deew aracını soyutlar.

Deew hakkında: https://github.com/pcroland/deew
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Callable

from audio_sync.config import (
    DeewConfig,
    DeewDRC,
    DeewDownmix,
    DeewFormat,
    DEEW_CONFIG,
    get_deew_bitrate_key,
    DEEW_DEFAULT_BITRATES,
)


# ── Deew Yol Bulma ──────────────────────────────────────────────────────────


def _find_deew_executable() -> str | None:
    """Deew çalıştırılabilir dosyasını bulur.

    Arama sırası:
        1. Proje ``tools/`` dizinindeki ``deew.exe``
        2. Sistem PATH'indeki ``deew``

    Returns:
        Deew çalıştırılabilir dosyasının tam yolu veya ``None``.
    """
    # 1. Proje tools/ dizini
    project_root = Path(__file__).resolve().parent.parent.parent
    local_deew = project_root / "tools" / "deew.exe"
    if local_deew.is_file():
        return str(local_deew)

    # Windows'ta .exe uzantısız da dene
    local_deew_no_ext = project_root / "tools" / "deew"
    if local_deew_no_ext.is_file():
        return str(local_deew_no_ext)

    # 2. Sistem PATH
    system_deew = shutil.which("deew")
    if system_deew:
        return system_deew

    return None


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
        self._deew_path: str | None = None

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
                "'deew' bulunamadı. Lütfen deew'i yükleyin:\n"
                "\n"
                "  Yöntem 1 — pip ile:\n"
                "    pip install deew\n"
                "\n"
                "  Yöntem 2 — Çalıştırılabilir dosya:\n"
                "    https://github.com/pcroland/deew/releases adresinden\n"
                "    deew.exe dosyasını indirip tools/ klasörüne koyun.\n"
                "\n"
                "  Not: Deew, Dolby Encoding Engine (DEE) gerektirir.\n"
                "    DEE'nin kurulu ve yapılandırılmış olduğundan emin olun."
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
        # Deew yolunu bul
        deew_path = self.check_availability()

        # Giriş dosyasını doğrula
        if not os.path.isfile(input_wav):
            raise FileNotFoundError(f"Giriş WAV dosyası bulunamadı: {input_wav}")

        # Parametreleri belirle (argüman > config > varsayılan)
        effective_fmt = fmt or self._config.format
        effective_downmix = downmix if downmix is not None else self._config.downmix
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

        # Komutu oluştur
        cmd = self._build_command(
            deew_path=deew_path,
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
        result = self._run_deew(cmd)

        if progress_callback:
            if result.stdout:
                for line in result.stdout.strip().splitlines()[-5:]:
                    progress_callback(f"deew: {line}")

        if result.returncode != 0:
            stderr_msg = result.stderr[-600:] if result.stderr else "(stderr boş)"
            stdout_msg = result.stdout[-600:] if result.stdout else ""
            error_detail = stderr_msg or stdout_msg
            raise RuntimeError(
                f"Deew encoding hatası (kod: {result.returncode}):\n{error_detail}"
            )

        # Çıktı dosyasını bul
        output_path = self._find_output_file(input_wav, output_dir, effective_fmt)

        if progress_callback:
            progress_callback(f"Deew encoding tamamlandı: {os.path.basename(output_path)}")

        return output_path

    # ── Komut Oluşturma ──────────────────────────────────────────────────

    @staticmethod
    def _build_command(
        deew_path: str,
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
            deew_path,
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
    def _run_deew(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        """Deew komutunu çalıştırır.

        Args:
            cmd: Çalıştırılacak komut ve argümanları.

        Returns:
            ``CompletedProcess`` nesnesi.

        Raises:
            RuntimeError: Zaman aşımı durumunda.
            OSError: Komut bulunamazsa.
        """
        kwargs: dict = dict(
            capture_output=True,
            text=True,
            timeout=600,  # 10 dakika timeout
        )
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        try:
            return subprocess.run(cmd, **kwargs)
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "Deew encoding işlemi 10 dakika içinde tamamlanamadı. "
                "Dosya çok büyük veya DEE yapılandırması hatalı olabilir."
            )
        except FileNotFoundError:
            raise OSError(
                f"'{cmd[0]}' çalıştırılamadı. Dosyanın var olduğundan "
                f"ve çalıştırma izniniz olduğundan emin olun."
            )

    @staticmethod
    def _find_output_file(
        input_wav: str,
        output_dir: str,
        fmt: DeewFormat,
    ) -> str:
        """Deew'in oluşturduğu çıktı dosyasını bulur.

        Deew, giriş dosyasının adını koruyarak uzantıyı değiştirir.

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
                f"Deew çıktı dizini bulunamadı: {output_dir}"
            )

        input_stem = Path(input_wav).stem
        expected_ext = fmt.extension
        expected_output = os.path.join(output_dir, f"{input_stem}{expected_ext}")

        if os.path.isfile(expected_output):
            return expected_output

        # Deew bazen farklı adlandırma kullanabilir — dizinde ara
        for f in os.listdir(output_dir):
            if f.startswith(input_stem) and f.endswith(expected_ext):
                return os.path.join(output_dir, f)

        # Son çare: en yeni dosyayı bul — yalnızca son 120 saniye içinde
        # oluşturulmuş dosyalar kabul edilir (eşzamanlılık koruması)
        now = time.time()
        max_age_sec = 120.0
        candidates = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.endswith(expected_ext)
            and (now - os.path.getmtime(os.path.join(output_dir, f))) < max_age_sec
        ]
        if candidates:
            warnings.warn(
                f"Deew çıktı dosyası ada göre bulunamadı; son {max_age_sec:.0f}s içinde "
                f"oluşturulan en yeni dosya fallback olarak kullanılıyor "
                f"({len(candidates)} aday).",
                RuntimeWarning,
                stacklevel=2,
            )
            return max(candidates, key=os.path.getmtime)

        raise RuntimeError(
            f"Deew çıktı dosyası bulunamadı.\n"
            f"Beklenen: {expected_output}\n"
            f"Dizin: {output_dir}"
        )


# ── Yardımcı Fonksiyonlar ───────────────────────────────────────────────────


def encode_wav_to_dolby(
    input_wav: str,
    final_output_path: str,
    fmt: DeewFormat = DeewFormat.DDP,
    bitrate: int | None = None,
    downmix: DeewDownmix | None = None,
    drc: DeewDRC = DeewDRC.MUSIC_LIGHT,
    dialnorm: int = 0,
    delete_wav: bool = True,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """WAV dosyasını Dolby formatına dönüştürür ve istenen konuma taşır.

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
    temp_dir = tempfile.mkdtemp(prefix="deew_")

    try:
        if progress_callback:
            progress_callback(f"Deew ile {fmt.display_name} encoding başlıyor…")

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
        )

        # Çıktıyı istenen konuma taşı
        final_dir = os.path.dirname(final_output_path)
        if final_dir and not os.path.isdir(final_dir):
            os.makedirs(final_dir, exist_ok=True)

        _shutil.move(encoded_path, final_output_path)

        if progress_callback:
            progress_callback(f"Çıktı dosyası taşındı: {os.path.basename(final_output_path)}")

        # Ara WAV dosyasını sil
        if delete_wav and os.path.isfile(input_wav):
            try:
                os.remove(input_wav)
                if progress_callback:
                    progress_callback("Ara WAV dosyası silindi.")
            except OSError:
                if progress_callback:
                    progress_callback("Uyarı: Ara WAV dosyası silinemedi.")

        return final_output_path

    finally:
        # Geçici dizini temizle
        _shutil.rmtree(temp_dir, ignore_errors=True)

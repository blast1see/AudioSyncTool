"""Audio Sync Tool giriş noktası.

Kullanım::

    python -m audio_sync
"""

from __future__ import annotations

import sys


def _check_dependencies() -> None:
    """Gerekli bağımlılıkların kurulu olduğunu doğrular."""
    missing: list[str] = []

    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")

    try:
        from scipy.io import wavfile  # noqa: F401
        from scipy.signal import butter, correlate, sosfiltfilt  # noqa: F401
    except ImportError:
        missing.append("scipy")

    if missing:
        print(
            f"Eksik bağımlılıklar: {', '.join(missing)}\n"
            f"Yüklemek için:\n"
            f"  {sys.executable} -m pip install {' '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    """Uygulamayı başlatır."""
    _check_dependencies()

    from audio_sync.ui.app import AudioSyncApp

    app = AudioSyncApp()
    app.mainloop()


if __name__ == "__main__":
    main()

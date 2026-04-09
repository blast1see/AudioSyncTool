"""Audio Sync Tool giriş noktası.

Kullanım::

    python -m audio_sync
"""

from __future__ import annotations

import importlib.util
import sys


def _check_dependencies() -> None:
    """Gerekli bağımlılıkların kurulu olduğunu doğrular."""
    missing = [
        package
        for package in ("numpy", "scipy")
        if importlib.util.find_spec(package) is None
    ]

    if missing:
        print(
            f"Missing dependencies: {', '.join(missing)}\n"
            f"To install:\n"
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

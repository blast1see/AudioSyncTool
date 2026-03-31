"""Audio Sync Tool -- PyInstaller ile exe derleme betigi.

Kullanim / Usage:
    python setup.py

Bu betik PyInstaller kullanarak tek bir calistiriabilir exe dosyasi olusturur.
This script creates a single executable using PyInstaller.

Gereksinimler / Requirements:
    pip install pyinstaller
"""

import os
import sys
import subprocess


def build_exe() -> None:
    """PyInstaller ile exe dosyasi olusturur."""

    # Proje kok dizini
    project_root = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(project_root, "audio_sync.ico")

    # PyInstaller komut satiri argumanlari
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "AudioSyncTool",
        "--hidden-import", "numpy",
        "--hidden-import", "scipy",
        "--hidden-import", "scipy.io",
        "--hidden-import", "scipy.io.wavfile",
        "--hidden-import", "scipy.signal",
        "--hidden-import", "audio_sync",
        "--hidden-import", "audio_sync.config",
        "--hidden-import", "audio_sync.i18n",
        "--hidden-import", "audio_sync.utils",
        "--hidden-import", "audio_sync.core",
        "--hidden-import", "audio_sync.core.analyzer",
        "--hidden-import", "audio_sync.core.ffmpeg_wrapper",
        "--hidden-import", "audio_sync.core.deew_encoder",
        "--hidden-import", "audio_sync.core.models",
        "--hidden-import", "audio_sync.ui",
        "--hidden-import", "audio_sync.ui.app",
        "--hidden-import", "audio_sync.ui.drop_zone",
        # Qt binding cakismalarini onle
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "PySide2",
        "--exclude-module", "PySide6",
        "--exclude-module", "matplotlib",
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "notebook",
        "--exclude-module", "sphinx",
        "--exclude-module", "docutils",
        "--exclude-module", "pytest",
        "--exclude-module", "PIL",
        "--exclude-module", "zmq",
        "--exclude-module", "cryptography",
        "--clean",
        "--noconfirm",
        os.path.join(project_root, "audio_sync.py"),
    ]

    # Ikon dosyasi varsa ekle
    if os.path.isfile(icon_path):
        # --name'den sonra icon ekle
        idx = args.index("--windowed") + 1
        args.insert(idx, "--icon")
        args.insert(idx + 1, icon_path)
    else:
        print(f"Uyari: Ikon dosyasi bulunamadi: {icon_path}")

    print("=" * 60)
    print("  Audio Sync Tool -- EXE Derleme")
    print("=" * 60)
    print()
    print(f"  Proje dizini : {project_root}")
    print(f"  Ikon         : {icon_path}")
    print(f"  Python       : {sys.executable}")
    print()
    print("  PyInstaller calistiriliyor...")
    print()

    result = subprocess.run(args, cwd=project_root)

    if result.returncode == 0:
        dist_path = os.path.join(project_root, "dist", "AudioSyncTool.exe")
        print()
        print("=" * 60)
        print("  [OK] Derleme basarili!")
        print(f"  Cikti: {dist_path}")
        print("=" * 60)
    else:
        print()
        print("=" * 60)
        print("  [FAIL] Derleme basarisiz!")
        print(f"  Cikis kodu: {result.returncode}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    build_exe()

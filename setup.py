"""Audio Sync Tool -- PyInstaller ile exe derleme betigi.

Kullanim / Usage:
    python setup.py

Bu betik PyInstaller kullanarak tek bir calistiriabilir exe dosyasi olusturur.
This script creates a single executable using PyInstaller.

Gereksinimler / Requirements:
    pip install pyinstaller
"""

import os
import subprocess
import sys

from build_support import (
    ENTRY_SCRIPT,
    ICON_PATH,
    PYINSTALLER_PATHEX,
    PYINSTALLER_EXCLUDES,
    PYINSTALLER_HIDDENIMPORTS,
    build_environment_warning,
)


def build_exe() -> None:
    """PyInstaller ile exe dosyasi olusturur."""

    # Proje kok dizini
    project_root = os.path.dirname(os.path.abspath(__file__))
    # PyInstaller komut satiri argumanlari
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "AudioSyncTool",
        "--clean",
        "--noconfirm",
        str(ENTRY_SCRIPT),
    ]

    for path_entry in PYINSTALLER_PATHEX:
        args.extend(["--paths", path_entry])

    for hidden_import in PYINSTALLER_HIDDENIMPORTS:
        args.extend(["--hidden-import", hidden_import])

    for excluded_module in PYINSTALLER_EXCLUDES:
        args.extend(["--exclude-module", excluded_module])

    # Ikon dosyasi varsa ekle
    if ICON_PATH.is_file():
        # --name'den sonra icon ekle
        idx = args.index("--windowed") + 1
        args.insert(idx, "--icon")
        args.insert(idx + 1, str(ICON_PATH))
    else:
        print(f"Uyari: Ikon dosyasi bulunamadi: {ICON_PATH}")

    print("=" * 60)
    print("  Audio Sync Tool -- EXE Derleme")
    print("=" * 60)
    print()
    print(f"  Proje dizini : {project_root}")
    print(f"  Ikon         : {ICON_PATH}")
    print(f"  Python       : {sys.executable}")
    warning = build_environment_warning(sys.executable)
    if warning:
        print()
        print(f"  Uyari        : {warning}")
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

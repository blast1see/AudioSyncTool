"""Shared build configuration for PyInstaller-based releases."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
ENTRY_SCRIPT = PROJECT_ROOT / "audio_sync.py"
ICON_PATH = PROJECT_ROOT / "audio_sync.ico"
VENDORED_DEEW_ROOT = PROJECT_ROOT / "vendor" / "deew_pkg"
PYINSTALLER_OPTIMIZE = 1

PYINSTALLER_HIDDENIMPORTS = [
    "numpy",
    "scipy",
    "scipy.io",
    "scipy.io.wavfile",
    "scipy.signal",
    "audio_sync",
    "audio_sync.config",
    "audio_sync.i18n",
    "audio_sync.utils",
    "audio_sync.core",
    "audio_sync.core.analyzer",
    "audio_sync.core.ffmpeg_wrapper",
    "audio_sync.core.deew_encoder",
    "audio_sync.core.models",
    "audio_sync.ui",
    "audio_sync.ui.app",
    "audio_sync.ui.drop_zone",
    "audio_sync.ui.stream_dialog",
]

if (VENDORED_DEEW_ROOT / "deew").is_dir():
    PYINSTALLER_HIDDENIMPORTS.append("deew")

PYINSTALLER_PATHEX = [str(PROJECT_ROOT)]
if VENDORED_DEEW_ROOT.is_dir():
    PYINSTALLER_PATHEX.append(str(VENDORED_DEEW_ROOT))

PYINSTALLER_EXCLUDES = [
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "jupyter_client",
    "nbformat",
    "nbconvert",
    "sphinx",
    "docutils",
    "pytest",
    "PIL",
    "zmq",
    "cryptography",
    "qtpy",
    "pandas",
    "pyarrow",
    "dask",
    "distributed",
    "numba",
    "llvmlite",
    "sklearn",
    "skimage",
    "statsmodels",
    "xarray",
    "bokeh",
    "panel",
    "plotly",
    "altair",
    "astropy",
    "openpyxl",
    "lxml",
    "tables",
    "sqlalchemy",
    "botocore",
    "h5py",
    "pyviz_comms",
    "markdown",
]


def is_conda_python(executable: str) -> bool:
    """Best-effort detection for Conda-based Python runtimes."""
    lower = executable.lower()
    if "anaconda" in lower or "miniconda" in lower or "\\conda\\" in lower:
        return True

    exe_path = Path(executable).resolve()
    return (exe_path.parent.parent / "conda-meta").is_dir()


def build_environment_warning(executable: str) -> str | None:
    """Return a warning when the current Python is likely to bloat the build."""
    if not is_conda_python(executable):
        return None

    return (
        "Conda-based Python detected. PyInstaller builds from Conda environments "
        "tend to be significantly larger. Prefer a clean CPython virtualenv for release builds."
    )

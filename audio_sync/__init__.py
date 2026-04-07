"""Audio Sync Tool — Sağlam gecikme tespiti ve senkronizasyon aracı."""

__version__ = "2.2.3"

# Lazy import: AudioSyncApp depends on tkinter which may not be available in
# headless environments.  Importing it eagerly would break ``import audio_sync``
# for library-only usage (e.g. using AudioAnalyzer without a GUI).
__all__: list[str] = []

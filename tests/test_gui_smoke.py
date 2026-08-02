from __future__ import annotations

import threading

import pytest

from audio_sync.i18n import Language, t

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app():
    """The single Tk root every test in this module shares.

    Repeatedly creating and destroying Tk roots in one interpreter is
    unreliable — some Tcl installations fail to re-read their library on a
    later root — so the whole module drives one window instead.
    """
    from audio_sync.ui.app import AudioSyncApp

    try:
        instance = AudioSyncApp()
    except Exception as exc:  # pragma: no cover - environment problem
        pytest.fail(f"GUI could not start: {exc}")

    instance.withdraw()
    instance.update_idletasks()
    yield instance
    instance.destroy()


def test_gui_opens_switches_panels_and_languages(app) -> None:
    assert app._sync_mode_frame.winfo_exists()
    assert app._fps_frame.winfo_exists()

    app._encoding_pipeline_var.set("ffmpeg")
    app._on_encoding_pipeline_change("ffmpeg")
    assert app._ffmpeg_enc_frame.winfo_manager() == "pack"

    app._on_language_change(Language.TR.display_name)
    assert app._i18n.language is Language.TR
    app._on_language_change(Language.EN.display_name)
    assert app._i18n.language is Language.EN


def test_wheel_over_the_log_box_does_not_scroll_the_page(app) -> None:
    assert app._scrolls_itself(app.log_box)
    assert not app._scrolls_itself(app._content)
    assert not app._scrolls_itself(app._canvas)


def test_progress_reports_percentage_and_stage(app) -> None:
    app._set_progress(42)
    app._log("Analyzing delay…")
    app.update()

    assert app._percent_lbl.cget("text") == "%42"
    assert "Analyzing delay" in app._status_lbl.cget("text")

    # Out-of-range values must not paint outside the bar.
    app._set_progress(140)
    app.update()
    assert app._percent_lbl.cget("text") == "%100"

    app._set_progress(0)
    app.update()
    assert app._percent_lbl.cget("text") == ""


def test_deew_status_is_probed_off_the_event_loop(app, monkeypatch) -> None:
    """Resolving deew starts a process with a 15 s timeout — never inline."""
    import audio_sync.ui.app as app_module

    probed = threading.Event()
    probe_threads: list[threading.Thread] = []
    release = threading.Event()

    def recording_status() -> tuple[bool, str]:
        probe_threads.append(threading.current_thread())
        probed.set()
        release.wait(timeout=10)
        return True, "deew"

    monkeypatch.setattr(app_module, "get_deew_runtime_status", recording_status)
    app._deew_available = None
    app._deew_probe_running = False

    app._update_deew_status()

    # The call returned while the probe is still blocked, and the badge shows
    # a pending state instead of a stale answer.
    assert app._deew_status_lbl.cget("text") == t("deew_checking")
    assert app._deew_available is None
    assert probed.wait(timeout=10), "deew status was never probed"
    assert probe_threads[0] is not threading.main_thread()
    release.set()

    # The worker hands the result back through the event loop; drive that
    # callback directly, since cross-thread ``after`` only delivers while
    # ``mainloop`` is running and this test never enters it.
    app._on_deew_status_probed(True)
    assert app._deew_available is True
    assert app._deew_status_lbl.cget("text") == t("deew_ready")


def test_late_worker_callbacks_are_dropped_after_teardown(app) -> None:
    """A probe that finishes after the window closed must not touch Tcl."""
    ran: list[str] = []
    app._closing = True
    try:
        app.schedule(lambda: ran.append("callback"))
        app.schedule_later(0, lambda: ran.append("delayed"))
        app.update()
        assert ran == []
    finally:
        app._closing = False

    # With the window alive again the same helper still delivers.
    app.schedule(lambda: ran.append("callback"))
    app.update()
    assert ran == ["callback"]

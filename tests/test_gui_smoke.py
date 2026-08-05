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


def test_switching_language_keeps_the_selected_sync_mode(app) -> None:
    """The menu stores a label, so relabelling must not silently reset it."""
    from audio_sync.config import SyncMode

    app._on_language_change(Language.EN.display_name)
    app.sync_mode_var.set(SyncMode.RUBBERBAND.display_name)
    assert app._get_selected_sync_mode() is SyncMode.RUBBERBAND

    app._on_language_change(Language.TR.display_name)
    assert app.sync_mode_var.get() == SyncMode.RUBBERBAND.display_name_tr
    assert app._get_selected_sync_mode() is SyncMode.RUBBERBAND

    app._on_language_change(Language.EN.display_name)
    assert app._get_selected_sync_mode() is SyncMode.RUBBERBAND
    app.sync_mode_var.set(SyncMode.ADELAY_AMIX.display_name)


def test_new_labels_are_translated(app) -> None:
    """Widgets added in the redesign must join the language refresh."""
    def labels(app):
        return {
            app._correct_drift_cb.cget("text"),
            app._correct_steps_cb.cget("text"),
            app._fps_auto_cb.cget("text"),
            app._timing_note_lbl.cget("text"),
            app._readout_caption.cget("text"),
            app._readout_detail.cget("text"),
        }

    app._on_language_change(Language.TR.display_name)
    turkish = labels(app)
    app._on_language_change(Language.EN.display_name)
    english = labels(app)
    assert not turkish & english, f"untranslated: {turkish & english}"


def test_layout_fits_a_1080p_screen(app) -> None:
    """The whole window must be usable without scrolling on a 1920x1080 panel.

    v2.3 stacked every panel in one column and needed ~1460 px of height, so
    the primary action sat below the fold on the most common desktop size.
    """
    app.update_idletasks()
    content_h = app._content.winfo_reqheight()
    chrome_h = app._bottom_bar.winfo_reqheight()

    # 1080 minus the taskbar and the window frame.
    usable_h = 1080 - 120
    assert content_h + chrome_h <= usable_h, (
        f"needs {content_h + chrome_h}px, only {usable_h}px available"
    )
    assert app._content.winfo_reqwidth() <= 1920


def test_cancel_is_hidden_until_there_is_work_to_cancel(app) -> None:
    app._set_cancel_active(False)
    app.update_idletasks()
    assert app.cancel_btn.winfo_manager() == ""

    app._set_cancel_active(True)
    app.update_idletasks()
    assert app.cancel_btn.winfo_manager() == "pack"
    assert str(app.cancel_btn.cget("state")) == "normal"

    app._set_cancel_active(False)
    app.update_idletasks()
    assert app.cancel_btn.winfo_manager() == ""


def test_scatter_downgrades_the_readout_even_at_a_good_score(app) -> None:
    """A confident-looking score must not present a result that cannot hold.

    Measured on a 132-minute pair: confidence 4.5, and the produced file was
    seconds out at the ends because the windows disagreed by 200 ms.
    """
    from audio_sync.core.models import AnalysisResult

    scattered = AnalysisResult(
        delay_ms=32873.0, coarse_ms=32672.0, confidence=4.5,
        total_segments=56, used_segments=31, drift_ms_per_min=-2.0,
        skip_fallback=False, residual_mad_ms=200.0,
    )
    app._display_analysis_result(scattered)
    app.update()

    detail = app._readout_detail.cget("text")
    assert t("confidence_weak") in detail
    assert t("confidence_strong") not in detail
    assert "200" in detail

    app._show_readout(None)


def test_readout_shows_signed_milliseconds_and_clears(app) -> None:
    app._show_readout(-2498.0, detail="sync audio is behind")
    app.update_idletasks()
    assert app.delay_val.cget("text") == "-2498"
    assert app._readout_unit.cget("text") == "ms"

    app._show_readout(None)
    app.update_idletasks()
    assert app.delay_val.cget("text") == "—"
    assert app._readout_unit.cget("text") == ""


def test_wheel_over_the_log_box_does_not_scroll_the_page(app) -> None:
    assert app._scrolls_itself(app.log_box)
    assert not app._scrolls_itself(app._content)
    assert not app._scrolls_itself(app._canvas)


def test_progress_reports_percentage_and_stage(app) -> None:
    app._set_progress(42)
    app._log("Analyzing delay…")
    app.update()

    # The sign sits on whichever side the active language puts it — the fixture
    # runs in English, where "%42" would be wrong.
    assert app._percent_lbl.cget("text") == "42%"
    assert "Analyzing delay" in app._status_lbl.cget("text")

    # Out-of-range values must not paint outside the bar.
    app._set_progress(140)
    app.update()
    assert app._percent_lbl.cget("text") == "100%"

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

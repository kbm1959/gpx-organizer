"""Smoke tests for the Milestone 2 app shell."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Event
from time import monotonic

import pytest


@pytest.mark.skipif(
    os.environ.get("DISPLAY") is None and os.environ.get("QT_QPA_PLATFORM") is None,
    reason="No display available for Qt smoke test",
)
def test_main_window_constructs() -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer.main_window import MainWindow
    from gpx_organizer.qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    library_root = Path.home() / ".config" / "gpx-organizer" / "library-test-smoke"
    store = LibraryStore(library_root)
    store.initialize()
    window = MainWindow(library_store=store)

    assert window.windowTitle().startswith("GPX Organizer")
    assert window.statusBar() is not None

    window.close()
    if QApplication.instance() is app:
        app.quit()


@pytest.mark.skipif(
    os.environ.get("DISPLAY") is None and os.environ.get("QT_QPA_PLATFORM") is None,
    reason="No display available for Qt smoke test",
)
def test_folder_preview_worker_and_large_document(tmp_path: Path, monkeypatch) -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer import main_window
    from gpx_organizer.qt_compat import QApplication

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(main_window, "QWebEngineView", None)
    monkeypatch.setattr(main_window.webbrowser, "open", lambda *args: None)
    app = QApplication.instance() or QApplication([])
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    window = main_window.MainWindow(store)
    folder_id = store.create_folder("Preview", store.get_root_folder_id())
    window._folder_ids.add(folder_id)
    monkeypatch.setattr(window, "_selected_folder_id", lambda: folder_id)
    monkeypatch.setattr(window, "_selected_track_ids", lambda: [])
    gpx = tmp_path / "track.gpx"
    gpx.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="48" lon="7"/><trkpt lat="49" lon="8"/>'
        '</trkseg></trk></gpx>', encoding="utf-8"
    )
    inputs = [(index, gpx, f"Track {index}", f"Folder/Track {index}") for index in range(500)]
    window._start_folder_preview_worker(folder_id, inputs, len(inputs))
    deadline = monotonic() + 10
    while folder_id not in window._preview_cache and monotonic() < deadline:
        app.processEvents()
        Event().wait(0.005)
    assert folder_id in window._preview_cache
    assert '"trackId": 499,' in window._preview_cache[folder_id].html

    started = Event()
    release = Event()

    class BlockingMapService(main_window.LeafletMapService):
        def render_track_lines_preview(self, tracks, progress=None, on_error=None):
            started.set()
            release.wait(5)
            progress(1, 1)
            return self.render_placeholder("Old preview", "Old preview")

    window.map_service = BlockingMapService()
    window._start_folder_preview_worker(folder_id, inputs[:1], 1)
    assert started.wait(5)
    window._preview_cancel.set()
    monkeypatch.setattr(window, "_selected_folder_id", lambda: folder_id + 1)
    release.set()
    deadline = monotonic() + 10
    while window._preview_worker_folder is not None and monotonic() < deadline:
        app.processEvents()
        Event().wait(0.005)
    assert window._preview_worker_folder is None
    assert '"trackId": 499,' in window._preview_cache[folder_id].html
    monkeypatch.setattr(window, "_selected_folder_id", lambda: folder_id)

    class FakeView:
        def load(self, url):
            self.path = Path(url.toLocalFile())

        def setHtml(self, html):
            self.html = html

        def page(self):
            return self

        def runJavaScript(self, script, callback):
            callback(False)

    view = FakeView()
    window.map_web_view = view
    html = "<html>" + "x" * (main_window.WEBENGINE_SETHTML_MAX_CHARS + 1) + "</html>"
    window._set_map_html(html, folder_preview=True)
    assert view.path.read_text(encoding="utf-8") == html
    window._folder_map_load_finished(False)
    assert "failed" in window.statusBar().currentMessage().lower()
    window._set_map_html(html, folder_preview=True)
    window._folder_map_load_finished(True)
    assert "initialize" in window.statusBar().currentMessage().lower()

    previous_html = window._preview_cache[folder_id].html
    stale = main_window.LeafletMapService().render_placeholder("Stale", "Stale")
    window._folder_preview_completed(folder_id, window._preview_revision - 1, (stale, []), 1, "")
    assert window._preview_cache[folder_id].html == previous_html
    window._preview_cache_queue.clear()
    window.map_web_view = None
    window.close()


@pytest.mark.skipif(
    os.environ.get("GPX_WEBENGINE_TEST") != "1",
    reason="Run WebEngine integration in a separate Qt process",
)
def test_large_folder_document_loads_in_webengine(tmp_path: Path, monkeypatch) -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer.main_window import MainWindow, WEBENGINE_SETHTML_MAX_CHARS
    from gpx_organizer.qt_compat import QApplication, QWebEngineView

    if QWebEngineView is None:
        pytest.skip("Qt WebEngine unavailable")
    monkeypatch.setenv("HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    window = MainWindow(store)
    html = (
        '<html><body><div id="map"></div><script>'
        'window.L = {}; window.__gpxFitTrack = function() {};</script><!--'
        + "x" * (WEBENGINE_SETHTML_MAX_CHARS + 1) + '--></body></html>'
    )
    window._set_map_html(html, folder_preview=True)
    deadline = monotonic() + 15
    while window._folder_map_loading and monotonic() < deadline:
        app.processEvents()
        Event().wait(0.005)
    assert not window._folder_map_loading
    assert window.statusBar().currentMessage() == "Folder map loaded"
    assert window.map_web_view.url().isLocalFile()
    window.close()

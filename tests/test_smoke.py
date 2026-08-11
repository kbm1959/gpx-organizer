"""Smoke tests for the Milestone 2 app shell."""

from __future__ import annotations

import os
from pathlib import Path

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

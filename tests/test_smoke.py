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
    folder_id = store.create_tray("Preview", store.get_root_folder_id())
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
        def render_track_lines_preview(self, tracks, progress=None, on_error=None, cache=None):
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

    window.map_service = main_window.LeafletMapService()
    imported = store.import_gpx(gpx, target_folder_id=folder_id)
    window._start_folder_preview_worker(
        folder_id, [(imported.track_id, imported.managed_path, "Track", "Folder/Track")], 1
    )
    deadline = monotonic() + 10
    while window._preview_worker_folder is not None and monotonic() < deadline:
        app.processEvents()
        Event().wait(0.005)
    assert window._preview_worker_folder is None
    with store.preview_data_cache() as cache:
        assert cache.get(imported.track_id, imported.managed_path) is not None

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
    os.environ.get("DISPLAY") is None and os.environ.get("QT_QPA_PLATFORM") is None,
    reason="No display available for Qt smoke test",
)
def test_tray_ui_and_folder_tree_import(tmp_path: Path, monkeypatch) -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer import main_window
    from gpx_organizer.qt_compat import QApplication

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(main_window, "QWebEngineView", None)
    monkeypatch.setattr(main_window.webbrowser, "open", lambda *args: None)
    app = QApplication.instance() or QApplication([])
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    root = store.get_root_folder_id()
    tray = store.create_tray("Holding", root)
    window = main_window.MainWindow(store)
    window._load_library_tree(selected_folder_id=tray)
    assert window._selected_folder_kind() == "tray"
    assert window._import_action.isEnabled()
    assert window._import_folder_tree_action.isEnabled()
    assert not window._tray_icon.isNull()
    assert window.library_tree.currentItem().icon(0).cacheKey() == window._tray_icon.cacheKey()
    window._clipboard_payload = main_window._ClipboardPayload(kind="items", item_ids=(1,))
    assert window._can_paste_into_kind("tray")
    assert not window._can_paste_into_kind("normal")
    window._clipboard_payload = main_window._ClipboardPayload(kind="folder", folder_id=tray)
    assert window._can_paste_into_kind("normal")
    assert not window._can_paste_into_kind("tray")

    source = tmp_path / "Trip"
    (source / "Items").mkdir(parents=True)
    gpx = ('<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
           '<trkpt lat="48" lon="7"/><trkpt lat="49" lon="8"/>'
           '</trkseg></trk></gpx>')
    (source / "direct.gpx").write_text(gpx, encoding="utf-8")
    (source / "Items" / "nested.gpx").write_text(gpx, encoding="utf-8")
    imported, _, _, failures, imported_root, _, processed = window._import_folder_tree_recursive(source)
    assert (imported, failures, processed) == (2, [], 2)
    folders = store.list_folders()
    children = {node.name: node for node in folders if node.parent_id == imported_root}
    assert store.get_folder(imported_root).kind == "normal"
    assert children["Items"].kind == children["Items (1)"].kind == "tray"
    assert len(store.list_tracks_recursive(imported_root)) == 2

    (source / "Items" / "Items").mkdir()
    (source / "Items" / "Items" / "more.gpx").write_text(gpx, encoding="utf-8")
    imported, _, _, failures, _, _, _ = window._import_folder_tree_recursive(source)
    assert imported == 3 and not failures
    assert store.get_folder(children["Items"].id).kind == "normal"
    promoted_children = {node.name: node for node in store.list_folders() if node.parent_id == children["Items"].id}
    assert len(store.list_tracks(promoted_children["Items"].id)) == 1
    assert len(store.list_tracks(promoted_children["Items (1)"].id)) == 2
    assert len(store.list_tracks_recursive(imported_root)) == 5
    assert all(store.get_folder(track.folder_id).kind == "tray" for track in store.list_tracks_recursive(imported_root))

    same_folder = store.create_folder("Shared", root)
    same_tray = store.create_tray("Shared", root)
    folder_source = tmp_path / "folder-source" / "Shared"
    (folder_source / "Nested").mkdir(parents=True)
    (folder_source / "Nested" / "track.gpx").write_text(gpx, encoding="utf-8")
    _, _, _, failures, folder_result, _, _ = window._import_folder_tree_recursive(folder_source)
    assert not failures and folder_result == same_folder
    assert store.get_folder(same_tray).kind == "tray"
    assert not store.list_tracks(same_tray)

    tray_source = tmp_path / "tray-source" / "Shared"
    tray_source.mkdir(parents=True)
    (tray_source / "track.gpx").write_text(gpx, encoding="utf-8")
    _, _, _, failures, tray_result, _, _ = window._import_folder_tree_recursive(tray_source)
    assert not failures and tray_result == same_tray
    assert len(store.list_tracks(same_tray)) == 1
    assert len(store.list_tracks_recursive(same_folder)) == 1

    window._load_library_tree(selected_folder_id=root)
    assert not window._import_action.isEnabled()
    assert not window._import_folder_tree_action.isEnabled()
    window.close()
    app.processEvents()


@pytest.mark.skipif(
    os.environ.get("DISPLAY") is None and os.environ.get("QT_QPA_PLATFORM") is None,
    reason="No display available for Qt smoke test",
)
def test_create_multiple_trays_dialog(tmp_path: Path, monkeypatch) -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer import main_window
    from gpx_organizer.qt_compat import QApplication, QDialog, QLineEdit, QSpinBox

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(main_window, "QWebEngineView", None)
    monkeypatch.setattr(main_window.webbrowser, "open", lambda *args: None)
    app = QApplication.instance() or QApplication([])
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    root = store.get_root_folder_id()
    window = main_window.MainWindow(store)
    window._load_library_tree(selected_folder_id=root)
    created_names = ["Road rides", "Gravel rides", "Weekend rides"]

    def accept_names(dialog):
        count_spin = dialog.findChild(QSpinBox)
        assert count_spin is not None and count_spin.value() == 1
        fields = dialog.findChildren(QLineEdit, "trayNameInput")
        assert len(fields) == 1 and fields[0].text() == ""
        fields[0].setText("Road rides")
        count_spin.setValue(3)
        fields = dialog.findChildren(QLineEdit, "trayNameInput")
        assert len(fields) == 3
        assert [field.text() for field in fields] == ["Road rides", "", ""]
        for field, name in zip(fields, created_names):
            field.setText(name)
        return int(QDialog.DialogCode.Accepted)

    monkeypatch.setattr(QDialog, "exec", accept_names)
    window._create_tray_dialog()
    created = sorted(
        (folder for folder in store.list_folders() if folder.name in created_names),
        key=lambda folder: folder.position,
    )
    assert [folder.name for folder in created] == created_names
    assert all(folder.kind == "tray" and folder.parent_id == root for folder in created)
    assert window._selected_folder_id() == created[0].id
    assert "Created 3 tray(s)" in window.statusBar().currentMessage()
    window.close()
    app.processEvents()


@pytest.mark.skipif(
    os.environ.get("DISPLAY") is None and os.environ.get("QT_QPA_PLATFORM") is None,
    reason="No display available for Qt smoke test",
)
def test_low_distance_per_point_tracks_are_highlighted(tmp_path: Path, monkeypatch) -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer import main_window
    from gpx_organizer.qt_compat import QApplication, QColor

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(main_window, "QWebEngineView", None)
    monkeypatch.setattr(main_window.webbrowser, "open", lambda *args: None)
    app = QApplication.instance() or QApplication([])
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    tray = store.create_tray("Tracks", store.get_root_folder_id())
    short_source = tmp_path / "short.gpx"
    short_points = "".join(
        f'<trkpt lat="{48 + index * 0.000001:.6f}" lon="7"><ele>100</ele></trkpt>'
        for index in range(5)
    )
    short_source.write_text(
        f'<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>{short_points}</trkseg></trk></gpx>',
        encoding="utf-8",
    )
    short_track = store.import_gpx(short_source, tray)
    normal_source = tmp_path / "normal.gpx"
    normal_source.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="48" lon="7"/><trkpt lat="48.01" lon="7"/>'
        '</trkseg></trk></gpx>', encoding="utf-8"
    )
    normal_track = store.import_gpx(normal_source, tray)
    waypoint_source = tmp_path / "waypoint.gpx"
    waypoint_source.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><wpt lat="48" lon="7"/></gpx>',
        encoding="utf-8",
    )
    waypoint = store.import_gpx(waypoint_source, tray)

    window = main_window.MainWindow(store)
    window._load_library_tree(selected_folder_id=tray)
    items = {
        int(window.track_list.item(index).data(main_window.TRACK_ID_ROLE)): window.track_list.item(index)
        for index in range(window.track_list.count())
        if window.track_list.item(index).data(main_window.TRACK_ID_ROLE) is not None
    }
    flagged = items[short_track.track_id]
    assert flagged.font().bold()
    assert flagged.foreground().color() == QColor("#c62828")
    assert "m/track point" in flagged.toolTip()
    flagged.setSelected(True)
    assert flagged.foreground().color() == QColor("#c62828")
    assert not items[normal_track.track_id].font().bold()
    assert not items[waypoint.track_id].font().bold()
    window.close()
    app.processEvents()


@pytest.mark.skipif(
    os.environ.get("DISPLAY") is None and os.environ.get("QT_QPA_PLATFORM") is None,
    reason="No display available for Qt smoke test",
)
def test_svg_icons_render_and_prefer_vector(tmp_path: Path, monkeypatch) -> None:
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
    icon_dir = Path(main_window.__file__).resolve().parent / "icons"
    real_icon = main_window.QIcon
    attempted: list[str] = []

    def recording_icon(source=None):
        if isinstance(source, str):
            attempted.append(Path(source).name)
        return real_icon() if source is None else real_icon(source)

    with monkeypatch.context() as patch:
        patch.setattr(main_window, "QIcon", recording_icon)
        for name in ("folder-closed", "folder-open", "folder_selected", "folder-open-selected", "folder-hover", "tray", "map-pin", "track"):
            attempted.clear()
            icon = window._load_icon_candidate(icon_dir, [f"{name}.svg", f"{name}.png"])
            assert icon is not None
            assert attempted == [f"{name}.svg"]
            for size in (16, 48):
                image = icon.pixmap(size, size).toImage()
                assert any(image.pixelColor(x, y).alpha() for x in range(image.width()) for y in range(image.height()))

        def unsupported_svg_icon(source=None):
            if isinstance(source, str) and source.endswith(".svg"):
                return real_icon()
            return real_icon() if source is None else real_icon(source)

        patch.setattr(main_window, "QIcon", unsupported_svg_icon)
        patch.setattr(main_window.shutil, "which", lambda name: None)
        fallback = window._load_icon_candidate(icon_dir, ["tray.svg", "tray.png"])
        assert fallback is not None and not fallback.pixmap(16, 16).isNull()
    window.close()
    app.processEvents()


@pytest.mark.skipif(
    os.environ.get("DISPLAY") is None and os.environ.get("QT_QPA_PLATFORM") is None,
    reason="No display available for Qt smoke test",
)
def test_track_analysis_follows_list_and_selection(tmp_path: Path, monkeypatch) -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer import main_window
    from gpx_organizer.qt_compat import QApplication, QDialog, Qt
    from gpx_organizer.settings_store import (
        get_time_zone,
        get_track_rest_endpoint_distance_multiplier,
        get_track_rest_min_duration_s,
        get_track_rest_radius_m,
    )
    from gpx_organizer.track_analysis import summarize_tracks

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(main_window, "QWebEngineView", None)
    monkeypatch.setattr(main_window.webbrowser, "open", lambda *args: None)
    app = QApplication.instance() or QApplication([])
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    folder = store.create_folder("Trips", store.get_root_folder_id())
    tray = store.create_tray("Tracks", folder)
    empty = store.create_tray("Empty", folder)
    source = tmp_path / "track.gpx"
    source.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="48" lon="7"><ele>100</ele><time>2026-01-01T10:00:00Z</time></trkpt>'
        '<trkpt lat="48.001" lon="7.001"><ele>110</ele><time>2026-01-01T10:01:00Z</time></trkpt>'
        '</trkseg></trk></gpx>', encoding="utf-8"
    )
    first = store.import_gpx(source, tray)
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            '</trkseg>',
            '<trkpt lat="48.002" lon="7.002"><ele>105</ele><time>2026-01-01T10:02:00Z</time></trkpt></trkseg>',
        ), encoding="utf-8"
    )
    second = store.import_gpx(source, tray)
    waypoint_path = tmp_path / "waypoint.gpx"
    waypoint_path.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><wpt lat="48" lon="7"/></gpx>', encoding="utf-8"
    )
    waypoint = store.import_gpx(waypoint_path, tray)
    window = main_window.MainWindow(store)
    window._preview_folder_track_list_enabled = False
    menus = {
        action.text(): action.menu()
        for action in window.menuBar().actions()
    }
    assert menus["Edit"].actions()[-1].text() == "Preferences..."
    assert all(action.text() != "Preferences..." for action in menus["View"].actions())
    window._load_library_tree(selected_folder_id=tray)

    def wait_for_analysis() -> None:
        deadline = monotonic() + 10
        while (window._analysis_update_timer.isActive() or window._analysis_worker_active) and monotonic() < deadline:
            app.processEvents()
            Event().wait(0.005)
        assert not window._analysis_update_timer.isActive()
        assert not window._analysis_worker_active

    wait_for_analysis()
    assert [window._analysis_tabs.tabText(index) for index in range(4)] == ["Properties", "Comments", "Links", "Graph"]
    assert window._analysis_scope_label.text() == "All listed tracks: 2"
    assert window._analysis_values["point_count"].text() == "5 pts"
    assert window._analysis_values["start_time"].text() == "2026-01-01\n11:00:00\nCET (UTC+01:00)"
    assert window._analysis_values["end_time"].text() == "2026-01-01\n11:02:00\nCET (UTC+01:00)"
    assert window._analysis_values["elapsed_s"].text() == "00:03:00 h:m:s"
    assert float(window._analysis_values["distance_m"].text().split()[0]) > 0
    assert float(window._analysis_values["max_uphill_percent"].text().split()[0]) > 0
    assert float(window._analysis_values["max_downhill_percent"].text().split()[0]) < 0
    analyses, failures = store.get_track_analyses([first.track_id, second.track_id])
    assert not failures
    summary = summarize_tracks(analyses)
    for key in ("distance_m", "area_km2", "average_speed_kmh", "moving_average_speed_kmh", "min_speed_kmh", "max_speed_kmh"):
        value = summary[key] / 1000 if key == "distance_m" else summary[key]
        assert window._analysis_values[key].text() == f"{value:.1f} {window._analysis_units[key]}"
    for key in ("min_elevation_m", "max_elevation_m", "ascent_m", "descent_m", "max_uphill_percent", "max_downhill_percent"):
        assert window._analysis_values[key].text() == f"{round(summary[key])} {window._analysis_units[key]}"
    properties = window._analysis_values["point_count"].parentWidget()
    grid = properties.layout().itemAt(0).layout()
    window.resize(1400, 840)
    window.show()
    app.processEvents()
    for index in range(grid.count()):
        widget = grid.itemAt(index).widget()
        if widget is not None and widget.hasHeightForWidth():
            assert widget.height() >= widget.heightForWidth(widget.width())
    for key, unit in {
        "point_count": "pts", "distance_m": "km", "area_km2": "km\u00b2",
        "start_time": "", "elapsed_s": "h:m:s", "rest_count": "rests",
        "average_speed_kmh": "km/h", "min_elevation_m": "m", "max_uphill_percent": "%",
    }.items():
        index = grid.indexOf(window._analysis_values[key])
        row, column, _, _ = grid.getItemPosition(index)
        assert column == 1
        assert window._analysis_values[key].alignment() & Qt.AlignmentFlag.AlignLeft
        assert window._analysis_units[key] == unit
        if unit:
            assert window._analysis_values[key].text().endswith(f" {unit}")

    items = {
        int(window.track_list.item(index).data(main_window.TRACK_ID_ROLE)): window.track_list.item(index)
        for index in range(window.track_list.count())
        if window.track_list.item(index).data(main_window.TRACK_ID_ROLE) is not None
    }
    window.track_list.setCurrentItem(items[first.track_id])
    wait_for_analysis()
    assert window._analysis_scope_label.text() == "Selected tracks: 1"
    assert window._analysis_values["point_count"].text() == "2 pts"
    assert window._analysis_values["end_time"].text() == "2026-01-01\n11:01:00\nCET (UTC+01:00)"
    items[second.track_id].setSelected(True)
    items[waypoint.track_id].setSelected(True)
    wait_for_analysis()
    assert window._analysis_scope_label.text() == "Selected tracks: 2"
    assert window._analysis_values["point_count"].text() == "5 pts"
    window.track_list.clearSelection()
    window.track_list.setCurrentItem(items[waypoint.track_id])
    wait_for_analysis()
    assert window._analysis_scope_label.text() == "No tracks selected"
    assert window._analysis_values["point_count"].text() == "\u2014"
    window.track_list.clearSelection()
    wait_for_analysis()
    assert window._analysis_scope_label.text() == "All listed tracks: 2"

    started = Event()
    release = Event()
    load_analyses = store.get_track_analyses

    def delayed_analysis(
        track_ids,
        progress=None,
        rest_radius_m=2.0,
        rest_min_duration_s=60.0,
        rest_endpoint_distance_multiplier=10.0,
    ):
        if track_ids == [first.track_id]:
            started.set()
            release.wait(5)
        return load_analyses(
            track_ids,
            progress=progress,
            rest_radius_m=rest_radius_m,
            rest_min_duration_s=rest_min_duration_s,
            rest_endpoint_distance_multiplier=rest_endpoint_distance_multiplier,
        )

    monkeypatch.setattr(store, "get_track_analyses", delayed_analysis)
    window.track_list.setCurrentItem(items[first.track_id])
    deadline = monotonic() + 5
    while not started.is_set() and monotonic() < deadline:
        app.processEvents()
        Event().wait(0.005)
    assert started.is_set()
    window.track_list.setCurrentItem(items[second.track_id])
    release.set()
    wait_for_analysis()
    assert window._analysis_scope_label.text() == "Selected tracks: 1"
    assert window._analysis_values["point_count"].text() == "3 pts"

    def accept_timezone(dialog):
        assert dialog.selected_time_zone() == "Europe/Berlin"
        dialog._time_zone_combo.setCurrentText("UTC")
        assert dialog.selected_rest_stop_radius_m() == 2.0
        assert dialog.selected_rest_stop_min_duration_s() == 60.0
        assert dialog.selected_rest_stop_endpoint_distance_multiplier() == 10.0
        dialog._rest_stop_radius_spin.setValue(5.0)
        dialog._rest_stop_min_duration_spin.setValue(120)
        dialog._rest_stop_endpoint_distance_multiplier_spin.setValue(5.0)
        return int(QDialog.DialogCode.Accepted)

    with monkeypatch.context() as patch:
        patch.setattr(main_window.PreferencesDialog, "exec", accept_timezone)
        window._open_preferences_dialog()
    wait_for_analysis()
    assert get_time_zone() == "UTC"
    assert get_track_rest_radius_m() == 5.0
    assert get_track_rest_min_duration_s() == 120.0
    assert get_track_rest_endpoint_distance_multiplier() == 5.0
    assert window.map_service.rest_stop_radius_m == 5.0
    assert window.map_service.rest_stop_min_duration_s == 120.0
    assert window.map_service.rest_stop_endpoint_distance_multiplier == 5.0
    assert window._analysis_values["start_time"].text() == "2026-01-01\n10:00:00\nUTC (UTC+00:00)"
    assert window.map_service.time_zone == "UTC"
    map_payload = window.map_service._build_track_payload(second.managed_path, "Track")
    assert map_payload["startTimeDisplay"] == window._analysis_values["start_time"].text().replace("\n", " ")
    assert all(
        stop["durationMin"] >= 2.0
        for stop in map_payload["restStops"]
    )
    saved_analyses, failures = store.get_track_analyses(
        [second.track_id], rest_radius_m=5.0, rest_min_duration_s=120.0,
        rest_endpoint_distance_multiplier=5.0,
    )
    assert not failures
    assert saved_analyses[0]["rest_radius_m"] == 5.0
    assert saved_analyses[0]["rest_min_duration_s"] == 120.0
    assert saved_analyses[0]["rest_endpoint_distance_multiplier"] == 5.0

    window._load_library_tree(selected_folder_id=empty)
    wait_for_analysis()
    assert window._analysis_scope_label.text() == "No tracks in this view"
    window.close()
    app.processEvents()


@pytest.mark.skipif(
    os.environ.get("DISPLAY") is None and os.environ.get("QT_QPA_PLATFORM") is None,
    reason="No display available for Qt smoke test",
)
def test_selection_highlights_and_folder_icon_states(tmp_path: Path, monkeypatch) -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer import main_window
    from gpx_organizer.qt_compat import QApplication, QListWidgetItem

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(main_window, "QWebEngineView", None)
    monkeypatch.setattr(main_window.webbrowser, "open", lambda *args: None)
    app = QApplication.instance() or QApplication([])
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    folder_id = store.create_folder("Folder", store.get_root_folder_id())
    tray_id = store.create_tray("Tray", folder_id)
    window = main_window.MainWindow(store)
    window._preview_folder_track_list_enabled = False
    window._load_library_tree(selected_folder_id=folder_id)
    window.show()
    app.processEvents()
    tree = window.library_tree
    track_list = window.track_list
    assert tree is not None and track_list is not None
    folder = window._find_tree_item_by_folder_id(folder_id)
    assert folder is not None

    def selected_background(widget, item):
        rect = widget.visualItemRect(item)
        image = widget.viewport().grab().toImage()
        return image.pixelColor(min(image.width() - 3, rect.right() - 3), rect.center().y())

    def assert_light_selection(widget, item):
        color = selected_background(widget, item)
        assert abs(color.red() - 211) <= 8
        assert abs(color.green() - 230) <= 8
        assert abs(color.blue() - 244) <= 8

    folder.setExpanded(False)
    app.processEvents()
    assert folder.icon(0).cacheKey() == window._folder_selected_icon.cacheKey()
    assert_light_selection(tree, folder)
    folder.setExpanded(True)
    app.processEvents()
    assert folder.icon(0).cacheKey() == window._folder_open_selected_icon.cacheKey()
    tree._set_drop_hover_item(folder)
    assert folder.icon(0).cacheKey() == window._folder_hover_icon.cacheKey()
    tree._set_drop_hover_item(None)
    assert folder.icon(0).cacheKey() == window._folder_open_selected_icon.cacheKey()

    tree.setCurrentItem(window._find_tree_item_by_folder_id(tray_id))
    assert folder.icon(0).cacheKey() == window._folder_open_icon.cacheKey()
    assert tree.currentItem().icon(0).cacheKey() == window._tray_icon.cacheKey()
    track_list.clear()
    for label, icon in (("Track", window._track_item_icon), ("Waypoint", window._waypoint_item_icon)):
        item = QListWidgetItem(label)
        item.setIcon(icon)
        track_list.addItem(item)
        track_list.setCurrentItem(item)
        app.processEvents()
        assert_light_selection(track_list, item)
        window._preview_update_timer.stop()
    window.close()
    app.processEvents()


@pytest.mark.skipif(
    os.environ.get("DISPLAY") is None and os.environ.get("QT_QPA_PLATFORM") is None,
    reason="No display available for Qt smoke test",
)
def test_tree_drop_destinations(monkeypatch, tmp_path: Path) -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer import main_window
    from gpx_organizer.qt_compat import QApplication, QMimeData, QPoint, QUrl, Qt

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(main_window, "QWebEngineView", None)
    monkeypatch.setattr(main_window.webbrowser, "open", lambda *args: None)
    app = QApplication.instance() or QApplication([])
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    root = store.get_root_folder_id()
    folder = store.create_folder("Folder", root)
    tray = store.create_tray("Tray", folder)
    window = main_window.MainWindow(store)
    window._load_library_tree(selected_folder_id=folder)
    tree = window.library_tree
    assert tree is not None

    class Position:
        def toPoint(self):
            return QPoint(0, 0)

    class DropEvent:
        def __init__(self, mime):
            self.mime = mime
            self.accepted = False
            self.action = Qt.DropAction.MoveAction

        def mimeData(self):
            return self.mime

        def position(self):
            return Position()

        def accept(self):
            self.accepted = True

        def acceptProposedAction(self):
            self.accepted = True

        def ignore(self):
            self.accepted = False

        def setDropAction(self, action):
            self.action = action

        def dropAction(self):
            return self.action

    items = QMimeData()
    items.setData(main_window.TRACK_IDS_MIME, b"42")
    folders = QMimeData()
    folders.setData(main_window.FOLDER_ID_MIME, b"42")
    external = QMimeData()
    external.setUrls([QUrl.fromLocalFile(str(tmp_path / "track.gpx"))])
    emitted: list[str] = []
    tree.track_drop_requested.disconnect()
    tree.folder_move_requested.disconnect()
    tree.gpx_files_dropped.disconnect()
    tree.track_drop_requested.connect(lambda *args: emitted.append("items"))
    tree.folder_move_requested.connect(lambda *args: emitted.append("folders"))
    tree.gpx_files_dropped.connect(lambda *args: emitted.append("external"))
    for folder_id, mime, allowed in (
        (root, items, False), (folder, items, False), (tray, items, True),
        (root, folders, True), (folder, folders, True), (tray, folders, False),
        (folder, external, False), (tray, external, True),
        (store.get_trash_folder_id(), items, False),
        (store.get_trash_folder_id(), folders, False),
    ):
        target = window._find_tree_item_by_folder_id(folder_id)
        monkeypatch.setattr(tree, "itemAt", lambda *args, target=target: target)
        move = DropEvent(mime)
        tree.dragMoveEvent(move)
        assert move.accepted == allowed
        drop = DropEvent(mime)
        before = len(emitted)
        tree.dropEvent(drop)
        assert drop.accepted == allowed
        assert len(emitted) == before + int(allowed)
    window.close()
    app.processEvents()


@pytest.mark.skipif(
    os.environ.get("GPX_WEBENGINE_TEST") != "1",
    reason="Run WebEngine integration in a separate Qt process",
)
def test_large_folder_document_loads_in_webengine(tmp_path: Path, monkeypatch) -> None:
    from gpx_organizer.library_store import LibraryStore
    from gpx_organizer.main_window import MainWindow, WEBENGINE_SETHTML_MAX_CHARS
    from gpx_organizer.map_service import _load_waypoint_icon_data_url
    from gpx_organizer.qt_compat import QApplication, QWebEngineView

    if QWebEngineView is None:
        pytest.skip("Qt WebEngine unavailable")
    monkeypatch.setenv("HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    window = MainWindow(store)
    waypoint_icon = _load_waypoint_icon_data_url()
    assert waypoint_icon is not None and waypoint_icon.startswith("data:image/svg+xml;base64,")
    html = (
        f'<html><body><div id="map"></div><img id="waypoint" src="{waypoint_icon}"><script>'
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
    pixels: list[bool] = []
    window.map_web_view.page().runJavaScript(
        "(() => { const image = document.getElementById('waypoint'); "
        "if (!image.complete || !image.naturalWidth) return false; "
        "const canvas = document.createElement('canvas'); canvas.width = 24; canvas.height = 24; "
        "const context = canvas.getContext('2d'); context.drawImage(image, 0, 0, 24, 24); "
        "return context.getImageData(12, 4, 1, 1).data[3] > 0; })()",
        lambda value: pixels.append(bool(value)),
    )
    deadline = monotonic() + 10
    while not pixels and monotonic() < deadline:
        app.processEvents()
        Event().wait(0.005)
    assert pixels == [True]
    window.close()

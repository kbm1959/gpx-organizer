"""Main window for the GPX Organizer app shell."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs
import webbrowser

from .qt_compat import (
    QT_BINDING,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QDrag,
    QEvent,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QMimeData,
    QPoint,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTimer,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWebEngineView,
    QWidget,
    Qt,
    Signal,
)

from .config import APP_NAME, get_app_paths
from .library_store import FolderRecord, LibraryStore
from .map_service import LeafletMapService, MapService
from .settings_store import (
    get_map_default_track_color,
    get_map_direction_arrow_color,
    get_map_direction_arrow_interval_km,
    get_map_direction_arrow_size_px,
    get_map_distance_marker_color,
    get_map_responsive_threshold_px,
    get_map_rest_stop_color,
    get_map_track_point_color,
    get_map_track_point_size_px,
    set_map_default_track_color,
    set_map_direction_arrow_color,
    set_map_direction_arrow_interval_km,
    set_map_direction_arrow_size_px,
    set_map_distance_marker_color,
    set_library_root,
    set_map_responsive_threshold_px,
    set_map_rest_stop_color,
    set_map_track_point_color,
    set_map_track_point_size_px,
)


TRACK_IDS_MIME = "application/x-gpx-track-ids"
FOLDER_ID_ROLE = Qt.ItemDataRole.UserRole
FOLDER_KIND_ROLE = Qt.ItemDataRole.UserRole + 1
TRACK_ID_ROLE = Qt.ItemDataRole.UserRole


class FolderTreeWidget(QTreeWidget):
    """Folder tree supporting both internal and external drag-and-drop."""

    folder_move_requested = Signal(int, int)
    track_drop_requested = Signal(list, int)
    gpx_files_dropped = Signal(list, int)

    def dragEnterEvent(self, event) -> None:  # pragma: no cover - GUI behavior
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # pragma: no cover - GUI behavior
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat(TRACK_IDS_MIME):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # pragma: no cover - GUI behavior
        if event.mimeData().hasUrls():
            target_item = self.itemAt(event.position().toPoint())
            if target_item is None:
                target_item = self.currentItem()
            if target_item is None:
                event.ignore()
                return

            target_folder_id = target_item.data(0, FOLDER_ID_ROLE)
            if target_folder_id is None:
                event.ignore()
                return

            file_paths: list[str] = []
            for url in event.mimeData().urls():
                if not url.isLocalFile():
                    continue
                file_paths.append(url.toLocalFile())

            if not file_paths:
                event.ignore()
                return

            self.gpx_files_dropped.emit(file_paths, int(target_folder_id))
            event.acceptProposedAction()
            return

        target_item = self.itemAt(event.position().toPoint())
        if event.mimeData().hasFormat(TRACK_IDS_MIME):
            if target_item is None:
                event.ignore()
                return

            target_folder_id = target_item.data(0, FOLDER_ID_ROLE)
            if target_folder_id is None:
                event.ignore()
                return

            raw_ids = bytes(event.mimeData().data(TRACK_IDS_MIME)).decode("utf-8")
            track_ids = [int(value) for value in raw_ids.split(",") if value.strip()]
            if not track_ids:
                event.ignore()
                return

            self.track_drop_requested.emit(track_ids, int(target_folder_id))
            event.acceptProposedAction()
            return

        moving_item = self.currentItem()
        moving_folder_id = None
        old_parent_id = None
        if moving_item is not None:
            folder_id = moving_item.data(0, FOLDER_ID_ROLE)
            if folder_id is not None:
                moving_folder_id = int(folder_id)

            parent_item = moving_item.parent()
            if parent_item is not None:
                parent_id = parent_item.data(0, FOLDER_ID_ROLE)
                if parent_id is not None:
                    old_parent_id = int(parent_id)

        super().dropEvent(event)

        if moving_folder_id is None:
            return

        moved_item = self.currentItem() or moving_item
        if moved_item is None:
            return

        new_parent_item = moved_item.parent()
        if new_parent_item is None:
            return

        new_parent_id = new_parent_item.data(0, FOLDER_ID_ROLE)
        if new_parent_id is None:
            return

        if old_parent_id == int(new_parent_id):
            return

        self.folder_move_requested.emit(moving_folder_id, int(new_parent_id))


class TrackListWidget(QListWidget):
    """Track list that drags selected track IDs as custom mime payload."""

    def startDrag(self, supported_actions) -> None:  # pragma: no cover - GUI behavior
        selected_ids: list[int] = []
        for item in self.selectedItems():
            track_id = item.data(TRACK_ID_ROLE)
            if track_id is not None:
                selected_ids.append(int(track_id))

        if not selected_ids:
            return

        mime_data = QMimeData()
        payload = ",".join(str(track_id) for track_id in selected_ids)
        mime_data.setData(TRACK_IDS_MIME, payload.encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.MoveAction)


class PreferencesDialog(QDialog):
    """Dedicated preferences dialog for user-configurable app settings."""

    def __init__(
        self,
        current_threshold_px: int,
        rest_stop_color: str,
        default_track_color: str,
        distance_marker_color: str,
        direction_arrow_color: str,
        direction_arrow_interval_km: float,
        direction_arrow_size_px: int,
        track_point_color: str,
        track_point_size_px: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(520, 290)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._map_threshold_spin = QSpinBox(self)
        self._map_threshold_spin.setRange(320, 2000)
        self._map_threshold_spin.setSingleStep(20)
        self._map_threshold_spin.setValue(current_threshold_px)
        self._map_threshold_spin.setSuffix(" px")
        form.addRow("Map responsive threshold:", self._map_threshold_spin)

        self._rest_stop_color_button = QPushButton(rest_stop_color, self)
        self._rest_stop_color_button.clicked.connect(
            lambda: self._pick_color(self._rest_stop_color_button)
        )
        self._apply_color_button_style(self._rest_stop_color_button)
        form.addRow("Rest stop color:", self._rest_stop_color_button)

        self._default_track_color_button = QPushButton(default_track_color, self)
        self._default_track_color_button.clicked.connect(
            lambda: self._pick_color(self._default_track_color_button)
        )
        self._apply_color_button_style(self._default_track_color_button)
        form.addRow("Default track color:", self._default_track_color_button)

        self._distance_marker_color_button = QPushButton(distance_marker_color, self)
        self._distance_marker_color_button.clicked.connect(
            lambda: self._pick_color(self._distance_marker_color_button)
        )
        self._apply_color_button_style(self._distance_marker_color_button)
        form.addRow("Distance marker color:", self._distance_marker_color_button)

        self._direction_arrow_color_button = QPushButton(direction_arrow_color, self)
        self._direction_arrow_color_button.clicked.connect(
            lambda: self._pick_color(self._direction_arrow_color_button)
        )
        self._apply_color_button_style(self._direction_arrow_color_button)
        form.addRow("Direction arrow color:", self._direction_arrow_color_button)

        self._direction_arrow_interval_spin = QDoubleSpinBox(self)
        self._direction_arrow_interval_spin.setRange(0.5, 10.0)
        self._direction_arrow_interval_spin.setSingleStep(0.1)
        self._direction_arrow_interval_spin.setDecimals(1)
        self._direction_arrow_interval_spin.setValue(direction_arrow_interval_km)
        self._direction_arrow_interval_spin.setSuffix(" km")
        form.addRow("Direction arrow spacing:", self._direction_arrow_interval_spin)

        self._direction_arrow_size_spin = QSpinBox(self)
        self._direction_arrow_size_spin.setRange(8, 40)
        self._direction_arrow_size_spin.setSingleStep(1)
        self._direction_arrow_size_spin.setValue(direction_arrow_size_px)
        self._direction_arrow_size_spin.setSuffix(" px")
        form.addRow("Direction arrow size:", self._direction_arrow_size_spin)

        self._track_point_color_button = QPushButton(track_point_color, self)
        self._track_point_color_button.clicked.connect(
            lambda: self._pick_color(self._track_point_color_button)
        )
        self._apply_color_button_style(self._track_point_color_button)
        form.addRow("Track point color:", self._track_point_color_button)

        self._track_point_size_spin = QSpinBox(self)
        self._track_point_size_spin.setRange(1, 10)
        self._track_point_size_spin.setSingleStep(1)
        self._track_point_size_spin.setValue(track_point_size_px)
        self._track_point_size_spin.setSuffix(" px")
        form.addRow("Track point size:", self._track_point_size_spin)

        self._live_preview_label = QLabel(self)
        self._live_preview_label.setWordWrap(True)
        self._live_preview_label.setTextFormat(Qt.TextFormat.RichText)
        self._refresh_live_preview_swatch()
        form.addRow("Live preview:", self._live_preview_label)

        hint = QLabel(
            "Configure how map overlays are displayed. More options will be added here.",
            self,
        )
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def selected_map_threshold_px(self) -> int:
        return int(self._map_threshold_spin.value())

    def selected_rest_stop_color(self) -> str:
        return self._rest_stop_color_button.text()

    def selected_default_track_color(self) -> str:
        return self._default_track_color_button.text()

    def selected_distance_marker_color(self) -> str:
        return self._distance_marker_color_button.text()

    def selected_direction_arrow_color(self) -> str:
        return self._direction_arrow_color_button.text()

    def selected_direction_arrow_interval_km(self) -> float:
        return float(self._direction_arrow_interval_spin.value())

    def selected_direction_arrow_size_px(self) -> int:
        return int(self._direction_arrow_size_spin.value())

    def selected_track_point_color(self) -> str:
        return self._track_point_color_button.text()

    def selected_track_point_size_px(self) -> int:
        return int(self._track_point_size_spin.value())

    def _pick_color(self, button: QPushButton) -> None:
        color = QColorDialog.getColor(parent=self)
        if not color.isValid():
            return

        button.setText(color.name().upper())
        self._apply_color_button_style(button)
        self._refresh_live_preview_swatch()

    def _apply_color_button_style(self, button: QPushButton) -> None:
        value = button.text().strip()
        button.setStyleSheet(
            f"QPushButton {{ background: {value}; border: 1px solid #8a8a8a; padding: 4px 8px; }}"
        )

    def _refresh_live_preview_swatch(self) -> None:
        rest = self._rest_stop_color_button.text().strip()
        track = self._default_track_color_button.text().strip()
        marker = self._distance_marker_color_button.text().strip()
        arrow = self._direction_arrow_color_button.text().strip()
        point = self._track_point_color_button.text().strip()
        self._live_preview_label.setText(
            ""
            f"<span style='font-weight:600;'>Track</span> "
            f"<span style='display:inline-block; min-width:48px; text-align:center; color:{track};'>━━</span> &nbsp;"
            f"<span style='font-weight:600;'>Rest</span> "
            f"<span style='display:inline-block; min-width:20px; text-align:center; color:{rest};'>●</span> &nbsp;"
            f"<span style='font-weight:600;'>Marker</span> "
            f"<span style='display:inline-block; min-width:20px; text-align:center; color:{marker};'>◉</span> &nbsp;"
            f"<span style='font-weight:600;'>Arrow</span> "
            f"<span style='display:inline-block; min-width:20px; text-align:center; color:{arrow}; font-weight:900;'>&gt;</span> &nbsp;"
            f"<span style='font-weight:600;'>Point</span> "
            f"<span style='display:inline-block; min-width:20px; text-align:center; color:{point};'>•</span>"
        )


class MainWindow(QMainWindow):
    """Primary application window with organizer-first panel layout."""

    def __init__(
        self,
        library_store: LibraryStore,
        map_service: MapService | None = None,
    ) -> None:
        super().__init__()
        self.library_store = library_store
        self.map_service = map_service or LeafletMapService()
        self.library_tree: FolderTreeWidget | None = None
        self.track_list: TrackListWidget | None = None
        self.map_web_view: QWebEngineView | None = None
        self.map_fallback_label: QLabel | None = None
        self._map_panel_container: QWidget | None = None
        self._map_toolbar: QWidget | None = None
        self._current_map_html: str = ""
        self._pending_trim_start_percent: float | None = None
        self._map_hide_timer = QTimer(self)
        self._map_hide_timer.setSingleShot(True)
        self._map_hide_timer.timeout.connect(self._hide_map_toolbar)
        self._import_action = None
        self.setWindowTitle(f"{APP_NAME} - Milestone 3 Organizer")
        self.resize(1400, 840)
        self.setAcceptDrops(True)
        self._init_menu()
        self._init_body()
        self._init_status_bar()
        self._load_library_tree()

    def _init_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        new_library_action = file_menu.addAction("New Library")
        new_library_action.triggered.connect(self._new_library_dialog)
        open_library_action = file_menu.addAction("Open Library")
        open_library_action.triggered.connect(self._open_library_dialog)
        file_menu.addSeparator()
        self._import_action = file_menu.addAction("Import GPX")
        self._import_action.triggered.connect(self._import_gpx_into_selected_folder)
        file_menu.addAction("Export GPX")
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

        edit_menu = menu_bar.addMenu("Edit")
        rename_action = edit_menu.addAction("Rename")
        rename_action.triggered.connect(self._rename_selected_item)
        delete_action = edit_menu.addAction("Delete")
        delete_action.triggered.connect(self._delete_selected_item)
        edit_menu.addSeparator()
        edit_menu.addAction("Undo")
        edit_menu.addAction("Redo")

        track_menu = menu_bar.addMenu("Track")
        trim_action = track_menu.addAction("Trim")
        trim_action.triggered.connect(self._trim_selected_track)
        split_action = track_menu.addAction("Split")
        split_action.triggered.connect(self._split_selected_track)
        track_menu.addAction("Merge")
        reverse_action = track_menu.addAction("Reverse")
        reverse_action.triggered.connect(self._reverse_selected_tracks)

        view_menu = menu_bar.addMenu("View")
        view_menu.addAction("Toggle Panels")
        refresh_map_action = view_menu.addAction("Refresh Map")
        refresh_map_action.triggered.connect(self._refresh_map_view)
        fit_map_action = view_menu.addAction("Fit Track")
        fit_map_action.triggered.connect(self._fit_track_in_view)
        preferences_action = view_menu.addAction("Preferences...")
        preferences_action.triggered.connect(self._open_preferences_dialog)

        help_menu = menu_bar.addMenu("Help")
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._show_about)

    def _init_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        tree_panel = self._build_tree_panel()
        list_panel = self._build_track_list_panel()
        map_panel = self._build_map_panel()

        splitter.addWidget(tree_panel)
        splitter.addWidget(list_panel)
        splitter.addWidget(map_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 3)

        self.setCentralWidget(splitter)

    def _build_tree_panel(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Library Tree", container)
        title.setObjectName("panelTitle")

        tree = FolderTreeWidget(container)
        tree.setHeaderLabel("Folders")
        tree.setDragEnabled(True)
        tree.setAcceptDrops(True)
        tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        tree.itemSelectionChanged.connect(self._reload_track_list)
        tree.folder_move_requested.connect(self._move_folder_persisted)
        tree.track_drop_requested.connect(self._move_tracks_to_folder)
        tree.gpx_files_dropped.connect(self._import_dropped_paths)
        self.library_tree = tree

        layout.addWidget(title)
        layout.addWidget(tree)
        return container

    def _build_track_list_panel(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Tracks", container)
        title.setObjectName("panelTitle")

        track_list = TrackListWidget(container)
        track_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        track_list.setDragEnabled(True)
        track_list.setAcceptDrops(False)
        track_list.setAlternatingRowColors(True)
        track_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        track_list.customContextMenuRequested.connect(self._show_track_context_menu)
        track_list.itemSelectionChanged.connect(self._preview_selected_track)
        track_list.itemDoubleClicked.connect(self._open_track_preview)
        self.track_list = track_list

        layout.addWidget(title)
        layout.addWidget(track_list)
        return container

    def _build_map_panel(self) -> QWidget:
        container = QWidget(self)
        self._map_panel_container = container
        container.setMouseTracking(True)
        container.installEventFilter(self)

        layout = QGridLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        if QWebEngineView is not None:
            web_view = QWebEngineView(container)
            web_view.installEventFilter(self)
            web_view.urlChanged.connect(self._handle_map_web_url_changed)
            self.map_web_view = web_view
            self._set_map_placeholder(
                title="Map Placeholder",
                message="Double-click a track to preview it on the map.",
            )
            layout.addWidget(web_view, 0, 0)
        else:
            fallback = QLabel(
                "Embedded map is unavailable in this environment. "
                "Track previews will open in your default web browser.",
                container,
            )
            fallback.setWordWrap(True)
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.installEventFilter(self)
            self.map_fallback_label = fallback
            layout.addWidget(fallback, 0, 0)

        toolbar = self._build_map_toolbar(container)
        self._map_toolbar = toolbar
        toolbar.installEventFilter(self)
        toolbar.setVisible(False)
        layout.addWidget(
            toolbar,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )

        return container

    def _build_map_toolbar(self, parent: QWidget) -> QWidget:
        toolbar = QWidget(parent)
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(4)

        refresh_button = QPushButton("↻", toolbar)
        refresh_button.setToolTip("Refresh map")
        refresh_button.clicked.connect(self._refresh_map_view)

        fit_button = QPushButton("⤢", toolbar)
        fit_button.setToolTip("Fit track to view")
        fit_button.clicked.connect(self._fit_track_in_view)

        open_browser_button = QPushButton("⌁", toolbar)
        open_browser_button.setToolTip("Open current map in browser")
        open_browser_button.clicked.connect(self._open_current_map_in_browser)

        for button in (refresh_button, fit_button, open_browser_button):
            button.setFixedSize(30, 26)
            toolbar_layout.addWidget(button)

        toolbar.setStyleSheet(
            "QWidget { background: rgba(255, 255, 255, 215); border: 1px solid #c8c8c8; border-radius: 8px; }"
            "QPushButton { font-size: 14px; font-weight: 600; border: none; border-radius: 5px; margin: 1px; }"
            "QPushButton:hover { background: rgba(0, 127, 95, 35); }"
        )
        return toolbar

    def eventFilter(self, watched, event) -> bool:  # pragma: no cover - GUI behavior
        if watched in {
            self._map_panel_container,
            self._map_toolbar,
            self.map_web_view,
            self.map_fallback_label,
        }:
            event_type = event.type()
            if event_type in {QEvent.Type.Enter, QEvent.Type.MouseMove}:
                self._show_map_toolbar()
            elif event_type == QEvent.Type.Leave:
                self._map_hide_timer.start(1000)

        return super().eventFilter(watched, event)

    def _show_map_toolbar(self) -> None:
        if self._map_toolbar is None:
            return
        self._map_hide_timer.stop()
        self._map_toolbar.setVisible(True)

    def _hide_map_toolbar(self) -> None:
        if self._map_toolbar is None:
            return
        self._map_toolbar.setVisible(False)

    def _init_status_bar(self) -> None:
        status_bar = QStatusBar(self)
        embedded = "enabled" if QWebEngineView is not None else "fallback-browser"
        status_bar.showMessage(
            f"Ready - Qt: {QT_BINDING} - Map mode: {embedded}"
        )
        self.setStatusBar(status_bar)

    def _load_library_tree(self, selected_folder_id: int | None = None) -> None:
        if self.library_tree is None:
            return

        folders = self.library_store.list_folders()
        self.library_tree.clear()

        item_by_folder_id: dict[int, QTreeWidgetItem] = {}
        for folder in folders:
            item = QTreeWidgetItem([folder.name])
            item.setData(0, FOLDER_ID_ROLE, folder.id)
            item.setData(0, FOLDER_KIND_ROLE, folder.kind)

            flags = item.flags() | Qt.ItemFlag.ItemIsDropEnabled
            if folder.kind in {"root", "trash"}:
                flags = flags & ~Qt.ItemFlag.ItemIsDragEnabled
            else:
                flags = flags | Qt.ItemFlag.ItemIsDragEnabled
            item.setFlags(flags)
            item_by_folder_id[folder.id] = item

        for folder in folders:
            item = item_by_folder_id[folder.id]
            if folder.parent_id is None:
                self.library_tree.addTopLevelItem(item)
            else:
                parent = item_by_folder_id.get(folder.parent_id)
                if parent is not None:
                    parent.addChild(item)
                else:
                    self.library_tree.addTopLevelItem(item)

            if folder.kind == "root":
                item.setExpanded(True)

        target_id = selected_folder_id
        if target_id is None:
            root = self._find_root_folder(folders)
            if root is not None:
                target_id = root.id

        if target_id is not None:
            target_item = item_by_folder_id.get(target_id)
            if target_item is not None:
                self.library_tree.setCurrentItem(target_item)
                parent = target_item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()

    def _find_root_folder(self, folders: list[FolderRecord]) -> FolderRecord | None:
        for folder in folders:
            if folder.kind == "root":
                return folder
        return None

    def _selected_folder_id(self) -> int:
        if self.library_tree is None or self.library_tree.currentItem() is None:
            return self.library_store.get_root_folder_id()

        folder_id = self.library_tree.currentItem().data(0, FOLDER_ID_ROLE)
        if folder_id is None:
            return self.library_store.get_root_folder_id()
        return int(folder_id)

    def _selected_folder_kind(self) -> str | None:
        if self.library_tree is None or self.library_tree.currentItem() is None:
            return None

        kind = self.library_tree.currentItem().data(0, FOLDER_KIND_ROLE)
        if kind is None:
            return None
        return str(kind)

    def _reload_track_list(self, selected_track_id: int | None = None) -> None:
        if self.track_list is None:
            return

        folder_id = self._selected_folder_id()
        tracks = self.library_store.list_tracks(folder_id)

        self.track_list.clear()
        if not tracks:
            placeholder = QListWidgetItem("No tracks in this folder")
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.track_list.addItem(placeholder)
            return

        for track in tracks:
            item = QListWidgetItem(track.display_name)
            item.setData(TRACK_ID_ROLE, track.id)
            self.track_list.addItem(item)
            if selected_track_id is not None and track.id == selected_track_id:
                self.track_list.setCurrentItem(item)

    def _import_file_paths(self, file_paths: list[Path], folder_id: int) -> tuple[int, int, list[str]]:
        imported_count = 0
        duplicate_count = 0
        failures: list[str] = []

        for path in file_paths:
            if path.suffix.lower() != ".gpx":
                failures.append(f"{path}: not a .gpx file")
                continue

            try:
                result = self.library_store.import_gpx(path, folder_id)
                imported_count += 1
                if result.is_duplicate:
                    duplicate_count += 1
            except Exception as exc:  # pragma: no cover - GUI pathway
                failures.append(f"{path}: {exc}")

        return imported_count, duplicate_count, failures

    def _import_gpx_into_selected_folder(self) -> None:
        selected_files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import GPX Files",
            str(Path.home()),
            "GPX Files (*.gpx)",
        )
        if not selected_files:
            return

        folder_id = self._selected_folder_id()
        file_paths = [Path(value) for value in selected_files]
        imported_count, duplicate_count, failures = self._import_file_paths(file_paths, folder_id)

        self._reload_track_list()

        self.statusBar().showMessage(
            f"Imported {imported_count} file(s); duplicates: {duplicate_count}",
            7000,
        )

        if failures:
            QMessageBox.warning(
                self,
                "Import completed with errors",
                "\n".join(failures[:10]),
            )

    def _import_dropped_paths(self, path_values: list[str], folder_id: int) -> None:
        file_paths = [Path(value) for value in path_values]
        imported_count, duplicate_count, failures = self._import_file_paths(file_paths, folder_id)
        self._reload_track_list()
        self.statusBar().showMessage(
            f"Imported {imported_count} dropped GPX file(s); duplicates: {duplicate_count}",
            7000,
        )
        if failures:
            QMessageBox.warning(self, "Dropped import errors", "\n".join(failures[:10]))

    def _new_library_dialog(self) -> None:
        base_dir = QFileDialog.getExistingDirectory(
            self,
            "Choose Parent Folder for New Library",
            str(Path.home()),
        )
        if not base_dir:
            return

        suggested_name = "gpx-library"
        folder_name, ok = QInputDialog.getText(
            self,
            "New Library",
            "Library folder name:",
            text=suggested_name,
        )
        if not ok:
            return

        if not folder_name.strip():
            QMessageBox.warning(self, "New library", "Library folder name cannot be empty.")
            return

        library_root = Path(base_dir) / folder_name.strip()
        if library_root.exists() and any(library_root.iterdir()):
            reply = QMessageBox.question(
                self,
                "Folder not empty",
                "Selected library folder is not empty. Use it anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._switch_library(library_root)

    def _open_library_dialog(self) -> None:
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Open Existing Library Folder",
            str(Path.home()),
        )
        if not selected_dir:
            return

        library_root = Path(selected_dir)
        db_path = library_root / "library.db"
        if not db_path.exists():
            QMessageBox.warning(
                self,
                "Invalid library",
                "Selected folder does not contain library.db.",
            )
            return

        self._switch_library(library_root)

    def _switch_library(self, library_root: Path) -> None:
        try:
            new_store = LibraryStore(library_root=library_root.expanduser().resolve())
            new_store.initialize()
            self.library_store = new_store
            set_library_root(new_store.library_root)
            self._load_library_tree()
            self.statusBar().showMessage(
                f"Opened library: {new_store.library_root}",
                6000,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Open library failed", str(exc))

    def _show_tree_context_menu(self, pos) -> None:
        if self.library_tree is None:
            return

        target_item = self.library_tree.itemAt(pos)
        if target_item is not None:
            self.library_tree.setCurrentItem(target_item)

        menu = QMenu(self)
        new_folder_action = menu.addAction("New Folder")
        new_folder_action.triggered.connect(self._create_folder_dialog)

        rename_folder_action = menu.addAction("Rename")
        rename_folder_action.triggered.connect(self._rename_selected_folder_dialog)

        delete_folder_action = menu.addAction("Delete")
        delete_folder_action.triggered.connect(self._delete_selected_folder)

        menu.addSeparator()
        import_action = menu.addAction("Import GPX Here")
        import_action.triggered.connect(self._import_gpx_into_selected_folder)

        kind = self._selected_folder_kind()
        if kind in {"root", "trash", None}:
            rename_folder_action.setEnabled(False)
            delete_folder_action.setEnabled(False)

        menu.exec(self.library_tree.viewport().mapToGlobal(pos))

    def _show_track_context_menu(self, pos: QPoint) -> None:
        if self.track_list is None:
            return

        target_item = self.track_list.itemAt(pos)
        if target_item is not None:
            target_item.setSelected(True)

        menu = QMenu(self)
        show_action = menu.addAction("Show on Map")
        show_action.triggered.connect(self._preview_selected_track)

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(self._rename_selected_track_dialog)

        reverse_action = menu.addAction("Reverse")
        reverse_action.triggered.connect(self._reverse_selected_tracks)

        trim_action = menu.addAction("Trim")
        trim_action.triggered.connect(self._trim_selected_track)

        split_action = menu.addAction("Split")
        split_action.triggered.connect(self._split_selected_track)

        set_color_action = menu.addAction("Set color")
        set_color_action.triggered.connect(self._set_selected_track_color)

        delete_label = "Delete Permanently" if self._selected_folder_kind() == "trash" else "Move to Trash"
        delete_action = menu.addAction(delete_label)
        delete_action.triggered.connect(self._delete_selected_tracks)

        if not self._selected_track_ids():
            show_action.setEnabled(False)
            rename_action.setEnabled(False)
            reverse_action.setEnabled(False)
            trim_action.setEnabled(False)
            split_action.setEnabled(False)
            set_color_action.setEnabled(False)
            delete_action.setEnabled(False)

        menu.exec(self.track_list.viewport().mapToGlobal(pos))

    def _open_track_preview(self, item: QListWidgetItem) -> None:
        track_id = item.data(TRACK_ID_ROLE)
        if track_id is None:
            return

        track_name = item.text()
        try:
            managed_path = self.library_store.get_track_managed_path(int(track_id))
            rendered = self.map_service.render_track(managed_path, track_name)
            self._set_map_html(rendered.html)
            self.statusBar().showMessage(f"Loaded map preview for {track_name}", 5000)
        except Exception as exc:
            self._set_map_placeholder(
                title="Map preview failed",
                message=str(exc),
            )
            QMessageBox.warning(self, "Map preview failed", str(exc))

    def _preview_selected_track(self) -> None:
        if self.track_list is None:
            return

        item = self.track_list.currentItem()
        if item is None:
            return

        if item.data(TRACK_ID_ROLE) is None:
            return

        self._open_track_preview(item)

    def _set_map_html(self, html_content: str) -> None:
        self._current_map_html = html_content

        if self.map_web_view is not None:
            self.map_web_view.setHtml(html_content)
            return

        # Fallback path: render map HTML in the system browser when WebEngine
        # cannot be loaded due missing system runtime dependencies.
        preview_file = self._write_current_map_preview()
        webbrowser.open(preview_file.as_uri())

        if self.map_fallback_label is not None:
            self.map_fallback_label.setText(
                "Embedded map unavailable. Opened preview in your default web browser."
            )

    def _set_map_placeholder(self, title: str, message: str) -> None:
        rendered = LeafletMapService().render_placeholder(title=title, message=message)
        self._set_map_html(rendered.html)

        if self.map_fallback_label is not None and self.map_web_view is None:
            self.map_fallback_label.setText(f"{title}\n\n{message}")

    def _write_current_map_preview(self) -> Path:
        preview_dir = get_app_paths().base_dir / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_file = preview_dir / "current_map_preview.html"
        preview_file.write_text(self._current_map_html, encoding="utf-8")
        return preview_file

    def _refresh_map_view(self) -> None:
        if not self._current_map_html:
            self.statusBar().showMessage("No map loaded yet", 3000)
            return

        if self.map_web_view is not None:
            self.map_web_view.setHtml(self._current_map_html)
            self.statusBar().showMessage("Map refreshed", 3000)
            return

        preview_file = self._write_current_map_preview()
        webbrowser.open(preview_file.as_uri())
        self.statusBar().showMessage("Map preview opened in browser", 4000)

    def _fit_track_in_view(self) -> None:
        if self.map_web_view is None:
            self.statusBar().showMessage("Fit Track requires embedded map mode", 4000)
            return

        page = self.map_web_view.page()
        if page is None:
            return

        page.runJavaScript(
            "if (window.__gpxFitTrack) { window.__gpxFitTrack(); true; } else { false; }",
        )
        self.statusBar().showMessage("Fit Track requested", 3000)

    def _open_current_map_in_browser(self) -> None:
        if not self._current_map_html:
            self.statusBar().showMessage("No map loaded yet", 3000)
            return

        preview_file = self._write_current_map_preview()
        webbrowser.open(preview_file.as_uri())
        self.statusBar().showMessage("Opened current map in browser", 4000)

    def _open_preferences_dialog(self) -> None:
        dialog = PreferencesDialog(
            current_threshold_px=get_map_responsive_threshold_px(),
            rest_stop_color=get_map_rest_stop_color(),
            default_track_color=get_map_default_track_color(),
            distance_marker_color=get_map_distance_marker_color(),
            direction_arrow_color=get_map_direction_arrow_color(),
            direction_arrow_interval_km=get_map_direction_arrow_interval_km(),
            direction_arrow_size_px=get_map_direction_arrow_size_px(),
            track_point_color=get_map_track_point_color(),
            track_point_size_px=get_map_track_point_size_px(),
            parent=self,
        )
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return

        saved_threshold = set_map_responsive_threshold_px(dialog.selected_map_threshold_px())
        saved_rest_stop_color = set_map_rest_stop_color(dialog.selected_rest_stop_color())
        saved_default_track_color = set_map_default_track_color(dialog.selected_default_track_color())
        saved_distance_marker_color = set_map_distance_marker_color(
            dialog.selected_distance_marker_color()
        )
        saved_direction_arrow_color = set_map_direction_arrow_color(
            dialog.selected_direction_arrow_color()
        )
        saved_direction_arrow_interval_km = set_map_direction_arrow_interval_km(
            dialog.selected_direction_arrow_interval_km()
        )
        saved_direction_arrow_size_px = set_map_direction_arrow_size_px(
            dialog.selected_direction_arrow_size_px()
        )
        saved_track_point_color = set_map_track_point_color(dialog.selected_track_point_color())
        saved_track_point_size_px = set_map_track_point_size_px(dialog.selected_track_point_size_px())

        if isinstance(self.map_service, LeafletMapService):
            self.map_service.responsive_threshold_px = saved_threshold
            self.map_service.rest_stop_color = saved_rest_stop_color
            self.map_service.default_track_color = saved_default_track_color
            self.map_service.distance_marker_color = saved_distance_marker_color
            self.map_service.direction_arrow_color = saved_direction_arrow_color
            self.map_service.direction_arrow_interval_km = saved_direction_arrow_interval_km
            self.map_service.direction_arrow_size_px = saved_direction_arrow_size_px
            self.map_service.track_point_color = saved_track_point_color
            self.map_service.track_point_size_px = saved_track_point_size_px

        if self._rerender_current_track_preview():
            self.statusBar().showMessage(
                f"Preferences saved (map threshold {saved_threshold}px), preview updated",
                5000,
            )
            return

        self.statusBar().showMessage(
            f"Preferences saved (map threshold {saved_threshold}px)",
            5000,
        )

    def _set_selected_track_color(self) -> None:
        track_ids = self._selected_track_ids()
        if len(track_ids) != 1:
            QMessageBox.information(self, "Set track color", "Please select exactly one track.")
            return

        track_id = track_ids[0]
        color = QColorDialog.getColor(parent=self)
        if not color.isValid():
            return

        selected_color = color.name().upper()

        try:
            self.library_store.set_track_color(track_id, selected_color)
            self._reload_track_list(selected_track_id=track_id)
            self._rerender_current_track_preview()
            self.statusBar().showMessage(
                f"Track color set to {selected_color}",
                5000,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Set track color failed", str(exc))

    def _current_selected_track_id(self) -> int | None:
        if self.track_list is None:
            return None
        item = self.track_list.currentItem()
        if item is None:
            return None
        value = item.data(TRACK_ID_ROLE)
        if value is None:
            return None
        return int(value)

    def _handle_map_web_url_changed(self, url) -> None:
        fragment = url.fragment()
        if not fragment:
            return
        if not fragment.startswith("gpxcmd=1"):
            return

        params = parse_qs(fragment)
        action = params.get("action", [None])[0]
        percent_raw = params.get("percent", [None])[0]

        try:
            percent = float(percent_raw) if percent_raw is not None else None
        except ValueError:
            percent = None

        if action is None or percent is None:
            return

        self._run_map_point_action(action, percent)
        if self.map_web_view is not None:
            self.map_web_view.page().runJavaScript(
                "if (window.location.hash.startsWith('#gpxcmd=1')) { window.location.hash = ''; }",
            )

    def _run_map_point_action(self, action: str, percent: float) -> None:
        track_id = self._current_selected_track_id()
        if track_id is None:
            self.statusBar().showMessage("Select a track first", 4000)
            return

        bounded = max(0.0, min(100.0, percent))

        if action == "split":
            if bounded <= 0.0 or bounded >= 100.0:
                self.statusBar().showMessage("Split point must be inside track range", 4000)
                return
            try:
                part_a, part_b = self.library_store.split_track(track_id, split_percent=bounded)
                self._reload_track_list(selected_track_id=part_a.id)
                self.statusBar().showMessage(
                    f"Split from map: {part_a.display_name} and {part_b.display_name}",
                    6000,
                )
            except Exception as exc:
                QMessageBox.warning(self, "Split track failed", str(exc))
            return

        if action == "trim_start":
            self._pending_trim_start_percent = bounded
            self.statusBar().showMessage(f"Trim start set to {bounded:.1f}%", 4000)
            return

        if action == "trim_end":
            if self._pending_trim_start_percent is None:
                self.statusBar().showMessage("Set Trim Start first", 4000)
                return
            start_value = self._pending_trim_start_percent
            end_value = bounded
            if end_value <= start_value:
                self.statusBar().showMessage("Trim end must be after trim start", 4000)
                return

            try:
                trimmed = self.library_store.trim_track(
                    track_id,
                    start_percent=start_value,
                    end_percent=end_value,
                )
                self._pending_trim_start_percent = None
                self._reload_track_list(selected_track_id=trimmed.id)
                self.statusBar().showMessage(
                    f"Trimmed from map: {trimmed.display_name}",
                    6000,
                )
            except Exception as exc:
                QMessageBox.warning(self, "Trim track failed", str(exc))

    def _rerender_current_track_preview(self) -> bool:
        if self.track_list is None:
            return False

        item = self.track_list.currentItem()
        if item is None:
            return False

        if item.data(TRACK_ID_ROLE) is None:
            return False

        self._open_track_preview(item)
        return True

    def _reverse_selected_tracks(self) -> None:
        track_ids = self._selected_track_ids()
        if len(track_ids) != 1:
            QMessageBox.information(self, "Reverse track", "Please select exactly one track.")
            return

        track_id = track_ids[0]
        reply = QMessageBox.question(
            self,
            "Reverse track",
            "Reverse all track points in the selected GPX file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.library_store.reverse_track(track_id)
            self._reload_track_list(selected_track_id=track_id)
            self.statusBar().showMessage("Track reversed", 5000)
        except Exception as exc:
            QMessageBox.warning(self, "Reverse track failed", str(exc))

    def _trim_selected_track(self) -> None:
        track_ids = self._selected_track_ids()
        if len(track_ids) != 1:
            QMessageBox.information(self, "Trim track", "Please select exactly one track.")
            return

        start_percent, ok = QInputDialog.getDouble(
            self,
            "Trim track",
            "Start percent (0-100):",
            value=0.0,
            min=0.0,
            max=99.0,
            decimals=1,
        )
        if not ok:
            return

        end_percent, ok = QInputDialog.getDouble(
            self,
            "Trim track",
            "End percent (0-100):",
            value=100.0,
            min=1.0,
            max=100.0,
            decimals=1,
        )
        if not ok:
            return

        if end_percent <= start_percent:
            QMessageBox.warning(
                self,
                "Trim track",
                "End percent must be greater than start percent.",
            )
            return

        try:
            trimmed = self.library_store.trim_track(
                track_ids[0],
                start_percent=start_percent,
                end_percent=end_percent,
            )
            self._reload_track_list(selected_track_id=trimmed.id)
            self.statusBar().showMessage(
                f"Created trimmed track: {trimmed.display_name}",
                6000,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Trim track failed", str(exc))

    def _split_selected_track(self) -> None:
        track_ids = self._selected_track_ids()
        if len(track_ids) != 1:
            QMessageBox.information(self, "Split track", "Please select exactly one track.")
            return

        split_percent, ok = QInputDialog.getDouble(
            self,
            "Split track",
            "Split position (percent, 0-100):",
            value=50.0,
            min=1.0,
            max=99.0,
            decimals=1,
        )
        if not ok:
            return

        try:
            part_a, part_b = self.library_store.split_track(
                track_ids[0],
                split_percent=split_percent,
            )
            self._reload_track_list(selected_track_id=part_a.id)
            self.statusBar().showMessage(
                f"Created split tracks: {part_a.display_name} and {part_b.display_name}",
                6000,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Split track failed", str(exc))

    def _create_folder_dialog(self) -> None:
        parent_id = self._selected_folder_id()
        text, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok:
            return

        try:
            self.library_store.create_folder(text, parent_id=parent_id)
            self._load_library_tree(selected_folder_id=parent_id)
            self.statusBar().showMessage("Folder created", 4000)
        except Exception as exc:
            QMessageBox.warning(self, "Create folder failed", str(exc))

    def _rename_selected_folder_dialog(self) -> None:
        folder_id = self._selected_folder_id()
        folder_kind = self._selected_folder_kind()
        if folder_kind in {"root", "trash", None}:
            return

        folder = self.library_store.get_folder(folder_id)
        text, ok = QInputDialog.getText(
            self,
            "Rename Folder",
            "Folder name:",
            text=folder.name,
        )
        if not ok:
            return

        try:
            self.library_store.rename_folder(folder_id, text)
            self._load_library_tree(selected_folder_id=folder_id)
            self.statusBar().showMessage("Folder renamed", 4000)
        except Exception as exc:
            QMessageBox.warning(self, "Rename folder failed", str(exc))

    def _delete_selected_folder(self) -> None:
        folder_id = self._selected_folder_id()
        folder_kind = self._selected_folder_kind()
        if folder_kind in {"root", "trash", None}:
            return

        reply = QMessageBox.question(
            self,
            "Delete folder",
            "Delete this folder subtree? Tracks inside will be moved to Trash.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            root_id = self.library_store.get_root_folder_id()
            self.library_store.delete_folder(folder_id)
            self._load_library_tree(selected_folder_id=root_id)
            self.statusBar().showMessage("Folder deleted; tracks moved to Trash", 5000)
        except Exception as exc:
            QMessageBox.warning(self, "Delete folder failed", str(exc))

    def _selected_track_ids(self) -> list[int]:
        if self.track_list is None:
            return []

        track_ids: list[int] = []
        for item in self.track_list.selectedItems():
            value = item.data(TRACK_ID_ROLE)
            if value is not None:
                track_ids.append(int(value))
        return track_ids

    def _rename_selected_track_dialog(self) -> None:
        track_ids = self._selected_track_ids()
        if len(track_ids) != 1:
            QMessageBox.information(self, "Rename track", "Please select exactly one track.")
            return

        if self.track_list is None or self.track_list.currentItem() is None:
            return

        current_name = self.track_list.currentItem().text()
        text, ok = QInputDialog.getText(
            self,
            "Rename Track",
            "Track name:",
            text=current_name,
        )
        if not ok:
            return

        try:
            self.library_store.rename_track(track_ids[0], text)
            self._reload_track_list()
            self.statusBar().showMessage("Track renamed", 4000)
        except Exception as exc:
            QMessageBox.warning(self, "Rename track failed", str(exc))

    def _delete_selected_tracks(self) -> None:
        track_ids = self._selected_track_ids()
        if not track_ids:
            return

        in_trash = self._selected_folder_kind() == "trash"
        if in_trash:
            prompt = "Permanently delete selected tracks from Trash?"
        else:
            prompt = "Move selected tracks to Trash?"

        reply = QMessageBox.question(
            self,
            "Delete tracks",
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        failures: list[str] = []
        for track_id in track_ids:
            try:
                if in_trash:
                    self.library_store.purge_track(track_id)
                else:
                    self.library_store.move_track_to_trash(track_id)
            except Exception as exc:
                failures.append(str(exc))

        self._reload_track_list()
        if failures:
            QMessageBox.warning(self, "Delete tracks", "\n".join(failures[:8]))
        elif in_trash:
            self.statusBar().showMessage("Tracks permanently deleted", 5000)
        else:
            self.statusBar().showMessage("Tracks moved to Trash", 5000)

    def _rename_selected_item(self) -> None:
        if self.track_list is not None and self.track_list.hasFocus() and self._selected_track_ids():
            self._rename_selected_track_dialog()
            return
        self._rename_selected_folder_dialog()

    def _delete_selected_item(self) -> None:
        if self.track_list is not None and self.track_list.hasFocus() and self._selected_track_ids():
            self._delete_selected_tracks()
            return
        self._delete_selected_folder()

    def _move_folder_persisted(self, folder_id: int, new_parent_id: int) -> None:
        try:
            self.library_store.move_folder(folder_id, new_parent_id)
            self._load_library_tree(selected_folder_id=folder_id)
            self.statusBar().showMessage("Folder moved", 4000)
        except Exception as exc:
            self._load_library_tree(selected_folder_id=folder_id)
            QMessageBox.warning(self, "Move folder failed", str(exc))

    def _move_tracks_to_folder(self, track_ids: list[int], folder_id: int) -> None:
        failures: list[str] = []
        for track_id in track_ids:
            try:
                self.library_store.move_track_to_folder(track_id, folder_id)
            except Exception as exc:
                failures.append(str(exc))

        self._load_library_tree(selected_folder_id=folder_id)
        self._reload_track_list()

        moved_count = len(track_ids) - len(failures)
        self.statusBar().showMessage(f"Moved {moved_count} track(s)", 4000)
        if failures:
            QMessageBox.warning(self, "Move tracks failed", "\n".join(failures[:8]))

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About GPX Organizer",
            "GPX Organizer\nMilestone 3 organizer workflows\nPySide6 desktop application scaffold.",
        )

    def dragEnterEvent(self, event) -> None:  # pragma: no cover - GUI behavior
        mime = event.mimeData()
        if mime.hasUrls() and any(url.isLocalFile() for url in mime.urls()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # pragma: no cover - GUI behavior
        mime = event.mimeData()
        if mime.hasUrls() and any(url.isLocalFile() for url in mime.urls()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # pragma: no cover - GUI behavior
        mime = event.mimeData()
        if not mime.hasUrls():
            super().dropEvent(event)
            return

        paths: list[Path] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() == ".gpx":
                paths.append(path)

        if not paths:
            super().dropEvent(event)
            return

        self._import_dropped_paths([str(path) for path in paths], self._selected_folder_id())

        event.acceptProposedAction()

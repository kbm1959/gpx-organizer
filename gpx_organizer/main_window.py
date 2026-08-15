"""Main window for the GPX Organizer app shell."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs
import webbrowser

from .qt_compat import (
    QT_BINDING,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QDrag,
    QEvent,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
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
    QTabWidget,
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
from .library_store import FolderRecord, LibraryStore, TrackRecord
from .map_service import LeafletMapService, MapService
from .settings_store import (
    get_map_default_track_color,
    get_map_direction_arrow_count,
    get_map_direction_arrow_color,
    get_map_direction_arrow_size_px,
    get_map_distance_marker_border_color,
    get_map_distance_marker_color,
    get_map_distance_marker_size_px,
    get_map_preview_lightening_factor,
    get_map_responsive_threshold_px,
    get_map_rest_stop_color,
    get_map_rest_stop_size_px,
    get_map_start_symbol_color,
    get_map_start_symbol_shape,
    get_map_start_symbol_size_px,
    get_map_stop_symbol_color,
    get_map_stop_symbol_shape,
    get_map_stop_symbol_size_px,
    get_map_track_point_color,
    get_map_track_point_size_px,
    get_window_folder_tree_expanded_ids,
    get_window_keep_configuration_enabled,
    get_window_keep_folder_tree_structure_enabled,
    get_window_keep_last_track_shown_enabled,
    get_window_last_track_id,
    get_window_preview_folder_track_list_enabled,
    get_window_size,
    get_window_splitter_sizes,
    set_map_default_track_color,
    set_map_direction_arrow_count,
    set_map_direction_arrow_color,
    set_map_direction_arrow_size_px,
    set_map_distance_marker_border_color,
    set_map_distance_marker_color,
    set_map_distance_marker_size_px,
    set_map_preview_lightening_factor,
    set_library_root,
    set_map_responsive_threshold_px,
    set_map_rest_stop_color,
    set_map_rest_stop_size_px,
    set_map_start_symbol_color,
    set_map_start_symbol_shape,
    set_map_start_symbol_size_px,
    set_map_stop_symbol_color,
    set_map_stop_symbol_shape,
    set_map_stop_symbol_size_px,
    set_map_track_point_color,
    set_map_track_point_size_px,
    set_window_folder_tree_expanded_ids,
    set_window_keep_configuration_enabled,
    set_window_keep_folder_tree_structure_enabled,
    set_window_keep_last_track_shown_enabled,
    set_window_last_track_id,
    set_window_preview_folder_track_list_enabled,
    set_window_size,
    set_window_splitter_sizes,
)


TRACK_IDS_MIME = "application/x-gpx-track-ids"
FOLDER_ID_ROLE = Qt.ItemDataRole.UserRole
FOLDER_KIND_ROLE = Qt.ItemDataRole.UserRole + 1
TRACK_ID_ROLE = Qt.ItemDataRole.UserRole


@dataclass
class _EditCommand:
    label: str
    undo: Callable[[], None]
    redo: Callable[[], None]


@dataclass
class _FolderPreviewCacheEntry:
    html: str
    track_count: int
    dirty: bool = False


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
        library_root_path: str,
        current_threshold_px: int,
        preview_folder_track_list: bool,
        preview_lightening_factor: float,
        keep_window_configuration: bool,
        keep_folder_tree_structure: bool,
        keep_last_track_shown: bool,
        rest_stop_color: str,
        rest_stop_size_px: int,
        default_track_color: str,
        start_symbol_color: str,
        start_symbol_size_px: int,
        start_symbol_shape: str,
        stop_symbol_color: str,
        stop_symbol_size_px: int,
        stop_symbol_shape: str,
        distance_marker_color: str,
        distance_marker_border_color: str,
        distance_marker_size_px: int,
        direction_arrow_color: str,
        direction_arrow_count: int,
        direction_arrow_size_px: int,
        track_point_color: str,
        track_point_size_px: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(650, 560)

        layout = QVBoxLayout(self)

        tabs = QTabWidget(self)

        general_tab = QWidget(self)
        general_form = QFormLayout(general_tab)
        library_row = QWidget(general_tab)
        library_layout = QHBoxLayout(library_row)
        library_layout.setContentsMargins(0, 0, 0, 0)
        self._library_root_path_edit = QLineEdit(library_root_path, library_row)
        browse_button = QPushButton("Browse...", library_row)
        browse_button.clicked.connect(self._browse_library_root_path)
        library_layout.addWidget(self._library_root_path_edit)
        library_layout.addWidget(browse_button)
        general_form.addRow("Track Library Path:", library_row)
        tabs.addTab(general_tab, "General")

        window_tab = QWidget(self)
        window_form = QFormLayout(window_tab)
        self._map_threshold_spin = QSpinBox(window_tab)
        self._map_threshold_spin.setRange(320, 2000)
        self._map_threshold_spin.setSingleStep(20)
        self._map_threshold_spin.setValue(current_threshold_px)
        self._map_threshold_spin.setSuffix(" px")
        window_form.addRow("Map responsive threshold:", self._map_threshold_spin)

        self._preview_folder_track_list_checkbox = QCheckBox("Enable folder track overview preview", window_tab)
        self._preview_folder_track_list_checkbox.setChecked(preview_folder_track_list)
        window_form.addRow("Preview folder track list:", self._preview_folder_track_list_checkbox)

        self._preview_lightening_factor_spin = QDoubleSpinBox(window_tab)
        self._preview_lightening_factor_spin.setRange(0.0, 1.0)
        self._preview_lightening_factor_spin.setSingleStep(0.05)
        self._preview_lightening_factor_spin.setDecimals(2)
        self._preview_lightening_factor_spin.setSpecialValueText("No lightening (0.00)")
        self._preview_lightening_factor_spin.setValue(preview_lightening_factor)
        window_form.addRow("Track preview lightening factor:", self._preview_lightening_factor_spin)

        self._keep_window_configuration_checkbox = QCheckBox("Keep app size and panel widths", window_tab)
        self._keep_window_configuration_checkbox.setChecked(keep_window_configuration)
        window_form.addRow("Keep window configuration:", self._keep_window_configuration_checkbox)

        self._keep_folder_tree_structure_checkbox = QCheckBox("Restore expanded/collapsed folder tree", window_tab)
        self._keep_folder_tree_structure_checkbox.setChecked(keep_folder_tree_structure)
        window_form.addRow("Keep folder tree structure:", self._keep_folder_tree_structure_checkbox)

        self._keep_last_track_shown_checkbox = QCheckBox("Restore last shown track", window_tab)
        self._keep_last_track_shown_checkbox.setChecked(keep_last_track_shown)
        window_form.addRow("Keep last track shown:", self._keep_last_track_shown_checkbox)
        tabs.addTab(window_tab, "Window")

        track_tab = QWidget(self)
        form = QFormLayout(track_tab)

        def add_section_header(title: str, shaded: bool) -> None:
            header = QLabel(title, track_tab)
            background = "#f2f2f2" if shaded else "#ffffff"
            header.setStyleSheet(
                "QLabel {"
                f"background: {background};"
                "border: 1px solid #d8d8d8;"
                "padding: 6px 8px;"
                "font-weight: 600;"
                "}"
            )
            form.addRow(header)

        add_section_header("Track", shaded=False)

        self._default_track_color_button = QPushButton(default_track_color, track_tab)
        self._default_track_color_button.clicked.connect(
            lambda: self._pick_color(self._default_track_color_button)
        )
        self._apply_color_button_style(self._default_track_color_button)
        form.addRow("Default track color:", self._default_track_color_button)

        add_section_header("Start Symbol", shaded=True)

        self._start_symbol_color_button = QPushButton(start_symbol_color, track_tab)
        self._start_symbol_color_button.clicked.connect(
            lambda: self._pick_color(self._start_symbol_color_button)
        )
        self._apply_color_button_style(self._start_symbol_color_button)
        form.addRow("Start symbol color:", self._start_symbol_color_button)

        self._start_symbol_size_spin = QSpinBox(track_tab)
        self._start_symbol_size_spin.setRange(4, 40)
        self._start_symbol_size_spin.setValue(start_symbol_size_px)
        self._start_symbol_size_spin.setSuffix(" px")
        form.addRow("Start symbol size:", self._start_symbol_size_spin)

        self._start_symbol_shape_combo = QComboBox(track_tab)
        self._start_symbol_shape_combo.addItems(["square", "circle"])
        self._start_symbol_shape_combo.setCurrentText(start_symbol_shape)
        form.addRow("Start symbol shape:", self._start_symbol_shape_combo)

        add_section_header("Stop Symbol", shaded=False)

        self._stop_symbol_color_button = QPushButton(stop_symbol_color, track_tab)
        self._stop_symbol_color_button.clicked.connect(
            lambda: self._pick_color(self._stop_symbol_color_button)
        )
        self._apply_color_button_style(self._stop_symbol_color_button)
        form.addRow("Stop symbol color:", self._stop_symbol_color_button)

        self._stop_symbol_size_spin = QSpinBox(track_tab)
        self._stop_symbol_size_spin.setRange(4, 40)
        self._stop_symbol_size_spin.setValue(stop_symbol_size_px)
        self._stop_symbol_size_spin.setSuffix(" px")
        form.addRow("Stop symbol size:", self._stop_symbol_size_spin)

        self._stop_symbol_shape_combo = QComboBox(track_tab)
        self._stop_symbol_shape_combo.addItems(["square", "circle"])
        self._stop_symbol_shape_combo.setCurrentText(stop_symbol_shape)
        form.addRow("Stop symbol shape:", self._stop_symbol_shape_combo)

        add_section_header("Distance Marker", shaded=True)

        self._distance_marker_color_button = QPushButton(distance_marker_color, track_tab)
        self._distance_marker_color_button.clicked.connect(
            lambda: self._pick_color(self._distance_marker_color_button)
        )
        self._apply_color_button_style(self._distance_marker_color_button)
        form.addRow("Distance marker color:", self._distance_marker_color_button)

        self._distance_marker_border_color_button = QPushButton(distance_marker_border_color, track_tab)
        self._distance_marker_border_color_button.clicked.connect(
            lambda: self._pick_color(self._distance_marker_border_color_button)
        )
        self._apply_color_button_style(self._distance_marker_border_color_button)
        form.addRow("Distance marker border color:", self._distance_marker_border_color_button)

        self._distance_marker_size_spin = QSpinBox(track_tab)
        self._distance_marker_size_spin.setRange(2, 24)
        self._distance_marker_size_spin.setValue(distance_marker_size_px)
        self._distance_marker_size_spin.setSuffix(" px")
        form.addRow("Distance marker size:", self._distance_marker_size_spin)

        add_section_header("Rest Stop", shaded=False)

        self._rest_stop_color_button = QPushButton(rest_stop_color, track_tab)
        self._rest_stop_color_button.clicked.connect(
            lambda: self._pick_color(self._rest_stop_color_button)
        )
        self._apply_color_button_style(self._rest_stop_color_button)
        form.addRow("Rest stop color:", self._rest_stop_color_button)

        self._rest_stop_size_spin = QSpinBox(track_tab)
        self._rest_stop_size_spin.setRange(2, 24)
        self._rest_stop_size_spin.setValue(rest_stop_size_px)
        self._rest_stop_size_spin.setSuffix(" px")
        form.addRow("Rest stop size:", self._rest_stop_size_spin)

        add_section_header("Direction Arrows", shaded=True)

        self._direction_arrow_color_button = QPushButton(direction_arrow_color, track_tab)
        self._direction_arrow_color_button.clicked.connect(
            lambda: self._pick_color(self._direction_arrow_color_button)
        )
        self._apply_color_button_style(self._direction_arrow_color_button)
        form.addRow("Direction arrow color:", self._direction_arrow_color_button)

        self._direction_arrow_count_spin = QSpinBox(track_tab)
        self._direction_arrow_count_spin.setRange(1, 200)
        self._direction_arrow_count_spin.setSingleStep(1)
        self._direction_arrow_count_spin.setValue(direction_arrow_count)
        self._direction_arrow_count_spin.setSuffix(" arrows")
        form.addRow("Direction arrows per track:", self._direction_arrow_count_spin)

        self._direction_arrow_size_spin = QSpinBox(track_tab)
        self._direction_arrow_size_spin.setRange(8, 40)
        self._direction_arrow_size_spin.setSingleStep(1)
        self._direction_arrow_size_spin.setValue(direction_arrow_size_px)
        self._direction_arrow_size_spin.setSuffix(" px")
        form.addRow("Direction arrow size:", self._direction_arrow_size_spin)

        add_section_header("Track Points", shaded=False)

        self._track_point_color_button = QPushButton(track_point_color, track_tab)
        self._track_point_color_button.clicked.connect(
            lambda: self._pick_color(self._track_point_color_button)
        )
        self._apply_color_button_style(self._track_point_color_button)
        form.addRow("Track point color:", self._track_point_color_button)

        self._track_point_size_spin = QSpinBox(track_tab)
        self._track_point_size_spin.setRange(1, 10)
        self._track_point_size_spin.setSingleStep(1)
        self._track_point_size_spin.setValue(track_point_size_px)
        self._track_point_size_spin.setSuffix(" px")
        form.addRow("Track point size:", self._track_point_size_spin)

        for spin in (
            self._start_symbol_size_spin,
            self._stop_symbol_size_spin,
            self._distance_marker_size_spin,
            self._rest_stop_size_spin,
            self._direction_arrow_count_spin,
            self._direction_arrow_size_spin,
            self._track_point_size_spin,
        ):
            spin.valueChanged.connect(lambda _value: self._refresh_live_preview_swatch())

        self._start_symbol_shape_combo.currentTextChanged.connect(
            lambda _value: self._refresh_live_preview_swatch()
        )
        self._stop_symbol_shape_combo.currentTextChanged.connect(
            lambda _value: self._refresh_live_preview_swatch()
        )

        self._live_preview_label = QLabel(track_tab)
        self._live_preview_label.setWordWrap(True)
        self._live_preview_label.setTextFormat(Qt.TextFormat.RichText)
        self._refresh_live_preview_swatch()
        form.addRow("Live preview:", self._live_preview_label)
        tabs.addTab(track_tab, "Track")

        hint = QLabel("Configure application behavior and track map rendering preferences.", self)
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(tabs)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def selected_library_root_path(self) -> Path:
        return Path(self._library_root_path_edit.text().strip()).expanduser()

    def selected_map_threshold_px(self) -> int:
        return int(self._map_threshold_spin.value())

    def selected_preview_folder_track_list_enabled(self) -> bool:
        return self._preview_folder_track_list_checkbox.isChecked()

    def selected_preview_lightening_factor(self) -> float:
        return float(self._preview_lightening_factor_spin.value())

    def selected_keep_window_configuration_enabled(self) -> bool:
        return self._keep_window_configuration_checkbox.isChecked()

    def selected_keep_folder_tree_structure_enabled(self) -> bool:
        return self._keep_folder_tree_structure_checkbox.isChecked()

    def selected_keep_last_track_shown_enabled(self) -> bool:
        return self._keep_last_track_shown_checkbox.isChecked()

    def selected_rest_stop_color(self) -> str:
        return self._rest_stop_color_button.text()

    def selected_default_track_color(self) -> str:
        return self._default_track_color_button.text()

    def selected_start_symbol_color(self) -> str:
        return self._start_symbol_color_button.text()

    def selected_start_symbol_size_px(self) -> int:
        return int(self._start_symbol_size_spin.value())

    def selected_start_symbol_shape(self) -> str:
        return self._start_symbol_shape_combo.currentText()

    def selected_stop_symbol_color(self) -> str:
        return self._stop_symbol_color_button.text()

    def selected_stop_symbol_size_px(self) -> int:
        return int(self._stop_symbol_size_spin.value())

    def selected_stop_symbol_shape(self) -> str:
        return self._stop_symbol_shape_combo.currentText()

    def selected_distance_marker_color(self) -> str:
        return self._distance_marker_color_button.text()

    def selected_distance_marker_border_color(self) -> str:
        return self._distance_marker_border_color_button.text()

    def selected_distance_marker_size_px(self) -> int:
        return int(self._distance_marker_size_spin.value())

    def selected_rest_stop_size_px(self) -> int:
        return int(self._rest_stop_size_spin.value())

    def selected_direction_arrow_color(self) -> str:
        return self._direction_arrow_color_button.text()

    def selected_direction_arrow_count(self) -> int:
        return int(self._direction_arrow_count_spin.value())

    def selected_direction_arrow_size_px(self) -> int:
        return int(self._direction_arrow_size_spin.value())

    def selected_track_point_color(self) -> str:
        return self._track_point_color_button.text()

    def selected_track_point_size_px(self) -> int:
        return int(self._track_point_size_spin.value())

    def _browse_library_root_path(self) -> None:
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Track Library Folder",
            self._library_root_path_edit.text().strip() or str(Path.home()),
        )
        if not selected_dir:
            return
        self._library_root_path_edit.setText(selected_dir)

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
        marker_border = self._distance_marker_border_color_button.text().strip()
        arrow = self._direction_arrow_color_button.text().strip()
        point = self._track_point_color_button.text().strip()
        start = self._start_symbol_color_button.text().strip()
        stop = self._stop_symbol_color_button.text().strip()
        start_size = int(self._start_symbol_size_spin.value())
        stop_size = int(self._stop_symbol_size_spin.value())
        marker_size = int(self._distance_marker_size_spin.value())
        rest_size = int(self._rest_stop_size_spin.value())
        point_size = int(self._track_point_size_spin.value())
        start_glyph = "●" if self._start_symbol_shape_combo.currentText() == "circle" else "■"
        stop_glyph = "●" if self._stop_symbol_shape_combo.currentText() == "circle" else "■"

        # Use text glyphs (rather than CSS boxes) because QLabel rich text support
        # for inline block geometry is limited and can hide custom shape spans.
        start_symbol = f"<span style='color:{start}; font-size:{max(10, start_size + 2)}px;'>{start_glyph}</span>"
        stop_symbol = f"<span style='color:{stop}; font-size:{max(10, stop_size + 2)}px;'>{stop_glyph}</span>"
        rest_symbol = f"<span style='color:{rest}; font-size:{max(10, rest_size + 4)}px;'>●</span>"
        marker_symbol = (
            f"<span style='color:{marker_border}; font-size:{max(10, marker_size + 5)}px;'>○</span>"
            f"<span style='color:{marker}; font-size:{max(10, marker_size + 5)}px;'>●</span>"
        )
        point_symbol = f"<span style='color:{point}; font-size:{max(8, point_size + 7)}px;'>•</span>"
        self._live_preview_label.setText(
            ""
            f"<span style='font-weight:600;'>Track</span> "
            f"<span style='display:inline-block; min-width:48px; text-align:center; color:{track};'>━━</span> &nbsp;"
            f"<span style='font-weight:600;'>Start</span> "
            f"{start_symbol} &nbsp;"
            f"<span style='font-weight:600;'>Stop</span> "
            f"{stop_symbol} &nbsp;"
            f"<span style='font-weight:600;'>Rest</span> "
            f"{rest_symbol} &nbsp;"
            f"<span style='font-weight:600;'>Marker</span> "
            f"{marker_symbol} &nbsp;"
            f"<span style='font-weight:600;'>Arrow</span> "
            f"<span style='display:inline-block; min-width:20px; text-align:center; color:{arrow}; font-weight:900;'>&gt;</span> &nbsp;"
            f"<span style='font-weight:600;'>Point</span> "
            f"{point_symbol}"
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
        self._main_splitter: QSplitter | None = None
        self._current_map_html: str = ""
        self._pending_trim_start_percent: float | None = None
        self._map_hide_timer = QTimer(self)
        self._map_hide_timer.setSingleShot(True)
        self._map_hide_timer.timeout.connect(self._hide_map_toolbar)
        self._preview_update_timer = QTimer(self)
        self._preview_update_timer.setSingleShot(True)
        self._preview_update_timer.timeout.connect(self._preview_selected_track)
        self._import_action = None
        self._undo_action = None
        self._redo_action = None
        self._undo_stack: list[_EditCommand] = []
        self._redo_stack: list[_EditCommand] = []
        self._visible_tracks: list[TrackRecord] = []
        self._preview_cache: dict[int, _FolderPreviewCacheEntry] = {}
        self._preview_cache_queue: set[int] = set()
        self._folder_parent_by_id: dict[int, int | None] = {}
        self._folder_kind_by_id: dict[int, str] = {}
        self._folder_ids: set[int] = set()
        self._expanded_folder_ids: set[int] = set(get_window_folder_tree_expanded_ids())
        self._preview_folder_track_list_enabled = get_window_preview_folder_track_list_enabled()
        self._keep_window_configuration_enabled = get_window_keep_configuration_enabled()
        self._keep_folder_tree_structure_enabled = get_window_keep_folder_tree_structure_enabled()
        self._keep_last_track_shown_enabled = get_window_keep_last_track_shown_enabled()
        self._last_track_id_to_restore: int | None = (
            get_window_last_track_id() if self._keep_last_track_shown_enabled else None
        )
        self._preview_cache_timer = QTimer(self)
        self._preview_cache_timer.setSingleShot(True)
        self._preview_cache_timer.timeout.connect(self._process_preview_cache_queue)
        self._map_overlay_state: dict[str, bool] = {
            "gradient": True,
            "points": False,
            "endpoints": True,
            "distance": True,
            "directionArrows": True,
            "rests": True,
            "bicycleRoutes": False,
        }
        self.setWindowTitle(f"{APP_NAME} - Milestone 6 Organizer")
        if self._keep_window_configuration_enabled:
            width, height = get_window_size()
            self.resize(width, height)
        else:
            self.resize(1400, 840)
        self.setAcceptDrops(True)
        self._init_menu()
        self._init_body()
        self._init_status_bar()
        self._load_library_tree()
        self._restore_last_track_if_needed()

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
        export_action = file_menu.addAction("Export GPX")
        export_action.triggered.connect(self._export_selected_track)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

        edit_menu = menu_bar.addMenu("Edit")
        rename_action = edit_menu.addAction("Rename")
        rename_action.triggered.connect(self._rename_selected_item)
        delete_action = edit_menu.addAction("Delete")
        delete_action.triggered.connect(self._delete_selected_item)
        edit_menu.addSeparator()
        self._undo_action = edit_menu.addAction("Undo")
        self._undo_action.triggered.connect(self._undo_last_edit)
        self._redo_action = edit_menu.addAction("Redo")
        self._redo_action.triggered.connect(self._redo_last_edit)

        track_menu = menu_bar.addMenu("Track")
        trim_action = track_menu.addAction("Trim")
        trim_action.triggered.connect(self._trim_selected_track)
        split_action = track_menu.addAction("Split")
        split_action.triggered.connect(self._split_selected_track)
        merge_action = track_menu.addAction("Merge")
        merge_action.triggered.connect(self._merge_selected_tracks)
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
        self._update_undo_redo_actions()

    def _init_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter = splitter
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

        if self._keep_window_configuration_enabled:
            saved_sizes = get_window_splitter_sizes()
            if len(saved_sizes) == 3:
                splitter.setSizes(saved_sizes)

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
        tree.itemExpanded.connect(self._handle_tree_item_expanded)
        tree.itemCollapsed.connect(self._handle_tree_item_collapsed)
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
        track_list.itemSelectionChanged.connect(self._schedule_preview_update)
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
            self._show_select_track_placeholder()
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
        self._refresh_folder_topology(folders)
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
            if self._keep_folder_tree_structure_enabled and folder.id in self._expanded_folder_ids:
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

    def _handle_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        folder_id = item.data(0, FOLDER_ID_ROLE)
        if folder_id is None:
            return
        self._expanded_folder_ids.add(int(folder_id))

    def _handle_tree_item_collapsed(self, item: QTreeWidgetItem) -> None:
        folder_id = item.data(0, FOLDER_ID_ROLE)
        if folder_id is None:
            return
        self._expanded_folder_ids.discard(int(folder_id))

    def _restore_last_track_if_needed(self) -> None:
        if not self._keep_last_track_shown_enabled:
            return

        if self._last_track_id_to_restore is None:
            return

        try:
            track = self.library_store.get_track(self._last_track_id_to_restore)
        except ValueError:
            self._last_track_id_to_restore = None
            return

        self._load_library_tree(selected_folder_id=track.folder_id)
        self._reload_track_list(selected_track_id=track.id)
        if self.track_list is not None:
            self._preview_selected_track()
        self._last_track_id_to_restore = None

    def _refresh_folder_topology(self, folders: list[FolderRecord]) -> None:
        self._folder_parent_by_id = {folder.id: folder.parent_id for folder in folders}
        self._folder_kind_by_id = {folder.id: folder.kind for folder in folders}
        self._folder_ids = {folder.id for folder in folders}
        self._evict_obsolete_preview_cache()

    def _set_map_delete_behavior(self, use_permanent_delete: bool) -> None:
        if isinstance(self.map_service, LeafletMapService):
            self.map_service.track_delete_uses_permanent = bool(use_permanent_delete)

    def _evict_obsolete_preview_cache(self) -> None:
        obsolete = [folder_id for folder_id in self._preview_cache if folder_id not in self._folder_ids]
        for folder_id in obsolete:
            self._preview_cache.pop(folder_id, None)
            self._preview_cache_queue.discard(folder_id)

    def _mark_preview_cache_dirty_for_ancestor_chain(self, folder_id: int) -> None:
        current: int | None = folder_id
        while current is not None:
            entry = self._preview_cache.get(current)
            if entry is not None:
                entry.dirty = True
            self._preview_cache_queue.add(current)
            current = self._folder_parent_by_id.get(current)

        self._schedule_preview_cache_rebuild()

    def _mark_all_preview_cache_dirty(self) -> None:
        for folder_id in self._folder_ids:
            entry = self._preview_cache.get(folder_id)
            if entry is not None:
                entry.dirty = True
            self._preview_cache_queue.add(folder_id)
        self._schedule_preview_cache_rebuild()

    def _schedule_preview_cache_rebuild(self) -> None:
        if not self._preview_cache_queue:
            return
        # Debounce rebuilds to coalesce bursts of edits/imports/moves.
        self._preview_cache_timer.start(250)

    def _process_preview_cache_queue(self) -> None:
        if not self._preview_cache_queue:
            return

        folder_id = min(self._preview_cache_queue)
        self._preview_cache_queue.discard(folder_id)
        if folder_id in self._folder_ids:
            self._rebuild_preview_cache_for_folder(folder_id)

        if self._preview_cache_queue:
            self._preview_cache_timer.start(60)

    def _rebuild_preview_cache_for_folder(self, folder_id: int) -> None:
        if not isinstance(self.map_service, LeafletMapService):
            return

        self._set_map_delete_behavior(self._folder_kind_by_id.get(folder_id) == "trash")

        tracks = self.library_store.list_tracks_recursive(folder_id)
        if not tracks:
            rendered = self.map_service.render_placeholder(
                title="Map Preview",
                message="No tracks in this folder view.",
            )
            self._preview_cache[folder_id] = _FolderPreviewCacheEntry(
                html=rendered.html,
                track_count=0,
                dirty=False,
            )
        else:
            folder_path_by_id = self._build_folder_path_by_id()
            track_inputs: list[tuple[int, Path, str, str]] = []
            for track in tracks:
                managed_path = self.library_store.library_root / track.managed_rel_path
                if not managed_path.exists():
                    continue
                folder_path = folder_path_by_id.get(track.folder_id, "My Library")
                hover_label = f"{folder_path}/{track.display_name}"
                track_inputs.append((track.id, managed_path, track.display_name, hover_label))

            if not track_inputs:
                rendered = self.map_service.render_placeholder(
                    title="Map Preview",
                    message="No valid track files in this folder view.",
                )
                self._preview_cache[folder_id] = _FolderPreviewCacheEntry(
                    html=rendered.html,
                    track_count=0,
                    dirty=False,
                )
            else:
                rendered = self.map_service.render_track_lines_preview(track_inputs)
                self._preview_cache[folder_id] = _FolderPreviewCacheEntry(
                    html=rendered.html,
                    track_count=len(track_inputs),
                    dirty=False,
                )

        if self._selected_folder_id() == folder_id and not self._selected_track_ids():
            entry = self._preview_cache.get(folder_id)
            if entry is not None:
                self._set_map_html(entry.html)

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
        tracks = self.library_store.list_tracks_recursive(folder_id)
        self._visible_tracks = tracks

        self.track_list.blockSignals(True)
        self.track_list.clear()
        if not tracks:
            placeholder = QListWidgetItem("No tracks in this folder")
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.track_list.addItem(placeholder)
            self.track_list.blockSignals(False)
            self._set_map_placeholder(
                title="Map Preview",
                message="No tracks in this folder view.",
            )
            return

        for track in tracks:
            item = QListWidgetItem(track.display_name)
            item.setData(TRACK_ID_ROLE, track.id)
            self.track_list.addItem(item)
            if selected_track_id is not None and track.id == selected_track_id:
                self.track_list.setCurrentItem(item)

        self.track_list.blockSignals(False)
        self._schedule_preview_update()

    def _schedule_preview_update(self) -> None:
        # Coalesce rapid selection changes into one render to keep UI responsive.
        self._preview_update_timer.start(90)

    def _import_file_paths(self, file_paths: list[Path], folder_id: int) -> tuple[int, int, list[str]]:
        imported_count = 0
        duplicate_count = 0
        failures: list[str] = []

        for path in file_paths:
            if path.suffix.lower() != ".gpx":
                failures.append(f"{path}: not a .gpx file")
                continue

            try:
                results = self.library_store.import_gpx_all(path, folder_id)
                imported_count += len(results)
                duplicate_count += sum(1 for result in results if result.is_duplicate)
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
        self._mark_preview_cache_dirty_for_ancestor_chain(folder_id)

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
        self._mark_preview_cache_dirty_for_ancestor_chain(folder_id)
        self.statusBar().showMessage(
            f"Imported {imported_count} dropped GPX file(s); duplicates: {duplicate_count}",
            7000,
        )
        if failures:
            QMessageBox.warning(self, "Dropped import errors", "\n".join(failures[:10]))

    def _export_selected_track(self) -> None:
        track_ids = self._selected_track_ids()
        if len(track_ids) != 1:
            QMessageBox.information(self, "Export GPX", "Please select exactly one track.")
            return

        track = self.library_store.get_track(track_ids[0])
        default_target = str(Path.home() / track.display_name)
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export GPX",
            default_target,
            "GPX Files (*.gpx)",
        )
        if not selected_path:
            return

        destination = Path(selected_path)
        if destination.suffix.lower() != ".gpx":
            destination = destination.with_suffix(".gpx")

        overwrite = False
        if destination.exists():
            reply = QMessageBox.question(
                self,
                "Export GPX",
                f"{destination.name} already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            overwrite = True

        try:
            exported_path = self.library_store.export_track(
                track_id=track.id,
                destination_path=destination,
                overwrite=overwrite,
            )
            self.statusBar().showMessage(f"Exported GPX to {exported_path}", 6000)
        except Exception as exc:
            QMessageBox.warning(self, "Export GPX failed", str(exc))

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
            self._preview_cache.clear()
            self._preview_cache_queue.clear()
            self._folder_parent_by_id.clear()
            self._folder_ids.clear()
            self._expanded_folder_ids.clear()
            self._last_track_id_to_restore = None
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
        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(self._rename_selected_track_dialog)

        reverse_action = menu.addAction("Reverse")
        reverse_action.triggered.connect(self._reverse_selected_tracks)

        export_action = menu.addAction("Export GPX")
        export_action.triggered.connect(self._export_selected_track)

        set_color_action = menu.addAction("Set color")
        set_color_action.triggered.connect(self._set_selected_track_color)

        in_trash = self._selected_folder_kind() == "trash"
        move_to_trash_action = None
        delete_action = None
        if in_trash:
            delete_action = menu.addAction("Delete Permanently")
            delete_action.triggered.connect(self._delete_selected_tracks)
        else:
            move_to_trash_action = menu.addAction("Move to Trash")
            move_to_trash_action.triggered.connect(self._delete_selected_tracks)

        menu.addSeparator()
        show_action = menu.addAction("Show on Map")
        show_action.triggered.connect(self._preview_selected_track)

        trim_action = menu.addAction("Trim")
        trim_action.triggered.connect(self._trim_selected_track)

        split_action = menu.addAction("Split")
        split_action.triggered.connect(self._split_selected_track)

        merge_action = menu.addAction("Merge")
        merge_action.triggered.connect(self._merge_selected_tracks)

        if not self._selected_track_ids():
            show_action.setEnabled(False)
            rename_action.setEnabled(False)
            reverse_action.setEnabled(False)
            trim_action.setEnabled(False)
            split_action.setEnabled(False)
            merge_action.setEnabled(False)
            export_action.setEnabled(False)
            set_color_action.setEnabled(False)
            if move_to_trash_action is not None:
                move_to_trash_action.setEnabled(False)
            if delete_action is not None:
                delete_action.setEnabled(False)
        elif len(self._selected_track_ids()) < 2:
            merge_action.setEnabled(False)

        menu.exec(self.track_list.viewport().mapToGlobal(pos))

    def _open_track_preview(self, item: QListWidgetItem) -> None:
        track_id = item.data(TRACK_ID_ROLE)
        if track_id is None:
            self._show_select_track_placeholder()
            return

        track_name = item.text()
        try:
            managed_path = self.library_store.get_track_managed_path(int(track_id))
            if isinstance(self.map_service, LeafletMapService):
                self._set_map_delete_behavior(self._selected_folder_kind() == "trash")
                rendered = self.map_service.render_track(
                    managed_path,
                    track_name,
                    initial_overlays=self._map_overlay_state,
                )
            else:
                rendered = self.map_service.render_track(managed_path, track_name)
            self._set_map_html(rendered.html)
            self.statusBar().showMessage(f"Loaded map preview for {track_name}", 5000)
        except Exception as exc:
            # Treat a stale selection (deleted track) as a normal empty-preview state.
            if isinstance(exc, ValueError) and "Track id" in str(exc) and "not found" in str(exc):
                self._show_select_track_placeholder()
                return

            self._set_map_placeholder(title="Map preview failed", message=str(exc))
            QMessageBox.warning(self, "Map preview failed", str(exc))

    def _preview_selected_track(self) -> None:
        if self.track_list is None:
            if self._preview_folder_track_list_enabled:
                self._preview_visible_tracks_overview()
            else:
                self._show_select_track_placeholder()
            return

        selected_items = [
            item
            for item in self.track_list.selectedItems()
            if item.data(TRACK_ID_ROLE) is not None
        ]
        if not selected_items:
            if self._preview_folder_track_list_enabled:
                self._preview_visible_tracks_overview()
            else:
                self._show_select_track_placeholder()
            return

        if len(selected_items) == 1:
            self._open_track_preview(selected_items[0])
            return

        self._open_selected_tracks_with_overlays(selected_items)

    def _show_select_track_placeholder(self) -> None:
        self._set_map_placeholder(
            title="Map Preview",
            message="Select a track for preview",
        )

    def _preview_temp_track(self, preview_path: Path, preview_name: str) -> None:
        try:
            if isinstance(self.map_service, LeafletMapService):
                self._set_map_delete_behavior(self._selected_folder_kind() == "trash")
                rendered = self.map_service.render_track(
                    preview_path,
                    preview_name,
                    initial_overlays=self._map_overlay_state,
                )
            else:
                rendered = self.map_service.render_track(preview_path, preview_name)
            self._set_map_html(rendered.html)
            self.statusBar().showMessage(f"Preview loaded: {preview_name}", 5000)
        finally:
            if preview_path.exists():
                preview_path.unlink()

    def _preview_visible_tracks_overview(self) -> None:
        folder_id = self._selected_folder_id()
        entry = self._preview_cache.get(folder_id)

        if entry is not None:
            self._set_map_html(entry.html)
            self.statusBar().showMessage(
                f"Previewing {entry.track_count} track(s) in folder view",
                3000,
            )
            if entry.dirty:
                self._preview_cache_queue.add(folder_id)
                self._schedule_preview_cache_rebuild()
            return

        self._set_map_placeholder(
            title="Map Preview",
            message="Preparing folder preview...",
        )
        self._preview_cache_queue.add(folder_id)
        self._schedule_preview_cache_rebuild()

    def _build_folder_path_by_id(self) -> dict[int, str]:
        folders = self.library_store.list_folders()
        folder_by_id = {folder.id: folder for folder in folders}

        path_by_id: dict[int, str] = {}
        for folder in folders:
            names: list[str] = []
            current = folder
            seen: set[int] = set()
            while current is not None and current.id not in seen:
                seen.add(current.id)
                names.append(current.name)
                if current.parent_id is None:
                    break
                current = folder_by_id.get(current.parent_id)

            path_by_id[folder.id] = "/".join(reversed(names)) if names else "My Library"

        return path_by_id

    def _open_selected_tracks_with_overlays(self, selected_items: list[QListWidgetItem]) -> None:
        track_inputs: list[tuple[Path, str]] = []
        for item in selected_items:
            track_id = int(item.data(TRACK_ID_ROLE))
            managed_path = self.library_store.get_track_managed_path(track_id)
            if managed_path.exists():
                track_inputs.append((managed_path, item.text()))

        if not track_inputs:
            self._preview_visible_tracks_overview()
            return

        try:
            if isinstance(self.map_service, LeafletMapService):
                self._set_map_delete_behavior(self._selected_folder_kind() == "trash")
                rendered = self.map_service.render_tracks_with_overlays(
                    track_inputs,
                    initial_overlays=self._map_overlay_state,
                )
            else:
                rendered = self.map_service.render_track(track_inputs[0][0], track_inputs[0][1])
            self._set_map_html(rendered.html)
            self.statusBar().showMessage(
                f"Loaded preview for {len(track_inputs)} selected track(s)",
                5000,
            )
        except Exception as exc:
            self._set_map_placeholder(title="Map preview failed", message=str(exc))
            QMessageBox.warning(self, "Map preview failed", str(exc))

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
            library_root_path=str(self.library_store.library_root),
            current_threshold_px=get_map_responsive_threshold_px(),
            preview_folder_track_list=get_window_preview_folder_track_list_enabled(),
            preview_lightening_factor=get_map_preview_lightening_factor(),
            keep_window_configuration=get_window_keep_configuration_enabled(),
            keep_folder_tree_structure=get_window_keep_folder_tree_structure_enabled(),
            keep_last_track_shown=get_window_keep_last_track_shown_enabled(),
            rest_stop_color=get_map_rest_stop_color(),
            rest_stop_size_px=get_map_rest_stop_size_px(),
            default_track_color=get_map_default_track_color(),
            start_symbol_color=get_map_start_symbol_color(),
            start_symbol_size_px=get_map_start_symbol_size_px(),
            start_symbol_shape=get_map_start_symbol_shape(),
            stop_symbol_color=get_map_stop_symbol_color(),
            stop_symbol_size_px=get_map_stop_symbol_size_px(),
            stop_symbol_shape=get_map_stop_symbol_shape(),
            distance_marker_color=get_map_distance_marker_color(),
            distance_marker_border_color=get_map_distance_marker_border_color(),
            distance_marker_size_px=get_map_distance_marker_size_px(),
            direction_arrow_color=get_map_direction_arrow_color(),
            direction_arrow_count=get_map_direction_arrow_count(),
            direction_arrow_size_px=get_map_direction_arrow_size_px(),
            track_point_color=get_map_track_point_color(),
            track_point_size_px=get_map_track_point_size_px(),
            parent=self,
        )
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return

        selected_library_root = dialog.selected_library_root_path().expanduser()
        try:
            selected_library_root_resolved = selected_library_root.resolve()
        except FileNotFoundError:
            selected_library_root_resolved = selected_library_root

        if selected_library_root_resolved != self.library_store.library_root:
            db_path = selected_library_root / "library.db"
            is_empty_dir = selected_library_root.exists() and selected_library_root.is_dir() and not any(selected_library_root.iterdir())
            if db_path.exists() or not selected_library_root.exists() or is_empty_dir:
                self._switch_library(selected_library_root)
            else:
                QMessageBox.warning(
                    self,
                    "Invalid library",
                    "Track Library Path must point to an existing library (contains library.db).",
                )

        saved_threshold = set_map_responsive_threshold_px(dialog.selected_map_threshold_px())
        self._preview_folder_track_list_enabled = set_window_preview_folder_track_list_enabled(
            dialog.selected_preview_folder_track_list_enabled()
        )
        saved_preview_lightening_factor = set_map_preview_lightening_factor(
            dialog.selected_preview_lightening_factor()
        )
        self._keep_window_configuration_enabled = set_window_keep_configuration_enabled(
            dialog.selected_keep_window_configuration_enabled()
        )
        self._keep_folder_tree_structure_enabled = set_window_keep_folder_tree_structure_enabled(
            dialog.selected_keep_folder_tree_structure_enabled()
        )
        self._keep_last_track_shown_enabled = set_window_keep_last_track_shown_enabled(
            dialog.selected_keep_last_track_shown_enabled()
        )
        saved_rest_stop_color = set_map_rest_stop_color(dialog.selected_rest_stop_color())
        saved_rest_stop_size_px = set_map_rest_stop_size_px(dialog.selected_rest_stop_size_px())
        saved_default_track_color = set_map_default_track_color(dialog.selected_default_track_color())
        saved_start_symbol_color = set_map_start_symbol_color(dialog.selected_start_symbol_color())
        saved_start_symbol_size_px = set_map_start_symbol_size_px(dialog.selected_start_symbol_size_px())
        saved_start_symbol_shape = set_map_start_symbol_shape(dialog.selected_start_symbol_shape())
        saved_stop_symbol_color = set_map_stop_symbol_color(dialog.selected_stop_symbol_color())
        saved_stop_symbol_size_px = set_map_stop_symbol_size_px(dialog.selected_stop_symbol_size_px())
        saved_stop_symbol_shape = set_map_stop_symbol_shape(dialog.selected_stop_symbol_shape())
        saved_distance_marker_color = set_map_distance_marker_color(
            dialog.selected_distance_marker_color()
        )
        saved_distance_marker_border_color = set_map_distance_marker_border_color(
            dialog.selected_distance_marker_border_color()
        )
        saved_distance_marker_size_px = set_map_distance_marker_size_px(
            dialog.selected_distance_marker_size_px()
        )
        saved_direction_arrow_color = set_map_direction_arrow_color(
            dialog.selected_direction_arrow_color()
        )
        saved_direction_arrow_count = set_map_direction_arrow_count(
            dialog.selected_direction_arrow_count()
        )
        saved_direction_arrow_size_px = set_map_direction_arrow_size_px(
            dialog.selected_direction_arrow_size_px()
        )
        saved_track_point_color = set_map_track_point_color(dialog.selected_track_point_color())
        saved_track_point_size_px = set_map_track_point_size_px(dialog.selected_track_point_size_px())

        if isinstance(self.map_service, LeafletMapService):
            self.map_service.responsive_threshold_px = saved_threshold
            self.map_service.rest_stop_color = saved_rest_stop_color
            self.map_service.rest_stop_size_px = saved_rest_stop_size_px
            self.map_service.default_track_color = saved_default_track_color
            self.map_service.preview_lightening_factor = saved_preview_lightening_factor
            self.map_service.start_symbol_color = saved_start_symbol_color
            self.map_service.start_symbol_size_px = saved_start_symbol_size_px
            self.map_service.start_symbol_shape = saved_start_symbol_shape
            self.map_service.stop_symbol_color = saved_stop_symbol_color
            self.map_service.stop_symbol_size_px = saved_stop_symbol_size_px
            self.map_service.stop_symbol_shape = saved_stop_symbol_shape
            self.map_service.distance_marker_color = saved_distance_marker_color
            self.map_service.distance_marker_border_color = saved_distance_marker_border_color
            self.map_service.distance_marker_size_px = saved_distance_marker_size_px
            self.map_service.direction_arrow_color = saved_direction_arrow_color
            self.map_service.direction_arrow_count = saved_direction_arrow_count
            self.map_service.direction_arrow_size_px = saved_direction_arrow_size_px
            self.map_service.track_point_color = saved_track_point_color
            self.map_service.track_point_size_px = saved_track_point_size_px

        # Force style recalculation for all folder-level previews (root and subfolders).
        self._preview_cache.clear()
        self._preview_cache_queue.clear()

        if not self._keep_folder_tree_structure_enabled:
            self._expanded_folder_ids.clear()

        if not self._keep_last_track_shown_enabled:
            set_window_last_track_id(None)

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
            self._mark_preview_cache_dirty_for_ancestor_chain(self._selected_folder_id())
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
        if action == "open_track":
            track_id_raw = params.get("track_id", [None])[0]
            if track_id_raw is not None:
                try:
                    track_id = int(track_id_raw)
                    self._open_track_from_overview_map(track_id)
                except ValueError:
                    pass

            if self.map_web_view is not None:
                self.map_web_view.page().runJavaScript(
                    "if (window.location.hash.startsWith('#gpxcmd=1')) { window.location.hash = ''; }",
                )
            return

        if action == "track_action":
            track_id_raw = params.get("track_id", [None])[0]
            operation = params.get("op", [None])[0]
            if operation is not None:
                if track_id_raw is not None:
                    try:
                        self._run_track_action_from_overview_map(int(track_id_raw), str(operation))
                    except ValueError:
                        pass
                else:
                    self._run_track_action_for_current_track(str(operation))

            if self.map_web_view is not None:
                self.map_web_view.page().runJavaScript(
                    "if (window.location.hash.startsWith('#gpxcmd=1')) { window.location.hash = ''; }",
                )
            return

        if action == "overlay_state":
            layer_name = params.get("layer", [None])[0]
            enabled_raw = params.get("enabled", [None])[0]
            if layer_name is not None and enabled_raw is not None:
                enabled = enabled_raw in {"1", "true", "True"}
                self._map_overlay_state[str(layer_name)] = enabled

            if self.map_web_view is not None:
                self.map_web_view.page().runJavaScript(
                    "if (window.location.hash.startsWith('#gpxcmd=1')) { window.location.hash = ''; }",
                )
            return

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

    def _open_track_from_overview_map(self, track_id: int) -> None:
        try:
            track = self.library_store.get_track(track_id)
        except ValueError:
            self.statusBar().showMessage("Selected preview track is no longer available", 5000)
            self._rerender_current_track_preview()
            return

        self._load_library_tree(selected_folder_id=track.folder_id)
        self._reload_track_list(selected_track_id=track_id)
        self.statusBar().showMessage(f"Selected track: {track.display_name}", 5000)

    def _run_track_action_from_overview_map(self, track_id: int, operation: str) -> None:
        self._open_track_from_overview_map(track_id)

        if operation == "show":
            self._preview_selected_track()
            return
        if operation == "rename":
            self._rename_selected_track_dialog()
            return
        if operation == "reverse":
            self._reverse_selected_tracks()
            return
        if operation == "export":
            self._export_selected_track()
            return
        if operation == "set_color":
            self._set_selected_track_color()
            return
        if operation == "delete_permanently":
            self._delete_selected_tracks_permanently_from_map()
            return
        if operation == "move_to_trash":
            self._delete_selected_tracks()
            return

    def _run_track_action_for_current_track(self, operation: str) -> None:
        if operation == "rename":
            self._rename_selected_track_dialog()
            return
        if operation == "reverse":
            self._reverse_selected_tracks()
            return
        if operation == "export":
            self._export_selected_track()
            return
        if operation == "set_color":
            self._set_selected_track_color()
            return
        if operation == "delete_permanently":
            self._delete_selected_tracks_permanently_from_map()
            return
        if operation == "move_to_trash":
            self._delete_selected_tracks()
            return

    def _delete_selected_tracks_permanently_from_map(self) -> None:
        track_ids = self._selected_track_ids()
        if not track_ids:
            self.statusBar().showMessage("Select a track first", 4000)
            return

        reply = QMessageBox.question(
            self,
            "Delete permanently",
            "Permanently delete selected track(s)? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        failures: list[str] = []
        affected_folder_ids: set[int] = set()
        for track_id in track_ids:
            try:
                track = self.library_store.get_track(track_id)
                affected_folder_ids.add(track.folder_id)
                self.library_store.purge_track(track_id)
            except Exception as exc:
                failures.append(str(exc))

        self._reload_track_list()
        for folder_id in affected_folder_ids:
            self._mark_preview_cache_dirty_for_ancestor_chain(folder_id)

        if failures:
            QMessageBox.warning(self, "Delete permanently", "\n".join(failures[:8]))
            return

        self.statusBar().showMessage("Tracks permanently deleted", 5000)

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
                preview_a_path, preview_b_path = self.library_store.build_split_preview(
                    track_id,
                    split_percent=bounded,
                )
                self._preview_temp_track(preview_a_path, "Split preview (A)")
                if preview_b_path.exists():
                    preview_b_path.unlink()

                reply = QMessageBox.question(
                    self,
                    "Split track",
                    "Apply split and create two new track copies?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self._rerender_current_track_preview()
                    return

                part_a, part_b = self.library_store.split_track(track_id, split_percent=bounded)
                self._reload_track_list(selected_track_id=part_a.id)
                source_track = self.library_store.get_track(track_id)
                self._mark_preview_cache_dirty_for_ancestor_chain(source_track.folder_id)
                self.statusBar().showMessage(
                    f"Split from map: {part_a.display_name} and {part_b.display_name}",
                    6000,
                )

                state = {"track_ids": [part_a.id, part_b.id]}

                def _undo() -> None:
                    for generated_track_id in state["track_ids"]:
                        self.library_store.move_track_to_trash(generated_track_id)
                    self._reload_track_list(selected_track_id=track_id)

                def _redo() -> None:
                    new_a, new_b = self.library_store.split_track(
                        track_id,
                        split_percent=bounded,
                    )
                    state["track_ids"] = [new_a.id, new_b.id]
                    self._reload_track_list(selected_track_id=new_a.id)

                self._push_edit_command(_EditCommand(label="Split track", undo=_undo, redo=_redo))
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
                preview_path = self.library_store.build_trim_preview(
                    track_id,
                    start_percent=start_value,
                    end_percent=end_value,
                )
                self._preview_temp_track(preview_path, "Trim preview")

                reply = QMessageBox.question(
                    self,
                    "Trim track",
                    "Apply trim and create a new track copy?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self._rerender_current_track_preview()
                    return

                trimmed = self.library_store.trim_track(
                    track_id,
                    start_percent=start_value,
                    end_percent=end_value,
                )
                self._pending_trim_start_percent = None
                self._reload_track_list(selected_track_id=trimmed.id)
                source_track = self.library_store.get_track(track_id)
                self._mark_preview_cache_dirty_for_ancestor_chain(source_track.folder_id)
                self.statusBar().showMessage(
                    f"Trimmed from map: {trimmed.display_name}",
                    6000,
                )

                state = {"track_id": trimmed.id}

                def _undo() -> None:
                    self.library_store.move_track_to_trash(state["track_id"])
                    self._reload_track_list(selected_track_id=track_id)

                def _redo() -> None:
                    new_trimmed = self.library_store.trim_track(
                        track_id,
                        start_percent=start_value,
                        end_percent=end_value,
                    )
                    state["track_id"] = new_trimmed.id
                    self._reload_track_list(selected_track_id=new_trimmed.id)

                self._push_edit_command(_EditCommand(label="Trim track", undo=_undo, redo=_redo))
            except Exception as exc:
                QMessageBox.warning(self, "Trim track failed", str(exc))

    def _rerender_current_track_preview(self) -> bool:
        if self.track_list is None:
            if self._preview_folder_track_list_enabled:
                self._preview_visible_tracks_overview()
            else:
                self._show_select_track_placeholder()
            return False

        selected_items = [
            item
            for item in self.track_list.selectedItems()
            if item.data(TRACK_ID_ROLE) is not None
        ]
        if not selected_items:
            if self._preview_folder_track_list_enabled:
                self._preview_visible_tracks_overview()
            else:
                self._show_select_track_placeholder()
            return False

        if len(selected_items) == 1:
            self._open_track_preview(selected_items[0])
        else:
            self._open_selected_tracks_with_overlays(selected_items)
        return True

    def _push_edit_command(self, command: _EditCommand) -> None:
        self._undo_stack.append(command)
        self._redo_stack.clear()
        self._update_undo_redo_actions()

    def _update_undo_redo_actions(self) -> None:
        if self._undo_action is not None:
            self._undo_action.setEnabled(bool(self._undo_stack))
            if self._undo_stack:
                self._undo_action.setText(f"Undo {self._undo_stack[-1].label}")
            else:
                self._undo_action.setText("Undo")

        if self._redo_action is not None:
            self._redo_action.setEnabled(bool(self._redo_stack))
            if self._redo_stack:
                self._redo_action.setText(f"Redo {self._redo_stack[-1].label}")
            else:
                self._redo_action.setText("Redo")

    def _undo_last_edit(self) -> None:
        if not self._undo_stack:
            return

        command = self._undo_stack.pop()
        try:
            command.undo()
            self._redo_stack.append(command)
            self.statusBar().showMessage(f"Undid: {command.label}", 5000)
        except Exception as exc:
            QMessageBox.warning(self, "Undo failed", str(exc))
        finally:
            self._update_undo_redo_actions()

    def _redo_last_edit(self) -> None:
        if not self._redo_stack:
            return

        command = self._redo_stack.pop()
        try:
            command.redo()
            self._undo_stack.append(command)
            self.statusBar().showMessage(f"Redid: {command.label}", 5000)
        except Exception as exc:
            QMessageBox.warning(self, "Redo failed", str(exc))
        finally:
            self._update_undo_redo_actions()

    def _reverse_selected_tracks(self) -> None:
        track_ids = self._selected_track_ids()
        if len(track_ids) != 1:
            QMessageBox.information(self, "Reverse track", "Please select exactly one track.")
            return

        track_id = track_ids[0]
        try:
            preview_path = self.library_store.build_reverse_preview(track_id)
            self._preview_temp_track(preview_path, "Reverse preview")
        except Exception as exc:
            QMessageBox.warning(self, "Reverse preview failed", str(exc))
            return

        reply = QMessageBox.question(
            self,
            "Reverse track",
            "Apply reverse to the selected track?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._rerender_current_track_preview()
            return

        try:
            self.library_store.reverse_track(track_id)
            self._reload_track_list(selected_track_id=track_id)
            self._mark_preview_cache_dirty_for_ancestor_chain(self._selected_folder_id())
            self.statusBar().showMessage("Track reversed", 5000)

            def _undo() -> None:
                self.library_store.reverse_track(track_id)
                self._reload_track_list(selected_track_id=track_id)

            def _redo() -> None:
                self.library_store.reverse_track(track_id)
                self._reload_track_list(selected_track_id=track_id)

            self._push_edit_command(_EditCommand(label="Reverse track", undo=_undo, redo=_redo))
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
            preview_path = self.library_store.build_trim_preview(
                track_ids[0],
                start_percent=start_percent,
                end_percent=end_percent,
            )
            self._preview_temp_track(preview_path, "Trim preview")
        except Exception as exc:
            QMessageBox.warning(self, "Trim preview failed", str(exc))
            return

        reply = QMessageBox.question(
            self,
            "Trim track",
            "Apply trim and create a new track copy?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._rerender_current_track_preview()
            return

        try:
            source_track_id = track_ids[0]
            source_track = self.library_store.get_track(source_track_id)
            trimmed = self.library_store.trim_track(
                source_track_id,
                start_percent=start_percent,
                end_percent=end_percent,
            )
            self._reload_track_list(selected_track_id=trimmed.id)
            self._mark_preview_cache_dirty_for_ancestor_chain(source_track.folder_id)
            self.statusBar().showMessage(
                f"Created trimmed track: {trimmed.display_name}",
                6000,
            )

            state = {"track_id": trimmed.id}

            def _undo() -> None:
                self.library_store.move_track_to_trash(state["track_id"])
                self._reload_track_list(selected_track_id=source_track_id)

            def _redo() -> None:
                new_trimmed = self.library_store.trim_track(
                    source_track_id,
                    start_percent=start_percent,
                    end_percent=end_percent,
                )
                state["track_id"] = new_trimmed.id
                self._reload_track_list(selected_track_id=new_trimmed.id)

            self._push_edit_command(_EditCommand(label="Trim track", undo=_undo, redo=_redo))
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
            preview_a_path, preview_b_path = self.library_store.build_split_preview(
                track_ids[0],
                split_percent=split_percent,
            )
            self._preview_temp_track(preview_a_path, "Split preview (A)")
            if preview_b_path.exists():
                preview_b_path.unlink()
        except Exception as exc:
            QMessageBox.warning(self, "Split preview failed", str(exc))
            return

        reply = QMessageBox.question(
            self,
            "Split track",
            "Apply split and create two new track copies?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._rerender_current_track_preview()
            return

        try:
            source_track_id = track_ids[0]
            source_track = self.library_store.get_track(source_track_id)
            part_a, part_b = self.library_store.split_track(
                source_track_id,
                split_percent=split_percent,
            )
            self._reload_track_list(selected_track_id=part_a.id)
            self._mark_preview_cache_dirty_for_ancestor_chain(source_track.folder_id)
            self.statusBar().showMessage(
                f"Created split tracks: {part_a.display_name} and {part_b.display_name}",
                6000,
            )

            state = {"track_ids": [part_a.id, part_b.id]}

            def _undo() -> None:
                for track_id in state["track_ids"]:
                    self.library_store.move_track_to_trash(track_id)
                self._reload_track_list(selected_track_id=source_track_id)

            def _redo() -> None:
                new_a, new_b = self.library_store.split_track(
                    source_track_id,
                    split_percent=split_percent,
                )
                state["track_ids"] = [new_a.id, new_b.id]
                self._reload_track_list(selected_track_id=new_a.id)

            self._push_edit_command(_EditCommand(label="Split track", undo=_undo, redo=_redo))
        except Exception as exc:
            QMessageBox.warning(self, "Split track failed", str(exc))

    def _merge_selected_tracks(self) -> None:
        track_ids = self._selected_track_ids()
        if len(track_ids) < 2:
            QMessageBox.information(self, "Merge tracks", "Please select at least two tracks.")
            return

        try:
            preview_path = self.library_store.build_merge_preview(track_ids)
            self._preview_temp_track(preview_path, "Merge preview")
        except Exception as exc:
            QMessageBox.warning(self, "Merge preview failed", str(exc))
            return

        reply = QMessageBox.question(
            self,
            "Merge tracks",
            f"Create a merged copy from {len(track_ids)} selected tracks?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._rerender_current_track_preview()
            return

        try:
            source_track_ids = list(track_ids)
            source_track = self.library_store.get_track(source_track_ids[0])
            merged = self.library_store.merge_tracks(source_track_ids)
            self._reload_track_list(selected_track_id=merged.id)
            self._mark_preview_cache_dirty_for_ancestor_chain(source_track.folder_id)
            self.statusBar().showMessage(
                f"Created merged track: {merged.display_name}",
                6000,
            )

            state = {"track_id": merged.id}

            def _undo() -> None:
                self.library_store.move_track_to_trash(state["track_id"])
                self._reload_track_list(selected_track_id=source_track_ids[0])

            def _redo() -> None:
                new_merged = self.library_store.merge_tracks(source_track_ids)
                state["track_id"] = new_merged.id
                self._reload_track_list(selected_track_id=new_merged.id)

            self._push_edit_command(_EditCommand(label="Merge tracks", undo=_undo, redo=_redo))
        except Exception as exc:
            QMessageBox.warning(self, "Merge tracks failed", str(exc))

    def _create_folder_dialog(self) -> None:
        parent_id = self._selected_folder_id()
        text, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok:
            return

        try:
            self.library_store.create_folder(text, parent_id=parent_id)
            self._load_library_tree(selected_folder_id=parent_id)
            self._mark_preview_cache_dirty_for_ancestor_chain(parent_id)
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
            self._mark_all_preview_cache_dirty()
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
            self._mark_all_preview_cache_dirty()
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
            track = self.library_store.get_track(track_ids[0])
            self.library_store.rename_track(track_ids[0], text)
            self._reload_track_list()
            self._mark_preview_cache_dirty_for_ancestor_chain(track.folder_id)
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
        affected_folder_ids: set[int] = set()
        for track_id in track_ids:
            try:
                track = self.library_store.get_track(track_id)
                affected_folder_ids.add(track.folder_id)
                if in_trash:
                    self.library_store.purge_track(track_id)
                else:
                    self.library_store.move_track_to_trash(track_id)
                    affected_folder_ids.add(self.library_store.get_trash_folder_id())
            except Exception as exc:
                failures.append(str(exc))

        self._reload_track_list()
        for folder_id in affected_folder_ids:
            self._mark_preview_cache_dirty_for_ancestor_chain(folder_id)
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
            self._mark_all_preview_cache_dirty()
            self.statusBar().showMessage("Folder moved", 4000)
        except Exception as exc:
            self._load_library_tree(selected_folder_id=folder_id)
            QMessageBox.warning(self, "Move folder failed", str(exc))

    def _move_tracks_to_folder(self, track_ids: list[int], folder_id: int) -> None:
        failures: list[str] = []
        source_folder_ids: set[int] = set()
        for track_id in track_ids:
            try:
                track = self.library_store.get_track(track_id)
                source_folder_ids.add(track.folder_id)
                self.library_store.move_track_to_folder(track_id, folder_id)
            except Exception as exc:
                failures.append(str(exc))

        self._load_library_tree(selected_folder_id=folder_id)
        self._reload_track_list()
        self._mark_preview_cache_dirty_for_ancestor_chain(folder_id)
        for source_folder_id in source_folder_ids:
            self._mark_preview_cache_dirty_for_ancestor_chain(source_folder_id)

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

    def closeEvent(self, event) -> None:  # pragma: no cover - GUI behavior
        if self._keep_window_configuration_enabled:
            set_window_size(self.width(), self.height())
            if self._main_splitter is not None:
                set_window_splitter_sizes(self._main_splitter.sizes())

        if self._keep_folder_tree_structure_enabled:
            set_window_folder_tree_expanded_ids(sorted(self._expanded_folder_ids))
        else:
            set_window_folder_tree_expanded_ids([])

        if self._keep_last_track_shown_enabled:
            set_window_last_track_id(self._current_selected_track_id())
        else:
            set_window_last_track_id(None)

        super().closeEvent(event)

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

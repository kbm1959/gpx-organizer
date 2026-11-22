"""Settings persistence for application-level configuration."""

from __future__ import annotations

import json
from pathlib import Path
import re

from .config import get_app_paths
from .time_utils import DEFAULT_TIME_ZONE, normalize_time_zone


DEFAULT_SETTINGS = {
    "library_root": "",
    "time_zone": DEFAULT_TIME_ZONE,
    "map_responsive_threshold_px": "900",
    "map_rest_stop_color": "#AB47BC",
    "map_rest_stop_size_px": "6",
    "map_default_track_color": "#007F5F",
    "map_preview_lightening_factor": "0.0",
    "map_distance_marker_color": "#37474F",
    "map_distance_marker_border_color": "#FF0000",
    "map_distance_marker_size_px": "5",
    "map_start_symbol_color": "#2E7D32",
    "map_start_symbol_size_px": "12",
    "map_start_symbol_shape": "square",
    "map_stop_symbol_color": "#C62828",
    "map_stop_symbol_size_px": "12",
    "map_stop_symbol_shape": "square",
    "map_direction_arrow_color": "#1F1F1F",
    "map_direction_arrow_count": "10",
    "map_direction_arrow_size_px": "12",
    "map_track_point_color": "#000000",
    "map_track_point_size_px": "1",
    "window_preview_folder_track_list": "1",
    "window_keep_configuration": "1",
    "window_keep_folder_tree_structure": "1",
    "window_keep_last_track_shown": "1",
    "window_tracks_first_then_waypoints": "0",
    "window_min_distance_per_track_point_m": "2.0",
    "track_rest_radius_m": "2.0",
    "track_rest_min_duration_s": "60",
    "track_rest_endpoint_distance_multiplier": "10",
    "window_drag_preview_opacity_percent": "90",
    "window_import_progress_min_gpx_files": "10",
    "window_subfolder_separator_color": "#6E6E6E",
    "window_subfolder_separator_opacity_percent": "70",
    "window_size": "1400,840",
    "window_splitter_sizes": "",
    "window_library_splitter_sizes": "",
    "window_folder_tree_expanded_ids": "",
    "window_last_track_id": "",
    "window_last_folder_id": "",
}

MIN_MAP_RESPONSIVE_THRESHOLD_PX = 320
MAX_MAP_RESPONSIVE_THRESHOLD_PX = 2000
DEFAULT_MAP_RESPONSIVE_THRESHOLD_PX = 900
DEFAULT_MAP_REST_STOP_COLOR = "#AB47BC"
DEFAULT_MAP_REST_STOP_SIZE_PX = 6
MIN_MAP_REST_STOP_SIZE_PX = 2
MAX_MAP_REST_STOP_SIZE_PX = 24
DEFAULT_MAP_DEFAULT_TRACK_COLOR = "#007F5F"
DEFAULT_MAP_PREVIEW_LIGHTENING_FACTOR = 0.0
MIN_MAP_PREVIEW_LIGHTENING_FACTOR = 0.0
MAX_MAP_PREVIEW_LIGHTENING_FACTOR = 1.0
DEFAULT_MAP_DISTANCE_MARKER_COLOR = "#37474F"
DEFAULT_MAP_DISTANCE_MARKER_BORDER_COLOR = "#FF0000"
DEFAULT_MAP_DISTANCE_MARKER_SIZE_PX = 5
MIN_MAP_DISTANCE_MARKER_SIZE_PX = 2
MAX_MAP_DISTANCE_MARKER_SIZE_PX = 24
DEFAULT_MAP_START_SYMBOL_COLOR = "#2E7D32"
DEFAULT_MAP_START_SYMBOL_SIZE_PX = 12
DEFAULT_MAP_START_SYMBOL_SHAPE = "square"
DEFAULT_MAP_STOP_SYMBOL_COLOR = "#C62828"
DEFAULT_MAP_STOP_SYMBOL_SIZE_PX = 12
DEFAULT_MAP_STOP_SYMBOL_SHAPE = "square"
MIN_MAP_ENDPOINT_SYMBOL_SIZE_PX = 4
MAX_MAP_ENDPOINT_SYMBOL_SIZE_PX = 40
MAP_ENDPOINT_SYMBOL_SHAPES = {"circle", "square"}
DEFAULT_MAP_DIRECTION_ARROW_COLOR = "#1F1F1F"
DEFAULT_MAP_DIRECTION_ARROW_COUNT = 10
MIN_MAP_DIRECTION_ARROW_COUNT = 1
MAX_MAP_DIRECTION_ARROW_COUNT = 200
DEFAULT_MAP_DIRECTION_ARROW_SIZE_PX = 12
MIN_MAP_DIRECTION_ARROW_SIZE_PX = 8
MAX_MAP_DIRECTION_ARROW_SIZE_PX = 40
DEFAULT_MAP_TRACK_POINT_COLOR = "#000000"
DEFAULT_MAP_TRACK_POINT_SIZE_PX = 1
MIN_MAP_TRACK_POINT_SIZE_PX = 1
MAX_MAP_TRACK_POINT_SIZE_PX = 10
DEFAULT_WINDOW_PREVIEW_FOLDER_TRACK_LIST = True
DEFAULT_WINDOW_KEEP_CONFIGURATION = True
DEFAULT_WINDOW_KEEP_FOLDER_TREE_STRUCTURE = True
DEFAULT_WINDOW_KEEP_LAST_TRACK_SHOWN = True
DEFAULT_WINDOW_TRACKS_FIRST_THEN_WAYPOINTS = False
DEFAULT_WINDOW_MIN_DISTANCE_PER_TRACK_POINT_M = 2.0
MIN_WINDOW_MIN_DISTANCE_PER_TRACK_POINT_M = 0.0
MAX_WINDOW_MIN_DISTANCE_PER_TRACK_POINT_M = 1000.0
DEFAULT_TRACK_REST_RADIUS_M = 2.0
MIN_TRACK_REST_RADIUS_M = 0.1
MAX_TRACK_REST_RADIUS_M = 1000.0
DEFAULT_TRACK_REST_MIN_DURATION_S = 60.0
MIN_TRACK_REST_MIN_DURATION_S = 1.0
MAX_TRACK_REST_MIN_DURATION_S = 86400.0
DEFAULT_TRACK_REST_ENDPOINT_DISTANCE_MULTIPLIER = 10.0
MIN_TRACK_REST_ENDPOINT_DISTANCE_MULTIPLIER = 1.0
MAX_TRACK_REST_ENDPOINT_DISTANCE_MULTIPLIER = 1000.0
DEFAULT_WINDOW_DRAG_PREVIEW_OPACITY_PERCENT = 90
MIN_WINDOW_DRAG_PREVIEW_OPACITY_PERCENT = 10
MAX_WINDOW_DRAG_PREVIEW_OPACITY_PERCENT = 100
DEFAULT_WINDOW_IMPORT_PROGRESS_MIN_GPX_FILES = 10
MIN_WINDOW_IMPORT_PROGRESS_MIN_GPX_FILES = 0
MAX_WINDOW_IMPORT_PROGRESS_MIN_GPX_FILES = 100000
DEFAULT_WINDOW_SUBFOLDER_SEPARATOR_COLOR = "#6E6E6E"
DEFAULT_WINDOW_SUBFOLDER_SEPARATOR_OPACITY_PERCENT = 70
MIN_WINDOW_SUBFOLDER_SEPARATOR_OPACITY_PERCENT = 10
MAX_WINDOW_SUBFOLDER_SEPARATOR_OPACITY_PERCENT = 100
DEFAULT_WINDOW_WIDTH = 1400
DEFAULT_WINDOW_HEIGHT = 840
MIN_WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 480

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def load_settings() -> dict[str, str]:
    """Load app settings from JSON file, returning defaults on first run."""
    paths = get_app_paths()
    if not paths.config_file.exists():
        return dict(DEFAULT_SETTINGS)

    raw = json.loads(paths.config_file.read_text(encoding="utf-8"))
    settings = dict(DEFAULT_SETTINGS)
    settings.update({k: str(v) for k, v in raw.items()})
    return settings


def save_settings(settings: dict[str, str]) -> None:
    """Persist app settings to JSON file."""
    paths = get_app_paths()
    paths.base_dir.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text(
        json.dumps(settings, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def get_or_create_library_root() -> Path:
    """Resolve and persist the default managed library root path."""
    settings = load_settings()
    configured = settings.get("library_root", "").strip()

    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        root = get_app_paths().base_dir / "library"
        settings["library_root"] = str(root)
        save_settings(settings)

    root.mkdir(parents=True, exist_ok=True)
    return root


def set_library_root(root: Path) -> Path:
    """Persist the selected library root path and ensure the directory exists."""
    resolved = root.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)

    settings = load_settings()
    settings["library_root"] = str(resolved)
    save_settings(settings)
    return resolved


def get_time_zone() -> str:
    return normalize_time_zone(load_settings().get("time_zone", DEFAULT_TIME_ZONE))


def set_time_zone(value: str) -> str:
    time_zone = normalize_time_zone(value)
    settings = load_settings()
    settings["time_zone"] = time_zone
    save_settings(settings)
    return time_zone


def get_map_responsive_threshold_px() -> int:
    """Read the responsive threshold used by the map UI overlays."""
    settings = load_settings()
    raw = settings.get("map_responsive_threshold_px", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_MAP_RESPONSIVE_THRESHOLD_PX

    return max(MIN_MAP_RESPONSIVE_THRESHOLD_PX, min(MAX_MAP_RESPONSIVE_THRESHOLD_PX, value))


def set_map_responsive_threshold_px(value: int) -> int:
    """Persist the responsive threshold used by the map UI overlays."""
    threshold_px = max(
        MIN_MAP_RESPONSIVE_THRESHOLD_PX,
        min(MAX_MAP_RESPONSIVE_THRESHOLD_PX, int(value)),
    )

    settings = load_settings()
    settings["map_responsive_threshold_px"] = str(threshold_px)
    save_settings(settings)
    return threshold_px


def get_map_rest_stop_color() -> str:
    settings = load_settings()
    return _normalize_hex_color(
        settings.get("map_rest_stop_color", ""),
        DEFAULT_MAP_REST_STOP_COLOR,
    )


def set_map_rest_stop_color(value: str) -> str:
    color = _normalize_hex_color(value, DEFAULT_MAP_REST_STOP_COLOR)
    settings = load_settings()
    settings["map_rest_stop_color"] = color
    save_settings(settings)
    return color


def get_map_rest_stop_size_px() -> int:
    settings = load_settings()
    raw = settings.get("map_rest_stop_size_px", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_MAP_REST_STOP_SIZE_PX

    return max(MIN_MAP_REST_STOP_SIZE_PX, min(MAX_MAP_REST_STOP_SIZE_PX, value))


def set_map_rest_stop_size_px(value: int) -> int:
    size_px = max(MIN_MAP_REST_STOP_SIZE_PX, min(MAX_MAP_REST_STOP_SIZE_PX, int(value)))
    settings = load_settings()
    settings["map_rest_stop_size_px"] = str(size_px)
    save_settings(settings)
    return size_px


def get_map_default_track_color() -> str:
    settings = load_settings()
    return _normalize_hex_color(
        settings.get("map_default_track_color", ""),
        DEFAULT_MAP_DEFAULT_TRACK_COLOR,
    )


def set_map_default_track_color(value: str) -> str:
    color = _normalize_hex_color(value, DEFAULT_MAP_DEFAULT_TRACK_COLOR)
    settings = load_settings()
    settings["map_default_track_color"] = color
    save_settings(settings)
    return color


def get_map_preview_lightening_factor() -> float:
    settings = load_settings()
    raw = settings.get("map_preview_lightening_factor", "").strip()
    try:
        value = float(raw)
    except ValueError:
        value = DEFAULT_MAP_PREVIEW_LIGHTENING_FACTOR

    return max(
        MIN_MAP_PREVIEW_LIGHTENING_FACTOR,
        min(MAX_MAP_PREVIEW_LIGHTENING_FACTOR, value),
    )


def set_map_preview_lightening_factor(value: float) -> float:
    factor = max(
        MIN_MAP_PREVIEW_LIGHTENING_FACTOR,
        min(MAX_MAP_PREVIEW_LIGHTENING_FACTOR, float(value)),
    )
    settings = load_settings()
    settings["map_preview_lightening_factor"] = f"{factor:.2f}"
    save_settings(settings)
    return factor


def get_map_distance_marker_color() -> str:
    settings = load_settings()
    return _normalize_hex_color(
        settings.get("map_distance_marker_color", ""),
        DEFAULT_MAP_DISTANCE_MARKER_COLOR,
    )


def set_map_distance_marker_color(value: str) -> str:
    color = _normalize_hex_color(value, DEFAULT_MAP_DISTANCE_MARKER_COLOR)
    settings = load_settings()
    settings["map_distance_marker_color"] = color
    save_settings(settings)
    return color


def get_map_distance_marker_border_color() -> str:
    settings = load_settings()
    return _normalize_hex_color(
        settings.get("map_distance_marker_border_color", ""),
        DEFAULT_MAP_DISTANCE_MARKER_BORDER_COLOR,
    )


def set_map_distance_marker_border_color(value: str) -> str:
    color = _normalize_hex_color(value, DEFAULT_MAP_DISTANCE_MARKER_BORDER_COLOR)
    settings = load_settings()
    settings["map_distance_marker_border_color"] = color
    save_settings(settings)
    return color


def get_map_distance_marker_size_px() -> int:
    settings = load_settings()
    raw = settings.get("map_distance_marker_size_px", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_MAP_DISTANCE_MARKER_SIZE_PX

    return max(MIN_MAP_DISTANCE_MARKER_SIZE_PX, min(MAX_MAP_DISTANCE_MARKER_SIZE_PX, value))


def set_map_distance_marker_size_px(value: int) -> int:
    size_px = max(
        MIN_MAP_DISTANCE_MARKER_SIZE_PX,
        min(MAX_MAP_DISTANCE_MARKER_SIZE_PX, int(value)),
    )
    settings = load_settings()
    settings["map_distance_marker_size_px"] = str(size_px)
    save_settings(settings)
    return size_px


def get_map_start_symbol_color() -> str:
    settings = load_settings()
    return _normalize_hex_color(
        settings.get("map_start_symbol_color", ""),
        DEFAULT_MAP_START_SYMBOL_COLOR,
    )


def set_map_start_symbol_color(value: str) -> str:
    color = _normalize_hex_color(value, DEFAULT_MAP_START_SYMBOL_COLOR)
    settings = load_settings()
    settings["map_start_symbol_color"] = color
    save_settings(settings)
    return color


def get_map_start_symbol_size_px() -> int:
    settings = load_settings()
    raw = settings.get("map_start_symbol_size_px", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_MAP_START_SYMBOL_SIZE_PX

    return max(MIN_MAP_ENDPOINT_SYMBOL_SIZE_PX, min(MAX_MAP_ENDPOINT_SYMBOL_SIZE_PX, value))


def set_map_start_symbol_size_px(value: int) -> int:
    size_px = max(
        MIN_MAP_ENDPOINT_SYMBOL_SIZE_PX,
        min(MAX_MAP_ENDPOINT_SYMBOL_SIZE_PX, int(value)),
    )
    settings = load_settings()
    settings["map_start_symbol_size_px"] = str(size_px)
    save_settings(settings)
    return size_px


def get_map_start_symbol_shape() -> str:
    settings = load_settings()
    raw = settings.get("map_start_symbol_shape", "").strip().lower()
    if raw in MAP_ENDPOINT_SYMBOL_SHAPES:
        return raw
    return DEFAULT_MAP_START_SYMBOL_SHAPE


def set_map_start_symbol_shape(value: str) -> str:
    normalized = value.strip().lower()
    shape = normalized if normalized in MAP_ENDPOINT_SYMBOL_SHAPES else DEFAULT_MAP_START_SYMBOL_SHAPE
    settings = load_settings()
    settings["map_start_symbol_shape"] = shape
    save_settings(settings)
    return shape


def get_map_stop_symbol_color() -> str:
    settings = load_settings()
    return _normalize_hex_color(
        settings.get("map_stop_symbol_color", ""),
        DEFAULT_MAP_STOP_SYMBOL_COLOR,
    )


def set_map_stop_symbol_color(value: str) -> str:
    color = _normalize_hex_color(value, DEFAULT_MAP_STOP_SYMBOL_COLOR)
    settings = load_settings()
    settings["map_stop_symbol_color"] = color
    save_settings(settings)
    return color


def get_map_stop_symbol_size_px() -> int:
    settings = load_settings()
    raw = settings.get("map_stop_symbol_size_px", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_MAP_STOP_SYMBOL_SIZE_PX

    return max(MIN_MAP_ENDPOINT_SYMBOL_SIZE_PX, min(MAX_MAP_ENDPOINT_SYMBOL_SIZE_PX, value))


def set_map_stop_symbol_size_px(value: int) -> int:
    size_px = max(
        MIN_MAP_ENDPOINT_SYMBOL_SIZE_PX,
        min(MAX_MAP_ENDPOINT_SYMBOL_SIZE_PX, int(value)),
    )
    settings = load_settings()
    settings["map_stop_symbol_size_px"] = str(size_px)
    save_settings(settings)
    return size_px


def get_map_stop_symbol_shape() -> str:
    settings = load_settings()
    raw = settings.get("map_stop_symbol_shape", "").strip().lower()
    if raw in MAP_ENDPOINT_SYMBOL_SHAPES:
        return raw
    return DEFAULT_MAP_STOP_SYMBOL_SHAPE


def set_map_stop_symbol_shape(value: str) -> str:
    normalized = value.strip().lower()
    shape = normalized if normalized in MAP_ENDPOINT_SYMBOL_SHAPES else DEFAULT_MAP_STOP_SYMBOL_SHAPE
    settings = load_settings()
    settings["map_stop_symbol_shape"] = shape
    save_settings(settings)
    return shape


def get_map_direction_arrow_color() -> str:
    settings = load_settings()
    return _normalize_hex_color(
        settings.get("map_direction_arrow_color", ""),
        DEFAULT_MAP_DIRECTION_ARROW_COLOR,
    )


def set_map_direction_arrow_color(value: str) -> str:
    color = _normalize_hex_color(value, DEFAULT_MAP_DIRECTION_ARROW_COLOR)
    settings = load_settings()
    settings["map_direction_arrow_color"] = color
    save_settings(settings)
    return color


def get_map_direction_arrow_count() -> int:
    settings = load_settings()
    raw = settings.get("map_direction_arrow_count", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_MAP_DIRECTION_ARROW_COUNT

    return max(
        MIN_MAP_DIRECTION_ARROW_COUNT,
        min(MAX_MAP_DIRECTION_ARROW_COUNT, value),
    )


def set_map_direction_arrow_count(value: int) -> int:
    arrow_count = max(
        MIN_MAP_DIRECTION_ARROW_COUNT,
        min(MAX_MAP_DIRECTION_ARROW_COUNT, int(value)),
    )

    settings = load_settings()
    settings["map_direction_arrow_count"] = str(arrow_count)
    save_settings(settings)
    return arrow_count


def get_map_direction_arrow_size_px() -> int:
    settings = load_settings()
    raw = settings.get("map_direction_arrow_size_px", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_MAP_DIRECTION_ARROW_SIZE_PX

    return max(MIN_MAP_DIRECTION_ARROW_SIZE_PX, min(MAX_MAP_DIRECTION_ARROW_SIZE_PX, value))


def set_map_direction_arrow_size_px(value: int) -> int:
    size_px = max(MIN_MAP_DIRECTION_ARROW_SIZE_PX, min(MAX_MAP_DIRECTION_ARROW_SIZE_PX, int(value)))
    settings = load_settings()
    settings["map_direction_arrow_size_px"] = str(size_px)
    save_settings(settings)
    return size_px


def get_map_track_point_color() -> str:
    settings = load_settings()
    return _normalize_hex_color(
        settings.get("map_track_point_color", ""),
        DEFAULT_MAP_TRACK_POINT_COLOR,
    )


def set_map_track_point_color(value: str) -> str:
    color = _normalize_hex_color(value, DEFAULT_MAP_TRACK_POINT_COLOR)
    settings = load_settings()
    settings["map_track_point_color"] = color
    save_settings(settings)
    return color


def get_map_track_point_size_px() -> int:
    settings = load_settings()
    raw = settings.get("map_track_point_size_px", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_MAP_TRACK_POINT_SIZE_PX

    return max(MIN_MAP_TRACK_POINT_SIZE_PX, min(MAX_MAP_TRACK_POINT_SIZE_PX, value))


def set_map_track_point_size_px(value: int) -> int:
    size_px = max(MIN_MAP_TRACK_POINT_SIZE_PX, min(MAX_MAP_TRACK_POINT_SIZE_PX, int(value)))
    settings = load_settings()
    settings["map_track_point_size_px"] = str(size_px)
    save_settings(settings)
    return size_px


def get_window_preview_folder_track_list_enabled() -> bool:
    settings = load_settings()
    return _to_bool(
        settings.get("window_preview_folder_track_list", ""),
        DEFAULT_WINDOW_PREVIEW_FOLDER_TRACK_LIST,
    )


def set_window_preview_folder_track_list_enabled(enabled: bool) -> bool:
    value = bool(enabled)
    settings = load_settings()
    settings["window_preview_folder_track_list"] = "1" if value else "0"
    save_settings(settings)
    return value


def get_window_keep_configuration_enabled() -> bool:
    settings = load_settings()
    return _to_bool(
        settings.get("window_keep_configuration", ""),
        DEFAULT_WINDOW_KEEP_CONFIGURATION,
    )


def set_window_keep_configuration_enabled(enabled: bool) -> bool:
    value = bool(enabled)
    settings = load_settings()
    settings["window_keep_configuration"] = "1" if value else "0"
    save_settings(settings)
    return value


def get_window_keep_folder_tree_structure_enabled() -> bool:
    settings = load_settings()
    return _to_bool(
        settings.get("window_keep_folder_tree_structure", ""),
        DEFAULT_WINDOW_KEEP_FOLDER_TREE_STRUCTURE,
    )


def set_window_keep_folder_tree_structure_enabled(enabled: bool) -> bool:
    value = bool(enabled)
    settings = load_settings()
    settings["window_keep_folder_tree_structure"] = "1" if value else "0"
    save_settings(settings)
    return value


def get_window_keep_last_track_shown_enabled() -> bool:
    settings = load_settings()
    return _to_bool(
        settings.get("window_keep_last_track_shown", ""),
        DEFAULT_WINDOW_KEEP_LAST_TRACK_SHOWN,
    )


def set_window_keep_last_track_shown_enabled(enabled: bool) -> bool:
    value = bool(enabled)
    settings = load_settings()
    settings["window_keep_last_track_shown"] = "1" if value else "0"
    save_settings(settings)
    return value


def get_window_tracks_first_then_waypoints_enabled() -> bool:
    settings = load_settings()
    return _to_bool(
        settings.get("window_tracks_first_then_waypoints", ""),
        DEFAULT_WINDOW_TRACKS_FIRST_THEN_WAYPOINTS,
    )


def set_window_tracks_first_then_waypoints_enabled(enabled: bool) -> bool:
    value = bool(enabled)
    settings = load_settings()
    settings["window_tracks_first_then_waypoints"] = "1" if value else "0"
    save_settings(settings)
    return value


def get_window_min_distance_per_track_point_m() -> float:
    settings = load_settings()
    try:
        value = float(settings.get("window_min_distance_per_track_point_m", ""))
    except ValueError:
        value = DEFAULT_WINDOW_MIN_DISTANCE_PER_TRACK_POINT_M
    return max(0.0, min(1000.0, value))


def set_window_min_distance_per_track_point_m(value: float) -> float:
    normalized = max(0.0, min(1000.0, float(value)))
    settings = load_settings()
    settings["window_min_distance_per_track_point_m"] = str(normalized)
    save_settings(settings)
    return normalized


def get_track_rest_radius_m() -> float:
    settings = load_settings()
    try:
        value = float(settings.get("track_rest_radius_m", ""))
    except ValueError:
        value = DEFAULT_TRACK_REST_RADIUS_M
    return max(MIN_TRACK_REST_RADIUS_M, min(MAX_TRACK_REST_RADIUS_M, value))


def set_track_rest_radius_m(value: float) -> float:
    normalized = max(MIN_TRACK_REST_RADIUS_M, min(MAX_TRACK_REST_RADIUS_M, float(value)))
    settings = load_settings()
    settings["track_rest_radius_m"] = str(normalized)
    save_settings(settings)
    return normalized


def get_track_rest_min_duration_s() -> float:
    settings = load_settings()
    try:
        value = float(settings.get("track_rest_min_duration_s", ""))
    except ValueError:
        value = DEFAULT_TRACK_REST_MIN_DURATION_S
    return max(MIN_TRACK_REST_MIN_DURATION_S, min(MAX_TRACK_REST_MIN_DURATION_S, value))


def set_track_rest_min_duration_s(value: float) -> float:
    normalized = max(
        MIN_TRACK_REST_MIN_DURATION_S,
        min(MAX_TRACK_REST_MIN_DURATION_S, float(value)),
    )
    settings = load_settings()
    settings["track_rest_min_duration_s"] = str(normalized)
    save_settings(settings)
    return normalized


def get_track_rest_endpoint_distance_multiplier() -> float:
    settings = load_settings()
    try:
        value = float(settings.get("track_rest_endpoint_distance_multiplier", ""))
    except ValueError:
        value = DEFAULT_TRACK_REST_ENDPOINT_DISTANCE_MULTIPLIER
    return max(
        MIN_TRACK_REST_ENDPOINT_DISTANCE_MULTIPLIER,
        min(MAX_TRACK_REST_ENDPOINT_DISTANCE_MULTIPLIER, value),
    )


def set_track_rest_endpoint_distance_multiplier(value: float) -> float:
    normalized = max(
        MIN_TRACK_REST_ENDPOINT_DISTANCE_MULTIPLIER,
        min(MAX_TRACK_REST_ENDPOINT_DISTANCE_MULTIPLIER, float(value)),
    )
    settings = load_settings()
    settings["track_rest_endpoint_distance_multiplier"] = str(normalized)
    save_settings(settings)
    return normalized


def get_window_min_distance_per_track_point_m() -> float:
    settings = load_settings()
    try:
        value = float(settings.get("window_min_distance_per_track_point_m", ""))
    except ValueError:
        value = DEFAULT_WINDOW_MIN_DISTANCE_PER_TRACK_POINT_M
    return max(
        MIN_WINDOW_MIN_DISTANCE_PER_TRACK_POINT_M,
        min(MAX_WINDOW_MIN_DISTANCE_PER_TRACK_POINT_M, value),
    )


def set_window_min_distance_per_track_point_m(value: float) -> float:
    normalized = max(
        MIN_WINDOW_MIN_DISTANCE_PER_TRACK_POINT_M,
        min(MAX_WINDOW_MIN_DISTANCE_PER_TRACK_POINT_M, float(value)),
    )
    settings = load_settings()
    settings["window_min_distance_per_track_point_m"] = str(normalized)
    save_settings(settings)
    return normalized


def get_window_drag_preview_opacity_percent() -> int:
    settings = load_settings()
    raw = settings.get("window_drag_preview_opacity_percent", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_WINDOW_DRAG_PREVIEW_OPACITY_PERCENT

    return max(
        MIN_WINDOW_DRAG_PREVIEW_OPACITY_PERCENT,
        min(MAX_WINDOW_DRAG_PREVIEW_OPACITY_PERCENT, value),
    )


def set_window_drag_preview_opacity_percent(value: int) -> int:
    normalized = max(
        MIN_WINDOW_DRAG_PREVIEW_OPACITY_PERCENT,
        min(MAX_WINDOW_DRAG_PREVIEW_OPACITY_PERCENT, int(value)),
    )
    settings = load_settings()
    settings["window_drag_preview_opacity_percent"] = str(normalized)
    save_settings(settings)
    return normalized


def get_window_import_progress_min_gpx_files() -> int:
    settings = load_settings()
    raw = settings.get("window_import_progress_min_gpx_files", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_WINDOW_IMPORT_PROGRESS_MIN_GPX_FILES

    return max(
        MIN_WINDOW_IMPORT_PROGRESS_MIN_GPX_FILES,
        min(MAX_WINDOW_IMPORT_PROGRESS_MIN_GPX_FILES, value),
    )


def set_window_import_progress_min_gpx_files(value: int) -> int:
    normalized = max(
        MIN_WINDOW_IMPORT_PROGRESS_MIN_GPX_FILES,
        min(MAX_WINDOW_IMPORT_PROGRESS_MIN_GPX_FILES, int(value)),
    )
    settings = load_settings()
    settings["window_import_progress_min_gpx_files"] = str(normalized)
    save_settings(settings)
    return normalized


def get_window_subfolder_separator_color() -> str:
    settings = load_settings()
    return _normalize_hex_color(
        settings.get("window_subfolder_separator_color", ""),
        DEFAULT_WINDOW_SUBFOLDER_SEPARATOR_COLOR,
    )


def set_window_subfolder_separator_color(value: str) -> str:
    color = _normalize_hex_color(value, DEFAULT_WINDOW_SUBFOLDER_SEPARATOR_COLOR)
    settings = load_settings()
    settings["window_subfolder_separator_color"] = color
    save_settings(settings)
    return color


def get_window_subfolder_separator_opacity_percent() -> int:
    settings = load_settings()
    raw = settings.get("window_subfolder_separator_opacity_percent", "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_WINDOW_SUBFOLDER_SEPARATOR_OPACITY_PERCENT

    return max(
        MIN_WINDOW_SUBFOLDER_SEPARATOR_OPACITY_PERCENT,
        min(MAX_WINDOW_SUBFOLDER_SEPARATOR_OPACITY_PERCENT, value),
    )


def set_window_subfolder_separator_opacity_percent(value: int) -> int:
    normalized = max(
        MIN_WINDOW_SUBFOLDER_SEPARATOR_OPACITY_PERCENT,
        min(MAX_WINDOW_SUBFOLDER_SEPARATOR_OPACITY_PERCENT, int(value)),
    )
    settings = load_settings()
    settings["window_subfolder_separator_opacity_percent"] = str(normalized)
    save_settings(settings)
    return normalized


def get_window_size() -> tuple[int, int]:
    settings = load_settings()
    raw = settings.get("window_size", "").strip()
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != 2:
        return (DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return (DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

    width = max(MIN_WINDOW_WIDTH, width)
    height = max(MIN_WINDOW_HEIGHT, height)
    return (width, height)


def set_window_size(width: int, height: int) -> tuple[int, int]:
    stored_width = max(MIN_WINDOW_WIDTH, int(width))
    stored_height = max(MIN_WINDOW_HEIGHT, int(height))
    settings = load_settings()
    settings["window_size"] = f"{stored_width},{stored_height}"
    save_settings(settings)
    return (stored_width, stored_height)


def get_window_splitter_sizes() -> list[int]:
    settings = load_settings()
    raw = settings.get("window_splitter_sizes", "").strip()
    if not raw:
        return []

    result: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            continue
        if value > 0:
            result.append(value)
    return result


def set_window_splitter_sizes(sizes: list[int]) -> list[int]:
    normalized: list[int] = []
    for size in sizes:
        value = int(size)
        if value > 0:
            normalized.append(value)

    settings = load_settings()
    settings["window_splitter_sizes"] = ",".join(str(value) for value in normalized)
    save_settings(settings)
    return normalized


def get_window_library_splitter_sizes() -> list[int]:
    settings = load_settings()
    raw = settings.get("window_library_splitter_sizes", "").strip()
    if not raw:
        return []

    result: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            continue
        if value > 0:
            result.append(value)
    return result


def set_window_library_splitter_sizes(sizes: list[int]) -> list[int]:
    normalized: list[int] = []
    for size in sizes:
        value = int(size)
        if value > 0:
            normalized.append(value)

    settings = load_settings()
    settings["window_library_splitter_sizes"] = ",".join(str(value) for value in normalized)
    save_settings(settings)
    return normalized


def get_window_folder_tree_expanded_ids() -> list[int]:
    settings = load_settings()
    raw = settings.get("window_folder_tree_expanded_ids", "").strip()
    if not raw:
        return []

    ids: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            continue
    return ids


def set_window_folder_tree_expanded_ids(folder_ids: list[int]) -> list[int]:
    normalized = sorted({int(folder_id) for folder_id in folder_ids})
    settings = load_settings()
    settings["window_folder_tree_expanded_ids"] = ",".join(str(folder_id) for folder_id in normalized)
    save_settings(settings)
    return normalized


def get_window_last_track_id() -> int | None:
    settings = load_settings()
    raw = settings.get("window_last_track_id", "").strip()
    if not raw:
        return None

    try:
        return int(raw)
    except ValueError:
        return None


def set_window_last_track_id(track_id: int | None) -> int | None:
    settings = load_settings()
    if track_id is None:
        settings["window_last_track_id"] = ""
        save_settings(settings)
        return None

    stored = int(track_id)
    settings["window_last_track_id"] = str(stored)
    save_settings(settings)
    return stored


def get_window_last_folder_id() -> int | None:
    settings = load_settings()
    raw = settings.get("window_last_folder_id", "").strip()
    if not raw:
        return None

    try:
        return int(raw)
    except ValueError:
        return None


def set_window_last_folder_id(folder_id: int | None) -> int | None:
    settings = load_settings()
    if folder_id is None:
        settings["window_last_folder_id"] = ""
        save_settings(settings)
        return None

    stored = int(folder_id)
    settings["window_last_folder_id"] = str(stored)
    save_settings(settings)
    return stored


def _normalize_hex_color(value: str, fallback: str) -> str:
    cleaned = value.strip().upper()
    if _HEX_COLOR_RE.match(cleaned):
        return cleaned
    return fallback


def _to_bool(value: str, fallback: bool) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return fallback

"""Application entry helpers for GPX Organizer."""

from __future__ import annotations

import logging
import os
import sys

from .config import APP_NAME
from .library_store import LibraryStore
from .logging_setup import configure_logging
from .main_window import MainWindow
from .map_service import LeafletMapService
from .qt_compat import QApplication, QT_BINDING
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
    get_or_create_library_root,
)


def run() -> int:
    """Create QApplication, show main window, and run event loop."""
    logger = configure_logging(logging.INFO)
    logger.info("Starting %s", APP_NAME)
    logger.info("Qt binding: %s", QT_BINDING)

    library_root = get_or_create_library_root()
    library_store = LibraryStore(library_root=library_root)
    library_store.initialize()
    logger.info("Managed library initialized at %s", library_root)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    threshold_raw = os.getenv("GPX_MAP_RESPONSIVE_THRESHOLD_PX", "").strip()
    responsive_threshold_px = get_map_responsive_threshold_px()
    if threshold_raw:
        try:
            responsive_threshold_px = int(threshold_raw)
        except ValueError:
            logger.warning("Invalid GPX_MAP_RESPONSIVE_THRESHOLD_PX=%s. Using saved setting.", threshold_raw)

    logger.info("Map responsive threshold: %spx", responsive_threshold_px)
    map_service = LeafletMapService(
        responsive_threshold_px=responsive_threshold_px,
        rest_stop_color=get_map_rest_stop_color(),
        default_track_color=get_map_default_track_color(),
        distance_marker_color=get_map_distance_marker_color(),
        direction_arrow_color=get_map_direction_arrow_color(),
        direction_arrow_interval_km=get_map_direction_arrow_interval_km(),
        direction_arrow_size_px=get_map_direction_arrow_size_px(),
        track_point_color=get_map_track_point_color(),
        track_point_size_px=get_map_track_point_size_px(),
    )
    window = MainWindow(library_store=library_store, map_service=map_service)
    window.show()

    exit_code = app.exec()
    logger.info("%s exited with code %s", APP_NAME, exit_code)
    return exit_code

"""Configuration and application paths for GPX Organizer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


APP_NAME = "GPX Organizer"
APP_ORG = "gpx-organizer"


@dataclass(frozen=True)
class AppPaths:
    """Filesystem locations used by the application."""

    base_dir: Path
    config_file: Path
    log_file: Path


def get_app_paths() -> AppPaths:
    """Build default app paths inside the user's home config directory."""
    base_dir = Path.home() / ".config" / APP_ORG
    return AppPaths(
        base_dir=base_dir,
        config_file=base_dir / "settings.json",
        log_file=base_dir / "gpx_organizer.log",
    )

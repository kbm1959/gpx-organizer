"""Tests for settings persistence helpers."""

from __future__ import annotations

from pathlib import Path

from gpx_organizer import settings_store


def test_set_library_root_persists(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"

    def fake_get_app_paths():
        from gpx_organizer.config import AppPaths

        return AppPaths(
            base_dir=config_root,
            config_file=config_root / "settings.json",
            log_file=config_root / "gpx_organizer.log",
        )

    monkeypatch.setattr(settings_store, "get_app_paths", fake_get_app_paths)

    target = tmp_path / "my-library"
    saved = settings_store.set_library_root(target)

    assert saved == target.resolve()
    loaded = settings_store.load_settings()
    assert loaded["library_root"] == str(target.resolve())


def test_set_map_responsive_threshold_persists(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"

    def fake_get_app_paths():
        from gpx_organizer.config import AppPaths

        return AppPaths(
            base_dir=config_root,
            config_file=config_root / "settings.json",
            log_file=config_root / "gpx_organizer.log",
        )

    monkeypatch.setattr(settings_store, "get_app_paths", fake_get_app_paths)

    saved = settings_store.set_map_responsive_threshold_px(840)

    assert saved == 840
    assert settings_store.get_map_responsive_threshold_px() == 840


def test_get_map_responsive_threshold_falls_back_on_invalid_value(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"

    def fake_get_app_paths():
        from gpx_organizer.config import AppPaths

        return AppPaths(
            base_dir=config_root,
            config_file=config_root / "settings.json",
            log_file=config_root / "gpx_organizer.log",
        )

    monkeypatch.setattr(settings_store, "get_app_paths", fake_get_app_paths)
    settings_store.save_settings(
        {
            "library_root": "",
            "map_responsive_threshold_px": "not-a-number",
        }
    )

    assert (
        settings_store.get_map_responsive_threshold_px()
        == settings_store.DEFAULT_MAP_RESPONSIVE_THRESHOLD_PX
    )


def test_map_color_preferences_persist(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"

    def fake_get_app_paths():
        from gpx_organizer.config import AppPaths

        return AppPaths(
            base_dir=config_root,
            config_file=config_root / "settings.json",
            log_file=config_root / "gpx_organizer.log",
        )

    monkeypatch.setattr(settings_store, "get_app_paths", fake_get_app_paths)

    assert settings_store.set_map_rest_stop_color("#112233") == "#112233"
    assert settings_store.set_map_default_track_color("#445566") == "#445566"
    assert settings_store.set_map_distance_marker_color("#778899") == "#778899"
    assert settings_store.set_map_direction_arrow_color("#AA5500") == "#AA5500"
    assert settings_store.set_map_direction_arrow_count(14) == 14
    assert settings_store.set_map_direction_arrow_size_px(18) == 18
    assert settings_store.set_map_track_point_color("#010203") == "#010203"
    assert settings_store.set_map_track_point_size_px(5) == 5

    assert settings_store.get_map_rest_stop_color() == "#112233"
    assert settings_store.get_map_default_track_color() == "#445566"
    assert settings_store.get_map_distance_marker_color() == "#778899"
    assert settings_store.get_map_direction_arrow_color() == "#AA5500"
    assert settings_store.get_map_direction_arrow_count() == 14
    assert settings_store.get_map_direction_arrow_size_px() == 18
    assert settings_store.get_map_track_point_color() == "#010203"
    assert settings_store.get_map_track_point_size_px() == 5


def test_map_color_preferences_fall_back_on_invalid_values(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"

    def fake_get_app_paths():
        from gpx_organizer.config import AppPaths

        return AppPaths(
            base_dir=config_root,
            config_file=config_root / "settings.json",
            log_file=config_root / "gpx_organizer.log",
        )

    monkeypatch.setattr(settings_store, "get_app_paths", fake_get_app_paths)
    settings_store.save_settings(
        {
            "library_root": "",
            "map_responsive_threshold_px": "900",
            "map_rest_stop_color": "oops",
            "map_default_track_color": "#12",
            "map_distance_marker_color": "red",
            "map_direction_arrow_color": "teal",
            "map_direction_arrow_count": "999",
            "map_direction_arrow_size_px": "500",
            "map_track_point_color": "white",
            "map_track_point_size_px": "33",
        }
    )

    assert settings_store.get_map_rest_stop_color() == settings_store.DEFAULT_MAP_REST_STOP_COLOR
    assert (
        settings_store.get_map_default_track_color()
        == settings_store.DEFAULT_MAP_DEFAULT_TRACK_COLOR
    )
    assert (
        settings_store.get_map_distance_marker_color()
        == settings_store.DEFAULT_MAP_DISTANCE_MARKER_COLOR
    )
    assert (
        settings_store.get_map_direction_arrow_color()
        == settings_store.DEFAULT_MAP_DIRECTION_ARROW_COLOR
    )
    assert (
        settings_store.get_map_direction_arrow_count()
        == settings_store.MAX_MAP_DIRECTION_ARROW_COUNT
    )
    assert (
        settings_store.get_map_direction_arrow_size_px()
        == settings_store.MAX_MAP_DIRECTION_ARROW_SIZE_PX
    )
    assert (
        settings_store.get_map_track_point_color()
        == settings_store.DEFAULT_MAP_TRACK_POINT_COLOR
    )
    assert (
        settings_store.get_map_track_point_size_px()
        == settings_store.MAX_MAP_TRACK_POINT_SIZE_PX
    )


def test_map_direction_arrow_count_default_is_ten(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"

    def fake_get_app_paths():
        from gpx_organizer.config import AppPaths

        return AppPaths(
            base_dir=config_root,
            config_file=config_root / "settings.json",
            log_file=config_root / "gpx_organizer.log",
        )

    monkeypatch.setattr(settings_store, "get_app_paths", fake_get_app_paths)
    loaded = settings_store.load_settings()

    assert loaded["map_direction_arrow_count"] == "10"
    assert loaded["map_direction_arrow_size_px"] == "12"
    assert loaded["map_track_point_color"] == "#000000"
    assert loaded["map_track_point_size_px"] == "1"

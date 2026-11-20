"""Tests for Milestone 3 managed library storage."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from gpx_analyzer import GPXAnalyzer
from gpx_organizer.library_store import LibraryStore


SAMPLE_GPX = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<gpx version=\"1.1\" creator=\"test\" xmlns=\"http://www.topografix.com/GPX/1/1\">
  <trk>
    <name>Sample</name>
    <trkseg>
      <trkpt lat=\"48.100000\" lon=\"7.100000\">
        <ele>200</ele>
        <time>2026-08-08T08:00:00Z</time>
      </trkpt>
      <trkpt lat=\"48.101000\" lon=\"7.101000\">
        <ele>210</ele>
        <time>2026-08-08T08:02:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
"""

WAYPOINT_GPX = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<gpx version=\"1.1\" creator=\"test\" xmlns=\"http://www.topografix.com/GPX/1/1\">
    <wpt lat=\"49.755773\" lon=\"6.993925\">
        <name>ZuHause</name>
        <sym>Residence</sym>
    </wpt>
</gpx>
"""


def _write_sample(path: Path) -> None:
    path.write_text(SAMPLE_GPX, encoding="utf-8")


def _default_tray(store: LibraryStore) -> int:
    root_id = store.get_root_folder_id()
    for folder in store.list_folders():
        if folder.parent_id == root_id and folder.name == "Test tray" and folder.kind == "tray":
            return folder.id
    return store.create_tray("Test tray", root_id)


def test_initialize_creates_root_and_trash(tmp_path: Path) -> None:
    store = LibraryStore(tmp_path / "library")
    store.initialize()

    folders = store.list_folders()
    names = {folder.name for folder in folders}

    assert "My Library" in names
    assert "Trash" in names


def test_legacy_tray_migration_preserves_items_and_handles_mixed_folders(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    root = store.get_root_folder_id()
    leaf = store.create_tray("Leaf", root)
    mixed = store.create_folder("Mixed", root)
    store.create_folder("Items", mixed)
    staging = store.create_tray("Staging", root)
    empty = store.create_folder("Empty", root)
    leaf_track = store.import_gpx(source, leaf)
    mixed_track = store.import_gpx(source, staging)
    root_track = store.import_gpx(source, staging)
    trashed_track = store.import_gpx(source, staging)
    store.move_track_to_trash(trashed_track.track_id)
    with store._connect() as conn:
        conn.execute("UPDATE tracks SET folder_id = ? WHERE id = ?", (mixed, mixed_track.track_id))
        conn.execute("UPDATE tracks SET folder_id = ? WHERE id = ?", (root, root_track.track_id))
        conn.execute("ALTER TABLE folders DROP COLUMN is_tray")

    store.initialize()
    folders = {folder.id: folder for folder in store.list_folders()}
    assert folders[leaf].kind == "tray"
    assert folders[empty].kind == "normal"
    assert store.get_track(leaf_track.track_id).folder_id == leaf
    mixed_tray = folders[store.get_track(mixed_track.track_id).folder_id]
    assert (mixed_tray.parent_id, mixed_tray.name, mixed_tray.kind) == (mixed, "Items (1)", "tray")
    root_tray = folders[store.get_track(root_track.track_id).folder_id]
    assert root_tray.parent_id == root and root_tray.kind == "tray"
    assert store.get_track(trashed_track.track_id).folder_id == store.get_trash_folder_id()
    assert all(item.managed_path.exists() for item in (leaf_track, mixed_track, root_track, trashed_track))
    before = store.list_folders()
    store.initialize()
    assert store.list_folders() == before


def test_tray_storage_rules_and_copy(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    root = store.get_root_folder_id()
    folder = store.create_folder("Folder", root)
    tray = store.create_tray("Tray", folder)
    other_tray = store.create_tray("Other", folder)
    item = store.import_gpx(source, tray)
    assert store.get_folder(tray).kind == "tray"
    with pytest.raises(ValueError, match="folders"):
        store.create_folder("Nested", tray)
    with pytest.raises(ValueError, match="folders"):
        store.create_tray("Nested", tray)
    with pytest.raises(ValueError, match="trays"):
        store.import_gpx(source, folder)
    with pytest.raises(ValueError, match="trays"):
        store.move_track_to_folder(item.track_id, root)
    with pytest.raises(ValueError, match="trays"):
        store.copy_items_to_folder([item.track_id], folder)
    with pytest.raises(ValueError, match="folders"):
        store.move_folder(folder, tray)
    with pytest.raises(ValueError, match="folders"):
        store.copy_folder_subtree(folder, tray)
    with pytest.raises(ValueError, match="folders"):
        store.move_folder(tray, store.get_trash_folder_id())
    store.move_track_to_folder(item.track_id, other_tray)
    copied = store.copy_folder_subtree(folder, root)
    copied_trays = [node for node in store.list_folders() if node.parent_id == copied]
    assert len(copied_trays) == 2 and all(node.kind == "tray" for node in copied_trays)
    assert len(store.list_tracks_recursive(copied)) == 1


def test_folder_and_tray_names_are_unique_per_type(tmp_path: Path) -> None:
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    root = store.get_root_folder_id()
    folder = store.create_folder("Ride", root)
    tray = store.create_tray("ride", root)
    with pytest.raises(ValueError):
        store.create_folder("RIDE", root)
    with pytest.raises(ValueError):
        store.create_tray("RIDE", root)

    source = store.create_folder("Source", root)
    other_tray = store.create_tray("Other", source)
    store.rename_folder(other_tray, "Ride")
    with pytest.raises(ValueError):
        store.move_folder(other_tray, root)
    store.delete_folder(tray)
    store.move_folder(other_tray, root)
    assert store.get_folder(other_tray).parent_id == root

    destination = store.create_folder("Destination", root)
    store.create_tray("Ride", destination)
    copied = store.copy_folder_subtree(folder, destination)
    assert store.get_folder(copied).name == "Ride"
    assert store.get_folder(copied).kind == "normal"
    copied_again = store.copy_folder_subtree(folder, destination)
    assert store.get_folder(copied_again).name == "Ride (1)"
    with pytest.raises(ValueError):
        store.rename_folder(store.create_tray("Another", root), "ride")
    with pytest.raises(ValueError):
        store.convert_tray_to_folder(other_tray)
    assert store.get_folder(other_tray).kind == "tray"

    other_parent = store.create_folder("Other parent", root)
    moved_folder = store.create_folder("Shared", other_parent)
    store.create_tray("Shared", destination)
    store.move_folder(moved_folder, destination)
    assert store.get_folder(moved_folder).parent_id == destination
    new_tray = store.create_tray("Temporary", other_parent)
    store.rename_folder(new_tray, "Shared")
    copied_tray = store.copy_folder_subtree(new_tray, store.create_folder("Copy target", root))
    assert store.get_folder(copied_tray).name == "Shared"


def test_tray_migration_rolls_back_on_failure(tmp_path: Path, monkeypatch) -> None:
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    with store._connect() as conn:
        conn.execute("ALTER TABLE folders DROP COLUMN is_tray")

    def fail_migration(conn):
        raise RuntimeError("migration interrupted")

    monkeypatch.setattr(store, "_migrate_existing_trays", fail_migration)
    with pytest.raises(RuntimeError, match="migration interrupted"):
        store.initialize()
    with store._connect() as conn:
        assert "is_tray" not in {row["name"] for row in conn.execute("PRAGMA table_info(folders)")}
    LibraryStore(store.library_root).initialize()
    assert LibraryStore(store.library_root).get_folder(store.get_root_folder_id()).kind == "root"


def test_preview_cache_flushes_after_interrupted_build(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    track = store.import_gpx(source, target_folder_id=_default_tray(store))
    payload = {"coordinates": [], "waypoints": [], "color": None}
    with pytest.raises(RuntimeError, match="interrupted"):
        with store.preview_data_cache() as cache:
            assert cache.get(track.track_id, track.managed_path) is None
            cache.put(track.track_id, track.managed_path, payload)
            raise RuntimeError("interrupted")
    with store.preview_data_cache() as cache:
        assert cache.get(track.track_id, track.managed_path) == payload


def test_preview_cache_rejects_stale_write_after_edit_or_purge(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)
    store = LibraryStore(tmp_path / "library")
    store.initialize()
    track = store.import_gpx(source, target_folder_id=_default_tray(store))
    payload = {"coordinates": [], "waypoints": [], "color": None}

    with store.preview_data_cache() as cache:
        assert cache.get(track.track_id, track.managed_path) is None
        cache.put(track.track_id, track.managed_path, payload)
        store.reverse_track(track.track_id)
    with store.preview_data_cache() as cache:
        assert cache.get(track.track_id, track.managed_path) is None
        cache.put(track.track_id, track.managed_path, payload)
        store.move_track_to_trash(track.track_id)
        store.purge_track(track.track_id)
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM preview_data_cache").fetchone()[0] == 0


def test_import_hash_duplicate_gets_numbered_filename(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    first = store.import_gpx(source, target_folder_id=_default_tray(store))
    second = store.import_gpx(source, target_folder_id=_default_tray(store))

    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert "(1).gpx" in second.display_name


def test_import_waypoint_only_gpx(tmp_path: Path) -> None:
        source = tmp_path / "waypoint.gpx"
        source.write_text(WAYPOINT_GPX, encoding="utf-8")

        store = LibraryStore(tmp_path / "library")
        store.initialize()

        results = store.import_gpx_all(source, target_folder_id=_default_tray(store))

        assert len(results) == 1
        assert results[0].entry_kind == "waypoint"
        assert results[0].managed_path.exists()

        root_id = store.get_root_folder_id()
        entries = store.list_tracks_recursive(root_id)
        assert len(entries) == 1
        assert entries[0].entry_kind == "waypoint"


def test_import_mixed_track_and_waypoint_gpx(tmp_path: Path) -> None:
    source = tmp_path / "mixed.gpx"
    source.write_text(
        SAMPLE_GPX.replace("</gpx>", "")
        + """
    <wpt lat=\"49.755773\" lon=\"6.993925\">
        <name>Home Pin</name>
    </wpt>
</gpx>
""",
        encoding="utf-8",
    )

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    results = store.import_gpx_all(source, target_folder_id=_default_tray(store))
    imported_kinds = {result.entry_kind for result in results}

    assert imported_kinds == {"track", "waypoint"}
    assert len(results) == 2


def test_copy_waypoint_to_another_folder(tmp_path: Path) -> None:
    source = tmp_path / "waypoint.gpx"
    source.write_text(WAYPOINT_GPX, encoding="utf-8")

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx_all(source, target_folder_id=_default_tray(store))
    waypoint = next(result for result in imported if result.entry_kind == "waypoint")

    root_id = store.get_root_folder_id()
    target_folder = store.create_tray("Pins", parent_id=root_id)

    copied = store.copy_items_to_folder([waypoint.track_id], target_folder)
    assert len(copied) == 1
    assert copied[0].entry_kind == "waypoint"

    target_items = store.list_tracks(target_folder)
    assert len(target_items) == 1
    assert target_items[0].entry_kind == "waypoint"


def test_copy_track_name_uses_single_increment_suffix(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source, target_folder_id=_default_tray(store))
    root_id = store.get_root_folder_id()

    first_copy = store.copy_items_to_folder([imported.track_id], _default_tray(store))[0]
    second_copy = store.copy_items_to_folder([first_copy.id], _default_tray(store))[0]

    assert first_copy.display_name.endswith(" (1).gpx")
    assert second_copy.display_name.endswith(" (2).gpx")
    assert "(1) (1)" not in second_copy.display_name


def test_copy_waypoint_name_uses_single_increment_suffix(tmp_path: Path) -> None:
    source = tmp_path / "waypoint.gpx"
    source.write_text(WAYPOINT_GPX, encoding="utf-8")

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx_all(source, target_folder_id=_default_tray(store))
    waypoint = next(result for result in imported if result.entry_kind == "waypoint")
    root_id = store.get_root_folder_id()

    first_copy = store.copy_items_to_folder([waypoint.track_id], _default_tray(store))[0]
    second_copy = store.copy_items_to_folder([first_copy.id], _default_tray(store))[0]

    assert first_copy.display_name.endswith(" (1).gpx")
    assert second_copy.display_name.endswith(" (2).gpx")
    assert "(1) (1)" not in second_copy.display_name


def test_copy_folder_subtree_uses_increment_suffix_and_copies_items(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()
    root_id = store.get_root_folder_id()

    source_folder_id = store.create_folder("Trips", parent_id=root_id)
    child_folder_id = store.create_tray("Day1", parent_id=source_folder_id)
    source_tray_id = store.create_tray("Day2", parent_id=source_folder_id)
    store.import_gpx(source, target_folder_id=source_tray_id)
    store.import_gpx(source, target_folder_id=child_folder_id)

    first_copy_id = store.copy_folder_subtree(source_folder_id, root_id)
    second_copy_id = store.copy_folder_subtree(first_copy_id, root_id)

    folders = {folder.id: folder for folder in store.list_folders()}
    assert folders[first_copy_id].name == "Trips (1)"
    assert folders[second_copy_id].name == "Trips (2)"

    first_copy_tracks = store.list_tracks_recursive(first_copy_id)
    second_copy_tracks = store.list_tracks_recursive(second_copy_id)
    assert len(first_copy_tracks) == 2
    assert len(second_copy_tracks) == 2


def test_trash_then_purge_removes_file_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source, target_folder_id=_default_tray(store))
    track_id = imported.track_id

    store.move_track_to_trash(track_id)
    store.purge_track(track_id)

    trash_id = store.get_trash_folder_id()
    assert store.list_tracks(trash_id) == []
    assert not imported.managed_path.exists()


def test_rename_track_changes_managed_filename(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source, target_folder_id=_default_tray(store))
    renamed = store.rename_track(imported.track_id, "Morning Ride")

    assert renamed.display_name.startswith("Morning Ride")
    assert (store.library_root / renamed.managed_rel_path).exists()


def test_rename_track_rejects_duplicate_name_across_tree(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    root_id = store.get_root_folder_id()
    folder_a = store.create_tray("A", parent_id=root_id)
    folder_b = store.create_tray("B", parent_id=root_id)

    first = store.import_gpx(source, target_folder_id=folder_a)
    second = store.import_gpx(source, target_folder_id=folder_b)

    try:
        store.rename_track(second.track_id, Path(first.display_name).stem)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "already exists in the library tree" in str(exc)


def test_folder_move_and_rename_and_track_move(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    root_id = store.get_root_folder_id()
    trash_id = store.get_trash_folder_id()

    folder_a = store.create_tray("A", parent_id=root_id)
    folder_b = store.create_tray("B", parent_id=root_id)

    imported = store.import_gpx(source, target_folder_id=folder_a)
    store.move_track_to_folder(imported.track_id, folder_b)
    tracks_in_b = store.list_tracks(folder_b)
    assert len(tracks_in_b) == 1

    renamed = store.rename_folder(folder_b, "Renamed B")
    assert renamed.name == "Renamed B"

    store.move_folder(folder_b, root_id)
    moved_folder = store.get_folder(folder_b)
    assert moved_folder.parent_id == root_id

    # ensure protected folder restrictions remain
    try:
        store.rename_folder(trash_id, "Nope")
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_subfolders_are_listed_alphabetically(tmp_path: Path) -> None:
    store = LibraryStore(tmp_path / "library")
    store.initialize()

    root_id = store.get_root_folder_id()
    parent_id = store.create_folder("Parent", parent_id=root_id)
    store.create_folder("Zoo", parent_id=parent_id)
    store.create_folder("alpha", parent_id=parent_id)
    store.create_folder("Bravo", parent_id=parent_id)

    folders = store.list_folders()
    child_names = [
        folder.name
        for folder in folders
        if folder.parent_id == parent_id and folder.kind == "normal"
    ]
    assert child_names == ["alpha", "Bravo", "Zoo"]


def test_delete_folder_moves_tracks_to_trash(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    root_id = store.get_root_folder_id()
    trash_id = store.get_trash_folder_id()

    folder = store.create_tray("DeleteMe", parent_id=root_id)
    imported = store.import_gpx(source, target_folder_id=folder)

    store.delete_folder(folder)

    trash_tracks = store.list_tracks(trash_id)
    assert any(track.id == imported.track_id for track in trash_tracks)


def test_delete_folder_removes_entire_subtree(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    root_id = store.get_root_folder_id()
    trash_id = store.get_trash_folder_id()

    parent_id = store.create_folder("Parent", parent_id=root_id)
    child_id = store.create_folder("Child", parent_id=parent_id)
    grandchild_id = store.create_tray("Grandchild", parent_id=child_id)
    child_tray_id = store.create_tray("Items", parent_id=child_id)

    store.import_gpx(source, target_folder_id=child_tray_id)
    store.import_gpx(source, target_folder_id=grandchild_id)

    store.delete_folder(parent_id)

    remaining_folder_ids = {folder.id for folder in store.list_folders()}
    assert parent_id not in remaining_folder_ids
    assert child_id not in remaining_folder_ids
    assert grandchild_id not in remaining_folder_ids

    trash_tracks = store.list_tracks(trash_id)
    assert len(trash_tracks) == 2


def test_get_track_and_managed_path(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source, target_folder_id=_default_tray(store))
    track = store.get_track(imported.track_id)
    managed_path = store.get_track_managed_path(imported.track_id)

    assert track.id == imported.track_id
    assert managed_path.exists()
    assert managed_path.name == track.display_name


def test_copy_item_uses_global_unique_display_name(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    root_id = store.get_root_folder_id()
    folder_a = store.create_tray("A", parent_id=root_id)
    folder_b = store.create_tray("B", parent_id=root_id)

    imported = store.import_gpx(source, target_folder_id=folder_a)
    copied = store.copy_items_to_folder([imported.track_id], folder_b)[0]

    assert copied.display_name != imported.display_name


def test_export_track_copies_managed_gpx(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source, target_folder_id=_default_tray(store))
    destination = tmp_path / "exports" / "ride-export.gpx"

    exported = store.export_track(imported.track_id, destination)
    assert exported == destination.resolve()
    assert exported.exists()
    assert exported.read_text(encoding="utf-8") == store.get_track_managed_path(
        imported.track_id
    ).read_text(encoding="utf-8")


def test_export_track_refuses_overwrite_by_default(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source, target_folder_id=_default_tray(store))
    destination = tmp_path / "already_exists.gpx"
    destination.write_text("existing", encoding="utf-8")

    try:
        store.export_track(imported.track_id, destination)
        assert False, "Expected FileExistsError"
    except FileExistsError:
        pass


def test_reverse_track_reverses_point_order(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source, target_folder_id=_default_tray(store))
    managed_path = store.get_track_managed_path(imported.track_id)

    analyzer = GPXAnalyzer()
    analyzer.read_gpx_file(managed_path)
    before = analyzer.get_track_points()

    store.reverse_track(imported.track_id)

    analyzer.read_gpx_file(managed_path)
    after = analyzer.get_track_points()

    assert len(before) == len(after)
    assert before[0].latitude == after[-1].latitude
    assert before[0].longitude == after[-1].longitude
    assert before[-1].latitude == after[0].latitude
    assert before[-1].longitude == after[0].longitude


def test_set_track_color_writes_gpx_extension(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source, target_folder_id=_default_tray(store))
    store.set_track_color(imported.track_id, "#123ABC")

    assert store.get_track_color(imported.track_id) == "#123ABC"

    managed_path = store.get_track_managed_path(imported.track_id)
    content = managed_path.read_text(encoding="utf-8")
    assert "go:displayColor" in content
    assert "#123ABC" in content


def test_build_reverse_preview_creates_temp_reversed_track(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()
    imported = store.import_gpx(source, target_folder_id=_default_tray(store))

    preview_path = store.build_reverse_preview(imported.track_id)
    assert preview_path.exists()

    analyzer = GPXAnalyzer()
    analyzer.read_gpx_file(preview_path)
    points = analyzer.get_track_points()
    assert len(points) == 2
    assert points[0].latitude == 48.101

    preview_path.unlink()


def test_build_trim_preview_creates_temp_trimmed_track(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()
    imported = store.import_gpx(source, target_folder_id=_default_tray(store))

    preview_path = store.build_trim_preview(imported.track_id, 0.0, 50.0)
    assert preview_path.exists()

    analyzer = GPXAnalyzer()
    analyzer.read_gpx_file(preview_path)
    points = analyzer.get_track_points()
    assert len(points) >= 2

    preview_path.unlink()


def test_build_split_preview_creates_two_temp_tracks(tmp_path: Path) -> None:
    source = tmp_path / "ride_split.gpx"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
    <trk>
        <name>SplitSample</name>
        <trkseg>
            <trkpt lat="48.100000" lon="7.100000"><ele>200</ele><time>2026-08-08T08:00:00Z</time></trkpt>
            <trkpt lat="48.101000" lon="7.101000"><ele>205</ele><time>2026-08-08T08:01:00Z</time></trkpt>
            <trkpt lat="48.102000" lon="7.102000"><ele>210</ele><time>2026-08-08T08:02:00Z</time></trkpt>
            <trkpt lat="48.103000" lon="7.103000"><ele>215</ele><time>2026-08-08T08:03:00Z</time></trkpt>
        </trkseg>
    </trk>
</gpx>
""",
        encoding="utf-8",
    )

    store = LibraryStore(tmp_path / "library")
    store.initialize()
    imported = store.import_gpx(source, target_folder_id=_default_tray(store))

    preview_a, preview_b = store.build_split_preview(imported.track_id, 50.0)
    assert preview_a.exists()
    assert preview_b.exists()

    analyzer = GPXAnalyzer()
    analyzer.read_gpx_file(preview_a)
    points_a = analyzer.get_track_points()
    analyzer.read_gpx_file(preview_b)
    points_b = analyzer.get_track_points()
    assert len(points_a) >= 2
    assert len(points_b) >= 2

    preview_a.unlink()
    preview_b.unlink()


def test_build_merge_preview_creates_temp_merged_track(tmp_path: Path) -> None:
    source_a = tmp_path / "merge_a.gpx"
    source_b = tmp_path / "merge_b.gpx"

    source_a.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
    <trk><name>A</name><trkseg>
        <trkpt lat="48.100000" lon="7.100000"><ele>200</ele><time>2026-08-08T08:00:00Z</time></trkpt>
        <trkpt lat="48.101000" lon="7.101000"><ele>205</ele><time>2026-08-08T08:01:00Z</time></trkpt>
    </trkseg></trk>
</gpx>
""",
        encoding="utf-8",
    )
    source_b.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
    <trk><name>B</name><trkseg>
        <trkpt lat="48.101000" lon="7.101000"><ele>205</ele><time>2026-08-08T08:01:00Z</time></trkpt>
        <trkpt lat="48.102000" lon="7.102000"><ele>210</ele><time>2026-08-08T08:02:00Z</time></trkpt>
    </trkseg></trk>
</gpx>
""",
        encoding="utf-8",
    )

    store = LibraryStore(tmp_path / "library")
    store.initialize()
    imported_a = store.import_gpx(source_a, target_folder_id=_default_tray(store))
    imported_b = store.import_gpx(source_b, target_folder_id=_default_tray(store))

    preview_path = store.build_merge_preview([imported_a.track_id, imported_b.track_id])
    assert preview_path.exists()

    analyzer = GPXAnalyzer()
    analyzer.read_gpx_file(preview_path)
    points = analyzer.get_track_points()
    assert len(points) == 3

    preview_path.unlink()


def test_trim_track_creates_new_trimmed_copy(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source, target_folder_id=_default_tray(store))
    trimmed = store.trim_track(imported.track_id, start_percent=0.0, end_percent=50.0)

    assert trimmed.id != imported.track_id
    assert "(trim)" in trimmed.display_name

    original_path = store.get_track_managed_path(imported.track_id)
    trimmed_path = store.get_track_managed_path(trimmed.id)
    assert original_path.exists()
    assert trimmed_path.exists()
    assert original_path != trimmed_path

    analyzer = GPXAnalyzer()
    analyzer.read_gpx_file(trimmed_path)
    trimmed_points = analyzer.get_track_points()
    assert len(trimmed_points) >= 2


def test_split_track_creates_two_new_tracks(tmp_path: Path) -> None:
        source = tmp_path / "ride_split.gpx"
        source.write_text(
                """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<gpx version=\"1.1\" creator=\"test\" xmlns=\"http://www.topografix.com/GPX/1/1\"> 
    <trk>
        <name>SplitSample</name>
        <trkseg>
            <trkpt lat=\"48.100000\" lon=\"7.100000\"><ele>200</ele><time>2026-08-08T08:00:00Z</time></trkpt>
            <trkpt lat=\"48.101000\" lon=\"7.101000\"><ele>205</ele><time>2026-08-08T08:01:00Z</time></trkpt>
            <trkpt lat=\"48.102000\" lon=\"7.102000\"><ele>210</ele><time>2026-08-08T08:02:00Z</time></trkpt>
            <trkpt lat=\"48.103000\" lon=\"7.103000\"><ele>215</ele><time>2026-08-08T08:03:00Z</time></trkpt>
        </trkseg>
    </trk>
</gpx>
""",
                encoding="utf-8",
        )

        store = LibraryStore(tmp_path / "library")
        store.initialize()

        imported = store.import_gpx(source, target_folder_id=_default_tray(store))
        part_a, part_b = store.split_track(imported.track_id, split_percent=50.0)

        assert part_a.id != imported.track_id
        assert part_b.id != imported.track_id
        assert "(split A)" in part_a.display_name
        assert "(split B)" in part_b.display_name
        assert store.get_track_managed_path(part_a.id).exists()
        assert store.get_track_managed_path(part_b.id).exists()


def test_merge_tracks_creates_new_merged_copy(tmp_path: Path) -> None:
        source_a = tmp_path / "merge_a.gpx"
        source_b = tmp_path / "merge_b.gpx"

        source_a.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
    <trk>
        <name>Merge A</name>
        <trkseg>
            <trkpt lat="48.100000" lon="7.100000"><ele>200</ele><time>2026-08-08T08:00:00Z</time></trkpt>
            <trkpt lat="48.101000" lon="7.101000"><ele>205</ele><time>2026-08-08T08:01:00Z</time></trkpt>
        </trkseg>
    </trk>
</gpx>
""",
                encoding="utf-8",
        )
        source_b.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
    <trk>
        <name>Merge B</name>
        <trkseg>
            <trkpt lat="48.101000" lon="7.101000"><ele>205</ele><time>2026-08-08T08:01:00Z</time></trkpt>
            <trkpt lat="48.102000" lon="7.102000"><ele>210</ele><time>2026-08-08T08:02:00Z</time></trkpt>
        </trkseg>
    </trk>
</gpx>
""",
                encoding="utf-8",
        )

        store = LibraryStore(tmp_path / "library")
        store.initialize()

        imported_a = store.import_gpx(source_a, target_folder_id=_default_tray(store))
        imported_b = store.import_gpx(source_b, target_folder_id=_default_tray(store))

        merged = store.merge_tracks([imported_a.track_id, imported_b.track_id])
        assert merged.id not in {imported_a.track_id, imported_b.track_id}
        assert "(merge)" in merged.display_name

        merged_path = store.get_track_managed_path(merged.id)
        assert merged_path.exists()

        analyzer = GPXAnalyzer()
        analyzer.read_gpx_file(merged_path)
        merged_points = analyzer.get_track_points()
        assert len(merged_points) == 3
        assert merged_points[0].latitude == 48.1
        assert merged_points[-1].latitude == 48.102


def test_import_multi_track_gpx_creates_named_separate_tracks(tmp_path: Path) -> None:
        source = tmp_path / "multi.gpx"
        source.write_text(
                """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<gpx version=\"1.1\" creator=\"test\" xmlns=\"http://www.topografix.com/GPX/1/1\">
    <trk>
        <name>Morning Loop</name>
        <trkseg>
            <trkpt lat=\"48.100000\" lon=\"7.100000\"><ele>200</ele><time>2026-08-08T08:00:00Z</time></trkpt>
            <trkpt lat=\"48.101000\" lon=\"7.101000\"><ele>210</ele><time>2026-08-08T08:02:00Z</time></trkpt>
        </trkseg>
    </trk>
    <trk>
        <name>Evening Sprint</name>
        <trkseg>
            <trkpt lat=\"48.200000\" lon=\"7.200000\"><ele>100</ele><time>2026-08-08T18:00:00Z</time></trkpt>
            <trkpt lat=\"48.201000\" lon=\"7.201000\"><ele>105</ele><time>2026-08-08T18:02:00Z</time></trkpt>
        </trkseg>
    </trk>
</gpx>
""",
                encoding="utf-8",
        )

        store = LibraryStore(tmp_path / "library")
        store.initialize()

        imported = store.import_gpx_all(source, target_folder_id=_default_tray(store))
        assert len(imported) == 2

        tracks = store.list_tracks_recursive(store.get_root_folder_id())
        names = {track.display_name for track in tracks}
        assert "Morning Loop" in names
        assert "Evening Sprint" in names


def test_list_tracks_recursive_includes_subfolders(tmp_path: Path) -> None:
        source_a = tmp_path / "a.gpx"
        source_b = tmp_path / "b.gpx"
        _write_sample(source_a)
        _write_sample(source_b)

        store = LibraryStore(tmp_path / "library")
        store.initialize()

        root_id = store.get_root_folder_id()
        parent_folder = store.create_folder("Parent", parent_id=root_id)
        child_folder = store.create_tray("Child", parent_id=parent_folder)
        parent_tray = store.create_tray("Parent items", parent_id=parent_folder)

        track_parent = store.import_gpx(source_a, target_folder_id=parent_tray)
        track_child = store.import_gpx(source_b, target_folder_id=child_folder)

        recursive_tracks = store.list_tracks_recursive(parent_folder)
        recursive_ids = {track.id for track in recursive_tracks}

        assert track_parent.track_id in recursive_ids
        assert track_child.track_id in recursive_ids

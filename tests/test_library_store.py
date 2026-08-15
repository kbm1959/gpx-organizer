"""Tests for Milestone 3 managed library storage."""

from __future__ import annotations

from pathlib import Path

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


def _write_sample(path: Path) -> None:
    path.write_text(SAMPLE_GPX, encoding="utf-8")


def test_initialize_creates_root_and_trash(tmp_path: Path) -> None:
    store = LibraryStore(tmp_path / "library")
    store.initialize()

    folders = store.list_folders()
    names = {folder.name for folder in folders}

    assert "My Library" in names
    assert "Trash" in names


def test_import_hash_duplicate_gets_numbered_filename(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    first = store.import_gpx(source)
    second = store.import_gpx(source)

    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert "(1).gpx" in second.display_name


def test_trash_then_purge_removes_file_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source)
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

    imported = store.import_gpx(source)
    renamed = store.rename_track(imported.track_id, "Morning Ride")

    assert renamed.display_name.startswith("Morning Ride")
    assert (store.library_root / renamed.managed_rel_path).exists()


def test_folder_move_and_rename_and_track_move(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    root_id = store.get_root_folder_id()
    trash_id = store.get_trash_folder_id()

    folder_a = store.create_folder("A", parent_id=root_id)
    folder_b = store.create_folder("B", parent_id=root_id)

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

    folder = store.create_folder("DeleteMe", parent_id=root_id)
    imported = store.import_gpx(source, target_folder_id=folder)

    store.delete_folder(folder)

    trash_tracks = store.list_tracks(trash_id)
    assert any(track.id == imported.track_id for track in trash_tracks)


def test_get_track_and_managed_path(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source)
    track = store.get_track(imported.track_id)
    managed_path = store.get_track_managed_path(imported.track_id)

    assert track.id == imported.track_id
    assert managed_path.exists()
    assert managed_path.name == track.display_name


def test_export_track_copies_managed_gpx(tmp_path: Path) -> None:
    source = tmp_path / "ride.gpx"
    _write_sample(source)

    store = LibraryStore(tmp_path / "library")
    store.initialize()

    imported = store.import_gpx(source)
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

    imported = store.import_gpx(source)
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

    imported = store.import_gpx(source)
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

    imported = store.import_gpx(source)
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
    imported = store.import_gpx(source)

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
    imported = store.import_gpx(source)

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
    imported = store.import_gpx(source)

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
    imported_a = store.import_gpx(source_a)
    imported_b = store.import_gpx(source_b)

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

    imported = store.import_gpx(source)
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

        imported = store.import_gpx(source)
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

        imported_a = store.import_gpx(source_a)
        imported_b = store.import_gpx(source_b)

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

        imported = store.import_gpx_all(source)
        assert len(imported) == 2

        tracks = store.list_tracks(store.get_root_folder_id())
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
        child_folder = store.create_folder("Child", parent_id=parent_folder)

        track_parent = store.import_gpx(source_a, target_folder_id=parent_folder)
        track_child = store.import_gpx(source_b, target_folder_id=child_folder)

        recursive_tracks = store.list_tracks_recursive(parent_folder)
        recursive_ids = {track.id for track in recursive_tracks}

        assert track_parent.track_id in recursive_ids
        assert track_child.track_id in recursive_ids

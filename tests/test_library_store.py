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

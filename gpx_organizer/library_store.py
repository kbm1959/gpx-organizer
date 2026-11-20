"""Persistent managed library storage for GPX Organizer."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import copy
import hashlib
from io import BytesIO
import json
import logging
import math
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any, Iterator
import xml.etree.ElementTree as ET

from gpx_analyzer import GPXAnalyzer


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
COPY_SUFFIX_RE = re.compile(r"^(.*)\s\((\d+)\)$")

GPX_NS = "http://www.topografix.com/GPX/1/1"
GPX_ORGANIZER_EXT_NS = "https://gpx-organizer.dev/xmlns/1"
ET.register_namespace("go", GPX_ORGANIZER_EXT_NS)


@dataclass(frozen=True)
class FolderRecord:
    """Folder row loaded from SQLite."""

    id: int
    parent_id: int | None
    name: str
    kind: str
    position: int


@dataclass(frozen=True)
class TrackRecord:
    """Track row loaded from SQLite."""

    id: int
    folder_id: int
    display_name: str
    managed_rel_path: str
    original_source_path: str
    file_hash: str
    file_size: int
    duplicate_of_track_id: int | None
    entry_kind: str = "track"


@dataclass(frozen=True)
class ImportResult:
    """Details about an imported GPX file."""

    track_id: int
    display_name: str
    managed_path: Path
    file_hash: str
    is_duplicate: bool
    entry_kind: str = "track"


PREVIEW_DATA_VERSION = 1
_LOGGER = logging.getLogger(__name__)


class PreviewDataCache:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._sources: dict[int, tuple[int, int, str]] = {}
        self._pending: list[tuple[int, int, int, int, str, str]] = []
        self._disabled = False

    def get(self, track_id: int, path: Path) -> dict[str, Any] | None:
        stat = path.stat()
        if self._disabled:
            return None
        try:
            row = self._conn.execute(
                """SELECT t.file_hash, c.source_hash, c.version, c.file_mtime_ns, c.file_size, c.payload_json
                   FROM tracks t LEFT JOIN preview_data_cache c ON c.track_id = t.id
                   WHERE t.id = ?""",
                (track_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            self._disabled = True
            _LOGGER.warning("Preview cache unavailable: %s", exc)
            return None
        if row is None:
            return None
        self._sources[track_id] = (stat.st_mtime_ns, stat.st_size, str(row["file_hash"]))
        if (
            row["version"] != PREVIEW_DATA_VERSION
            or row["source_hash"] != row["file_hash"]
            or row["file_mtime_ns"] != stat.st_mtime_ns
            or row["file_size"] != stat.st_size
        ):
            return None
        try:
            payload = json.loads(row["payload_json"])
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("coordinates"), list)
                or not isinstance(payload.get("waypoints"), list)
            ):
                return None
            return payload
        except (ValueError, TypeError):
            return None

    def put(self, track_id: int, path: Path, payload: dict[str, Any]) -> None:
        source = self._sources.get(track_id)
        if source is None or self._disabled:
            return
        stat = path.stat()
        mtime_ns, size, file_hash = source
        if (stat.st_mtime_ns, stat.st_size) != (mtime_ns, size):
            return
        self._pending.append((track_id, PREVIEW_DATA_VERSION, mtime_ns, size, json.dumps(payload), file_hash))
        if len(self._pending) >= 32:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        try:
            self._conn.executemany(
                """INSERT OR REPLACE INTO preview_data_cache
                   (track_id, version, file_mtime_ns, file_size, payload_json, source_hash)
                   SELECT id, ?, ?, ?, ?, file_hash FROM tracks WHERE id = ? AND file_hash = ?""",
                [(version, mtime, size, payload, track_id, file_hash)
                 for track_id, version, mtime, size, payload, file_hash in self._pending],
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            self._disabled = True
            _LOGGER.warning("Preview cache could not be saved: %s", exc)
        self._pending.clear()


class LibraryStore:
    """Handle persistent storage, import, and managed-file lifecycle."""

    def __init__(self, library_root: Path) -> None:
        self.library_root = library_root
        self.db_path = self.library_root / "library.db"
        self.tracks_dir = self.library_root / "tracks"

    def initialize(self) -> None:
        """Create managed library folders, schema, and default folder rows."""
        self.library_root.mkdir(parents=True, exist_ok=True)
        self.tracks_dir.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('root', 'normal', 'trash')),
                    is_tray INTEGER NOT NULL DEFAULT 0 CHECK (is_tray IN (0, 1)),
                    position INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE RESTRICT,
                    entry_kind TEXT NOT NULL DEFAULT 'track' CHECK (entry_kind IN ('track', 'waypoint')),
                    display_name TEXT NOT NULL,
                    managed_rel_path TEXT NOT NULL UNIQUE,
                    original_source_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    duplicate_of_track_id INTEGER REFERENCES tracks(id),
                    metadata_json TEXT,
                    imported_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tracks_folder_id ON tracks(folder_id);
                CREATE INDEX IF NOT EXISTS idx_tracks_hash ON tracks(file_hash);

                CREATE TABLE IF NOT EXISTS preview_data_cache (
                    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    file_mtime_ns INTEGER NOT NULL,
                    file_size INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_hash TEXT NOT NULL
                );
                """
            )

            track_columns = {
                str(row["name"]) for row in conn.execute("PRAGMA table_info(tracks)").fetchall()
            }
            if "entry_kind" not in track_columns:
                conn.execute(
                    """
                    ALTER TABLE tracks
                    ADD COLUMN entry_kind TEXT NOT NULL DEFAULT 'track'
                    CHECK (entry_kind IN ('track', 'waypoint'))
                    """
                )

            folder_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(folders)")}
            if "is_tray" not in folder_columns:
                conn.execute("BEGIN")
                conn.execute("ALTER TABLE folders ADD COLUMN is_tray INTEGER NOT NULL DEFAULT 0")
                self._migrate_existing_trays(conn)

            now = _utc_now_iso()
            root_row = conn.execute(
                "SELECT id FROM folders WHERE kind = 'root' LIMIT 1"
            ).fetchone()
            if root_row is None:
                conn.execute(
                    """
                    INSERT INTO folders(parent_id, name, kind, position, created_at, updated_at)
                    VALUES (?, ?, 'root', 0, ?, ?)
                    """,
                    (None, "My Library", now, now),
                )
                root_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            else:
                root_id = int(root_row["id"])

            trash_row = conn.execute(
                "SELECT id FROM folders WHERE kind = 'trash' LIMIT 1"
            ).fetchone()
            if trash_row is None:
                conn.execute(
                    """
                    INSERT INTO folders(parent_id, name, kind, position, created_at, updated_at)
                    VALUES (?, ?, 'trash', 0, ?, ?)
                    """,
                    (root_id, "Trash", now, now),
                )

    def _migrate_existing_trays(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """SELECT f.id, f.kind,
                      EXISTS(SELECT 1 FROM folders child WHERE child.parent_id = f.id) AS has_children
               FROM folders f
               WHERE f.kind != 'trash' AND EXISTS(SELECT 1 FROM tracks t WHERE t.folder_id = f.id)"""
        ).fetchall()
        for row in rows:
            folder_id = int(row["id"])
            if row["kind"] == "normal" and not row["has_children"]:
                conn.execute("UPDATE folders SET is_tray = 1 WHERE id = ?", (folder_id,))
                continue
            name = "Items"
            number = 1
            while self._sibling_name_exists(conn, folder_id, name):
                name = f"Items ({number})"
                number += 1
            now = _utc_now_iso()
            cursor = conn.execute(
                """INSERT INTO folders(parent_id, name, kind, is_tray, position, created_at, updated_at)
                   VALUES (?, ?, 'normal', 1, 0, ?, ?)""",
                (folder_id, name, now, now),
            )
            conn.execute("UPDATE tracks SET folder_id = ? WHERE folder_id = ?", (cursor.lastrowid, folder_id))

    def list_folders(self) -> list[FolderRecord]:
        """Return all folders for tree rendering."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                  SELECT id, parent_id, name,
                      CASE WHEN is_tray = 1 THEN 'tray' ELSE kind END AS kind, position
                FROM folders
                ORDER BY
                    CASE kind WHEN 'root' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                    parent_id,
                    name COLLATE NOCASE
                """
            ).fetchall()
        return [
            FolderRecord(
                id=int(row["id"]),
                parent_id=int(row["parent_id"]) if row["parent_id"] is not None else None,
                name=str(row["name"]),
                kind=str(row["kind"]),
                position=int(row["position"]),
            )
            for row in rows
        ]

    @contextmanager
    def preview_data_cache(self) -> Iterator[PreviewDataCache]:
        conn = self._connect()
        cache = PreviewDataCache(conn)
        try:
            yield cache
        finally:
            try:
                cache.flush()
            finally:
                conn.close()

    def list_tracks(self, folder_id: int) -> list[TrackRecord]:
        """Return tracks assigned to a given folder."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                           file_hash, file_size, duplicate_of_track_id, entry_kind
                FROM tracks
                WHERE folder_id = ?
                ORDER BY display_name COLLATE NOCASE
                """,
                (folder_id,),
            ).fetchall()
        return [_track_record_from_row(row) for row in rows]

    def list_tracks_recursive(self, folder_id: int) -> list[TrackRecord]:
        """Return tracks from folder_id and all descendant folders."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                WITH RECURSIVE folder_tree(id) AS (
                    SELECT ?
                    UNION ALL
                    SELECT f.id
                    FROM folders f
                    JOIN folder_tree ft ON f.parent_id = ft.id
                )
                SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                           file_hash, file_size, duplicate_of_track_id, entry_kind
                FROM tracks
                WHERE folder_id IN (SELECT id FROM folder_tree)
                ORDER BY display_name COLLATE NOCASE
                """,
                (folder_id,),
            ).fetchall()
        return [_track_record_from_row(row) for row in rows]

    def get_track(self, track_id: int) -> TrackRecord:
        """Return a single track row by id."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                           file_hash, file_size, duplicate_of_track_id, entry_kind
                FROM tracks
                WHERE id = ?
                """,
                (track_id,),
            ).fetchone()

        if row is None:
            raise ValueError(f"Track id {track_id} not found")
        return _track_record_from_row(row)

    def get_track_managed_path(self, track_id: int) -> Path:
        """Resolve managed absolute file path for a track id."""
        track = self.get_track(track_id)
        return self.library_root / track.managed_rel_path

    def create_folder(self, name: str, parent_id: int) -> int:
        """Create a new normal folder under parent_id and return its id."""
        return self._create_folder_or_tray(name, parent_id, is_tray=False)

    def create_tray(self, name: str, parent_id: int) -> int:
        """Create a tray under a folder and return its id."""
        return self._create_folder_or_tray(name, parent_id, is_tray=True)

    def _create_folder_or_tray(self, name: str, parent_id: int, is_tray: bool) -> int:
        cleaned = _clean_folder_name(name)
        now = _utc_now_iso()

        with self._connect() as conn:
            self._require_folder_destination(conn, parent_id)

            if self._sibling_name_exists(conn, parent_id=parent_id, name=cleaned, is_tray=is_tray):
                label = "tray" if is_tray else "folder"
                raise ValueError(f"A {label} named '{cleaned}' already exists in this location")

            row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM folders WHERE parent_id = ?",
                (parent_id,),
            ).fetchone()
            next_pos = int(row["next_pos"])
            conn.execute(
                """
                INSERT INTO folders(parent_id, name, kind, is_tray, position, created_at, updated_at)
                VALUES (?, ?, 'normal', ?, ?, ?, ?)
                """,
                (parent_id, cleaned, int(is_tray), next_pos, now, now),
            )
            return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def convert_tray_to_folder(self, tray_id: int, reserved_names: set[str] | None = None) -> int:
        """Turn a tray into a folder, retaining its contents in an Items tray."""
        with self._connect() as conn:
            self._require_tray_destination(conn, tray_id)
            tray = conn.execute("SELECT parent_id, name FROM folders WHERE id = ?", (tray_id,)).fetchone()
            if self._sibling_name_exists(conn, tray["parent_id"], str(tray["name"]), is_tray=False):
                raise ValueError(f"A folder named '{tray['name']}' already exists in this location")
            now = _utc_now_iso()
            reserved = {name.casefold() for name in (reserved_names or set())}
            name = "Items"
            number = 1
            while name.casefold() in reserved or self._sibling_name_exists(conn, tray_id, name):
                name = f"Items ({number})"
                number += 1
            cursor = conn.execute(
                """INSERT INTO folders(parent_id, name, kind, is_tray, position, created_at, updated_at)
                   VALUES (?, ?, 'normal', 1, 0, ?, ?)""",
                (tray_id, name, now, now),
            )
            child_id = int(cursor.lastrowid)
            conn.execute("UPDATE tracks SET folder_id = ? WHERE folder_id = ?", (child_id, tray_id))
            conn.execute("UPDATE folders SET is_tray = 0, updated_at = ? WHERE id = ?", (now, tray_id))
            return child_id

    def rename_folder(self, folder_id: int, new_name: str) -> FolderRecord:
        """Rename a normal folder."""
        cleaned = _clean_folder_name(new_name)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, parent_id, name, CASE WHEN is_tray = 1 THEN 'tray' ELSE kind END AS kind, position FROM folders WHERE id = ?",
                (folder_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Folder id {folder_id} not found")

            current = FolderRecord(
                id=int(row["id"]),
                parent_id=int(row["parent_id"]) if row["parent_id"] is not None else None,
                name=str(row["name"]),
                kind=str(row["kind"]),
                position=int(row["position"]),
            )

            if current.kind in {"root", "trash"}:
                raise ValueError("Root and Trash folders cannot be renamed")

            if self._sibling_name_exists(
                conn,
                parent_id=current.parent_id,
                name=cleaned,
                exclude_folder_id=current.id,
                is_tray=current.kind == "tray",
            ):
                raise ValueError(f"A {current.kind if current.kind == 'tray' else 'folder'} named '{cleaned}' already exists in this location")

            conn.execute(
                "UPDATE folders SET name = ?, updated_at = ? WHERE id = ?",
                (cleaned, _utc_now_iso(), folder_id),
            )

            return FolderRecord(
                id=current.id,
                parent_id=current.parent_id,
                name=cleaned,
                kind=current.kind,
                position=current.position,
            )

    def delete_folder(self, folder_id: int) -> None:
        """Delete a normal folder subtree and move contained tracks to Trash first."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, parent_id, name, kind, position FROM folders WHERE id = ?",
                (folder_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Folder id {folder_id} not found")

            kind = str(row["kind"])
            if kind in {"root", "trash"}:
                raise ValueError("Root and Trash folders cannot be deleted")

            folder_ids = [
                int(subtree_row["id"])
                for subtree_row in conn.execute(
                    """
                    WITH RECURSIVE folder_tree(id) AS (
                        SELECT id FROM folders WHERE id = ?
                        UNION ALL
                        SELECT f.id
                        FROM folders f
                        JOIN folder_tree ft ON f.parent_id = ft.id
                    )
                    SELECT id FROM folder_tree
                    """,
                    (folder_id,),
                ).fetchall()
            ]

            trash_row = conn.execute(
                "SELECT id FROM folders WHERE kind = 'trash' LIMIT 1"
            ).fetchone()
            if trash_row is None:
                raise RuntimeError("Trash folder missing. Did you call initialize()?")
            trash_id = int(trash_row["id"])

            placeholders = ",".join("?" for _ in folder_ids)
            params: list[Any] = [trash_id, _utc_now_iso(), *folder_ids]
            conn.execute(
                f"UPDATE tracks SET folder_id = ?, updated_at = ? WHERE folder_id IN ({placeholders})",
                tuple(params),
            )
            conn.execute(
                f"DELETE FROM folders WHERE id IN ({placeholders})",
                tuple(folder_ids),
            )

    def move_folder(self, folder_id: int, new_parent_id: int | None) -> None:
        """Move a normal folder under a different parent."""
        if new_parent_id is None:
            raise ValueError("new_parent_id cannot be None")

        with self._connect() as conn:
            moving_row = conn.execute(
                "SELECT id, parent_id, name, kind, is_tray, position FROM folders WHERE id = ?",
                (folder_id,),
            ).fetchone()
            if moving_row is None:
                raise ValueError(f"Folder id {folder_id} not found")

            moving_kind = str(moving_row["kind"])
            if moving_kind in {"root", "trash"}:
                raise ValueError("Root and Trash folders cannot be moved")

            self._require_folder_destination(conn, new_parent_id)

            if int(moving_row["id"]) == new_parent_id:
                raise ValueError("Cannot move a folder into itself")

            if self._is_descendant(conn, ancestor_id=folder_id, candidate_descendant_id=new_parent_id):
                raise ValueError("Cannot move a folder into its own descendant")

            current_parent_id = (
                int(moving_row["parent_id"]) if moving_row["parent_id"] is not None else None
            )
            if current_parent_id == new_parent_id:
                return

            if self._sibling_name_exists(
                conn,
                parent_id=new_parent_id,
                name=str(moving_row["name"]),
                exclude_folder_id=folder_id,
                is_tray=bool(moving_row["is_tray"]),
            ):
                label = "tray" if moving_row["is_tray"] else "folder"
                raise ValueError(
                    f"Target location already has a {label} with the same name"
                )

            row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM folders WHERE parent_id = ?",
                (new_parent_id,),
            ).fetchone()
            next_pos = int(row["next_pos"])

            conn.execute(
                """
                UPDATE folders
                SET parent_id = ?, position = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_parent_id, next_pos, _utc_now_iso(), folder_id),
            )

    def move_track_to_folder(self, track_id: int, folder_id: int) -> None:
        """Move a track to another folder."""
        with self._connect() as conn:
            self._require_tray_destination(conn, folder_id)

            updated = conn.execute(
                "UPDATE tracks SET folder_id = ?, updated_at = ? WHERE id = ?",
                (folder_id, _utc_now_iso(), track_id),
            )
            if updated.rowcount == 0:
                raise ValueError(f"Track id {track_id} not found")

    def copy_items_to_folder(self, item_ids: list[int], folder_id: int) -> list[TrackRecord]:
        """Copy managed GPX items (tracks/waypoints) into another folder."""
        if not item_ids:
            return []

        with self._connect() as conn:
            self._require_tray_destination(conn, folder_id)

            copied: list[TrackRecord] = []
            for item_id in item_ids:
                row = conn.execute(
                    """
                    SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                           file_hash, file_size, duplicate_of_track_id, entry_kind, metadata_json
                    FROM tracks
                    WHERE id = ?
                    """,
                    (item_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"Track id {item_id} not found")

                source = _track_record_from_row(row)
                source_path = self.library_root / source.managed_rel_path
                if not source_path.exists():
                    raise FileNotFoundError(f"Managed GPX file missing: {source_path}")

                copied_display_name = _build_copy_track_display_name(
                    conn,
                    folder_id=folder_id,
                    source_display_name=source.display_name,
                )

                source_name = Path(copied_display_name)
                copied_filename = _build_managed_filename(
                    desired_stem=source_name.stem,
                    suffix=source_name.suffix if source_name.suffix else ".gpx",
                    target_dir=self.tracks_dir,
                    force_numbered=False,
                )
                copied_path = self.tracks_dir / copied_filename
                shutil.copy2(source_path, copied_path)

                copied_record = self._insert_item_from_managed_file(
                    conn=conn,
                    folder_id=folder_id,
                    managed_path=copied_path,
                    original_source_path=source.original_source_path,
                    entry_kind=source.entry_kind,
                    metadata_override=(str(row["metadata_json"]) if row["metadata_json"] is not None else None),
                    display_name_override=copied_display_name,
                )
                copied.append(copied_record)

            return copied

    def copy_folder_subtree(self, folder_id: int, new_parent_id: int) -> int:
        """Copy a normal folder subtree under new_parent_id and return new root folder id."""
        with self._connect() as conn:
            source_row = conn.execute(
                "SELECT id, parent_id, name, kind FROM folders WHERE id = ?",
                (folder_id,),
            ).fetchone()
            if source_row is None:
                raise ValueError(f"Folder id {folder_id} not found")

            if str(source_row["kind"]) in {"root", "trash"}:
                raise ValueError("Root and Trash folders cannot be copied")

            self._require_folder_destination(conn, new_parent_id)

            folder_ids = self._collect_subtree_ids(conn, folder_id)
            folder_rows = {
                int(row["id"]): row
                for row in conn.execute(
                    "SELECT id, parent_id, name, kind, is_tray FROM folders WHERE id IN ({})".format(
                        ",".join("?" for _ in folder_ids)
                    ),
                    tuple(folder_ids),
                ).fetchall()
            }

            id_map: dict[int, int] = {}
            copied_root_id: int | None = None
            now = _utc_now_iso()

            for old_folder_id in folder_ids:
                row = folder_rows[old_folder_id]
                old_parent = int(row["parent_id"]) if row["parent_id"] is not None else None
                source_name = str(row["name"])

                if old_folder_id == folder_id:
                    parent_id = new_parent_id
                    folder_name = _build_copy_folder_name(
                        conn, parent_id=parent_id, source_name=source_name, is_tray=bool(row["is_tray"])
                    )
                else:
                    if old_parent is None or old_parent not in id_map:
                        raise ValueError("Folder copy failed due to inconsistent subtree")
                    parent_id = id_map[old_parent]
                    folder_name = source_name

                pos_row = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM folders WHERE parent_id = ?",
                    (parent_id,),
                ).fetchone()
                next_pos = int(pos_row["next_pos"])

                conn.execute(
                    """
                    INSERT INTO folders(parent_id, name, kind, is_tray, position, created_at, updated_at)
                    VALUES (?, ?, 'normal', ?, ?, ?, ?)
                    """,
                    (parent_id, folder_name, int(row["is_tray"]), next_pos, now, now),
                )
                new_folder_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
                id_map[old_folder_id] = new_folder_id
                if copied_root_id is None:
                    copied_root_id = new_folder_id

                track_rows = conn.execute(
                    """
                    SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                           file_hash, file_size, duplicate_of_track_id, entry_kind, metadata_json
                    FROM tracks
                    WHERE folder_id = ?
                    ORDER BY display_name COLLATE NOCASE
                    """,
                    (old_folder_id,),
                ).fetchall()

                for track_row in track_rows:
                    source_track = _track_record_from_row(track_row)
                    source_path = self.library_root / source_track.managed_rel_path
                    if not source_path.exists():
                        continue

                    copied_display_name = _build_copy_track_display_name(
                        conn,
                        folder_id=new_folder_id,
                        source_display_name=source_track.display_name,
                    )
                    source_name_path = Path(copied_display_name)
                    copied_filename = _build_managed_filename(
                        desired_stem=source_name_path.stem,
                        suffix=source_name_path.suffix if source_name_path.suffix else ".gpx",
                        target_dir=self.tracks_dir,
                        force_numbered=False,
                    )
                    copied_path = self.tracks_dir / copied_filename
                    shutil.copy2(source_path, copied_path)

                    self._insert_item_from_managed_file(
                        conn=conn,
                        folder_id=new_folder_id,
                        managed_path=copied_path,
                        original_source_path=source_track.original_source_path,
                        entry_kind=source_track.entry_kind,
                        metadata_override=(
                            str(track_row["metadata_json"]) if track_row["metadata_json"] is not None else None
                        ),
                        display_name_override=copied_display_name,
                    )

            if copied_root_id is None:
                raise ValueError("Folder copy failed")
            return copied_root_id

    def import_gpx(self, source_path: Path, target_folder_id: int | None = None) -> ImportResult:
        """Copy a GPX file into managed storage and return the first imported track."""
        results = self.import_gpx_all(source_path, target_folder_id=target_folder_id)
        if not results:
            raise ValueError(f"No track data imported from {source_path}")
        return results[0]

    def import_gpx_all(
        self,
        source_path: Path,
        target_folder_id: int | None = None,
    ) -> list[ImportResult]:
        """Import all <trk> and <wpt> entries from a GPX file as separate managed files."""
        if target_folder_id is None:
            raise ValueError("Select a tray before importing GPX items")
        with self._connect() as conn:
            self._require_tray_destination(conn, target_folder_id)
        source = source_path.expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"GPX file not found: {source}")
        if source.suffix.lower() != ".gpx":
            raise ValueError(f"Expected .gpx file, got: {source}")

        import_entries = _extract_gpx_import_entries(source)
        if not import_entries:
            raise ValueError(f"No <trk> or <wpt> entries found in {source}")

        total_entries = len(import_entries)
        imported: list[ImportResult] = []

        with self._connect() as conn:
            folder_id = target_folder_id

            for idx, entry in enumerate(import_entries, start=1):
                file_hash = hashlib.sha256(entry.gpx_bytes).hexdigest()
                file_size = len(entry.gpx_bytes)

                duplicate_row = conn.execute(
                    "SELECT id FROM tracks WHERE file_hash = ? ORDER BY id LIMIT 1",
                    (file_hash,),
                ).fetchone()
                duplicate_of_track_id = (
                    int(duplicate_row["id"]) if duplicate_row is not None else None
                )

                entry_label = "waypoint" if entry.entry_kind == "waypoint" else "track"
                fallback_stem = (
                    source.stem if total_entries == 1 else f"{source.stem} {entry_label} {idx}"
                )
                managed_name = _build_managed_filename(
                    desired_stem=entry.name if entry.name is not None else fallback_stem,
                    suffix=".gpx",
                    target_dir=self.tracks_dir,
                    force_numbered=duplicate_of_track_id is not None,
                )
                managed_path = self.tracks_dir / managed_name
                managed_path.write_bytes(entry.gpx_bytes)

                metadata = _extract_basic_metadata(managed_path)
                now = _utc_now_iso()

                display_name = managed_name
                if total_entries > 1 and entry.name is not None and entry.name.strip():
                    display_name = entry.name.strip()

                conn.execute(
                    """
                    INSERT INTO tracks(
                        folder_id, entry_kind, display_name, managed_rel_path, original_source_path,
                        file_hash, file_size, duplicate_of_track_id, metadata_json, imported_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        folder_id,
                        entry.entry_kind,
                        display_name,
                        str(managed_path.relative_to(self.library_root)),
                        str(source),
                        file_hash,
                        file_size,
                        duplicate_of_track_id,
                        metadata,
                        now,
                        now,
                    ),
                )
                track_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

                imported.append(
                    ImportResult(
                        track_id=track_id,
                        display_name=display_name,
                        managed_path=managed_path,
                        file_hash=file_hash,
                        is_duplicate=duplicate_of_track_id is not None,
                        entry_kind=entry.entry_kind,
                    )
                )

        return imported

    def move_track_to_trash(self, track_id: int) -> None:
        """Move track assignment to the dedicated Trash folder."""
        trash_folder_id = self.get_trash_folder_id()
        with self._connect() as conn:
            conn.execute(
                "UPDATE tracks SET folder_id = ?, updated_at = ? WHERE id = ?",
                (trash_folder_id, _utc_now_iso(), track_id),
            )

    def get_folder(self, folder_id: int) -> FolderRecord:
        """Load a folder by id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, parent_id, name, CASE WHEN is_tray = 1 THEN 'tray' ELSE kind END AS kind, position FROM folders WHERE id = ?",
                (folder_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Folder id {folder_id} not found")

            return FolderRecord(
                id=int(row["id"]),
                parent_id=int(row["parent_id"]) if row["parent_id"] is not None else None,
                name=str(row["name"]),
                kind=str(row["kind"]),
                position=int(row["position"]),
            )

    def purge_track(self, track_id: int) -> None:
        """Permanently remove track metadata and managed file (Trash behavior)."""
        trash_folder_id = self.get_trash_folder_id()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT folder_id, managed_rel_path FROM tracks WHERE id = ?",
                (track_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Track id {track_id} not found")

            if int(row["folder_id"]) != trash_folder_id:
                raise ValueError("Track must be in Trash before permanent deletion")

            managed_path = self.library_root / str(row["managed_rel_path"])
            if managed_path.exists():
                managed_path.unlink()

            conn.execute("DELETE FROM preview_data_cache WHERE track_id = ?", (track_id,))
            conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))

    def export_track(self, track_id: int, destination_path: Path, overwrite: bool = False) -> Path:
        """Export a managed GPX track to a destination file path."""
        source_path = self.get_track_managed_path(track_id)
        if not source_path.exists():
            raise FileNotFoundError(f"Managed GPX file missing: {source_path}")

        target = destination_path.expanduser().resolve()
        if target.exists() and not overwrite:
            raise FileExistsError(f"Destination already exists: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        return target

    def rename_track(self, track_id: int, new_name: str) -> TrackRecord:
        """Rename physical managed file and update metadata row."""
        if not new_name.strip():
            raise ValueError("Track name cannot be empty")

        cleaned_stem = _sanitize_filename_stem(Path(new_name).stem)
        if not cleaned_stem:
            raise ValueError("Track name contains no valid characters")

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                       file_hash, file_size, duplicate_of_track_id
                FROM tracks
                WHERE id = ?
                """,
                (track_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Track id {track_id} not found")

            current = _track_record_from_row(row)
            old_path = self.library_root / current.managed_rel_path

            candidate_display_name = f"{cleaned_stem}{old_path.suffix if old_path.suffix else '.gpx'}"
            duplicate_name_row = conn.execute(
                """
                SELECT id
                FROM tracks
                WHERE id != ? AND lower(display_name) = lower(?)
                LIMIT 1
                """,
                (current.id, candidate_display_name),
            ).fetchone()
            if duplicate_name_row is not None:
                raise ValueError(
                    f"An item named '{candidate_display_name}' already exists in the library tree"
                )

            suffix = old_path.suffix if old_path.suffix else ".gpx"
            new_filename = _build_managed_filename(
                desired_stem=cleaned_stem,
                suffix=suffix,
                target_dir=self.tracks_dir,
                force_numbered=False,
                exclude_name=old_path.name,
            )
            new_path = self.tracks_dir / new_filename

            old_path.rename(new_path)
            now = _utc_now_iso()
            conn.execute(
                """
                UPDATE tracks
                SET display_name = ?, managed_rel_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_filename,
                    str(new_path.relative_to(self.library_root)),
                    now,
                    track_id,
                ),
            )

            return TrackRecord(
                id=current.id,
                folder_id=current.folder_id,
                display_name=new_filename,
                managed_rel_path=str(new_path.relative_to(self.library_root)),
                original_source_path=current.original_source_path,
                file_hash=current.file_hash,
                file_size=current.file_size,
                duplicate_of_track_id=current.duplicate_of_track_id,
                entry_kind=current.entry_kind,
            )

    def reverse_track(self, track_id: int) -> TrackRecord:
        """Reverse point order in managed GPX file and refresh stored metadata."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                       file_hash, file_size, duplicate_of_track_id
                FROM tracks
                WHERE id = ?
                """,
                (track_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Track id {track_id} not found")

            current = _track_record_from_row(row)
            managed_path = self.library_root / current.managed_rel_path
            if not managed_path.exists():
                raise FileNotFoundError(f"Managed GPX file missing: {managed_path}")

            reversed_points = _reverse_gpx_track_points(managed_path)
            if reversed_points == 0:
                raise ValueError("Track has no points to reverse")

            file_hash = _sha256(managed_path)
            file_size = managed_path.stat().st_size
            metadata = _extract_basic_metadata(managed_path)

            duplicate_row = conn.execute(
                "SELECT id FROM tracks WHERE file_hash = ? AND id != ? ORDER BY id LIMIT 1",
                (file_hash, track_id),
            ).fetchone()
            duplicate_of_track_id = int(duplicate_row["id"]) if duplicate_row is not None else None

            conn.execute(
                """
                UPDATE tracks
                SET file_hash = ?, file_size = ?, duplicate_of_track_id = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    file_hash,
                    file_size,
                    duplicate_of_track_id,
                    metadata,
                    _utc_now_iso(),
                    track_id,
                ),
            )

            return TrackRecord(
                id=current.id,
                folder_id=current.folder_id,
                display_name=current.display_name,
                managed_rel_path=current.managed_rel_path,
                original_source_path=current.original_source_path,
                file_hash=file_hash,
                file_size=file_size,
                duplicate_of_track_id=duplicate_of_track_id,
                entry_kind=current.entry_kind,
            )

    def get_track_color(self, track_id: int) -> str | None:
        """Return the per-track display color from GPX extensions, if set."""
        managed_path = self.get_track_managed_path(track_id)
        if not managed_path.exists():
            raise FileNotFoundError(f"Managed GPX file missing: {managed_path}")
        return _read_gpx_display_color(managed_path)

    def set_track_color(self, track_id: int, color_hex: str) -> TrackRecord:
        """Persist a per-track display color into GPX extensions and refresh metadata."""
        if not HEX_COLOR_RE.match(color_hex.strip()):
            raise ValueError("Track color must be a hex value like #12ABEF")

        normalized_color = color_hex.strip().upper()

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                       file_hash, file_size, duplicate_of_track_id
                FROM tracks
                WHERE id = ?
                """,
                (track_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Track id {track_id} not found")

            current = _track_record_from_row(row)
            managed_path = self.library_root / current.managed_rel_path
            if not managed_path.exists():
                raise FileNotFoundError(f"Managed GPX file missing: {managed_path}")

            _write_gpx_display_color(managed_path, normalized_color)

            file_hash = _sha256(managed_path)
            file_size = managed_path.stat().st_size
            metadata = _extract_basic_metadata(managed_path)

            duplicate_row = conn.execute(
                "SELECT id FROM tracks WHERE file_hash = ? AND id != ? ORDER BY id LIMIT 1",
                (file_hash, track_id),
            ).fetchone()
            duplicate_of_track_id = int(duplicate_row["id"]) if duplicate_row is not None else None

            conn.execute(
                """
                UPDATE tracks
                SET file_hash = ?, file_size = ?, duplicate_of_track_id = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    file_hash,
                    file_size,
                    duplicate_of_track_id,
                    metadata,
                    _utc_now_iso(),
                    track_id,
                ),
            )

            return TrackRecord(
                id=current.id,
                folder_id=current.folder_id,
                display_name=current.display_name,
                managed_rel_path=current.managed_rel_path,
                original_source_path=current.original_source_path,
                file_hash=file_hash,
                file_size=file_size,
                duplicate_of_track_id=duplicate_of_track_id,
                entry_kind=current.entry_kind,
            )

    def trim_track(self, track_id: int, start_percent: float, end_percent: float) -> TrackRecord:
        """Create a trimmed copy of a track based on start/end percentages."""
        start_value = float(start_percent)
        end_value = float(end_percent)
        if start_value < 0 or end_value > 100 or end_value <= start_value:
            raise ValueError("Trim range must satisfy 0 <= start < end <= 100")

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                       file_hash, file_size, duplicate_of_track_id
                FROM tracks
                WHERE id = ?
                """,
                (track_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Track id {track_id} not found")

            current = _track_record_from_row(row)
            source_path = self.library_root / current.managed_rel_path
            if not source_path.exists():
                raise FileNotFoundError(f"Managed GPX file missing: {source_path}")

            source_name = Path(current.display_name)
            trimmed_name = _build_managed_filename(
                desired_stem=f"{source_name.stem} (trim)",
                suffix=source_name.suffix if source_name.suffix else ".gpx",
                target_dir=self.tracks_dir,
                force_numbered=False,
            )
            trimmed_path = self.tracks_dir / trimmed_name
            shutil.copy2(source_path, trimmed_path)

            try:
                kept_points = _trim_gpx_track_points(trimmed_path, start_value, end_value)
                if kept_points < 2:
                    raise ValueError("Trim result must contain at least two track points")

                file_hash = _sha256(trimmed_path)
                file_size = trimmed_path.stat().st_size
                metadata = _extract_basic_metadata(trimmed_path)
                now = _utc_now_iso()

                duplicate_row = conn.execute(
                    "SELECT id FROM tracks WHERE file_hash = ? ORDER BY id LIMIT 1",
                    (file_hash,),
                ).fetchone()
                duplicate_of_track_id = (
                    int(duplicate_row["id"])
                    if duplicate_row is not None
                    else None
                )

                conn.execute(
                    """
                    INSERT INTO tracks(
                        folder_id, entry_kind, display_name, managed_rel_path, original_source_path,
                        file_hash, file_size, duplicate_of_track_id, metadata_json, imported_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current.folder_id,
                        "track",
                        trimmed_name,
                        str(trimmed_path.relative_to(self.library_root)),
                        current.original_source_path,
                        file_hash,
                        file_size,
                        duplicate_of_track_id,
                        metadata,
                        now,
                        now,
                    ),
                )
                new_track_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            except Exception:
                if trimmed_path.exists():
                    trimmed_path.unlink()
                raise

            return TrackRecord(
                id=new_track_id,
                folder_id=current.folder_id,
                display_name=trimmed_name,
                managed_rel_path=str(trimmed_path.relative_to(self.library_root)),
                original_source_path=current.original_source_path,
                file_hash=file_hash,
                file_size=file_size,
                duplicate_of_track_id=duplicate_of_track_id,
                entry_kind="track",
            )

    def split_track(self, track_id: int, split_percent: float) -> tuple[TrackRecord, TrackRecord]:
        """Create two split copies of a track based on a split percentage."""
        split_value = float(split_percent)
        if split_value <= 0.0 or split_value >= 100.0:
            raise ValueError("Split percent must be between 0 and 100")

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                       file_hash, file_size, duplicate_of_track_id
                FROM tracks
                WHERE id = ?
                """,
                (track_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Track id {track_id} not found")

            current = _track_record_from_row(row)
            source_path = self.library_root / current.managed_rel_path
            if not source_path.exists():
                raise FileNotFoundError(f"Managed GPX file missing: {source_path}")

            source_name = Path(current.display_name)
            split_a_name = _build_managed_filename(
                desired_stem=f"{source_name.stem} (split A)",
                suffix=source_name.suffix if source_name.suffix else ".gpx",
                target_dir=self.tracks_dir,
                force_numbered=False,
            )
            split_b_name = _build_managed_filename(
                desired_stem=f"{source_name.stem} (split B)",
                suffix=source_name.suffix if source_name.suffix else ".gpx",
                target_dir=self.tracks_dir,
                force_numbered=False,
            )

            split_a_path = self.tracks_dir / split_a_name
            split_b_path = self.tracks_dir / split_b_name
            shutil.copy2(source_path, split_a_path)
            shutil.copy2(source_path, split_b_path)

            try:
                kept_a, kept_b = _split_gpx_track_points(
                    source_path,
                    split_a_path,
                    split_b_path,
                    split_value,
                )
                if kept_a < 2 or kept_b < 2:
                    raise ValueError("Split result must contain at least two points per output")

                record_a = self._insert_item_from_managed_file(
                    conn=conn,
                    folder_id=current.folder_id,
                    managed_path=split_a_path,
                    original_source_path=current.original_source_path,
                )
                record_b = self._insert_item_from_managed_file(
                    conn=conn,
                    folder_id=current.folder_id,
                    managed_path=split_b_path,
                    original_source_path=current.original_source_path,
                )
            except Exception:
                if split_a_path.exists():
                    split_a_path.unlink()
                if split_b_path.exists():
                    split_b_path.unlink()
                raise

            return record_a, record_b

    def merge_tracks(self, track_ids: list[int]) -> TrackRecord:
        """Create a merged copy from multiple source tracks."""
        if len(track_ids) < 2:
            raise ValueError("Please select at least two tracks to merge")

        with self._connect() as conn:
            source_tracks: list[TrackRecord] = []
            for track_id in track_ids:
                row = conn.execute(
                    """
                    SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                           file_hash, file_size, duplicate_of_track_id
                    FROM tracks
                    WHERE id = ?
                    """,
                    (track_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"Track id {track_id} not found")
                source_tracks.append(_track_record_from_row(row))

            primary = source_tracks[0]
            primary_path = self.library_root / primary.managed_rel_path
            if not primary_path.exists():
                raise FileNotFoundError(f"Managed GPX file missing: {primary_path}")

            source_name = Path(primary.display_name)
            merged_name = _build_managed_filename(
                desired_stem=f"{source_name.stem} (merge)",
                suffix=source_name.suffix if source_name.suffix else ".gpx",
                target_dir=self.tracks_dir,
                force_numbered=False,
            )
            merged_path = self.tracks_dir / merged_name
            shutil.copy2(primary_path, merged_path)

            try:
                merged_points: list[ET.Element] = []
                for source in source_tracks:
                    source_path = self.library_root / source.managed_rel_path
                    if not source_path.exists():
                        raise FileNotFoundError(f"Managed GPX file missing: {source_path}")

                    points = _extract_gpx_track_points(source_path)
                    if len(points) < 2:
                        raise ValueError("Each track must contain at least two points to merge")

                    if merged_points and _same_track_point(merged_points[-1], points[0]):
                        merged_points.extend(points[1:])
                    else:
                        merged_points.extend(points)

                if len(merged_points) < 2:
                    raise ValueError("Merged track has too few points")

                _replace_gpx_track_points(merged_path, merged_points)
                return self._insert_item_from_managed_file(
                    conn=conn,
                    folder_id=primary.folder_id,
                    managed_path=merged_path,
                    original_source_path=primary.original_source_path,
                )
            except Exception:
                if merged_path.exists():
                    merged_path.unlink()
                raise

    def build_reverse_preview(self, track_id: int) -> Path:
        """Create a temporary GPX preview for reverse operation."""
        source_path = self.get_track_managed_path(track_id)
        if not source_path.exists():
            raise FileNotFoundError(f"Managed GPX file missing: {source_path}")

        preview_path = _create_temp_gpx_copy(source_path)
        try:
            _reverse_gpx_track_points(preview_path)
            return preview_path
        except Exception:
            if preview_path.exists():
                preview_path.unlink()
            raise

    def build_trim_preview(self, track_id: int, start_percent: float, end_percent: float) -> Path:
        """Create a temporary GPX preview for trim operation."""
        source_path = self.get_track_managed_path(track_id)
        if not source_path.exists():
            raise FileNotFoundError(f"Managed GPX file missing: {source_path}")

        preview_path = _create_temp_gpx_copy(source_path)
        try:
            kept_points = _trim_gpx_track_points(preview_path, float(start_percent), float(end_percent))
            if kept_points < 2:
                raise ValueError("Trim result must contain at least two points")
            return preview_path
        except Exception:
            if preview_path.exists():
                preview_path.unlink()
            raise

    def build_split_preview(self, track_id: int, split_percent: float) -> tuple[Path, Path]:
        """Create temporary GPX previews for split operation."""
        source_path = self.get_track_managed_path(track_id)
        if not source_path.exists():
            raise FileNotFoundError(f"Managed GPX file missing: {source_path}")

        preview_a_path = _create_temp_gpx_copy(source_path)
        preview_b_path = _create_temp_gpx_copy(source_path)
        try:
            kept_a, kept_b = _split_gpx_track_points(
                source_path,
                preview_a_path,
                preview_b_path,
                float(split_percent),
            )
            if kept_a < 2 or kept_b < 2:
                raise ValueError("Split result must contain at least two points per output")
            return preview_a_path, preview_b_path
        except Exception:
            if preview_a_path.exists():
                preview_a_path.unlink()
            if preview_b_path.exists():
                preview_b_path.unlink()
            raise

    def build_merge_preview(self, track_ids: list[int]) -> Path:
        """Create a temporary GPX preview for merge operation."""
        if len(track_ids) < 2:
            raise ValueError("Please select at least two tracks to merge")

        with self._connect() as conn:
            source_tracks: list[TrackRecord] = []
            for track_id in track_ids:
                row = conn.execute(
                    """
                    SELECT id, folder_id, display_name, managed_rel_path, original_source_path,
                           file_hash, file_size, duplicate_of_track_id
                    FROM tracks
                    WHERE id = ?
                    """,
                    (track_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"Track id {track_id} not found")
                source_tracks.append(_track_record_from_row(row))

        primary_path = self.library_root / source_tracks[0].managed_rel_path
        if not primary_path.exists():
            raise FileNotFoundError(f"Managed GPX file missing: {primary_path}")

        preview_path = _create_temp_gpx_copy(primary_path)
        try:
            merged_points: list[ET.Element] = []
            for source in source_tracks:
                source_path = self.library_root / source.managed_rel_path
                if not source_path.exists():
                    raise FileNotFoundError(f"Managed GPX file missing: {source_path}")

                points = _extract_gpx_track_points(source_path)
                if len(points) < 2:
                    raise ValueError("Each track must contain at least two points to merge")

                if merged_points and _same_track_point(merged_points[-1], points[0]):
                    merged_points.extend(points[1:])
                else:
                    merged_points.extend(points)

            if len(merged_points) < 2:
                raise ValueError("Merged track has too few points")

            _replace_gpx_track_points(preview_path, merged_points)
            return preview_path
        except Exception:
            if preview_path.exists():
                preview_path.unlink()
            raise

    def _insert_item_from_managed_file(
        self,
        conn: sqlite3.Connection,
        folder_id: int,
        managed_path: Path,
        original_source_path: str,
        entry_kind: str = "track",
        metadata_override: str | None = None,
        display_name_override: str | None = None,
    ) -> TrackRecord:
        file_hash = _sha256(managed_path)
        file_size = managed_path.stat().st_size
        metadata = metadata_override if metadata_override is not None else _extract_basic_metadata(managed_path)
        now = _utc_now_iso()

        duplicate_row = conn.execute(
            "SELECT id FROM tracks WHERE file_hash = ? ORDER BY id LIMIT 1",
            (file_hash,),
        ).fetchone()
        duplicate_of_track_id = int(duplicate_row["id"]) if duplicate_row is not None else None

        conn.execute(
            """
            INSERT INTO tracks(
                folder_id, entry_kind, display_name, managed_rel_path, original_source_path,
                file_hash, file_size, duplicate_of_track_id, metadata_json, imported_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                folder_id,
                entry_kind,
                display_name_override if display_name_override is not None else managed_path.name,
                str(managed_path.relative_to(self.library_root)),
                original_source_path,
                file_hash,
                file_size,
                duplicate_of_track_id,
                metadata,
                now,
                now,
            ),
        )
        track_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        return TrackRecord(
            id=track_id,
            folder_id=folder_id,
            display_name=display_name_override if display_name_override is not None else managed_path.name,
            managed_rel_path=str(managed_path.relative_to(self.library_root)),
            original_source_path=original_source_path,
            file_hash=file_hash,
            file_size=file_size,
            duplicate_of_track_id=duplicate_of_track_id,
            entry_kind=entry_kind,
        )

    def get_root_folder_id(self) -> int:
        """Return root folder id."""
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM folders WHERE kind = 'root' LIMIT 1").fetchone()
            if row is None:
                raise RuntimeError("Root folder missing. Did you call initialize()?")
            return int(row["id"])

    def get_trash_folder_id(self) -> int:
        """Return trash folder id."""
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM folders WHERE kind = 'trash' LIMIT 1").fetchone()
            if row is None:
                raise RuntimeError("Trash folder missing. Did you call initialize()?")
            return int(row["id"])

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _require_folder_destination(self, conn: sqlite3.Connection, folder_id: int) -> None:
        row = conn.execute("SELECT kind, is_tray FROM folders WHERE id = ?", (folder_id,)).fetchone()
        if row is None:
            raise ValueError(f"Folder id {folder_id} not found")
        if row["kind"] == "trash" or row["is_tray"]:
            raise ValueError("Folders and trays can only be placed inside folders")

    def _require_tray_destination(self, conn: sqlite3.Connection, folder_id: int) -> None:
        row = conn.execute("SELECT kind, is_tray FROM folders WHERE id = ?", (folder_id,)).fetchone()
        if row is None:
            raise ValueError(f"Folder id {folder_id} not found")
        if row["kind"] != "normal" or not row["is_tray"]:
            raise ValueError("Tracks and waypoints can only be placed inside trays")

    def _collect_subtree_ids(self, conn: sqlite3.Connection, root_id: int) -> list[int]:
        children_map: dict[int | None, list[int]] = {}
        rows = conn.execute("SELECT id, parent_id FROM folders").fetchall()
        for row in rows:
            parent_id = int(row["parent_id"]) if row["parent_id"] is not None else None
            children_map.setdefault(parent_id, []).append(int(row["id"]))

        ordered: list[int] = []
        stack = [root_id]
        while stack:
            current = stack.pop()
            ordered.append(current)
            for child_id in children_map.get(current, []):
                stack.append(child_id)
        return ordered

    def _is_descendant(
        self,
        conn: sqlite3.Connection,
        ancestor_id: int,
        candidate_descendant_id: int,
    ) -> bool:
        stack = [ancestor_id]
        while stack:
            current = stack.pop()
            rows = conn.execute(
                "SELECT id FROM folders WHERE parent_id = ?",
                (current,),
            ).fetchall()
            for row in rows:
                child = int(row["id"])
                if child == candidate_descendant_id:
                    return True
                stack.append(child)
        return False

    def _sibling_name_exists(
        self,
        conn: sqlite3.Connection,
        parent_id: int | None,
        name: str,
        exclude_folder_id: int | None = None,
        is_tray: bool | None = None,
    ) -> bool:
        if parent_id is None:
            query = "SELECT id FROM folders WHERE parent_id IS NULL AND lower(name) = lower(?)"
            params: list[Any] = [name]
        else:
            query = "SELECT id FROM folders WHERE parent_id = ? AND lower(name) = lower(?)"
            params = [parent_id, name]

        if is_tray is not None:
            query += " AND is_tray = ?"
            params.append(int(is_tray))

        if exclude_folder_id is not None:
            query += " AND id != ?"
            params.append(exclude_folder_id)

        row = conn.execute(query, tuple(params)).fetchone()
        return row is not None


def _track_record_from_row(row: sqlite3.Row) -> TrackRecord:
    entry_kind = "track"
    if "entry_kind" in row.keys() and row["entry_kind"] is not None:
        entry_kind = str(row["entry_kind"])

    return TrackRecord(
        id=int(row["id"]),
        folder_id=int(row["folder_id"]),
        display_name=str(row["display_name"]),
        managed_rel_path=str(row["managed_rel_path"]),
        original_source_path=str(row["original_source_path"]),
        file_hash=str(row["file_hash"]),
        file_size=int(row["file_size"]),
        duplicate_of_track_id=(
            int(row["duplicate_of_track_id"])
            if row["duplicate_of_track_id"] is not None
            else None
        ),
        entry_kind=entry_kind,
    )


def _clean_folder_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Folder name cannot be empty")
    return cleaned


def _sanitize_filename_stem(stem: str) -> str:
    sanitized = INVALID_FILENAME_CHARS.sub("_", stem.strip())
    sanitized = re.sub(r"\s+", " ", sanitized)
    sanitized = sanitized.strip(" .")
    if not sanitized:
        return "track"
    return sanitized


def _build_managed_filename(
    desired_stem: str,
    suffix: str,
    target_dir: Path,
    force_numbered: bool,
    exclude_name: str | None = None,
) -> str:
    stem = _sanitize_filename_stem(desired_stem)

    def exists(filename: str) -> bool:
        if exclude_name is not None and filename == exclude_name:
            return False
        return (target_dir / filename).exists()

    if not force_numbered:
        candidate = f"{stem}{suffix}"
        if not exists(candidate):
            return candidate

    index = 1
    while True:
        candidate = f"{stem} ({index}){suffix}"
        if not exists(candidate):
            return candidate
        index += 1


def _split_copy_suffix(name: str) -> tuple[str, int | None]:
    match = COPY_SUFFIX_RE.match(name)
    if match is None:
        return name, None
    return match.group(1), int(match.group(2))


def _build_copy_track_display_name(
    conn: sqlite3.Connection,
    folder_id: int,
    source_display_name: str,
) -> str:
    source_path = Path(source_display_name)
    stem, number = _split_copy_suffix(source_path.stem)
    base_stem = stem.strip() or source_path.stem
    suffix = source_path.suffix

    rows = conn.execute("SELECT display_name FROM tracks").fetchall()
    existing = {str(row["display_name"]).lower() for row in rows}

    start_number = 1 if number is None else number + 1
    copy_number = start_number
    while True:
        candidate = f"{base_stem} ({copy_number}){suffix}"
        if candidate.lower() not in existing:
            return candidate
        copy_number += 1


def _build_copy_folder_name(conn: sqlite3.Connection, parent_id: int, source_name: str, is_tray: bool) -> str:
    rows = conn.execute(
        "SELECT name FROM folders WHERE parent_id = ? AND is_tray = ?",
        (parent_id, int(is_tray)),
    ).fetchall()
    existing = {str(row["name"]).lower() for row in rows}

    if source_name.lower() not in existing:
        return source_name

    stem, number = _split_copy_suffix(source_name)
    base_name = stem.strip() or source_name

    start_number = 1 if number is None else number + 1
    copy_number = start_number
    while True:
        candidate = f"{base_name} ({copy_number})"
        if candidate.lower() not in existing:
            return candidate
        copy_number += 1


def _extract_basic_metadata(gpx_path: Path) -> str:
    analyzer = GPXAnalyzer()
    analyzer.read_gpx_file(gpx_path)
    points = analyzer.get_track_points()
    stats = analyzer.get_ride_stats_pretty(track_points=points)

    start_time = points[0].time.isoformat() if points and points[0].time is not None else None
    end_time = points[-1].time.isoformat() if points and points[-1].time is not None else None

    metadata: dict[str, Any] = {
        "track_points": len(points),
        "total_distance_km": stats["total_distance_km"],
        "moving_time_hms": stats["moving_time_hms"],
        "average_speed_kmh": stats["average_speed_kmh"],
        "start_time": start_time,
        "end_time": end_time,
        "display_color": _read_gpx_display_color(gpx_path),
    }
    return json.dumps(metadata, sort_keys=True)


def _sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reverse_gpx_track_points(gpx_path: Path) -> int:
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", maxsplit=1)[0][1:]
        trkseg_path = f".//{{{namespace}}}trkseg"
        trkpt_path = f"{{{namespace}}}trkpt"
    else:
        trkseg_path = ".//trkseg"
        trkpt_path = "trkpt"

    reversed_points = 0
    for segment in root.findall(trkseg_path):
        points = list(segment.findall(trkpt_path))
        if not points:
            continue

        for point in points:
            segment.remove(point)
        for point in reversed(points):
            segment.append(point)
        reversed_points += len(points)

    tree.write(gpx_path, encoding="utf-8", xml_declaration=True)
    return reversed_points


def _trim_gpx_track_points(gpx_path: Path, start_percent: float, end_percent: float) -> int:
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", maxsplit=1)[0][1:]
        trk_path = f".//{{{namespace}}}trk"
        trkseg_tag = f"{{{namespace}}}trkseg"
        trkpt_tag = f"{{{namespace}}}trkpt"
    else:
        trk_path = ".//trk"
        trkseg_tag = "trkseg"
        trkpt_tag = "trkpt"

    track = root.find(trk_path)
    if track is None:
        raise ValueError("GPX track element not found")

    segments = track.findall(trkseg_tag)
    all_points: list[ET.Element] = []
    for segment in segments:
        all_points.extend(list(segment.findall(trkpt_tag)))

    total_points = len(all_points)
    if total_points < 2:
        raise ValueError("Track has too few points to trim")

    max_index = total_points - 1
    start_index = int(math.floor((start_percent / 100.0) * max_index))
    end_index = int(math.ceil((end_percent / 100.0) * max_index))
    end_index = min(end_index, max_index)
    if end_index <= start_index:
        end_index = min(max_index, start_index + 1)
    if end_index <= start_index:
        raise ValueError("Trim range leaves no points")

    kept_points = all_points[start_index : end_index + 1]

    for segment in segments:
        track.remove(segment)

    new_segment = ET.SubElement(track, trkseg_tag)
    for point in kept_points:
        new_segment.append(point)

    tree.write(gpx_path, encoding="utf-8", xml_declaration=True)
    return len(kept_points)


def _split_gpx_track_points(
    source_gpx_path: Path,
    output_a_path: Path,
    output_b_path: Path,
    split_percent: float,
) -> tuple[int, int]:
    source_tree = ET.parse(source_gpx_path)
    source_root = source_tree.getroot()

    if source_root.tag.startswith("{"):
        namespace = source_root.tag.split("}", maxsplit=1)[0][1:]
        trk_path = f".//{{{namespace}}}trk"
        trkseg_tag = f"{{{namespace}}}trkseg"
        trkpt_tag = f"{{{namespace}}}trkpt"
    else:
        trk_path = ".//trk"
        trkseg_tag = "trkseg"
        trkpt_tag = "trkpt"

    source_track = source_root.find(trk_path)
    if source_track is None:
        raise ValueError("GPX track element not found")

    source_segments = source_track.findall(trkseg_tag)
    all_points: list[ET.Element] = []
    for segment in source_segments:
        all_points.extend(list(segment.findall(trkpt_tag)))

    total_points = len(all_points)
    if total_points < 3:
        raise ValueError("Track has too few points to split")

    max_index = total_points - 1
    split_index = int(round((split_percent / 100.0) * max_index))
    split_index = max(1, min(max_index - 1, split_index))

    points_a = all_points[: split_index + 1]
    points_b = all_points[split_index:]

    _replace_gpx_track_points(output_a_path, points_a)
    _replace_gpx_track_points(output_b_path, points_b)
    return len(points_a), len(points_b)


def _replace_gpx_track_points(target_path: Path, points: list[ET.Element]) -> None:
    tree = ET.parse(target_path)
    root = tree.getroot()

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", maxsplit=1)[0][1:]
        trk_path = f".//{{{namespace}}}trk"
        trkseg_tag = f"{{{namespace}}}trkseg"
    else:
        trk_path = ".//trk"
        trkseg_tag = "trkseg"

    track = root.find(trk_path)
    if track is None:
        raise ValueError("GPX track element not found")

    for segment in list(track.findall(trkseg_tag)):
        track.remove(segment)

    new_segment = ET.SubElement(track, trkseg_tag)
    for point in points:
        new_segment.append(copy.deepcopy(point))

    tree.write(target_path, encoding="utf-8", xml_declaration=True)


def _extract_gpx_track_points(gpx_path: Path) -> list[ET.Element]:
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", maxsplit=1)[0][1:]
        trk_path = f".//{{{namespace}}}trk"
        trkseg_tag = f"{{{namespace}}}trkseg"
        trkpt_tag = f"{{{namespace}}}trkpt"
    else:
        trk_path = ".//trk"
        trkseg_tag = "trkseg"
        trkpt_tag = "trkpt"

    track = root.find(trk_path)
    if track is None:
        raise ValueError("GPX track element not found")

    points: list[ET.Element] = []
    for segment in track.findall(trkseg_tag):
        points.extend(list(segment.findall(trkpt_tag)))

    return points


def _create_temp_gpx_copy(source_path: Path) -> Path:
    temp_handle = tempfile.NamedTemporaryFile(suffix=".gpx", delete=False)
    temp_path = Path(temp_handle.name)
    temp_handle.close()
    shutil.copy2(source_path, temp_path)
    return temp_path


def _same_track_point(left: ET.Element, right: ET.Element) -> bool:
    left_ele = left.find("ele")
    right_ele = right.find("ele")
    left_time = left.find("time")
    right_time = right.find("time")

    return (
        left.get("lat") == right.get("lat")
        and left.get("lon") == right.get("lon")
        and (left_ele.text if left_ele is not None else None)
        == (right_ele.text if right_ele is not None else None)
        and (left_time.text if left_time is not None else None)
        == (right_time.text if right_time is not None else None)
    )


@dataclass(frozen=True)
class _TrackImportEntry:
    name: str | None
    gpx_bytes: bytes
    entry_kind: str


def _extract_gpx_import_entries(source_path: Path) -> list[_TrackImportEntry]:
    tree = ET.parse(source_path)
    root = tree.getroot()

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", maxsplit=1)[0][1:]
        trk_path = f".//{{{namespace}}}trk"
        trk_name_tag = f"{{{namespace}}}name"
        wpt_path = f".//{{{namespace}}}wpt"
        wpt_name_tag = f"{{{namespace}}}name"
    else:
        namespace = None
        trk_path = ".//trk"
        trk_name_tag = "name"
        wpt_path = ".//wpt"
        wpt_name_tag = "name"

    entries: list[_TrackImportEntry] = []

    def add_entries(elements: list[ET.Element], name_tag: str, entry_kind: str) -> None:
        for element in elements:
            name_element = element.find(name_tag)
            entry_name = None
            if name_element is not None and name_element.text:
                entry_name = name_element.text.strip()

            cloned_root = copy.deepcopy(root)
            for cloned_track in cloned_root.findall(trk_path):
                parent = _find_xml_parent(cloned_root, cloned_track)
                if parent is not None:
                    parent.remove(cloned_track)

            for cloned_waypoint in cloned_root.findall(wpt_path):
                parent = _find_xml_parent(cloned_root, cloned_waypoint)
                if parent is not None:
                    parent.remove(cloned_waypoint)

            cloned_root.append(copy.deepcopy(element))

            buffer = BytesIO()
            ET.ElementTree(cloned_root).write(buffer, encoding="utf-8", xml_declaration=True)
            entries.append(
                _TrackImportEntry(
                    name=entry_name,
                    gpx_bytes=buffer.getvalue(),
                    entry_kind=entry_kind,
                )
            )

    add_entries(root.findall(trk_path), trk_name_tag, "track")
    add_entries(root.findall(wpt_path), wpt_name_tag, "waypoint")

    return entries


def _find_xml_parent(root: ET.Element, target: ET.Element) -> ET.Element | None:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                return parent
    return None


def _read_gpx_display_color(gpx_path: Path) -> str | None:
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    track = root.find(f".//{{{GPX_NS}}}trk")
    if track is None:
        return None

    extensions = track.find(f"{{{GPX_NS}}}extensions")
    if extensions is None:
        return None

    color_element = extensions.find(f"{{{GPX_ORGANIZER_EXT_NS}}}displayColor")
    if color_element is None or color_element.text is None:
        return None

    color = color_element.text.strip().upper()
    if not HEX_COLOR_RE.match(color):
        return None
    return color


def _write_gpx_display_color(gpx_path: Path, color_hex: str) -> None:
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    track = root.find(f".//{{{GPX_NS}}}trk")
    if track is None:
        raise ValueError("GPX track element not found")

    extensions = track.find(f"{{{GPX_NS}}}extensions")
    if extensions is None:
        extensions = ET.SubElement(track, f"{{{GPX_NS}}}extensions")

    color_element = extensions.find(f"{{{GPX_ORGANIZER_EXT_NS}}}displayColor")
    if color_element is None:
        color_element = ET.SubElement(extensions, f"{{{GPX_ORGANIZER_EXT_NS}}}displayColor")

    color_element.text = color_hex
    tree.write(gpx_path, encoding="utf-8", xml_declaration=True)

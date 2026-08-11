# Milestone 1 Specification

## Scope
This milestone defines the organizer-first MVP behavior and UI contract before coding deeper features.

## 1. Functional Requirements (Organizer-First MVP)

### Library and Storage
- FR-001: The app shall create or open a managed library root folder selected by the user.
- FR-002: Imported GPX files shall be copied into the managed library root (original source files remain untouched).
- FR-003: The app shall persist library structure and file references in SQLite.
- FR-004: On restart, the app shall restore the same folder tree and track assignments.

### Folder Tree
- FR-010: The app shall support creating folders and nested subfolders.
- FR-011: Folder names shall be editable in place (rename).
- FR-012: Folder deletion shall require confirmation.
- FR-013: Deleting a folder shall also remove all nested child folders from the library tree model.
- FR-014: The app shall support moving folders by drag and drop with cycle prevention (cannot drop into own descendant).

### Track Organization
- FR-020: The app shall support importing one or multiple GPX files.
- FR-021: Imported tracks shall appear in the selected folder list.
- FR-022: Tracks shall be movable by drag and drop between folders.
- FR-023: The same physical GPX shall not be duplicated in storage when only moved within the tree.
- FR-024: Track rename shall immediately rename the physical file in managed storage and update metadata.
- FR-025: Import shall detect duplicate GPX content by file hash.
- FR-026: If duplicate content is intentionally imported again, the managed filename shall receive an incremented suffix like (1), (2), etc.

### Selection and Display
- FR-030: Clicking a track item shall load and display it on the map panel.
- FR-031: The map shall auto-fit to track bounds after load.
- FR-032: Start and end markers shall be displayed.
- FR-033: Invalid GPX files shall show a clear error toast/dialog and not crash the app.

### Basic Editing Toolbox (first set)
- FR-040: The app shall provide trim, split, merge, reverse operations.
- FR-041: Editing shall be non-destructive by default (preview + apply).
- FR-042: The user shall be able to save edited output as a new GPX.

## 2. Interaction Rules

### Tree and Drag-and-Drop
- IR-001: Dragging a track onto a folder moves the track to that folder.
- IR-002: Dragging a folder onto another folder moves it as a child, unless invalid (self/descendant).
- IR-003: Dropping onto empty tree background is ignored.
- IR-004: During drag, valid targets are highlighted; invalid targets show forbidden cursor.
- IR-005: Multi-select track drag moves all selected tracks together.

### Rename Rules
- IR-010: F2 or slow double click enters rename mode.
- IR-011: Empty names are rejected.
- IR-012: Duplicate sibling folder names are rejected with message.
- IR-013: Disallowed filesystem characters are sanitized for managed filenames.

### Delete Rules
- IR-020: Delete action opens confirmation dialog.
- IR-021: Deleting a track moves it to a dedicated Trash folder.
- IR-022: Deleting a track from the Trash folder permanently removes metadata and the managed file.
- IR-023: Deleting a folder removes folder assignment for contained items per selected policy.

## 3. UI Layout (PySide6)

### Main Window Regions
- Left panel: Library tree (folders/subfolders)
- Center panel: Track list for selected folder
- Right panel: Map display (Qt WebEngine with Leaflet)
- Bottom status bar: import/edit status, warnings, progress

### Primary Menus
- File: New Library, Open Library, Import GPX, Export GPX, Exit
- Edit: Rename, Delete, Undo, Redo
- Track: Trim, Split, Merge, Reverse
- View: Toggle Panels, Refresh Map
- Help: About

### Context Menus
- Tree folder context:
  - New Folder
  - Rename
  - Delete
  - Import GPX Here
- Track list item context:
  - Show on Map
  - Rename
  - Move To...
  - Trim
  - Split
  - Reverse
  - Delete

## 4. Data Model (Milestone 1 Level)
- Folder(id, parent_id, name, position, created_at, updated_at)
- Track(id, folder_id, display_name, managed_path, original_source_path, imported_at, updated_at)
- AppState(id, last_opened_library_path, window_layout_blob, updated_at)

## 5. Non-Functional Requirements
- NFR-001: Startup with existing library under 2 seconds for 1,000 tracks on typical Linux desktop.
- NFR-002: Drag-and-drop operations should feel immediate (<100 ms UI feedback).
- NFR-003: Import pipeline should show progress for large batch imports.
- NFR-004: App should not block UI thread during parsing/import.

## 6. Milestone 1 Exit Criteria
- Requirements and interactions are accepted.
- No unresolved ambiguity in organizer workflows.
- Ready to begin Milestone 2 implementation (PySide6 app shell).

## 7. Resolved Product Decisions
- RD-001: Deleted tracks are moved to a dedicated Trash folder.
- RD-002: Deleting tracks inside Trash permanently deletes metadata and managed GPX files.
- RD-003: Track rename immediately renames the physical managed file.
- RD-004: Import detects duplicates by hash.
- RD-005: Intentional real duplicates get suffix naming such as (1), (2), etc.

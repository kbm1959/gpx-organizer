# GPX Organizer App Roadmap

## Vision
Build a Python desktop app (similar in spirit to Garmin BaseCamp) to organize GPX files in a folder/subfolder tree with drag-and-drop, display selected tracks on a map, and provide editing and analysis tools.

## Locked Product Decisions
- GUI framework: PySide6
- First release target: Linux
- Final product target: Linux and Windows
- Map tiles for first release: online only
- Offline mode: add later for final product
- Managed storage model: app-managed library folder
- Priority order: organizer features first, analysis features second
- First editing tools: trim, split, merge, reverse
- Delete policy: move deleted tracks to a dedicated Trash folder; deleting from Trash permanently removes metadata and managed file
- Rename policy: rename the physical managed GPX file immediately
- Duplicate import policy: detect duplicates by file hash; if duplicate content should be kept intentionally, append (n) to filename

## Architecture Direction
- UI: PySide6
- Embedded map: Qt WebEngine + Leaflet (loaded in a web view)
- GPX parsing and core metrics: reuse and evolve logic from existing code in gpx_analyzer.py
- Persistent app data: SQLite (library tree, item metadata, app state)
- Managed library root: user-selected folder where imported GPX files are copied and tracked

## Milestones

### Milestone 1: Product Scope and UX Blueprint
Goal:
- Define exact behavior for tree organization, drag-and-drop operations, and map interactions.

Deliverables:
- Final MVP scope list (Must/Should/Later)
- UI layout spec for main window and panels
- Interaction rules for rename, move, copy, delete, and selection behavior

Acceptance criteria:
- No ambiguity remains in organizer workflows and first map-display workflow.

### Milestone 2: App Skeleton and Tooling
Goal:
- Create runnable PySide6 app shell with module structure and quality baseline.

Deliverables:
- Initial package layout
- Main window with placeholder panels (tree, list, map)
- Logging and configuration setup
- Test framework baseline

Acceptance criteria:
- App launches on Linux and closes cleanly; smoke tests pass.

### Milestone 3: Data Model and Managed Library Core
Goal:
- Implement persistent library model and managed file storage.

Deliverables:
- SQLite schema for folders, items, metadata
- Library root initialization flow
- Import pipeline that copies GPX files into managed library folder
- Basic metadata extraction and index update

Acceptance criteria:
- Imported files survive restarts and tree structure is restored exactly.

### Milestone 4: Organizer UI (Tree + Drag and Drop)
Goal:
- Deliver primary organizer workflows first.

Deliverables:
- Renamable folders/subfolders in a tree
- Track list display per selected folder
- Drag-and-drop move of tracks and folders where valid
- Context menu actions (new folder, rename, delete, move)

Acceptance criteria:
- Typical organization tasks can be completed without terminal/manual file edits.

### Milestone 5: Map Display Integration
Goal:
- Show clicked GPX file on an interactive map.

Deliverables:
- Track render on selection
- Auto-fit bounds
- Start/end markers and optional segment styling
- Basic layer controls

Acceptance criteria:
- Selecting any valid GPX in library displays correctly and reliably.

### Milestone 6: Track Editing Tools (First Set)
Goal:
- Add non-destructive editing for first selected operations.

Deliverables:
- Trim tool
- Split tool
- Merge tool
- Reverse tool
- Preview + apply + undo/redo model
- Export/save edited GPX

Acceptance criteria:
- All four edits work on real sample files and preserve valid GPX output.

### Milestone 7: Analysis Features (After Organizer)
Goal:
- Add analysis after core organizer and basic editing are stable.

Deliverables:
- Summary stats panel (distance, duration, speed, ascent/descent)
- Rest-stop and segment-level views
- Basic chart/profile views as a first step

Acceptance criteria:
- Analysis results are reproducible for sample tracks and visible in UI.

### Milestone 8: Cross-Platform and Packaging
Goal:
- Prepare Linux release and path to Windows release.

Deliverables:
- Linux packaging and install instructions
- File/path compatibility hardening for Windows
- Platform test checklist

Acceptance criteria:
- Linux release candidate is installable and documented.

### Milestone 9: Final Product Add-ons
Goal:
- Complete features planned for final product.

Deliverables:
- Offline map mode
- Windows release packaging
- Performance and UX polish

Acceptance criteria:
- Linux + Windows builds available, with online and offline map modes.

## MVP Boundary (First Usable Version)
- Managed library folder setup and import
- Folder/subfolder tree and drag-and-drop organization
- Click-to-display GPX on map (online tiles)
- Editing tools: trim, split, merge, reverse
- Basic metadata and persistence

## Step-by-Step Execution Plan
1. Implement Milestone 1 outputs in documents and simple wireframe sketches.
2. Build Milestone 2 shell (runnable PySide6 app with placeholder panels).
3. Implement Milestones 3-4 (organizer core first).
4. Add Milestone 5 map display.
5. Add Milestone 6 editing tools.
6. Add Milestone 7 analysis features.
7. Package Linux release, then extend for Windows and offline maps.

## Immediate Next Implementation Step
Start Milestone 1 by producing:
- Functional requirements list for organizer-first MVP
- Detailed interaction rules for tree and drag-and-drop
- Main window layout spec tied to PySide6 widgets

# GPX Organizer
This is a Python App which I am developing to get rid of my Windows Computer and Garmin Basecamp, which I preferably use to store and organize all my GPX tracks which I record during my bicycle tours.

It already has the basic funcionality of Garmin basecamp, though some features are still missing, since development is going on.
So this is almost a Beta version.

Actually I am developing and running it on a Raspberry Pi 5 with bookworm installed. 
The final Version should run on most Unix derivates as well as on Windows Computers.

You are welcome to test it and any hints concerning bugs or improvements are appreciated.

Folder previews cache simplified track and waypoint data in the library database.
The first preview of an existing folder builds the cache in the background; later
previews can reuse it, including after restarting the app. Original GPX files are
not altered by preview caching.

Tracks and waypoints are stored in trays. Folders contain folders and trays;
trays cannot contain other folders or trays. Create a tray from a folder's
context menu and select it to import GPX files. A folder and a tray may share
the same name within a parent; names must be unique within each type.
Folder-tree imports start from
the selected tray and create or merge the imported tree alongside it; a mixed
source directory stores its directly contained GPX files in an Items tray.
Trash remains the special container for deleted items.

Existing folders containing items are migrated automatically on opening the
library. If a folder also contains subfolders, its existing items are moved to
an Items tray within that folder. Managed GPX files are not moved or deleted.
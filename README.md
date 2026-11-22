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
The New Tray action uses one dialog for the tray count and names. It defaults to
one blank name field and adjusts the number of fields as the count changes; the
batch is created only if all names are valid and unique.
Folder-tree imports start from
the selected tray and create or merge the imported tree alongside it; a mixed
source directory stores its directly contained GPX files in an Items tray.
Trash remains the special container for deleted items.

Tracks whose cached total distance per track point falls below the configurable
Track preference (default 2 m/point) are highlighted bold red in the list.

Existing folders containing items are migrated automatically on opening the
library. If a folder also contains subfolders, its existing items are moved to
an Items tray within that folder. Managed GPX files are not moved or deleted.

The Properties tab summarizes selected tracks, or all tracks in the list when
none are selected. Waypoints are excluded. Track properties are stored in the
library database; older entries are analyzed in the background when needed.
Elapsed time is summed within GPX segments. Rest radius, minimum duration, and
the endpoint-distance multiplier are configurable under Rest Stop in Track
preferences (defaults: 2 m, 60 seconds, and 10× the radius). The first and last
detected rests must be at least that distance from the track endpoints. The map
and Properties tab use the same rest calculation; map markers are numbered in
track order.
Driving time excludes detected rest periods. Average
speeds are distance-weighted over the corresponding elapsed or driving time.
The bounding area is the spherical rectangle enclosing all included points.
Start and end show the track endpoints, or the earliest and latest endpoints
for multiple tracks. Offset-aware timestamps use the time zone configured in
General preferences (Europe/Berlin by default), including daylight saving time;
timestamps without an offset are shown with an unknown time zone. The map uses
the same time-zone setting. Gradients use
the same sampled segments and 0.5 m distance threshold as the map tooltips;
GPS elevation noise can still produce extreme values. Missing or inconsistent
timestamps are shown as unavailable.
Comments, Links and Graph tabs are reserved for later implementation.
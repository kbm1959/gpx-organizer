"""Map rendering service abstraction for Milestone 5 integration."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import html
import json
import math
from pathlib import Path
from typing import Callable, Protocol
import re
import xml.etree.ElementTree as ET

from gpx_analyzer import GPXAnalyzer, TrackPoint
from .library_store import PreviewDataCache


DEFAULT_RESPONSIVE_THRESHOLD_PX = 900
DEFAULT_BICYCLE_ROUTE_TILE_URL = "https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png"
DEFAULT_BICYCLE_ROUTE_ATTRIBUTION = (
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors '
  '| &copy; <a href="https://waymarkedtrails.org">Waymarked Trails</a>'
)
DEFAULT_REST_STOP_COLOR = "#AB47BC"
DEFAULT_REST_STOP_SIZE_PX = 6
DEFAULT_TRACK_COLOR = "#007F5F"
DEFAULT_PREVIEW_LIGHTENING_FACTOR = 0.0
DEFAULT_DISTANCE_MARKER_COLOR = "#37474F"
DEFAULT_DISTANCE_MARKER_BORDER_COLOR = "#FF0000"
DEFAULT_DISTANCE_MARKER_SIZE_PX = 5
DEFAULT_START_SYMBOL_COLOR = "#2E7D32"
DEFAULT_START_SYMBOL_SIZE_PX = 12
DEFAULT_START_SYMBOL_SHAPE = "square"
DEFAULT_STOP_SYMBOL_COLOR = "#C62828"
DEFAULT_STOP_SYMBOL_SIZE_PX = 12
DEFAULT_STOP_SYMBOL_SHAPE = "square"
DEFAULT_DIRECTION_ARROW_COLOR = "#1F1F1F"
DEFAULT_DIRECTION_ARROW_COUNT = 10
DEFAULT_DIRECTION_ARROW_SIZE_PX = 12
DEFAULT_TRACK_POINT_COLOR = "#000000"
DEFAULT_TRACK_POINT_SIZE_PX = 1
TRACK_RENDER_MAX_POINTS = 3500
PREVIEW_TOTAL_POINT_BUDGET = 7000
PREVIEW_MIN_POINTS_PER_TRACK = 8
PREVIEW_MAX_POINTS_PER_TRACK = 320

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
GPX_NS = "http://www.topografix.com/GPX/1/1"
GPX_ORGANIZER_EXT_NS = "https://gpx-organizer.dev/xmlns/1"


@dataclass(frozen=True)
class RenderedMap:
    """HTML payload produced by a map rendering service."""

    title: str
    html: str


class MapService(Protocol):
    """Interface for converting track data into embeddable map HTML."""

    def render_track(
      self,
      track_path: Path,
      track_name: str,
      initial_overlays: dict[str, bool] | None = None,
    ) -> RenderedMap:
        """Render a GPX track into HTML for the embedded map panel."""


class LeafletMapService:
    """Leaflet-based map service using OpenStreetMap online tiles."""

    def __init__(
        self,
        responsive_threshold_px: int = DEFAULT_RESPONSIVE_THRESHOLD_PX,
        bicycle_route_tile_url: str = DEFAULT_BICYCLE_ROUTE_TILE_URL,
        bicycle_route_attribution: str = DEFAULT_BICYCLE_ROUTE_ATTRIBUTION,
        rest_stop_color: str = DEFAULT_REST_STOP_COLOR,
        rest_stop_size_px: int = DEFAULT_REST_STOP_SIZE_PX,
        default_track_color: str = DEFAULT_TRACK_COLOR,
        preview_lightening_factor: float = DEFAULT_PREVIEW_LIGHTENING_FACTOR,
        distance_marker_color: str = DEFAULT_DISTANCE_MARKER_COLOR,
        distance_marker_border_color: str = DEFAULT_DISTANCE_MARKER_BORDER_COLOR,
        distance_marker_size_px: int = DEFAULT_DISTANCE_MARKER_SIZE_PX,
        start_symbol_color: str = DEFAULT_START_SYMBOL_COLOR,
        start_symbol_size_px: int = DEFAULT_START_SYMBOL_SIZE_PX,
        start_symbol_shape: str = DEFAULT_START_SYMBOL_SHAPE,
        stop_symbol_color: str = DEFAULT_STOP_SYMBOL_COLOR,
        stop_symbol_size_px: int = DEFAULT_STOP_SYMBOL_SIZE_PX,
        stop_symbol_shape: str = DEFAULT_STOP_SYMBOL_SHAPE,
        direction_arrow_color: str = DEFAULT_DIRECTION_ARROW_COLOR,
        direction_arrow_count: int = DEFAULT_DIRECTION_ARROW_COUNT,
        direction_arrow_size_px: int = DEFAULT_DIRECTION_ARROW_SIZE_PX,
        track_point_color: str = DEFAULT_TRACK_POINT_COLOR,
        track_point_size_px: int = DEFAULT_TRACK_POINT_SIZE_PX,
    ) -> None:
        self.responsive_threshold_px = max(320, int(responsive_threshold_px))
        self.bicycle_route_tile_url = bicycle_route_tile_url
        self.bicycle_route_attribution = bicycle_route_attribution
        self.rest_stop_color = _normalize_hex_color(rest_stop_color, DEFAULT_REST_STOP_COLOR)
        self.rest_stop_size_px = max(2, min(24, int(rest_stop_size_px)))
        self.default_track_color = _normalize_hex_color(default_track_color, DEFAULT_TRACK_COLOR)
        self.preview_lightening_factor = max(0.0, min(1.0, float(preview_lightening_factor)))
        self.distance_marker_color = _normalize_hex_color(
            distance_marker_color,
            DEFAULT_DISTANCE_MARKER_COLOR,
        )
        self.distance_marker_border_color = _normalize_hex_color(
          distance_marker_border_color,
          DEFAULT_DISTANCE_MARKER_BORDER_COLOR,
        )
        self.distance_marker_size_px = max(2, min(24, int(distance_marker_size_px)))
        self.start_symbol_color = _normalize_hex_color(start_symbol_color, DEFAULT_START_SYMBOL_COLOR)
        self.start_symbol_size_px = max(4, min(40, int(start_symbol_size_px)))
        self.start_symbol_shape = (
          start_symbol_shape if start_symbol_shape in {"circle", "square"} else DEFAULT_START_SYMBOL_SHAPE
        )
        self.stop_symbol_color = _normalize_hex_color(stop_symbol_color, DEFAULT_STOP_SYMBOL_COLOR)
        self.stop_symbol_size_px = max(4, min(40, int(stop_symbol_size_px)))
        self.stop_symbol_shape = (
          stop_symbol_shape if stop_symbol_shape in {"circle", "square"} else DEFAULT_STOP_SYMBOL_SHAPE
        )
        self.direction_arrow_color = _normalize_hex_color(
          direction_arrow_color,
          DEFAULT_DIRECTION_ARROW_COLOR,
        )
        self.direction_arrow_count = max(1, min(200, int(direction_arrow_count)))
        self.direction_arrow_size_px = max(8, min(40, int(direction_arrow_size_px)))
        self.track_point_color = _normalize_hex_color(track_point_color, DEFAULT_TRACK_POINT_COLOR)
        self.track_point_size_px = max(1, min(10, int(track_point_size_px)))
        self.track_delete_uses_permanent = False

    def render_track(
      self,
      track_path: Path,
      track_name: str,
      initial_overlays: dict[str, bool] | None = None,
    ) -> RenderedMap:
      payload = self._build_track_payload(track_path, track_name)
      if payload is None:
            return RenderedMap(
                title=track_name,
                html=self._build_message_html(
                    title="Track has no points",
                    message=f"No track points found in {track_name}.",
                ),
            )

      return RenderedMap(
        title=track_name,
        html=self._build_leaflet_html(payload, initial_overlays=initial_overlays),
      )

    def render_waypoint(self, waypoint_path: Path, waypoint_name: str) -> RenderedMap:
      """Render waypoint GPX as marker-only map."""
      waypoints = _extract_gpx_waypoints(waypoint_path)
      if not waypoints:
        return RenderedMap(
          title=waypoint_name,
          html=self._build_message_html(
            title="Waypoint has no coordinates",
            message=f"No waypoint coordinates found in {waypoint_name}.",
          ),
        )

      return RenderedMap(
        title=waypoint_name,
        html=self._build_waypoint_html(waypoints, waypoint_name),
      )

    def render_track_lines_preview(
      self,
      tracks: list[
        tuple[Path, str]
        | tuple[int, Path, str]
        | tuple[int, Path, str, str]
      ],
      progress: Callable[[int, int], None] | None = None,
      on_error: Callable[[str, str], None] | None = None,
      cache: PreviewDataCache | None = None,
    ) -> RenderedMap:
      """Render a lightweight overview of multiple tracks and waypoints."""
      track_count_estimate = max(1, len(tracks))
      points_per_track = PREVIEW_TOTAL_POINT_BUDGET // track_count_estimate
      points_per_track = max(PREVIEW_MIN_POINTS_PER_TRACK, points_per_track)
      points_per_track = min(PREVIEW_MAX_POINTS_PER_TRACK, points_per_track)

      entries: list[dict[str, object]] = []
      waypoints: list[dict[str, object]] = []
      for index, track_entry in enumerate(tracks):
        if progress is not None:
          progress(index, len(tracks))
        if len(track_entry) == 4:
          track_id, track_path, track_name, hover_label = track_entry
        elif len(track_entry) == 3:
          track_id, track_path, track_name = track_entry
          hover_label = track_name
        else:
          track_id = None
          track_path, track_name = track_entry
          hover_label = track_name

        try:
          data = cache.get(track_id, track_path) if cache is not None and track_id is not None else None
          if data is None:
            root = ET.parse(track_path).getroot()
            coordinates = _extract_gpx_line_coordinates(track_path, root)
            waypoint_points = _extract_gpx_waypoints(track_path, root) if len(coordinates) < 2 else []
            track_color = _read_track_display_color(track_path, root) if len(coordinates) >= 2 else None
            data = {
              "coordinates": _downsample_coordinates(coordinates, max_points=PREVIEW_MAX_POINTS_PER_TRACK),
              "waypoints": waypoint_points,
              "color": track_color,
            }
            if cache is not None and track_id is not None:
              cache.put(track_id, track_path, data)
          coordinates = data["coordinates"]
          if len(coordinates) < 2:
            waypoint_points = data["waypoints"]
            if not waypoint_points and on_error is not None:
              on_error(track_name, "No track or waypoint coordinates")
            for waypoint in waypoint_points:
              waypoints.append(
                {
                  "trackId": track_id,
                  "name": track_name,
                  "hoverLabel": str(hover_label),
                  "lat": waypoint["lat"],
                  "lon": waypoint["lon"],
                  "waypointName": waypoint.get("name") or track_name,
                }
              )
            continue
          track_color = data.get("color") or self.default_track_color
        except Exception as exc:
          if on_error is not None:
            on_error(track_name, str(exc) or type(exc).__name__)
          # Keep overview usable even if one managed GPX file is malformed.
          continue

        entries.append(
          {
            "name": track_name,
            "trackId": track_id,
            "hoverLabel": str(hover_label),
            "trackColor": _lighten_hex_color(track_color, factor=self.preview_lightening_factor),
            "coordinates": _downsample_coordinates(coordinates, max_points=points_per_track),
          }
        )

      if progress is not None:
        progress(len(tracks), len(tracks))

      if not entries and not waypoints:
        return self.render_placeholder(
          title="Map Preview",
          message="No tracks or waypoints in this folder view.",
        )

      return RenderedMap(
        title="Track Overview",
        html=self._build_track_lines_preview_html(entries, waypoints),
      )

    def _build_waypoint_html(self, waypoints: list[dict[str, object]], title: str) -> str:
        waypoints_json = json.dumps(waypoints)
        waypoint_icon_url_json = json.dumps(_load_waypoint_icon_data_url())
        safe_title = html.escape(title)
        return f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <link
      rel=\"stylesheet\"
      href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\"
      integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\"
      crossorigin=\"\"
    />
    <style>
      html, body, #map {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
      .legend {{
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        top: 12px;
        z-index: 1000;
        background: rgba(255, 255, 255, 0.92);
        border-radius: 8px;
        padding: 8px 10px;
        font-family: sans-serif;
        font-size: 12px;
        text-align: center;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.15);
      }}
    </style>
  </head>
  <body>
    <div id=\"map\"></div>
    <div class=\"legend\">{safe_title}</div>
    <script
      src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"
      integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\"
      crossorigin=\"\"
    ></script>
    <script>
      const waypoints = {waypoints_json};
      const waypointIconUrl = {waypoint_icon_url_json};
      const map = L.map("map");
      L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
      }}).addTo(map);
      L.control.scale({{ imperial: false }}).addTo(map);

      const group = L.featureGroup().addTo(map);
      const waypointIcon = waypointIconUrl
        ? L.icon({{
            iconUrl: waypointIconUrl,
            iconSize: [24, 24],
            iconAnchor: [12, 24],
            tooltipAnchor: [0, -22],
          }})
        : null;

      waypoints.forEach((waypoint) => {{
        const marker = waypointIcon
          ? L.marker([waypoint.lat, waypoint.lon], {{ icon: waypointIcon }})
          : L.circleMarker([waypoint.lat, waypoint.lon], {{
              radius: 7,
              color: "#B71C1C",
              fillColor: "#E53935",
              fillOpacity: 0.85,
              weight: 2,
            }});
        marker.addTo(group);
        marker.bindTooltip(waypoint.name || "Waypoint", {{ sticky: true }});
      }});

      window.__gpxFitTrack = function() {{
        const bounds = group.getBounds();
        if (bounds && bounds.isValid()) {{
          map.fitBounds(bounds, {{ padding: [24, 24], maxZoom: 16 }});
        }}
      }};
      window.__gpxFitTrack();
    </script>
  </body>
</html>
"""

    def render_tracks_with_overlays(
      self,
      tracks: list[tuple[Path, str]],
      initial_overlays: dict[str, bool] | None = None,
    ) -> RenderedMap:
      """Render one or more selected tracks with standard overlay controls."""
      payloads: list[dict[str, object]] = []
      for track_path, track_name in tracks:
        payload = self._build_track_payload(track_path, track_name)
        if payload is not None:
          payloads.append(payload)

      if not payloads:
        return self.render_placeholder(
          title="Map Preview",
          message="No valid track points found for selected tracks.",
        )

      if len(payloads) == 1:
        return RenderedMap(
          title=str(payloads[0]["trackName"]),
          html=self._build_leaflet_html(payloads[0], initial_overlays=initial_overlays),
        )

      return RenderedMap(
        title=f"{len(payloads)} selected tracks",
        html=self._build_multi_track_leaflet_html(payloads, initial_overlays=initial_overlays),
      )

    def _build_track_payload(self, track_path: Path, track_name: str) -> dict[str, object] | None:
      analyzer = GPXAnalyzer()
      analyzer.read_gpx_file(track_path)
      points = analyzer.get_track_points()

      if not points:
        return None

      render_points = _downsample_track_points(points, max_points=TRACK_RENDER_MAX_POINTS)

      stats = analyzer.calculate_ride_stats(track_points=points)
      rest_stops = analyzer.find_rest_stops(
        track_points=points,
        radius_m=5.0,
        min_duration_s=120.0,
      )

      coordinates = [
        {
          "lat": point.latitude,
          "lon": point.longitude,
          "ele": point.elevation_m,
          "time": point.time.isoformat() if point.time is not None else None,
        }
        for point in render_points
      ]

      start = coordinates[0]
      end = coordinates[-1]
      distance_markers = self._build_distance_markers(render_points, interval_km=10.0)
      direction_arrows = self._build_direction_arrows(
          render_points,
          arrow_count=self.direction_arrow_count,
      )
      total_distance_km = round(stats["total_distance_m"] / 1000.0, 2)
      track_color = _read_track_display_color(track_path) or self.default_track_color

      payload = {
          "coordinates": coordinates,
          "start": start,
          "end": end,
          "trackName": track_name,
        "totalDistanceKm": total_distance_km,
        "trackColor": track_color,
        "restStopColor": self.rest_stop_color,
        "restStopSizePx": self.rest_stop_size_px,
        "distanceMarkerColor": self.distance_marker_color,
        "distanceMarkerBorderColor": self.distance_marker_border_color,
        "distanceMarkerSizePx": self.distance_marker_size_px,
        "startSymbolColor": self.start_symbol_color,
        "startSymbolSizePx": self.start_symbol_size_px,
        "startSymbolShape": self.start_symbol_shape,
        "stopSymbolColor": self.stop_symbol_color,
        "stopSymbolSizePx": self.stop_symbol_size_px,
        "stopSymbolShape": self.stop_symbol_shape,
        "directionArrowColor": self.direction_arrow_color,
        "directionArrowCount": self.direction_arrow_count,
        "directionArrowSizePx": self.direction_arrow_size_px,
        "trackPointColor": self.track_point_color,
        "trackPointSizePx": self.track_point_size_px,
        "distanceMarkers": distance_markers,
        "directionArrows": direction_arrows,
        "restStops": [
          {
            "lat": stop.latitude,
            "lon": stop.longitude,
            "startTime": stop.start_time.isoformat(),
            "endTime": stop.end_time.isoformat(),
            "durationMin": round(stop.duration_s / 60.0, 1),
            "elevation": stop.elevation_m,
          }
          for stop in rest_stops
        ],
      }

      return payload

    def render_placeholder(self, title: str, message: str) -> RenderedMap:
        """Create a simple placeholder HTML payload."""
        return RenderedMap(title=title, html=self._build_message_html(title, message))

    def _build_message_html(self, title: str, message: str) -> str:
        safe_title = html.escape(title)
        safe_message = html.escape(message)
        return f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <style>
      body {{ font-family: sans-serif; margin: 2rem; }}
      h2 {{ margin-bottom: 0.75rem; }}
    </style>
  </head>
  <body>
    <h2>{safe_title}</h2>
    <p>{safe_message}</p>
  </body>
</html>
"""

    def _build_leaflet_html(
      self,
      payload: dict[str, object],
      initial_overlays: dict[str, bool] | None = None,
    ) -> str:
        payload_json = json.dumps(payload)
        initial_overlays_json = json.dumps(initial_overlays or {})
        responsive_threshold_px = self.responsive_threshold_px
        bicycle_route_tile_url_json = json.dumps(self.bicycle_route_tile_url)
        bicycle_route_attribution_json = json.dumps(self.bicycle_route_attribution)
        track_delete_action = (
            "track_delete_permanently"
            if self.track_delete_uses_permanent
            else "track_move_to_trash"
        )
        track_delete_label = (
            "Delete permanently"
            if self.track_delete_uses_permanent
            else "Move to Trash"
        )
        return f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <link
      rel=\"stylesheet\"
      href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\"
      integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\"
      crossorigin=\"\"
    />
    <style>
      html, body, #map {{
        width: 100%;
        height: 100%;
        margin: 0;
        padding: 0;
      }}
      .legend {{
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        top: 12px;
        z-index: 1000;
        background: rgba(255, 255, 255, 0.92);
        border-radius: 8px;
        padding: 8px 10px;
        font-family: sans-serif;
        font-size: 12px;
        line-height: 1.3;
        text-align: center;
        max-width: min(70vw, 440px);
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.15);
      }}

      @media (max-width: {responsive_threshold_px}px) {{
        .legend {{
          max-width: min(88vw, 420px);
          font-size: 11px;
          padding: 6px 8px;
        }}
      }}

      .map-point-menu {{
        position: absolute;
        z-index: 2200;
        display: none;
        background: rgba(255, 255, 255, 0.97);
        border: 1px solid #b9b9b9;
        border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.22);
        min-width: 140px;
        overflow: hidden;
        font-family: sans-serif;
        font-size: 12px;
      }}

      .map-point-menu button {{
        width: 100%;
        border: none;
        background: transparent;
        padding: 8px 10px;
        text-align: left;
        cursor: pointer;
      }}

      .map-point-menu button:hover {{
        background: rgba(0, 127, 95, 0.12);
      }}

      .map-point-menu button:disabled {{
        opacity: 0.45;
        cursor: not-allowed;
      }}

      .map-point-menu button:disabled:hover {{
        background: transparent;
      }}
    </style>
  </head>
  <body>
    <div id=\"map\"></div>
    <div class=\"legend\"><strong id=\"track-title\"></strong><br/>Milestone 6 map preview</div>
    <div id=\"point-menu\" class=\"map-point-menu\">
      <button data-action="track_rename">Rename</button>
      <button data-action="track_reverse">Reverse</button>
      <button data-action="track_export">Export GPX</button>
      <button data-action="track_set_color">Set color</button>
      <button data-action="{track_delete_action}">{track_delete_label}</button>
      <button disabled style="opacity:0.4; cursor:default;">----------------</button>
      <button data-action="split" class="point-action">Split</button>
      <button data-action="trim_start" class="point-action">Trim Start</button>
      <button data-action="trim_end" class="point-action">Trim End</button>
    </div>
    <script
      src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"
      integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\"
      crossorigin=\"\"
    ></script>
    <script>
      const payload = {payload_json};
      const initialOverlays = {initial_overlays_json};
      const responsiveThresholdPx = {responsive_threshold_px};
      const map = L.map("map");
      L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
      }}).addTo(map);
      L.control.scale({{ imperial: false }}).addTo(map);

      const bicycleRoutesLayer = L.tileLayer({bicycle_route_tile_url_json}, {{
        maxZoom: 18,
        opacity: 0.85,
        attribution: {bicycle_route_attribution_json}
      }});

      const coordinates = payload.coordinates;
      const latLngs = coordinates.map((p) => [p.lat, p.lon]);

      const layers = {{
        track: L.featureGroup().addTo(map),
        gradient: L.featureGroup().addTo(map),
        points: L.layerGroup(),
        endpoints: L.layerGroup().addTo(map),
        distance: L.layerGroup().addTo(map),
        rests: L.layerGroup().addTo(map),
        directionArrows: L.layerGroup().addTo(map),
      }};
      const layerRegistry = {{
        gradient: layers.gradient,
        points: layers.points,
        endpoints: layers.endpoints,
        distance: layers.distance,
        directionArrows: layers.directionArrows,
        rests: layers.rests,
        bicycleRoutes: bicycleRoutesLayer,
      }};
      let suppressOverlayEvents = true;

      function haversineMeters(a, b) {{
        const toRad = (deg) => (deg * Math.PI) / 180;
        const earth = 6371000;
        const dLat = toRad(b.lat - a.lat);
        const dLon = toRad(b.lon - a.lon);
        const lat1 = toRad(a.lat);
        const lat2 = toRad(b.lat);
        const x =
          Math.sin(dLat / 2) ** 2 +
          Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
        return earth * (2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x)));
      }}

      function bearingDegrees(a, b) {{
        const toRad = (deg) => (deg * Math.PI) / 180;
        const toDeg = (rad) => (rad * 180) / Math.PI;
        const lat1 = toRad(a.lat);
        const lat2 = toRad(b.lat);
        const deltaLon = toRad(b.lon - a.lon);
        const y = Math.sin(deltaLon) * Math.cos(lat2);
        const x =
          Math.cos(lat1) * Math.sin(lat2)
          - Math.sin(lat1) * Math.cos(lat2) * Math.cos(deltaLon);
        return (toDeg(Math.atan2(y, x)) + 360) % 360;
      }}

      function addEndpointSymbol(lat, lon, color, sizePx, shape, popupHtml) {{
        const symbolShape = shape === "circle" ? "50%" : "3px";
        const icon = L.divIcon({{
          className: "endpoint-symbol-icon",
          html: (
            `<div style="` +
            `width:${{sizePx}}px;height:${{sizePx}}px;` +
            `background:${{color}};border:2px solid ${{color}};box-sizing:border-box;` +
            `border-radius:${{symbolShape}};` +
            `"></div>`
          ),
          iconSize: [sizePx, sizePx],
          iconAnchor: [sizePx / 2, sizePx / 2],
        }});

        return L.marker([lat, lon], {{ icon }})
          .addTo(layers.endpoints)
          .bindPopup(popupHtml);
      }}

      function bearingDegrees(a, b) {{
        const toRad = (deg) => (deg * Math.PI) / 180;
        const toDeg = (rad) => (rad * 180) / Math.PI;
        const lat1 = toRad(a.lat);
        const lat2 = toRad(b.lat);
        const deltaLon = toRad(b.lon - a.lon);
        const y = Math.sin(deltaLon) * Math.cos(lat2);
        const x =
          Math.cos(lat1) * Math.sin(lat2)
          - Math.sin(lat1) * Math.cos(lat2) * Math.cos(deltaLon);
        return (toDeg(Math.atan2(y, x)) + 360) % 360;
      }}

      function gradeColor(gradePercent) {{
        if (gradePercent <= -10) return "#0B3D2E";
        if (gradePercent <= -6) return "#1E7A47";
        if (gradePercent <= -2) return "#6CCB5F";
        if (gradePercent < 2) return "#F2D64B";
        if (gradePercent < 5) return "#F7B267";
        if (gradePercent < 8) return "#EE8F39";
        if (gradePercent < 10) return "#E57373";
        return "#8B0000";
      }}

      L.polyline(latLngs, {{
        color: payload.trackColor,
        weight: 5,
        opacity: 0.92,
      }}).addTo(layers.track);

      coordinates.forEach((point) => {{
        L.circleMarker([point.lat, point.lon], {{
          radius: payload.trackPointSizePx,
          color: payload.trackPointColor,
          fillColor: payload.trackPointColor,
          fillOpacity: 0.9,
          weight: 1,
        }}).addTo(layers.points);
      }});

      for (let i = 0; i < coordinates.length - 1; i += 1) {{
        const a = coordinates[i];
        const b = coordinates[i + 1];
        const horiz = haversineMeters(a, b);
        let grade = null;
        if (a.ele !== null && b.ele !== null && horiz > 0.5) {{
          grade = ((b.ele - a.ele) / horiz) * 100;
        }}

        const color = grade === null ? "#007f5f" : gradeColor(grade);
        const segment = L.polyline([[a.lat, a.lon], [b.lat, b.lon]], {{
          color,
          weight: 5,
          opacity: 0.92,
        }});

        const tooltip = grade === null
          ? "Segment: grade n/a"
          : `Segment grade: ${{grade.toFixed(1)}}%`;
        segment.bindTooltip(tooltip, {{ sticky: true }});
        segment.addTo(layers.gradient);
      }}

      if (map.hasLayer(layers.track)) {{
        map.removeLayer(layers.track);
      }}

      function applyGradientMode(gradientEnabled) {{
        if (gradientEnabled) {{
          if (!map.hasLayer(layers.gradient)) {{
            map.addLayer(layers.gradient);
          }}
          if (map.hasLayer(layers.track)) {{
            map.removeLayer(layers.track);
          }}
          return;
        }}

        if (map.hasLayer(layers.gradient)) {{
          map.removeLayer(layers.gradient);
        }}
        if (!map.hasLayer(layers.track)) {{
          map.addLayer(layers.track);
        }}
      }}

      function emitOverlayState(layerName, enabled) {{
        window.location.hash =
          `gpxcmd=1&action=overlay_state&layer=${{encodeURIComponent(layerName)}}&enabled=${{enabled ? 1 : 0}}`;
      }}

      function setLayerEnabled(layerName, enabled) {{
        const layer = layerRegistry[layerName];
        if (!layer) {{
          return;
        }}
        if (enabled) {{
          if (!map.hasLayer(layer)) {{
            map.addLayer(layer);
          }}
          return;
        }}
        if (map.hasLayer(layer)) {{
          map.removeLayer(layer);
        }}
      }}

      function updateDirectionArrowsForViewport() {{
        if (!map._loaded) {{
          return;
        }}
        layers.directionArrows.clearLayers();

        if (!coordinates || coordinates.length < 2) {{
          return;
        }}

        const bounds = map.getBounds();
        const cumulativeMeters = [0];
        for (let i = 0; i < coordinates.length - 1; i += 1) {{
          const a = coordinates[i];
          const b = coordinates[i + 1];
          const segmentMeters = haversineMeters(a, b);
          cumulativeMeters.push(cumulativeMeters[cumulativeMeters.length - 1] + Math.max(0, segmentMeters));
        }}

        const totalDistanceMeters = cumulativeMeters[cumulativeMeters.length - 1];
        if (totalDistanceMeters <= 0) {{
          return;
        }}

        const visibleSegments = [];
        let visibleDistanceMeters = 0;
        for (let i = 0; i < coordinates.length - 1; i += 1) {{
          const a = coordinates[i];
          const b = coordinates[i + 1];
          const aIn = bounds.contains([a.lat, a.lon]);
          const bIn = bounds.contains([b.lat, b.lon]);
          if (!aIn && !bIn) {{
            continue;
          }}

          const segmentMeters = cumulativeMeters[i + 1] - cumulativeMeters[i];
          if (segmentMeters <= 0) {{
            continue;
          }}

          visibleSegments.push({{
            a,
            b,
            startMeters: cumulativeMeters[i],
            segmentMeters,
          }});
          visibleDistanceMeters += segmentMeters;
        }}

        if (visibleDistanceMeters <= 0 || visibleSegments.length === 0) {{
          return;
        }}

        const configuredCount = Math.max(1, Number(payload.directionArrowCount || 10));
        const visibleRatio = Math.max(0, Math.min(1, visibleDistanceMeters / totalDistanceMeters));
        const scaledRatio = Math.max(visibleRatio, Math.sqrt(visibleRatio));
        const arrowCount = Math.max(2, Math.round(configuredCount * scaledRatio));

        const targetsMeters = [];
        for (let i = 0; i < arrowCount; i += 1) {{
          targetsMeters.push((visibleDistanceMeters * (i + 1)) / (arrowCount + 1));
        }}

        let targetIndex = 0;
        let traversedVisibleMeters = 0;
        for (const segment of visibleSegments) {{
          const beforeSegmentVisible = traversedVisibleMeters;
          traversedVisibleMeters += segment.segmentMeters;

          while (
            targetIndex < targetsMeters.length
            && traversedVisibleMeters >= targetsMeters[targetIndex]
          ) {{
            const targetVisibleMeters = targetsMeters[targetIndex];
            const ratio = (targetVisibleMeters - beforeSegmentVisible) / segment.segmentMeters;
            const clampedRatio = Math.max(0, Math.min(1, ratio));
            const arrowLat = segment.a.lat + (segment.b.lat - segment.a.lat) * clampedRatio;
            const arrowLon = segment.a.lon + (segment.b.lon - segment.a.lon) * clampedRatio;
            const globalDistanceKm = (
              segment.startMeters + segment.segmentMeters * clampedRatio
            ) / 1000.0;

            const normalizedBearingDeg = bearingDegrees(segment.a, segment.b);

            const arrowSizePx = payload.directionArrowSizePx;
            const arrowHalfPx = arrowSizePx / 2;
            const arrowIcon = L.divIcon({{
              className: "direction-arrow-icon",
              html: (
                `<div style="` +
                `width: ${{arrowSizePx}}px; height: ${{arrowSizePx}}px; display: flex; align-items: center; justify-content: center; ` +
                `line-height: 1; font-size: ${{arrowSizePx + 6}}px; font-weight: 900; color: ${{payload.directionArrowColor}}; ` +
                `transform: rotate(${{normalizedBearingDeg - 90}}deg);">&gt;</div>`
              ),
              iconSize: [arrowSizePx, arrowSizePx],
              iconAnchor: [arrowHalfPx, arrowHalfPx],
            }});

            L.marker([arrowLat, arrowLon], {{ icon: arrowIcon }})
              .addTo(layers.directionArrows)
              .bindTooltip(`Direction @ ${{globalDistanceKm.toFixed(1)}} km`, {{ permanent: false }});

            targetIndex += 1;
          }}

          if (targetIndex >= targetsMeters.length) {{
            break;
          }}
        }}
      }}

      map.on("overlayadd", (event) => {{
        if (event.layer === layers.gradient) {{
          applyGradientMode(true);
          if (!suppressOverlayEvents) {{
            emitOverlayState("gradient", true);
          }}
          return;
        }}
        if (event.layer === layers.points) {{
          if (!suppressOverlayEvents) emitOverlayState("points", true);
          return;
        }}
        if (event.layer === layers.endpoints) {{
          if (!suppressOverlayEvents) emitOverlayState("endpoints", true);
          return;
        }}
        if (event.layer === layers.distance) {{
          if (!suppressOverlayEvents) emitOverlayState("distance", true);
          return;
        }}
        if (event.layer === layers.directionArrows) {{
          if (!suppressOverlayEvents) emitOverlayState("directionArrows", true);
          return;
        }}
        if (event.layer === layers.rests) {{
          if (!suppressOverlayEvents) emitOverlayState("rests", true);
          return;
        }}
        if (event.layer === bicycleRoutesLayer) {{
          if (!suppressOverlayEvents) emitOverlayState("bicycleRoutes", true);
        }}
      }});
      map.on("overlayremove", (event) => {{
        if (event.layer === layers.gradient) {{
          applyGradientMode(false);
          if (!suppressOverlayEvents) {{
            emitOverlayState("gradient", false);
          }}
          return;
        }}
        if (event.layer === layers.points) {{
          if (!suppressOverlayEvents) emitOverlayState("points", false);
          return;
        }}
        if (event.layer === layers.endpoints) {{
          if (!suppressOverlayEvents) emitOverlayState("endpoints", false);
          return;
        }}
        if (event.layer === layers.distance) {{
          if (!suppressOverlayEvents) emitOverlayState("distance", false);
          return;
        }}
        if (event.layer === layers.directionArrows) {{
          if (!suppressOverlayEvents) emitOverlayState("directionArrows", false);
          return;
        }}
        if (event.layer === layers.rests) {{
          if (!suppressOverlayEvents) emitOverlayState("rests", false);
          return;
        }}
        if (event.layer === bicycleRoutesLayer) {{
          if (!suppressOverlayEvents) emitOverlayState("bicycleRoutes", false);
        }}
      }});

      const overlayDefaults = {{
        gradient: true,
        points: false,
        endpoints: true,
        distance: true,
        directionArrows: true,
        rests: true,
        bicycleRoutes: false,
      }};
      const overlayState = Object.assign({{}}, overlayDefaults, initialOverlays);
      setLayerEnabled("points", !!overlayState.points);
      setLayerEnabled("endpoints", !!overlayState.endpoints);
      setLayerEnabled("distance", !!overlayState.distance);
      setLayerEnabled("directionArrows", !!overlayState.directionArrows);
      setLayerEnabled("rests", !!overlayState.rests);
      setLayerEnabled("bicycleRoutes", !!overlayState.bicycleRoutes);
      applyGradientMode(!!overlayState.gradient);
      suppressOverlayEvents = false;

      map.on("moveend", updateDirectionArrowsForViewport);
      map.on("zoomend", updateDirectionArrowsForViewport);

      window.__gpxFitTrack = function() {{
        const bounds = layers.gradient.getBounds();
        if (bounds && bounds.isValid()) {{
          map.fitBounds(bounds, {{ padding: [24, 24] }});
        }}
      }};
      window.__gpxFitTrack();
      updateDirectionArrowsForViewport();

      const startTime = payload.start.time ? new Date(payload.start.time).toLocaleString() : "n/a";
      const endTime = payload.end.time ? new Date(payload.end.time).toLocaleString() : "n/a";

      addEndpointSymbol(
        payload.start.lat,
        payload.start.lon,
        payload.startSymbolColor,
        payload.startSymbolSizePx,
        payload.startSymbolShape,
        `<strong>Start</strong><br>` +
          `Time: ${{startTime}}<br>` +
          `Elevation: ${{payload.start.ele ?? "n/a"}} m<br>` +
          `Lat/Lon: ${{payload.start.lat.toFixed(5)}}, ${{payload.start.lon.toFixed(5)}}`
      );

      addEndpointSymbol(
        payload.end.lat,
        payload.end.lon,
        payload.stopSymbolColor,
        payload.stopSymbolSizePx,
        payload.stopSymbolShape,
        `<strong>End</strong><br>` +
          `Time: ${{endTime}}<br>` +
          `Elevation: ${{payload.end.ele ?? "n/a"}} m<br>` +
          `Lat/Lon: ${{payload.end.lat.toFixed(5)}}, ${{payload.end.lon.toFixed(5)}}`
      );

      payload.distanceMarkers.forEach((marker) => {{
        L.circleMarker([marker.lat, marker.lon], {{
          radius: payload.distanceMarkerSizePx,
          color: payload.distanceMarkerBorderColor,
          fillColor: payload.distanceMarkerColor,
          fillOpacity: 1,
          weight: 1,
        }})
          .addTo(layers.distance)
          .bindTooltip(`${{marker.distanceKm.toFixed(0)}} km`, {{ permanent: false }});
      }});

      payload.restStops.forEach((stop) => {{
        const elevation = stop.elevation === null ? "n/a" : `${{Math.round(stop.elevation)}} m`;
        const popup =
          `<strong>Rest Stop</strong><br>` +
          `Start: ${{new Date(stop.startTime).toLocaleString()}}<br>` +
          `End: ${{new Date(stop.endTime).toLocaleString()}}<br>` +
          `Duration: ${{stop.durationMin}} min<br>` +
          `Elevation: ${{elevation}}`;

        L.circleMarker([stop.lat, stop.lon], {{
          radius: payload.restStopSizePx,
          color: payload.restStopColor,
          fillColor: payload.restStopColor,
          fillOpacity: 0.85,
          weight: 2,
        }})
          .addTo(layers.rests)
          .bindPopup(popup);
      }});

      const pointMenu = document.getElementById("point-menu");
      let selectedPointPercent = null;
      const pointActionButtons = Array.from(pointMenu.querySelectorAll(".point-action"));
      const pointActionThresholdPx = 28;

      function emitMapCommand(action, percent) {{
        const safePercent = Math.max(0, Math.min(100, percent));
        window.location.hash = `gpxcmd=1&action=${{encodeURIComponent(action)}}&percent=${{safePercent.toFixed(3)}}`;
      }}

      function emitTrackAction(operation) {{
        if (!operation) {{
          return;
        }}
        window.location.hash = `gpxcmd=1&action=track_action&op=${{encodeURIComponent(operation)}}`;
      }}

      function nearestPointIndex(targetLatLng) {{
        let bestIdx = 0;
        let bestDist = Number.POSITIVE_INFINITY;

        for (let i = 0; i < coordinates.length; i += 1) {{
          const p = coordinates[i];
          const dLat = p.lat - targetLatLng.lat;
          const dLon = p.lon - targetLatLng.lng;
          const d = dLat * dLat + dLon * dLon;
          if (d < bestDist) {{
            bestDist = d;
            bestIdx = i;
          }}
        }}

        return bestIdx;
      }}

      function nearestPointData(containerPoint) {{
        let bestIdx = 0;
        let bestDistSq = Number.POSITIVE_INFINITY;

        for (let i = 0; i < coordinates.length; i += 1) {{
          const p = coordinates[i];
          const pixel = map.latLngToContainerPoint([p.lat, p.lon]);
          const dx = pixel.x - containerPoint.x;
          const dy = pixel.y - containerPoint.y;
          const distSq = dx * dx + dy * dy;
          if (distSq < bestDistSq) {{
            bestDistSq = distSq;
            bestIdx = i;
          }}
        }}

        return {{
          index: bestIdx,
          distancePx: Math.sqrt(bestDistSq),
        }};
      }}

      function setPointActionsEnabled(enabled) {{
        pointActionButtons.forEach((button) => {{
          button.disabled = !enabled;
        }});
      }}

      map.on("contextmenu", (event) => {{
        let canUsePointActions = false;
        if (coordinates.length > 1) {{
          const nearest = nearestPointData(event.containerPoint);
          canUsePointActions = nearest.distancePx <= pointActionThresholdPx;
          if (canUsePointActions) {{
            selectedPointPercent = (nearest.index / (coordinates.length - 1)) * 100;
          }} else {{
            selectedPointPercent = null;
          }}
        }} else {{
          selectedPointPercent = null;
        }}

        setPointActionsEnabled(canUsePointActions);
        pointMenu.style.left = `${{event.containerPoint.x}}px`;
        pointMenu.style.top = `${{event.containerPoint.y}}px`;
        pointMenu.style.display = "block";
      }});

      map.on("click", () => {{
        pointMenu.style.display = "none";
      }});

      pointMenu.querySelectorAll("button").forEach((button) => {{
        button.addEventListener("click", () => {{
          const action = button.dataset.action;
          if (!action) {{
            return;
          }}

          if (button.disabled) {{
            return;
          }}

          if (action.startsWith("track_")) {{
            emitTrackAction(action.slice("track_".length));
            pointMenu.style.display = "none";
            return;
          }}

          if (selectedPointPercent === null) {{
            return;
          }}
          emitMapCommand(action, selectedPointPercent);
          pointMenu.style.display = "none";
        }});
      }});

      const isNarrowDisplay = window.innerWidth < responsiveThresholdPx;

      L.control.layers(null, {{
        "Show Gradient": layers.gradient,
        "Track Points": layers.points,
        "Start/End": layers.endpoints,
        "Distance Markers": layers.distance,
        "Direction Arrows": layers.directionArrows,
        "Rest Stops": layers.rests,
        "Bicycle Routes": bicycleRoutesLayer,
      }}, {{ collapsed: isNarrowDisplay, position: "bottomright" }}).addTo(map);

      document.getElementById("track-title").textContent =
        `${{payload.trackName}} (${{payload.totalDistanceKm}} km)`;
    </script>
  </body>
</html>
"""

    def _build_track_lines_preview_html(
        self,
        tracks: list[dict[str, object]],
        waypoints: list[dict[str, object]],
    ) -> str:
        tracks_json = json.dumps(tracks)
        waypoints_json = json.dumps(waypoints)
        waypoint_icon_url_json = json.dumps(_load_waypoint_icon_data_url())
        track_delete_operation = "delete_permanently" if self.track_delete_uses_permanent else "move_to_trash"
        track_delete_label = "Delete permanently" if self.track_delete_uses_permanent else "Move to Trash"
        return f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <link
      rel=\"stylesheet\"
      href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\"
      integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\"
      crossorigin=\"\"
    />
    <style>
      html, body, #map {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
      .legend {{
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        top: 12px;
        z-index: 1000;
        background: rgba(255, 255, 255, 0.92);
        border-radius: 8px;
        padding: 8px 10px;
        font-family: sans-serif;
        font-size: 12px;
        line-height: 1.3;
        text-align: center;
      }}
      .map-track-menu {{
        position: absolute;
        z-index: 2200;
        display: none;
        background: rgba(255, 255, 255, 0.97);
        border: 1px solid #b9b9b9;
        border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.22);
        min-width: 170px;
        overflow: hidden;
        font-family: sans-serif;
        font-size: 12px;
      }}
      .map-track-menu button {{
        width: 100%;
        border: none;
        background: transparent;
        padding: 8px 10px;
        text-align: left;
        cursor: pointer;
      }}
      .map-track-menu button:hover {{
        background: rgba(0, 127, 95, 0.12);
      }}
    </style>
  </head>
  <body>
    <div id=\"map\"></div>
    <div class=\"legend\"><strong id=\"overview-title\"></strong></div>
    <div id=\"track-menu\" class=\"map-track-menu\">
      <button data-op=\"show\">Show on Map</button>
      <button data-op=\"rename\">Rename</button>
      <button data-op=\"reverse\">Reverse</button>
      <button data-op=\"export\">Export GPX</button>
      <button data-op=\"set_color\">Set color</button>
      <button data-op=\"{track_delete_operation}\">{track_delete_label}</button>
    </div>
    <script
      src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"
      integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\"
      crossorigin=\"\"
    ></script>
    <script>
      const tracks = {tracks_json};
      const waypoints = {waypoints_json};
      const waypointIconUrl = {waypoint_icon_url_json};
      const map = L.map("map");
      L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
      }}).addTo(map);
      L.control.scale({{ imperial: false }}).addTo(map);

      const group = L.featureGroup().addTo(map);
      const waypointIcon = waypointIconUrl
        ? L.icon({{
            iconUrl: waypointIconUrl,
            iconSize: [24, 24],
            iconAnchor: [12, 24],
            tooltipAnchor: [0, -22],
          }})
        : null;
      const trackMenu = document.getElementById("track-menu");
      let contextTrackId = null;

      function openTrackById(trackId) {{
        if (trackId === null || trackId === undefined) {{
          return;
        }}
        window.location.hash = `gpxcmd=1&action=open_track&track_id=${{encodeURIComponent(String(trackId))}}`;
      }}

      function emitTrackAction(trackId, operation) {{
        if (trackId === null || trackId === undefined || !operation) {{
          return;
        }}
        window.location.hash =
          `gpxcmd=1&action=track_action&track_id=${{encodeURIComponent(String(trackId))}}&op=${{encodeURIComponent(operation)}}`;
      }}

      tracks.forEach((track) => {{
        const latLngs = track.coordinates.map((p) => [p.lat, p.lon]);
        const polyline = L.polyline(latLngs, {{
          color: track.trackColor,
          weight: 4,
          opacity: 0.72,
        }}).addTo(group);

        polyline.bindTooltip(track.hoverLabel, {{
          sticky: true,
          direction: "top",
          opacity: 0.92,
        }});

        polyline.on("mouseover", () => {{
          polyline.setStyle({{ weight: 6, opacity: 0.95 }});
        }});

        polyline.on("mouseout", () => {{
          polyline.setStyle({{ weight: 4, opacity: 0.72 }});
        }});

        polyline.on("click", () => {{
          trackMenu.style.display = "none";
          openTrackById(track.trackId);
        }});

        polyline.on("contextmenu", (event) => {{
          if (track.trackId === null || track.trackId === undefined) {{
            return;
          }}
          contextTrackId = track.trackId;
          trackMenu.style.left = `${{event.containerPoint.x}}px`;
          trackMenu.style.top = `${{event.containerPoint.y}}px`;
          trackMenu.style.display = "block";
        }});
      }});

      waypoints.forEach((waypoint) => {{
        const marker = waypointIcon
          ? L.marker([waypoint.lat, waypoint.lon], {{ icon: waypointIcon }})
          : L.circleMarker([waypoint.lat, waypoint.lon], {{
              radius: 6,
              color: "#B71C1C",
              fillColor: "#E53935",
              fillOpacity: 0.85,
              weight: 2,
            }});
        marker.addTo(group);

        marker.bindTooltip(waypoint.waypointName || waypoint.hoverLabel || "Waypoint", {{
          sticky: true,
          direction: "top",
          opacity: 0.95,
        }});

        marker.on("click", () => {{
          trackMenu.style.display = "none";
          openTrackById(waypoint.trackId);
        }});
      }});

      map.on("click", () => {{
        trackMenu.style.display = "none";
      }});

      trackMenu.querySelectorAll("button").forEach((button) => {{
        button.addEventListener("click", () => {{
          if (contextTrackId === null) {{
            return;
          }}
          emitTrackAction(contextTrackId, button.dataset.op);
          trackMenu.style.display = "none";
        }});
      }});

      window.__gpxFitTrack = function() {{
        const bounds = group.getBounds();
        if (bounds && bounds.isValid()) {{
          map.fitBounds(bounds, {{ padding: [24, 24] }});
        }}
      }};
      window.__gpxFitTrack();

      document.getElementById("overview-title").textContent =
        `${{tracks.length}} track(s), ${{waypoints.length}} waypoint(s) in current folder view`;
    </script>
  </body>
</html>
"""

    def _build_multi_track_leaflet_html(
      self,
      tracks: list[dict[str, object]],
      initial_overlays: dict[str, bool] | None = None,
    ) -> str:
        tracks_json = json.dumps(tracks)
        initial_overlays_json = json.dumps(initial_overlays or {})
        responsive_threshold_px = self.responsive_threshold_px
        bicycle_route_tile_url_json = json.dumps(self.bicycle_route_tile_url)
        bicycle_route_attribution_json = json.dumps(self.bicycle_route_attribution)
        return f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <link
      rel=\"stylesheet\"
      href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\"
      integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\"
      crossorigin=\"\"
    />
    <style>
      html, body, #map {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
      .legend {{
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        top: 12px;
        z-index: 1000;
        background: rgba(255, 255, 255, 0.92);
        border-radius: 8px;
        padding: 8px 10px;
        font-family: sans-serif;
        font-size: 12px;
        line-height: 1.3;
        text-align: center;
      }}
      @media (max-width: {responsive_threshold_px}px) {{
        .legend {{ font-size: 11px; padding: 6px 8px; }}
      }}
    </style>
  </head>
  <body>
    <div id=\"map\"></div>
    <div class=\"legend\"><strong id=\"track-title\"></strong></div>
    <script
      src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"
      integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\"
      crossorigin=\"\"
    ></script>
    <script>
      const tracks = {tracks_json};
      const initialOverlays = {initial_overlays_json};
      const map = L.map(\"map\");
      L.tileLayer(\"https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png\", {{
        maxZoom: 19,
        attribution: \"&copy; OpenStreetMap contributors\"
      }}).addTo(map);
      L.control.scale({{ imperial: false }}).addTo(map);

      const bicycleRoutesLayer = L.tileLayer({bicycle_route_tile_url_json}, {{
        maxZoom: 18,
        opacity: 0.85,
        attribution: {bicycle_route_attribution_json}
      }});

      const layers = {{
        track: L.featureGroup().addTo(map),
        gradient: L.featureGroup().addTo(map),
        points: L.layerGroup(),
        endpoints: L.layerGroup().addTo(map),
        distance: L.layerGroup().addTo(map),
        rests: L.layerGroup().addTo(map),
        directionArrows: L.layerGroup().addTo(map),
      }};
      const layerRegistry = {{
        gradient: layers.gradient,
        points: layers.points,
        endpoints: layers.endpoints,
        distance: layers.distance,
        directionArrows: layers.directionArrows,
        rests: layers.rests,
        bicycleRoutes: bicycleRoutesLayer,
      }};
      let suppressOverlayEvents = true;

      function haversineMeters(a, b) {{
        const toRad = (deg) => (deg * Math.PI) / 180;
        const earth = 6371000;
        const dLat = toRad(b.lat - a.lat);
        const dLon = toRad(b.lon - a.lon);
        const lat1 = toRad(a.lat);
        const lat2 = toRad(b.lat);
        const x =
          Math.sin(dLat / 2) ** 2 +
          Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
        return earth * (2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x)));
      }}

      function bearingDegrees(a, b) {{
        const toRad = (deg) => (deg * Math.PI) / 180;
        const toDeg = (rad) => (rad * 180) / Math.PI;
        const lat1 = toRad(a.lat);
        const lat2 = toRad(b.lat);
        const deltaLon = toRad(b.lon - a.lon);
        const y = Math.sin(deltaLon) * Math.cos(lat2);
        const x =
          Math.cos(lat1) * Math.sin(lat2)
          - Math.sin(lat1) * Math.cos(lat2) * Math.cos(deltaLon);
        return (toDeg(Math.atan2(y, x)) + 360) % 360;
      }}

      function addDirectionArrowMarker(track, arrowLat, arrowLon, bearingDeg) {{
        const glyphRotationDeg = bearingDeg - 90;
        const arrowSizePx = track.directionArrowSizePx;
        const arrowHalfPx = arrowSizePx / 2;
        const arrowIcon = L.divIcon({{
          className: "direction-arrow-icon",
          html: (
            `<div style="width:${{arrowSizePx}}px;height:${{arrowSizePx}}px;display:flex;align-items:center;justify-content:center;line-height:1;font-size:${{arrowSizePx + 6}}px;font-weight:900;color:${{track.directionArrowColor}};transform:rotate(${{glyphRotationDeg}}deg);">&gt;</div>`
          ),
          iconSize: [arrowSizePx, arrowSizePx],
          iconAnchor: [arrowHalfPx, arrowHalfPx],
        }});
        L.marker([arrowLat, arrowLon], {{ icon: arrowIcon }}).addTo(layers.directionArrows);
      }}

      function addEndpointSymbol(lat, lon, color, sizePx, shape, popupHtml) {{
        const symbolShape = shape === "circle" ? "50%" : "3px";
        const icon = L.divIcon({{
          className: "endpoint-symbol-icon",
          html: (
            `<div style="` +
            `width:${{sizePx}}px;height:${{sizePx}}px;` +
            `background:${{color}};border:2px solid ${{color}};box-sizing:border-box;` +
            `border-radius:${{symbolShape}};` +
            `"></div>`
          ),
          iconSize: [sizePx, sizePx],
          iconAnchor: [sizePx / 2, sizePx / 2],
        }});
        L.marker([lat, lon], {{ icon }})
          .addTo(layers.endpoints)
          .bindPopup(popupHtml);
      }}

      function addTrackDirectionArrowsForViewport(track, bounds) {{
        const coordinates = track.coordinates;
        if (!coordinates || coordinates.length < 2) {{
          return;
        }}

        const cumulativeMeters = [0];
        for (let i = 0; i < coordinates.length - 1; i += 1) {{
          const a = coordinates[i];
          const b = coordinates[i + 1];
          const segmentMeters = haversineMeters(a, b);
          cumulativeMeters.push(cumulativeMeters[cumulativeMeters.length - 1] + Math.max(0, segmentMeters));
        }}

        const totalDistanceMeters = cumulativeMeters[cumulativeMeters.length - 1];
        if (totalDistanceMeters <= 0) {{
          return;
        }}

        const visibleSegments = [];
        let visibleDistanceMeters = 0;
        for (let i = 0; i < coordinates.length - 1; i += 1) {{
          const a = coordinates[i];
          const b = coordinates[i + 1];
          const aIn = bounds.contains([a.lat, a.lon]);
          const bIn = bounds.contains([b.lat, b.lon]);
          if (!aIn && !bIn) {{
            continue;
          }}

          const segmentMeters = cumulativeMeters[i + 1] - cumulativeMeters[i];
          if (segmentMeters <= 0) {{
            continue;
          }}

          visibleSegments.push({{
            a,
            b,
            segmentMeters,
          }});
          visibleDistanceMeters += segmentMeters;
        }}

        if (visibleDistanceMeters <= 0 || visibleSegments.length === 0) {{
          return;
        }}

        const configuredCount = Math.max(1, Number(track.directionArrowCount || 10));
        const visibleRatio = Math.max(0, Math.min(1, visibleDistanceMeters / totalDistanceMeters));
        const scaledRatio = Math.max(visibleRatio, Math.sqrt(visibleRatio));
        const arrowCount = Math.max(2, Math.round(configuredCount * scaledRatio));

        const targetsMeters = [];
        for (let i = 0; i < arrowCount; i += 1) {{
          targetsMeters.push((visibleDistanceMeters * (i + 1)) / (arrowCount + 1));
        }}

        let targetIndex = 0;
        let traversedVisibleMeters = 0;
        for (const segment of visibleSegments) {{
          const beforeSegmentVisible = traversedVisibleMeters;
          traversedVisibleMeters += segment.segmentMeters;

          while (
            targetIndex < targetsMeters.length
            && traversedVisibleMeters >= targetsMeters[targetIndex]
          ) {{
            const targetVisibleMeters = targetsMeters[targetIndex];
            const ratio = (targetVisibleMeters - beforeSegmentVisible) / segment.segmentMeters;
            const clampedRatio = Math.max(0, Math.min(1, ratio));
            const arrowLat = segment.a.lat + (segment.b.lat - segment.a.lat) * clampedRatio;
            const arrowLon = segment.a.lon + (segment.b.lon - segment.a.lon) * clampedRatio;
            addDirectionArrowMarker(track, arrowLat, arrowLon, bearingDegrees(segment.a, segment.b));
            targetIndex += 1;
          }}

          if (targetIndex >= targetsMeters.length) {{
            break;
          }}
        }}
      }}

      function updateDirectionArrowsForViewport() {{
        if (!map._loaded) {{
          return;
        }}
        layers.directionArrows.clearLayers();
        const bounds = map.getBounds();
        tracks.forEach((track) => {{
          addTrackDirectionArrowsForViewport(track, bounds);
        }});
      }}

      function gradeColor(gradePercent) {{
        if (gradePercent <= -10) return \"#0B3D2E\";
        if (gradePercent <= -6) return \"#1E7A47\";
        if (gradePercent <= -2) return \"#6CCB5F\";
        if (gradePercent < 2) return \"#F2D64B\";
        if (gradePercent < 5) return \"#F7B267\";
        if (gradePercent < 8) return \"#EE8F39\";
        if (gradePercent < 10) return \"#E57373\";
        return \"#8B0000\";
      }}

      tracks.forEach((track) => {{
        const coordinates = track.coordinates;
        const latLngs = coordinates.map((p) => [p.lat, p.lon]);
        L.polyline(latLngs, {{ color: track.trackColor, weight: 5, opacity: 0.92 }}).addTo(layers.track);

        coordinates.forEach((point) => {{
          L.circleMarker([point.lat, point.lon], {{
            radius: track.trackPointSizePx,
            color: track.trackPointColor,
            fillColor: track.trackPointColor,
            fillOpacity: 0.9,
            weight: 1,
          }}).addTo(layers.points);
        }});

        for (let i = 0; i < coordinates.length - 1; i += 1) {{
          const a = coordinates[i];
          const b = coordinates[i + 1];
          const horiz = haversineMeters(a, b);
          let grade = null;
          if (a.ele !== null && b.ele !== null && horiz > 0.5) {{
            grade = ((b.ele - a.ele) / horiz) * 100;
          }}
          const color = grade === null ? track.trackColor : gradeColor(grade);
          L.polyline([[a.lat, a.lon], [b.lat, b.lon]], {{ color, weight: 5, opacity: 0.92 }}).addTo(layers.gradient);
        }}

        addEndpointSymbol(
          track.start.lat,
          track.start.lon,
          track.startSymbolColor,
          track.startSymbolSizePx,
          track.startSymbolShape,
          `<strong>${{track.trackName}} - Start</strong>`
        );
        addEndpointSymbol(
          track.end.lat,
          track.end.lon,
          track.stopSymbolColor,
          track.stopSymbolSizePx,
          track.stopSymbolShape,
          `<strong>${{track.trackName}} - End</strong>`
        );

        track.distanceMarkers.forEach((marker) => {{
          L.circleMarker([marker.lat, marker.lon], {{
            radius: track.distanceMarkerSizePx,
            color: track.distanceMarkerBorderColor,
            fillColor: track.distanceMarkerColor,
            fillOpacity: 1,
            weight: 1,
          }}).addTo(layers.distance);
        }});

        track.restStops.forEach((stop) => {{
          L.circleMarker([stop.lat, stop.lon], {{
            radius: track.restStopSizePx,
            color: track.restStopColor,
            fillColor: track.restStopColor,
            fillOpacity: 0.85,
            weight: 2,
          }}).addTo(layers.rests);
        }});

      }});

      function applyGradientMode(gradientEnabled) {{
        if (gradientEnabled) {{
          if (!map.hasLayer(layers.gradient)) map.addLayer(layers.gradient);
          if (map.hasLayer(layers.track)) map.removeLayer(layers.track);
          return;
        }}
        if (map.hasLayer(layers.gradient)) map.removeLayer(layers.gradient);
        if (!map.hasLayer(layers.track)) map.addLayer(layers.track);
      }}

      function emitOverlayState(layerName, enabled) {{
        window.location.hash =
          `gpxcmd=1&action=overlay_state&layer=${{encodeURIComponent(layerName)}}&enabled=${{enabled ? 1 : 0}}`;
      }}

      function setLayerEnabled(layerName, enabled) {{
        const layer = layerRegistry[layerName];
        if (!layer) return;
        if (enabled) {{
          if (!map.hasLayer(layer)) map.addLayer(layer);
          return;
        }}
        if (map.hasLayer(layer)) map.removeLayer(layer);
      }}

      map.on(\"overlayadd\", (event) => {{
        if (event.layer === layers.gradient) {{
          applyGradientMode(true);
          if (!suppressOverlayEvents) emitOverlayState("gradient", true);
          return;
        }}
        if (event.layer === layers.points) {{ if (!suppressOverlayEvents) emitOverlayState("points", true); return; }}
        if (event.layer === layers.endpoints) {{ if (!suppressOverlayEvents) emitOverlayState("endpoints", true); return; }}
        if (event.layer === layers.distance) {{ if (!suppressOverlayEvents) emitOverlayState("distance", true); return; }}
        if (event.layer === layers.directionArrows) {{ if (!suppressOverlayEvents) emitOverlayState("directionArrows", true); return; }}
        if (event.layer === layers.rests) {{ if (!suppressOverlayEvents) emitOverlayState("rests", true); return; }}
        if (event.layer === bicycleRoutesLayer) {{ if (!suppressOverlayEvents) emitOverlayState("bicycleRoutes", true); }}
      }});
      map.on(\"overlayremove\", (event) => {{
        if (event.layer === layers.gradient) {{
          applyGradientMode(false);
          if (!suppressOverlayEvents) emitOverlayState("gradient", false);
          return;
        }}
        if (event.layer === layers.points) {{ if (!suppressOverlayEvents) emitOverlayState("points", false); return; }}
        if (event.layer === layers.endpoints) {{ if (!suppressOverlayEvents) emitOverlayState("endpoints", false); return; }}
        if (event.layer === layers.distance) {{ if (!suppressOverlayEvents) emitOverlayState("distance", false); return; }}
        if (event.layer === layers.directionArrows) {{ if (!suppressOverlayEvents) emitOverlayState("directionArrows", false); return; }}
        if (event.layer === layers.rests) {{ if (!suppressOverlayEvents) emitOverlayState("rests", false); return; }}
        if (event.layer === bicycleRoutesLayer) {{ if (!suppressOverlayEvents) emitOverlayState("bicycleRoutes", false); }}
      }});

      const overlayDefaults = {{
        gradient: true,
        points: false,
        endpoints: true,
        distance: true,
        directionArrows: true,
        rests: true,
        bicycleRoutes: false,
      }};
      const overlayState = Object.assign({{}}, overlayDefaults, initialOverlays);
      setLayerEnabled("points", !!overlayState.points);
      setLayerEnabled("endpoints", !!overlayState.endpoints);
      setLayerEnabled("distance", !!overlayState.distance);
      setLayerEnabled("directionArrows", !!overlayState.directionArrows);
      setLayerEnabled("rests", !!overlayState.rests);
      setLayerEnabled("bicycleRoutes", !!overlayState.bicycleRoutes);
      applyGradientMode(!!overlayState.gradient);
      suppressOverlayEvents = false;

      map.on("moveend", updateDirectionArrowsForViewport);
      map.on("zoomend", updateDirectionArrowsForViewport);

      window.__gpxFitTrack = function() {{
        const bounds = layers.track.getBounds();
        if (bounds && bounds.isValid()) {{
          map.fitBounds(bounds, {{ padding: [24, 24] }});
        }}
      }};
      window.__gpxFitTrack();
      updateDirectionArrowsForViewport();

      const isNarrowDisplay = window.innerWidth < {responsive_threshold_px};
      L.control.layers(null, {{
        \"Show Gradient\": layers.gradient,
        \"Track Points\": layers.points,
        \"Start/End\": layers.endpoints,
        \"Distance Markers\": layers.distance,
        \"Direction Arrows\": layers.directionArrows,
        \"Rest Stops\": layers.rests,
        \"Bicycle Routes\": bicycleRoutesLayer,
      }}, {{ collapsed: isNarrowDisplay, position: \"bottomright\" }}).addTo(map);

      document.getElementById(\"track-title\").textContent = `${{tracks.length}} selected tracks`;
    </script>
  </body>
</html>
"""

    def _build_distance_markers(
        self,
        points: list[TrackPoint],
        interval_km: float,
    ) -> list[dict[str, float]]:
        if interval_km <= 0 or len(points) < 2:
            return []

        interval_m = interval_km * 1000.0
        next_marker_m = interval_m
        traveled_m = 0.0
        markers: list[dict[str, float]] = []

        for start, end in zip(points, points[1:]):
            segment_m = self._haversine_distance_m(
                start.latitude,
                start.longitude,
                end.latitude,
                end.longitude,
            )
            traveled_m += segment_m

            while traveled_m >= next_marker_m:
                markers.append(
                    {
                        "lat": end.latitude,
                        "lon": end.longitude,
                        "distanceKm": next_marker_m / 1000.0,
                    }
                )
                next_marker_m += interval_m

        return markers

    def _build_direction_arrows(
      self,
      points: list[TrackPoint],
      arrow_count: int,
    ) -> list[dict[str, float]]:
      if arrow_count <= 0 or len(points) < 2:
        return []

      segments: list[tuple[TrackPoint, TrackPoint, float]] = []
      total_distance_m = 0.0
      for start, end in zip(points, points[1:]):
        segment_m = self._haversine_distance_m(
          start.latitude,
          start.longitude,
          end.latitude,
          end.longitude,
        )
        segments.append((start, end, segment_m))
        total_distance_m += max(0.0, segment_m)

      if total_distance_m <= 0:
        return []

      target_distances_m = [
        total_distance_m * (idx + 1) / (arrow_count + 1)
        for idx in range(arrow_count)
      ]

      target_index = 0
      traveled_m = 0.0
      arrows: list[dict[str, float]] = []

      for start, end, segment_m in segments:
        if segment_m <= 0:
          continue

        previous_traveled_m = traveled_m
        traveled_m += segment_m

        while target_index < len(target_distances_m) and traveled_m >= target_distances_m[target_index]:
          target_m = target_distances_m[target_index]
          ratio = (target_m - previous_traveled_m) / segment_m
          ratio = max(0.0, min(1.0, ratio))
          arrow_lat = start.latitude + (end.latitude - start.latitude) * ratio
          arrow_lon = start.longitude + (end.longitude - start.longitude) * ratio
          arrows.append(
            {
              "lat": arrow_lat,
              "lon": arrow_lon,
              "bearingDeg": self._bearing_degrees(
                start.latitude,
                start.longitude,
                end.latitude,
                end.longitude,
              ),
              "distanceKm": target_m / 1000.0,
            }
          )
          target_index += 1

        if target_index >= len(target_distances_m):
          break

      return arrows

    @staticmethod
    def _bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_lambda = math.radians(lon2 - lon1)
        y = math.sin(delta_lambda) * math.cos(phi2)
        x = (
            math.cos(phi1) * math.sin(phi2)
            - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
        )
        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360.0) % 360.0

    @staticmethod
    def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        earth_radius_m = 6_371_000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return earth_radius_m * c


def _normalize_hex_color(color: str, fallback: str) -> str:
    value = color.strip().upper()
    if HEX_COLOR_RE.match(value):
        return value
    return fallback


def _lighten_hex_color(color: str, factor: float = 0.3) -> str:
    value = _normalize_hex_color(color, DEFAULT_TRACK_COLOR)
    red = int(value[1:3], 16)
    green = int(value[3:5], 16)
    blue = int(value[5:7], 16)

    red = int(red + (255 - red) * factor)
    green = int(green + (255 - green) * factor)
    blue = int(blue + (255 - blue) * factor)
    return f"#{red:02X}{green:02X}{blue:02X}"


def _read_track_display_color(track_path: Path, root: ET.Element | None = None) -> str | None:
    if root is None:
        root = ET.parse(track_path).getroot()
    track = root.find(f".//{{{GPX_NS}}}trk")
    if track is None:
        return None

    extensions = track.find(f"{{{GPX_NS}}}extensions")
    if extensions is None:
        return None

    display_color = extensions.find(f"{{{GPX_ORGANIZER_EXT_NS}}}displayColor")
    if display_color is None or display_color.text is None:
        return None

    value = display_color.text.strip().upper()
    if not HEX_COLOR_RE.match(value):
        return None
    return value


def _extract_gpx_line_coordinates(track_path: Path, root: ET.Element | None = None) -> list[dict[str, float]]:
    if root is None:
        root = ET.parse(track_path).getroot()
    coordinates: list[dict[str, float]] = []

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", maxsplit=1)[0][1:]
        trkseg_path = f".//{{{namespace}}}trkseg"
        trkpt_tag = f"{{{namespace}}}trkpt"
    else:
        trkseg_path = ".//trkseg"
        trkpt_tag = "trkpt"

    for segment in root.findall(trkseg_path):
        for point in segment.findall(trkpt_tag):
            lat_text = point.get("lat")
            lon_text = point.get("lon")
            if lat_text is None or lon_text is None:
                continue
            try:
                coordinates.append(
                    {
                        "lat": float(lat_text),
                        "lon": float(lon_text),
                    }
                )
            except ValueError:
                continue

    return coordinates


def _extract_gpx_waypoints(track_path: Path, root: ET.Element | None = None) -> list[dict[str, object]]:
    if root is None:
        root = ET.parse(track_path).getroot()
    waypoints: list[dict[str, object]] = []

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", maxsplit=1)[0][1:]
        wpt_path = f".//{{{namespace}}}wpt"
        name_tag = f"{{{namespace}}}name"
    else:
        wpt_path = ".//wpt"
        name_tag = "name"

    for waypoint in root.findall(wpt_path):
        lat_text = waypoint.get("lat")
        lon_text = waypoint.get("lon")
        if lat_text is None or lon_text is None:
            continue
        try:
            lat = float(lat_text)
            lon = float(lon_text)
        except ValueError:
            continue

        name = None
        name_node = waypoint.find(name_tag)
        if name_node is not None and name_node.text:
            name = name_node.text.strip()

        waypoints.append(
            {
                "lat": lat,
                "lon": lon,
                "name": name,
            }
        )

    return waypoints


def _load_waypoint_icon_data_url() -> str | None:
    icon_paths = [
        Path.cwd() / "gpx_organizer" / "icons" / "map-waypoint.png",
        Path.cwd() / "icons" / "map-waypoint.png",
    ]
    for icon_path in icon_paths:
        if not icon_path.is_file():
            continue
        try:
            encoded = base64.b64encode(icon_path.read_bytes()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
        except Exception:
            continue
    return None


def _downsample_coordinates(
    coordinates: list[dict[str, float]],
    max_points: int,
) -> list[dict[str, float]]:
    if len(coordinates) <= max_points:
        return coordinates

    if max_points < 2:
        return [coordinates[0], coordinates[-1]]

    step = (len(coordinates) - 1) / float(max_points - 1)
    sampled: list[dict[str, float]] = []
    for index in range(max_points):
        src_index = int(round(index * step))
        src_index = max(0, min(len(coordinates) - 1, src_index))
        sampled.append(coordinates[src_index])

    return sampled


def _downsample_track_points(
    points: list[TrackPoint],
    max_points: int,
) -> list[TrackPoint]:
    if len(points) <= max_points:
        return points

    if max_points < 2:
        return [points[0], points[-1]]

    step = (len(points) - 1) / float(max_points - 1)
    sampled: list[TrackPoint] = []
    for index in range(max_points):
        src_index = int(round(index * step))
        src_index = max(0, min(len(points) - 1, src_index))
        sampled.append(points[src_index])

    return sampled

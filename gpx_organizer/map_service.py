"""Map rendering service abstraction for Milestone 5 integration."""

from __future__ import annotations

from dataclasses import dataclass
import html
import json
import math
from pathlib import Path
from typing import Protocol
import re
import xml.etree.ElementTree as ET

from gpx_analyzer import GPXAnalyzer, TrackPoint


DEFAULT_RESPONSIVE_THRESHOLD_PX = 900
DEFAULT_BICYCLE_ROUTE_TILE_URL = "https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png"
DEFAULT_BICYCLE_ROUTE_ATTRIBUTION = (
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors '
  '| &copy; <a href="https://waymarkedtrails.org">Waymarked Trails</a>'
)
DEFAULT_REST_STOP_COLOR = "#AB47BC"
DEFAULT_TRACK_COLOR = "#007F5F"
DEFAULT_DISTANCE_MARKER_COLOR = "#37474F"
DEFAULT_DIRECTION_ARROW_COLOR = "#1F1F1F"
DEFAULT_DIRECTION_ARROW_INTERVAL_KM = 0.5
DEFAULT_DIRECTION_ARROW_SIZE_PX = 12
DEFAULT_TRACK_POINT_COLOR = "#000000"
DEFAULT_TRACK_POINT_SIZE_PX = 1

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

    def render_track(self, track_path: Path, track_name: str) -> RenderedMap:
        """Render a GPX track into HTML for the embedded map panel."""


class LeafletMapService:
    """Leaflet-based map service using OpenStreetMap online tiles."""

    def __init__(
        self,
        responsive_threshold_px: int = DEFAULT_RESPONSIVE_THRESHOLD_PX,
        bicycle_route_tile_url: str = DEFAULT_BICYCLE_ROUTE_TILE_URL,
        bicycle_route_attribution: str = DEFAULT_BICYCLE_ROUTE_ATTRIBUTION,
        rest_stop_color: str = DEFAULT_REST_STOP_COLOR,
        default_track_color: str = DEFAULT_TRACK_COLOR,
        distance_marker_color: str = DEFAULT_DISTANCE_MARKER_COLOR,
        direction_arrow_color: str = DEFAULT_DIRECTION_ARROW_COLOR,
        direction_arrow_interval_km: float = DEFAULT_DIRECTION_ARROW_INTERVAL_KM,
        direction_arrow_size_px: int = DEFAULT_DIRECTION_ARROW_SIZE_PX,
        track_point_color: str = DEFAULT_TRACK_POINT_COLOR,
        track_point_size_px: int = DEFAULT_TRACK_POINT_SIZE_PX,
    ) -> None:
        self.responsive_threshold_px = max(320, int(responsive_threshold_px))
        self.bicycle_route_tile_url = bicycle_route_tile_url
        self.bicycle_route_attribution = bicycle_route_attribution
        self.rest_stop_color = _normalize_hex_color(rest_stop_color, DEFAULT_REST_STOP_COLOR)
        self.default_track_color = _normalize_hex_color(default_track_color, DEFAULT_TRACK_COLOR)
        self.distance_marker_color = _normalize_hex_color(
            distance_marker_color,
            DEFAULT_DISTANCE_MARKER_COLOR,
        )
        self.direction_arrow_color = _normalize_hex_color(
          direction_arrow_color,
          DEFAULT_DIRECTION_ARROW_COLOR,
        )
        self.direction_arrow_interval_km = max(0.5, float(direction_arrow_interval_km))
        self.direction_arrow_size_px = max(8, min(40, int(direction_arrow_size_px)))
        self.track_point_color = _normalize_hex_color(track_point_color, DEFAULT_TRACK_POINT_COLOR)
        self.track_point_size_px = max(1, min(10, int(track_point_size_px)))

    def render_track(self, track_path: Path, track_name: str) -> RenderedMap:
        analyzer = GPXAnalyzer()
        analyzer.read_gpx_file(track_path)
        points = analyzer.get_track_points()

        if not points:
            return RenderedMap(
                title=track_name,
                html=self._build_message_html(
                    title="Track has no points",
                    message=f"No track points found in {track_name}.",
                ),
            )

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
          for point in points
        ]

        start = coordinates[0]
        end = coordinates[-1]
        distance_markers = self._build_distance_markers(points, interval_km=10.0)
        direction_arrows = self._build_direction_arrows(
            points,
            interval_km=self.direction_arrow_interval_km,
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
          "distanceMarkerColor": self.distance_marker_color,
          "directionArrowColor": self.direction_arrow_color,
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

        return RenderedMap(
            title=track_name,
            html=self._build_leaflet_html(payload),
        )

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

    def _build_leaflet_html(self, payload: dict[str, object]) -> str:
        payload_json = json.dumps(payload)
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
    </style>
  </head>
  <body>
    <div id=\"map\"></div>
    <div class=\"legend\"><strong id=\"track-title\"></strong><br/>Milestone 5 map preview</div>
    <div id=\"point-menu\" class=\"map-point-menu\">
      <button data-action=\"split\">Split</button>
      <button data-action=\"trim_start\">Trim Start</button>
      <button data-action=\"trim_end\">Trim End</button>
    </div>
    <script
      src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"
      integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\"
      crossorigin=\"\"
    ></script>
    <script>
      const payload = {payload_json};
      const responsiveThresholdPx = {responsive_threshold_px};
      const map = L.map("map");
      L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
      }}).addTo(map);

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

      map.on("overlayadd", (event) => {{
        if (event.layer === layers.gradient) {{
          applyGradientMode(true);
        }}
      }});
      map.on("overlayremove", (event) => {{
        if (event.layer === layers.gradient) {{
          applyGradientMode(false);
        }}
      }});

      window.__gpxFitTrack = function() {{
        const bounds = layers.gradient.getBounds();
        if (bounds && bounds.isValid()) {{
          map.fitBounds(bounds, {{ padding: [24, 24] }});
        }}
      }};
      window.__gpxFitTrack();

      const startTime = payload.start.time ? new Date(payload.start.time).toLocaleString() : "n/a";
      const endTime = payload.end.time ? new Date(payload.end.time).toLocaleString() : "n/a";

      L.circleMarker([payload.start.lat, payload.start.lon], {{ radius: 8, color: "#2e7d32", fillOpacity: 1 }})
        .addTo(layers.endpoints)
        .bindPopup(
          `<strong>Start</strong><br>` +
          `Time: ${{startTime}}<br>` +
          `Elevation: ${{payload.start.ele ?? "n/a"}} m<br>` +
          `Lat/Lon: ${{payload.start.lat.toFixed(5)}}, ${{payload.start.lon.toFixed(5)}}`
        );

      L.circleMarker([payload.end.lat, payload.end.lon], {{ radius: 8, color: "#c62828", fillOpacity: 1 }})
        .addTo(layers.endpoints)
        .bindPopup(
          `<strong>End</strong><br>` +
          `Time: ${{endTime}}<br>` +
          `Elevation: ${{payload.end.ele ?? "n/a"}} m<br>` +
          `Lat/Lon: ${{payload.end.lat.toFixed(5)}}, ${{payload.end.lon.toFixed(5)}}`
        );

      payload.distanceMarkers.forEach((marker) => {{
        L.circleMarker([marker.lat, marker.lon], {{
          radius: 5,
          color: payload.distanceMarkerColor,
          fillColor: "#ffffff",
          fillOpacity: 1,
          weight: 2,
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
          radius: 6,
          color: payload.restStopColor,
          fillColor: payload.restStopColor,
          fillOpacity: 0.85,
          weight: 2,
        }})
          .addTo(layers.rests)
          .bindPopup(popup);
      }});

      payload.directionArrows.forEach((arrow) => {{
        const glyphRotationDeg = arrow.bearingDeg - 90;
        const arrowSizePx = payload.directionArrowSizePx;
        const arrowHalfPx = arrowSizePx / 2;
        const arrowIcon = L.divIcon({{
          className: "direction-arrow-icon",
          html: (
            `<div style="` +
            `width: ${{arrowSizePx}}px; height: ${{arrowSizePx}}px; display: flex; align-items: center; justify-content: center; ` +
            `line-height: 1; font-size: ${{arrowSizePx + 6}}px; font-weight: 900; color: ${{payload.directionArrowColor}}; ` +
            `transform: rotate(${{glyphRotationDeg}}deg);">&gt;</div>`
          ),
          iconSize: [arrowSizePx, arrowSizePx],
          iconAnchor: [arrowHalfPx, arrowHalfPx],
        }});

        L.marker([arrow.lat, arrow.lon], {{ icon: arrowIcon }})
          .addTo(layers.directionArrows)
          .bindTooltip(`Direction @ ${{arrow.distanceKm.toFixed(1)}} km`, {{ permanent: false }});
      }});

      const pointMenu = document.getElementById("point-menu");
      let selectedPointPercent = null;

      function emitMapCommand(action, percent) {{
        const safePercent = Math.max(0, Math.min(100, percent));
        window.location.hash = `gpxcmd=1&action=${{encodeURIComponent(action)}}&percent=${{safePercent.toFixed(3)}}`;
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

      map.on("contextmenu", (event) => {{
        const idx = nearestPointIndex(event.latlng);
        if (coordinates.length <= 1) {{
          return;
        }}

        selectedPointPercent = (idx / (coordinates.length - 1)) * 100;
        pointMenu.style.left = `${{event.containerPoint.x}}px`;
        pointMenu.style.top = `${{event.containerPoint.y}}px`;
        pointMenu.style.display = "block";
      }});

      map.on("click", () => {{
        pointMenu.style.display = "none";
      }});

      pointMenu.querySelectorAll("button").forEach((button) => {{
        button.addEventListener("click", () => {{
          if (selectedPointPercent === null) {{
            return;
          }}
          emitMapCommand(button.dataset.action, selectedPointPercent);
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
      interval_km: float,
    ) -> list[dict[str, float]]:
      if interval_km <= 0 or len(points) < 2:
        return []

      interval_m = interval_km * 1000.0
      next_marker_m = interval_m
      traveled_m = 0.0
      arrows: list[dict[str, float]] = []

      for start, end in zip(points, points[1:]):
        segment_m = self._haversine_distance_m(
          start.latitude,
          start.longitude,
          end.latitude,
          end.longitude,
        )
        if segment_m <= 0:
          continue

        previous_traveled_m = traveled_m
        traveled_m += segment_m

        while traveled_m >= next_marker_m:
          ratio = (next_marker_m - previous_traveled_m) / segment_m
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
              "distanceKm": next_marker_m / 1000.0,
            }
          )
          next_marker_m += interval_m

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


def _read_track_display_color(track_path: Path) -> str | None:
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

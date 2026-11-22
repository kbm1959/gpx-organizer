"""Utilities for loading and working with GPX files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class TrackPoint:
    """Single location sample from a GPX track."""

    latitude: float
    longitude: float
    elevation_m: float | None
    time: datetime | None


TRACK_RENDER_MAX_POINTS = 3500
DEFAULT_REST_RADIUS_M = 2.0
DEFAULT_REST_MIN_DURATION_S = 60.0
DEFAULT_REST_ENDPOINT_DISTANCE_MULTIPLIER = 10.0


def downsample_track_points(points: list[TrackPoint], max_points: int) -> list[TrackPoint]:
    if len(points) <= max_points:
        return points
    if max_points < 2:
        return [points[0], points[-1]]
    step = (len(points) - 1) / float(max_points - 1)
    return [points[min(len(points) - 1, max(0, int(round(index * step))))] for index in range(max_points)]


@dataclass(frozen=True)
class RestStop:
    """A detected stop where movement stayed within a small radius."""

    start_time: datetime
    end_time: datetime
    duration_s: float
    latitude: float
    longitude: float
    elevation_m: float | None


class GPXAnalyzer:
    """Analyze GPX files recorded during activities such as bike tours."""

    def __init__(self) -> None:
        self.file_path: Path | None = None
        self.tree: ET.ElementTree | None = None
        self.root: ET.Element | None = None

    def read_gpx_file(self, file_path: str | Path) -> ET.Element:
        """Read and parse the entire GPX file.

        Args:
            file_path: Path to a GPX file.

        Returns:
            The root XML element of the GPX document.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the path is not a `.gpx` file.
            ET.ParseError: If the file content is not valid XML/GPX.
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"GPX file not found: {path}")

        if path.suffix.lower() != ".gpx":
            raise ValueError(f"Expected a .gpx file, got: {path}")

        self.tree = ET.parse(path)
        self.root = self.tree.getroot()
        self.file_path = path

        return self.root

    def get_track_points(self) -> list[TrackPoint]:
        """Extract all track points from the currently loaded GPX file."""
        if self.root is None:
            raise RuntimeError("No GPX file loaded. Call read_gpx_file() first.")

        namespace = self._get_default_namespace()
        return self._extract_track_points(self.root, namespace)

    def get_track_point_segments(self) -> list[list[TrackPoint]]:
        """Extract track points grouped by GPX segment."""
        if self.root is None:
            raise RuntimeError("No GPX file loaded. Call read_gpx_file() first.")
        namespace = self._get_default_namespace()
        return [
            self._extract_track_points(segment, namespace)
            for segment in self.root.findall(f".//{{{namespace}}}trkseg")
        ]

    @staticmethod
    def _extract_track_points(root: ET.Element, namespace: str) -> list[TrackPoint]:
        trkpt_path = f".//{{{namespace}}}trkpt"
        ele_path = f"{{{namespace}}}ele"
        time_path = f"{{{namespace}}}time"

        points: list[TrackPoint] = []

        for trkpt in root.findall(trkpt_path):
            lat_raw = trkpt.get("lat")
            lon_raw = trkpt.get("lon")

            if lat_raw is None or lon_raw is None:
                continue

            ele_element = trkpt.find(ele_path)
            time_element = trkpt.find(time_path)

            elevation_m = None
            if ele_element is not None and ele_element.text:
                elevation_m = float(ele_element.text)

            timestamp = None
            if time_element is not None and time_element.text:
                timestamp = datetime.fromisoformat(time_element.text.replace("Z", "+00:00"))

            points.append(
                TrackPoint(
                    latitude=float(lat_raw),
                    longitude=float(lon_raw),
                    elevation_m=elevation_m,
                    time=timestamp,
                )
            )

        return points

    def calculate_ride_stats(
        self,
        track_points: list[TrackPoint] | None = None,
        min_distance_m: float = 1.0,
    ) -> dict[str, float]:
        """Calculate distance, moving time, and average speed for a loaded GPX track."""
        points = track_points if track_points is not None else self.get_track_points()

        if len(points) < 2:
            return {
                "total_distance_m": 0.0,
                "moving_time_s": 0.0,
                "average_speed_kmh": 0.0,
            }

        total_distance_m = 0.0
        moving_distance_m = 0.0
        moving_time_s = 0.0

        for current, nxt in zip(points, points[1:]):
            segment_distance = self._haversine_distance_m(
                current.latitude,
                current.longitude,
                nxt.latitude,
                nxt.longitude,
            )
            total_distance_m += segment_distance

            if current.time is None or nxt.time is None:
                continue

            try:
                delta_t = (nxt.time - current.time).total_seconds()
            except (TypeError, OverflowError):
                continue
            if delta_t <= 0:
                continue

            if segment_distance >= min_distance_m:
                moving_time_s += delta_t
                moving_distance_m += segment_distance

        average_speed_kmh = 0.0
        if moving_time_s > 0:
            average_speed_kmh = (moving_distance_m / moving_time_s) * 3.6

        return {
            "total_distance_m": total_distance_m,
            "moving_time_s": moving_time_s,
            "average_speed_kmh": average_speed_kmh,
        }

    def find_rest_stops(
        self,
        track_points: list[TrackPoint] | None = None,
        radius_m: float = DEFAULT_REST_RADIUS_M,
        min_duration_s: float = DEFAULT_REST_MIN_DURATION_S,
    ) -> list[RestStop]:
        """Find time spans where coordinates stay within a radius for long enough."""
        return [
            stop
            for stop, _, _ in self.find_rest_stops_indexed(
                track_points, radius_m=radius_m, min_duration_s=min_duration_s
            )
        ]

    def find_rest_stops_indexed(
        self,
        track_points: list[TrackPoint] | None = None,
        radius_m: float = DEFAULT_REST_RADIUS_M,
        min_duration_s: float = DEFAULT_REST_MIN_DURATION_S,
    ) -> list[tuple[RestStop, int, int]]:
        """Find rest spans and return their inclusive start/end point indices."""
        if radius_m <= 0:
            raise ValueError("radius_m must be > 0")

        if min_duration_s <= 0:
            raise ValueError("min_duration_s must be > 0")

        points = track_points if track_points is not None else self.get_track_points()

        if len(points) < 2:
            return []

        rest_stops: list[tuple[RestStop, int, int]] = []
        i = 0

        while i < len(points) - 1:
            anchor = points[i]
            if anchor.time is None:
                i += 1
                continue

            j = i + 1
            while j < len(points):
                current = points[j]
                distance_to_anchor = self._haversine_distance_m(
                    anchor.latitude,
                    anchor.longitude,
                    current.latitude,
                    current.longitude,
                )
                if distance_to_anchor > radius_m:
                    break
                j += 1

            end_idx = j - 1
            end_point = points[end_idx]

            if end_idx > i and end_point.time is not None:
                try:
                    duration_s = (end_point.time - anchor.time).total_seconds()
                except (TypeError, OverflowError):
                    i = max(i + 1, end_idx + 1)
                    continue
                if duration_s >= min_duration_s:
                    cluster = points[i : end_idx + 1]
                    avg_lat = sum(point.latitude for point in cluster) / len(cluster)
                    avg_lon = sum(point.longitude for point in cluster) / len(cluster)

                    elevations = [
                        point.elevation_m for point in cluster if point.elevation_m is not None
                    ]
                    avg_ele = None
                    if elevations:
                        avg_ele = sum(elevations) / len(elevations)

                    rest_stops.append(
                        (RestStop(
                            start_time=anchor.time,
                            end_time=end_point.time,
                            duration_s=duration_s,
                            latitude=avg_lat,
                            longitude=avg_lon,
                            elevation_m=avg_ele,
                        ), i, end_idx)
                    )

            i = max(i + 1, end_idx + 1)

        return rest_stops

    def find_track_rest_stops_indexed(
        self,
        track_segments: list[list[TrackPoint]] | None = None,
        radius_m: float = DEFAULT_REST_RADIUS_M,
        min_duration_s: float = DEFAULT_REST_MIN_DURATION_S,
        endpoint_distance_multiplier: float = DEFAULT_REST_ENDPOINT_DISTANCE_MULTIPLIER,
    ) -> list[tuple[int, RestStop, int, int]]:
        """Find segment stops, excluding endpoint-near first and last stops."""
        if endpoint_distance_multiplier <= 0:
            raise ValueError("endpoint_distance_multiplier must be > 0")

        segments = track_segments if track_segments is not None else self.get_track_point_segments()
        non_empty = [index for index, segment in enumerate(segments) if segment]
        if not non_empty:
            return []
        first_segment = non_empty[0]
        last_segment = non_empty[-1]
        stops: list[tuple[int, RestStop, int, int]] = []

        for segment_index, segment in enumerate(segments):
            if len(segment) < 2:
                continue
            deltas: list[float | None] = []
            for first, second in zip(segment, segment[1:]):
                if first.time is None or second.time is None:
                    deltas.append(None)
                    continue
                try:
                    deltas.append((second.time - first.time).total_seconds())
                except (TypeError, OverflowError):
                    deltas.append(None)
            descending = bool(deltas) and all(delta is not None and delta <= 0 for delta in deltas) and any(
                delta is not None and delta < 0 for delta in deltas
            )
            search_points = list(reversed(segment)) if descending else segment
            indexed = self.find_rest_stops_indexed(
                search_points, radius_m=radius_m, min_duration_s=min_duration_s
            )
            for stop, search_start, search_end in indexed:
                if descending:
                    start_index = len(segment) - 1 - search_end
                    end_index = len(segment) - 1 - search_start
                else:
                    start_index = search_start
                    end_index = search_end
                stops.append((segment_index, stop, start_index, end_index))

        stops.sort(key=lambda result: (result[0], result[2]))
        minimum_endpoint_distance_m = radius_m * endpoint_distance_multiplier
        start_point = segments[first_segment][0]
        while stops and self._haversine_distance_m(
            start_point.latitude,
            start_point.longitude,
            stops[0][1].latitude,
            stops[0][1].longitude,
        ) < minimum_endpoint_distance_m:
            stops.pop(0)

        end_point = segments[last_segment][-1]
        while stops and self._haversine_distance_m(
            end_point.latitude,
            end_point.longitude,
            stops[-1][1].latitude,
            stops[-1][1].longitude,
        ) < minimum_endpoint_distance_m:
            stops.pop()
        return stops

    def find_track_rest_stops(
        self,
        track_segments: list[list[TrackPoint]] | None = None,
        radius_m: float = DEFAULT_REST_RADIUS_M,
        min_duration_s: float = DEFAULT_REST_MIN_DURATION_S,
        endpoint_distance_multiplier: float = DEFAULT_REST_ENDPOINT_DISTANCE_MULTIPLIER,
    ) -> list[RestStop]:
        return [
            stop
            for _, stop, _, _ in self.find_track_rest_stops_indexed(
                track_segments,
                radius_m=radius_m,
                min_duration_s=min_duration_s,
                endpoint_distance_multiplier=endpoint_distance_multiplier,
            )
        ]

    def get_ride_stats_pretty(
        self,
        track_points: list[TrackPoint] | None = None,
        min_distance_m: float = 1.0,
        speed_decimals: int = 2,
        distance_decimals: int = 2,
    ) -> dict[str, float | str]:
        """Return ride statistics in human-friendly units and formatting."""
        stats = self.calculate_ride_stats(
            track_points=track_points,
            min_distance_m=min_distance_m,
        )

        total_distance_km = stats["total_distance_m"] / 1000.0
        moving_time_seconds = int(round(stats["moving_time_s"]))
        hours, remainder = divmod(moving_time_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        return {
            "total_distance_km": round(total_distance_km, distance_decimals),
            "moving_time_hms": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "average_speed_kmh": round(stats["average_speed_kmh"], speed_decimals),
        }

    def to_dataframe(self, track_points: list[TrackPoint] | None = None):
        """Return track points as a pandas DataFrame."""
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                "pandas is required for to_dataframe(). Install it with: pip install pandas"
            ) from exc

        points = track_points if track_points is not None else self.get_track_points()

        rows = [
            {
                "latitude": point.latitude,
                "longitude": point.longitude,
                "elevation_m": point.elevation_m,
                "time": point.time,
            }
            for point in points
        ]

        return pd.DataFrame(rows)

    def rest_stops_to_dataframe(
        self,
        rest_stops: list[RestStop] | None = None,
        radius_m: float = 2.0,
        min_duration_s: float = 60.0,
        time_format: str = "%Y-%m-%d %H:%M:%S%z",
    ):
        """Return detected rest stops as a pandas DataFrame with readable fields."""
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                "pandas is required for rest_stops_to_dataframe(). Install it with: pip install pandas"
            ) from exc

        stops = (
            rest_stops
            if rest_stops is not None
            else self.find_rest_stops(radius_m=radius_m, min_duration_s=min_duration_s)
        )

        rows = [
            {
                "start_time": stop.start_time,
                "end_time": stop.end_time,
                "start_time_str": stop.start_time.strftime(time_format),
                "end_time_str": stop.end_time.strftime(time_format),
                "duration_s": stop.duration_s,
                "duration_hms": self._seconds_to_hms(stop.duration_s),
                "latitude": stop.latitude,
                "longitude": stop.longitude,
                "elevation_m": stop.elevation_m,
            }
            for stop in stops
        ]

        return pd.DataFrame(rows)

    def _get_default_namespace(self) -> str:
        """Return the XML default namespace URI used in the loaded GPX file."""
        if self.root is None:
            raise RuntimeError("No GPX file loaded. Call read_gpx_file() first.")

        if not self.root.tag.startswith("{"):
            raise ValueError("GPX root element has no namespace.")

        return self.root.tag.split("}", maxsplit=1)[0][1:]

    @staticmethod
    def _haversine_distance_m(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Calculate great-circle distance between two coordinates in meters."""
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

    @staticmethod
    def _seconds_to_hms(total_seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        seconds_int = int(round(total_seconds))
        hours, remainder = divmod(seconds_int, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

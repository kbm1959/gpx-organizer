"""Track property calculations and summaries for the analysis panel."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from gpx_analyzer import (
    DEFAULT_REST_MIN_DURATION_S,
    DEFAULT_REST_ENDPOINT_DISTANCE_MULTIPLIER,
    DEFAULT_REST_RADIUS_M,
    GPXAnalyzer,
    TrackPoint,
    TRACK_RENDER_MAX_POINTS,
    downsample_track_points,
)


ANALYSIS_VERSION = 7
EARTH_RADIUS_KM = 6371.0
ANALYSIS_NUMERIC_FIELDS = (
    "distance_m", "elapsed_s", "moving_time_s", "rest_count", "rest_time_s",
    "timed_distance_m", "moving_distance_m", "min_speed_kmh", "max_speed_kmh",
    "min_elevation_m", "max_elevation_m", "ascent_m", "descent_m",
    "max_uphill_percent", "max_downhill_percent",
)


def is_valid_track_analysis(
    value: Any,
    rest_radius_m: float = DEFAULT_REST_RADIUS_M,
    rest_min_duration_s: float = DEFAULT_REST_MIN_DURATION_S,
    rest_endpoint_distance_multiplier: float = DEFAULT_REST_ENDPOINT_DISTANCE_MULTIPLIER,
) -> bool:
    if not isinstance(value, dict) or value.get("version") != ANALYSIS_VERSION:
        return False
    if not isinstance(value.get("point_count"), int) or value["point_count"] < 0:
        return False
    if not all(key in value for key in ANALYSIS_NUMERIC_FIELDS) or not all(
        key in value for key in (
            "bounds", "start_time", "end_time", "rest_radius_m", "rest_min_duration_s",
            "rest_endpoint_distance_multiplier",
        )
    ):
        return False
    if (
        value["rest_radius_m"] != rest_radius_m
        or value["rest_min_duration_s"] != rest_min_duration_s
        or value["rest_endpoint_distance_multiplier"] != rest_endpoint_distance_multiplier
    ):
        return False
    for key in ("start_time", "end_time"):
        timestamp = value[key]
        if timestamp is not None:
            if not isinstance(timestamp, str):
                return False
            try:
                datetime.fromisoformat(timestamp)
            except ValueError:
                return False
    for key in ANALYSIS_NUMERIC_FIELDS:
        number = value[key]
        if number is not None and (not isinstance(number, (int, float)) or not math.isfinite(number)):
            return False
    if value["distance_m"] is None:
        return False
    bounds = value["bounds"]
    return bounds is None or (
        isinstance(bounds, list) and len(bounds) == 4
        and all(isinstance(number, (int, float)) and math.isfinite(number) for number in bounds)
    )


def rectangle_area_km2(bounds: list[float] | None) -> float | None:
    if bounds is None:
        return None
    min_lat, max_lat, min_lon, max_lon = bounds
    return (
        EARTH_RADIUS_KM ** 2
        * abs(math.sin(math.radians(max_lat)) - math.sin(math.radians(min_lat)))
        * math.radians(max_lon - min_lon)
    )


def _longitude_bounds(ranges: list[tuple[float, float]]) -> tuple[float, float]:
    intervals: list[tuple[float, float]] = []
    for start, end in ranges:
        width = end - start
        if width >= 360:
            return (0.0, 360.0)
        start = start % 360
        end = start + width
        if end > 360:
            intervals.extend(((start, 360.0), (0.0, end - 360)))
        else:
            intervals.append((start, end))
    intervals.sort()
    merged: list[tuple[float, float]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    largest_gap = -1.0
    arc_start = 0.0
    for index, (_, end) in enumerate(merged):
        next_start = merged[(index + 1) % len(merged)][0] + (360 if index == len(merged) - 1 else 0)
        if next_start - end > largest_gap:
            largest_gap = next_start - end
            arc_start = next_start % 360
    return (arc_start, arc_start + 360 - largest_gap)


def analyze_track_segments(
    segments: list[list[TrackPoint]],
    rest_radius_m: float = DEFAULT_REST_RADIUS_M,
    rest_min_duration_s: float = DEFAULT_REST_MIN_DURATION_S,
    rest_endpoint_distance_multiplier: float = DEFAULT_REST_ENDPOINT_DISTANCE_MULTIPLIER,
) -> dict[str, Any]:
    analyzer = GPXAnalyzer()
    points = [point for segment in segments for point in segment]
    bounds = None
    if points:
        min_lon, max_lon = _longitude_bounds([(point.longitude, point.longitude) for point in points])
        bounds = [
            min(point.latitude for point in points), max(point.latitude for point in points),
            min_lon, max_lon,
        ]
    elevations = [point.elevation_m for point in points if point.elevation_m is not None]
    total_distance = 0.0
    timed_distance = 0.0
    moving_distance = 0.0
    elapsed = 0.0
    moving_time = 0.0
    rest_time = 0.0
    rest_count = 0
    ascent = 0.0
    descent = 0.0
    elevation_pairs = 0
    speeds: list[float] = []
    has_timing = False
    timing_complete = True
    indexed_stops = analyzer.find_track_rest_stops_indexed(
        segments,
        radius_m=rest_radius_m,
        min_duration_s=rest_min_duration_s,
        endpoint_distance_multiplier=rest_endpoint_distance_multiplier,
    )
    stops_by_segment: dict[int, list] = {}
    for segment_index, stop, _, _ in indexed_stops:
        stops_by_segment.setdefault(segment_index, []).append(stop)

    for segment_index, segment in enumerate(segments):
        if len(segment) < 2:
            continue
        try:
            durations = [
                (following.time - current.time).total_seconds()
                if current.time is not None and following.time is not None else None
                for current, following in zip(segment, segment[1:])
            ]
        except (TypeError, OverflowError):
            durations = [None] * (len(segment) - 1)
        ascending = all(duration is not None and duration >= 0 for duration in durations)
        descending = all(duration is not None and duration <= 0 for duration in durations)
        segment_timed = ascending or descending
        if not segment_timed:
            timing_complete = False
        stops = stops_by_segment.get(segment_index, []) if segment_timed else []
        rest_count += len(stops)
        rest_time += sum(stop.duration_s for stop in stops)
        stop_index = 0
        for index, (current, following) in enumerate(zip(segment, segment[1:])):
            distance = analyzer._haversine_distance_m(
                current.latitude, current.longitude, following.latitude, following.longitude
            )
            total_distance += distance
            if current.elevation_m is not None and following.elevation_m is not None:
                change = following.elevation_m - current.elevation_m
                elevation_pairs += 1
                ascent += max(change, 0.0)
                descent += max(-change, 0.0)
            if not segment_timed:
                continue
            duration = durations[index]
            assert duration is not None
            duration = abs(duration)
            has_timing = True
            elapsed += duration
            timed_distance += distance
            assert current.time is not None and following.time is not None
            while stop_index < len(stops) and (
                current.time <= stops[stop_index].start_time
                if descending and not ascending
                else current.time >= stops[stop_index].end_time
            ):
                stop_index += 1
            is_rest = (
                stop_index < len(stops)
                and min(current.time, following.time) >= stops[stop_index].start_time
                and max(current.time, following.time) <= stops[stop_index].end_time
            )
            if not is_rest:
                moving_time += duration
                moving_distance += distance
            if duration > 0:
                speeds.append(distance / duration * 3.6)

    rendered_points = downsample_track_points(points, TRACK_RENDER_MAX_POINTS)
    gradients: list[float] = []
    for current, following in zip(rendered_points, rendered_points[1:]):
        if current.elevation_m is None or following.elevation_m is None:
            continue
        distance = analyzer._haversine_distance_m(
            current.latitude, current.longitude, following.latitude, following.longitude
        )
        if distance > 0.5:
            gradients.append((following.elevation_m - current.elevation_m) / distance * 100.0)

    timing_available = has_timing and timing_complete
    return {
        "version": ANALYSIS_VERSION,
        "point_count": len(points),
        "start_time": points[0].time.isoformat() if points and points[0].time is not None else None,
        "end_time": points[-1].time.isoformat() if points and points[-1].time is not None else None,
        "rest_radius_m": rest_radius_m,
        "rest_min_duration_s": rest_min_duration_s,
        "rest_endpoint_distance_multiplier": rest_endpoint_distance_multiplier,
        "distance_m": total_distance,
        "bounds": bounds,
        "elapsed_s": elapsed if timing_available else None,
        "moving_time_s": moving_time if timing_available else None,
        "rest_count": rest_count if timing_available else None,
        "rest_time_s": rest_time if timing_available else None,
        "timed_distance_m": timed_distance if timing_available else None,
        "moving_distance_m": moving_distance if timing_available else None,
        "min_speed_kmh": min(speeds) if timing_available and speeds else None,
        "max_speed_kmh": max(speeds) if timing_available and speeds else None,
        "min_elevation_m": min(elevations) if elevations else None,
        "max_elevation_m": max(elevations) if elevations else None,
        "ascent_m": ascent if elevation_pairs else None,
        "descent_m": descent if elevation_pairs else None,
        "max_uphill_percent": max(gradients) if gradients else None,
        "max_downhill_percent": min(gradients) if gradients else None,
    }


def summarize_tracks(tracks: list[dict[str, Any]]) -> dict[str, Any]:
    if not tracks:
        return {}
    result: dict[str, Any] = {"track_count": len(tracks)}
    if len(tracks) == 1:
        result["start_time"] = tracks[0].get("start_time")
        result["end_time"] = tracks[0].get("end_time")
    else:
        times = [track.get(key) for track in tracks for key in ("start_time", "end_time")]
        result["start_time"] = None
        result["end_time"] = None
        if all(value is not None for value in times):
            parsed = [(datetime.fromisoformat(value), value) for value in times]
            awareness = {timestamp.utcoffset() is not None for timestamp, _ in parsed}
            if len(awareness) == 1:
                result["start_time"] = min(parsed, key=lambda item: item[0])[1]
                result["end_time"] = max(parsed, key=lambda item: item[0])[1]
    for key in ("point_count", "distance_m"):
        result[key] = sum(track[key] for track in tracks)
    for key in ("elapsed_s", "moving_time_s", "rest_count", "rest_time_s", "timed_distance_m", "moving_distance_m"):
        values = [track.get(key) for track in tracks]
        result[key] = sum(values) if all(value is not None for value in values) else None
    for key in ("ascent_m", "descent_m"):
        values = [track.get(key) for track in tracks]
        result[key] = sum(values) if all(value is not None for value in values) else None
    for key in ("min_speed_kmh", "min_elevation_m", "max_downhill_percent"):
        values = [track.get(key) for track in tracks]
        result[key] = min(values) if all(value is not None for value in values) else None
    for key in ("max_speed_kmh", "max_elevation_m", "max_uphill_percent"):
        values = [track.get(key) for track in tracks]
        result[key] = max(values) if all(value is not None for value in values) else None
    bounds = [track["bounds"] for track in tracks if track.get("bounds") is not None]
    longitude_bounds = _longitude_bounds([(bound[2], bound[3]) for bound in bounds]) if bounds else None
    result["bounds"] = [
        min(bound[0] for bound in bounds), max(bound[1] for bound in bounds),
        longitude_bounds[0], longitude_bounds[1],
    ] if bounds and longitude_bounds is not None else None
    result["area_km2"] = rectangle_area_km2(result["bounds"])
    result["average_speed_kmh"] = (
        result["timed_distance_m"] / result["elapsed_s"] * 3.6
        if result["elapsed_s"] and result["timed_distance_m"] is not None else None
    )
    result["moving_average_speed_kmh"] = (
        result["moving_distance_m"] / result["moving_time_s"] * 3.6
        if result["moving_time_s"] and result["moving_distance_m"] is not None else None
    )
    return result
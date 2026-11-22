from datetime import datetime, timedelta, timezone

import pytest

from gpx_analyzer import GPXAnalyzer, TrackPoint, TRACK_RENDER_MAX_POINTS, downsample_track_points
from gpx_organizer.map_service import LeafletMapService
from gpx_organizer.track_analysis import analyze_track_segments, summarize_tracks


def test_track_properties_and_weighted_summary() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [
        TrackPoint(48.0, 7.0, 100.0, start),
        TrackPoint(48.001, 7.0, 110.0, start + timedelta(seconds=30)),
        TrackPoint(48.002, 7.0, 110.0, start + timedelta(seconds=60)),
        TrackPoint(48.002, 7.0, 110.0, start + timedelta(seconds=150)),
        TrackPoint(48.003, 7.0, 115.0, start + timedelta(seconds=180)),
        TrackPoint(48.004, 7.0, 110.0, start + timedelta(seconds=240)),
    ]
    stats = analyze_track_segments([points])
    summary = summarize_tracks([stats, stats])
    assert stats["point_count"] == 6
    assert stats["rest_count"] == 1
    assert stats["rest_time_s"] == 90
    assert stats["elapsed_s"] == 240
    assert stats["moving_time_s"] == 150
    assert stats["ascent_m"] == 15
    assert stats["descent_m"] == 5
    assert stats["min_speed_kmh"] == 0
    assert stats["max_uphill_percent"] > 0
    assert stats["max_downhill_percent"] < 0
    assert summary["point_count"] == 12
    assert summary["distance_m"] == pytest.approx(stats["distance_m"] * 2)
    assert summary["average_speed_kmh"] == pytest.approx(stats["timed_distance_m"] / 240 * 3.6)
    assert summary["moving_average_speed_kmh"] == pytest.approx(stats["moving_distance_m"] / 150 * 3.6)


def test_missing_time_and_segment_boundaries() -> None:
    points = [TrackPoint(48.0, 7.0, None, None), TrackPoint(48.001, 7.0, None, None)]
    stats = analyze_track_segments([points, [TrackPoint(49.0, 8.0, None, None)]])
    assert stats["point_count"] == 3
    assert stats["distance_m"] < 200
    assert stats["elapsed_s"] is None
    assert stats["rest_count"] is None
    assert stats["ascent_m"] is None
    assert summarize_tracks([stats])["area_km2"] > 0


def test_summary_uses_elapsed_time_weighted_speed_and_flags_missing_data() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fast = analyze_track_segments([[
        TrackPoint(48.0, 7.0, 100.0, start),
        TrackPoint(48.001, 7.0, 110.0, start + timedelta(seconds=100)),
    ]])
    slow = analyze_track_segments([[
        TrackPoint(48.0, 7.0, 100.0, start),
        TrackPoint(48.001, 7.0, 110.0, start + timedelta(seconds=1000)),
    ]])
    summary = summarize_tracks([fast, slow])
    assert summary["average_speed_kmh"] == pytest.approx((fast["distance_m"] + slow["distance_m"]) / 1100 * 3.6)
    assert summary["average_speed_kmh"] != pytest.approx((fast["max_speed_kmh"] + slow["max_speed_kmh"]) / 2)
    missing = analyze_track_segments([[
        TrackPoint(48.0, 7.0, None, None), TrackPoint(48.001, 7.0, None, None)
    ]])
    partial = summarize_tracks([fast, missing])
    assert partial["elapsed_s"] is None
    assert partial["average_speed_kmh"] is None
    assert partial["min_speed_kmh"] is None
    assert partial["ascent_m"] is None


def test_reverse_track_keeps_time_and_rest_statistics() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [
        TrackPoint(48.0, 7.0, 100.0, start),
        TrackPoint(48.0, 7.0, 100.0, start + timedelta(seconds=90)),
        TrackPoint(48.001, 7.0, 110.0, start + timedelta(seconds=120)),
    ]
    forward = analyze_track_segments([points])
    reversed_stats = analyze_track_segments([list(reversed(points))])
    for key in ("elapsed_s", "moving_time_s", "rest_time_s", "rest_count", "distance_m"):
        assert reversed_stats[key] == pytest.approx(forward[key])
    assert reversed_stats["ascent_m"] == forward["descent_m"]
    assert reversed_stats["descent_m"] == forward["ascent_m"]
    assert reversed_stats["max_downhill_percent"] < 0
    assert reversed_stats["start_time"] == points[-1].time.isoformat()
    assert reversed_stats["end_time"] == points[0].time.isoformat()


def test_bounding_area_uses_short_span_across_antimeridian() -> None:
    crossing = analyze_track_segments([[
        TrackPoint(10.0, 179.9, None, None), TrackPoint(11.0, -179.9, None, None)
    ]])
    other = analyze_track_segments([[TrackPoint(10.5, 179.8, None, None)]])
    assert crossing["bounds"][3] - crossing["bounds"][2] == pytest.approx(0.2)
    combined = summarize_tracks([crossing, other])
    assert combined["bounds"][3] - combined["bounds"][2] == pytest.approx(0.3)
    assert 3000 < combined["area_km2"] < 4000


def test_rest_detection_excludes_track_endpoints_and_uses_shared_criteria() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [
        TrackPoint(48.0, 7.0, None, start),
        TrackPoint(48.0, 7.0, None, start + timedelta(seconds=61)),
        TrackPoint(48.001, 7.0, None, start + timedelta(seconds=70)),
        TrackPoint(48.002, 7.0, None, start + timedelta(seconds=80)),
        TrackPoint(48.002, 7.0, None, start + timedelta(seconds=140)),
        TrackPoint(48.003, 7.0, None, start + timedelta(seconds=150)),
        TrackPoint(48.003, 7.0, None, start + timedelta(seconds=211)),
    ]
    analyzer = GPXAnalyzer()
    stops = analyzer.find_track_rest_stops([points], radius_m=2, min_duration_s=60)
    stats = analyze_track_segments([points], rest_radius_m=2, rest_min_duration_s=60)
    assert len(stops) == stats["rest_count"] == 1
    assert stops[0].start_time == points[3].time
    assert stops[0].duration_s == 60
    assert stats["rest_radius_m"] == 2
    assert stats["rest_min_duration_s"] == 60
    assert stats["rest_endpoint_distance_multiplier"] == 10

    thresholded = analyzer.find_track_rest_stops([points], radius_m=2, min_duration_s=61)
    assert thresholded == []


def test_rest_endpoint_distance_multiplier_is_configurable() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [
        TrackPoint(48.0000, 7.0, None, start),
        TrackPoint(48.0001, 7.0, None, start + timedelta(seconds=10)),
        TrackPoint(48.0001, 7.0, None, start + timedelta(seconds=71)),
        TrackPoint(48.0100, 7.0, None, start + timedelta(seconds=80)),
        TrackPoint(48.0101, 7.0, None, start + timedelta(seconds=90)),
        TrackPoint(48.0101, 7.0, None, start + timedelta(seconds=151)),
        TrackPoint(48.0102, 7.0, None, start + timedelta(seconds=160)),
    ]
    analyzer = GPXAnalyzer()

    assert analyzer.find_track_rest_stops(
        [points], radius_m=2, min_duration_s=60, endpoint_distance_multiplier=10
    ) == []
    assert len(analyzer.find_track_rest_stops(
        [points], radius_m=2, min_duration_s=60, endpoint_distance_multiplier=5
    )) == 2


def test_gradients_use_map_sampled_points_and_map_distance_threshold() -> None:
    points = [TrackPoint(48.0 + index * 0.00001, 7.0, 100.0, None) for index in range(TRACK_RENDER_MAX_POINTS + 1)]
    sampled = downsample_track_points(points, TRACK_RENDER_MAX_POINTS)
    omitted = next(point for point in points if point not in sampled)
    index = points.index(omitted)
    points[index] = TrackPoint(omitted.latitude, omitted.longitude, 5000.0, None)
    stats = analyze_track_segments([points])
    assert stats["max_uphill_percent"] == 0
    assert stats["max_downhill_percent"] == 0

    short_segment = [TrackPoint(48.0, 7.0, 100.0, None), TrackPoint(48.000006, 7.0, 101.0, None)]
    stats = analyze_track_segments([short_segment])
    assert stats["max_uphill_percent"] > 100
    assert stats["max_downhill_percent"] == stats["max_uphill_percent"]


def test_summary_endpoint_times_respect_offsets_and_missing_timestamps() -> None:
    start = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    first = analyze_track_segments([[TrackPoint(48, 7, None, start), TrackPoint(48.01, 7, None, start + timedelta(hours=1))]])
    offset = timezone(timedelta(hours=2))
    second_start = datetime(2026, 1, 1, 11, 30, tzinfo=offset)
    second = analyze_track_segments([[TrackPoint(48, 7, None, second_start), TrackPoint(48.01, 7, None, second_start + timedelta(hours=4))]])
    summary = summarize_tracks([first, second])
    assert summary["start_time"] == second_start.isoformat()
    assert summary["end_time"] == (second_start + timedelta(hours=4)).isoformat()
    missing = analyze_track_segments([[TrackPoint(48, 7, None, None)]])
    assert summarize_tracks([first, missing])["start_time"] is None
    naive = analyze_track_segments([[TrackPoint(48, 7, None, datetime(2026, 1, 1))]])
    assert summarize_tracks([first, naive])["end_time"] is None


def test_gradient_extrema_match_actual_map_payload(tmp_path) -> None:
    count = TRACK_RENDER_MAX_POINTS + 1
    step = (count - 1) / (TRACK_RENDER_MAX_POINTS - 1)
    included = {round(index * step) for index in range(TRACK_RENDER_MAX_POINTS)}
    omitted = next(index for index in range(count) if index not in included)
    points = []
    for index in range(count):
        elevation = 5000 if index == omitted else 100 + (index % 10)
        points.append(f'<trkpt lat="{48 + index * 0.00001:.6f}" lon="7"><ele>{elevation}</ele></trkpt>')
    path = tmp_path / "dense.gpx"
    path.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        + ''.join(points) + '</trkseg></trk></gpx>', encoding="utf-8"
    )
    analyzer = GPXAnalyzer()
    analyzer.read_gpx_file(path)
    stats = analyze_track_segments(analyzer.get_track_point_segments())
    payload = LeafletMapService()._build_track_payload(path, "Dense")
    assert payload is not None
    coordinates = payload["coordinates"]
    grades = []
    for first, second in zip(coordinates, coordinates[1:]):
        distance = analyzer._haversine_distance_m(first["lat"], first["lon"], second["lat"], second["lon"])
        if distance > 0.5 and first["ele"] is not None and second["ele"] is not None:
            grades.append((second["ele"] - first["ele"]) / distance * 100)
    assert stats["max_uphill_percent"] == pytest.approx(max(grades))
    assert stats["max_downhill_percent"] == pytest.approx(min(grades))
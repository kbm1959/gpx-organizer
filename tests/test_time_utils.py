import pytest

from gpx_organizer.time_utils import format_track_time, normalize_time_zone
from gpx_analyzer import GPXAnalyzer, TrackPoint
from datetime import datetime, timezone


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2026-01-01T10:00:00Z", "2026-01-01 11:00:00 CET (UTC+01:00)"),
        ("2026-07-01T10:00:00Z", "2026-07-01 12:00:00 CEST (UTC+02:00)"),
        ("2026-03-29T00:59:59Z", "2026-03-29 01:59:59 CET (UTC+01:00)"),
        ("2026-03-29T01:00:00Z", "2026-03-29 03:00:00 CEST (UTC+02:00)"),
        ("2026-10-25T00:59:59Z", "2026-10-25 02:59:59 CEST (UTC+02:00)"),
        ("2026-10-25T01:00:00Z", "2026-10-25 02:00:00 CET (UTC+01:00)"),
    ],
)
def test_berlin_timezone_and_daylight_saving(timestamp: str, expected: str) -> None:
    assert format_track_time(timestamp, "Europe/Berlin") == expected


def test_timezones_offsets_and_unknown_timestamp() -> None:
    assert format_track_time("2026-07-01T12:00:00+02:00", "UTC") == "2026-07-01 10:00:00 UTC (UTC+00:00)"
    assert format_track_time("2026-01-01T10:00:00", "Europe/Berlin") == "2026-01-01 10:00:00 (timezone unknown)"
    assert format_track_time(None, "Europe/Berlin") is None
    assert format_track_time("invalid", "Europe/Berlin") is None
    assert normalize_time_zone("not/a/zone") == "Europe/Berlin"


def test_mixed_timezone_points_do_not_break_ride_or_rest_calculations() -> None:
    points = [
        TrackPoint(48, 7, None, datetime(2026, 1, 1, 10)),
        TrackPoint(48, 7, None, datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc)),
    ]
    analyzer = GPXAnalyzer()
    assert analyzer.calculate_ride_stats(points)["moving_time_s"] == 0
    assert analyzer.find_rest_stops(points) == []
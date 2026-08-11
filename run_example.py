"""Runnable example for GPXAnalyzer.

Usage:
    python run_example.py /path/to/track.gpx
"""

from __future__ import annotations

import argparse
from datetime import datetime
import math
from pathlib import Path
import sys
from textwrap import dedent

from gpx_analyzer import GPXAnalyzer, RestStop, TrackPoint


class HelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter,
    argparse.RawDescriptionHelpFormatter,
):
    """Keep readable multi-line help text and show default values."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=dedent(
            """
            Analyze a GPX track from a bicycle tour.

            The script can:
              - compute summary ride statistics
              - detect rest stops
              - export CSV files
              - export an OpenStreetMap HTML map
            """
        ),
        formatter_class=HelpFormatter,
        epilog=dedent(
            """
            Examples:
              run_example.py SB-Strassbourg.gpx
              run_example.py SB-Strassbourg.gpx --export-csv
              run_example.py SB-Strassbourg.gpx --export-map --track-casing
              run_example.py SB-Strassbourg.gpx --export-map --steepness-range 8
              run_example.py SB-Strassbourg.gpx --export-csv --csv-dir exports --csv-prefix day1
            """
        ),
    )
    parser.add_argument(
        "gpx_file",
        type=Path,
        nargs="?",
        help="Path to the GPX file to analyze.",
    )

    core_group = parser.add_argument_group("Core Analysis Options")
    core_group.add_argument(
        "--radius-m",
        type=float,
        default=2.0,
        help="Max radius around a stop location to still count as resting.",
    )
    core_group.add_argument(
        "--min-rest-seconds",
        type=float,
        default=60.0,
        help="Minimum duration required to classify a stop as a rest stop.",
    )
    core_group.add_argument(
        "--min-moving-distance-m",
        type=float,
        default=1.0,
        help="Minimum segment distance treated as movement for speed/time stats.",
    )

    output_group = parser.add_argument_group("Console / Preview Options")
    output_group.add_argument(
        "--head",
        type=int,
        default=5,
        help="Number of DataFrame rows shown in console previews.",
    )

    csv_group = parser.add_argument_group("CSV Export Options")
    csv_group.add_argument(
        "--export-csv",
        action="store_true",
        help="Export track points and rest stops as CSV files.",
    )
    csv_group.add_argument(
        "--csv-dir",
        type=Path,
        default=Path("."),
        help="Target directory for generated CSV files.",
    )
    csv_group.add_argument(
        "--csv-prefix",
        type=str,
        default=None,
        help="Filename prefix for exports; defaults to the GPX filename stem.",
    )

    map_group = parser.add_argument_group("Map Export Options")
    map_group.add_argument(
        "--export-map",
        action="store_true",
        help="Export an OpenStreetMap HTML map with track and rest points.",
    )
    map_group.add_argument(
        "--map-file",
        type=Path,
        default=None,
        help="Output HTML path for map export; defaults to <prefix>_map.html.",
    )
    map_group.add_argument(
        "--steepness-range",
        type=float,
        default=12.0,
        help="Absolute percent slope range for map color scaling (-range..+range).",
    )
    map_group.add_argument(
        "--track-casing",
        action="store_true",
        help="Draw a black underlay beneath the colored track for better contrast.",
    )
    return parser


def _format_mmss(total_seconds: float) -> str:
    """Format seconds as MM:SS."""
    seconds_int = int(round(total_seconds))
    minutes, seconds = divmod(seconds_int, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _to_local_datetime(value: datetime | None) -> datetime | None:
    """Convert an aware datetime to local timezone, keep None unchanged."""
    if value is None:
        return None
    return value.astimezone()


def _localize_track_points(track_points: list[TrackPoint]) -> list[TrackPoint]:
    """Return a new list of track points with local timestamps."""
    return [
        TrackPoint(
            latitude=point.latitude,
            longitude=point.longitude,
            elevation_m=point.elevation_m,
            time=_to_local_datetime(point.time),
        )
        for point in track_points
    ]


def _localize_rest_stops(rest_stops: list[RestStop]) -> list[RestStop]:
    """Return a new list of rest stops with local start/end times."""
    return [
        RestStop(
            start_time=stop.start_time.astimezone(),
            end_time=stop.end_time.astimezone(),
            duration_s=stop.duration_s,
            latitude=stop.latitude,
            longitude=stop.longitude,
            elevation_m=stop.elevation_m,
        )
        for stop in rest_stops
    ]


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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


def _segment_grade_percent(start: TrackPoint, end: TrackPoint) -> float | None:
    """Compute segment steepness in percent if elevation data is available."""
    if start.elevation_m is None or end.elevation_m is None:
        return None

    horizontal_distance_m = _haversine_distance_m(
        start.latitude,
        start.longitude,
        end.latitude,
        end.longitude,
    )
    if horizontal_distance_m < 0.5:
        return None

    return ((end.elevation_m - start.elevation_m) / horizontal_distance_m) * 100.0


def _export_map(
    map_file: Path,
    track_points: list[TrackPoint],
    rest_stops: list[RestStop],
    steepness_range: float,
    track_casing: bool,
) -> Path:
    """Export an OpenStreetMap HTML map with track and rest-stop markers."""
    try:
        import folium
        from branca.colormap import LinearColormap
    except ImportError as exc:
        raise ImportError(
            "folium is required for --export-map. Install it with: pip install folium"
        ) from exc

    if not track_points:
        raise ValueError("No track points available for map export.")

    if steepness_range <= 0:
        raise ValueError("steepness_range must be > 0")

    center = [track_points[0].latitude, track_points[0].longitude]
    fmap = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap")
    track_layer = folium.FeatureGroup(name="Track", show=True)
    rest_layer = folium.FeatureGroup(name="Rest Stops", show=True)

    steepness_colormap = LinearColormap(
        colors=["#006400", "#00c853", "#005bff", "#ffe600", "#ff8f00", "#d50000"],
        vmin=-steepness_range,
        vmax=steepness_range,
        caption="Track steepness (%)",
    )

    for start, end in zip(track_points, track_points[1:]):
        grade_percent = _segment_grade_percent(start, end)
        if grade_percent is None:
            segment_color = "#005bff"
        else:
            clipped_grade = max(-steepness_range, min(steepness_range, grade_percent))
            segment_color = steepness_colormap(clipped_grade)

        segment_points = [[start.latitude, start.longitude], [end.latitude, end.longitude]]

        if track_casing:
            folium.PolyLine(
                segment_points,
                color="#111111",
                weight=9,
                opacity=0.7,
            ).add_to(track_layer)

        folium.PolyLine(
            segment_points,
            color=segment_color,
            weight=6,
            opacity=0.98,
        ).add_to(track_layer)

    steepness_colormap.add_to(fmap)

    if rest_stops:
        durations = [stop.duration_s for stop in rest_stops]
        min_duration = min(durations)
        max_duration = max(durations)
        legend_max = max_duration if max_duration > min_duration else min_duration + 1.0
        colormap = LinearColormap(
            colors=["#ffff00", "#ff0000"],
            vmin=min_duration,
            vmax=legend_max,
            caption="Rest stop duration (seconds)",
        )

        for idx, stop in enumerate(rest_stops, start=1):
            color = colormap(stop.duration_s)
            start_hms = stop.start_time.strftime("%H:%M:%S")
            duration_mmss = _format_mmss(stop.duration_s)
            elevation_m = (
                f"{round(stop.elevation_m):.0f}" if stop.elevation_m is not None else "n/a"
            )
            info_html = (
                f"Stop {idx}<br>"
                f"Start: {start_hms}<br>"
                f"Duration: {duration_mmss}<br>"
                f"Elevation: {elevation_m} m"
            )
            folium.CircleMarker(
                location=[stop.latitude, stop.longitude],
                radius=7,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.9,
                weight=2,
                popup=info_html,
                tooltip=folium.Tooltip(info_html, sticky=True),
            ).add_to(rest_layer)

        colormap.add_to(fmap)

    track_layer.add_to(fmap)
    rest_layer.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    bounds = [[point.latitude, point.longitude] for point in track_points]
    fmap.fit_bounds(bounds)

    map_file.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(map_file))
    return map_file


def main() -> None:
    parser = _build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()
    if args.gpx_file is None:
        parser.error("gpx_file is required")

    analyzer = GPXAnalyzer()
    analyzer.read_gpx_file(args.gpx_file)
    prefix = args.csv_prefix if args.csv_prefix else args.gpx_file.stem

    track_points = analyzer.get_track_points()
    pretty_stats = analyzer.get_ride_stats_pretty(
        track_points=track_points,
        min_distance_m=args.min_moving_distance_m,
    )

    print("GPX analysis")
    print("============")
    print(f"File: {args.gpx_file}")
    print(f"Track points: {len(track_points)}")
    print(f"Total distance (km): {pretty_stats['total_distance_km']}")
    print(f"Moving time (HH:MM:SS): {pretty_stats['moving_time_hms']}")
    print(f"Average speed (km/h): {pretty_stats['average_speed_kmh']}")

    rest_stops = analyzer.find_rest_stops(
        track_points=track_points,
        radius_m=args.radius_m,
        min_duration_s=args.min_rest_seconds,
    )
    local_track_points = _localize_track_points(track_points)
    local_rest_stops = _localize_rest_stops(rest_stops)

    print()
    print(
        "Detected rest stops "
        f"(radius <= {args.radius_m} m, duration >= {args.min_rest_seconds} s): {len(rest_stops)}"
    )

    for idx, stop in enumerate(local_rest_stops, start=1):
        print(
            f"{idx:02d}. "
            f"{stop.start_time.isoformat()} -> {stop.end_time.isoformat()}, "
            f"duration {stop.duration_s:.0f}s, "
            f"lat {stop.latitude:.6f}, lon {stop.longitude:.6f}, "
            f"ele {stop.elevation_m if stop.elevation_m is not None else 'n/a'}"
        )

    try:
        points_df = analyzer.to_dataframe(track_points=local_track_points)
        rest_df = analyzer.rest_stops_to_dataframe(rest_stops=local_rest_stops)

        print()
        print("Track points DataFrame preview:")
        print(points_df.head(args.head))

        print()
        print("Rest stops DataFrame preview:")
        print(rest_df.head(args.head))

        if args.export_csv:
            csv_dir = args.csv_dir
            csv_dir.mkdir(parents=True, exist_ok=True)

            points_csv_path = csv_dir / f"{prefix}_track_points.csv"
            rest_csv_path = csv_dir / f"{prefix}_rest_stops.csv"

            points_df.to_csv(points_csv_path, index=False)
            rest_df.to_csv(rest_csv_path, index=False)

            print()
            print("CSV export complete:")
            print(f"- {points_csv_path}")
            print(f"- {rest_csv_path}")
    except ImportError as exc:
        print()
        print(f"DataFrame preview skipped: {exc}")

    if args.export_map:
        map_file = args.map_file if args.map_file is not None else Path(f"{prefix}_map.html")
        try:
            output_path = _export_map(
                map_file=map_file,
                track_points=local_track_points,
                rest_stops=local_rest_stops,
                steepness_range=args.steepness_range,
                track_casing=args.track_casing,
            )
            print()
            print("Map export complete:")
            print(f"- {output_path}")
        except ImportError as exc:
            print()
            print(f"Map export skipped: {exc}")


if __name__ == "__main__":
    main()

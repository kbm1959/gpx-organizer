"""Tests for map service rendering helpers."""

from __future__ import annotations

from pathlib import Path

from gpx_organizer.map_service import LeafletMapService


SAMPLE_GPX = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<gpx version=\"1.1\" creator=\"test\" xmlns=\"http://www.topografix.com/GPX/1/1\">
  <trk>
    <name>Sample</name>
    <trkseg>
      <trkpt lat=\"48.100000\" lon=\"7.100000\">
        <ele>200</ele>
        <time>2026-08-08T08:00:00Z</time>
      </trkpt>
      <trkpt lat=\"48.101000\" lon=\"7.101000\">
        <ele>210</ele>
        <time>2026-08-08T08:02:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
"""


def test_render_track_contains_leaflet_and_track_name(tmp_path: Path) -> None:
    gpx_path = tmp_path / "sample.gpx"
    gpx_path.write_text(SAMPLE_GPX, encoding="utf-8")

    service = LeafletMapService()
    rendered = service.render_track(gpx_path, "Sample Ride")

    assert rendered.title == "Sample Ride"
    assert "leaflet" in rendered.html.lower()
    assert "Sample Ride" in rendered.html


def test_render_placeholder_escapes_html() -> None:
    service = LeafletMapService()
    rendered = service.render_placeholder("<Title>", "Message <script>")

    assert "&lt;Title&gt;" in rendered.html
    assert "<script>" not in rendered.html


def test_render_track_supports_configurable_threshold_and_bicycle_overlay(tmp_path: Path) -> None:
    gpx_path = tmp_path / "sample.gpx"
    gpx_path.write_text(SAMPLE_GPX, encoding="utf-8")

    service = LeafletMapService(responsive_threshold_px=760)
    rendered = service.render_track(gpx_path, "Sample Ride")

    assert "@media (max-width: 760px)" in rendered.html
    assert "const responsiveThresholdPx = 760;" in rendered.html
    assert "Bicycle Routes" in rendered.html
    assert "waymarkedtrails.org/cycling" in rendered.html
    assert "Show Gradient" in rendered.html
    assert "Track Points" in rendered.html
    assert "Direction Arrows" in rendered.html
    assert "applyGradientMode" in rendered.html
    assert "#0B3D2E" in rendered.html
    assert "#F2D64B" in rendered.html
    assert "#8B0000" in rendered.html
    assert "Trim Start" in rendered.html
    assert "Trim End" in rendered.html
    assert "window.location.hash = `gpxcmd=1" in rendered.html
    assert "points: L.layerGroup()," in rendered.html
    assert "const initialOverlays =" in rendered.html


def test_render_track_supports_direction_arrow_color_and_count(tmp_path: Path) -> None:
    gpx_path = tmp_path / "sample.gpx"
    gpx_path.write_text(SAMPLE_GPX, encoding="utf-8")

    service = LeafletMapService(
        direction_arrow_color="#CC5500",
        direction_arrow_count=6,
        direction_arrow_size_px=18,
    )
    rendered = service.render_track(gpx_path, "Sample Ride")

    assert '"directionArrowColor": "#CC5500"' in rendered.html
    assert '"directionArrowSizePx": 18' in rendered.html
    assert "directionArrows" in rendered.html
    assert "updateDirectionArrowsForViewport" in rendered.html
    assert 'map.on("moveend", updateDirectionArrowsForViewport);' in rendered.html
    assert rendered.html.count('"bearingDeg"') == 6
    assert "L.control.scale({ imperial: false }).addTo(map);" in rendered.html


def test_render_track_default_arrow_count_is_ten(tmp_path: Path) -> None:
    gpx_path = tmp_path / "sample.gpx"
    gpx_path.write_text(SAMPLE_GPX, encoding="utf-8")

    service = LeafletMapService()
    rendered = service.render_track(gpx_path, "Sample Ride")

    assert '"directionArrowSizePx": 12' in rendered.html
    assert rendered.html.count('"bearingDeg"') == 10
    assert '"trackPointColor": "#000000"' in rendered.html
    assert '"trackPointSizePx": 1' in rendered.html


def test_render_track_lines_preview_for_multiple_tracks(tmp_path: Path) -> None:
    gpx_a = tmp_path / "a.gpx"
    gpx_b = tmp_path / "b.gpx"
    gpx_a.write_text(SAMPLE_GPX.replace("Sample", "A"), encoding="utf-8")
    gpx_b.write_text(SAMPLE_GPX.replace("Sample", "B"), encoding="utf-8")

    service = LeafletMapService()
    rendered = service.render_track_lines_preview(
        [
            (gpx_a, "Track A"),
            (gpx_b, "Track B"),
        ]
    )

    assert rendered.title == "Track Overview"
    assert "track(s) in current folder view" in rendered.html
    assert "L.featureGroup().addTo(map)" in rendered.html
    assert "L.control.scale({ imperial: false }).addTo(map);" in rendered.html


def test_render_tracks_with_overlays_for_multiple_tracks(tmp_path: Path) -> None:
    gpx_a = tmp_path / "a.gpx"
    gpx_b = tmp_path / "b.gpx"
    gpx_a.write_text(SAMPLE_GPX.replace("Sample", "A"), encoding="utf-8")
    gpx_b.write_text(SAMPLE_GPX.replace("Sample", "B"), encoding="utf-8")

    service = LeafletMapService(direction_arrow_count=7)
    rendered = service.render_tracks_with_overlays(
        [
            (gpx_a, "Track A"),
            (gpx_b, "Track B"),
        ]
    )

    assert rendered.title == "2 selected tracks"
    assert "Track Points" in rendered.html
    assert "Direction Arrows" in rendered.html
    assert "Rest Stops" in rendered.html
    assert "selected tracks" in rendered.html
    assert "L.control.scale({ imperial: false }).addTo(map);" in rendered.html


def test_render_track_lines_preview_contains_each_track_entry(tmp_path: Path) -> None:
    gpx_a = tmp_path / "a.gpx"
    gpx_b = tmp_path / "b.gpx"
    gpx_a.write_text(SAMPLE_GPX.replace("Sample", "A"), encoding="utf-8")
    gpx_b.write_text(SAMPLE_GPX.replace("Sample", "B"), encoding="utf-8")

    service = LeafletMapService()
    rendered = service.render_track_lines_preview(
        [
            (11, gpx_a, "Track A", "My Library/folder1/subfolder/Track A"),
            (22, gpx_b, "Track B", "My Library/folder2/Track B"),
        ]
    )

    assert '"name": "Track A"' in rendered.html
    assert '"name": "Track B"' in rendered.html
    assert '"trackId": 11' in rendered.html
    assert '"hoverLabel": "My Library/folder1/subfolder/Track A"' in rendered.html
    assert "bindTooltip(track.hoverLabel" in rendered.html
    assert "action=open_track&track_id=" in rendered.html
    assert "window.__gpxFitTrack = function()" in rendered.html

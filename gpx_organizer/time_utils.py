"""Timezone-aware display formatting for GPX timestamps."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIME_ZONE = "Europe/Berlin"


def normalize_time_zone(value: str) -> str:
    name = value.strip()
    try:
        ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        return DEFAULT_TIME_ZONE
    return name


def format_track_time(value: str | None, time_zone: str) -> str | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.utcoffset() is None:
        return timestamp.isoformat(sep=" ", timespec="seconds") + " (timezone unknown)"
    converted = timestamp.astimezone(ZoneInfo(normalize_time_zone(time_zone)))
    offset = converted.strftime("%z")
    return (
        f"{converted:%Y-%m-%d %H:%M:%S} {converted.tzname()} "
        f"(UTC{offset[:3]}:{offset[3:]})"
    )
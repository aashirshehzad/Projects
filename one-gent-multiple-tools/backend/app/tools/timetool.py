"""Current date/time for any IANA timezone (or a few common city aliases)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

DECLARATION = {
    "name": "get_current_time",
    "description": "Get the current date and time for a timezone, e.g. 'Asia/Karachi', 'Europe/London', or a city name like 'Tokyo'.",
    "parameters": {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone name or a well-known city name.",
            }
        },
        "required": ["timezone"],
    },
}

_ALIASES = {
    "utc": "UTC", "gmt": "UTC",
    "new york": "America/New_York", "nyc": "America/New_York",
    "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "chicago": "America/Chicago", "toronto": "America/Toronto",
    "london": "Europe/London", "paris": "Europe/Paris", "berlin": "Europe/Berlin",
    "madrid": "Europe/Madrid", "rome": "Europe/Rome", "moscow": "Europe/Moscow",
    "dubai": "Asia/Dubai", "karachi": "Asia/Karachi", "lahore": "Asia/Karachi",
    "islamabad": "Asia/Karachi", "delhi": "Asia/Kolkata", "mumbai": "Asia/Kolkata",
    "tokyo": "Asia/Tokyo", "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong",
    "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai", "sydney": "Australia/Sydney",
}


def _resolve(tz: str) -> str | None:
    raw = tz.strip()
    if raw in available_timezones():
        return raw
    low = raw.lower()
    if low in _ALIASES:
        return _ALIASES[low]
    for name in available_timezones():
        if name.lower() == low or name.lower().split("/")[-1].replace("_", " ") == low:
            return name
    return None


def run(timezone: str) -> dict:
    resolved = _resolve(timezone)
    if not resolved:
        return {"error": f"Unknown timezone '{timezone}'. Use an IANA name like 'Europe/London'."}
    now = datetime.now(ZoneInfo(resolved))
    return {
        "timezone": resolved,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "iso": now.isoformat(),
        "day_of_week": now.strftime("%A"),
        "utc_offset": now.strftime("%z"),
    }

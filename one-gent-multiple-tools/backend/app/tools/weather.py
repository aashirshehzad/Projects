"""Current weather for a city, powered by the keyless Open-Meteo API."""
from __future__ import annotations

from ._http import get_json

DECLARATION = {
    "name": "get_weather",
    "description": "Get the current weather (temperature, wind, humidity, conditions) for a city or place.",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name, optionally with country, e.g. 'Lahore' or 'Paris, France'.",
            }
        },
        "required": ["city"],
    },
}

# https://open-meteo.com/en/docs -> WMO weather interpretation codes
_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


def run(city: str) -> dict:
    geo = get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": city, "count": 1, "language": "en", "format": "json"},
    )
    results = geo.get("results") or []
    if not results:
        return {"error": f"Could not find a place called '{city}'."}

    place = results[0]
    lat, lon = place["latitude"], place["longitude"]
    forecast = get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code",
        },
    )
    cur = forecast.get("current", {})
    code = cur.get("weather_code")
    return {
        "location": ", ".join(
            p for p in [place.get("name"), place.get("admin1"), place.get("country")] if p
        ),
        "temperature_c": cur.get("temperature_2m"),
        "feels_like_c": cur.get("apparent_temperature"),
        "humidity_percent": cur.get("relative_humidity_2m"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "conditions": _CODES.get(code, f"code {code}"),
    }

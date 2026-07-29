import logging

import httpx

logger = logging.getLogger("voice_ai_agent")

# WMO weather codes -> a short, speakable description.
_WEATHER_CODES = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    80: "rain showers", 81: "rain showers", 82: "heavy rain showers",
    95: "thunderstorms", 96: "thunderstorms", 99: "thunderstorms",
}


async def get_weather_blurb(city: str) -> str | None:
    """Looks up real current weather for a city via Open-Meteo (free, no API
    key). Returns a short speakable phrase, or None if the city is missing or
    the lookup fails for any reason -- callers should treat that as
    'skip the weather line' rather than an error."""
    if not city:
        return None
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            geo = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1},
            )
            geo.raise_for_status()
            results = geo.json().get("results")
            if not results:
                return None
            lat, lon = results[0]["latitude"], results[0]["longitude"]

            forecast = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code",
                    "temperature_unit": "fahrenheit",
                },
            )
            forecast.raise_for_status()
            current = forecast.json().get("current", {})
            temp = current.get("temperature_2m")
            code = current.get("weather_code")
            if temp is None or code is None:
                return None
            condition = _WEATHER_CODES.get(code, "mild weather")
            city_label = city.split(",")[0]
            return f"about {round(temp)} degrees and {condition} in {city_label}"
    except Exception:
        logger.exception("Weather lookup failed for city=%s", city)
        return None

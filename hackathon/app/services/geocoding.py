"""
Geocoding service — converts location text to lat/lng coordinates.

Uses OpenStreetMap Nominatim (free, no API key needed).
Biased toward Morocco for better results.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Cache to avoid repeat lookups for the same location text
_cache: dict[str, tuple[float, float]] = {}


async def geocode_location(location_text: str) -> Optional[tuple[float, float]]:
    """
    Convert a location string to (latitude, longitude).
    Returns None if geocoding fails.
    Biased toward Morocco.
    """
    if not location_text or len(location_text.strip()) < 2:
        return None

    location_text = location_text.strip()

    # Check cache
    cache_key = location_text.lower()
    if cache_key in _cache:
        logger.debug("Geocode cache hit: %s", location_text)
        return _cache[cache_key]

    # If the text already contains lat,lng coords, parse directly
    import re
    coord_match = re.match(r'^([-\d.]+)\s*,\s*([-\d.]+)$', location_text.strip())
    if coord_match:
        lat, lng = float(coord_match.group(1)), float(coord_match.group(2))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            _cache[cache_key] = (lat, lng)
            return (lat, lng)

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # Try with Morocco bias first
            resp = await client.get(
                NOMINATIM_URL,
                params={
                    "q": location_text,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "ma",  # Bias toward Morocco
                    "accept-language": "en,fr,ar",
                },
                headers={
                    "User-Agent": "2020AIAgent/1.0",
                },
            )
            resp.raise_for_status()
            results = resp.json()

            # If no results with Morocco bias, try worldwide
            if not results:
                resp = await client.get(
                    NOMINATIM_URL,
                    params={
                        "q": location_text,
                        "format": "json",
                        "limit": 1,
                        "accept-language": "en,fr,ar",
                    },
                    headers={
                        "User-Agent": "2020AIAgent/1.0",
                    },
                )
                resp.raise_for_status()
                results = resp.json()

            if results:
                lat = float(results[0]["lat"])
                lng = float(results[0]["lon"])
                _cache[cache_key] = (lat, lng)
                logger.info(
                    "Geocoded '%s' → (%.6f, %.6f) [%s]",
                    location_text, lat, lng,
                    results[0].get("display_name", "")[:60],
                )
                return (lat, lng)
            else:
                logger.warning("Geocoding returned no results for: '%s'", location_text)
                return None

    except Exception as e:
        logger.warning("Geocoding failed for '%s': %s", location_text, e)
        return None

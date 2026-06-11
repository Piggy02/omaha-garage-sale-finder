"""Address geocoding via OpenStreetMap's Nominatim, with a disk cache and rate limiting."""

import json
import os
import threading
import time

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "OmahaGarageSaleFinder/1.0 (personal project; contact: jacobabyss@googlemail.com)"
MIN_REQUEST_INTERVAL = 1.1  # seconds, per Nominatim usage policy
OMAHA_VIEWBOX = "-96.3,41.45,-95.7,41.05"  # rough bounding box around the Omaha metro

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geocode_cache.json")

_lock = threading.Lock()
_last_request_time = 0.0
_cache = None
_suggest_cache = {}


def _load_cache():
    global _cache
    if _cache is not None:
        return _cache
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            _cache = {}
    else:
        _cache = {}
    return _cache


def _save_cache():
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f)
    except OSError:
        pass


def _nominatim_request(params):
    global _last_request_time
    with _lock:
        elapsed = time.monotonic() - _last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)

        try:
            response = requests.get(
                NOMINATIM_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            response.raise_for_status()
            results = response.json()
        except (requests.RequestException, ValueError):
            results = []
        finally:
            _last_request_time = time.monotonic()

    return results


def geocode(query):
    """Return (lat, lon) for a free-text address/place, or None if it can't be found.

    Results are cached on disk indefinitely (keyed by the lowercased query string),
    since geographic locations don't move.
    """
    if not query:
        return None

    key = query.strip().lower()
    cache = _load_cache()

    if key in cache:
        return tuple(cache[key]) if cache[key] is not None else None

    results = _nominatim_request({"q": query, "format": "json", "limit": 1})

    if results:
        result = (float(results[0]["lat"]), float(results[0]["lon"]))
    else:
        result = None

    cache[key] = list(result) if result else None
    _save_cache()

    return result


def search_suggestions(query, limit=5):
    """Return a list of address suggestion strings for the given partial query,
    biased toward the Omaha metro area. Cached in memory for the life of the process.
    """
    if not query:
        return []

    key = query.strip().lower()
    if key in _suggest_cache:
        return _suggest_cache[key]

    results = _nominatim_request({
        "q": query,
        "format": "json",
        "limit": limit,
        "countrycodes": "us",
        "viewbox": OMAHA_VIEWBOX,
        "bounded": 0,
        "addressdetails": 0,
    })

    suggestions = [r["display_name"] for r in results]
    _suggest_cache[key] = suggestions
    return suggestions

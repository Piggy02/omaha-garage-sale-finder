"""Scrapes Yard Sale Treasure Map (Omaha) and filters down to "today"."""

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://yardsaletreasuremap.com"
SEARCH_URL = f"{BASE_URL}/US/Nebraska/Omaha.html"
USER_AGENT = "OmahaGarageSaleFinder/1.0 (personal project; contact: jacobabyss@googlemail.com)"
TIMEZONE = ZoneInfo("America/Chicago")
SOURCE_NAME = "Yard Sale Treasure Map"

METADATA_RE = re.compile(r"const metadataStr = '(.*?)';", re.S)
ID_RE = re.compile(r"[?&]id=(\d+)")
PATH_ID_RE = re.compile(r"/(\d+)/(?:user)?listing\.html")


def _extract_sales(html):
    match = METADATA_RE.search(html)
    if not match:
        return []
    raw = match.group(1).encode().decode("unicode_escape")
    data = json.loads(raw)
    return data.get("sales", [])


def _image_url(media_json):
    if not media_json:
        return None
    try:
        media = json.loads(media_json)
    except ValueError:
        return None
    files = media.get("media") or []
    if not files:
        return None
    return f"{media['baseUrl']}/{files[0]}"


def _sale_id(url):
    match = ID_RE.search(url) or PATH_ID_RE.search(url)
    return f"ystm-{match.group(1)}" if match else f"ystm-{abs(hash(url))}"


def scrape_todays_listings():
    """Scrape Yard Sale Treasure Map and return today's Omaha-area sales.

    Returns a list of dicts matching the schema used by scraper.py.
    """
    today = datetime.now(TIMEZONE).date()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    response = session.get(SEARCH_URL, timeout=15)
    response.raise_for_status()
    sales = _extract_sales(response.text)

    results = []
    for sale in sales:
        sale_date = datetime.fromtimestamp(sale["date"], tz=TIMEZONE).date()
        if sale_date != today:
            continue

        location = sale["address"].strip()
        if location and "NE" not in location and "Nebraska" not in location:
            location = f"{location}, Omaha, NE"

        results.append({
            "id": _sale_id(sale["url"]),
            "title": sale["title"].strip() or "Garage Sale",
            "url": sale["url"],
            "location": location,
            "sale_dates": [today.isoformat()],
            "posted": None,
            "description": sale["description"].strip(),
            "image_url": _image_url(sale.get("media")),
            "source": SOURCE_NAME,
            "lat": float(sale["lat"]),
            "lon": float(sale["lng"]),
        })

    return results

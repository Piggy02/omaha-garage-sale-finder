"""Scrapes Omaha Craigslist garage/moving sales and filters down to "today"."""

import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from geocoding import geocode

BASE_URL = "https://omaha.craigslist.org"
SEARCH_URL = f"{BASE_URL}/search/gms"
SEARCH_PARAMS = {"postal": "68102", "search_distance": "30"}
USER_AGENT = "OmahaGarageSaleFinder/1.0 (personal project; contact: jacobabyss@googlemail.com)"
REQUEST_DELAY = 0.6  # seconds between detail-page fetches, to stay polite to Craigslist
MAX_FALLBACK_CANDIDATES = 25
TIMEZONE = ZoneInfo("America/Chicago")

POST_ID_RE = re.compile(r"/(\d+)\.html$")

MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
IMAGE_RE = re.compile(r"https://images\.craigslist\.org/([A-Za-z0-9_]+)_\d+x\d+c?\.jpg")
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/\d{2,4})?\b")
MONTH_DATE_RE = re.compile(
    r"\b(" + "|".join(MONTH_NAMES.keys()) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)


def _get(session, url, params=None):
    response = session.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.text


def _parse_search_results(html):
    soup = BeautifulSoup(html, "html.parser")
    listings = []

    for li in soup.select("li.cl-static-search-result"):
        a = li.find("a")
        if not a or not a.get("href"):
            continue

        url = a["href"]
        match = POST_ID_RE.search(url)
        if not match:
            continue

        title_el = li.find("div", class_="title")
        title = title_el.get_text(strip=True) if title_el else li.get("title", "")

        location_el = li.find("div", class_="location")
        location = location_el.get_text(strip=True) if location_el else ""

        listings.append({
            "id": match.group(1),
            "url": url,
            "title": title,
            "location": location,
        })

    return listings


def get_candidate_listings(target_iso, session):
    """Return candidate listings: structured sale_date matches plus a bounded
    number of other recent listings to check via text/posted-date heuristics."""
    structured_html = _get(session, SEARCH_URL, {**SEARCH_PARAMS, "sale_date": target_iso})
    structured = _parse_search_results(structured_html)
    structured_ids = {listing["id"] for listing in structured}
    for listing in structured:
        listing["from_structured_search"] = True

    all_html = _get(session, SEARCH_URL, SEARCH_PARAMS)
    all_listings = _parse_search_results(all_html)

    fallback = []
    for listing in all_listings:
        if listing["id"] in structured_ids:
            continue
        listing["from_structured_search"] = False
        fallback.append(listing)
        if len(fallback) >= MAX_FALLBACK_CANDIDATES:
            break

    return structured + fallback


def fetch_listing_detail(url, session):
    html = _get(session, url)
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.find("span", id="titletextonly")
    title = title_el.get_text(strip=True) if title_el else ""

    lat = lon = None
    map_div = soup.find("div", id="map")
    if map_div and map_div.get("data-latitude") and map_div.get("data-longitude"):
        lat = float(map_div["data-latitude"])
        lon = float(map_div["data-longitude"])

    map_address_el = soup.find("div", class_="mapaddress")
    map_address = map_address_el.get_text(strip=True) if map_address_el else ""

    sale_dates = []
    for label in soup.select(".attrgroup .labl"):
        if "date" in label.get_text(strip=True).lower():
            attrgroup = label.find_parent("div", class_="attrgroup")
            if attrgroup:
                for link in attrgroup.find_all("a", href=True):
                    date_match = re.search(r"sale_date=(\d{4}-\d{2}-\d{2})", link["href"])
                    if date_match:
                        sale_dates.append(date_match.group(1))
            break

    posted = None
    time_el = soup.select_one("div.postinginfos time.date")
    if time_el and time_el.get("datetime"):
        try:
            posted = datetime.strptime(time_el["datetime"], "%Y-%m-%dT%H:%M:%S%z")
            posted = posted.astimezone(TIMEZONE)
        except ValueError:
            posted = None

    body_el = soup.find("section", id="postingbody")
    body_text = ""
    if body_el:
        qr_el = body_el.find("div", class_="print-information")
        if qr_el:
            qr_el.decompose()
        body_text = body_el.get_text(" ", strip=True)

    image_url = None
    image_match = IMAGE_RE.search(html)
    if image_match:
        image_url = f"https://images.craigslist.org/{image_match.group(1)}_300x300.jpg"

    return {
        "title": title,
        "lat": lat,
        "lon": lon,
        "map_address": map_address,
        "sale_dates": sorted(set(sale_dates)),
        "posted": posted,
        "body_text": body_text,
        "image_url": image_url,
    }


def _extract_dates(text):
    """Yield (month, day) tuples found anywhere in free text."""
    for month, day in NUMERIC_DATE_RE.findall(text):
        yield int(month), int(day)

    for month_name, day in MONTH_DATE_RE.findall(text):
        month = MONTH_NAMES.get(month_name.lower())
        if month:
            yield month, int(day)


def matches_date(detail, target_date, from_structured_search):
    """Decide whether a listing's sale is happening on the target date.

    Prefers Craigslist's structured sale-date tags. If a posting has none, falls
    back to scanning the title/body for a date matching the target date, and
    finally to "posted today with no other date mentioned" for last-minute
    posts (which only ever matches when target_date is today).
    """
    if detail["sale_dates"]:
        return target_date.isoformat() in detail["sale_dates"]

    if from_structured_search:
        return True

    text = f"{detail['title']} {detail['body_text']}"
    found_dates = list(_extract_dates(text))
    if found_dates:
        return (target_date.month, target_date.day) in found_dates

    return bool(detail["posted"] and detail["posted"].date() == target_date)


def _normalize_text(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _listing_score(listing):
    """Higher is "better" when choosing which copy of a repost to keep."""
    return (
        bool(listing["sale_dates"]),
        bool(listing["image_url"]),
        listing["posted"] or "",
        len(listing["description"] or ""),
    )


def deduplicate_listings(listings):
    """Collapse reposts of the same sale (same ad, new post ID) into one entry.

    Sellers often repost an identical or near-identical ad to bump it back to
    the top of the search results, so we compare normalized title/description
    similarity rather than relying on post IDs or location.
    """
    deduped = []
    signatures = []

    for listing in listings:
        title = _normalize_text(listing["title"])
        description = _normalize_text(listing["description"])

        match_index = None
        for i, (other_title, other_description) in enumerate(signatures):
            title_sim = SequenceMatcher(None, title, other_title).ratio()
            if description and other_description:
                description_sim = SequenceMatcher(None, description, other_description).ratio()
                is_match = title_sim >= 0.5 and description_sim >= 0.75
            else:
                # No description to cross-check, so require the titles to be
                # near-identical to avoid merging unrelated generic posts
                # (e.g. two different sales both titled "Garage Sale").
                is_match = title_sim >= 0.95
            if is_match:
                match_index = i
                break

        if match_index is None:
            signatures.append((title, description))
            deduped.append(listing)
        elif _listing_score(listing) > _listing_score(deduped[match_index]):
            signatures[match_index] = (title, description)
            deduped[match_index] = listing

    return deduped


def scrape_listings(target_date):
    """Scrape, filter to target_date, and geocode listings missing coordinates.

    Returns a list of dicts: id, title, url, location, sale_dates, posted,
    description, image_url, source, lat, lon.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    candidates = get_candidate_listings(target_date.isoformat(), session)

    results = []
    for candidate in candidates:
        time.sleep(REQUEST_DELAY)
        try:
            detail = fetch_listing_detail(candidate["url"], session)
        except requests.RequestException:
            continue

        if not matches_date(detail, target_date, candidate["from_structured_search"]):
            continue

        lat, lon = detail["lat"], detail["lon"]
        location = detail["map_address"] or candidate["location"]
        if (lat is None or lon is None) and location:
            geo = geocode(f"{location}, Omaha, NE")
            if geo:
                lat, lon = geo

        results.append({
            "id": candidate["id"],
            "title": detail["title"] or candidate["title"],
            "url": candidate["url"],
            "location": location,
            "sale_dates": detail["sale_dates"],
            "posted": detail["posted"].isoformat() if detail["posted"] else None,
            "description": detail["body_text"],
            "image_url": detail["image_url"],
            "source": "Craigslist",
            "lat": lat,
            "lon": lon,
        })

    return results

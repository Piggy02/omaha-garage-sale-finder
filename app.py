"""Flask app: serves the garage sale finder UI and the listings API."""

import threading
from datetime import datetime

import requests
from flask import Flask, jsonify, render_template, request

import treasuremap
from geocoding import geocode, search_suggestions
from scraper import TIMEZONE, deduplicate_listings, scrape_todays_listings
from utils import haversine_miles, maps_directions_url

app = Flask(__name__)

CACHE_TTL_SECONDS = 20 * 60

_cache_lock = threading.Lock()
_cache = {"date": None, "fetched_at": None, "listings": []}


def get_todays_listings():
    today = datetime.now(TIMEZONE).date()

    with _cache_lock:
        now = datetime.now(TIMEZONE)
        is_fresh = (
            _cache["date"] == today
            and _cache["fetched_at"] is not None
            and (now - _cache["fetched_at"]).total_seconds() < CACHE_TTL_SECONDS
        )
        if is_fresh:
            return _cache["listings"]

        listings = []
        for scrape in (scrape_todays_listings, treasuremap.scrape_todays_listings):
            try:
                listings.extend(scrape())
            except requests.RequestException:
                continue

        listings = deduplicate_listings(listings)
        _cache["date"] = today
        _cache["fetched_at"] = datetime.now(TIMEZONE)
        _cache["listings"] = listings
        return listings


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/listings")
def api_listings():
    address = request.args.get("address", "").strip()
    if not address:
        return jsonify({"error": "Please enter an address."}), 400

    user_location = geocode(address) or geocode(f"{address}, Omaha, NE")
    if not user_location:
        return jsonify({
            "error": "Couldn't find that address. Try adding the city and state.",
        }), 400

    user_lat, user_lon = user_location
    listings = get_todays_listings()

    results = []
    for listing in listings:
        if listing["lat"] is not None and listing["lon"] is not None:
            distance = haversine_miles(user_lat, user_lon, listing["lat"], listing["lon"])
            maps_url = maps_directions_url(lat=listing["lat"], lon=listing["lon"])
        else:
            distance = None
            maps_url = (
                maps_directions_url(address=f"{listing['location']}, Omaha, NE")
                if listing["location"] else None
            )

        results.append({
            "id": listing["id"],
            "title": listing["title"],
            "url": listing["url"],
            "location": listing["location"],
            "sale_dates": listing["sale_dates"],
            "posted": listing["posted"],
            "description": listing["description"],
            "image_url": listing["image_url"],
            "source": listing["source"],
            "distance_miles": round(distance, 1) if distance is not None else None,
            "maps_url": maps_url,
        })

    results.sort(key=lambda r: (r["distance_miles"] is None, r["distance_miles"] or 0))

    return jsonify({"count": len(results), "listings": results})


@app.route("/api/autocomplete")
def api_autocomplete():
    query = request.args.get("q", "").strip()
    if len(query) < 3:
        return jsonify({"suggestions": []})

    return jsonify({"suggestions": search_suggestions(query)})


if __name__ == "__main__":
    app.run(debug=True)

"""Small geometry/URL helpers shared by the scraper and the Flask app."""

import math
from urllib.parse import quote


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in miles."""
    earth_radius_miles = 3958.8

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius_miles * c


def maps_directions_url(lat=None, lon=None, address=None):
    """Build a Google Maps directions URL that opens the Maps app on mobile.

    Prefers coordinates when available, falling back to an address string.
    """
    if lat is not None and lon is not None:
        destination = f"{lat},{lon}"
    elif address:
        destination = address
    else:
        return None

    return f"https://www.google.com/maps/dir/?api=1&destination={quote(destination)}"

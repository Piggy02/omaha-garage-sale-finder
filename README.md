# Omaha Garage Sale Finder

Finds today's garage & moving sales on Omaha Craigslist, sorted by distance from
your address, with one-tap Google Maps directions.

## How it works

- Scrapes `omaha.craigslist.org/search/gms` (covers Omaha, Bellevue, Papillion,
  Council Bluffs, Gretna, Elkhorn, etc. via a 30-mile radius from downtown Omaha).
- Uses Craigslist's structured `sale_date` field where available, and falls back to
  scanning the post text / posted date for listings that don't set it.
- Geocodes listing locations and your address with OpenStreetMap Nominatim.
- Results are cached for ~20 minutes so repeated searches are fast; the first
  search of the day can take up to a minute while it scrapes and geocodes.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 and enter an address.

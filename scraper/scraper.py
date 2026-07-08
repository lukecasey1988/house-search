"""
Daily house search scraper.

Fetches current listings for each configured village from Rightmove,
compares against previously seen listings, and writes:
  - data/current_listings.json  (everything currently live, for the website)
  - data/seen_ids.json          (all IDs ever seen, so we can detect new ones)
  - data/new_today.json         (just today's new matches, for a highlight banner)

Designed to be run once a day via GitHub Actions (see .github/workflows/daily_scrape.yml).
"""
import json
import re
import time
import sys
import os
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    LOCATIONS, MIN_PRICE, MAX_PRICE, MIN_BEDROOMS,
    LAND_KEYWORDS, REQUEST_HEADERS, REQUEST_DELAY_SECONDS,
)

BASE_URL = "https://www.rightmove.co.uk/property-for-sale/{slug}.html"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def fetch_location(slug: str) -> list[dict]:
    """Fetch all matching listings for one location slug, following pagination."""
    all_props = []
    index = 0
    while True:
        url = BASE_URL.format(slug=slug)
        params = {
            "minPrice": MIN_PRICE,
            "maxPrice": MAX_PRICE,
            "minBedrooms": MIN_BEDROOMS,
            "index": index,
        }
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, params=params, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ERROR fetching {slug} (index {index}): {e}")
            break

        match = NEXT_DATA_RE.search(resp.text)
        if not match:
            print(f"  WARNING: could not find __NEXT_DATA__ for {slug} - page structure "
                  f"may have changed and this scraper needs updating.")
            break

        try:
            data = json.loads(match.group(1))
            search_results = data["props"]["pageProps"]["searchResults"]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ERROR parsing JSON for {slug}: {e}")
            break

        props = search_results.get("properties", [])
        all_props.extend(props)

        pagination = search_results.get("pagination", {})
        total_pages = len(pagination.get("options", [1]))
        current_page = int(pagination.get("page", "1"))
        if current_page >= total_pages:
            break
        index += 24
        time.sleep(REQUEST_DELAY_SECONDS)

    return all_props


def has_land_mention(listing: dict) -> bool:
    text = (listing.get("summary") or "") + " " + (listing.get("displayAddress") or "")
    text = text.lower()
    return any(kw in text for kw in LAND_KEYWORDS)


def normalise(listing: dict, village: str) -> dict:
    price = listing.get("price", {}).get("amount")
    listing_id = listing.get("id")
    prop_url = listing.get("propertyUrl", "")
    full_url = f"https://www.rightmove.co.uk{prop_url}" if prop_url else None
    images = listing.get("images", [])
    thumb = images[0]["srcUrl"] if images else None
    added_reduced = listing.get("addedOrReduced", "")

    return {
        "id": listing_id,
        "village": village,
        "address": listing.get("displayAddress"),
        "price": price,
        "price_display": listing.get("price", {}).get("displayPrices", [{}])[0].get("displayPrice"),
        "bedrooms": listing.get("bedrooms"),
        "bathrooms": listing.get("bathrooms"),
        "property_type": listing.get("propertySubType"),
        "summary": listing.get("summary"),
        "url": full_url,
        "thumbnail": thumb,
        "added_or_reduced": added_reduced,
        "has_land_mention": has_land_mention(listing),
        "first_seen": None,  # filled in below when merging with history
    }


def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: str, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def main():
    seen_path = os.path.join(DATA_DIR, "seen_ids.json")
    current_path = os.path.join(DATA_DIR, "current_listings.json")
    new_today_path = os.path.join(DATA_DIR, "new_today.json")

    seen_ids = load_json(seen_path, {})  # {id: first_seen_date}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    all_current = []
    new_today = []

    for village, slug in LOCATIONS.items():
        print(f"Fetching {village} ({slug})...")
        raw_listings = fetch_location(slug)
        print(f"  -> {len(raw_listings)} listings matched price/bedroom filters")

        for raw in raw_listings:
            listing = normalise(raw, village)
            lid = str(listing["id"])

            if lid not in seen_ids:
                seen_ids[lid] = today
                listing["first_seen"] = today
                new_today.append(listing)
            else:
                listing["first_seen"] = seen_ids[lid]

            all_current.append(listing)

        time.sleep(REQUEST_DELAY_SECONDS)

    all_current.sort(key=lambda x: x["first_seen"] or "", reverse=True)

    save_json(seen_path, seen_ids)
    save_json(current_path, {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "listings": all_current,
    })
    save_json(new_today_path, {
        "date": today,
        "listings": new_today,
    })

    print(f"\nDone. {len(all_current)} total live listings, {len(new_today)} new today.")


if __name__ == "__main__":
    main()

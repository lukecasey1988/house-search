"""
Rightmove source. Uses their location-slug search pages, which embed a clean
JSON blob (__NEXT_DATA__) with structured listing data - the most reliable
source we have.
"""
import re
import json
import time

import requests

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
BASE_URL = "https://www.rightmove.co.uk/property-for-sale/{slug}.html"

SOURCE_NAME = "Rightmove"


def fetch(slug: str, min_price: int, max_price: int, min_bedrooms: int,
          headers: dict, delay: float) -> list[dict]:
    """Fetch all matching listings for one Rightmove location slug."""
    all_props = []
    index = 0
    while True:
        params = {
            "minPrice": min_price,
            "maxPrice": max_price,
            "minBedrooms": min_bedrooms,
            "index": index,
        }
        try:
            resp = requests.get(BASE_URL.format(slug=slug), headers=headers,
                                 params=params, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    [Rightmove] ERROR fetching {slug} (index {index}): {e}")
            break

        match = NEXT_DATA_RE.search(resp.text)
        if not match:
            print(f"    [Rightmove] WARNING: page structure changed for {slug}, "
                  f"scraper needs updating.")
            break

        try:
            data = json.loads(match.group(1))
            search_results = data["props"]["pageProps"]["searchResults"]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"    [Rightmove] ERROR parsing JSON for {slug}: {e}")
            break

        props = search_results.get("properties", [])
        all_props.extend(props)

        pagination = search_results.get("pagination", {})
        total_pages = len(pagination.get("options", [1]))
        current_page = int(pagination.get("page", "1"))
        if current_page >= total_pages:
            break
        index += 24
        time.sleep(delay)

    return [_normalise(p) for p in all_props]


def _normalise(listing: dict) -> dict:
    price = listing.get("price", {}).get("amount")
    prop_url = listing.get("propertyUrl", "")
    full_url = f"https://www.rightmove.co.uk{prop_url}" if prop_url else None
    images = listing.get("images", [])
    thumb = images[0]["srcUrl"] if images else None

    return {
        "source": SOURCE_NAME,
        "source_id": str(listing.get("id")),
        "address": listing.get("displayAddress"),
        "price": price,
        "price_display": listing.get("price", {}).get("displayPrices", [{}])[0].get("displayPrice"),
        "bedrooms": listing.get("bedrooms"),
        "bathrooms": listing.get("bathrooms"),
        "property_type": listing.get("propertySubType"),
        "summary": listing.get("summary"),
        "url": full_url,
        "thumbnail": thumb,
    }

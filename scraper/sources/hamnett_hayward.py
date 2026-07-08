"""
Hamnett Hayward (Thame) source - covers Long Crendon, Ludgershall, and
surrounding villages well since they're the local Thame-based independent agent.

Their site runs on an "eaPow"/EstateWeb template (identifiable by the
"eapow-*" CSS class names) - fairly plain server-rendered HTML with no JSON
API, so this uses regex extraction rather than a JSON parse. If Hamnett
Hayward redesigns their website, the regex patterns below will need updating -
check by viewing page source on https://www.hamnetthayward.co.uk/properties-for-sale
and searching for "eapow-overview-row".
"""
import re
import time

import requests

SOURCE_NAME = "Hamnett Hayward"
BASE = "https://www.hamnetthayward.co.uk"
LIST_URL = f"{BASE}/properties-for-sale"

BLOCK_RE = re.compile(r'<div class="eapow-row\d+ eapow-overview-row.*?(?=<div class="eapow-row\d+ eapow-overview-row|\Z)', re.S)
LINK_RE = re.compile(r'href="(/properties-for-sale/property/[^"]+)"')
THUMB_RE = re.compile(r'data-src="([^"]+)"')
TITLE_RE = re.compile(r'eapow-property-header-accent">\s*(.*?)\s*</a>', re.S)
PRICE_RE = re.compile(r'propPrice">([^<]+)<')
BEDS_RE = re.compile(r'flaticon-bed.*?IconNum">(\d+)', re.S)
BATHS_RE = re.compile(r'flaticon-bath.*?IconNum">(\d+)', re.S)
DESC_RE = re.compile(r'eapow-overview-short-desc"><p>(.*?)</p>', re.S)
TOTAL_PAGES_RE = re.compile(r'Results \d+ - \d+ of (\d+)')


def fetch(min_price: int, max_price: int, min_bedrooms: int,
          headers: dict, delay: float, village_filter: list[str]) -> list[dict]:
    """Fetch all listings, filtered to the target villages and criteria in Python
    (this site doesn't support server-side price/bedroom filtering via simple URL params)."""
    results = []
    start = 0
    page_size = 12

    while True:
        try:
            resp = requests.get(LIST_URL, headers=headers,
                                 params={"start": start} if start else {}, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    [Hamnett Hayward] ERROR fetching page (start={start}): {e}")
            break

        html = resp.text
        total_match = TOTAL_PAGES_RE.search(html)
        total_listings = int(total_match.group(1)) if total_match else None

        blocks = BLOCK_RE.findall(html)
        if not blocks:
            if start == 0:
                print("    [Hamnett Hayward] WARNING: no listing blocks found - "
                      "site structure may have changed, scraper needs updating.")
            break

        for block in blocks:
            listing = _parse_block(block)
            if listing:
                results.append(listing)

        start += page_size
        if total_listings is not None and start >= total_listings:
            break
        time.sleep(delay)

    filtered = []
    for listing in results:
        if listing["price"] is None:
            continue
        if not (min_price <= listing["price"] <= max_price):
            continue
        if listing["bedrooms"] is not None and listing["bedrooms"] < min_bedrooms:
            continue
        address = (listing["address"] or "").lower()
        if village_filter and not any(v.lower() in address for v in village_filter):
            continue
        filtered.append(listing)

    return filtered


def _parse_block(block: str) -> dict | None:
    link_match = LINK_RE.search(block)
    if not link_match:
        return None

    thumb_match = THUMB_RE.search(block)
    title_match = TITLE_RE.search(block)
    price_match = PRICE_RE.search(block)
    beds_match = BEDS_RE.search(block)
    baths_match = BATHS_RE.search(block)
    desc_match = DESC_RE.search(block)

    url = BASE + link_match.group(1)
    # ID is embedded in the URL slug, e.g. /property/1477-chilton-road-...
    id_match = re.search(r'/property/(\d+)-', link_match.group(1))
    source_id = id_match.group(1) if id_match else link_match.group(1)

    price = None
    price_display = None
    if price_match:
        price_display = price_match.group(1).strip()
        digits = re.sub(r'[^\d]', '', price_display)
        price = int(digits) if digits else None

    address = None
    if title_match:
        address = re.sub(r'<br\s*/?>', ', ', title_match.group(1)).strip()
        address = re.sub(r'\s+', ' ', address)
        address = re.sub(r',\s*,+', ',', address)
        address = re.sub(r'^,\s*|,\s*$', '', address)

    summary = None
    if desc_match:
        summary = re.sub(r'\s+', ' ', desc_match.group(1)).strip()

    return {
        "source": SOURCE_NAME,
        "source_id": source_id,
        "address": address,
        "price": price,
        "price_display": price_display,
        "bedrooms": int(beds_match.group(1)) if beds_match else None,
        "bathrooms": int(baths_match.group(1)) if baths_match else None,
        "property_type": None,
        "summary": summary,
        "url": url,
        "thumbnail": thumb_match.group(1) if thumb_match else None,
    }

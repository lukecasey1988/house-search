"""
Reaston Brown (Thame) source - another strong local independent agent for
Long Crendon / Thame area villages.

Their site's listing cards use "cards cards--property" as the identifying CSS
class. If they redesign their website, check by viewing page source on
https://www.reastonbrown.co.uk/search/?instruction_type=Sale&showstc=on and
searching for "cards--property".
"""
import re
import time

import requests

SOURCE_NAME = "Reaston Brown"
BASE = "https://www.reastonbrown.co.uk"
SEARCH_URL_TEMPLATE = BASE + "/search/{page}.html?instruction_type=Sale&showstc=on"

CARD_RE = re.compile(
    r'<a href="(/property-details/[^"]+)" class="cards cards--property">(.*?)</a>', re.S
)
IMG_RE = re.compile(r'<img src="([^"]+)"')
H4_RE = re.compile(r'<h4>([^<]+)</h4>')
H5_RE = re.compile(r'<h5>(.*?)</h5>', re.S)


def fetch(min_price: int, max_price: int, min_bedrooms: int,
          headers: dict, delay: float, village_filter: list[str]) -> list[dict]:
    results = []
    page = 1
    max_pages = None

    while True:
        url = SEARCH_URL_TEMPLATE.format(page=page)
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    [Reaston Brown] ERROR fetching page {page}: {e}")
            break

        html = resp.text
        if max_pages is None:
            page_numbers = [int(n) for n in re.findall(r'/search/(\d+)\.html\?instruction_type=Sale', html)]
            max_pages = max(page_numbers) if page_numbers else 1

        cards = CARD_RE.findall(html)
        if not cards and page == 1:
            print("    [Reaston Brown] WARNING: no listing cards found - "
                  "site structure may have changed, scraper needs updating.")
            break

        for href, inner_html in cards:
            listing = _parse_card(href, inner_html)
            if listing:
                results.append(listing)

        if page >= max_pages:
            break
        page += 1
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


def _parse_card(href: str, inner_html: str) -> dict | None:
    h4_match = H4_RE.search(inner_html)
    h5_match = H5_RE.search(inner_html)
    img_match = IMG_RE.search(inner_html)

    if not h5_match:
        return None

    beds = None
    property_type = None
    status = None
    if h4_match:
        h4_text = h4_match.group(1).strip()
        beds_m = re.match(r'(\d+)\s*Bed\s*(.*?)\s*-\s*(.*)', h4_text, re.I)
        if beds_m:
            beds = int(beds_m.group(1))
            property_type = beds_m.group(2).strip()
            status = beds_m.group(3).strip()

    h5_text = h5_match.group(1)
    parts = re.split(r'<br\s*/?>', h5_text)
    address = re.sub(r'\s+', ' ', parts[0]).strip() if parts else None
    price_display = None
    price = None
    if len(parts) > 1:
        price_text = re.sub(r'&pound;', '£', parts[1])
        price_text = re.sub(r'<[^>]+>', '', price_text).strip()
        price_display = price_text
        digits = re.sub(r'[^\d]', '', price_text)
        price = int(digits) if digits else None

    if status and status.lower() not in ("for sale",):
        return None

    source_id = href.strip("/").split("/")[1] if "/" in href.strip("/") else href
    thumb = None
    if img_match:
        img_src = img_match.group(1)
        thumb = img_src if img_src.startswith("http") else (BASE + img_src)

    return {
        "source": SOURCE_NAME,
        "source_id": source_id,
        "address": address,
        "price": price,
        "price_display": price_display,
        "bedrooms": beds,
        "bathrooms": None,
        "property_type": property_type,
        "summary": None,
        "url": BASE + href,
        "thumbnail": thumb,
    }

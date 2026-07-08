"""
Fine & Country - North Oxfordshire (Bicester branch) source.

Covers Bicester and the surrounding villages, including Long Crendon,
Ludgershall, and Princes Risborough - useful for higher-end/country-house
stock that Fine & Country specialises in.

Their site runs on the "nurtur" property platform (identifiable by
"card-property" CSS classes and cdn.members.nurtur.tech image URLs). If they
redesign their website, check by viewing page source on
https://www.fineandcountry.co.uk/north-oxfordshire-estate-agents/sales/property-for-sale
and searching for "card-property--horizontal".
"""
import re
import time

import requests

SOURCE_NAME = "Fine & Country"
BASE = "https://www.fineandcountry.co.uk"
LIST_URL = BASE + "/north-oxfordshire-estate-agents/sales/property-for-sale"

BLOCK_RE = re.compile(r'<div class="card-property card-property--horizontal.*?(?=<div class="card-property card-property--horizontal|\Z)', re.S)
TITLE_LINK_RE = re.compile(r'<h4><a href="([^"]+)" class="property-title-link"[^>]*><span>([^<]+)</span>', re.S)
THUMB_RE = re.compile(r'background-image:\s*url\(([^)]+)\)')
PRICE_RE = re.compile(r'class="property-price">\s*<span class="text-gold"><span class="notranslate">£</span>([\d,]+)', re.S)
ROOMS_RE = re.compile(r'card__list-rooms">(.*?)</ul>', re.S)
ROOM_NUMBER_RE = re.compile(r'</svg>\s*(\d+)\s*</p>')
LABEL_RE = re.compile(r'card__label">\s*<span>([^<]*)</span>', re.S)


def fetch(min_price: int, max_price: int, min_bedrooms: int,
          headers: dict, delay: float, village_filter: list[str]) -> list[dict]:
    results = []
    page = 1
    max_pages = None

    while True:
        url = LIST_URL if page == 1 else f"{LIST_URL}&page={page}"
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    [Fine & Country] ERROR fetching page {page}: {e}")
            break

        html = resp.text
        if max_pages is None:
            page_numbers = [int(n) for n in re.findall(r'page=(\d+)', html)]
            max_pages = max(page_numbers) if page_numbers else 1

        blocks = BLOCK_RE.findall(html)
        if not blocks:
            if page == 1:
                print("    [Fine & Country] WARNING: no listing cards found - "
                      "site structure may have changed, scraper needs updating.")
            break

        for block in blocks:
            listing = _parse_block(block)
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


def _parse_block(block: str) -> dict | None:
    title_match = TITLE_LINK_RE.search(block)
    if not title_match:
        return None

    url, address = title_match.groups()
    address = address.strip()

    thumb_match = THUMB_RE.search(block)
    price_match = PRICE_RE.search(block)
    rooms_match = ROOMS_RE.search(block)
    label_match = LABEL_RE.search(block)

    price = None
    price_display = None
    if price_match:
        price = int(price_match.group(1).replace(",", ""))
        price_display = f"£{price_match.group(1)}"

    bedrooms = None
    bathrooms = None
    if rooms_match:
        numbers = ROOM_NUMBER_RE.findall(rooms_match.group(1))
        if len(numbers) >= 1:
            bedrooms = int(numbers[0])
        if len(numbers) >= 2:
            bathrooms = int(numbers[1])

    id_match = re.search(r'/(\d+)$', url.split("?")[0])
    source_id = id_match.group(1) if id_match else url

    summary = label_match.group(1).strip() if label_match and label_match.group(1).strip() else None

    return {
        "source": SOURCE_NAME,
        "source_id": source_id,
        "address": address,
        "price": price,
        "price_display": price_display,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "property_type": None,
        "summary": summary,
        "url": url,
        "thumbnail": thumb_match.group(1) if thumb_match else None,
    }

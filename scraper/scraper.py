"""
Daily house search scraper.

Fetches current listings from Rightmove and configured local agent websites,
compares against previously seen listings, and writes:
  - data/current_listings.json  (everything currently live, for the website)
  - data/seen_ids.json          (all IDs ever seen, so we can detect new ones)
  - data/new_today.json         (just today's new matches, for a highlight banner)

Designed to be run once a day via GitHub Actions (see .github/workflows/daily_scrape.yml).

Note on duplicates: the same physical property can appear more than once,
either cross-posted on multiple sites, or relisted more than once on the same
site (agents sometimes re-insert an ad for visibility, which gets a brand new
listing ID even though nothing about the property changed). See
is_likely_duplicate() for how these get matched and merged.
"""
import json
import re
import sys
import os
import time
from datetime import datetime, timezone
from io import BytesIO

import requests
from PIL import Image
import imagehash

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    LOCATIONS, MIN_PRICE, MAX_PRICE, MIN_BEDROOMS, TARGET_VILLAGES,
    LAND_KEYWORDS, REQUEST_HEADERS, REQUEST_DELAY_SECONDS, AGENT_SOURCES_ENABLED,
)
from sources import rightmove, hamnett_hayward, reaston_brown, fine_and_country

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Words stripped out when comparing addresses for de-duplication - village/county/
# postal-town names that appear in almost every address and so carry no
# information about which SPECIFIC property it is.
ADDRESS_STOPWORDS = {
    "buckinghamshire", "bucks", "aylesbury", "oxfordshire", "hp18", "hp19",
    "hp20", "hp21", "hp22", "hp23", "hp27", "lu6", "lu7",
}
for _village in TARGET_VILLAGES:
    ADDRESS_STOPWORDS.update(_village.lower().split())
ADDRESS_STOPWORDS.update({"monks", "weston", "turville"})

PHOTO_HASH_RE = re.compile(r'/property-photo/([a-f0-9]+)/')

# Perceptual-hash distance below which two thumbnails are treated as the same
# photo. 0 = pixel-identical; a small tolerance (a few bits) allows for the
# different resizing/compression each site applies to what is otherwise the
# same source image, without being so loose that two different but similar
# looking houses get matched.
IMAGE_HASH_MAX_DISTANCE = 6


def fetch_image_hash(url: str, headers: dict) -> "imagehash.ImageHash | None":
    """Download a listing's thumbnail and compute a perceptual hash. This is
    the most reliable duplicate signal we have: it catches the same property
    cross-posted on completely different websites (different domains, different
    address specificity, different marketing copy) as long as the same
    underlying photo was used - confirmed against a real example where a
    Rightmove listing and a Hamnett Hayward listing for the same new-build
    house had visually identical thumbnails (hamming distance 0) despite the
    Rightmove address being too generic to match on text alone."""
    if not url:
        return None
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return imagehash.phash(Image.open(BytesIO(resp.content)))
    except Exception as e:
        print(f"    [image hash] could not hash {url}: {e}")
        return None


def address_tokens(address: str) -> set:
    """Break an address into meaningful tokens for duplicate detection,
    stripping village/county names that don't help distinguish one property
    from another in the same village."""
    if not address:
        return set()
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', address.lower())
    return {t for t in cleaned.split() if t not in ADDRESS_STOPWORDS and len(t) > 1}


def photo_hash(url: str) -> str | None:
    """Extract Rightmove's per-listing photo hash from a thumbnail URL, as a
    cheap same-source signal that doesn't need a network request. Kept as a
    fallback for when the full image-download hash isn't available."""
    if not url:
        return None
    m = PHOTO_HASH_RE.search(url)
    return m.group(1) if m else None


def is_likely_duplicate(a: dict, b: dict) -> bool:
    """Duplicate check with three routes to a match, in order of confidence:

    1. Perceptual image hash match (any sources) - the two thumbnails are the
       same photo, near-certainly the same physical property. This is the
       main mechanism and works across different sites/domains.

    2. Same source + matching Rightmove photo-hash URL fragment - a fallback
       for same-site relists if the full image download failed for some reason.

    3. Different sources, same village, same exact price, AND sharing at
       least one specific address token (e.g. a street name) - a fallback
       for when no usable image comparison exists at all.

    Deliberately does NOT match on price + village + bed/bath alone: tested
    against real data and found two genuinely different properties in Monks
    Risborough with identical price, bedrooms, bathrooms, and property type -
    matching on specs alone would have wrongly merged two different real
    houses into one.
    """
    hash_a, hash_b = a.get("_image_hash"), b.get("_image_hash")
    if hash_a is not None and hash_b is not None:
        if (hash_a - hash_b) <= IMAGE_HASH_MAX_DISTANCE:
            return True
        # Both images successfully hashed and they don't match - these are
        # confirmed different photos, so don't fall through to weaker checks
        # even if other fields happen to coincide (this is exactly what
        # protects the Monks Risborough case).
        return False

    if a["source"] == b["source"]:
        url_hash_a, url_hash_b = photo_hash(a.get("thumbnail")), photo_hash(b.get("thumbnail"))
        if url_hash_a and url_hash_b:
            return url_hash_a == url_hash_b
        return False

    if a["village"] != b["village"] or a["price"] != b["price"]:
        return False
    tokens_a = address_tokens(a.get("address"))
    tokens_b = address_tokens(b.get("address"))
    if not tokens_a or not tokens_b:
        return False
    return bool(tokens_a & tokens_b)


def deduplicate(listings: list[dict]) -> list[dict]:
    """Merge likely-duplicate listings (same property cross-posted on
    multiple sites, or relisted more than once on the same site) into single
    entries with a combined "sources" list. See is_likely_duplicate() for
    the matching rules and their trade-offs."""
    merged = []

    for listing in listings:
        match = None
        for existing in merged:
            if is_likely_duplicate(existing, listing):
                match = existing
                break

        if match is None:
            listing["sources"] = [{"name": listing["source"], "url": listing["url"]}]
            merged.append(listing)
        else:
            match["sources"].append({"name": listing["source"], "url": listing["url"]})
            if listing.get("address") and len(listing["address"]) > len(match.get("address") or ""):
                match["address"] = listing["address"]
            if listing.get("summary") and not match.get("summary"):
                match["summary"] = listing["summary"]
            if listing.get("thumbnail") and not match.get("thumbnail"):
                match["thumbnail"] = listing["thumbnail"]
            if listing.get("bedrooms") and not match.get("bedrooms"):
                match["bedrooms"] = listing["bedrooms"]
            if listing.get("bathrooms") and not match.get("bathrooms"):
                match["bathrooms"] = listing["bathrooms"]

    return merged


def has_land_mention(listing: dict) -> bool:
    text = (listing.get("summary") or "") + " " + (listing.get("address") or "")
    text = text.lower()
    return any(kw in text for kw in LAND_KEYWORDS)


def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: str, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def fetch_all_raw_listings() -> list[dict]:
    """Fetch from every configured source, tagging each with its village/source."""
    all_listings = []

    for village, slug in LOCATIONS.items():
        print(f"Fetching {village} from Rightmove ({slug})...")
        try:
            listings = rightmove.fetch(
                slug, MIN_PRICE, MAX_PRICE, MIN_BEDROOMS,
                REQUEST_HEADERS, REQUEST_DELAY_SECONDS,
            )
        except Exception as e:
            print(f"  ERROR: Rightmove fetch failed for {village}: {e}")
            listings = []
        print(f"  -> {len(listings)} matches")
        for l in listings:
            l["village"] = village
        all_listings.extend(listings)
        time.sleep(REQUEST_DELAY_SECONDS)

    agent_modules = {
        "hamnett_hayward": hamnett_hayward,
        "reaston_brown": reaston_brown,
        "fine_and_country": fine_and_country,
    }
    for key, module in agent_modules.items():
        if not AGENT_SOURCES_ENABLED.get(key, False):
            continue
        print(f"Fetching {module.SOURCE_NAME}...")
        try:
            listings = module.fetch(
                MIN_PRICE, MAX_PRICE, MIN_BEDROOMS,
                REQUEST_HEADERS, REQUEST_DELAY_SECONDS, TARGET_VILLAGES,
            )
        except Exception as e:
            print(f"  ERROR: {module.SOURCE_NAME} fetch failed: {e}")
            listings = []
        print(f"  -> {len(listings)} matches")
        for l in listings:
            address_lower = (l.get("address") or "").lower()
            villages_by_specificity = sorted(TARGET_VILLAGES, key=len, reverse=True)
            matched_village = next(
                (v for v in villages_by_specificity if v.lower() in address_lower),
                "Other (see address)"
            )
            l["village"] = matched_village
        all_listings.extend(listings)
        time.sleep(REQUEST_DELAY_SECONDS)

    return all_listings


def main():
    seen_path = os.path.join(DATA_DIR, "seen_ids.json")
    current_path = os.path.join(DATA_DIR, "current_listings.json")
    new_today_path = os.path.join(DATA_DIR, "new_today.json")

    seen_ids = load_json(seen_path, {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    raw_listings = fetch_all_raw_listings()

    print(f"\nHashing thumbnails for duplicate detection ({len(raw_listings)} images)...")
    for listing in raw_listings:
        listing["_image_hash"] = fetch_image_hash(listing.get("thumbnail"), REQUEST_HEADERS)

    deduped_listings = deduplicate(raw_listings)
    print(f"\nDeduplicated {len(raw_listings)} raw listings down to {len(deduped_listings)} "
          f"({len(raw_listings) - len(deduped_listings)} merged as duplicates).")

    all_current = []
    new_today = []

    for listing in deduped_listings:
        primary_source = listing["sources"][0]
        listing["id"] = f"{primary_source['name']}::{listing['source_id']}"
        listing["has_land_mention"] = has_land_mention(listing)

        if listing["id"] not in seen_ids:
            seen_ids[listing["id"]] = today
            listing["first_seen"] = today
            new_today.append(listing)
        else:
            listing["first_seen"] = seen_ids[listing["id"]]

        all_current.append(listing)

    for listing in all_current:
        listing.pop("_image_hash", None)

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

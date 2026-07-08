"""
Daily house search scraper.

Fetches current listings from Rightmove and configured local agent websites,
compares against previously seen listings, and writes:
  - data/current_listings.json  (everything currently live, for the website)
  - data/seen_ids.json          (all IDs ever seen, so we can detect new ones)
  - data/new_today.json         (just today's new matches, for a highlight banner)

Designed to be run once a day via GitHub Actions (see .github/workflows/daily_scrape.yml).

Note on duplicates: the same physical property can appear from more than one
source (e.g. an agent's own site AND Rightmove, since most agents cross-post).
This scraper does not attempt to de-duplicate across sources, since matching
listings reliably by address text alone is unreliable. Each card shows its
source, so you can tell at a glance.
"""
import json
import sys
import os
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    LOCATIONS, MIN_PRICE, MAX_PRICE, MIN_BEDROOMS, TARGET_VILLAGES,
    LAND_KEYWORDS, REQUEST_HEADERS, REQUEST_DELAY_SECONDS, AGENT_SOURCES_ENABLED,
)
from sources import rightmove, hamnett_hayward, reaston_brown, fine_and_country

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


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

    # --- Rightmove: one request per village, using its own location filtering ---
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

    # --- Local agent sites: fetch once, filter to target villages in Python ---
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
            # Best-guess village assignment from the address text, for grouping
            # on the site. Longer/more specific names are checked first so a
            # postal town like "Aylesbury" doesn't override the actual village
            # (e.g. "Chilton Road, Long Crendon, Aylesbury" should match
            # Long Crendon, not Aylesbury).
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

    seen_ids = load_json(seen_path, {})  # {"source::id": first_seen_date}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    raw_listings = fetch_all_raw_listings()

    all_current = []
    new_today = []

    for listing in raw_listings:
        listing["id"] = f"{listing['source']}::{listing['source_id']}"
        listing["has_land_mention"] = has_land_mention(listing)

        if listing["id"] not in seen_ids:
            seen_ids[listing["id"]] = today
            listing["first_seen"] = today
            new_today.append(listing)
        else:
            listing["first_seen"] = seen_ids[listing["id"]]

        all_current.append(listing)

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

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
import re
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

# Words stripped out when comparing addresses for de-duplication - village/county/
# postal-town names that appear in almost every address and so carry no
# information about which SPECIFIC property it is.
ADDRESS_STOPWORDS = {
    "buckinghamshire", "bucks", "aylesbury", "oxfordshire", "hp18", "hp19",
    "hp20", "hp21", "hp22", "hp23", "hp27", "lu6", "lu7",
}
for _village in TARGET_VILLAGES:
    ADDRESS_STOPWORDS.update(_village.lower().split())
# Extra place-name fragments not captured by TARGET_VILLAGES but still too
# generic to safely distinguish one property from another (hamlets/areas
# within a village, not street names). Add to this list if a false merge
# turns up involving another sub-area name.
ADDRESS_STOPWORDS.update({"monks", "weston", "turville"})


def address_tokens(address: str) -> set:
    """Break an address into meaningful tokens for duplicate detection,
    stripping village/county names that don't help distinguish one property
    from another in the same village."""
    if not address:
        return set()
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', address.lower())
    return {t for t in cleaned.split() if t not in ADDRESS_STOPWORDS and len(t) > 1}


def is_likely_duplicate(a: dict, b: dict) -> bool:
    """Conservative duplicate check: only merge if both listings are in the
    same village, have the EXACT same price, AND share at least one specific
    address token (e.g. a street name). Price + village alone is not enough -
    tested against real data and found two genuinely different properties in
    Monks Risborough both listed at the same price with generic addresses, so
    matching on price alone would have wrongly merged distinct houses."""
    if a["village"] != b["village"]:
        return False
    if a["price"] != b["price"]:
        return False
    tokens_a = address_tokens(a.get("address"))
    tokens_b = address_tokens(b.get("address"))
    if not tokens_a or not tokens_b:
        # One or both addresses are too generic (e.g. just "Long Crendon,
        # Buckinghamshire") to safely confirm a match - leave them separate
        # rather than risk merging two different properties.
        return False
    return bool(tokens_a & tokens_b)


def deduplicate(listings: list[dict]) -> list[dict]:
    """Merge likely-duplicate listings (same property cross-posted on
    multiple sites) into single entries with a combined "sources" list.
    See is_likely_duplicate() for the (deliberately conservative) matching
    rule - this will miss some true duplicates where the address is too
    vague to confirm a match, but that's a safer trade-off than incorrectly
    hiding two different real properties."""
    # First pass: collapse exact (source, source_id) repeats - can happen if
    # two overlapping village searches on the same site return the same
    # underlying property (e.g. a wide-radius search overlapping a narrower one).
    seen_exact = {}
    for listing in listings:
        key = (listing["source"], listing["source_id"])
        if key not in seen_exact:
            seen_exact[key] = listing
    listings = list(seen_exact.values())

    # Second pass: fuzzy cross-source matching for genuine cross-posted duplicates.
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
            # Prefer the more specific/longer address and any summary text found
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
    deduped_listings = deduplicate(raw_listings)
    print(f"\nDeduplicated {len(raw_listings)} raw listings down to {len(deduped_listings)} "
          f"({len(raw_listings) - len(deduped_listings)} merged as cross-posted duplicates).")

    all_current = []
    new_today = []

    for listing in deduped_listings:
        # ID is based on the first source found for this property. Since
        # deduplication only merges listings we're confident are the same
        # property, this stays stable day to day as long as that first
        # source keeps listing it.
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

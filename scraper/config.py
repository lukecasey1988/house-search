"""
Search configuration for the house search tracker.
Edit this file to change locations, price range, or bedroom requirements.
"""

LOCATIONS = {
    "Aylesbury": "Aylesbury",
    "Long Crendon": "Long-Crendon",
    "Ludgershall": "Ludgershall-16391",
    "Stewkley": "Stewkley",
    "Edlesborough": "Edlesborough",
    "Princes Risborough": "Princes-Risborough",
    "Whitchurch": "Whitchurch-26696",
    "Oving": "Oving",
    "Cublington": "Cublington",
    "Aston Abbotts": "Aston-Abbotts",
    "Quainton": "Quainton",
}
# ^ These are the villages/towns in or near Aylesbury Grammar School's formal
# catchment area. Whitchurch and its immediate neighbours (Oving, Cublington,
# Aston Abbotts, Quainton) sit right on/near the catchment boundary - status
# is genuinely uncertain from the published map, so they're included as
# "worth watching" rather than confirmed in-catchment. Verify any specific
# address via Buckinghamshire Council's postcode checker before relying on it:
# https://services.buckscc.gov.uk/school-admissions
# Bucks Council reviews the exact catchment boundary each admissions cycle, so it's
# worth double-checking this list against the current year's published catchment
# before relying on it: https://www.buckinghamshire.gov.uk (search "secondary transfer")

MIN_PRICE = 1400000
MAX_PRICE = 2000000
MIN_BEDROOMS = 5

# Used to filter listings from agent websites that don't support server-side
# location filtering (unlike Rightmove, where each village has its own URL).
# Keep this in sync with LOCATIONS above.
TARGET_VILLAGES = [
    "Aylesbury", "Long Crendon", "Ludgershall", "Stewkley",
    "Edlesborough", "Princes Risborough", "Risborough", "Weston Turville",
    "Whitchurch", "Oving", "Cublington", "Aston Abbotts", "Quainton",
]

# Keywords checked against each listing's summary/description text.
# Listings mentioning any of these get a "Land" flag on the site (informational only,
# does not exclude other listings - most land isn't mentioned until you open the listing).
LAND_KEYWORDS = [
    "acre", "acres", "paddock", "grounds", "smallholding", "equestrian",
    "stables", "meadow", "plot of", "land extending",
]

# Local independent agents to scrape directly, in addition to Rightmove.
# Set to False to skip a source (e.g. if it starts erroring and you want the
# rest of the daily run to keep working while you fix it).
# Local independent agents to scrape directly, in addition to Rightmove.
# Set to False to skip a source (e.g. if it starts erroring and you want the
# rest of the daily run to keep working while you fix it).
AGENT_SOURCES_ENABLED = {
    "hamnett_hayward": True,
    "reaston_brown": True,
    "fine_and_country": True,
}

# Manual duplicate overrides: for the rare case where you (or your wife) spot
# a duplicate on the live site that the automatic matching couldn't confirm
# (e.g. same property, but listed with a generic address on both sites AND
# different photos used by each site - so neither the address-matching nor
# the image-matching can prove it safely on their own).
#
# Add an entry as a list of {"source": ..., "source_id": ...} pairs to force
# those specific listings to always merge. Find the source_id by opening the
# listing's URL - for Rightmove it's the number in the URL
# (rightmove.co.uk/properties/174294314 -> "174294314"); for other sites it's
# usually the number in their URL similarly.
MANUAL_DUPLICATE_GROUPS = [
    [
        {"source": "Rightmove", "source_id": "174294314"},
        {"source": "Reaston Brown", "source_id": "4724696"},
    ],  # £1,950,000 Long Crendon - confirmed same property 22 Jul 2026, different
        # photos used by each site so automatic matching couldn't confirm it
]

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

REQUEST_DELAY_SECONDS = 3  # politeness delay between requests to avoid hammering the site

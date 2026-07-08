"""
Search configuration for the house search tracker.
Edit this file to change locations, price range, or bedroom requirements.
"""

# Rightmove location slugs. To find a new one: go to rightmove.co.uk, search the
# village/town name, and copy the slug from the URL
# (e.g. rightmove.co.uk/property-for-sale/Long-Crendon.html -> "Long-Crendon")
LOCATIONS = {
    "Aylesbury": "Aylesbury",
    "Long Crendon": "Long-Crendon",
    "Ludgershall": "Ludgershall-16391",
    "Stewkley": "Stewkley",
    "Edlesborough": "Edlesborough",
    "Princes Risborough": "Princes-Risborough",
}
# ^ These are the villages/towns in Aylesbury Grammar School's formal catchment area.
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
]

# Local independent agents to scrape directly, in addition to Rightmove.
# Set to False to skip a source (e.g. if it starts erroring and you want the
# rest of the daily run to keep working while you fix it).
AGENT_SOURCES_ENABLED = {
    "hamnett_hayward": True,
    "reaston_brown": True,
    "fine_and_country": True,
}

# Keywords checked against each listing's summary/description text.
# Listings mentioning any of these get a "Land" flag on the site (informational only,
# does not exclude other listings - most land isn't mentioned until you open the listing).
LAND_KEYWORDS = [
    "acre", "acres", "paddock", "grounds", "smallholding", "equestrian",
    "stables", "meadow", "plot of", "land extending",
]

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

REQUEST_DELAY_SECONDS = 3  # politeness delay between requests to avoid hammering the site

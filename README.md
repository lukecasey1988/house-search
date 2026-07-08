# House Search Tracker — Long Crendon / Ludgershall / Aylesbury catchment

A daily-refreshed website tracking new listings in your target villages, built
from a scraper that reads Rightmove's own listing data and a static site that
displays it. No third-party service, no subscription, no ongoing scraping cost.

## What this actually is (read this first)

- **`scraper/scraper.py`** fetches listings for each village directly from Rightmove
  and filters by price/bedrooms, using their normal public search pages.
- **`.github/workflows/daily_scrape.yml`** runs that script automatically once a
  day, using GitHub's free Actions minutes, and commits the results back to the repo.
- **`docs/index.html`** is a static website that reads the scraped data and displays
  it. GitHub Pages serves this folder as a live website automatically.
- Because it's all static + scheduled, **there is no server to pay for or maintain**
  — just the GitHub repo itself, which is free for this use case.

**Important caveat:** Rightmove's terms of service don't permit automated scraping
of their site. This is a personal, low-frequency (once/day), non-commercial tool,
which is a very different risk profile to commercial scraping — but it's still
against their terms, and they could block the request pattern at any time (in
which case you'd see errors in the GitHub Actions log and the scraper would need
updating, or you'd fall back to Rightmove's own email alerts). Treat this as a
personal convenience tool, not something to rely on exclusively — keep your
Rightmove saved-search email alerts running in parallel as a backup.

## One-time setup (about 15 minutes)

1. **Create a GitHub account** if you don't have one already (free): github.com

2. **Create a new repository**
   - Go to github.com/new
   - Name it something like `house-search` — you can make it Private if you'd
     rather your wife be the only other person with access (add her as a
     collaborator under repo Settings → Collaborators)
   - Don't initialise with a README (we already have one)

3. **Upload these files to the repo**
   - Easiest way: on the new repo's page, click "uploading an existing file" and
     drag in the whole folder structure, OR use git from a terminal:
     ```
     git init
     git add .
     git commit -m "Initial setup"
     git branch -M main
     git remote add origin https://github.com/YOUR-USERNAME/house-search.git
     git push -u origin main
     ```

4. **Enable GitHub Pages**
   - In the repo, go to Settings → Pages
   - Under "Build and deployment", set Source to "Deploy from a branch"
   - Set Branch to `main` and folder to `/docs`
   - Save. GitHub will give you a URL like
     `https://YOUR-USERNAME.github.io/house-search/` — this is your live site,
     shareable with your wife.

5. **Enable and run the scraper**
   - Go to the Actions tab in the repo — GitHub may ask you to confirm you want
     to enable Actions for this repo, click yes
   - Click on "Daily house search scrape" in the left sidebar, then "Run workflow"
     to trigger it manually the first time (don't wait for tomorrow's schedule)
   - After ~1 minute, refresh — you should see a green checkmark
   - Refresh your Pages site — listings should now appear

From this point on, it runs automatically every day at 07:00 UTC and the site
updates itself. You don't need to do anything else unless you want to change
the search criteria.

## Changing what it searches for

Edit `scraper/config.py`:

- **`LOCATIONS`** — add or remove villages. To find a new village's Rightmove
  slug: search for it on rightmove.co.uk and copy the last part of the URL
  (e.g. `rightmove.co.uk/property-for-sale/Long-Crendon.html` → `Long-Crendon`)
- **`MIN_PRICE` / `MAX_PRICE`** — your budget range
- **`MIN_BEDROOMS`** — minimum bedrooms
- **`LAND_KEYWORDS`** — words that trigger the "land/acreage" badge on the site
  (this is informational only — it doesn't filter listings out, since most
  land isn't mentioned in the short summary text)

After editing, commit and push the change — the next scheduled run (or a manual
"Run workflow" click) will pick it up.

## When this will need attention

- **If Rightmove changes their website's structure**, the scraper's method of
  reading their embedded data (`__NEXT_DATA__`) may break. You'd see this as
  errors in the Actions tab log, or the site simply stops getting new listings.
  This is the main ongoing maintenance cost of the "custom scraper" approach —
  worth checking every month or two, or whenever a search that should clearly
  show new houses shows nothing new.
- **If you want to add other portals** (Zoopla, OnTheMarket) or specific agent
  websites (Savills, Hamnett Hayward, etc.), each would need its own scraping
  logic written and added to `scraper.py`, since every site's HTML/JSON
  structure is different. Ask me and I can build that out for a specific site
  when you're ready.

## Files

```
house-search-tracker/
├── scraper/
│   ├── scraper.py       - the scraping logic
│   └── config.py        - your search criteria (edit this)
├── data/                 - scraper's working data (seen listing IDs etc.)
├── docs/                 - the published website (GitHub Pages serves this)
│   ├── index.html
│   └── data/             - the JSON the website reads (auto-updated daily)
├── .github/workflows/
│   └── daily_scrape.yml - the automation that runs it all
└── requirements.txt
```

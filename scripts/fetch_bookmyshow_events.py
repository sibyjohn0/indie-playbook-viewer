#!/usr/bin/env python3
"""
Fetches upcoming music events from BookMyShow (in.bookmyshow.com) by city.
Uses Playwright (Cloudflare-protected site) and extracts from the DOM.
Dates come from eventsSchema in __INITIAL_STATE__ when available (SSR pages).
Writes to data/bookmyshow-events.json
Run daily: python3 scripts/fetch_bookmyshow_events.py  (from repo root)
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Run: pip3 install playwright && python -m playwright install chromium")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
OUTPUT = REPO_ROOT / "data" / "bookmyshow-events.json"

EXPLORE_BASE = "https://in.bookmyshow.com/explore/events-{slug}?categories=music-shows"

CITIES = [
    {"name": "Mumbai",     "slug": "mumbai"},
    {"name": "Delhi",      "slug": "delhi"},
    {"name": "Bengaluru",  "slug": "bengaluru"},
    {"name": "Hyderabad",  "slug": "hyderabad"},
    {"name": "Chennai",    "slug": "chennai"},
    {"name": "Kolkata",    "slug": "kolkata"},
    {"name": "Pune",       "slug": "pune"},
    {"name": "Goa",        "slug": "goa"},
    {"name": "Jaipur",     "slug": "jaipur"},
    {"name": "Kochi",      "slug": "kochi"},
    {"name": "Ahmedabad",  "slug": "ahmedabad"},
    {"name": "Chandigarh", "slug": "chandigarh"},
]

# Extracts from DOM (always works) + eventsSchema for dates (SSR only)
EXTRACT_JS = """
() => {
  // DOM extraction: works for all cities
  const domEvents = [];
  document.querySelectorAll('a[href*="/events/"]').forEach(a => {
    const url = a.href;
    if (!url.match(/\/events\/.+\/ET\d+/)) return;
    const lines = (a.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
    if (lines.length < 2) return;
    domEvents.push({
      url,
      title: lines[0] || '',
      venue: lines[1] || '',
      category: lines[2] || '',
      price: lines[3] || '',
    });
  });

  // eventsSchema: has startDate, available via SSR for default city
  const queries = window.__INITIAL_STATE__?.exploreApi?.queries || {};
  const qKey = Object.keys(queries).find(k => k.startsWith('getDiscoveryData-'));
  const eventsSchema = queries[qKey]?.data?.meta?.ldSchema?.eventsSchema || [];
  const dateMap = {};
  for (const ev of eventsSchema) {
    if (ev.url && ev.startDate) dateMap[ev.url] = ev.startDate;
  }

  return { domEvents, dateMap };
}
"""


def parse_date(iso_date):
    if not iso_date:
        return None
    try:
        dt = datetime.strptime(iso_date[:10], "%Y-%m-%d")
        return dt.strftime("%-d %B %Y")
    except Exception:
        return iso_date


def fetch_city(page, city):
    city_name = city["name"]
    url = EXPLORE_BASE.format(slug=city["slug"])

    try:
        page.goto(url, wait_until="load", timeout=35000)
    except Exception as e:
        print(f"  [{city_name}] Load error: {e}", flush=True)
        return []

    try:
        page.wait_for_selector('a[href*="/events/"]', timeout=15000)
    except Exception as e:
        print(f"  [{city_name}] No event links: {e}", flush=True)
        return []

    try:
        result = page.evaluate(EXTRACT_JS)
    except Exception as e:
        print(f"  [{city_name}] JS error: {e}", flush=True)
        return []

    dom_events = result.get("domEvents", [])
    date_map = result.get("dateMap", {})

    events = []
    seen = set()
    for ev in dom_events:
        ev_url = ev.get("url", "")
        if not ev_url or ev_url in seen:
            continue
        seen.add(ev_url)

        price = ev.get("price", "").strip()
        if not price or price.lower() in ("concerts", "club gigs", "open mic", "festivals"):
            price = "See site"

        events.append({
            "title": ev.get("title", ""),
            "venue": ev.get("venue") or None,
            "date": parse_date(date_map.get(ev_url)),
            "time": None,
            "price": price,
            "url": ev_url,
            "city": city_name,
            "source": "bookmyshow.com",
        })

    print(f"  {city_name}: {len(events)} music events", flush=True)
    return events


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Fetching BookMyShow music events...", flush=True)

    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for city in CITIES:
            # Fresh context per city to avoid region cookie bleedover
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="en-IN",
            )
            page = context.new_page()
            results[city["slug"]] = fetch_city(page, city)
            context.close()
            time.sleep(1.5)

        browser.close()

    total = sum(len(v) for v in results.values())
    active = len([c for c in results.values() if c])
    print(f"\nTotal: {total} music events across {active} cities", flush=True)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "BookMyShow",
        "total_events": total,
        "cities": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()

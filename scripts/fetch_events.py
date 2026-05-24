#!/usr/bin/env python3
"""
Fetches upcoming live music events from District.in by city.
Writes output to data/live-events.json
Run daily via CCR: python3 scripts/fetch_events.py  (from repo root)
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright not installed. Run: pip3 install playwright && python3 -m playwright install chromium")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
OUTPUT = REPO_ROOT / "data" / "live-events.json"

CITIES = [
    ("Mumbai",     "mumbai"),
    ("Delhi",      "delhi"),
    ("Bengaluru",  "bengaluru"),
    ("Hyderabad",  "hyderabad"),
    ("Chennai",    "chennai"),
    ("Kolkata",    "kolkata"),
    ("Pune",       "pune"),
    ("Goa",        "goa"),
    ("Jaipur",     "jaipur"),
    ("Kochi",      "kochi"),
    ("Ahmedabad",  "ahmedabad"),
    ("Chandigarh", "chandigarh"),
]

CATEGORY_SLUGS = [
    "concerts--music-events-in-{city}",
    "live-music-events-in-{city}",
    "dj-events-in-{city}",
]

EXTRACT_JS = """
() => {
    const events = [];
    const seen = new Set();

    // Try __NEXT_DATA__ server-side props first
    try {
        const nd = window.__NEXT_DATA__?.props?.pageProps;
        const arr = nd?.events || nd?.data?.events || nd?.listings || nd?.items || [];
        arr.forEach(e => {
            const t = e.name || e.title || '';
            if (!t || seen.has(t)) return;
            seen.add(t);
            events.push({
                title: t,
                venue: e.venue?.name || e.location?.name || e.venue_name || null,
                date: e.start_time || e.date || e.start_date || null,
                price: e.min_price ? 'Rs. ' + e.min_price : (e.price_display || null),
                url: e.url || (e.slug ? 'https://www.district.in/e/' + e.slug : null),
            });
        });
    } catch(e) {}

    // Fallback: scrape DOM cards
    if (events.length === 0) {
        const links = document.querySelectorAll('a[href*="/e/"]');
        links.forEach(a => {
            const title = a.querySelector('h1,h2,h3,h4,[class*="title"],[class*="name"]')?.innerText?.trim()
                        || a.innerText?.split('\\n')[0]?.trim();
            if (!title || title.length < 3 || seen.has(title)) return;
            seen.add(title);
            const venue = a.querySelector('[class*="venue"],[class*="location"],[class*="place"]')?.innerText?.trim();
            const date  = a.querySelector('[class*="date"],[class*="time"],time')?.innerText?.trim();
            const price = a.querySelector('[class*="price"],[class*="ticket"],[class*="cost"]')?.innerText?.trim();
            events.push({ title, venue: venue || null, date: date || null, price: price || null, url: a.href });
        });
    }

    return events;
}
"""


def fetch_city(page, city_name, city_slug):
    events = []
    seen = set()

    for tmpl in CATEGORY_SLUGS:
        url = "https://www.district.in/" + tmpl.format(city=city_slug)
        try:
            page.goto(url, wait_until="networkidle", timeout=25000)
            time.sleep(2)
            raw = page.evaluate(EXTRACT_JS)
            for ev in raw:
                t = ev.get("title", "")
                if t and t not in seen:
                    seen.add(t)
                    ev["city"] = city_name
                    ev["source"] = "district"
                    events.append(ev)
        except Exception as e:
            print(f"  [{city_name}] {url}: {e}", flush=True)

    print(f"  {city_name}: {len(events)} events", flush=True)
    return events


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Fetching District.in events...", flush=True)
    results = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        for city_name, city_slug in CITIES:
            results[city_slug] = fetch_city(page, city_name, city_slug)

        browser.close()

    total = sum(len(v) for v in results.values())
    print(f"Total: {total} events across {len(results)} cities", flush=True)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "district.in (Zomato)",
        "cities": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}", flush=True)
    return total


if __name__ == "__main__":
    main()

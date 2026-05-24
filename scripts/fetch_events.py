#!/usr/bin/env python3
"""
Fetches upcoming live music events from District.in (Zomato) by city.
Uses Playwright with city-specific location cookies.
Writes to data/live-events.json
Run daily: python3 scripts/fetch_events.py  (from repo root)
"""

import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Run: pip3 install playwright && python3 -m playwright install chromium")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
OUTPUT = REPO_ROOT / "data" / "live-events.json"

# District.in city configs — cityId matches Zomato's internal IDs
CITIES = [
    {"name": "Mumbai",     "slug": "mumbai",     "cityId": 3,  "cityName": "Mumbai",     "lat": 19.0760, "lon": 72.8777, "title": "Mumbai", "subtitle": "Maharashtra"},
    {"name": "Delhi",      "slug": "delhi",      "cityId": 1,  "cityName": "Delhi NCR",  "lat": 28.6139, "lon": 77.2090, "title": "Delhi",  "subtitle": "Delhi"},
    {"name": "Bengaluru",  "slug": "bengaluru",  "cityId": 4,  "cityName": "Bengaluru",  "lat": 12.9716, "lon": 77.5946, "title": "Bengaluru", "subtitle": "Karnataka"},
    {"name": "Hyderabad",  "slug": "hyderabad",  "cityId": 5,  "cityName": "Hyderabad",  "lat": 17.3850, "lon": 78.4867, "title": "Hyderabad", "subtitle": "Telangana"},
    {"name": "Chennai",    "slug": "chennai",    "cityId": 6,  "cityName": "Chennai",    "lat": 13.0827, "lon": 80.2707, "title": "Chennai",  "subtitle": "Tamil Nadu"},
    {"name": "Kolkata",    "slug": "kolkata",    "cityId": 7,  "cityName": "Kolkata",    "lat": 22.5726, "lon": 88.3639, "title": "Kolkata",  "subtitle": "West Bengal"},
    {"name": "Pune",       "slug": "pune",       "cityId": 9,  "cityName": "Pune",       "lat": 18.5204, "lon": 73.8567, "title": "Pune",     "subtitle": "Maharashtra"},
    {"name": "Goa",        "slug": "goa",        "cityId": 20, "cityName": "Goa",        "lat": 15.2993, "lon": 74.1240, "title": "Goa",      "subtitle": "Goa"},
    {"name": "Jaipur",     "slug": "jaipur",     "cityId": 10, "cityName": "Jaipur",     "lat": 26.9124, "lon": 75.7873, "title": "Jaipur",   "subtitle": "Rajasthan"},
    {"name": "Kochi",      "slug": "kochi",      "cityId": 12, "cityName": "Kochi",      "lat": 9.9312,  "lon": 76.2673, "title": "Kochi",    "subtitle": "Kerala"},
    {"name": "Ahmedabad",  "slug": "ahmedabad",  "cityId": 11, "cityName": "Ahmedabad",  "lat": 23.0225, "lon": 72.5714, "title": "Ahmedabad","subtitle": "Gujarat"},
    {"name": "Chandigarh", "slug": "chandigarh", "cityId": 16, "cityName": "Chandigarh", "lat": 30.7333, "lon": 76.7794, "title": "Chandigarh","subtitle": "Chandigarh"},
]

MUSIC_KEYWORDS = [
    "music", "concert", "live", "gig", "band", "dj", "festival", "jam",
    "acoustic", "jazz", "blues", "rock", "indie", "hip hop", "electronic",
    "nh7", "sunburn", "bollywood", "classical", "folk", "fusion", "open mic",
    "singer", "artist", "performance", "show", "tour", "beats",
]

def make_location_cookie(city):
    """Build the location cookie value District.in uses for city selection."""
    payload = {
        "fullname": f"{city['title']}, {city['subtitle']}, India",
        "lat": city["lat"],
        "long": city["lon"],
        "subtitle": city["subtitle"],
        "title": city["title"],
        "id": city["cityId"],
        "cityId": city["cityId"],
        "cityName": city["cityName"],
        "pCityId": str(city["cityId"] + 50),
    }
    return urllib.parse.quote(json.dumps(payload))


def is_music_event(title):
    if not title:
        return False
    t = title.lower()
    return any(kw in t for kw in MUSIC_KEYWORDS)


EXTRACT_JS = """
() => {
    const events = [];
    const seen = new Set();

    document.querySelectorAll('a[href*="/events/"]').forEach(a => {
        const href = a.href || '';
        if (!href.includes('-buy-tickets') && !href.includes('/events/')) return;
        if (href === 'https://www.district.in/events/') return;

        // Try multiple title selectors
        const titleEl = a.querySelector('h1,h2,h3,h4,[class*="title"],[class*="name"],[class*="heading"]');
        const rawText = a.innerText?.trim() || '';
        const lines = rawText.split('\\n').map(l => l.trim()).filter(Boolean);

        // Title is usually the longest line or the one after a date line
        let title = titleEl?.innerText?.trim();
        if (!title && lines.length > 0) {
            // Skip date-like first lines (e.g. "Sat, 24 May, 7:00 PM")
            title = lines.find(l => l.length > 10 && !/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Every)/.test(l)) || lines[0];
        }

        if (!title || title.length < 3 || seen.has(title)) return;
        seen.add(title);

        // Extract other fields
        const venue = a.querySelector('[class*="venue"],[class*="location"],[class*="place"]')?.innerText?.trim()
                    || lines.find(l => l.includes('|') || (l.length > 5 && /[A-Z]/.test(l[0]) && !/^[₹\\d]/.test(l) && l !== title));
        const dateEl = lines.find(l => /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Every)/.test(l));
        const priceEl = a.querySelector('[class*="price"],[class*="ticket"]')?.innerText?.trim()
                      || lines.find(l => /[₹Rs\\d]/.test(l) && l.length < 30);

        events.push({
            title,
            venue: venue || null,
            date: dateEl || null,
            price: priceEl || null,
            url: href,
        });
    });

    return events;
}
"""


def fetch_city(ctx, city):
    city_slug = city["slug"]
    city_name = city["name"]

    # Set city via location cookie
    cookie_val = make_location_cookie(city)
    ctx.add_cookies([{
        "name": "location",
        "value": cookie_val,
        "domain": "www.district.in",
        "path": "/",
    }])

    page = ctx.new_page()
    events = []
    seen = set()

    try:
        page.goto("https://www.district.in/events/", wait_until="domcontentloaded", timeout=30000)
        # Wait for event cards to render
        try:
            page.wait_for_selector('a[href*="-buy-tickets"]', timeout=10000)
        except:
            time.sleep(5)

        raw = page.evaluate(EXTRACT_JS)
        for ev in raw:
            t = ev.get("title", "")
            if t and t not in seen and is_music_event(t):
                seen.add(t)
                ev["city"] = city_name
                ev["source"] = "district.in"
                events.append(ev)

    except Exception as e:
        print(f"  [{city_name}] Error: {e}", flush=True)
    finally:
        page.close()

    print(f"  {city_name}: {len(events)} music events", flush=True)
    return events


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Fetching District.in live music events...", flush=True)
    results = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        for city in CITIES:
            # Fresh context per city so cookies don't leak between cities
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
                locale="en-IN",
            )
            results[city["slug"]] = fetch_city(ctx, city)
            ctx.close()

        browser.close()

    total = sum(len(v) for v in results.values())
    print(f"\nTotal: {total} music events across {len([c for c in results.values() if c])} cities", flush=True)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "District.in (Zomato)",
        "total_events": total,
        "cities": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()

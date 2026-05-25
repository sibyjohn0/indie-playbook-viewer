#!/usr/bin/env python3
"""
Fetches upcoming live music events from SkillBox (skillboxes.com) by city.
Uses their internal JSON API directly — no browser required.
Writes to data/skillbox-events.json
Run daily: python3 scripts/fetch_skillbox_events.py  (from repo root)
"""

import json
import sys
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Run: pip3 install requests")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
OUTPUT = REPO_ROOT / "data" / "skillbox-events.json"

API_URL = "https://www.skillboxes.com/servers/v3/api/event-new/get-event-new"
EVENT_BASE_URL = "https://www.skillboxes.com/events/"

CITIES = [
    {"name": "Mumbai",     "slug": "mumbai",     "cityId": 5},
    {"name": "Delhi",      "slug": "delhi",      "cityId": 2},
    {"name": "Bengaluru",  "slug": "bengaluru",  "cityId": 9},
    {"name": "Hyderabad",  "slug": "hyderabad",  "cityId": 1114881},
    {"name": "Chennai",    "slug": "chennai",    "cityId": 7},
    {"name": "Kolkata",    "slug": "kolkata",    "cityId": 8},
    {"name": "Pune",       "slug": "pune",       "cityId": 1127652},
    {"name": "Goa",        "slug": "goa",        "cityId": 1113278},
    {"name": "Chandigarh", "slug": "chandigarh", "cityId": 1108767},
    {"name": "Ahmedabad",  "slug": "ahmedabad",  "cityId": 1103349},
    {"name": "Jaipur",     "slug": "jaipur",     "cityId": 1115282},
    {"name": "Kochi",      "slug": "kochi",      "cityId": 1119023},
]

MUSIC_CATEGORIES = {
    "club gigs - music",
    "music concerts",
    "music festival",
    "live music",
    "concerts",
}

MUSIC_SUBCATEGORY_KEYWORDS = [
    "music", "rock", "jazz", "blues", "indie", "hip hop", "electronic",
    "edm", "trance", "techno", "house", "folk", "classical", "metal",
    "pop", "r&b", "fusion", "acoustic", "concert", "live music",
]


def is_music_event(item):
    category = (item.get("category") or "").lower()
    if any(cat in category for cat in MUSIC_CATEGORIES):
        return True
    subcats = [s.get("name", "").lower() for s in (item.get("subcategories") or [])]
    return any(
        kw in subcat
        for subcat in subcats
        for kw in MUSIC_SUBCATEGORY_KEYWORDS
    )


def fetch_city(session, city, device_id):
    city_id = city["cityId"]
    city_name = city["name"]
    city_slug = city["slug"]
    events = []
    seen_slugs = set()
    page = 1

    while True:
        payload = {
            "default_city": city_id,
            "opcode": "search",
            "type": "fetchAll",
            "eventCityEnb": True,
            "page": page,
        }
        try:
            resp = session.post(API_URL, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [{city_name}] Error page {page}: {e}", flush=True)
            break

        items = data.get("items") or []
        for item in items:
            slug = item.get("slug", "")
            if not slug or slug in seen_slugs:
                continue
            if not is_music_event(item):
                continue
            seen_slugs.add(slug)

            min_p = item.get("min_price", 0)
            max_p = item.get("max_price", 0)
            if min_p and max_p and min_p != max_p:
                price_str = f"INR {min_p} - {max_p}"
            elif max_p:
                price_str = f"INR {max_p}"
            elif min_p:
                price_str = f"INR {min_p}"
            else:
                price_str = "Free"

            events.append({
                "title": item.get("event_display_name") or item.get("event_name", ""),
                "venue": item.get("venue_name") or None,
                "date": item.get("event_date") or item.get("date"),
                "time": item.get("event_time"),
                "price": price_str,
                "url": EVENT_BASE_URL + slug,
                "category": item.get("category"),
                "city": city_name,
                "source": "skillboxes.com",
            })

        has_next = data.get("next", False)
        if not has_next or not items or page >= 5:
            break
        page += 1
        time.sleep(0.3)

    print(f"  {city_name}: {len(events)} music events", flush=True)
    return events


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Fetching SkillBox live music events...", flush=True)

    device_id = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "x-device-id": device_id,
        "devicetype": "Angular 1",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
        "Referer": "https://www.skillboxes.com/",
    }

    results = {}
    with requests.Session() as session:
        session.headers.update(headers)
        # Warm up session with a GET to pick up any cookies
        session.get("https://www.skillboxes.com/", timeout=15)

        for city in CITIES:
            results[city["slug"]] = fetch_city(session, city, device_id)
            time.sleep(0.5)

    total = sum(len(v) for v in results.values())
    active_cities = len([c for c in results.values() if c])
    print(f"\nTotal: {total} music events across {active_cities} cities", flush=True)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "SkillBox (skillboxes.com)",
        "total_events": total,
        "cities": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()

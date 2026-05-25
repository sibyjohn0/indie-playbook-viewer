#!/usr/bin/env python3
"""
Fetches upcoming live music events from Townscript (townscript.com) by city.
Uses their public radar API — no auth required.
Writes to data/townscript-events.json
Run daily: python3 scripts/fetch_townscript_events.py  (from repo root)
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Run: pip3 install requests")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
OUTPUT = REPO_ROOT / "data" / "townscript-events.json"

RADAR_URL = "https://www.townscript.com/listings/event/radar"
EVENT_BASE_URL = "https://www.townscript.com/in/"

CITIES = [
    {"name": "Mumbai",     "slug": "mumbai",     "lat": 19.0760, "lon": 72.8777},
    {"name": "Delhi",      "slug": "delhi",      "lat": 28.6139, "lon": 77.2090},
    {"name": "Bengaluru",  "slug": "bengaluru",  "lat": 12.9716, "lon": 77.5946},
    {"name": "Hyderabad",  "slug": "hyderabad",  "lat": 17.3850, "lon": 78.4867},
    {"name": "Chennai",    "slug": "chennai",    "lat": 13.0827, "lon": 80.2707},
    {"name": "Kolkata",    "slug": "kolkata",    "lat": 22.5726, "lon": 88.3639},
    {"name": "Pune",       "slug": "pune",       "lat": 18.5204, "lon": 73.8567},
    {"name": "Goa",        "slug": "goa",        "lat": 15.2993, "lon": 74.1240},
    {"name": "Jaipur",     "slug": "jaipur",     "lat": 26.9124, "lon": 75.7873},
    {"name": "Kochi",      "slug": "kochi",      "lat":  9.9312, "lon": 76.2673},
    {"name": "Ahmedabad",  "slug": "ahmedabad",  "lat": 23.0225, "lon": 72.5714},
    {"name": "Chandigarh", "slug": "chandigarh", "lat": 30.7333, "lon": 76.7794},
]

# Townscript topic codes for music-adjacent topics
MUSIC_TOPICS = [
    {"topicCode": "music",   "keyword": "music"},
    {"topicCode": "gigs",    "keyword": "gigs"},
    {"topicCode": "concert", "keyword": "concert"},
]

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
    "Referer": "https://www.townscript.com/",
}


def fetch_city(session, city):
    city_name = city["name"]
    city_slug = city["slug"]
    events = []
    seen_ids = set()

    for topic in MUSIC_TOPICS:
        url = (
            f"{RADAR_URL}"
            f"?lat={city['lat']}&lng={city['lon']}"
            f"&radarDistance=50&page=0&size=20"
        )
        body = {
            "topicCode": topic["topicCode"],
            "keyword": topic["keyword"],
            "startingSoon": False,
            "recurrent": None,
        }
        try:
            resp = session.post(url, json=body, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [{city_name}/{topic['topicCode']}] Error: {e}", flush=True)
            continue

        items = data.get("data", {}).get("data") or []
        for item in items:
            event_id = item.get("id") or item.get("eventId")
            if not event_id or event_id in seen_ids:
                continue
            # Skip past events
            if item.get("live") is False:
                continue
            seen_ids.add(event_id)

            short_name = item.get("shortName", "")
            price = item.get("minimumTicketPrice")
            price_str = f"INR {int(price)}" if price else "Free"

            # Parse ISO date
            start_raw = item.get("startTime", "")
            date_str = None
            time_str = None
            if start_raw:
                try:
                    dt = datetime.fromisoformat(start_raw.replace("+0000", "+00:00"))
                    # Convert to IST (+5:30)
                    from datetime import timedelta
                    dt_ist = dt + timedelta(hours=5, minutes=30)
                    date_str = dt_ist.strftime("%-d %B %Y")
                    time_str = dt_ist.strftime("%I:%M %p")
                except Exception:
                    date_str = start_raw[:10]

            venue = item.get("locality") or item.get("venueLocation") or None

            events.append({
                "title": item.get("name", ""),
                "venue": venue,
                "date": date_str,
                "time": time_str,
                "price": price_str,
                "url": EVENT_BASE_URL + short_name if short_name else None,
                "organiser": item.get("organizerName"),
                "city": city_name,
                "source": "townscript.com",
            })

        time.sleep(0.2)

    print(f"  {city_name}: {len(events)} music events", flush=True)
    return events


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Fetching Townscript live music events...", flush=True)

    results = {}
    with requests.Session() as session:
        session.headers.update(HEADERS)
        session.get("https://www.townscript.com/", timeout=15)

        for city in CITIES:
            results[city["slug"]] = fetch_city(session, city)
            time.sleep(0.4)

    total = sum(len(v) for v in results.values())
    active = len([c for c in results.values() if c])
    print(f"\nTotal: {total} music events across {active} cities", flush=True)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Townscript",
        "total_events": total,
        "cities": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()

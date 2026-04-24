"""Scrape the Churches Conservation Trust gazetteer.

The public `/visit/our-churches` page is a Craft CMS "loadomatic" widget.
It renders churches via a POST to `/loadomatic/form-events` with a JSON
body and a session-bound CSRF token from the hosting page.

One call returns every church in the register (~350). Each entry
carries: id, url, title, latitude, longitude, image, listing_summary,
county. That's rich enough to create a register record without a
per-church follow-up pass — though we stub support for detail fetching
so we can deepen records later.
"""

from __future__ import annotations

import json
import re

import requests

from _util import write_raw, slugify, UA, RateLimiter

PAGE_URL = "https://www.visitchurches.org.uk/visit/our-churches"
ENDPOINT = "https://www.visitchurches.org.uk/loadomatic/form-events"

CSRF_RE = re.compile(r"X-CSRF-Token['\"]*: *['\"]([^'\"]+)['\"]")


def start_session() -> tuple[requests.Session, str]:
    """Open a session, load the host page, extract the CSRF token."""
    session = requests.Session()
    session.headers["User-Agent"] = UA
    resp = session.get(PAGE_URL, timeout=30)
    resp.raise_for_status()
    m = CSRF_RE.search(resp.text)
    if not m:
        raise RuntimeError("Could not locate X-CSRF-Token on our-churches page")
    return session, m.group(1)


def fetch_all(session: requests.Session, token: str) -> list[dict]:
    """One call returns the whole list. `location_name` MUST be the empty
    string, not null — nulling it is what triggers the 500 error this
    scraper was chasing for an hour."""
    body = {
        "sort": "az",
        "filters": {},
        "section_handle": "churches",
        "location_name": "",
        "lat": None,
        "lng": None,
        "page": 1,
        "radius_limit": "50",
        "view": "list",
        "free_events": 0,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-CSRF-Token": token,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://www.visitchurches.org.uk",
        "Referer": PAGE_URL,
    }
    resp = session.post(ENDPOINT, json=body, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("entries", [])


def normalise(entry: dict) -> dict:
    title = entry.get("title") or ""
    # CCT titles read "Name, Village" — split for structured place.
    parts = [p.strip() for p in title.split(",") if p.strip()]
    name = parts[0] if parts else title
    settlement = parts[1] if len(parts) > 1 else None

    image = entry.get("image")
    hero = None
    if image:
        hero = {
            "url": image,
            "credit": "Churches Conservation Trust",
            "source": "Churches Conservation Trust",
            "sourceUrl": entry.get("url"),
            "licence": "© Churches Conservation Trust — reproduction by permission",
            "caption": (f"{name} — {settlement}" if settlement else name),
        }

    return {
        "id": f"cct-{slugify(name)}-{slugify(settlement or '')}".strip("-"),
        "source": "cct",
        "sourceUrl": entry.get("url"),
        "cct_id": entry.get("id"),
        "name": name,
        "settlement": settlement,
        "region": entry.get("county"),
        "nation": "England",  # CCT is CofE-only, England-wide
        "lat": entry.get("latitude"),
        "lon": entry.get("longitude"),
        "summary": entry.get("listing_summary") or None,
        "hero": hero,
        "custodian": "Churches Conservation Trust",
        # All CCT buildings are held long-term by the charity — classify
        # as preserved.
        "status": "preserved",
    }


def main():
    print("Opening CCT session…")
    session, token = start_session()
    print(f"  CSRF: {token[:24]}…")
    print("Fetching the full register in one call…")
    entries = fetch_all(session, token)
    print(f"  → {len(entries)} churches")

    records = [normalise(e) for e in entries]
    # Drop anything without coords (shouldn't happen — all entries have them)
    records = [r for r in records if r.get("lat") and r.get("lon")]
    print(f"  → {len(records)} with coordinates")

    write_raw("cct", records)


if __name__ == "__main__":
    main()

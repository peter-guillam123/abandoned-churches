"""Attach a Geograph hero photograph (CC-BY-SA 2.0) to each building
that doesn't already have one.

Geograph is the closest thing to a complete photographic census of the
British landscape — virtually every parish church, chapel and meeting
house has a CC-BY-SA photo tagged to its grid reference.

Geograph requires a free API key. Register at
  https://www.geograph.org.uk/api/

and set GEOGRAPH_API_KEY in the environment before running this
script. Without a key the script exits quietly so the rest of the
pipeline still runs.

Strategy mirrors fetch_commons.py:
  1. For every raw record without a hero, query Geograph's API by
     bounding-box around (lat, lon) at ~250m radius.
  2. Pick the highest-rated photo that mentions the building name or
     'church' / 'chapel' in its title, avoiding stock landscape shots.
  3. Write build/_raw/_geograph.json keyed by building id; merge via
     build_register.py (same slot as Commons — Geograph wins when both
     have a match because Geograph IDs are more obviously "this is the
     building", whereas Commons can return a landscape with it in the
     background).

Optional: this is a complement to Commons, not a replacement.
"""

from __future__ import annotations

import json
import math
import os
import re

import requests

from _util import RAW, RateLimiter, slugify, UA

API = "https://api.geograph.org.uk/api-facetql.php"

CHURCH_VOCAB = re.compile(
    r"church|chapel|abbey|minster|priory|cathedral|meeting house|parish",
    re.IGNORECASE,
)


def bbox(lat: float, lon: float, radius_m: int) -> tuple[float, float, float, float]:
    """Return (min_lon, min_lat, max_lon, max_lat) for a radius in metres."""
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * max(math.cos(math.radians(lat)), 1e-6))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def query(session: requests.Session, key: str, lat: float, lon: float, radius_m: int = 300) -> list[dict]:
    minlon, minlat, maxlon, maxlat = bbox(lat, lon, radius_m)
    # api-facetql.php is a GET API; facet=photo returns photo rows.
    params = {
        "key": key,
        "format": "JSON",
        "facet": "photo",
        "limit": "12",
        "select": "gridimage_id,title,realname,user_id,moderation_status,ft,imagetaken,lat,long",
        "box": f"{minlon},{minlat},{maxlon},{maxlat}",
    }
    r = session.get(API, params=params, timeout=20)
    r.raise_for_status()
    return r.json() or []


def score(title: str, name: str) -> int:
    if not CHURCH_VOCAB.search(title or ""):
        return -1
    s = 2
    tokens = [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) > 3]
    for t in tokens:
        if t in (title or "").lower():
            s += 2
    return s


def hero_from(row: dict, building_name: str) -> dict:
    gid = row.get("gridimage_id")
    title = row.get("title") or building_name
    user = row.get("realname") or "Geograph contributor"
    return {
        # Geograph provides an open stable thumbnail URL per image id.
        "url": f"https://www.geograph.org.uk/photo/{gid}",
        "thumbUrl": f"https://s0.geograph.org.uk/geophotos/{gid}_thumb.jpg",
        "caption": title,
        "credit": user,
        "source": "Geograph",
        "sourceUrl": f"https://www.geograph.org.uk/photo/{gid}",
        "licence": "CC-BY-SA 2.0",
        "licenceUrl": "https://creativecommons.org/licenses/by-sa/2.0/",
    }


def main():
    key = os.environ.get("GEOGRAPH_API_KEY")
    if not key:
        print("GEOGRAPH_API_KEY not set — skipping. (Register free at geograph.org.uk/api)")
        # Write an empty file so build_register.py can treat this as
        # "ran but no results".
        (RAW / "_geograph.json").write_text("{}", encoding="utf-8")
        return

    # Gather candidates = every raw record without a hero, with coords
    all_recs = []
    for p in sorted(RAW.glob("*.json")):
        if p.name.startswith("_"):
            continue
        all_recs.extend(json.loads(p.read_text(encoding="utf-8")))
    candidates = [
        r for r in all_recs
        if not r.get("hero") and r.get("lat") is not None and r.get("lon") is not None
    ]
    print(f"Geograph candidates: {len(candidates)}")

    session = requests.Session()
    session.headers["User-Agent"] = UA
    limiter = RateLimiter(min_gap=0.35)

    out: dict[str, dict] = {}
    for i, r in enumerate(candidates, 1):
        try:
            limiter.wait()
            rows = query(session, key, r["lat"], r["lon"], radius_m=300)
            name = r.get("name") or ""
            ranked = sorted(
                ((score(row.get("title", ""), name), row) for row in rows),
                key=lambda x: x[0], reverse=True,
            )
            if ranked and ranked[0][0] > 0:
                out[r.get("id") or slugify(name)] = hero_from(ranked[0][1], name)
        except Exception as e:
            print(f"  [{i}/{len(candidates)}] failed: {e}")
        if i % 50 == 0:
            print(f"  [{i}/{len(candidates)}] matched {len(out)}")

    (RAW / "_geograph.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(out)} photos → build/_raw/_geograph.json")


if __name__ == "__main__":
    main()

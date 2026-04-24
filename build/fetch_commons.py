"""Attach hero photographs to any building that doesn't already have one,
via Wikimedia Commons' geosearch API.

Commons is free, key-less, and its geosearch endpoint returns a list of
files within a radius of a point, with imageinfo + extmetadata for each
so we can pick one whose licence is genuinely reusable.

Strategy:
  1. For every raw record across sources (FoFC + CCT + HAR) that lacks an
     imagery.hero AND has coordinates, query
       commons.wikimedia.org/w/api.php
         ?action=query
         &generator=geosearch
         &ggscoord={lat}|{lon}
         &ggsradius=500
         &ggsnamespace=6
         &prop=imageinfo
         &iiprop=url|extmetadata
         &iiurlwidth=1200
     → up to N files within 500m.
  2. Score each file: prefer filenames that contain the building's name
     (or common church vocabulary), reject non-photo extensions, and
     filter to licences we can republish (CC, PD, GFDL).
  3. Write build/_raw/commons.json keyed by building id; merge into
     the register via build_register.py.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse

import requests

from _util import RAW, RateLimiter, slugify, UA

# Force unbuffered stdout so progress prints are live (important when
# run as a detached background job or inside a GitHub Action).
sys.stdout.reconfigure(line_buffering=True)

API = "https://commons.wikimedia.org/w/api.php"

# Licence identifiers we accept. Case-insensitive substring match on the
# LicenseShortName field from extmetadata.
OK_LICENCES = [
    "cc-by-sa", "cc by-sa", "cc-by", "cc by",
    "public domain", "pd-", "cc0", "gfdl",
    "attribution",
]

CHURCH_VOCAB = re.compile(
    r"church|chapel|abbey|minster|priory|cathedral|meeting house|parish",
    re.IGNORECASE,
)

PHOTO_EXT = re.compile(r"\.(jpe?g|png|webp|tiff?)$", re.IGNORECASE)


def acceptable_licence(ext: dict) -> str | None:
    """Return a human-friendly licence string if acceptable, else None."""
    short = (ext.get("LicenseShortName") or {}).get("value") or ""
    url = (ext.get("LicenseUrl") or {}).get("value") or ""
    lower = short.lower()
    for needle in OK_LICENCES:
        if needle in lower:
            return short or url or "CC"
    return None


def score(filename: str, name: str) -> int:
    """Higher = better match. Bonus for filename mentioning the
    building's name or 'church', penalty for not being a photo."""
    if not PHOTO_EXT.search(filename):
        return -999
    s = 0
    if CHURCH_VOCAB.search(filename):
        s += 4
    tokens = [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) > 3]
    for t in tokens:
        if t in filename.lower():
            s += 2
    return s


def geosearch(session: requests.Session, lat: float, lon: float, radius_m: int = 500) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "geosearch",
        "ggscoord": f"{lat}|{lon}",
        "ggsradius": str(radius_m),
        "ggsnamespace": "6",
        "ggsprimary": "all",
        "ggslimit": "10",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size",
        "iiurlwidth": "1200",
    }
    # Short connect + read timeouts so one slow endpoint can't stall
    # the whole pipeline. The rate limiter throttles us, not timeouts.
    r = session.get(API, params=params, timeout=(5, 10))
    r.raise_for_status()
    data = r.json()
    pages = (data.get("query") or {}).get("pages") or []
    return pages if isinstance(pages, list) else list(pages.values())


def best_match(pages: list[dict], building_name: str) -> dict | None:
    candidates = []
    for p in pages:
        title = p.get("title") or ""
        if not PHOTO_EXT.search(title):
            continue
        info = (p.get("imageinfo") or [None])[0]
        if not info:
            continue
        ext = info.get("extmetadata") or {}
        licence = acceptable_licence(ext)
        if not licence:
            continue
        s = score(title, building_name)
        if s < 0:
            continue
        author = (ext.get("Artist") or {}).get("value") or ""
        # Strip HTML tags from the author field (Commons often embeds <a>)
        author = re.sub(r"<[^>]+>", "", author).strip() or "Unknown"
        candidates.append({
            "score": s,
            "title": title,
            "thumb": info.get("thumburl") or info.get("url"),
            "full": info.get("url"),
            "licence": licence,
            "licence_url": (ext.get("LicenseUrl") or {}).get("value"),
            "author": author,
            "file_page": p.get("title") and f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(p['title'])}",
        })
    if not candidates:
        return None
    candidates.sort(key=lambda c: c["score"], reverse=True)
    best = candidates[0]
    return {
        "url": best["thumb"] or best["full"],
        "thumbUrl": best["thumb"],
        "caption": best["title"].replace("File:", "").rsplit(".", 1)[0],
        "credit": best["author"],
        "source": "Wikimedia Commons",
        "sourceUrl": best["file_page"],
        "licence": best["licence"],
        "licenceUrl": best["licence_url"],
    }


def load_all_raw_records() -> list[dict]:
    out = []
    for p in sorted(RAW.glob("*.json")):
        if p.name.startswith("_"):
            continue
        for r in json.loads(p.read_text(encoding="utf-8")):
            out.append(r)
    return out


def building_key(rec: dict) -> str:
    """Mirror the id logic used by each source's normalise — needed so
    the enrichment keys line up with the final register ids."""
    source = rec.get("source")
    name = rec.get("name") or ""
    if source == "fofc":
        return f"fofc-{slugify(name)}-{slugify(rec.get('settlement') or '')}".strip("-")
    if source == "cct":
        return f"cct-{slugify(name)}-{slugify(rec.get('settlement') or '')}".strip("-")
    if source == "heritage-at-risk":
        key = rec.get("list_entry") or rec.get("har_id")
        return f"har-{slugify(name or 'Unknown place of worship')}-{key}"
    return rec.get("id") or slugify(name)


def main():
    records = load_all_raw_records()
    candidates = [
        r for r in records
        if not r.get("hero")
        and r.get("lat") is not None and r.get("lon") is not None
    ]
    print(f"Commons enrichment candidates: {len(candidates)}", flush=True)

    # Resume from an existing checkpoint — we write the file every 50
    # records so a killed run doesn't lose everything.
    out_path = RAW / "_commons.json"
    if out_path.exists():
        out: dict[str, dict] = json.loads(out_path.read_text(encoding="utf-8"))
        # Also skip any candidate whose id maps to a record in out with
        # an "enrichmentStatus" marker (meaning we tried and failed but
        # recorded the attempt).
        done = set(out.keys())
        print(f"  resuming — {len(done)} already attempted", flush=True)
    else:
        out = {}
        done = set()

    session = requests.Session()
    session.headers["User-Agent"] = UA
    limiter = RateLimiter(min_gap=0.35)

    CHECKPOINT_EVERY = 50

    def flush():
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        for i, r in enumerate(candidates, 1):
            key = building_key(r)
            if key in done:
                continue
            try:
                limiter.wait()
                pages = geosearch(session, r["lat"], r["lon"], radius_m=400)
                hero = best_match(pages, r.get("name") or "")
                if hero:
                    out[key] = hero
                else:
                    out[key] = {"enrichmentStatus": "no match"}
            except requests.Timeout:
                out[key] = {"enrichmentStatus": "timeout"}
            except Exception as e:
                out[key] = {"enrichmentStatus": f"error: {str(e)[:80]}"}
            done.add(key)
            if i % 25 == 0:
                matched = sum(1 for v in out.values() if "url" in v)
                print(f"  [{i}/{len(candidates)}] matched {matched}, attempted {len(out)}", flush=True)
            if i % CHECKPOINT_EVERY == 0:
                flush()
    finally:
        flush()

    matched = sum(1 for v in out.values() if "url" in v)
    print(f"\nWrote {matched} photos (of {len(out)} attempted) → {out_path.relative_to(RAW.parent.parent)}", flush=True)


if __name__ == "__main__":
    main()

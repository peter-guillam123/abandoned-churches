"""Enrich every raw record with postcodes.io geography.

Two paths:
  1. Records with a `postcode` but no coords (most FoFC entries) are
     looked up via /postcodes/{postcode} — this returns lat/lon AND
     the administrative context in one call.
  2. Records with (lat, lon) but no postcode (most Heritage at Risk
     entries) are reverse-geocoded via POST /postcodes (batched).

Output: build/_raw/_enrichment.json keyed by building id, shape::

    {
      "<id>": {
        "lat": 53.34, "lon": -4.34,
        "postcode": "LL71 8AG",
        "lsoa": {"code": "W01000021", "name": "Isle of Anglesey 002C"},
        "msoa": {...},
        "parish": "Rhosybol", "ward": "Twrcelyn", "council": "Isle of Anglesey",
        "constituency": "Ynys Môn",
        "ruralUrban": "Smaller rural: Further from a major town or city",
        "travelToWorkArea": "Bangor and Holyhead",
        "nationalPark": null,
        "nation": "Wales"
      }, ...
    }

postcodes.io is free and key-less. We rate-limit to ~3 req/s."""

from __future__ import annotations

import json

import requests

from _util import RAW, RateLimiter, slugify

FORWARD_URL = "https://api.postcodes.io/postcodes/{pc}"
REVERSE_URL = "https://api.postcodes.io/postcodes"  # POST batch reverse
HEADERS = {"User-Agent": "abandoned-churches-pipeline/0.1"}


def _clean_postcode(pc: str) -> str:
    return " ".join(pc.upper().strip().split())


def _park(park: str | None) -> str | None:
    if not park:
        return None
    # postcodes.io returns "England (non-National Park)" for most postcodes;
    # strip those.
    if "non-National Park" in park:
        return None
    return park


def _context_from_pc_record(rec: dict) -> dict:
    codes = rec.get("codes") or {}
    return {
        "lat": rec.get("latitude"),
        "lon": rec.get("longitude"),
        "postcode": rec.get("postcode"),
        "lsoa": {"code": codes.get("lsoa"), "name": rec.get("lsoa")},
        "msoa": {"code": codes.get("msoa"), "name": rec.get("msoa")},
        "parish": rec.get("parish"),
        "ward": rec.get("admin_ward"),
        "council": rec.get("admin_district"),
        "constituency": rec.get("parliamentary_constituency_2024") or rec.get("parliamentary_constituency"),
        "ruralUrban": rec.get("ruc21") or rec.get("ruc11"),
        "travelToWorkArea": rec.get("ttwa"),
        "nationalPark": _park(rec.get("national_park")),
        "nation": rec.get("country"),
    }


def _fofc_id(r: dict) -> str:
    """Recompute the id fetch_fofc.py builds so enrichment keys match."""
    name = r.get("name") or ""
    settlement = r.get("settlement") or ""
    return f"fofc-{slugify(name)}-{slugify(settlement)}".strip("-")


def _har_id(r: dict) -> str:
    name = r.get("name") or "Unknown place of worship"
    key = r.get("list_entry") or r.get("har_id")
    return f"har-{slugify(name)}-{key}"


def forward_lookup(records: list[tuple[str, str]]) -> dict[str, dict]:
    """Look up a list of (id, postcode) pairs via the single-postcode API."""
    out: dict[str, dict] = {}
    limiter = RateLimiter(min_gap=0.33)
    for i, (rid, pc) in enumerate(records, 1):
        limiter.wait()
        try:
            resp = requests.get(FORWARD_URL.format(pc=pc.replace(" ", "%20")), headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                out[rid] = {"enrichmentStatus": f"postcode {pc} not found"}
                continue
            body = resp.json()
            out[rid] = _context_from_pc_record(body.get("result") or {})
        except Exception as e:
            out[rid] = {"enrichmentStatus": f"forward lookup failed: {e}"}
        if i % 20 == 0:
            print(f"    forward: {i}/{len(records)}")
    return out


def reverse_lookup(records: list[tuple[str, float, float]]) -> dict[str, dict]:
    """Batch reverse-geocode (id, lat, lon). postcodes.io allows 100
    locations per call."""
    out: dict[str, dict] = {}
    BATCH = 100
    limiter = RateLimiter(min_gap=0.5)
    for i in range(0, len(records), BATCH):
        limiter.wait()
        chunk = records[i : i + BATCH]
        payload = {
            "geolocations": [
                {"latitude": lat, "longitude": lon, "limit": 1, "radius": 2000}
                for _, lat, lon in chunk
            ]
        }
        try:
            resp = requests.post(REVERSE_URL, json=payload, timeout=60, headers=HEADERS)
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            print(f"    reverse batch {i // BATCH + 1}: {e}")
            continue
        results = body.get("result") or []
        for (rid, lat, lon), hit in zip(chunk, results):
            matches = (hit or {}).get("result") or []
            if not matches:
                out[rid] = {"lat": lat, "lon": lon, "enrichmentStatus": "no postcode within 2km"}
                continue
            best = matches[0]
            ctx = _context_from_pc_record(best)
            # Keep the original coordinates — the postcode's lat/lon is fine
            # for context, but for map placement we want the building's.
            ctx["lat"] = lat
            ctx["lon"] = lon
            out[rid] = ctx
        print(f"    reverse: {min(i + BATCH, len(records))}/{len(records)}")
    return out


def main():
    # Gather raw records we need to enrich
    fofc_records = json.loads((RAW / "fofc.json").read_text(encoding="utf-8")) if (RAW / "fofc.json").exists() else []
    har_records = json.loads((RAW / "heritage_at_risk.json").read_text(encoding="utf-8")) if (RAW / "heritage_at_risk.json").exists() else []

    # FoFC — have postcodes, need forward lookup
    forward_pairs = []
    for r in fofc_records:
        pc = r.get("postcode")
        if not pc:
            continue
        forward_pairs.append((_fofc_id(r), _clean_postcode(pc)))
    print(f"Forward (postcode → geography): {len(forward_pairs)} FoFC records")
    forward_out = forward_lookup(forward_pairs)

    # HAR — have coords, need reverse lookup
    reverse_triples = []
    for r in har_records:
        if r.get("lat") is None or r.get("lon") is None:
            continue
        reverse_triples.append((_har_id(r), r["lat"], r["lon"]))
    print(f"\nReverse (lat/lon → geography): {len(reverse_triples)} HAR records")
    reverse_out = reverse_lookup(reverse_triples)

    merged = {**forward_out, **reverse_out}
    p = RAW / "_enrichment.json"
    p.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(merged)} enrichments → {p.relative_to(RAW.parent.parent)}")


if __name__ == "__main__":
    main()

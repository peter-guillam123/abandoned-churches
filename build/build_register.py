"""Merge build/_raw/*.json + enrichment into data/buildings.json.

Strategy
--------
1. Load the six hand-curated records from data/buildings.hand.json
   (preserved unchanged — these are the reporting-anchored portraits).
2. Load each raw source in turn — FoFC, Heritage at Risk, CCT (when
   available), etc. — and normalise into schema v2.
3. Dedupe: hand-curated entries win; then FoFC wins over HAR (FoFC pages
   are richer and often list the same building).
4. Attach enrichment (LSOA, parish, ward, …) from _enrichment.json.
5. Write data/buildings.json.

The schema is soft — any field can be null. Rendering code omits
empty sections.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from _util import RAW, slugify, infer_denomination, canonicalise_denomination

REPO = Path(__file__).parent.parent
DATA = REPO / "data"
HAND_PATH = DATA / "buildings.hand.json"
OUT_PATH = DATA / "buildings.json"


def load_hand() -> list[dict]:
    if not HAND_PATH.exists():
        return []
    return json.loads(HAND_PATH.read_text(encoding="utf-8")).get("buildings", [])


def load_raw(name: str) -> list[dict]:
    p = RAW / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def load_enrichment() -> dict[str, dict]:
    p = RAW / "_enrichment.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_commons_photos() -> dict[str, dict]:
    p = RAW / "_commons.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_geograph_photos() -> dict[str, dict]:
    p = RAW / "_geograph.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- Normalisers ----------

def _split_place(raw: str | None) -> tuple[str | None, str | None]:
    """FoFC pages format place as 'Village, County'. Split it."""
    if not raw:
        return None, None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return parts[0], None


def from_fofc(r: dict) -> dict:
    settlement, region = _split_place(r.get("place_raw"))
    # Fall back: extract from name "St X's, Village"
    if not settlement and r.get("name") and "," in r["name"]:
        settlement = r["name"].split(",", 1)[1].strip().rstrip("'s")

    return {
        "id": r["id"],
        "name": (r.get("name") or "").split(",")[0].strip() or None,
        "dedicatedTo": None,
        # Denomination is the *historical* tradition the building was
        # built for, not the current custodian. FoFC vesting doesn't
        # change that. Custodian sits separately.
        "denomination": {
            "current": r.get("denomination"),
            "confidence": r.get("denominationConfidence"),
            "historical": [],
        },
        "place": {
            "settlement": settlement,
            "region": region,
            "parish": None,
            "council": None,
            "ward": None,
            "constituency": None,
            "nation": r.get("nation"),
            "setting": "rural",
        },
        "listing": {
            "grade": r.get("listing_grade"),
            "listedOn": None,
            "body": "Cadw" if r.get("nation") == "Wales" else "Historic England",
            "reason": None,
            "associated": [],
        },
        "fabric": {"firstWorship": None, "phases": [], "materials": None, "plan": None, "style": None},
        "interior": {"features": []},
        "status": "preserved",
        "statusHistory": [],
        "custodian": {"body": "Friends of Friendless Churches", "since": None, "previously": None},
        "lastService": None,
        "condition": {"summary": None, "plannedWorks": [], "worksTimeline": None, "estimatedCost": None},
        "context": {"lsoa": None, "msoa": None, "ruralUrban": None, "ruralUrbanPrior": None,
                    "travelToWorkArea": None, "nationalPark": None,
                    "deprivationDecile": None, "deprivationSource": None},
        "use": {"servicesStatus": None, "lateCongregationSize": None, "openingHours": None},
        "people": [],
        "quotes": [],
        "coverage": {"guardian": []},
        "imagery": {"hero": r.get("hero"), "gallery": []},
        "sources": [
            {"label": "Friends of Friendless Churches", "url": r.get("sourceUrl")},
        ],
        "summary": r.get("summary"),
        "provenance": f"Scraped from Friends of Friendless Churches ({r.get('sourceUrl')}); schema v2.",
        # Coordinates filled in later — FoFC pages rarely publish them cleanly;
        # we can resolve via the place string through Nominatim in a
        # follow-up pass if needed.
        "lat": None,
        "lon": None,
    }


def from_cct(r: dict) -> dict:
    """Churches Conservation Trust entries — preserved, CofE redundant,
    with a CCT-owned hero photograph."""
    return {
        "id": r["id"],
        "name": r.get("name"),
        "dedicatedTo": None,
        "denomination": {
            "current": "Church of England",
            "confidence": "high",
            "historical": [],
        },
        "place": {
            "settlement": r.get("settlement"),
            "region": r.get("region"),
            "parish": None,
            "council": None,
            "ward": None,
            "constituency": None,
            "nation": r.get("nation") or "England",
            "setting": None,
        },
        "lat": r.get("lat"),
        "lon": r.get("lon"),
        "listing": {
            "grade": None,
            "listedOn": None,
            "body": "Historic England",
            "reason": None,
            "associated": [],
        },
        "fabric": {"firstWorship": None, "phases": [], "materials": None, "plan": None, "style": None},
        "interior": {"features": []},
        "status": "preserved",
        "statusHistory": [],
        "custodian": {"body": "Churches Conservation Trust", "since": None, "previously": "Church of England"},
        "lastService": None,
        "condition": {"summary": None, "plannedWorks": [], "worksTimeline": None, "estimatedCost": None},
        "context": {"lsoa": None, "msoa": None, "ruralUrban": None, "ruralUrbanPrior": None,
                    "travelToWorkArea": None, "nationalPark": None,
                    "deprivationDecile": None, "deprivationSource": None},
        "use": {"servicesStatus": "Open by arrangement / events", "lateCongregationSize": None, "openingHours": None},
        "people": [],
        "quotes": [],
        "coverage": {"guardian": []},
        "imagery": {"hero": r.get("hero"), "gallery": []},
        "sources": [
            {"label": "Churches Conservation Trust", "url": r.get("sourceUrl")},
        ],
        "summary": r.get("summary"),
        "provenance": f"Scraped from the Churches Conservation Trust gazetteer ({r.get('sourceUrl')}); schema v2.",
    }


_HAR_STATUS = {
    "very bad": "at-risk",
    "poor": "at-risk",
    "fair": "at-risk",
    "generally satisfactory but with significant localised problems": "at-risk",
    "good": "preserved",
}


def from_har(r: dict) -> dict:
    name = r.get("name") or "Unknown place of worship"
    council = r.get("local_auth") or None
    condition = (r.get("condition") or "").lower()
    status = _HAR_STATUS.get(condition, "at-risk")
    return {
        "id": f"har-{slugify(name)}-{r.get('list_entry') or r.get('har_id')}",
        "name": name,
        "dedicatedTo": None,
        "denomination": {
            "current": r.get("denomination"),
            "confidence": r.get("denominationConfidence"),
            "historical": [],
        },
        "place": {
            "settlement": None,
            "region": None,
            "parish": None,
            "council": council,
            "ward": None,
            "constituency": None,
            "nation": "England",
            "setting": None,
        },
        "lat": r.get("lat"),
        "lon": r.get("lon"),
        "listing": {
            "grade": r.get("grade"),
            "listedOn": None,
            "body": "Historic England",
            "reason": r.get("description"),
            "associated": [],
        },
        "fabric": {"firstWorship": None, "phases": [], "materials": None, "plan": None, "style": None},
        "interior": {"features": []},
        "status": status,
        "statusHistory": [],
        "custodian": {"body": None, "since": None, "previously": None},
        "lastService": None,
        "condition": {
            "summary": r.get("description"),
            "plannedWorks": [],
            "worksTimeline": None,
            "estimatedCost": None,
        },
        "context": {"lsoa": None, "msoa": None, "ruralUrban": None, "ruralUrbanPrior": None,
                    "travelToWorkArea": None, "nationalPark": None,
                    "deprivationDecile": None, "deprivationSource": None},
        "use": {"servicesStatus": None, "lateCongregationSize": None, "openingHours": None},
        "people": [],
        "quotes": [],
        "coverage": {"guardian": []},
        "imagery": {"hero": None, "gallery": []},
        "sources": [
            {"label": f"Historic England Heritage at Risk · list entry {r.get('list_entry')}",
             "url": f"https://historicengland.org.uk/listing/the-list/list-entry/{r.get('list_entry')}/" if r.get("list_entry") else None},
        ],
        "summary": (r.get("description") or "").strip().split(". ")[0] or None,
        "provenance": "Historic England Heritage at Risk Register (2024 annual release).",
    }


def apply_enrichment(building: dict, enrichment: dict) -> dict:
    data = enrichment.get(building["id"])
    if not data:
        return building
    # Even when enrichment failed with a status note, we might still have
    # partial coords — but in practice we just skip applying in that case.
    if data.get("enrichmentStatus"):
        return building
    # Coords — backfill when the raw source didn't provide them (FoFC).
    if building.get("lat") is None and data.get("lat") is not None:
        building["lat"] = data["lat"]
    if building.get("lon") is None and data.get("lon") is not None:
        building["lon"] = data["lon"]
    place = building["place"]
    place["parish"] = place.get("parish") or data.get("parish")
    place["ward"] = place.get("ward") or data.get("ward")
    place["council"] = place.get("council") or data.get("council")
    place["constituency"] = place.get("constituency") or data.get("constituency")
    if not place.get("nation") and data.get("nation"):
        place["nation"] = data["nation"]
    ctx = building["context"]
    ctx["lsoa"] = ctx.get("lsoa") or data.get("lsoa")
    ctx["msoa"] = ctx.get("msoa") or data.get("msoa")
    ctx["ruralUrban"] = ctx.get("ruralUrban") or data.get("ruralUrban")
    ctx["travelToWorkArea"] = ctx.get("travelToWorkArea") or data.get("travelToWorkArea")
    ctx["nationalPark"] = ctx.get("nationalPark") or data.get("nationalPark")
    return building


def _name_tokens(name: str) -> set[str]:
    """Strip down to the signal-bearing tokens for loose matching."""
    name = (name or "").lower()
    # Drop punctuation and common noise tokens (St, The, Church etc.)
    tokens = re.findall(r"[a-z0-9]+", name)
    drop = {"st", "the", "of", "a", "and", "church", "chapel", "old", "saint"}
    return {t for t in tokens if t not in drop and len(t) > 2}


def dedupe(all_records: list[dict]) -> list[dict]:
    """Prefer hand-curated > FoFC > CCT > HAR. Match on coord proximity
    + at least one shared distinctive token (dedicated saint / village
    name). Handles the common case where HAR calls it "Church of
    St Nicholas, London Road" and CCT has it as "St Nicholas, Blakeney"
    — same coordinates, clear token overlap."""
    kept: list[dict] = []
    seen_ids: set[str] = set()
    for r in all_records:
        if r["id"] in seen_ids:
            continue
        dup = False
        rtokens = _name_tokens(r.get("name") or "")
        for k in kept:
            if not r.get("lat") or not k.get("lat"):
                continue
            if abs(r["lat"] - k["lat"]) >= 0.0025 or abs(r["lon"] - k["lon"]) >= 0.0025:
                # Not within ~250m — can't be the same building.
                continue
            ktokens = _name_tokens(k.get("name") or "")
            # Either the names match loosely, or they share a meaningful
            # token (saint name, village), or they're at the exact same
            # address (within ~30m).
            close = abs(r["lat"] - k["lat"]) < 0.0003 and abs(r["lon"] - k["lon"]) < 0.0003
            if close or (rtokens & ktokens):
                dup = True
                break
        if dup:
            continue
        kept.append(r)
        seen_ids.add(r["id"])
    return kept


def apply_commons_photo(building: dict, photos: dict) -> dict:
    """Attach a Commons-/Geograph-sourced hero if the building doesn't
    already have one. Skip entries whose only field is an
    `enrichmentStatus` marker (attempted, no photo found)."""
    if building.get("imagery", {}).get("hero"):
        return building
    hero = photos.get(building["id"])
    if not hero or "url" not in hero:
        return building
    building.setdefault("imagery", {"hero": None, "gallery": []})
    building["imagery"]["hero"] = hero
    return building


def main():
    hand = load_hand()
    fofc = [from_fofc(r) for r in load_raw("fofc")]
    cct = [from_cct(r) for r in load_raw("cct")]
    har = [from_har(r) for r in load_raw("heritage_at_risk")]
    enrichment = load_enrichment()
    commons = load_commons_photos()
    geograph = load_geograph_photos()

    # Order matters for dedupe — first-seen wins. Hand-curated hero
    # records come first, then curated charity sets (FoFC and CCT both
    # have rich fields), then the broad Heritage at Risk list.
    combined = list(hand) + fofc + cct + har
    combined = [apply_enrichment(b, enrichment) for b in combined]
    combined = dedupe(combined)
    # Photo order: Commons first (free, well-covered), Geograph fills
    # whatever Commons missed. Both only apply when imagery.hero is null.
    combined = [apply_commons_photo(b, commons) for b in combined]
    combined = [apply_commons_photo(b, geograph) for b in combined]
    combined = [b for b in combined if b.get("lat") is not None and b.get("lon") is not None]

    # Canonicalise the denomination string on every record so the
    # frontend's filter-chip menu doesn't end up with near-duplicate
    # variants ("Church of England (Diocese of York)" → "Church of
    # England", "Roman Catholic Church" → "Roman Catholic", etc.).
    for b in combined:
        d = b.get("denomination") or {}
        canon = canonicalise_denomination(d.get("current"))
        if canon != d.get("current"):
            d["current"] = canon
            b["denomination"] = d

    # Count statuses
    counts: dict[str, int] = {}
    for b in combined:
        counts[b["status"]] = counts.get(b["status"], 0) + 1

    out = {
        "meta": {
            "title": "Church and State — a register of the UK's closed and at-risk churches",
            "updated": date.today().isoformat(),
            "schemaVersion": 2,
            "note": (
                f"{len(combined)} buildings. "
                f"{counts.get('at-risk', 0)} at risk · "
                f"{counts.get('preserved', 0)} preserved · "
                f"{counts.get('rescued', 0)} rescued · "
                f"{counts.get('repurposed', 0)} repurposed · "
                f"{counts.get('closed', 0)} closed · "
                f"{counts.get('demolished', 0)} lost."
            ),
        },
        "buildings": combined,
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(combined)} buildings to {OUT_PATH.relative_to(REPO)}")
    print(f"  {out['meta']['note']}")


if __name__ == "__main__":
    main()

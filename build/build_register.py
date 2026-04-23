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

from _util import RAW, slugify

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
        "denomination": {
            "current": "Friends of Friendless Churches (redundant)",
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
        "denomination": {"current": None, "historical": []},
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


def dedupe(all_records: list[dict]) -> list[dict]:
    """Prefer hand-curated, then FoFC, then HAR. Keyed by name + coords to
    within ~500m."""
    kept: list[dict] = []
    seen_ids: set[str] = set()
    for r in all_records:
        if r["id"] in seen_ids:
            continue
        # Fuzzy dedupe by name+lat+lon
        dup = False
        for k in kept:
            if not r.get("lat") or not k.get("lat"):
                continue
            if (
                r["name"]
                and k["name"]
                and r["name"].lower() == k["name"].lower()
                and abs(r["lat"] - k["lat"]) < 0.005
                and abs(r["lon"] - k["lon"]) < 0.005
            ):
                dup = True
                break
        if dup:
            continue
        kept.append(r)
        seen_ids.add(r["id"])
    return kept


def main():
    hand = load_hand()
    fofc = [from_fofc(r) for r in load_raw("fofc")]
    har = [from_har(r) for r in load_raw("heritage_at_risk")]
    enrichment = load_enrichment()

    # Order matters for dedupe — first-seen wins.
    combined = list(hand) + fofc + har
    # Enrichment runs BEFORE dedupe so FoFC records get their lat/lon,
    # which dedupe uses to match against HAR by coordinate proximity.
    combined = [apply_enrichment(b, enrichment) for b in combined]
    combined = dedupe(combined)
    # Drop records we still can't place on the map — no coords after
    # enrichment means they're not useful to a reader typing a postcode.
    combined = [b for b in combined if b.get("lat") is not None and b.get("lon") is not None]

    # Count statuses
    counts: dict[str, int] = {}
    for b in combined:
        counts[b["status"]] = counts.get(b["status"], 0) + 1

    out = {
        "meta": {
            "title": "Friendless — a register of the UK's closed and at-risk churches",
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

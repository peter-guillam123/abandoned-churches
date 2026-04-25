"""Pull Historic England's Heritage at Risk Register (places of worship only).

The 2024 annual register is published on Historic England's ArcGIS Open
Data Hub as a GeoJSON FeatureCollection. It contains ~4,900 features
covering archaeology, buildings and structures, places of worship,
conservation areas, parks, battlefields and wrecks. Each feature is a
polygon in Web Mercator (EPSG:3857), and each carries a `Risk_Metho`
field that classifies the kind of asset.

We keep only `Risk_Metho == 'Place of worship'`, reproject the polygon
centroid to WGS84, and write build/_raw/heritage_at_risk.json.
"""

from __future__ import annotations

import json
import math

from _util import get_json, write_raw, infer_denomination

HAR_ITEM = "3866e4532c5146ceb8ba23679bf8fc31"
HAR_URL = (
    f"https://hub.arcgis.com/api/download/v1/items/{HAR_ITEM}/geojson"
    "?redirect=false&layers=0"
)

# EPSG:3857 (Web Mercator) → WGS84 (lon,lat in degrees)
def mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    lon = x * 180 / 20037508.34
    lat = (
        math.atan(math.exp(y * math.pi / 20037508.34))
        * 360 / math.pi
        - 90
    )
    return lon, lat


def polygon_centroid(ring: list[list[float]]) -> tuple[float, float]:
    lons = [c[0] for c in ring]
    lats = [c[1] for c in ring]
    return sum(lons) / len(lons), sum(lats) / len(lats)


def feature_centroid_wgs84(feat: dict) -> tuple[float, float] | tuple[None, None]:
    geom = feat.get("geometry") or {}
    t = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None, None
    if t == "Polygon":
        cx, cy = polygon_centroid(coords[0])
    elif t == "MultiPolygon":
        # Centroid of the first polygon is fine for a single church pin.
        cx, cy = polygon_centroid(coords[0][0])
    elif t == "Point":
        cx, cy = coords[0], coords[1]
    else:
        return None, None
    lon, lat = mercator_to_wgs84(cx, cy)
    return lat, lon


def normalise(feat: dict) -> dict:
    props = feat.get("properties", {}) or {}
    lat, lon = feature_centroid_wgs84(feat)
    name = props.get("EntryName")
    # All HAR records sit in England, so the inference can default
    # to Church of England for the "St X's" pattern.
    denom, denom_conf = infer_denomination(
        name=name, body=None, summary=None, nation="England",
    )
    return {
        "source": "heritage-at-risk",
        "har_id": props.get("uid") or props.get("FID"),
        "list_entry": props.get("List_Entry"),
        "name": name,
        "heritage_category": props.get("HeritageCa"),
        "risk_category": props.get("Risk_Metho"),
        "url": props.get("URL"),
        "lat": lat,
        "lon": lon,
        "denomination": denom,
        "denominationConfidence": denom_conf,
        "_props": props,
    }


def main():
    print("Fetching Historic England Heritage at Risk GeoJSON…")
    manifest = get_json(HAR_URL, cache=True)
    if manifest.get("status") in {"Pending", "Processing"}:
        print("  ArcGIS job still processing — re-run in 30s.")
        return
    result_url = manifest.get("resultUrl")
    if not result_url:
        print(f"  unexpected manifest: {manifest}")
        return
    data = get_json(result_url, cache=True)
    feats = data.get("features", [])
    print(f"  → {len(feats)} total features in register")

    # Filter to places of worship — the value is exactly "Place of worship"
    # (lowercase w, singular)
    pow_feats = [f for f in feats if f.get("properties", {}).get("Risk_Metho") == "Place of worship"]
    print(f"  → {len(pow_feats)} places of worship")

    records = [normalise(f) for f in pow_feats]
    records = [r for r in records if r.get("lat") and r.get("lon")]
    print(f"  → {len(records)} with coordinates")

    write_raw("heritage_at_risk", records)


if __name__ == "__main__":
    main()

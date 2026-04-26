// data.js — loads and exposes the register.

let cache = null;

export async function loadBuildings() {
  if (cache) return cache;
  const res = await fetch('./data/buildings.json', { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to load register: ${res.status}`);
  const json = await res.json();
  cache = json;
  return json;
}

// Haversine — returns distance in kilometres between two lat/lon points.
export function distanceKm(aLat, aLon, bLat, bLon) {
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(bLat - aLat);
  const dLon = toRad(bLon - aLon);
  const lat1 = toRad(aLat);
  const lat2 = toRad(bLat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

// Nearest N buildings to a point, annotated with .distanceKm.
export function nearestTo(lat, lon, buildings, limit = 5) {
  return buildings
    .map((b) => ({ ...b, distanceKm: distanceKm(lat, lon, b.lat, b.lon) }))
    .sort((a, b) => a.distanceKm - b.distanceKm)
    .slice(0, limit);
}

// Human-friendly distance label. Keeps the figure compact — this sits in a
// mono-font column that would look wrong with long decimal tails.
export function formatDistance(km) {
  if (km < 1) return `${Math.round(km * 1000)} m`;
  if (km < 10) return `${km.toFixed(1)} km`;
  return `${Math.round(km)} km`;
}

export const STATUS_LABELS = {
  'at-risk': 'At risk',
  rescued: 'Rescued',
  preserved: 'Preserved',
  repurposed: 'Repurposed',
  closed: 'Closed, unresolved',
  demolished: 'Lost',
};

// Editorial place label — "Llandyfrydog, Anglesey". Used in result lists
// and in the detail header. Written once so the UI speaks consistently.
//
// Most records carry settlement + region, but Heritage at Risk entries
// arrive with neither (the HAR feed only ships an EntryName). For
// those, fall back through the postcodes.io enrichment fields so we
// always say *something* concrete: parish + council, or council on
// its own when there's no civil parish.
export function placeLabel(b) {
  const p = b.place || {};
  const settlement = p.settlement;
  const region = p.region;
  if (settlement || region) {
    return [settlement, region].filter(Boolean).join(', ');
  }
  const fallback = [p.parish, p.council, p.constituency].filter(Boolean);
  return fallback.length ? fallback[0] + (fallback.length > 1 ? `, ${fallback[fallback.length - 1]}` : '') : '';
}

export function denominationLabel(b) {
  return b.denomination?.current || '';
}

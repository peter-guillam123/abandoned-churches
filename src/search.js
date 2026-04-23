// search.js — resolves a postcode or place name to a lat/lon.
// UK postcodes go to postcodes.io (free, no key). Place names fall back to
// OSM Nominatim. Both are rate-limited; this is a reader-entry path, not a
// bulk job, so no debounce beyond the form submission itself.

const POSTCODE_RE = /^([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})$/i;

export async function resolve(query) {
  const q = (query || '').trim();
  if (!q) throw new Error('Enter a postcode or a place name.');

  const pc = q.match(POSTCODE_RE);
  if (pc) {
    const clean = `${pc[1]} ${pc[2]}`.toUpperCase();
    try {
      const res = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(clean)}`);
      if (res.ok) {
        const j = await res.json();
        if (j.result) {
          return {
            lat: j.result.latitude,
            lon: j.result.longitude,
            label: `${clean} — ${j.result.admin_district || j.result.region || ''}`.trim(),
            kind: 'postcode',
          };
        }
      }
    } catch (_) { /* fall through to Nominatim */ }
  }

  const nom = await fetch(
    `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1&countrycodes=gb`,
    { headers: { 'Accept-Language': 'en-GB' } }
  );
  if (!nom.ok) throw new Error('Place lookup failed. Try again?');
  const arr = await nom.json();
  if (!arr.length) throw new Error(`No UK location found for "${q}".`);
  const r = arr[0];
  return {
    lat: parseFloat(r.lat),
    lon: parseFloat(r.lon),
    label: r.display_name.split(',').slice(0, 2).join(','),
    kind: 'place',
  };
}

export function geolocate() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation is not available in this browser.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        label: 'Your location',
        kind: 'geoloc',
      }),
      (err) => reject(new Error(err.message || 'Could not get your location.')),
      { timeout: 8000, maximumAge: 60000 }
    );
  });
}

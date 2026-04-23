// map.js — Leaflet map with status-coloured markers. Thin wrapper that
// hides Leaflet's defaults so the rest of the code speaks in domain terms.

let map = null;
const markers = new Map(); // id -> { marker, el, building }
let meMarker = null;
let onMarkerClick = () => {};

export function initMap(elId) {
  const L = window.L;
  map = L.map(elId, {
    center: [54.5, -3.5], // UK-ish centroid
    zoom: 6,
    minZoom: 5,
    maxZoom: 17,
    zoomControl: true,
    attributionControl: true,
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  return map;
}

function markerIcon(status) {
  const L = window.L;
  const el = document.createElement('div');
  el.className = `chmark status-${status}`;
  return { element: el, icon: L.divIcon({
    className: '',
    html: el.outerHTML,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  })};
}

export function addBuildings(buildings) {
  const L = window.L;
  buildings.forEach((b) => {
    const { icon } = markerIcon(b.status);
    const marker = L.marker([b.lat, b.lon], { icon, title: b.name }).addTo(map);
    marker.on('click', () => onMarkerClick(b));
    markers.set(b.id, { marker, building: b });
  });
}

export function setClickHandler(fn) {
  onMarkerClick = fn;
}

export function highlight(id) {
  markers.forEach((m, mid) => {
    const el = m.marker.getElement();
    if (!el) return;
    const dot = el.querySelector('.chmark');
    if (dot) dot.classList.toggle('is-active', mid === id);
  });
}

// Show only the markers whose status is in `visibleStatuses`.
export function filterByStatus(visibleStatuses) {
  markers.forEach((m) => {
    const shouldShow = visibleStatuses.has(m.building.status);
    const isOnMap = map.hasLayer(m.marker);
    if (shouldShow && !isOnMap) m.marker.addTo(map);
    else if (!shouldShow && isOnMap) map.removeLayer(m.marker);
  });
}

export function flyToBuilding(id, zoom = 14) {
  const m = markers.get(id);
  if (!m) return;
  const b = m.building;
  map.flyTo([b.lat, b.lon], zoom, { duration: 1.1 });
}

export function framePoints(points, padding = 80) {
  const L = window.L;
  if (!points.length) return;
  if (points.length === 1) {
    map.flyTo([points[0].lat, points[0].lon], 11, { duration: 1.1 });
    return;
  }
  const bounds = L.latLngBounds(points.map((p) => [p.lat, p.lon]));
  map.flyToBounds(bounds, { padding: [padding, padding], duration: 1.1, maxZoom: 12 });
}

export function setMe(lat, lon) {
  const L = window.L;
  if (meMarker) meMarker.remove();
  const el = document.createElement('div');
  el.className = 'chmark-me';
  meMarker = L.marker([lat, lon], {
    icon: L.divIcon({
      className: '',
      html: el.outerHTML,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    }),
    interactive: false,
    keyboard: false,
  }).addTo(map);
}

export function clearMe() {
  if (meMarker) { meMarker.remove(); meMarker = null; }
}

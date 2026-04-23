// map.js — Leaflet + markercluster wrapper. Hides the library details so
// the rest of the app speaks in domain terms (buildings, statuses, click
// handlers) rather than panes and layers.

let map = null;
let cluster = null;               // L.markerClusterGroup holding all markers
const markers = new Map();        // id -> { marker, building }
let meMarker = null;
let onMarkerClick = () => {};

export function initMap(elId) {
  const L = window.L;
  map = L.map(elId, {
    center: [54.5, -3.5],
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

  // Cluster group sits above the tile layer. Cluster icons take their
  // styling from CSS (see styles.css: .marker-cluster-*) so they feel
  // like the rest of the register rather than Leaflet's default blue.
  cluster = L.markerClusterGroup({
    maxClusterRadius: 50,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
    disableClusteringAtZoom: 13,
    iconCreateFunction: (c) => {
      const n = c.getChildCount();
      const size = n < 10 ? 'sm' : n < 100 ? 'md' : 'lg';
      return L.divIcon({
        html: `<div class="cluster cluster-${size}"><span>${n}</span></div>`,
        className: '',
        iconSize: [40, 40],
      });
    },
  });
  map.addLayer(cluster);
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
  const layers = [];
  buildings.forEach((b) => {
    const { icon } = markerIcon(b.status);
    const marker = L.marker([b.lat, b.lon], { icon, title: b.name });
    marker.on('click', () => onMarkerClick(b));
    markers.set(b.id, { marker, building: b });
    layers.push(marker);
  });
  cluster.addLayers(layers);
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

// Show only the markers whose status is in `visibleStatuses`. With
// clustering we add/remove from the cluster group rather than the map
// itself so the cluster counts update as the filter changes.
export function filterByStatus(visibleStatuses) {
  const toAdd = [];
  const toRemove = [];
  markers.forEach((m) => {
    const shouldShow = visibleStatuses.has(m.building.status);
    const isOnCluster = cluster.hasLayer(m.marker);
    if (shouldShow && !isOnCluster) toAdd.push(m.marker);
    else if (!shouldShow && isOnCluster) toRemove.push(m.marker);
  });
  if (toRemove.length) cluster.removeLayers(toRemove);
  if (toAdd.length) cluster.addLayers(toAdd);
}

export function flyToBuilding(id, zoom = 14) {
  const m = markers.get(id);
  if (!m) return;
  const b = m.building;
  // If the marker is inside a cluster, ask markercluster to expand it.
  // Otherwise a plain flyTo is fine.
  if (cluster && typeof cluster.zoomToShowLayer === 'function') {
    cluster.zoomToShowLayer(m.marker, () => {
      map.flyTo([b.lat, b.lon], Math.max(zoom, map.getZoom()), { duration: 0.8 });
    });
  } else {
    map.flyTo([b.lat, b.lon], zoom, { duration: 1.1 });
  }
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

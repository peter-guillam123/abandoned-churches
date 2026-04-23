// main.js — wires the page together.

import { loadBuildings, nearestTo, formatDistance, STATUS_LABELS, placeLabel } from './data.js';
import { resolve as resolveLocation, geolocate } from './search.js';
import { initMap, addBuildings, setClickHandler, highlight, flyToBuilding, framePoints, setMe, clearMe, filterByStatus } from './map.js';
import { render as renderDetail } from './detail.js';

const state = {
  buildings: [],
  visibleStatuses: new Set(['at-risk', 'rescued', 'preserved', 'repurposed', 'closed', 'demolished']),
  mode: 'overview', // 'overview' | 'located'
  origin: null,     // { lat, lon, label } when the user has located themselves
};

const el = {
  statBig: document.getElementById('stat-big'),
  statSub: document.getElementById('stat-sub'),
  form: document.getElementById('find-form'),
  q: document.getElementById('q'),
  clearBtn: document.getElementById('clear-btn'),
  geolocBtn: document.getElementById('geoloc-btn'),
  headTitle: document.getElementById('head-title'),
  headMeta: document.getElementById('head-meta'),
  readingEyebrow: document.getElementById('reading-eyebrow'),
  idleState: document.getElementById('idle-state'),
  resultList: document.getElementById('result-list'),
  detail: document.getElementById('detail'),
  legend: document.getElementById('status-legend'),
  submitModal: document.getElementById('submit-modal'),
  submitClose: document.getElementById('submit-close'),
  submitForm: document.getElementById('submit-form'),
  submitIntro: document.getElementById('submit-intro'),
  submitSent: document.getElementById('submit-sent'),
  submitMemory: document.getElementById('submit-memory'),
  submitName: document.getElementById('submit-name'),
  submitEmail: document.getElementById('submit-email'),
};

function visibleBuildings() {
  return state.buildings.filter((b) => state.visibleStatuses.has(b.status));
}

function renderResultList(list, { showDistance, totalCount }) {
  if (!list.length) {
    el.resultList.innerHTML = '';
    el.idleState.textContent = 'No buildings match these filters. Toggle a status on the left to bring them back.';
    el.idleState.hidden = false;
    return;
  }
  el.idleState.hidden = true;
  const hint = (totalCount && totalCount > list.length)
    ? `<li class="result-hint">Showing ${list.length} of ${totalCount.toLocaleString()} — type a postcode to find the ones nearest you.</li>`
    : '';
  el.resultList.innerHTML = hint + list.map((b) => {
    const color = `var(--status-${b.status})`;
    return `
      <li class="result" data-id="${b.id}">
        <span class="dot" style="background:${color}"></span>
        <span>
          <span class="result-name">${b.name}</span>
          <span class="result-place">${placeLabel(b)}</span>
          <span class="result-status">${STATUS_LABELS[b.status] || b.status}</span>
        </span>
        ${showDistance ? `<span class="result-dist">${formatDistance(b.distanceKm)}</span>` : ''}
      </li>
    `;
  }).join('');

  el.resultList.querySelectorAll('.result').forEach((row) => {
    row.addEventListener('mouseenter', () => highlight(row.dataset.id));
    row.addEventListener('mouseleave', () => highlight(null));
    row.addEventListener('click', () => selectBuilding(row.dataset.id, { fly: true }));
  });
}

function selectBuilding(id, opts = {}) {
  const b = state.buildings.find((x) => x.id === id);
  if (!b) return;
  highlight(id);
  renderDetail(el.detail, b);
  if (opts.fly) flyToBuilding(id, 14);
  // Smooth-scroll the reader down to the detail panel.
  requestAnimationFrame(() => {
    el.detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function refreshLegendCounts() {
  const counts = {};
  state.buildings.forEach((b) => { counts[b.status] = (counts[b.status] || 0) + 1; });
  el.legend.querySelectorAll('[data-count]').forEach((n) => {
    n.textContent = counts[n.dataset.count] || 0;
  });
  el.statBig.textContent = state.buildings.length;
}

function wireLegend() {
  el.legend.querySelectorAll('li').forEach((li) => {
    li.addEventListener('click', () => {
      const s = li.dataset.status;
      if (state.visibleStatuses.has(s)) state.visibleStatuses.delete(s);
      else state.visibleStatuses.add(s);
      li.classList.toggle('muted', !state.visibleStatuses.has(s));
      rerender();
    });
  });
}

const OVERVIEW_LIST_CAP = 30;

function rerender() {
  filterByStatus(state.visibleStatuses);
  const list = visibleBuildings();
  if (state.mode === 'located' && state.origin) {
    const withDist = list
      .map((b) => ({ ...b, distanceKm: haversine(state.origin, b) }))
      .sort((a, b) => a.distanceKm - b.distanceKm)
      .slice(0, 8);
    renderResultList(withDist, { showDistance: true });
  } else {
    // In overview mode the register can be thousands of entries — a full
    // list would be a scrolling forever. Cap with a "showing N of M" hint.
    const capped = list.slice(0, OVERVIEW_LIST_CAP);
    renderResultList(capped, { showDistance: false, totalCount: list.length });
  }
}

function haversine(origin, b) {
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - origin.lat);
  const dLon = toRad(b.lon - origin.lon);
  const lat1 = toRad(origin.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

async function handleFind(query) {
  el.q.disabled = true;
  try {
    const loc = await resolveLocation(query);
    applyOrigin(loc);
  } catch (err) {
    el.idleState.hidden = false;
    el.idleState.innerHTML = `<em>${err.message}</em>`;
  } finally {
    el.q.disabled = false;
  }
}

async function handleGeolocate() {
  el.geolocBtn.disabled = true;
  try {
    const loc = await geolocate();
    applyOrigin(loc);
  } catch (err) {
    el.idleState.hidden = false;
    el.idleState.innerHTML = `<em>${err.message}</em>`;
  } finally {
    el.geolocBtn.disabled = false;
  }
}

function applyOrigin(loc) {
  state.mode = 'located';
  state.origin = loc;
  setMe(loc.lat, loc.lon);
  const nearest = nearestTo(loc.lat, loc.lon, visibleBuildings(), 8);
  framePoints([loc, ...nearest.slice(0, 3)], 80);
  el.headTitle.textContent = `The closest ${nearest.length} to ${loc.label}`;
  // Empty state gets wiped so the list renders below it.
  el.idleState.hidden = true;
  el.readingEyebrow.textContent = `Near ${loc.label}`;
  renderResultList(nearest, { showDistance: true });
}

function resetOverview() {
  state.mode = 'overview';
  state.origin = null;
  clearMe();
  framePoints(state.buildings, 60);
  el.q.value = '';
  el.headTitle.textContent = 'Six buildings to start — six stories';
  el.readingEyebrow.textContent = 'The six seeded buildings';
  el.idleState.hidden = true;
  rerender();
  renderDetail(el.detail, null);
}

function openSubmitModal(buildingId, buildingName) {
  el.submitIntro.textContent = buildingName
    ? `About ${buildingName}. Tell us what you remember.`
    : 'Tell us about this church.';
  el.submitModal.dataset.for = buildingId || '';
  el.submitSent.hidden = true;
  el.submitForm.reset();
  el.submitModal.classList.add('is-open');
  setTimeout(() => el.submitMemory.focus(), 50);
}

function closeSubmitModal() {
  el.submitModal.classList.remove('is-open');
}

function wireSubmit() {
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.open-submit');
    if (btn) openSubmitModal(btn.dataset.building, btn.dataset.buildingName);
  });
  el.submitClose.addEventListener('click', closeSubmitModal);
  el.submitModal.addEventListener('click', (e) => {
    if (e.target === el.submitModal) closeSubmitModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && el.submitModal.classList.contains('is-open')) closeSubmitModal();
  });
  el.submitForm.addEventListener('submit', (e) => {
    e.preventDefault();
    // Prototype: we don't POST anywhere. Persist locally so the UI feels
    // real and so an editor can eyeball what readers would have sent.
    const payload = {
      building: el.submitModal.dataset.for || null,
      memory: el.submitMemory.value.trim(),
      name: el.submitName.value.trim(),
      email: el.submitEmail.value.trim(),
      at: new Date().toISOString(),
    };
    const queue = JSON.parse(localStorage.getItem('friendless-submissions') || '[]');
    queue.push(payload);
    localStorage.setItem('friendless-submissions', JSON.stringify(queue));
    el.submitSent.hidden = false;
    setTimeout(closeSubmitModal, 1400);
  });
}

async function boot() {
  window.__bootStart = Date.now();
  const { buildings, meta } = await loadBuildings();
  window.__bootLoaded = Date.now();
  state.buildings = buildings;
  if (meta?.updated) el.statSub.textContent = `prototype · updated ${meta.updated}`;
  refreshLegendCounts();

  // Wait for Leaflet core AND the markercluster plugin to load.
  await new Promise((r) => {
    const check = () => {
      if (window.L && window.L.markerClusterGroup) r();
      else setTimeout(check, 50);
    };
    if (window.L && window.L.markerClusterGroup) r();
    else window.addEventListener('load', check, { once: true });
  });
  window.__bootLeafletReady = Date.now();

  initMap('map');
  window.__bootInitMapDone = Date.now();
  addBuildings(state.buildings);
  window.__bootAddBuildingsDone = Date.now();
  setClickHandler((b) => selectBuilding(b.id, { fly: true }));
  framePoints(state.buildings, 60);

  rerender();
  wireLegend();
  wireSubmit();

  el.form.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = el.q.value.trim();
    if (!q) return;
    handleFind(q);
  });
  el.clearBtn.addEventListener('click', resetOverview);
  el.geolocBtn.addEventListener('click', handleGeolocate);
}

boot().catch((err) => {
  console.error(err);
  el.idleState.hidden = false;
  el.idleState.innerHTML = `<em>${err.message}</em>`;
});

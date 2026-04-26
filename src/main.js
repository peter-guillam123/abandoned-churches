// main.js — wires the page together.

import { loadBuildings, nearestTo, formatDistance, STATUS_LABELS, placeLabel } from './data.js';
import { resolve as resolveLocation, geolocate } from './search.js';
import { initMap, addBuildings, setClickHandler, highlight, flyToBuilding, framePoints, setMe, clearMe, applyFilters } from './map.js';
import { render as renderDetail } from './detail.js';

// ---- State ----------------------------------------------------------------
//
// All UI is a function of this object. Anything that changes the visible
// register goes through `rerender()` so the map markers, the right-panel
// list and any inline counts stay in sync.

const state = {
  buildings: [],
  selectedStatus: null,        // null = all visible. Otherwise a single status string.
  selectedDenomination: null,  // null = all. Otherwise a canonical denomination.
  selectedPeriod: null,        // null = all. Otherwise an era bucket from fabric.era.
  nameQuery: '',               // debounced free-text filter against name + place
  mode: 'overview',            // 'overview' | 'located'
  origin: null,                // { lat, lon, label } when located
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
  denomChips: document.getElementById('denom-chips'),
  periodChips: document.getElementById('period-chips'),
  activeFilters: document.getElementById('active-filters'),
  submitModal: document.getElementById('submit-modal'),
  submitClose: document.getElementById('submit-close'),
  submitForm: document.getElementById('submit-form'),
  submitIntro: document.getElementById('submit-intro'),
  submitSent: document.getElementById('submit-sent'),
  submitMemory: document.getElementById('submit-memory'),
  submitName: document.getElementById('submit-name'),
  submitEmail: document.getElementById('submit-email'),
};

// Hand-curated records are the editorial spine — six buildings drawn
// from the reporting series. They live in buildings.hand.json and are
// preserved through the merger; their ids don't carry a fetch-source
// prefix.
function isHandCurated(b) {
  const p = b.id || '';
  return !(p.startsWith('fofc-') || p.startsWith('cct-') || p.startsWith('har-'));
}

// ---- Filtering -----------------------------------------------------------

function matchesNameQuery(b, q) {
  if (!q) return true;
  const hay = `${b.name || ''} ${(b.place && (b.place.settlement || '') + ' ' + (b.place.region || '')) || ''} ${(b.denomination && b.denomination.current) || ''}`.toLowerCase();
  // Token-AND: every term in the query must match somewhere in the haystack.
  return q.toLowerCase().split(/\s+/).filter(Boolean).every((t) => hay.includes(t));
}

function passesFilters(b) {
  if (state.selectedStatus && b.status !== state.selectedStatus) return false;
  if (state.selectedDenomination) {
    const d = (b.denomination && b.denomination.current) || null;
    if (d !== state.selectedDenomination) return false;
  }
  if (state.selectedPeriod) {
    const era = (b.fabric && b.fabric.era) || null;
    if (era !== state.selectedPeriod) return false;
  }
  if (!matchesNameQuery(b, state.nameQuery)) return false;
  return true;
}

function visibleBuildings() {
  return state.buildings.filter(passesFilters);
}

// ---- Result list rendering ----------------------------------------------

function renderResultList(list, { showDistance, totalCount, eyebrow }) {
  if (eyebrow !== undefined) el.readingEyebrow.textContent = eyebrow;
  if (!list.length) {
    el.resultList.innerHTML = '';
    el.idleState.innerHTML = `<em>No buildings match that combination of filters.</em> Clear a chip — or the search — to widen the register.`;
    el.idleState.hidden = false;
    return;
  }
  el.idleState.hidden = true;
  const hint = (totalCount && totalCount > list.length)
    ? `<li class="result-hint">${list.length} of ${totalCount.toLocaleString()} shown — use the chips or the postcode field to narrow.</li>`
    : '';
  el.resultList.innerHTML = hint + list.map((b) => {
    const color = `var(--status-${b.status})`;
    const denom = (b.denomination && b.denomination.current) || '';
    const era = (b.fabric && b.fabric.era) || '';
    const place = placeLabel(b);
    const placeLine = [place, denom, era].filter(Boolean).join(' · ');
    return `
      <li class="result" data-id="${b.id}">
        <span class="dot" style="background:${color}"></span>
        <span>
          <span class="result-name">${b.name}</span>
          ${placeLine ? `<span class="result-place">${placeLine}</span>` : ''}
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
  requestAnimationFrame(() => {
    el.detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

// ---- Status chips --------------------------------------------------------
//
// Click a status to filter TO that status. Click again to clear.
// Default state has no chip selected = all visible.

function refreshLegendCounts() {
  const counts = {};
  state.buildings.forEach((b) => { counts[b.status] = (counts[b.status] || 0) + 1; });
  el.legend.querySelectorAll('[data-count]').forEach((n) => {
    n.textContent = counts[n.dataset.count] || 0;
  });
  el.statBig.textContent = state.buildings.length.toLocaleString();
}

function refreshStatusChipState() {
  el.legend.querySelectorAll('li').forEach((li) => {
    li.classList.toggle('chip-on', li.dataset.status === state.selectedStatus);
    li.setAttribute('aria-pressed', String(li.dataset.status === state.selectedStatus));
  });
}

function wireStatusChips() {
  el.legend.querySelectorAll('li').forEach((li) => {
    li.setAttribute('role', 'button');
    li.setAttribute('tabindex', '0');
    li.setAttribute('aria-pressed', 'false');
    const click = () => {
      const s = li.dataset.status;
      state.selectedStatus = state.selectedStatus === s ? null : s;
      refreshStatusChipState();
      rerender();
    };
    li.addEventListener('click', click);
    li.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); click(); }
    });
  });
}

// ---- Denomination chips --------------------------------------------------

const DENOM_PRIORITY = [
  'Church of England',
  'Church in Wales',
  'Roman Catholic',
  'Methodist',
  'Baptist',
  'Quaker',
  'Congregational',
  'United Reformed',
  'Unitarian',
  'Presbyterian',
  'Nonconformist',
  'Muslim',
];

function renderDenominationChips() {
  const counts = {};
  state.buildings.forEach((b) => {
    const d = (b.denomination && b.denomination.current) || null;
    if (!d) return;
    counts[d] = (counts[d] || 0) + 1;
  });
  // Stable order: priority list first, then any others alphabetically.
  const seen = new Set();
  const ordered = [];
  DENOM_PRIORITY.forEach((d) => { if (counts[d]) { ordered.push(d); seen.add(d); } });
  Object.keys(counts).sort().forEach((d) => { if (!seen.has(d)) ordered.push(d); });

  el.denomChips.innerHTML = ordered.map((d) => `
    <li role="button" tabindex="0" data-denom="${d}" aria-pressed="false">
      <span class="dlabel">${d}</span>
      <span class="dcount">${counts[d].toLocaleString()}</span>
    </li>
  `).join('');

  el.denomChips.querySelectorAll('li').forEach((li) => {
    const click = () => {
      const d = li.dataset.denom;
      state.selectedDenomination = state.selectedDenomination === d ? null : d;
      refreshDenominationChipState();
      rerender();
    };
    li.addEventListener('click', click);
    li.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); click(); }
    });
  });
}

function refreshDenominationChipState() {
  el.denomChips.querySelectorAll('li').forEach((li) => {
    li.classList.toggle('chip-on', li.dataset.denom === state.selectedDenomination);
    li.setAttribute('aria-pressed', String(li.dataset.denom === state.selectedDenomination));
  });
}

// ---- Period chips -------------------------------------------------------
//
// Era buckets come straight from the data — fabric.era is one of the
// canonical strings emitted by infer_period in build_register.py.

const PERIOD_ORDER = [
  'Pre-Conquest',
  'Norman',
  'Medieval',
  'Tudor & Stuart',
  'Georgian',
  'Victorian',
  '20th century onwards',
];

function renderPeriodChips() {
  const counts = {};
  state.buildings.forEach((b) => {
    const era = (b.fabric && b.fabric.era) || null;
    if (!era) return;
    counts[era] = (counts[era] || 0) + 1;
  });
  const ordered = PERIOD_ORDER.filter((p) => counts[p]);

  el.periodChips.innerHTML = ordered.map((p) => `
    <li role="button" tabindex="0" data-period="${p}" aria-pressed="false">
      <span class="dlabel">${p}</span>
      <span class="dcount">${counts[p].toLocaleString()}</span>
    </li>
  `).join('');

  el.periodChips.querySelectorAll('li').forEach((li) => {
    const click = () => {
      const p = li.dataset.period;
      state.selectedPeriod = state.selectedPeriod === p ? null : p;
      refreshPeriodChipState();
      rerender();
    };
    li.addEventListener('click', click);
    li.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); click(); }
    });
  });
}

function refreshPeriodChipState() {
  el.periodChips.querySelectorAll('li').forEach((li) => {
    li.classList.toggle('chip-on', li.dataset.period === state.selectedPeriod);
    li.setAttribute('aria-pressed', String(li.dataset.period === state.selectedPeriod));
  });
}

// ---- Active-filters bar -------------------------------------------------
//
// Lozenges above the result list — one per active filter — each with
// a dismiss × that clears that single filter. When two or more are
// on, an extra "Clear all" pill clears the lot. The bar hides itself
// when nothing's active so it doesn't take up space in the idle state.

function renderActiveFilters() {
  const lozenges = [];

  if (state.mode === 'located' && state.origin) {
    lozenges.push({
      kind: 'origin',
      label: state.origin.label,
      eyebrow: 'near',
      action: () => resetOverview(),
    });
  }
  if (state.nameQuery) {
    lozenges.push({
      kind: 'name',
      label: `“${state.nameQuery}”`,
      eyebrow: 'search',
      action: () => {
        state.nameQuery = '';
        el.q.value = '';
        rerender();
      },
    });
  }
  if (state.selectedStatus) {
    lozenges.push({
      kind: 'status',
      label: STATUS_LABELS[state.selectedStatus] || state.selectedStatus,
      eyebrow: 'status',
      action: () => {
        state.selectedStatus = null;
        refreshStatusChipState();
        rerender();
      },
    });
  }
  if (state.selectedDenomination) {
    lozenges.push({
      kind: 'denom',
      label: state.selectedDenomination,
      eyebrow: 'denomination',
      action: () => {
        state.selectedDenomination = null;
        refreshDenominationChipState();
        rerender();
      },
    });
  }
  if (state.selectedPeriod) {
    lozenges.push({
      kind: 'period',
      label: state.selectedPeriod,
      eyebrow: 'period',
      action: () => {
        state.selectedPeriod = null;
        refreshPeriodChipState();
        rerender();
      },
    });
  }

  if (!lozenges.length) {
    el.activeFilters.hidden = true;
    el.activeFilters.innerHTML = '';
    return;
  }
  el.activeFilters.hidden = false;
  const showClearAll = lozenges.length >= 2;
  el.activeFilters.innerHTML = lozenges.map((l, i) => `
    <button type="button" class="lozenge lozenge-${l.kind}" data-i="${i}" aria-label="Remove ${l.eyebrow} filter ${l.label}">
      <span class="lozenge-eyebrow">${l.eyebrow}</span>
      <span class="lozenge-label">${l.label}</span>
      <span class="lozenge-x" aria-hidden="true">×</span>
    </button>
  `).join('') + (showClearAll
    ? `<button type="button" class="lozenge lozenge-clear-all" id="clear-all-filters" aria-label="Clear all filters">Clear all</button>`
    : '');

  el.activeFilters.querySelectorAll('button[data-i]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.i, 10);
      lozenges[idx].action();
    });
  });
  const clearAll = document.getElementById('clear-all-filters');
  if (clearAll) {
    clearAll.addEventListener('click', () => {
      state.selectedStatus = null;
      state.selectedDenomination = null;
      state.selectedPeriod = null;
      state.nameQuery = '';
      state.mode = 'overview';
      state.origin = null;
      el.q.value = '';
      clearMe();
      framePoints(state.buildings, 60);
      refreshStatusChipState();
      refreshDenominationChipState();
      refreshPeriodChipState();
      rerender();
    });
  }
}

// ---- Main rerender -------------------------------------------------------
//
// Curated state: in overview mode with no filters and no search, show
// the six hand-curated portraits as a "from the reporting" panel.
// Filtered state: show up to 12 matching results with a "showing N of M"
// hint. Located state: show nearest 8.

function rerender() {
  applyFilters(passesFilters);
  renderActiveFilters();

  const list = visibleBuildings();
  const hasFilters = state.selectedStatus || state.selectedDenomination || state.selectedPeriod || state.nameQuery;

  if (state.mode === 'located' && state.origin) {
    const withDist = list
      .map((b) => ({ ...b, distanceKm: haversine(state.origin, b) }))
      .sort((a, b) => a.distanceKm - b.distanceKm)
      .slice(0, 8);
    renderResultList(withDist, {
      showDistance: true,
      eyebrow: `Near ${state.origin.label}`,
    });
    return;
  }

  if (!hasFilters) {
    // Curated highlights — hand-curated records first, in the order
    // they appear in buildings.hand.json. These are the editorial
    // anchor points for new readers.
    const curated = state.buildings.filter(isHandCurated);
    renderResultList(curated, {
      showDistance: false,
      totalCount: state.buildings.length,
      eyebrow: 'From the reporting',
    });
    return;
  }

  // Filtered overview — cap to keep the column compact. The map shows
  // the rest of the matches as cluster bubbles.
  const cap = 12;
  renderResultList(list.slice(0, cap), {
    showDistance: false,
    totalCount: list.length,
    eyebrow: 'Filter results',
  });
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

// ---- Search input --------------------------------------------------------
//
// One field, two behaviours.
//   - On every keystroke (debounced) → filter the visible register by
//     name / place / denomination text-match.
//   - On submit (Enter or Find button) → if the text looks like a
//     postcode or recognisable place, fly to nearest. Otherwise, the
//     debounced filter is what the reader was after; do nothing more.

let searchDebounce = null;

function onSearchInput() {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    state.nameQuery = el.q.value.trim();
    rerender();
  }, 180);
}

async function handleFind(query) {
  // First try postcode/place lookup. If that fails, the typed query is
  // probably a name search — fall back gracefully.
  el.q.disabled = true;
  try {
    const loc = await resolveLocation(query);
    applyOrigin(loc);
  } catch (err) {
    // Couldn't resolve as a location — keep filtering by name. If
    // there are no matches, surface the error.
    state.nameQuery = query.trim();
    rerender();
    if (!visibleBuildings().length) {
      el.idleState.hidden = false;
      el.idleState.innerHTML = `<em>No buildings match "${query}".</em> Try a postcode (LL71 8AG), a place (Hackney), or part of a name (St Mary's).`;
    }
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
  el.idleState.hidden = true;
  rerender();
}

function resetOverview() {
  state.mode = 'overview';
  state.origin = null;
  state.selectedStatus = null;
  state.selectedDenomination = null;
  state.selectedPeriod = null;
  state.nameQuery = '';
  clearMe();
  framePoints(state.buildings, 60);
  el.q.value = '';
  el.headTitle.textContent = "The register — a map of what's closing, falling down and being saved";
  el.idleState.hidden = true;
  refreshStatusChipState();
  refreshDenominationChipState();
  refreshPeriodChipState();
  rerender();
  renderDetail(el.detail, null);
}

// ---- Submission modal ----------------------------------------------------

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

// On mobile the filter drawer should start collapsed so the map sits
// near the top of the column. On desktop it stays open. We watch a
// matchMedia listener so a screen-rotation or window-resize doesn't
// strand the user with the drawer in the wrong default state.
// On mobile the filter drawer should start collapsed so the map sits
// near the top of the column. The HTML always carries `open` so
// desktop is correct without JS; we strip it once at boot when the
// viewport is narrow.
function wireFilterDrawer() {
  const drawer = document.querySelector('.filter-drawer');
  window.__drawerWired = true;
  if (!drawer) return;
  if (window.matchMedia('(max-width: 960px)').matches) {
    drawer.removeAttribute('open');
  }
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
    const payload = {
      building: el.submitModal.dataset.for || null,
      memory: el.submitMemory.value.trim(),
      name: el.submitName.value.trim(),
      email: el.submitEmail.value.trim(),
      at: new Date().toISOString(),
    };
    const queue = JSON.parse(localStorage.getItem('church-and-state-submissions') || '[]');
    queue.push(payload);
    localStorage.setItem('church-and-state-submissions', JSON.stringify(queue));
    el.submitSent.hidden = false;
    setTimeout(closeSubmitModal, 1400);
  });
}

// ---- Boot ----------------------------------------------------------------

async function boot() {
  const { buildings, meta } = await loadBuildings();
  state.buildings = buildings;
  if (meta?.updated) {
    el.statSub.textContent = `register · updated ${meta.updated}`;
    if (el.headMeta) el.headMeta.textContent = `Register · updated ${meta.updated}`;
  }
  refreshLegendCounts();
  renderDenominationChips();
  renderPeriodChips();

  await new Promise((r) => {
    const check = () => {
      if (window.L && window.L.markerClusterGroup) r();
      else setTimeout(check, 50);
    };
    check();
  });

  initMap('map');
  addBuildings(state.buildings);
  setClickHandler((b) => selectBuilding(b.id, { fly: true }));
  framePoints(state.buildings, 60);

  rerender();
  wireStatusChips();
  wireSubmit();
  wireFilterDrawer();

  el.q.addEventListener('input', onSearchInput);
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

// detail.js — renders the long-form building page beneath the map.
// Every section is optional: if the corresponding slot in the record is
// null or empty, the section is omitted. Panels are independent so the
// same template renders the richly-sourced St Tyfrydog's entry and the
// sparse records that don't yet have a listing description to show.

import { STATUS_LABELS, placeLabel, denominationLabel } from './data.js';

const STATUS_COLORS = {
  'at-risk': 'var(--status-at-risk)',
  rescued: 'var(--status-rescued)',
  preserved: 'var(--status-preserved)',
  repurposed: 'var(--status-repurposed)',
  closed: 'var(--status-closed)',
  demolished: 'var(--status-demolished)',
};

// SVG fallback for when we haven't seeded real photography yet. Seeded
// by building id so each sparse entry gets a consistent silhouette.
function silhouetteSvg(building) {
  const seed = [...building.id].reduce((a, c) => a + c.charCodeAt(0), 0);
  const towerLean = (seed % 5) - 2;
  const crossY = 6 + (seed % 3);
  const ivy = (seed % 3) === 0;
  return `
    <svg viewBox="0 0 400 420" preserveAspectRatio="xMidYMax meet" role="img" aria-hidden="true">
      <defs>
        <pattern id="grainbg-${building.id}" width="2" height="2" patternUnits="userSpaceOnUse">
          <rect width="2" height="2" fill="#E8DFD0"/>
          <circle cx="1" cy="1" r="0.25" fill="#121212" opacity="0.08"/>
        </pattern>
      </defs>
      <rect width="400" height="420" fill="url(#grainbg-${building.id})"/>
      <path d="M0 330 Q 110 315 200 320 T 400 328 L 400 420 L 0 420 Z" fill="#D0C4AE" opacity="0.6"/>
      <g opacity="0.55" fill="#5f5c55">
        <ellipse cx="58" cy="300" rx="44" ry="56"/>
        <ellipse cx="342" cy="305" rx="52" ry="62"/>
      </g>
      <path d="M 20 345 Q 200 320 380 345" fill="none" stroke="#3d3a35" stroke-width="3"/>
      <rect x="130" y="220" width="200" height="110" fill="#B47D2C" opacity="0.9"/>
      <polygon points="130,220 230,170 330,220" fill="#3d3a35"/>
      <g transform="translate(110 150) rotate(${towerLean} 30 95)">
        <rect x="0" y="0" width="60" height="180" fill="#B47D2C"/>
        <rect x="0" y="0" width="60" height="180" fill="none" stroke="#3d3a35" stroke-width="2"/>
        <rect x="22" y="35" width="16" height="32" fill="#3d3a35"/>
        <rect x="22" y="92" width="16" height="26" fill="#3d3a35" opacity="0.75"/>
        <path d="M -4 0 L 30 -34 L 64 0 Z" fill="#3d3a35"/>
        <line x1="30" y1="-34" x2="30" y2="-${34 + crossY + 10}" stroke="#121212" stroke-width="2"/>
        <line x1="${30 - 5}" y1="-${34 + crossY + 4}" x2="${30 + 5}" y2="-${34 + crossY + 4}" stroke="#121212" stroke-width="2"/>
      </g>
      <rect x="160" y="255" width="30" height="50" fill="#3d3a35" opacity="0.8"/>
      <rect x="210" y="255" width="30" height="50" fill="#3d3a35" opacity="0.8"/>
      <rect x="260" y="255" width="30" height="50" fill="#3d3a35" opacity="0.8"/>
      <g fill="#3d3a35">
        <rect x="75" y="330" width="6" height="14" rx="3"/>
        <rect x="95" y="334" width="6" height="12" rx="3"/>
        <rect x="300" y="330" width="6" height="15" rx="3"/>
        <rect x="318" y="334" width="6" height="12" rx="3"/>
      </g>
      ${ivy ? `
        <g fill="#22874d" opacity="0.55">
          <path d="M130 330 Q 140 280 130 240 T 150 190 T 145 230"/>
          <circle cx="140" cy="260" r="6"/>
          <circle cx="135" cy="290" r="7"/>
          <circle cx="145" cy="315" r="5"/>
        </g>` : ''}
    </svg>
  `;
}

function heroSection(b) {
  const h = b.imagery?.hero;
  if (h) {
    return `
      <figure class="hero">
        <img src="${h.url}" alt="${h.caption || b.name}" loading="lazy" />
        <figcaption>
          <span class="caption">${h.caption || ''}</span>
          <span class="credit">${h.credit} / <a href="${h.sourceUrl}" target="_blank" rel="noopener">${h.source}</a> · <a href="${h.licenceUrl || '#'}" target="_blank" rel="noopener">${h.licence}</a></span>
        </figcaption>
      </figure>
    `;
  }
  return `
    <div class="hero hero-silhouette">
      ${silhouetteSvg(b)}
      <span class="hero-note">Photograph to come — the register currently carries a decorative plate for this entry.</span>
    </div>
  `;
}

function fact(key, val) {
  if (val === null || val === undefined || val === '') return '';
  return `<div class="fact"><span class="key">${key}</span><span class="val">${val}</span></div>`;
}

function factBand(b) {
  const status = b.status ? `
    <div class="fact"><span class="key">Status</span><span class="val status"><span class="dot" style="background:${STATUS_COLORS[b.status]}"></span>${STATUS_LABELS[b.status] || b.status}</span></div>
  ` : '';
  const listingVal = b.listing?.grade ? `Grade ${b.listing.grade}${b.listing.body ? ` · ${b.listing.body}` : ''}` : null;
  const custodianVal = b.custodian?.body
    ? (b.custodian.since ? `${b.custodian.body} · since ${b.custodian.since}` : b.custodian.body)
    : null;
  return `
    <div class="factline">
      ${status}
      ${fact('Listing', listingVal)}
      ${fact('Listed', b.listing?.listedOn)}
      ${fact('Custodian', custodianVal)}
      ${fact('Last service', b.lastService)}
    </div>
  `;
}

function listEntryPanel(b) {
  const bits = [];
  if (b.listing?.reason) {
    bits.push(`<p class="pull">"${b.listing.reason}"<cite>${b.listing.body || 'Listing body'} · ${b.listing.grade ? 'Grade ' + b.listing.grade : ''}${b.listing.listedOn ? ', ' + b.listing.listedOn : ''}</cite></p>`);
  }
  if (b.fabric?.materials) bits.push(`<p class="para">${b.fabric.materials}</p>`);
  if (b.fabric?.plan) bits.push(`<p class="para">${b.fabric.plan}</p>`);
  if (b.fabric?.phases?.length) {
    bits.push(`
      <ol class="timeline">
        ${b.fabric.phases.map((p) => `
          <li>
            <span class="when">${p.year}</span>
            <span class="what">${p.what}</span>
          </li>
        `).join('')}
      </ol>
    `);
  }
  if (b.listing?.associated?.length) {
    bits.push(`
      <p class="also">
        Also listed:
        ${b.listing.associated.map((a) => `<span>${a.what} (Grade ${a.grade})${a.note ? ` — ${a.note}` : ''}</span>`).join(' · ')}
      </p>
    `);
  }
  if (!bits.length) return '';
  return `
    <section class="panel">
      <p class="section-h">From the list entry</p>
      ${bits.join('')}
    </section>
  `;
}

function interiorPanel(b) {
  if (!b.interior?.features?.length) return '';
  return `
    <section class="panel">
      <p class="section-h">Inside</p>
      <ul class="features">
        ${b.interior.features.map((f) => `<li>${f}</li>`).join('')}
      </ul>
    </section>
  `;
}

function conditionPanel(b) {
  if (!b.condition?.summary && !b.condition?.plannedWorks?.length) return '';
  const works = b.condition.plannedWorks?.length
    ? `<ul class="features">${b.condition.plannedWorks.map((w) => `<li>${w}</li>`).join('')}</ul>`
    : '';
  const metaBits = [];
  if (b.condition.estimatedCost) metaBits.push(`<strong>Cost:</strong> ${b.condition.estimatedCost}`);
  if (b.condition.worksTimeline) metaBits.push(`<strong>Timeline:</strong> ${b.condition.worksTimeline}`);
  const meta = metaBits.length ? `<p class="meta-row">${metaBits.join(' · ')}</p>` : '';
  const title = works ? 'Condition and plan' : 'Condition';
  const introHeading = works ? `<p class="mini-h">What&rsquo;s happening</p>` : '';
  return `
    <section class="panel">
      <p class="section-h">${title}</p>
      ${introHeading}
      ${b.condition.summary ? `<p class="para">${b.condition.summary}</p>` : ''}
      ${works ? '<p class="mini-h">Planned works</p>' : ''}
      ${works}
      ${meta}
    </section>
  `;
}

function quotesPanel(b) {
  if (!b.quotes?.length) return '';
  return `
    <section class="panel">
      <p class="section-h">Voices</p>
      ${b.quotes.map((q) => `
        <blockquote>
          "${q.quote}"
          <cite>${q.attribution}</cite>
        </blockquote>
      `).join('')}
    </section>
  `;
}

function contextPanel(b) {
  const c = b.context || {};
  const items = [];
  if (c.lsoa?.name) items.push(['Neighbourhood', `${c.lsoa.name}${c.lsoa.code ? ` · ${c.lsoa.code}` : ''}`]);
  if (b.place?.parish) items.push(['Parish', b.place.parish]);
  if (b.place?.ward) items.push(['Ward', b.place.ward]);
  if (b.place?.constituency) items.push(['Constituency', b.place.constituency]);
  if (c.ruralUrban) items.push(['Settlement (2021)', c.ruralUrban]);
  if (c.travelToWorkArea) items.push(['Travel-to-work area', c.travelToWorkArea]);
  if (c.nationalPark) items.push(['National park', c.nationalPark]);
  if (c.deprivationDecile !== null && c.deprivationDecile !== undefined) {
    items.push(['Deprivation', `Decile ${c.deprivationDecile} · ${c.deprivationSource || ''}`]);
  } else if (c.deprivationSource) {
    items.push(['Deprivation', `<span class="tk">${c.deprivationSource}</span>`]);
  }
  if (b.nationalGridRef) items.push(['Grid ref', b.nationalGridRef]);
  if (!items.length) return '';
  return `
    <section class="panel panel-context">
      <p class="section-h">Where it sits</p>
      <dl class="context-grid">
        ${items.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}
      </dl>
    </section>
  `;
}

function coveragePanel(b) {
  const a = b.coverage?.guardian || [];
  if (!a.length) return '';
  return `
    <section class="panel">
      <p class="section-h">In the Guardian</p>
      <div class="dispatches">
        ${a.map((x) => {
          const byline = [x.author, x.photographer ? `photography ${x.photographer}` : null].filter(Boolean).join(' · ');
          const pos = x.seriesPosition ? `Dispatch ${String(x.seriesPosition).padStart(2, '0')}` : 'Dispatch';
          return `
            <a href="${x.url || '#'}" ${x.url ? 'target="_blank" rel="noopener"' : 'onclick="event.preventDefault()"'}>
              <span class="article-kicker">${pos} · ${x.date}</span>
              <span class="article-title">${x.title}</span>
              <span class="article-byline">${byline}</span>
            </a>
          `;
        }).join('')}
      </div>
    </section>
  `;
}

function peoplePanel(b) {
  if (!b.people?.length) return '';
  return `
    <section class="panel panel-people">
      <p class="section-h">People</p>
      <ul class="people">
        ${b.people.map((p) => `
          <li>
            <span class="pname">${p.name}${p.age ? `, ${p.age}` : ''}</span>
            <span class="prole">${p.role}</span>
          </li>
        `).join('')}
      </ul>
    </section>
  `;
}

export function render(el, building) {
  if (!building) { el.hidden = true; return; }
  el.hidden = false;

  const sidecarLinks = (building.sources || [])
    .map((l) => l.url
      ? `<a href="${l.url}" target="_blank" rel="noopener">${l.label}</a>`
      : `<span class="nolink">${l.label}</span>`)
    .join(' · ');

  el.innerHTML = `
    ${heroSection(building)}

    <div class="body">
      <article class="long">
        <p class="kicker">Building · ${building.place?.nation || ''}</p>
        <h2>${building.name}</h2>
        <p class="place-line">${placeLabel(building)} · ${denominationLabel(building)}</p>

        ${factBand(building)}

        ${building.summary ? `<p class="summary">${building.summary}</p>` : ''}

        ${listEntryPanel(building)}
        ${interiorPanel(building)}
        ${conditionPanel(building)}
        ${quotesPanel(building)}
        ${contextPanel(building)}
        ${peoplePanel(building)}
        ${coveragePanel(building)}
      </article>

      <aside class="sidecar">
        <div class="submit-card">
          <p class="label">Do you know this church?</p>
          <h3>Share a memory, or a photograph.</h3>
          <p>Every building in the register becomes richer when the people who remember it contribute. Nothing is published without editorial review.</p>
          <button type="button" data-building="${building.id}" data-building-name="${building.name}" class="open-submit">Add to the record</button>
        </div>

        <div class="sources">
          ${sidecarLinks || ''}
          <span class="prov">${building.provenance || ''}</span>
        </div>
      </aside>
    </div>
  `;
}

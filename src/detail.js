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

// Escape user-visible / source-text content for safe interpolation
// into HTML. Most of our copy is editor-trusted, but the NHLE listing
// descriptions are scraped from a third-party mirror and routed
// through here.
function escapeHtml(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}


function heroSection(b) {
  const h = b.imagery?.hero;
  if (!h) return '';
  // Don't repeat the source when credit already equals it (FoFC / CCT
  // own their photography). Show author + source + licence separately
  // when Commons or Geograph — those are where "Nigel Williams via
  // Geograph, CC-BY-SA 2.0" is meaningful.
  const creditEqualsSource = (h.credit || '').trim() === (h.source || '').trim();
  const sourceLink = h.sourceUrl
    ? `<a href="${h.sourceUrl}" target="_blank" rel="noopener">${h.source}</a>`
    : h.source;
  const licenceLink = h.licenceUrl
    ? `<a href="${h.licenceUrl}" target="_blank" rel="noopener">${h.licence}</a>`
    : h.licence;
  const attribution = creditEqualsSource
    ? `${sourceLink}${h.licence ? ` · ${licenceLink}` : ''}`
    : `${h.credit} / ${sourceLink}${h.licence ? ` · ${licenceLink}` : ''}`;
  return `
    <figure class="hero">
      <img src="${h.url}" alt="${h.caption || b.name}" loading="lazy" />
      <figcaption>
        <span class="caption">${h.caption || ''}</span>
        <span class="credit">${attribution}</span>
      </figcaption>
    </figure>
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
  // Period — combines the era bucket with the earliest fabric date
  // when we have one ("Medieval · c. 1330"), or just the era.
  let periodVal = null;
  const era = b.fabric?.era;
  const earliest = b.fabric?.earliestDate;
  if (era && earliest) periodVal = `${era} · c. ${earliest}`;
  else if (era) periodVal = era;
  else if (earliest) periodVal = `c. ${earliest}`;

  return `
    <div class="factline">
      ${status}
      ${fact('Listing', listingVal)}
      ${fact('Period', periodVal)}
      ${fact('Custodian', custodianVal)}
      ${fact('Last service', b.lastService)}
    </div>
  `;
}

function listEntryPanel(b) {
  const bits = [];
  if (b.listing?.reason) {
    const text = b.listing.reason;
    const cite = `${b.listing.body || 'Listing body'} · ${b.listing.grade ? 'Grade ' + b.listing.grade : ''}${b.listing.listedOn ? ', ' + b.listing.listedOn : ''}`;
    if (text.length > 400) {
      // Long NHLE-style description — preserve the original typewriter
      // formatting (line breaks, indents) and let it run as a panel.
      bits.push(`
        <div class="listing-text">
          <pre>${escapeHtml(text)}</pre>
          <cite>${cite}</cite>
        </div>
      `);
    } else {
      bits.push(`<p class="pull">"${escapeHtml(text)}"<cite>${cite}</cite></p>`);
    }
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

  // Two outbound buttons in the sidecar:
  // - Street View opens Google Maps in pano mode at the building's
  //   coords. No API key, no quota.
  // - Wikipedia link surfaces only when we have a known article via
  //   the NHLE → Wikidata join.
  const lat = building.lat;
  const lon = building.lon;
  const streetViewUrl = (lat && lon)
    ? `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}`
    : null;
  const wikipediaUrl = building.wikipediaUrl || null;
  const externalButtons = `
    <div class="external-links">
      ${streetViewUrl ? `<a class="ext-btn" href="${streetViewUrl}" target="_blank" rel="noopener" aria-label="Open Google Street View at this location">
        <span class="ext-icon" aria-hidden="true">◷</span>
        <span class="ext-label">Street view</span>
      </a>` : ''}
      ${wikipediaUrl ? `<a class="ext-btn" href="${escapeHtml(wikipediaUrl)}" target="_blank" rel="noopener" aria-label="Read this church on Wikipedia">
        <span class="ext-icon" aria-hidden="true">W</span>
        <span class="ext-label">Wikipedia</span>
      </a>` : ''}
    </div>
  `;

  el.innerHTML = `
    ${heroSection(building)}

    <div class="body">
      <article class="long">
        <p class="kicker">Building · ${building.place?.nation || ''}</p>
        <h2>${building.name}</h2>
        <p class="place-line">${[placeLabel(building), denominationLabel(building)].filter(Boolean).join(' · ')}</p>

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
        ${externalButtons}

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

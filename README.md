# Friendless

A reader's companion to The Guardian's reporting series on the UK's derelict churches, chapels and meeting houses. Type a postcode; find the one at the end of your lane; read its story.

Live at **https://peter-guillam123.github.io/abandoned-churches/** (once Pages is enabled).

## How it works

1. A suite of Python ingestion scripts in `build/` pulls from the UK's heritage registries and conservation charities: Historic England's Heritage at Risk Register, Cadw, Historic Environment Scotland, the Friends of Friendless Churches gazetteer, the Churches Conservation Trust, the National Churches Trust. Each source lives in its own script so we can run them independently when one changes.
2. Every record is geocoded / contextualised via [postcodes.io](https://postcodes.io/) to attach LSOA, parish, ward, constituency, rural-urban classification, and travel-to-work area.
3. A photo is attached per building where one exists on [Geograph](https://www.geograph.org.uk/) (CC-BY-SA 2.0). Buildings without a photo fall back to a generated silhouette.
4. `build/build_register.py` merges and deduplicates the sources into a single `data/buildings.json` that matches [`data/schema.md`](data/schema.md).
5. The frontend is vanilla HTML + ES modules + Leaflet on OpenStreetMap tiles. No build step, no bundler, no tokens. Deployed to GitHub Pages via a nightly GitHub Action.

## Design

The visual language is adapted from [Guardian Angles](https://github.com/peter-guillam123/guardian-angles) — warm parchment paper, Guardian Headline / Text Egyptian / Text Sans — with a topic-specific palette shift: **ivy** green for living decay / rescue, **rust** for weathered iron / risk. Guardian blue kept only for links and the primary CTA. The map is framed as a plate in a heritage atlas with a cartouche, compass rose, and sepia-grayscale tile treatment.

## Run locally

```bash
python3 -m http.server 8766
# open http://localhost:8766
```

No install. Fonts + Leaflet + OpenStreetMap tiles all served from CDNs.

## Ingest the data

```bash
cd build
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Each source script writes raw JSON to build/_raw/
python3 fetch_fofc.py                # 72 rescued/preserved (Friends of Friendless Churches)
python3 fetch_cct.py                 # 356 preserved (Churches Conservation Trust)
python3 fetch_heritage_at_risk.py    # 969 at-risk (Historic England, 2024 register)

# Enrich
python3 enrich_postcodes.py          # postcodes.io: LSOA / parish / ward / RUC / TTWA
python3 fetch_commons.py             # Wikimedia Commons hero photos (no key needed)
python3 fetch_geograph.py            # optional — needs GEOGRAPH_API_KEY in env

# Merge
python3 build_register.py            # writes data/buildings.json
```

`fetch_commons.py` and `enrich_postcodes.py` both checkpoint to
`build/_raw/` so a killed run can resume without repeating work.

## Files

| Path | What it does |
| --- | --- |
| `index.html` | Find one near you — map + register |
| `stories.html` | The Guardian reporting series |
| `about.html` | Status taxonomy, sources, how to contribute |
| `data/buildings.json` | The hand-curated + ingested register |
| `data/schema.md` | Schema v2 reference |
| `src/styles.css` | Parchment palette, typography, layout |
| `src/main.js` | Page orchestrator |
| `src/data.js` | Register loader + Haversine + formatters |
| `src/search.js` | Postcode → location resolver |
| `src/map.js` | Leaflet wrapper |
| `src/detail.js` | Building long-form view |
| `build/*.py` | Data ingestion scripts |
| `.github/workflows/build.yml` | Nightly rebuild + Pages deploy |

## Licence

MIT on the code. Third-party data retains its own terms — credited in the footer and on each building's page.

## Not affiliated

This is a companion to The Guardian's reporting, not an official Guardian product.

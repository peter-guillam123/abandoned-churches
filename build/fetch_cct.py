"""Scrape the Churches Conservation Trust gazetteer.

Stub — the CCT site has ~350 church pages at visitchurches.org.uk/
find-a-church/, but its index is a JS-rendered search UI so scraping
requires either (a) a headless browser or (b) reverse-engineering the
search API. Neither is in scope for the first pass.

Next step:
  - Inspect the network tab on https://www.visitchurches.org.uk/find-a-church.html
  - Find the JSON endpoint that backs the map/search and pull it here.
  - Normalise with the same shape as fetch_fofc.py.

For now this script writes an empty list so build_register.py runs."""

from __future__ import annotations

from _util import write_raw


def main():
    print("CCT ingestion is a stub — see file header for the next step.")
    write_raw("cct", [])


if __name__ == "__main__":
    main()

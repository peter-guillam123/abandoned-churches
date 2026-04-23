"""Attach a hero photograph from Geograph (CC-BY-SA 2.0) to each building.

Stub — Geograph offers a search API at
https://api.geograph.org.uk/api-facetql.php but requires a free API key
(register at https://www.geograph.org.uk/api/). Set GEOGRAPH_API_KEY
in the environment to enable.

Strategy when enabled:
  1. For each building without an imagery.hero, query the Geograph API
     by a small bounding box around (lat, lon).
  2. Pick the highest-voted photo that matches the building name.
  3. Write the result into build/_raw/geograph.json keyed by building id.

For now this script does nothing so the pipeline still runs end-to-end."""

from __future__ import annotations

import os

from _util import write_raw


def main():
    if not os.environ.get("GEOGRAPH_API_KEY"):
        print("GEOGRAPH_API_KEY not set — skipping Geograph enrichment.")
        write_raw("geograph", [])
        return
    # TODO: implement the API call and photo attachment pass
    print("Geograph ingestion not yet implemented.")
    write_raw("geograph", [])


if __name__ == "__main__":
    main()

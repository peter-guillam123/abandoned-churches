"""Pull the National Heritage List for England (NHLE) listing description
for each Heritage at Risk record we hold.

Historic England's own NHLE list-entry pages sit behind a Cloudflare
challenge that blocks server-side scraping. The third-party mirror
**British Listed Buildings** (britishlistedbuildings.co.uk) preserves
the canonical NHLE listing text verbatim (the typewriter-formatted
"Reasons for Designation" / "History" / "Details" block). It also
surfaces the Wikipedia link and Wikidata Q-number for entries that
have them, which gives us a free join into the rest of the open
heritage graph.

We GET `https://britishlistedbuildings.co.uk/{list_entry}` per record,
parse the Description block, the Wikipedia URL and the Wikidata
Q-number, and write build/_raw/_nhle.json keyed by list_entry.

Rate-limited 1.5 s/request. Caches HTML hard so a re-run only fetches
records that aren't cached.

Output shape, keyed by list_entry::

    {
      "1027914": {
        "description": "ARUNDEL  692/1/2  LONDON ROAD  ...",
        "wikipediaUrl": "https://en.wikipedia.org/wiki/St_Nicholas_Church,_Arundel",
        "wikidataId": "Q17528730",
        "blbUrl": "https://britishlistedbuildings.co.uk/101027914-church-of-st-nicholas-arundel",
        "fetchedAt": "2026-04-26"
      }, ...
    }
"""

from __future__ import annotations

import json
import re
import time
from datetime import date

from _util import RAW, RateLimiter, get

OUT_PATH = RAW / "_nhle.json"

# British Listed Buildings has its own ID space, prefixing English NHLE
# entries with `10` (so 1027914 → 101027914). The raw list_entry alone
# returns 404. Heritage at Risk only ships English entries.
def blb_url(list_entry: int | str) -> str:
    return f"https://britishlistedbuildings.co.uk/10{list_entry}"


WIKIPEDIA_RE = re.compile(r'href="(https?://en\.wikipedia\.org/wiki/[^"]+)"')
WIKIDATA_RE = re.compile(r"Wikidata\s+(Q\d+)")
DESC_START_RE = re.compile(r"<h2[^>]*>\s*Description\s*</h2>", re.I)
DESC_END_MARKERS = ("External Links", "</section>", "<h2", "Listing NGR")


def _strip_tags(s: str) -> str:
    s = re.sub(r"<br[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&#039;", "'", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"\r", "", s)
    return s


def parse_description(html: str) -> str | None:
    m = DESC_START_RE.search(html)
    if not m:
        return None
    rest = html[m.end():]
    # Trim at the first end marker we find
    cut = len(rest)
    for marker in DESC_END_MARKERS:
        i = rest.find(marker)
        if i > 0 and i < cut:
            cut = i
    body = rest[:cut]
    text = _strip_tags(body)
    # Collapse runs of internal whitespace per line, but keep paragraph breaks.
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    # Drop empty lines at top + bottom, collapse multiple blanks to one.
    out = []
    blank = False
    for ln in lines:
        if ln:
            out.append(ln)
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip() or None


def parse_wikipedia(html: str) -> str | None:
    m = WIKIPEDIA_RE.search(html)
    return m.group(1) if m else None


def parse_wikidata(html: str) -> str | None:
    m = WIKIDATA_RE.search(html)
    return m.group(1) if m else None


def main():
    har = json.loads((RAW / "heritage_at_risk.json").read_text(encoding="utf-8"))
    targets = [r for r in har if r.get("list_entry")]
    print(f"NHLE candidates: {len(targets)} HAR records with a list_entry")

    out: dict[str, dict] = {}
    if OUT_PATH.exists():
        out = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    print(f"  resuming from {len(out)} previously fetched")

    todo = [t for t in targets if str(t["list_entry"]) not in out]
    print(f"  to fetch: {len(todo)}")

    limiter = RateLimiter(min_gap=1.5)
    today = date.today().isoformat()

    for i, rec in enumerate(todo, 1):
        le = str(rec["list_entry"])
        url = blb_url(le)
        try:
            html = get(url, limiter=limiter, cache=True, suffix=".html")
        except Exception as e:
            out[le] = {"error": str(e)[:200], "fetchedAt": today}
            continue

        desc = parse_description(html)
        wiki = parse_wikipedia(html)
        wdid = parse_wikidata(html)

        out[le] = {
            "description": desc,
            "wikipediaUrl": wiki,
            "wikidataId": wdid,
            "blbUrl": url,
            "fetchedAt": today,
        }

        # Checkpoint every 25 records so a killed run is salvaged.
        if i % 25 == 0:
            OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
            matched = sum(1 for v in out.values() if v.get("description"))
            print(f"  [{i}/{len(todo)}] saved · {matched}/{len(out)} have a description")

    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    matched = sum(1 for v in out.values() if v.get("description"))
    wikis = sum(1 for v in out.values() if v.get("wikipediaUrl"))
    wikidatas = sum(1 for v in out.values() if v.get("wikidataId"))
    print(f"\nWrote {len(out)} records → build/_raw/_nhle.json")
    print(f"  with description: {matched}")
    print(f"  with Wikipedia URL: {wikis}")
    print(f"  with Wikidata id: {wikidatas}")


if __name__ == "__main__":
    main()

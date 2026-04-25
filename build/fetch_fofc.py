"""Scrape the Friends of Friendless Churches gazetteer.

The site is a WordPress build with content split across semantic
sections rather than a single article body. We target the richest
signal on each page:

  - <meta property="og:image"> — a curated hero photograph FoFC owns.
  - The H1 — always "Church name, Village, County/Region".
  - The "About <church name>" block — narrative paragraphs.
  - The "Visitor information" block — address (incl. postcode),
    OS grid reference, and a status line like "Closed for repairs"
    or "Open regularly".
  - The meta description — a one-line standfirst we use as `summary`.

Writes build/_raw/fofc.json.
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from _util import RateLimiter, get, slugify, write_raw, infer_denomination

INDEX_URL = "https://friendsoffriendlesschurches.org.uk/find-churches/"
BASE = "https://friendsoffriendlesschurches.org.uk"

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.IGNORECASE)
OSGB_RE = re.compile(r"\b([A-Z]{2}\s*\d{4,5}\s+\d{4,5})\b")

WELSH_REGIONS = {
    "anglesey", "ynys môn", "gwynedd", "conwy", "denbighshire", "flintshire",
    "wrexham", "powys", "ceredigion", "pembrokeshire", "carmarthenshire",
    "swansea", "neath port talbot", "bridgend", "vale of glamorgan", "cardiff",
    "rhondda cynon taf", "merthyr tydfil", "caerphilly", "blaenau gwent",
    "torfaen", "monmouthshire", "newport",
}


def extract_index_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.select('a[href*="/church/"]'):
        href = a.get("href", "")
        if not href:
            continue
        url = href if href.startswith("http") else BASE + href
        if "/church/" not in url:
            continue
        rows.append({"url": url})
    # Dedupe
    seen, out = set(), []
    for r in rows:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append(r)
    return out


def _split_title(title: str) -> dict:
    """'St Tyfrydog's, Llandyfrydog, Anglesey' → name + settlement + region."""
    parts = [p.strip() for p in title.split(",") if p.strip()]
    if len(parts) >= 3:
        return {"name": parts[0], "settlement": parts[1], "region": parts[-1]}
    if len(parts) == 2:
        return {"name": parts[0], "settlement": parts[1], "region": None}
    return {"name": parts[0] if parts else None, "settlement": None, "region": None}


def _plain(html_chunk: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", html_chunk)
    txt = re.sub(r"&#8217;", "'", txt)
    txt = re.sub(r"&#8216;", "'", txt)
    txt = re.sub(r"&#8220;", '"', txt)
    txt = re.sub(r"&#8221;", '"', txt)
    txt = re.sub(r"&amp;", "&", txt)
    txt = re.sub(r"&[a-z]+;", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def extract_about_block(soup: BeautifulSoup, name: str) -> str | None:
    """Find the 'About <name>' H2 and collect the following paragraphs."""
    for h2 in soup.find_all(["h2"]):
        text = h2.get_text(" ", strip=True)
        if text.lower().startswith("about"):
            paras = []
            for sib in h2.find_all_next():
                if sib.name in {"h1", "h2"} and sib is not h2:
                    break
                if sib.name == "p":
                    t = sib.get_text(" ", strip=True)
                    if len(t) > 30:
                        paras.append(t)
                if len(paras) >= 4:
                    break
            if paras:
                return "\n\n".join(paras)
    return None


def extract_visitor_info(html: str) -> dict:
    """Pull address, postcode, status, OS grid ref from the Visitor
    information block."""
    out = {"address": None, "postcode": None, "status_text": None, "osgb": None}
    # crude: take the 2kB slice after the H2 and rely on regex
    i = html.find("Visitor information")
    if i < 0:
        return out
    chunk = _plain(html[i : i + 2500])

    # OS grid reference — 'SH 44353 85343' style
    m = OSGB_RE.search(chunk)
    if m:
        out["osgb"] = m.group(1)

    # Postcode
    m = POSTCODE_RE.search(chunk)
    if m:
        out["postcode"] = re.sub(r"\s+", " ", m.group(1).upper().strip())

    # Status phrase — look for 'Closed…' or 'Open…' near the visitor block
    sm = re.search(r"(Closed for [^.]+|Open [^.]+|Open regularly|Open by appointment)", chunk)
    if sm:
        out["status_text"] = sm.group(1).strip()

    # Address — the first line between the H2 and the next marker. Very
    # heuristic but good enough; we also already have postcode separately.
    # Find a line containing the postcode if present; use that as address.
    if out["postcode"]:
        idx = chunk.find(out["postcode"])
        if idx > 0:
            # Walk back to a reasonable start — previous full-stop or section
            start = max(0, idx - 140)
            addr = chunk[start:idx + len(out["postcode"])].strip()
            # Trim trailing words before start that look like the "Visitor information" header
            addr = re.sub(r"^.*Visitor information\s*", "", addr).strip()
            out["address"] = addr or None

    return out


def extract_detail(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else None
    titleparts = _split_title(title or "")

    # Meta description — concise standfirst
    md = soup.find("meta", attrs={"name": "description"})
    summary = md.get("content", "").strip() if md else None

    about = extract_about_block(soup, titleparts.get("name") or "")

    # Hero — og:image is always the best photograph on FoFC pages
    hero = None
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        hero = {
            "url": og["content"],
            "credit": "Friends of Friendless Churches",
            "source": "Friends of Friendless Churches",
            "sourceUrl": url,
            "licence": "© Friends of Friendless Churches — reproduction by permission",
            "caption": f"{titleparts.get('name')} — {titleparts.get('settlement')}" if titleparts.get("settlement") else None,
        }

    # Visitor info
    vinfo = extract_visitor_info(html)

    # Nation inference from region
    region = (titleparts.get("region") or "").lower()
    nation = "Wales" if region in WELSH_REGIONS else "England"

    # Listing grade — FoFC pages don't consistently print it anymore; we
    # leave it null here and let downstream enrichment fill it from
    # Historic England / Cadw if we ever wire that join.
    denom, denom_conf = infer_denomination(
        name=titleparts.get("name"),
        body=about,
        summary=summary,
        nation=nation,
    )
    return {
        "id": f"fofc-{slugify(titleparts.get('name') or url)}-{slugify(titleparts.get('settlement') or '')}".strip("-"),
        "source": "fofc",
        "sourceUrl": url,
        "name": titleparts.get("name"),
        "settlement": titleparts.get("settlement"),
        "region": titleparts.get("region"),
        "nation": nation,
        "postcode": vinfo["postcode"],
        "address": vinfo["address"],
        "osgb": vinfo["osgb"],
        "status_text": vinfo["status_text"],
        "listing_grade": None,
        "summary": summary,
        "body": about,
        "hero": hero,
        "custodian": "Friends of Friendless Churches",
        "denomination": denom,
        "denominationConfidence": denom_conf,
        # Status classification:
        # - "Closed for repairs" / "Closed" → rescued (we're about to open)
        # - "Open regularly" / "Open by appointment" → preserved
        "status": "rescued" if (vinfo["status_text"] or "").lower().startswith("closed") else "preserved",
    }


def main():
    print("Fetching FoFC index…")
    limiter = RateLimiter(min_gap=1.1)
    index_html = get(INDEX_URL, limiter=limiter)
    rows = extract_index_rows(index_html)
    print(f"  → {len(rows)} churches on the index")

    records = []
    for i, row in enumerate(rows, 1):
        slug = row["url"].rstrip("/").rsplit("/", 1)[-1]
        print(f"  [{i}/{len(rows)}] {slug}")
        try:
            html = get(row["url"], limiter=limiter)
            rec = extract_detail(row["url"], html)
            records.append(rec)
        except Exception as e:
            print(f"      failed: {e}")

    write_raw("fofc", records)


if __name__ == "__main__":
    main()

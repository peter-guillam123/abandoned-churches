"""Shared helpers for the ingestion scripts.

Rate-limited HTTP with a simple on-disk cache so a re-run of a script
doesn't hammer a charity's web server. Each script stages its records
into build/_raw/ as JSON; build_register.py joins them."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

import requests

HERE = Path(__file__).parent
RAW = HERE / "_raw"
CACHE = HERE / "_cache"
RAW.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

UA = (
    "abandoned-churches-prototype/0.1 "
    "(+https://github.com/peter-guillam123/abandoned-churches; "
    "chris.moran@guardian.co.uk)"
)


class RateLimiter:
    """Simple token-bucket-ish minimum-gap limiter."""

    def __init__(self, min_gap: float = 1.1):
        self.min_gap = min_gap
        self._last = 0.0

    def wait(self):
        delta = time.time() - self._last
        if delta < self.min_gap:
            time.sleep(self.min_gap - delta)
        self._last = time.time()


def _cache_path(url: str, suffix: str = ".html") -> Path:
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    return CACHE / f"{key}{suffix}"


def get(url: str, *, limiter: RateLimiter | None = None, cache: bool = True, suffix: str = ".html", **kwargs) -> str:
    """GET with cache + rate limit. Returns text."""
    p = _cache_path(url, suffix)
    if cache and p.exists():
        return p.read_text(encoding="utf-8")
    if limiter:
        limiter.wait()
    headers = {"User-Agent": UA, **kwargs.pop("headers", {})}
    resp = requests.get(url, headers=headers, timeout=30, **kwargs)
    resp.raise_for_status()
    if cache:
        p.write_text(resp.text, encoding="utf-8")
    return resp.text


def get_json(url: str, *, limiter: RateLimiter | None = None, cache: bool = True, **kwargs) -> Any:
    txt = get(url, limiter=limiter, cache=cache, suffix=".json", **kwargs)
    return json.loads(txt)


def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


# Denomination keyword mining — applied to name + body text + summary.
# Order matters: longer / more specific phrases first. Each tuple is
#   (regex, canonical denomination, confidence)
# where confidence is "high" for explicit denominational vocabulary and
# "low" for the residual "St X's" Anglican default.
DENOM_RULES = [
    (re.compile(r"\bRoman\s+Catholic\b|\bR\.?\s*C\.?\s+Church\b", re.I), "Roman Catholic", "high"),
    (re.compile(r"\bCatholic\b", re.I), "Roman Catholic", "high"),
    (re.compile(r"\bMethodist\b|\bWesleyan\b|\bPrimitive\s+Methodist\b", re.I), "Methodist", "high"),
    (re.compile(r"\bBaptist\b|\bStrict\s+(?:and\s+)?Particular\b", re.I), "Baptist", "high"),
    (re.compile(r"\bQuaker\b|\bFriends?\s+Meeting\s+House\b|\bSociety\s+of\s+Friends\b", re.I), "Quaker", "high"),
    (re.compile(r"\bUnited\s+Reformed\b|\bU\.?R\.?C\.?\b", re.I), "United Reformed", "high"),
    (re.compile(r"\bPresbyterian\b|\bChurch\s+of\s+Scotland\b", re.I), "Presbyterian", "high"),
    (re.compile(r"\bCongregational\b", re.I), "Congregational", "high"),
    (re.compile(r"\bSynagogue\b|\bMachzike\b|\bJamme[s]?\s+Masjid\b|\bMasjid\b", re.I), None, None),
    (re.compile(r"\bUnitarian\b", re.I), "Unitarian", "high"),
    (re.compile(r"\bMoravian\b", re.I), "Moravian", "high"),
    (re.compile(r"\bDissenter|\bNonconformist", re.I), "Nonconformist", "medium"),
    (re.compile(r"\bSalvation\s+Army\b", re.I), "Salvation Army", "high"),
    (re.compile(r"\bChurch\s+of\s+(?:Jesus\s+Christ|Latter[- ]day\s+Saints?)\b", re.I), "Latter-day Saints", "high"),
    (re.compile(r"\bChristian\s+Scien", re.I), "Christian Science", "high"),
    # Anglican-style heuristic — only fired if no other rule matched.
    # We split this off below so the loop can still try every rule before
    # falling back.
]


def infer_denomination(name: str | None, body: str | None, summary: str | None,
                        nation: str | None) -> tuple[str | None, str | None]:
    """Return (denomination, confidence) where either may be None.

    Confidence is "high" for explicit keyword matches, "low" for the
    'St X's' Anglican default. Special-case: matched Masjid / Synagogue
    phrases return None,None — the historical denomination depends on
    whether the building has shifted use and is best handled in the
    hand-curated record (Brick Lane is Muslim today; we keep it that
    way only if explicitly set in buildings.hand.json).
    """
    text = " ".join([name or "", body or "", summary or ""])
    for regex, denom, confidence in DENOM_RULES:
        if regex.search(text):
            return denom, confidence

    # Fallback: a "St X's" or "Church of …" name in a Christian context
    # almost always means an Anglican parish church in this dataset.
    saintish = re.search(
        r"\b(?:St\.?|Saint|Holy|Trinity|All\s+Saints|All\s+Souls|"
        r"Christ\s+Church|Church\s+of)\b",
        name or "",
        re.I,
    )
    chapel = re.search(r"\bChapel\b", name or "", re.I)
    if saintish and not chapel:
        if (nation or "").lower().startswith("wales"):
            return "Church in Wales", "low"
        if (nation or "").lower().startswith("scot"):
            return None, None
        return "Church of England", "low"

    return None, None


def write_raw(name: str, records: list[dict]):
    p = RAW / f"{name}.json"
    p.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → wrote {len(records)} records to {p.relative_to(HERE.parent)}")


def read_raw(name: str) -> list[dict]:
    p = RAW / f"{name}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# Period / age extraction
# ----------------------------------------------------------------------
#
# We mine the building's free text — name + listing description + body
# + summary — for the EARLIEST date or century mentioned. NHLE listing
# entries use compact century notation ("C13", "Late C12"); FoFC and
# CCT prose tends toward "13th century" or explicit years ("1859");
# and a final fallback recognises period-name keywords ("Norman",
# "Tudor", "Victorian"). The earliest-of-these wins because that's
# usually when the surviving fabric began.
#
# Output:
#   periodCentury: int (e.g. 13 for C13)
#   periodEra: one of the canonical buckets
#                 "Pre-Conquest" (<1066), "Norman" (1066-1199),
#                 "Medieval" (1200-1499), "Tudor & Stuart" (1500-1714),
#                 "Georgian" (1715-1836), "Victorian" (1837-1901),
#                 "20th century onwards" (1902+)

ERA_BUCKETS = [
    (-9999, 1065, "Pre-Conquest"),
    (1066, 1199, "Norman"),
    (1200, 1499, "Medieval"),
    (1500, 1714, "Tudor & Stuart"),
    (1715, 1836, "Georgian"),
    (1837, 1901, "Victorian"),
    (1902, 9999, "20th century onwards"),
]

PERIOD_KEYWORDS = [
    # (regex, midpoint year used as a representative date)
    (re.compile(r"\bPre[-\s]?Conquest\b|\bSaxon\b|\bAnglo[-\s]?Saxon\b", re.I), 950),
    (re.compile(r"\bNorman\b|\bRomanesque\b", re.I), 1100),
    (re.compile(r"\bEarly\s+English\b", re.I), 1230),
    (re.compile(r"\bDecorated\b(?:\s+(?:Gothic|style))?", re.I), 1330),
    (re.compile(r"\bPerpendicular\b(?:\s+(?:Gothic|style))?", re.I), 1430),
    (re.compile(r"\bTudor\b", re.I), 1530),
    (re.compile(r"\bElizabethan\b", re.I), 1580),
    (re.compile(r"\bJacobean\b", re.I), 1620),
    (re.compile(r"\bStuart\b|\bRestoration\b", re.I), 1670),
    (re.compile(r"\bGeorgian\b", re.I), 1750),
    (re.compile(r"\bRegency\b", re.I), 1815),
    (re.compile(r"\bGothic\s+Revival\b", re.I), 1870),
    (re.compile(r"\bVictorian\b", re.I), 1870),
    (re.compile(r"\bEdwardian\b", re.I), 1905),
    (re.compile(r"\bMedieval\b|\bMediaeval\b", re.I), 1300),
]

# C13, C14*, "late C12", etc. — NHLE convention is capital C, exactly.
# Lower-case `c1100` means *circa 1100* and must not match this.
CENTURY_RE = re.compile(
    r"(?P<modifier>(?:Early|Mid|Late)[\s-]?)?C\s?(?P<n>1[0-9]|[1-9])(?:th)?(?:[\s-]?cent(?:ury)?)?",
)
# "13th century", "fourteenth century"
ORDINAL_CENTURY_RE = re.compile(
    r"\b(?P<n>[1-9][0-9]?)(?:st|nd|rd|th)\s+century\b",
    re.I,
)
# Explicit year — between 700 and 2029. Allow optional circa prefix
# ("c1100", "c.1380", "circa 1380"). Must be word-bounded after.
YEAR_RE = re.compile(
    r"(?:\bc\.?\s*|\bcirca\s+)?(?<![\d/.])(?P<y>(?:6[5-9][0-9]|[7-9][0-9]{2}|1[0-9]{3}|20[0-2][0-9]))\b"
)


def _century_to_year(n: int, modifier: str | None) -> int:
    """Return a representative year inside the given century.
    For C13 → 1230 (early), 1250 (mid), 1280 (late), 1230 default."""
    base = (n - 1) * 100
    mod = (modifier or "").strip().lower()
    if mod.startswith("early"):
        return base + 25
    if mod.startswith("mid"):
        return base + 50
    if mod.startswith("late"):
        return base + 80
    return base + 30  # plain "C13" — early-third


# Phrases that look like dates but refer to something else.
# "800-year-old", "900 years of craftsmanship", "untouched for 700
# years" are ages, not founding years. "C6th St Doged" or "6th century
# site of St Beuno" refers to a saint, not the building.
NOISE_PATTERNS = [
    # "800-year-old" / "800 year old"
    re.compile(r"\b\d{2,4}[-\s]?year[-\s]?old\b", re.I),
    # "900 years of …" / "for 700 years" / "in 800 years" — generic age
    re.compile(r"\b(?:for|in|over|of|after|nearly|almost|some|about|over)\s+\d{2,4}\s+years?\b", re.I),
    re.compile(r"\b\d{2,4}\s+years\s+(?:of|since|ago|on|under|untouched|after|before)\b", re.I),
    # "C6th St Beuno" / "Saint Doged C6th" / "6th century St Beuno"
    re.compile(r"\b(?:St|Saint|Bishop|King|Queen|Pope)\.?\s+\w+,?\s+(?:a\s+)?(?:[Cc]\s?\d{1,2}(?:th)?|\d{1,2}(?:st|nd|rd|th)\s+century)", re.I),
    re.compile(r"\b(?:[Cc]\s?\d{1,2}(?:th)?|\d{1,2}(?:st|nd|rd|th)\s+century)\s+(?:site\s+of\s+)?(?:St\b|Saint\b|martyr|monk|missionary|abbess?|abbot|hermit)", re.I),
    # "site of St Beuno's cell" — strip the saint clause
    re.compile(r"\bsite\s+of\s+St\.?\s+\w+", re.I),
    # NHLE list-reference serials like "811/1/298", "1478-4/10003",
    # "8/12" — typewriter index numbers, not dates.
    re.compile(r"\b\d{1,5}[-/]\d{1,3}(?:/\d{2,5})?\b"),
    # Capacity numbers — "designed to seat between 700 and 800 people"
    # / "300 sittings" / "150 souls".
    re.compile(
        r"\b\d{2,4}(?:\s*(?:to|and|or|-)\s*\d{2,4})?\s+"
        r"(?:people|persons|seats?|sittings?|congregants?|worshippers?|"
        r"men|women|families|souls|sq\.?\s*ft|sq\.?\s*m)\b",
        re.I,
    ),
    # OS National Grid Refs at the top of NHLE entries — letters then
    # digits, sometimes with a compass suffix (TQ 0123 4567, SP52NE).
    re.compile(r"\b[A-Z]{2}\s?\d{1,5}(?:\s+\d{1,5})?(?:\s?[NSEW]{1,2})?\b"),
]


def _scrub_noise(text: str) -> str:
    """Replace noise phrases with spaces so they don't show up in
    extract_dates' regex matches."""
    if not text:
        return ""
    out = text
    for rx in NOISE_PATTERNS:
        out = rx.sub(lambda m: " " * len(m.group(0)), out)
    return out


def extract_dates(text: str) -> list[int]:
    """Return all plausible dates found in a piece of free text, oldest
    first."""
    if not text:
        return []
    text = _scrub_noise(text)
    found: list[int] = []
    for m in CENTURY_RE.finditer(text):
        try:
            n = int(m.group("n"))
            if 5 <= n <= 21:
                found.append(_century_to_year(n, m.group("modifier")))
        except (TypeError, ValueError):
            continue
    for m in ORDINAL_CENTURY_RE.finditer(text):
        try:
            n = int(m.group("n"))
            if 5 <= n <= 21:
                found.append(_century_to_year(n, None))
        except (TypeError, ValueError):
            continue
    for m in YEAR_RE.finditer(text):
        try:
            y = int(m.group("y"))
            if 700 <= y <= 2030:
                # Skip obvious listing-date / postcode dates by checking
                # for ISO-ish proximity.
                start = max(0, m.start() - 6)
                ctx = text[start:m.end() + 6]
                if re.search(r"-\d{2}-\d{2}", ctx):
                    continue
                found.append(y)
        except (TypeError, ValueError):
            continue
    # Period keywords are weakest signal — only use them when nothing
    # else fired. Otherwise "Norman font in a Victorian church" would
    # falsely date the whole building to 1100.
    if not found:
        for regex, year in PERIOD_KEYWORDS:
            if regex.search(text):
                found.append(year)
                break
    return sorted(set(found))


def year_to_era(year: int) -> str | None:
    if year is None:
        return None
    for lo, hi, label in ERA_BUCKETS:
        if lo <= year <= hi:
            return label
    return None


def infer_period(name: str | None, body: str | None,
                 summary: str | None, listing_reason: str | None,
                 fabric_phases: list[dict] | None = None) -> tuple[int | None, str | None]:
    """Best-guess earliest-extant-date for a building, plus its era
    bucket.

    Sources are weighted by how reliable they are for the BUILDING's
    date (vs. an artefact's, or a saint's, or an age-phrase):
      1. `fabric.phases[0]` from hand-curated records — canonical.
      2. NHLE listing description — first explicit year is normally
         when the present church was built.
      3. The summary line as a fallback only.

    The first source that yields a candidate wins; we don't blend
    across sources, so a Victorian church with a Saxon font isn't
    pulled back into the Saxon era by a keyword in the summary."""

    if fabric_phases:
        for p in fabric_phases:
            yr = p.get("year") if isinstance(p, dict) else None
            if isinstance(yr, int):
                return yr, year_to_era(yr)
            if isinstance(yr, str):
                ys = extract_dates(yr)
                if ys:
                    return ys[0], year_to_era(ys[0])

    if listing_reason:
        ys = extract_dates(listing_reason)
        if ys:
            return ys[0], year_to_era(ys[0])

    # Marketing-copy summaries (FoFC, CCT) are unreliable for periods —
    # they mention features (Saxon font, Norman door) and ages
    # ("800-year-old") that the noise scrub mostly handles, but to be
    # safe we only accept an explicit 4-digit YEAR from these — no
    # centuries, no period keywords. That filters "Saxon survivor" and
    # "C6th St Beuno's" while still catching "1689 by Henry Oxley".
    for source in (body, summary, name):
        if not source:
            continue
        scrubbed = _scrub_noise(source)
        years_only: list[int] = []
        for m in YEAR_RE.finditer(scrubbed):
            try:
                y = int(m.group("y"))
                if 1000 <= y <= 2030:
                    years_only.append(y)
            except (TypeError, ValueError):
                continue
        if years_only:
            best = min(years_only)
            return best, year_to_era(best)

    return None, None


# Canonical names for filter chips. Variants from hand-curated records
# ("Church of England (Diocese of York)", "Roman Catholic Church") all
# collapse to one of these so the UI doesn't show fifty near-duplicates.
def canonicalise_denomination(s: str | None) -> str | None:
    if not s:
        return None
    text = s.lower()
    if "church of england" in text or "anglican" in text:
        return "Church of England"
    if "church in wales" in text:
        return "Church in Wales"
    if "scottish episcopal" in text:
        return "Scottish Episcopal"
    if "church of scotland" in text or "presbyterian" in text:
        return "Presbyterian"
    if "roman catholic" in text or "catholic" in text:
        return "Roman Catholic"
    if "methodist" in text or "wesleyan" in text:
        return "Methodist"
    if "baptist" in text:
        return "Baptist"
    if "quaker" in text or "friends meeting" in text or "society of friends" in text:
        return "Quaker"
    if "united reformed" in text or "u.r.c" in text:
        return "United Reformed"
    if "congregational" in text:
        return "Congregational"
    if "unitarian" in text:
        return "Unitarian"
    if "moravian" in text:
        return "Moravian"
    if "salvation army" in text:
        return "Salvation Army"
    if "latter-day" in text or "latter day" in text:
        return "Latter-day Saints"
    if "christian scien" in text:
        return "Christian Science"
    if "muslim" in text or "masjid" in text:
        return "Muslim"
    if "jewish" in text or "synagogue" in text or "machzike" in text:
        return "Jewish"
    # "Non-denominational" comes first — Abney Park's hand-curated text
    # is "Non-denominational (originally for Dissenters)" and the Dissenter
    # branch would otherwise win.
    if "non-denominational" in text:
        return "Non-denominational"
    if "nonconformist" in text or "dissenter" in text:
        return "Nonconformist"
    return s.strip()

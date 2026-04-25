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

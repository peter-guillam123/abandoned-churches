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


def write_raw(name: str, records: list[dict]):
    p = RAW / f"{name}.json"
    p.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → wrote {len(records)} records to {p.relative_to(HERE.parent)}")


def read_raw(name: str) -> list[dict]:
    p = RAW / f"{name}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))

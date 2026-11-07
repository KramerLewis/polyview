"""Shared helpers: polite HTTP fetching with provenance records.

Every file we download is written under ``data/raw/<source>/`` and gets a line
in ``data/raw/manifest.jsonl`` recording where it came from, when, and its
SHA-256. Every number the site publishes must be traceable back to one of
these records.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SAMPLES = ROOT / "data" / "samples"
MANIFEST = RAW / "manifest.jsonl"

USER_AGENT = "polyview/0.0.1 (+https://github.com/KramerLewis/polyview)"


def fetch(url: str, source: str, filename: str, *, data: bytes | None = None,
          timeout: int = 300, retries: int = 3) -> Path:
    """Download ``url`` to ``data/raw/<source>/<filename>`` and record provenance."""
    dest = RAW / source / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                last_modified = resp.headers.get("Last-Modified")
            break
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    dest.write_bytes(body)
    record = {
        "source": source,
        "url": url,
        "path": str(dest.relative_to(ROOT)),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_modified": last_modified,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return dest


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return path


def dollars(text: str | None) -> int | None:
    """'$45,521,000' -> 45521000."""
    if not text:
        return None
    digits = text.replace("$", "").replace(",", "").strip()
    return int(digits) if digits.lstrip("-").isdigit() else None

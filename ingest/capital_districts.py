"""Capital budget projects by legislative district (LEAP report on fiscal.wa.gov).

The report needs JavaScript, so the raw CSVs are fetched by
scripts/fetch_capital_districts.js and committed as a snapshot under
data/snapshots/capital_districts/<version>/ (DECISIONS D-035). This module
parses that snapshot.

Each row: district, agency, grant program (optional), project, amount ($K,
total budgeted funds). LEAP marks some rows with footnote symbols:
  *  funded through alternative financing
  $  amount is for the entire project, which spans several locations, so it is
     NOT specific to this district
  #  only the components located in this district are shown
  %  minor works amounts for this location are preliminary
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .common import ROOT, SAMPLES, write_csv

SNAPSHOTS = ROOT / "data" / "snapshots" / "capital_districts"
MARKERS = {"*": "alt_financing", "$": "multi_location", "#": "local_components_only", "%": "preliminary"}


@dataclass
class DistrictProject:
    version: str
    district: int
    agency: str
    program: str
    project: str
    amount: int  # dollars
    alt_financing: bool
    multi_location: bool
    local_components_only: bool
    preliminary: bool


def _strip_markers(text: str) -> tuple[str, set[str]]:
    found = set()
    text = text.strip()
    while text and text[-1] in MARKERS:
        found.add(MARKERS[text[-1]])
        text = text[:-1].rstrip()
    return text, found


def parse_csv(body: str, version: str) -> tuple[list[DistrictProject], int | None]:
    body = body.lstrip("﻿")
    # The export has a footnote block, a blank line, then the detail table.
    start = body.find("textbox35")
    if start < 0:
        return [], None
    rows = []
    total = None
    for rec in csv.reader(io.StringIO(body[start:])):
        if not rec or rec[0].startswith("textbox"):
            continue
        dist_label, dist_total, agency, program, project, amount = (rec + [""] * 6)[:6]
        m = re.search(r"(\d+)\w\w Legislative District", dist_label)
        if not m or not amount.strip():
            continue
        total = int(dist_total.replace(",", "")) * 1000 if dist_total.strip() else None
        program, f1 = _strip_markers(program)
        project, f2 = _strip_markers(project)
        flags = f1 | f2
        rows.append(DistrictProject(
            version, int(m.group(1)), agency.strip(), program, project,
            int(amount.replace(",", "")) * 1000,
            *(name in flags for name in MARKERS.values())))
    return rows, total


def load(version_dir: Path) -> tuple[list[DistrictProject], dict, list[str]]:
    meta = json.loads((version_dir / "versions.json").read_text())
    version = meta["selected"]
    projects: list[DistrictProject] = []
    issues = []
    for path in sorted(version_dir.glob("ld*.csv")):
        rows, total = parse_csv(path.read_text(encoding="utf-8-sig"), version)
        if rows and total is not None and abs(sum(r.amount for r in rows) - total) > 1000 * len(rows):
            issues.append(f"{path.name}: rows sum {sum(r.amount for r in rows):,} != district total {total:,}")
        projects.extend(rows)
    return projects, meta, issues


def run() -> None:
    for version_dir in sorted(p for p in SNAPSHOTS.iterdir() if p.is_dir()):
        projects, meta, issues = load(version_dir)
        districts = {p.district for p in projects}
        local = [p for p in projects if not p.multi_location]
        print(f"{version_dir.name} ({meta['selected']}): {len(projects)} project rows in {len(districts)} "
              f"districts; ${sum(p.amount for p in projects)/1e9:,.2f}B listed, "
              f"${sum(p.amount for p in local)/1e9:,.2f}B location-specific; {len(issues)} total mismatches")
        for i in issues[:5]:
            print("  ", i)
        write_csv(SAMPLES / f"capital_by_district_{version_dir.name}.csv", [asdict(p) for p in projects])

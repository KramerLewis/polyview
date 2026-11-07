"""Reconcile parsed totals against published reference figures.

Reference values live in crosswalk/reference_totals.csv with their source.
Exits non-zero if any check is outside tolerance, which stops the site
build (DECISIONS D-017).
"""

from __future__ import annotations

import csv
import sys

from .budget_current import build_all
from .common import ROOT

# Near General Fund-Outlook: the accounts the four-year balanced budget outlook covers.
NGFO_FUNDS = {
    "General Fund",
    "Education Legacy Trust Account",
    "Washington Opportunity Pathways Account",
    "Workforce Education Investment Account",
}


def ngfo(rows: list[dict], biennium: str, version: str) -> int:
    """version: 'original', 'current', or an intermediate 'after_<label>' column
    (a line a supplemental didn't touch keeps its original amount)."""
    def amount(r: dict) -> int:
        if version in ("original", "current"):
            return r[version]
        return r.get(version, r["original"])
    return sum(amount(r) for r in rows
               if r["budget"] == "operating" and r["biennium"] == biennium
               and r["kind"] == "appropriation" and r["fund"] in NGFO_FUNDS
               and r["fund_source"] == "State")


MEASURES = {"ngfo_appropriations": ngfo}


def run() -> bool:
    rows, _ = build_all()
    ok = True
    with (ROOT / "crosswalk" / "reference_totals.csv").open(encoding="utf-8") as f:
        for ref in csv.DictReader(f):
            got = MEASURES[ref["measure"]](rows, ref["biennium"], ref["version"])
            exp = int(ref["expected"])
            off = abs(got - exp) / exp
            passed = off <= float(ref["tolerance"])
            ok &= passed
            print(f"{'PASS' if passed else 'FAIL'} {ref['check']}: parsed ${got/1e9:,.3f}B vs "
                  f"published ${exp/1e9:,.3f}B ({off:.3%} off; source: {ref['source']})")
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)

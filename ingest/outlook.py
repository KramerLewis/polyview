"""ERFC four-year balanced budget outlook (funds subject to the outlook, NGF-O).

The outlook adopted for each enacted budget is a one-page balance sheet: NGF-O
beginning balance, forecast revenue, other resource changes, appropriations,
assumed reversions, ending balance and reserves (Budget Stabilization Account),
for the current biennium and the next one. It is the Legislature's official
income-vs-spending picture, and it projects the *next* biennium.

Source page: https://erfc.wa.gov/budget-outlook  (PDF, $ millions)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .budget_to_actual import pdf_text
from .common import SAMPLES, fetch, write_csv

OUTLOOKS = [
    # (label, url)
    ("Enacted 2026 supplemental (ESSB 5998), adopted April 2026",
     "https://erfc.wa.gov/sites/default/files/2026-04/20260422_Enacted_Sup_BO_Adopted.pdf"),
]
COLUMNS = ["fy1", "fy2", "biennium1", "fy3", "fy4", "biennium2"]
NUM = r"-?[\d,]+(?:\.\d+)?%?"
ROW = re.compile(rf"^(?P<indent>\s*)(?P<label>\S.*?)\s{{2,}}(?P<nums>(?:{NUM}\s+){{3,5}}{NUM})\s*$")


@dataclass
class OutlookRow:
    outlook: str
    order: int
    section: str
    label: str
    is_detail: bool
    fy1: float | None
    fy2: float | None
    biennium1: float | None
    fy3: float | None
    fy4: float | None
    biennium2: float | None


def _n(s: str) -> float:
    s = s.replace(",", "")
    return float(s[:-1]) / 100 if s.endswith("%") else float(s)


def parse_text(text: str, outlook: str) -> tuple[list[OutlookRow], dict]:
    lines = text.splitlines()
    header = next((l for l in lines if re.search(r"\d{4}-\d{2}\s+\d{4}-\d{2}", l)), "")
    years = re.findall(r"\d{4}-\d{2}", header)
    rows: list[OutlookRow] = []
    base_indent = None
    section = ""
    for line in lines:
        m = ROW.match(line)
        if not m:
            if line.strip() and not re.search(r"\d", line) and len(line.strip()) < 60:
                section = line.strip()
            continue
        nums = m["nums"].split()
        indent = len(m["indent"])
        base_indent = indent if base_indent is None else min(base_indent, indent)
        vals: list[float | None] = [_n(x) for x in nums]
        if len(vals) == 4:  # percentage rows show FY values only
            vals = [vals[0], vals[1], None, vals[2], vals[3], None]
        if len(vals) != 6:
            continue
        label = m["label"].strip()
        is_detail = indent > (base_indent or 0)
        if not is_detail:
            section = label
        rows.append(OutlookRow(outlook, len(rows), section, label, is_detail, *vals))
    meta = {"bienniums": years[:2]}
    return rows, meta


def get(rows: list[OutlookRow], label: str) -> OutlookRow:
    return next(r for r in rows if r.label == label and not r.is_detail)


def arithmetic_errors(rows: list[OutlookRow]) -> list[str]:
    """The outlook's own identities must hold (within $1M rounding per term)."""
    g = lambda label: get(rows, label)  # noqa: E731
    errors = []
    for col in ("biennium1", "biennium2"):
        v = lambda label: getattr(g(label), col)  # noqa: E731
        checks = {
            "resources = beginning + forecast + other":
                (v("Total Revenues and Resources"),
                 v("NGF-O Beginning Balance") + v("Forecasted Revenues") + v("Other Resource Changes")),
            "revised = enacted + maintenance + policy + reversions":
                (v("Revised Appropriations"),
                 v("Enacted Appropriations") + v("Maintenance Level Total") + v("Policy Level Total")
                 + v("Reversions")),
            "ending = resources - revised":
                (v("NGF-O Projected Ending Balance"),
                 v("Total Revenues and Resources") - v("Revised Appropriations")),
        }
        for name, (stated, computed) in checks.items():
            if abs(stated - computed) > 3:
                errors.append(f"{col}: {name}: stated {stated:,.0f} vs computed {computed:,.0f}")
    return errors


def run() -> list[OutlookRow]:
    all_rows: list[OutlookRow] = []
    for label, url in OUTLOOKS:
        path = fetch(url, "outlook", url.rsplit("/", 1)[-1])
        rows, meta = parse_text(pdf_text(path), label)
        rev = get(rows, "Total Revenues and Resources")
        app = get(rows, "Revised Appropriations")
        end = get(rows, "NGF-O Projected Ending Balance")
        b1, b2 = meta["bienniums"]
        print(f"{label}: {len(rows)} rows; {b1} resources ${rev.biennium1:,.0f}M vs revised "
              f"appropriations ${app.biennium1:,.0f}M, ending ${end.biennium1:,.0f}M; "
              f"{b2} ending ${end.biennium2:,.0f}M (FY lows: {min(end.fy1, end.fy2, end.fy3, end.fy4):,.0f}M)")
        errors = arithmetic_errors(rows)
        if errors:
            raise ValueError(f"outlook arithmetic doesn't hold: {errors}")
        all_rows.extend(rows)
    write_csv(SAMPLES / "budget_outlook.csv", [asdict(r) for r in all_rows])
    return all_rows

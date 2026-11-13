"""ERFC four-year balanced budget outlook (funds subject to the outlook, NGF-O).

The outlook adopted for each enacted budget is a one-page balance sheet: NGF-O
beginning balance, forecast revenue, other resource changes, appropriations,
assumed reversions, ending balance and reserves, by fiscal year and biennium.
Supplemental outlooks show two bienniums (current, next); biennial outlooks
show three (prior, new, next). Rows are stored in long format, one per
(row, biennium).

Source pages: https://erfc.wa.gov/budget-outlook and .../budget-outlook-archives
(PDF, $ millions). DECISIONS D-034.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .budget_to_actual import pdf_text
from .common import SAMPLES, fetch, write_csv

ERFC = "https://erfc.wa.gov/sites/default/files/"
# Oldest first; the last one is the current outlook shown on the site.
OUTLOOKS = [
    ("Enacted 2019-21 budget (EHB 1109), June 2019", ERFC + "2025-03/20190611_Outlook.pdf"),
    ("Enacted 2020 supplemental (ESSB 6168), April 2020", ERFC + "2025-03/20200430_outlook.pdf"),
    ("Enacted 2022 supplemental (ESSB 5693), April 2022",
     ERFC + "2025-03/20220421%20FY%202022%20Enacted%20Sup%20Budget%20Outlook%20Adopted.pdf"),
    ("Enacted 2023-25 budget (ESSB 5187), June 2023", ERFC + "2025-03/20230613%20FY2023-25EnactedOutlook.pdf"),
    ("Enacted 2024 supplemental (ESSB 5950), 2024", ERFC + "2025-03/FY%202024%20Enacted%20Outlook_Final.pdf"),
    ("Enacted 2025-27 budget (ESSB 5167), 2025", ERFC + "2025-06/2025%20Enacted%20Outlook%20Final.pdf"),
    ("Enacted 2026 supplemental (ESSB 5998), April 2026", ERFC + "2026-04/20260422_Enacted_Sup_BO_Adopted.pdf"),
]
# Row labels vary between years; map each to one canonical name.
CANONICAL = {
    "Beginning Balance": "NGF-O Beginning Balance",
    "Current Revenues": "Forecasted Revenues",  # 2019-2020 outlooks
    "Projected Ending Balance": "NGF-O Projected Ending Balance",
    "Budget Stabilization Account Ending Balance": "BSA Ending Balance",
}
NUM = r"-?[\d,]+(?:\.\d+)?%?"
ROW = re.compile(rf"^(?P<indent>\s*)(?P<label>\S.*?)\s{{2,}}(?P<nums>(?:{NUM}\s+){{3,}}{NUM})\s*$")


@dataclass
class OutlookRow:
    outlook: str
    order: int
    label: str
    is_detail: bool
    biennium: str
    fy_a: float | None  # first fiscal year of the biennium
    fy_b: float | None  # second fiscal year
    total: float | None  # biennium total (None for percentage rows)


def local_name(url: str) -> str:
    return url.rsplit("/", 1)[-1].replace("%20", "_")


def _n(s: str) -> float:
    s = s.replace(",", "")
    return float(s[:-1]) / 100 if s.endswith("%") else float(s)


def _bienniums(lines: list[str]) -> list[str]:
    """From the header row 'FY 2026 FY 2027 2025-27 FY 2028 ...'."""
    fy_line = next(l for l in lines if len(re.findall(r"FY\s*\d{4}", l)) >= 4)
    fys = [int(y) for y in re.findall(r"FY\s*(\d{4})", fy_line)]
    starts = sorted({fy - 1 if fy % 2 == 0 else fy - 2 for fy in fys})
    return [f"{s}-{str(s + 2)[-2:]}" for s in starts]


def parse_text(text: str, outlook: str) -> tuple[list[OutlookRow], list[str]]:
    lines = text.splitlines()
    bienniums = _bienniums(lines)
    n = len(bienniums)
    rows: list[OutlookRow] = []
    base_indent = None
    order = 0
    for line in lines:
        m = ROW.match(line)
        if not m:
            continue
        nums = [_n(x) for x in m["nums"].split()]
        indent = len(m["indent"])
        base_indent = indent if base_indent is None else min(base_indent, indent)
        if len(nums) == 3 * n:
            groups = [nums[3 * i:3 * i + 3] for i in range(n)]
        elif len(nums) == 2 * n:  # percentage rows: fiscal years only
            groups = [[nums[2 * i], nums[2 * i + 1], None] for i in range(n)]
        else:
            continue
        label = CANONICAL.get(m["label"].strip(), m["label"].strip())
        for b, (a, c, t) in zip(bienniums, groups):
            rows.append(OutlookRow(outlook, order, label, indent > base_indent, b, a, c, t))
        order += 1
    return rows, bienniums


def get(rows: list[OutlookRow], label: str, biennium: str) -> OutlookRow | None:
    return next((r for r in rows if r.label == label and r.biennium == biennium and not r.is_detail), None)


def enacted_level(rows: list[OutlookRow], biennium: str) -> float:
    """Appropriations as enacted by the bill the outlook is for, before assumed
    reversions: the base plus carry-forward, maintenance and policy changes."""
    total = 0.0
    for label in ("Enacted Appropriations", "Carryforward Level Adjustments",
                  "Maintenance Level Total", "Policy Level Total"):
        r = get(rows, label, biennium)
        total += r.total if r else 0
    return total


def arithmetic_errors(rows: list[OutlookRow], bienniums: list[str]) -> list[str]:
    """The outlook's own identities must hold (within $3M of rounding)."""
    errors = []
    for b in bienniums:
        def v(label: str) -> float:
            r = get(rows, label, b)
            return r.total if r else 0.0
        checks = {
            "resources = beginning + forecast + other":
                (v("Total Revenues and Resources"),
                 v("NGF-O Beginning Balance") + v("Forecasted Revenues") + v("Other Resource Changes")),
            "revised = enacted level + reversions":
                (v("Revised Appropriations"), enacted_level(rows, b) + v("Reversions")),
            "ending = resources - revised":
                (v("NGF-O Projected Ending Balance"),
                 v("Total Revenues and Resources") - v("Revised Appropriations")),
        }
        for name, (stated, computed) in checks.items():
            if abs(stated - computed) > 3:
                errors.append(f"{b}: {name}: stated {stated:,.0f} vs computed {computed:,.0f}")
    return errors


def _title(text: str) -> str:
    """'Outlook for the Enacted 2026 Supplemental Omnibus Operating Budget - Chapter 268, ...'"""
    for line in text.splitlines():
        if "Outlook for" in line:
            return re.sub(r"\s+", " ", line).strip()
    return "Budget outlook"


def outlook_list() -> list[tuple[str, str, bool]]:
    """(label, url, pinned). Pinned outlooks must parse; newly discovered ones are
    added only if they pass their arithmetic checks (D-043)."""
    pinned = [(label, url, True) for label, url in OUTLOOKS]
    try:
        from .discover import enacted_outlooks
        known = {u for _, u in OUTLOOKS}
        new = [("", u, False) for u in enacted_outlooks() if u not in known]
    except Exception as e:
        print(f"  outlook: discovery failed ({e}); using pinned outlooks")
        new = []
    return pinned + new


def load() -> list[tuple[str, str, list[OutlookRow], list[str]]]:
    out = []
    for label, url, pinned in outlook_list():
        path = fetch(url, "outlook", local_name(url))
        text = pdf_text(path)
        label = label or _title(text)
        try:
            rows, bienniums = parse_text(text, label)
            errors = arithmetic_errors(rows, bienniums)
        except Exception as e:  # a new layout we can't read
            rows, bienniums, errors = [], [], [f"could not parse: {e}"]
        if errors:
            if pinned:
                raise ValueError(f"{label}: outlook arithmetic doesn't hold: {errors}")
            print(f"  outlook: skipping newly found {url} ({errors[0]})")
            continue
        out.append((label, url, rows, bienniums))
    return out


def summarize(label: str, url: str, rows: list[OutlookRow], bienniums: list[str]) -> list[dict]:
    out = []
    for b in bienniums:
        g = lambda name: (get(rows, name, b).total if get(rows, name, b) else None)  # noqa: E731
        out.append({
            "outlook": label, "url": url, "biennium": b,
            "enacted_level": enacted_level(rows, b),
            "revised_appropriations": g("Revised Appropriations"),
            "forecast_revenue": g("Forecasted Revenues"),
            "total_resources": g("Total Revenues and Resources"),
            "ending_balance": g("NGF-O Projected Ending Balance"),
            "total_reserves": g("Total Reserves"),
        })
    return out


def run() -> None:
    all_rows: list[OutlookRow] = []
    summary: list[dict] = []
    for label, url, rows, bienniums in load():
        s = summarize(label, url, rows, bienniums)
        summary.extend(s)
        print(f"{label}: arithmetic OK; " + "; ".join(
            f"{x['biennium']} enacted ${x['enacted_level']:,.0f}M, ending ${x['ending_balance']:,.0f}M" for x in s))
        all_rows.extend(rows)
    write_csv(SAMPLES / "budget_outlook.csv", [asdict(r) for r in all_rows])
    write_csv(SAMPLES / "budget_outlook_vintages.csv", summary)

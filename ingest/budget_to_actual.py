"""OFM Budget-to-Actual Detailed Report: final budget vs. actual spending.

Published annually with the ACFR (one PDF per fiscal year, FY2020 onward) at
https://ofm.wa.gov/spending/financial-audit-reports/annual-comprehensive-financial-report/

Each row: rollup fund, account (fund), agency, expenditure authority, final
budget, actual amount, variance, in thousands of dollars on a *budgetary
basis* and *biennium-to-date*. The odd-year report (e.g. FY2025) covers the
whole biennium; the even-year report covers its first year.

The parser checks itself: rows are summed and compared with the report's own
"... Total" subtotal lines. Mismatches are reported, not silently ignored.
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from .common import SAMPLES, fetch, write_csv

# OFM's file names are inconsistent ("State" vs "state").
FILE_VARIANTS = {
    20: "FY20_Washington_State_Budget-to-Actual_Detail_Report.pdf",
    21: "FY21_Washington_state_Budget-to-Actual_Detail_Report.pdf",
    22: "FY22_Washington_State_Budget-to-Actual_Detail_Report.pdf",
    23: "FY23_Washington_State_Budget-to-Actual_Detail_Report.pdf",
    24: "FY24_Washington_State_Budget-to-Actual_Detail_Report.pdf",
    25: "FY25_Washington_State_Budget-to-Actual_Detail_Report.pdf",
}
BASE = "https://ofm.wa.gov/wp-content/uploads/"

NUM = r"(?:\(?-?[\d,]+\)?|-)"
ROW_END = re.compile(rf"\s+({NUM})\s+({NUM})\s+({NUM})\s*$")
# Some rows leave the variance column blank; only accept these far to the right
# so a trailing year in a name ("Minor Works 2021-2023") isn't mistaken for money.
ROW_END_2 = re.compile(rf"\s{{2,}}({NUM})\s{{2,}}({NUM})\s*$")
MIN_NUMBER_COL = 120
ROLLUP = re.compile(r"^[A-Z]{2,3}[A-Z0-9]?-")
ACCOUNT = re.compile(r"^[0-9A-Z]{3}-")
AGENCY = re.compile(r"^\d{4}-")
AUTH = re.compile(r"^[0-9A-Z]{3}-")


@dataclass
class Row:
    fiscal_year: int
    biennium: str
    rollup_fund: str
    account_code: str
    account: str
    agency_code: str
    agency: str
    authority_code: str
    authority: str
    final_budget_k: int
    actual_k: int
    variance_k: int
    is_adjustment: bool  # accounting entries, not agency program spending


def _num(s: str) -> int:
    s = s.strip()
    if s in ("-", ""):
        return 0
    neg = s.startswith("(") or s.startswith("-")
    v = int(re.sub(r"[^\d]", "", s) or 0)
    return -v if neg else v


# Pseudo-agencies used for statewide accounting entries. Kept in the data (so
# totals reconcile) but flagged so agency views can exclude them.
ADJUSTMENT_AGENCIES = {"7000", "7010"}  # OFM Financial Statement Control, Treasurer's Transfers

ROUNDING_K = 5  # each line is rounded to $1K, so subtotals can drift by a few $K


def _off(got: list[int], total: list[int], _n: int) -> bool:
    return any(abs(a - b) > ROUNDING_K for a, b in zip(got, total))


def _split_code(s: str) -> tuple[str, str]:
    code, _, name = s.partition("-")
    return code.strip(), name.strip()


def _biennium(fy: int) -> str:
    start = fy - 1 if fy % 2 == 0 else fy - 2
    return f"{start}-{str(start + 2)[-2:]}"


def parse_text(text: str, fy: int) -> tuple[list[Row], list[str]]:
    rows: list[Row] = []
    checks: list[str] = []
    pending_auth = ""
    agency_sum: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    account_sum: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    current_account = ""
    current_rollup = ""
    rollup_sum: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for line in text.splitlines():
        if not line.strip() or "Rollup Fund" in line or "expressed in thousands" in line:
            continue
        m = ROW_END.search(line)
        groups: tuple[str, ...] | None = m.groups() if m else None
        if not m:
            m = ROW_END_2.search(line)
            if m and m.start() >= MIN_NUMBER_COL:
                groups = (*m.groups(), "")
            else:
                m = None
        left = line[: m.start()] if m else line
        fields = [f.strip() for f in re.split(r"\s{2,}", left.strip()) if f.strip()]

        if not m:
            # Wrapped authority name: text alone in the authority column.
            if len(fields) == 1 and AUTH.match(fields[0]) and line.startswith(" " * 40):
                pending_auth = fields[0]
            continue

        budget, actual = _num(groups[0]), _num(groups[1])
        variance = _num(groups[2]) if groups[2] else budget - actual

        if fields and fields[-1].endswith(" Total"):
            label = fields[-1][: -len(" Total")]
            if label == current_rollup and not line[:1].isspace():  # rollup totals are flush-left
                got = rollup_sum.get(label)
                if got and _off(got, [budget, actual], len(rows)):
                    checks.append(f"FY{fy} {label}: rows {got} != total {[budget, actual]}")
            elif AGENCY.match(label):
                got = agency_sum.get((current_rollup, current_account, label))
                if got and _off(got, [budget, actual], len(rows)):
                    checks.append(f"FY{fy} {current_rollup} / {current_account} / {label}: "
                                  f"rows {got} != total {[budget, actual]}")
            elif ACCOUNT.match(label):
                got = account_sum.get((current_rollup, label))
                if got and _off(got, [budget, actual], len(rows)):
                    checks.append(f"FY{fy} {current_rollup} / {label}: rows {got} != total {[budget, actual]}")
            pending_auth = ""
            continue

        if not fields or not ROLLUP.match(fields[0]):
            pending_auth = ""
            continue
        rollup, account, agency = fields[0], fields[1], fields[2]
        auth = " ".join(fields[3:])
        if pending_auth:
            auth = f"{pending_auth} {auth}".strip()
            pending_auth = ""
        current_account, current_rollup = account, rollup
        acct_code, acct_name = _split_code(account)
        agy_code, agy_name = _split_code(agency)
        auth_code, auth_name = _split_code(auth) if auth else ("", "")
        rows.append(Row(fy, _biennium(fy), rollup, acct_code, acct_name, agy_code, agy_name,
                        auth_code, auth_name, budget, actual, variance,
                        agy_code in ADJUSTMENT_AGENCIES))
        for key, store in (((rollup, account, agency), agency_sum), ((rollup, account), account_sum),
                           (rollup, rollup_sum)):
            store[key][0] += budget
            store[key][1] += actual
    return rows, checks


def pdf_text(path: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True,
                          capture_output=True, text=True).stdout


def run(years: tuple[int, ...] = (25,)) -> None:
    """FY2025 onward use this summary layout; earlier years: see budget_to_actual_detail."""
    for yy in years:
        fname = FILE_VARIANTS[yy]
        path = fetch(BASE + fname, "budget_to_actual", fname)
        rows, checks = parse_text(pdf_text(path), 2000 + yy)
        budget = sum(r.final_budget_k for r in rows)
        actual = sum(r.actual_k for r in rows)
        print(f"FY20{yy}: {len(rows)} rows, final budget ${budget/1e6:,.1f}B, actual ${actual/1e6:,.1f}B, "
              f"{len(checks)} subtotal mismatches")
        for c in checks[:10]:
            print("  MISMATCH", c)
        write_csv(SAMPLES / f"budget_to_actual_fy20{yy}.csv", [asdict(r) for r in rows])

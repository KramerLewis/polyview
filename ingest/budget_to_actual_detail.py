"""OFM Budget-to-Actual *Detail* Report, long format (FY2020-FY2024).

Before FY2025 OFM published a 2,000+ page version. It has one page per fund,
per fund+agency, and per fund+agency+account, and each page shows:

- Resources (revenue by source: taxes, federal grants, fees, transfers in, ...)
- Charges to appropriations (spending by function: general government,
  human services, education, ... plus capital outlays and transfers out)
- Reconciling items and the budgetary fund balance

with Original budget, Final budget, Actual and Variance in whole dollars.
That covers both the income side and the spending side.

Rows with blank cells are placed into columns using the report's own
arithmetic: variance = actual - final for resources and reconciling items, and
final - actual for charges. Rows that can't be placed unambiguously are
counted and reported.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations

from .budget_to_actual import BASE, FILE_VARIANTS, _biennium, pdf_text
from .common import SAMPLES, fetch, write_csv

TITLE = re.compile(r"^(?P<name>.*?)\s*(?:\((?P<code>[^()]+)\))?\*?$")
LINE = re.compile(r"^\s*(?P<code>[A-Z][A-Z0-9])\s+(?P<label>\S.*?)(?:\s{2,}|\s+\$\s*)(?P<rest>[\d(\-—$].*)$")
LABEL_ONLY = re.compile(r"^\s*(?P<code>[A-Z][A-Z0-9])\s+(?P<label>[A-Za-z][^\d]*?)\s*$")
EXP_AUTH = re.compile(r"^\s{10,}(?P<code>[0-9A-Z]{3})\s{2,}(?P<rest>[\d(\-—$].*)$")
TOKEN = re.compile(r"\(?[\d,]+\)?|—|(?<![\w,])-(?![\w,])")
SECTIONS = {
    "resources": "resources",
    "charges to appropriations": "charges",
    "reconciling items": "reconciling",
}


@dataclass
class DetailRow:
    fiscal_year: int
    biennium: str
    level: str  # fund | agency | account
    fund_code: str
    fund: str
    agency_code: str
    agency: str
    account_code: str
    account: str
    section: str  # balance | resources | charges | reconciling
    line_code: str
    line: str
    authority_code: str  # expenditure authority (appropriation) code, account-level charges only
    original: int
    final: int
    actual: int
    variance: int


def _val(tok: str) -> int:
    if tok in ("-", "—"):
        return 0
    neg = tok.startswith("(")
    v = int(tok.strip("()").replace(",", "") or 0)
    return -v if neg else v


def place(tokens: list[str], section: str) -> tuple[int, int, int, int] | None:
    """Assign 1-4 number tokens to (original, final, actual, variance)."""
    vals = [_val(t) for t in tokens]
    if len(vals) == 4:
        return tuple(vals)  # type: ignore[return-value]
    sign = 1 if section == "charges" else -1  # variance = sign * (final - actual)
    fits = set()
    for slots in combinations(range(4), len(vals)):
        cols = [0, 0, 0, 0]
        for s, v in zip(slots, vals):
            cols[s] = v
        if cols[3] == sign * (cols[1] - cols[2]):
            fits.add(tuple(cols))
    return fits.pop() if len(fits) == 1 else None


def parse_text(text: str, fy: int) -> tuple[list[DetailRow], int]:
    rows: list[DetailRow] = []
    unplaced = 0
    # Context carries across continuation pages, which repeat no titles.
    ctx = {"level": "", "fund_code": "", "fund": "", "agency_code": "", "agency": "",
           "account_code": "", "account": ""}
    section, function = "balance", ("", "")
    for page in text.split("\f"):
        lines = page.splitlines()
        try:
            start = next(i for i, l in enumerate(lines) if re.match(r"^\s*June 30, \d{4}\s*$", l))
        except StopIteration:
            continue
        titles: list[tuple[str, str]] = []
        for l in lines[start + 1:]:
            if (re.search(r"\b(Original|Budget|Final)\b|Exp\. Auth\.|\d,\d{3}", l)
                    or EXP_AUTH.match(l) or LINE.match(l)):
                break
            if l.strip():
                m = TITLE.match(l.strip())
                titles.append((m["code"] or "", m["name"].strip()))
        body = lines[start + 1:]
        if titles:
            fund_code, fund = titles[0]
            agency_code = agency = account_code = account = ""
            for code, name in titles[1:]:
                if re.fullmatch(r"\d{4}", code):
                    agency_code, agency = code, name
                else:
                    account_code, account = code, name
            ctx = {"level": "account" if account_code else "agency" if agency_code else "fund",
                   "fund_code": fund_code, "fund": fund, "agency_code": agency_code,
                   "agency": agency, "account_code": account_code, "account": account}
            section, function = "balance", ("", "")

        for l in body:
            low = l.strip().lower()
            if low in SECTIONS:
                section = SECTIONS[low]
                function = ("", "")
                continue
            if low.startswith("total"):
                function = ("", "")
                continue
            m = LINE.match(l)
            e = EXP_AUTH.match(l) if not m else None
            if not m and not e:
                lo = LABEL_ONLY.match(l)
                if lo and section == "charges":
                    function = (lo["code"], lo["label"].strip())
                continue
            if e:
                if not function[0]:
                    continue
                line_code, label, auth, rest = function[0], function[1], e["code"], e["rest"]
            else:
                line_code, label, auth, rest = m["code"], m["label"].strip(), "", m["rest"]
            tokens = TOKEN.findall(rest.replace("$", " "))
            if not tokens or len(tokens) > 4:
                continue
            placed = place(tokens, section)
            if placed is None:
                unplaced += 1
                continue
            rows.append(DetailRow(fy, _biennium(fy), ctx["level"], ctx["fund_code"], ctx["fund"],
                                  ctx["agency_code"], ctx["agency"], ctx["account_code"],
                                  ctx["account"], section, line_code, label, auth, *placed))
    return rows, unplaced


def reconcile(rows: list[DetailRow]) -> list[str]:
    """Fund-level lines should equal the sum of the deepest pages under them."""
    fund_level: dict[tuple, int] = {}
    leaf: dict[tuple, int] = defaultdict(int)
    has_account = {(r.fund_code, r.agency_code) for r in rows if r.level == "account"}
    for r in rows:
        key = (r.fund_code, r.section, r.line_code)
        if r.level == "fund":
            fund_level[key] = fund_level.get(key, 0) + r.actual
        elif r.level == "account" or (r.level == "agency" and (r.fund_code, r.agency_code) not in has_account):
            leaf[key] += r.actual
    issues = []
    for key, total in fund_level.items():
        if key[1] == "balance":
            continue
        if abs(leaf.get(key, 0) - total) > 1000:
            issues.append(f"{key}: fund page {total:,} vs detail {leaf.get(key, 0):,}")
    return issues


def run(years: tuple[int, ...] = (21, 23)) -> None:
    """Odd fiscal years close a biennium, so they are the complete record.

    Even years (mid-biennium snapshots) parse with the same code for FY2020 and
    FY2022; FY2024 uses a different layout that isn't handled yet.
    """
    for yy in years:
        fname = FILE_VARIANTS[yy]
        path = fetch(BASE + fname, "budget_to_actual", fname)
        rows, unplaced = parse_text(pdf_text(path), 2000 + yy)
        issues = reconcile(rows)
        funds = [r for r in rows if r.level == "fund"]
        rev = sum(r.actual for r in funds if r.section == "resources")
        spend = sum(r.actual for r in funds if r.section == "charges")
        print(f"FY20{yy}: {len(rows):,} rows, {unplaced} unplaced; fund-level resources ${rev/1e9:,.1f}B, "
              f"charges ${spend/1e9:,.1f}B; {len(issues)} reconciliation differences "
              f"(see data/samples/budget_to_actual_detail_fy20{yy}_reconciliation.csv)")
        write_csv(SAMPLES / f"budget_to_actual_detail_fy20{yy}_funds.csv", [asdict(r) for r in funds])
        write_csv(SAMPLES / f"budget_to_actual_detail_fy20{yy}_reconciliation.csv",
                  [{"issue": i} for i in issues], ["issue"])

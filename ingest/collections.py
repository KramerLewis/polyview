"""Monthly General Fund-State tax collections (ERFC Economic & Revenue Update).

Each monthly update (https://erfc.wa.gov/publications/monthly-economic-and-revenue-updates)
has a "Key Revenue Variables" table: collections by tax for the last 13 monthly
collection periods ($ thousands), and a "Revenue Forecast Variance" table comparing
the latest period, and the cumulative total since the last forecast, with the
forecast. We combine overlapping issues, newest first, so each month carries the
latest (possibly revised) figure. DECISIONS D-042.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .budget_to_actual import pdf_text
from .common import SAMPLES, fetch, write_csv

ERFC = "https://erfc.wa.gov/sites/default/files/"
# Newest first. Two issues a year apart cover the 2025-27 biennium so far plus the
# same months of 2023-25 for comparison.
ISSUES = [ERFC + "2026-10/oct26.pdf", ERFC + "2025-10/oct25.pdf", ERFC + "2025-03/oct24.pdf",
          ERFC + "2025-03/oct23.pdf"]

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
NUM = r"-?[\d,]+"
ROW = re.compile(rf"^(?P<indent>\s*)(?P<label>[A-Za-z][A-Za-z&()/,.\- ]*?[A-Za-z)*])\**\s{{2,}}(?P<nums>(?:{NUM}\s+)+{NUM})\s*$")


@dataclass
class Collection:
    issue: str
    period: str  # "YYYY-MM": month the collection period starts (e.g. Sep 11 - Oct 10 -> YYYY-09)
    line: str
    is_detail: bool
    amount: int  # dollars


@dataclass
class Variance:
    issue: str
    scope: str  # "latest period" | "cumulative since forecast"
    period_text: str
    line: str
    estimate: int
    actual: int


def _latest_period(text: str) -> tuple[int, int, str]:
    """From 'September 11 - October 10, 2026' under 'Revenue Forecast Variance'."""
    i = text.find("Revenue Forecast Variance")
    m = re.search(r"([A-Z][a-z]+) \d{1,2} - ([A-Z][a-z]+) \d{1,2}, (\d{4})", text[i:])
    start_month, end_month, year = MONTHS[m.group(1).lower()], MONTHS[m.group(2).lower()], int(m.group(3))
    start_year = year - 1 if start_month > end_month else year
    return start_year, start_month, m.group(0)


def _months_back(year: int, month: int, n: int) -> list[str]:
    out = []
    for k in range(n - 1, -1, -1):
        y, mth = year, month - k
        while mth <= 0:
            mth += 12
            y -= 1
        out.append(f"{y}-{mth:02d}")
    return out


def parse_issue(text: str, issue: str) -> tuple[list[Collection], list[Variance]]:
    y, m, period_text = _latest_period(text)
    start = text.find("Key Revenue Variables")
    end = text.find("Revenue Forecast Variance", start)
    block = text[start:end].splitlines()
    rows: list[Collection] = []
    base_indent = None
    for line in block:
        mm = ROW.match(line)
        if not mm:
            continue
        nums = mm["nums"].split()
        if any("." in x for x in nums) or len(nums) < 12:
            continue  # year-over-year % rows
        label = mm["label"].strip()
        if label.lower().startswith("change in amount"):
            continue
        indent = len(mm["indent"])
        base_indent = indent if base_indent is None else min(base_indent, indent)
        periods = _months_back(y, m, len(nums))
        for p, v in zip(periods, nums):
            rows.append(Collection(issue, p, label, indent > base_indent + 2, int(v.replace(",", "")) * 1000))

    variances: list[Variance] = []
    vtext = text[end:]
    scopes = [("latest period", vtext.find("Compared to the")),
              ("cumulative since forecast", vtext.find("Cumulative Variance"))]
    for (scope, s0), (_, s1) in zip(scopes, scopes[1:] + [("", vtext.find("\n1 Collections"))]):
        for line in vtext[s0:s1 if s1 > s0 else None].splitlines():
            mm = re.match(r"^\s*(?P<label>[A-Za-z][^$\d(]*?)\s*(?:\(\d\))?\s+\$?(?P<est>\(?[\d,]+\)?)\s+\$?(?P<act>\(?[\d,]+\)?)\s+", line)
            if mm and "Total General Fund-State" in mm["label"] or (mm and mm["label"].strip().startswith(("Department of Revenue", "Revenue Act", "Non-Revenue Act"))):
                val = lambda s: -int(s.strip("()").replace(",", "")) * 1000 if s.startswith("(") else int(s.replace(",", "")) * 1000  # noqa: E731
                variances.append(Variance(issue, scope, period_text, mm["label"].replace("*", "").strip(),
                                          val(mm["est"]), val(mm["act"])))
    return rows, variances


def issue_urls() -> list[str]:
    """Newest issues found on ERFC's site (D-043), falling back to the pinned list."""
    try:
        from .discover import collection_issues
        found = collection_issues()
        if found:
            return found
    except Exception as e:  # ERFC down: use what we know
        print(f"  collections: discovery failed ({e}); using pinned issues")
    return ISSUES


def load() -> tuple[list[Collection], list[Variance]]:
    """Combine issues; the newest issue's figure wins for each (period, line)."""
    seen: set[tuple[str, str]] = set()
    rows: list[Collection] = []
    latest_variances: list[Variance] = []
    for i, url in enumerate(issue_urls()):
        path = fetch(url, "collections", url.rsplit("/", 1)[-1])
        issue_rows, variances = parse_issue(pdf_text(path), url.rsplit("/", 1)[-1])
        if i == 0:
            latest_variances = variances
        for r in issue_rows:
            if (r.period, r.line) not in seen:
                seen.add((r.period, r.line))
                rows.append(r)
    rows.sort(key=lambda r: (r.period, r.line))
    return rows, latest_variances


def check(rows: list[Collection]) -> list[str]:
    """Revenue Act + Non-Revenue Act must equal the DOR total for every month."""
    by = {(r.period, r.line): r.amount for r in rows}
    issues = []
    for p in sorted({r.period for r in rows}):
        dor, ra, nra = (by.get((p, k)) for k in ("Department of Revenue-Total", "Revenue Act", "Non-Revenue Act"))
        if None not in (dor, ra, nra) and abs(dor - ra - nra) > 2000:
            issues.append(f"{p}: DOR {dor:,} != RA {ra:,} + non-RA {nra:,}")
    return issues


def run() -> None:
    rows, variances = load()
    problems = check(rows)
    totals = {r.period: r.amount for r in rows if r.line == "Total General Fund-State"}
    months = sorted(totals)
    print(f"collections: {len(months)} months ({months[0]} to {months[-1]}), {len(rows)} values; "
          f"{len(problems)} arithmetic problems; latest variance rows: {len(variances)}")
    for p in problems[:5]:
        print("  ", p)
    if problems:
        raise ValueError("collections arithmetic doesn't hold")
    write_csv(SAMPLES / "gfs_collections.csv", [asdict(r) for r in rows])
    write_csv(SAMPLES / "gfs_collections_variance.csv", [asdict(v) for v in variances])

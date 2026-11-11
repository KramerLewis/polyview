"""Find newly published source files, so the weekly build stays current.

Two kinds of source (DECISIONS D-043):
- **Auto**: safe to pick up without a person, because the parser checks its own
  arithmetic: ERFC monthly collection reports and adopted budget outlooks. New
  files are used automatically; if one fails its checks, it is skipped and
  reported.
- **Attention**: a new file exists but a person has to wire it in: a new enacted
  budget bill (its amendment chain must be configured), a new OFM Budget-to-Actual
  report (layouts change), or a newer LEAP district project list (needs a browser).

`run()` writes data/samples/freshness.json. The Pages workflow turns any
"attention" items, and any failed step, into a GitHub issue.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .common import SAMPLES, USER_AGENT

ERFC_BASE = "https://erfc.wa.gov"
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read().decode("utf-8", "ignore")


def _links(html: str, pattern: str) -> list[str]:
    return sorted({h for h in re.findall(r'href="([^"]+)"', html) if re.search(pattern, h, re.I)})


def _abs(href: str, base: str) -> str:
    return href if href.startswith("http") else base + href


# --- ERFC monthly Economic & Revenue Updates -------------------------------
def monthly_issues() -> dict[tuple[int, int], str]:
    """{(year, month): url} for every monthly update ERFC lists."""
    out: dict[tuple[int, int], str] = {}
    for page in ("/publications/monthly-economic-and-revenue-updates", "/publications/publications-archives"):
        for href in _links(_get(ERFC_BASE + page), r"/(%s)\d\d\.pdf$" % "|".join(MONTHS)):
            m = re.search(r"/([a-z]{3})(\d\d)\.pdf$", href, re.I)
            out[(2000 + int(m.group(2)), MONTHS.index(m.group(1).lower()) + 1)] = _abs(href, ERFC_BASE)
    return out


def collection_issues(n_years: int = 4) -> list[str]:
    """Latest issue and the ones 12, 24, 36 months earlier (each covers 13 months)."""
    issues = monthly_issues()
    if not issues:
        return []
    y, m = max(issues)
    picks = []
    for k in range(n_years):
        url = issues.get((y - k, m))
        if url:
            picks.append(url)
    return picks


# --- ERFC adopted budget outlooks -------------------------------------------
OUTLOOK_EXCLUDE = re.compile(r"metho|alternativ|_alt|guidance|memo|growth|handout|meeting|assum|presentation", re.I)


def is_enacted_outlook(filename: str) -> bool:
    return "enact" in filename.lower() and not OUTLOOK_EXCLUDE.search(filename)


def enacted_outlooks(since_year: int = 2023) -> list[str]:
    """Outlooks adopted for enacted budgets (not proposals, methodology or alternatives)."""
    found = set()
    for page in ("/budget-outlook", "/budget-outlook/budget-outlook-archives"):
        for href in _links(_get(ERFC_BASE + page), r"\.pdf$"):
            name = urllib.parse.unquote(href.rsplit("/", 1)[-1])
            if not is_enacted_outlook(name):
                continue
            year = re.search(r"(20\d\d)", name) or re.search(r"/(20\d\d)-\d\d/", href)
            if year and int(year.group(1)) >= since_year:
                found.add(_abs(href, ERFC_BASE))

    def when(url: str) -> str:
        n = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        d = re.search(r"(20\d\d)(\d\d)(\d\d)", n)
        if d:
            return d.group(0)
        y = re.search(r"(20\d\d)", n)
        return (y.group(1) + "0600") if y else n  # undated names: mid-year
    return sorted(found, key=when)


# --- Attention items --------------------------------------------------------
def enacted_budget_bills() -> set[str]:
    """Bill numbers of enacted budgets fiscal.wa.gov lists for recent bienniums."""
    html = _get("https://fiscal.wa.gov/StateBudgets/AllBudgetsEnactedBills.aspx")
    nums = re.findall(r"biennium/20(?:2[3-9]|3\d)-\d\d/Pdf/Bills/Session%20Laws/[A-Za-z]+/(\d{4})-", html)
    return set(nums)


def budget_to_actual_reports() -> list[str]:
    html = _get("https://ofm.wa.gov/spending/financial-audit-reports/annual-comprehensive-financial-report/")
    return _links(html, r"FY\d\d_Washington_State_Budget-to-Actual")


def run() -> dict:
    from .budget_bills import BUDGET_BILLS
    from .budget_to_actual import FILE_VARIANTS
    from . import collections as coll_mod, outlook as outlook_mod

    report: dict = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                    "auto": [], "attention": [], "errors": []}

    def guard(name, fn):
        try:
            return fn()
        except Exception as e:  # a site being down must not stop the build
            report["errors"].append(f"{name}: {type(e).__name__}: {e}")
            return None

    issues = guard("ERFC monthly updates", collection_issues)
    if issues:
        new = [u for u in issues if u not in coll_mod.ISSUES]
        report["auto"].append({"source": "ERFC monthly collections", "using": issues, "new": new})
    outlooks = guard("ERFC outlooks", enacted_outlooks)
    if outlooks:
        known = {u for _, u in outlook_mod.OUTLOOKS}
        new = [u for u in outlooks if u not in known]
        report["auto"].append({"source": "ERFC adopted outlooks", "found": outlooks, "new": new})

    bills = guard("enacted budget bills", enacted_budget_bills)
    if bills:
        configured = {n for _, _, n, _, _ in BUDGET_BILLS}
        for n in sorted(bills - configured - {"1148", "5194"}):  # bond-authorization bills, no appropriations
            report["attention"].append({
                "source": "Enacted budget bills",
                "what": f"Enacted budget bill {n} is listed on fiscal.wa.gov but not configured",
                "action": "Add it to BUDGET_BILLS in ingest/budget_bills.py and its amendment chain "
                          "in ingest/budget_current.py; add a reference check (DECISIONS D-017, D-037)."})
    reports = guard("OFM Budget-to-Actual", budget_to_actual_reports)
    if reports:
        known = set(FILE_VARIANTS.values())
        for href in reports:
            name = href.rsplit("/", 1)[-1]
            if name not in known:
                report["attention"].append({
                    "source": "OFM Budget-to-Actual report",
                    "what": f"New report published: {name}",
                    "action": "Check its layout, add it to FILE_VARIANTS in ingest/budget_to_actual.py, "
                              "and make sure its subtotal checks pass (DECISIONS D-002, D-010)."})

    (SAMPLES / "freshness.json").write_text(json.dumps(report, indent=1))
    print(f"discover: {len(report['auto'])} auto sources, {len(report['attention'])} need attention, "
          f"{len(report['errors'])} errors")
    for a in report["attention"]:
        print("  ATTENTION", a["what"])
    for e in report["errors"]:
        print("  ERROR", e)
    return report

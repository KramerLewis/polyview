"""Build the *current* enacted budget: original budget overlaid with supplementals.

A supplemental budget reprints only the sections it changes ("2025 c 424 s 102
is amended to read…"), striking old amounts and adding new ones. The current
budget is every original line, replaced by the latest supplemental version
where one exists, plus any lines or sections the supplemental adds.

Self-check: each supplemental line's struck ("prior") amount should equal the
original enacted amount for that line. Mismatches mean an intermediate
amendment we don't know about, or a matching error, and are reported.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .budget_bills import Appropriation, parse_bill
from .common import RAW, SAMPLES, write_csv

# (biennium, original bill, original chapter, [(supplemental bill, label), ...])
BUDGETS = [
    ("2025-27", "5167", "2025 c 424", [("5998", "2026 supplemental")]),
]


def _norm(account: str) -> str:
    """Normalize an account line so the same line matches across bills
    (bills differ in dashes, apostrophes, hyphenation and line breaks)."""
    # Transfer lines embed their amounts in the text ("…$6,880,000 for fiscal
    # year 2026…"); drop those so an amended amount still matches its line.
    account = re.sub(r"\$[\d,]+|fiscal year \d{4}", "", account.lower())
    return re.sub(r"[^a-z]", "", account)


def _keyed(lines: list[Appropriation], section_of) -> list[tuple[tuple[str, str, int], Appropriation]]:
    """Key = (section, normalized account, n-th occurrence within the section).

    Some sections (e.g. DSHS programs) contain several appropriation blocks
    with the same account names; occurrence order tells them apart.
    """
    seen: Counter = Counter()
    out = []
    for a in lines:
        sec = section_of(a)
        base = (sec, _norm(a.account))
        out.append(((*base, seen[base]), a))
        seen[base] += 1
    return out


def overlay(biennium: str, original: list[Appropriation], chapter: str,
            supplementals: list[tuple[str, list[Appropriation]]]) -> tuple[list[dict], list[str]]:
    rows: dict[tuple, dict] = {}
    order: list[tuple] = []
    base = [a for a in original if a.biennium == biennium and a.section_type == "new"]
    for k, a in _keyed(base, lambda a: a.section):
        rows[k] = {
            "biennium": biennium, "section": a.section, "agency_code": a.agency_code,
            "department": a.department, "account": a.account, "kind": a.kind,
            "fund": a.fund, "fund_source": a.fund_source, "fiscal_year": a.fiscal_year,
            "original": a.amount or 0, "original_vetoed": a.vetoed,
        }
        order.append(k)

    issues: list[str] = []
    sec_re = re.compile(rf"^{re.escape(chapter)} s (\d+)$")
    for label, supp in supplementals:
        col = f"after_{label.replace(' ', '_')}"
        changed_sections = set()

        def section_of(a: Appropriation) -> str:
            m = sec_re.match(a.amends)
            return m.group(1) if m else f"{label}:{a.section}"

        for k, a in _keyed([a for a in supp if a.biennium == biennium], section_of):
            section = k[0]
            changed_sections.add(section)
            if k not in rows:
                rows[k] = {
                    "biennium": biennium, "section": section, "agency_code": a.agency_code,
                    "department": a.department, "account": a.account, "kind": a.kind,
                    "fund": a.fund, "fund_source": a.fund_source, "fiscal_year": a.fiscal_year,
                    "original": 0, "original_vetoed": False,
                }
                order.append(k)
                if a.prior_amount:
                    issues.append(f"{label} sec {section} '{a.account}': prior "
                                  f"{a.prior_amount:,} but no matching original line")
            else:
                prev = rows[k].get("_latest", rows[k]["original"])
                if a.prior_amount is not None and a.prior_amount != prev:
                    issues.append(f"{label} sec {section} '{a.account}': prior "
                                  f"{a.prior_amount:,} != enacted {prev:,}")
            rows[k][col] = a.amount or 0
            rows[k][f"{col}_vetoed"] = a.vetoed
            rows[k]["_latest"] = 0 if a.vetoed else (a.amount or 0)
        # Lines in a reprinted section that the supplemental dropped entirely.
        for k in order:
            if k[0] in changed_sections and col not in rows[k]:
                rows[k][col] = 0
                rows[k]["_latest"] = 0
                issues.append(f"{label} sec {k[0]} '{rows[k]['account']}': not in reprinted section "
                              f"(treated as removed)")

    out = []
    for k in order:
        r = rows[k]
        latest = r.pop("_latest", None)
        r["current"] = (0 if r["original_vetoed"] else r["original"]) if latest is None else latest
        r["changed"] = r["current"] != r["original"]
        out.append(r)
    return out, issues


def run() -> None:
    for biennium, orig_bill, chapter, supps in BUDGETS:
        orig, _ = parse_bill(RAW / "budget_bills" / f"{orig_bill}-S.SL.xml", orig_bill, biennium)
        parsed = [(label, parse_bill(RAW / "budget_bills" / f"{b}-S.SL.xml", b, biennium)[0])
                  for b, label in supps]
        rows, issues = overlay(biennium, orig, chapter, parsed)
        approps = [r for r in rows if r["kind"] == "appropriation"]
        print(f"{biennium}: {len(rows)} lines ({Counter(r['kind'] for r in rows)}); "
              f"agency appropriations original ${sum(r['original'] for r in approps)/1e9:,.2f}B "
              f"-> current ${sum(r['current'] for r in approps)/1e9:,.2f}B; "
              f"{sum(r['changed'] for r in rows)} lines changed; {len(issues)} issues")
        for i in issues[:15]:
            print("  ", i)
        cols = ["biennium", "section", "agency_code", "department", "account", "kind", "fund",
                "fund_source", "fiscal_year", "original", "original_vetoed"]
        extra = sorted({c for r in rows for c in r} - set(cols) - {"current", "changed"})
        write_csv(SAMPLES / f"budget_current_{biennium}.csv", rows,
                  cols + extra + ["current", "changed"])
        write_csv(SAMPLES / f"budget_current_{biennium}_issues.csv",
                  [{"issue": i} for i in issues], ["issue"])

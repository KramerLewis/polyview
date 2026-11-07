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

from .budget_bills import BUDGET_BILLS, Appropriation, chapter_of, parse_bill

BILL_BIENNIUM = {number: budget_biennium for _, _, number, budget_biennium, _ in BUDGET_BILLS}
from .common import RAW, SAMPLES, write_csv

# (biennium, budget, original bill, chapters in the amendment chain, [(supplemental bill, label), ...])
# A supplemental's amendatory section cites the chapter it amends: the original
# act or an earlier supplemental ("2024 c 376 s 101" amends sec. 101 as last
# amended by the 2024 supplemental). Any chapter in the chain maps to that section.
BUDGETS = [
    ("2025-27", "operating", "5167", ["2025 c 424"], [("5998", "2026 supplemental")]),
    ("2025-27", "transportation", "5161", ["2025 c 416"], [("6005", "2026 supplemental")]),
    ("2025-27", "capital", "5195", ["2025 c 414"], [("6003", "2026 supplemental")]),
    ("2023-25", "operating", "5187", ["2023 c 475", "2024 c 376"],
     [("5950", "2024 supplemental"), ("5167", "2025 supplemental")]),
    ("2023-25", "transportation", "1125", ["2023 c 472", "2024 c 310"],
     [("2134", "2024 supplemental"), ("5161", "2025 supplemental")]),
    ("2023-25", "capital", "5200", ["2023 c 474", "2024 c 375"],
     [("5949", "2024 supplemental"), ("5195", "2025 supplemental")]),
]


def _norm(account: str) -> str:
    """Normalize an account line so the same line matches across bills
    (bills differ in dashes, apostrophes, hyphenation and line breaks)."""
    # Transfer lines embed their amounts in the text ("…$6,880,000 for fiscal
    # year 2026…"); drop those so an amended amount still matches its line.
    account = re.sub(r"\$[\d,]+|fiscal year \d{4}", "", account.lower())
    return re.sub(r"[^a-z]", "", account)


def _keyed(lines: list[Appropriation], section_of) -> list[tuple[tuple[str, str, int], Appropriation]]:
    """Key = (section, capital project, normalized account, n-th occurrence).

    Some sections (e.g. DSHS programs) contain several appropriation blocks
    with the same account names; occurrence order tells them apart.
    """
    seen: Counter = Counter()
    out = []
    for a in lines:
        sec = section_of(a)
        base = (sec, a.project, _norm(a.account))
        out.append(((*base, seen[base]), a))
        seen[base] += 1
    return out


def overlay(biennium: str, original: list[Appropriation], chapters: str | list[str],
            supplementals: list[tuple]) -> tuple[list[dict], list[str]]:
    """supplementals: [(label, lines) or (label, lines, own_chapter), ...] in enactment order.

    A supplemental's own chapter lets later bills that cite *its* section numbers
    ("2024 c 376 s 112") be translated back to the original section.
    """
    rows: dict[tuple, dict] = {}
    order: list[tuple] = []
    base = [a for a in original if a.biennium == biennium and a.section_type == "new"]
    for k, a in _keyed(base, lambda a: a.section):
        rows[k] = {
            "biennium": biennium, "section": a.section, "agency_code": a.agency_code,
            "department": a.department, "project": a.project, "project_name": a.project_name,
            "account": a.account, "kind": a.kind,
            "fund": a.fund, "fund_source": a.fund_source, "fiscal_year": a.fiscal_year,
            "original": a.amount or 0, "original_vetoed": a.vetoed,
        }
        order.append(k)

    issues: list[str] = []
    if isinstance(chapters, str):
        chapters = [chapters]
    # (chapter, section as numbered in that chapter) -> original section key.
    # The original act's chapter maps sections to themselves.
    sec_map: dict[tuple[str, str], str] = {}
    original_chapter = chapters[0]
    cite_re = re.compile(r"^(\d{4} c \d+) s (\d+)$")

    for entry in supplementals:
        label, supp = entry[0], entry[1]
        own_chapter = entry[2] if len(entry) > 2 else ""
        col = f"after_{label.replace(' ', '_')}"
        changed_sections = set()

        def section_of(a: Appropriation) -> str:
            m = cite_re.match(a.amends)
            if m:
                chap, sec = m.group(1), m.group(2)
                if chap == original_chapter:
                    target = sec
                elif (chap, sec) in sec_map:
                    target = sec_map[(chap, sec)]
                elif chap in chapters:
                    target = sec  # chain chapter we have no section map for: assume same numbering
                else:
                    target = f"{label}:{a.section}"
            else:
                target = f"{label}:{a.section}"
            if own_chapter:
                sec_map[(own_chapter, a.section)] = target
            return target

        for k, a in _keyed([a for a in supp if a.biennium == biennium], section_of):
            section = k[0]
            changed_sections.add(section)
            if k not in rows:
                rows[k] = {
                    "biennium": biennium, "section": section, "agency_code": a.agency_code,
                    "department": a.department, "project": a.project,
                    "project_name": a.project_name, "account": a.account, "kind": a.kind,
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


def build_all() -> tuple[list[dict], dict[str, list[str]]]:
    """Overlay every budget in BUDGETS; rows carry a 'budget' column."""
    all_rows: list[dict] = []
    all_issues: dict[str, list[str]] = {}
    for biennium, budget, orig_bill, chapters, supps in BUDGETS:
        orig, _ = parse_bill(RAW / "budget_bills" / f"{orig_bill}-S.SL.xml", orig_bill, biennium)
        # Parse each bill with *its own* budget biennium: a 2025 bill that amends
        # 2023-25 sections also has new 2025-27 sections, which must not be
        # mistaken for 2023-25 lines.
        parsed = [(label, parse_bill(RAW / "budget_bills" / f"{b}-S.SL.xml", b, BILL_BIENNIUM[b])[0],
                   chapter_of(RAW / "budget_bills" / f"{b}-S.SL.xml"))
                  for b, label in supps]
        rows, issues = overlay(biennium, orig, chapters, parsed)
        for r in rows:
            r["budget"] = budget
        all_rows.extend(rows)
        all_issues[f"{biennium} {budget}"] = issues
    return all_rows, all_issues


def run() -> None:
    rows, issues = build_all()
    for (biennium, budget, *_rest) in BUDGETS:
        sub = [r for r in rows if r["biennium"] == biennium and r["budget"] == budget]
        new = [r for r in sub if r["kind"] == "appropriation"]
        print(f"{biennium} {budget}: {len(sub)} lines ({dict(Counter(r['kind'] for r in sub))}); "
              f"new appropriations ${sum(r['original'] for r in new)/1e9:,.2f}B original -> "
              f"${sum(r['current'] for r in new)/1e9:,.2f}B current; "
              f"{len(issues[f'{biennium} {budget}'])} issues")
    cols = ["biennium", "budget", "section", "agency_code", "department", "project", "project_name",
            "account", "kind", "fund", "fund_source", "fiscal_year", "original", "original_vetoed"]
    extra = sorted({c for r in rows for c in r} - set(cols) - {"current", "changed"})
    for biennium in sorted({r["biennium"] for r in rows}):
        write_csv(SAMPLES / f"budget_current_{biennium}.csv",
                  [r for r in rows if r["biennium"] == biennium], cols + extra + ["current", "changed"])
    write_csv(SAMPLES / "budget_current_issues.csv",
              [{"budget": k, "issue": i} for k, v in issues.items() for i in v], ["budget", "issue"])

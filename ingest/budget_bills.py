"""Parse enacted budget bills (session-law XML) into appropriation and proviso rows.

The Legislature publishes every bill as structured XML at
https://lawfilesext.leg.wa.gov/biennium/<YYYY-YY>/Xml/... . Budget bills use
<Appropriations agency="NNN"> blocks with one <Appropriation> per account line,
so no PDF scraping is needed.

Supplemental budgets amend earlier sections. In those, each changed line shows
the old amount (amendingStyle="strike") followed by a line with an empty
account name and the new amount (amendingStyle="add"). We emit both
``prior_amount`` and ``amount`` so the supplemental change is preserved.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

from .common import SAMPLES, dollars, fetch, write_csv

NS = "{http://leg.wa.gov/2012/document}"
BLOCK_TAGS = {f"{NS}BudgetP", f"{NS}P"}
LAWFILES = "https://lawfilesext.leg.wa.gov/biennium"

# Enacted operating budgets and supplementals we know about. Extend for backfill.
# (legislative biennium, chamber, bill number, budget biennium, label)
OPERATING_BUDGETS = [
    ("2025-26", "Senate", "5167", "2025-27", "2025-27 operating budget (original)"),
    ("2025-26", "Senate", "5998", "2025-27", "2026 supplemental operating budget"),
]

# Session-law chapters of enacted operating budgets -> the biennium they fund.
# Amendatory sections cite the chapter they amend (e.g. "2024 c 376 s 101").
CHAPTER_BIENNIUM = {
    "2023 c 475": "2023-25",  # 2023-25 operating budget (SSB 5187)
    "2024 c 376": "2023-25",  # 2024 supplemental (ESSB 5950)
    "2025 c 424": "2025-27",  # 2025-27 operating budget (ESSB 5167)
}

ACCOUNT_RE = re.compile(
    r"^(?P<fund>.+?)\s*[—-]\s*(?P<source>[A-Za-z/ ]+?)\s+Appropriation"
    r"(?:\s*\(FY\s*(?P<fy>\d{4})\))?\s*$"
)
PROVISO_RE = re.compile(
    r"\$(?P<amount>[\d,]+) of the (?P<account>.+?) appropriation"
    r"(?: for fiscal year (?P<fy>\d{4}))?(?P<solely> is provided solely)?",
    re.IGNORECASE,
)


@dataclass
class Appropriation:
    bill: str
    section: str
    section_type: str
    amends: str
    biennium: str
    agency_code: str
    department: str
    account: str
    fund: str
    fund_source: str
    fiscal_year: str
    prior_amount: int | None
    amount: int | None


@dataclass
class Proviso:
    bill: str
    section: str
    agency_code: str
    department: str
    amount: int
    account: str
    fiscal_year: str
    solely_for: bool
    text: str


def _text(el: ET.Element | None, *, skip_struck: bool = True) -> str:
    """Concatenate text under ``el``, dropping struck-out runs."""
    if el is None:
        return ""
    parts: list[str] = []

    def walk(node: ET.Element) -> None:
        if skip_struck and node.get("amendingStyle") == "strike":
            if node.tail:
                parts.append(node.tail)
            return
        if node.tag in BLOCK_TAGS:
            parts.append(" ")
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
        if node is not el and node.tail:
            parts.append(node.tail)

    walk(el)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _amounts(dollar_el: ET.Element | None) -> tuple[int | None, int | None]:
    """Return (struck_amount, current_amount) for a <DollarAmount>."""
    if dollar_el is None:
        return None, None
    runs = dollar_el.findall(f"{NS}TextRun")
    struck = next((r.text for r in runs if r.get("amendingStyle") == "strike"), None)
    added = next((r.text for r in runs if r.get("amendingStyle") == "add"), None)
    plain = dollar_el.text if dollar_el.text and dollar_el.text.strip() else None
    if plain is None and not struck and not added:
        plain = _text(dollar_el)
    return dollars(struck), dollars(added or plain)


def _biennium(fy: str) -> str:
    """Fiscal year 2026 (July 2025-June 2026) -> '2025-27'."""
    if not fy:
        return ""
    y = int(fy)
    start = y - 1 if y % 2 == 0 else y - 2
    return f"{start}-{str(start + 2)[-2:]}"


def parse_account(account: str) -> tuple[str, str, str]:
    m = ACCOUNT_RE.match(account)
    if not m:
        return account, "", ""
    return m["fund"].strip(), m["source"].strip(), m["fy"] or ""


def parse_bill(xml_path: Path, bill: str, budget_biennium: str = ""
               ) -> tuple[list[Appropriation], list[Proviso]]:
    root = ET.parse(xml_path).getroot()
    approps: list[Appropriation] = []
    provisos: list[Proviso] = []

    for sec in root.iter(f"{NS}BillSection"):
        header = sec.find(f"{NS}BillSectionHeader")
        if header is None:
            continue
        section = _text(header.find(f"{NS}BillSectionNumber/{NS}Value"))
        dept_el = header.find(f"{NS}Department/{NS}DeptName")
        department = re.sub(r"^FOR THE\s+", "", _text(dept_el), flags=re.I)
        blocks = sec.findall(f"{NS}Appropriations")
        if not blocks:
            continue
        agency = blocks[0].get("agency", "")
        amends = _text(header.find(f"{NS}UncodCite"))
        first_new = len(approps)

        for block in blocks:
            pending: Appropriation | None = None
            for ap in block.findall(f"{NS}Appropriation"):
                account = _text(ap.find(f"{NS}AccountName"))
                struck, current = _amounts(ap.find(f"{NS}DollarAmount"))
                if not account and pending is not None:
                    # Continuation line carrying the amended amount.
                    pending.amount = current
                    continue
                fund, source, fy = parse_account(account)
                row = Appropriation(
                    bill=bill, section=section, section_type=sec.get("type", ""),
                    amends=amends, biennium=_biennium(fy),
                    agency_code=block.get("agency", agency), department=department,
                    account=account, fund=fund, fund_source=source, fiscal_year=fy,
                    prior_amount=struck if struck is not None else (
                        current if sec.get("type") == "amendatory" else None),
                    amount=current if struck is None else None,
                )
                if struck is not None:
                    row.amount = 0  # struck with no replacement = removed
                approps.append(row)
                pending = row

        # Lines without "(FY ...)" are biennial: take the biennium of the
        # chapter this section amends, or the bill's own biennium if it's new.
        chapter = re.sub(r"\s+s\s+\d+.*$", "", amends)
        section_biennium = CHAPTER_BIENNIUM.get(chapter, "") if amends else budget_biennium
        for a in approps[first_new:]:
            a.biennium = a.biennium or section_biennium

        for p in sec.findall(f"{NS}P"):
            text = _text(p)
            for m in PROVISO_RE.finditer(text):
                provisos.append(Proviso(
                    bill=bill, section=section, agency_code=agency,
                    department=department, amount=dollars(m["amount"]) or 0,
                    account=m["account"], fiscal_year=m["fy"] or "",
                    solely_for=bool(m["solely"]), text=text[:1000],
                ))
    return approps, provisos


def run(sample_rows: int = 400) -> None:
    for biennium, chamber, number, budget_biennium, label in OPERATING_BUDGETS:
        url = f"{LAWFILES}/{biennium}/Xml/Bills/Session%20Laws/{chamber}/{number}-S.SL.xml"
        path = fetch(url, "budget_bills", f"{number}-S.SL.xml")
        approps, provisos = parse_bill(path, f"{number}-S.SL", budget_biennium)
        totals: dict[str, int] = {}
        for a in approps:
            totals[a.biennium or "unknown"] = totals.get(a.biennium or "unknown", 0) + (a.amount or 0)
        by_bien = ", ".join(f"{k}: ${v:,}" for k, v in sorted(totals.items()))
        print(f"{label}: {len(approps)} appropriation lines, {len(provisos)} provisos; "
              f"line totals by biennium funded: {by_bien}")
        write_csv(SAMPLES / f"appropriations_{number}.csv",
                  [asdict(a) for a in approps[:sample_rows]])
        write_csv(SAMPLES / f"provisos_{number}.csv",
                  [asdict(p) for p in provisos[:sample_rows // 4]])

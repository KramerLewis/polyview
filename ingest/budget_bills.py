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

# Enacted budget bills we know about. Extend for backfill.
# (legislative biennium, chamber, bill number, budget biennium, label)
BUDGET_BILLS = [
    ("2025-26", "Senate", "5167", "2025-27", "2025-27 operating budget (original)"),
    ("2025-26", "Senate", "5998", "2025-27", "2026 supplemental operating budget"),
    ("2025-26", "Senate", "5161", "2025-27", "2025-27 transportation budget (original)"),
    ("2025-26", "Senate", "6005", "2025-27", "2026 supplemental transportation budget"),
    ("2025-26", "Senate", "5195", "2025-27", "2025-27 capital budget (original)"),
    ("2025-26", "Senate", "6003", "2025-27", "2026 supplemental capital budget"),
    ("2023-24", "Senate", "5187", "2023-25", "2023-25 operating budget (original)"),
    ("2023-24", "Senate", "5950", "2023-25", "2024 supplemental operating budget"),
    ("2023-24", "House", "1125", "2023-25", "2023-25 transportation budget (original)"),
    ("2023-24", "House", "2134", "2023-25", "2024 supplemental transportation budget"),
    ("2023-24", "Senate", "5200", "2023-25", "2023-25 capital budget (original)"),
    ("2023-24", "Senate", "5949", "2023-25", "2024 supplemental capital budget"),
    ("2021-22", "Senate", "5092", "2021-23", "2021-23 operating budget (original)"),
    ("2021-22", "Senate", "5693", "2021-23", "2022 supplemental operating budget"),
    ("2021-22", "Senate", "5165", "2021-23", "2021-23 transportation budget (original)"),
    ("2021-22", "Senate", "5689", "2021-23", "2022 supplemental transportation budget"),
    ("2021-22", "Senate", "5975", "2021-23", "2022 additive transportation budget (Move Ahead WA)"),
    ("2021-22", "House", "1080", "2021-23", "2021-23 capital budget (original)"),
    ("2021-22", "Senate", "5651", "2021-23", "2022 supplemental capital budget"),
    ("2019-20", "House", "1109", "2019-21", "2019-21 operating budget (original)"),
    ("2019-20", "Senate", "6168", "2019-21", "2020 supplemental operating budget"),
    ("2019-20", "House", "1160", "2019-21", "2019-21 transportation budget (original)"),
    ("2019-20", "House", "2322", "2019-21", "2020 supplemental transportation budget"),
    ("2019-20", "House", "1102", "2019-21", "2019-21 capital budget (original)"),
    ("2019-20", "Senate", "6248", "2019-21", "2020 supplemental capital budget"),
]

# Session-law chapters of enacted operating budgets -> the biennium they fund.
# Amendatory sections cite the chapter they amend (e.g. "2024 c 376 s 101").
CHAPTER_BIENNIUM = {
    "2019 c 415": "2019-21", "2020 c 357": "2019-21",  # operating 1109, 6168
    "2019 c 416": "2019-21", "2020 c 219": "2019-21",  # transportation 1160, 2322
    "2019 c 413": "2019-21", "2020 c 356": "2019-21",  # capital 1102, 6248
    "2021 c 334": "2021-23", "2022 c 297": "2021-23",  # operating 5092, 5693
    "2021 c 333": "2021-23", "2022 c 186": "2021-23", "2022 c 187": "2021-23",  # transportation 5165, 5689, 5975
    "2021 c 332": "2021-23", "2022 c 296": "2021-23",  # capital 1080, 5651
    "2023 c 475": "2023-25",  # 2023-25 operating budget (SSB 5187)
    "2024 c 376": "2023-25",  # 2024 supplemental (ESSB 5950)
    "2023 c 472": "2023-25",  # 2023-25 transportation budget (ESHB 1125)
    "2024 c 310": "2023-25",  # 2024 supplemental transportation (ESHB 2134)
    "2023 c 474": "2023-25",  # 2023-25 capital budget (ESSB 5200)
    "2024 c 375": "2023-25",  # 2024 supplemental capital (ESSB 5949)
    "2025 c 424": "2025-27",  # 2025-27 operating budget (ESSB 5167)
    "2025 c 416": "2025-27",  # 2025-27 transportation budget (ESSB 5161)
    "2025 c 414": "2025-27",  # 2025-27 capital budget (ESSB 5195)
}

ACCOUNT_RE = re.compile(
    r"^(?P<fund>.+?)\s*[—-]\s*(?P<source>[A-Za-z/ ]+?)(?:\s+Appropriation)?"
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
    kind: str  # appropriation | distribution | transfer | reappropriation | capital_context
    fund: str
    fund_source: str
    fiscal_year: str
    prior_amount: int | None
    amount: int | None
    vetoed: bool
    project: str = ""  # capital budget project number (from the printed name when present)
    project_name: str = ""
    xml_conflict: bool = False  # the XML's hidden project attribute disagrees with the printed text


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
    vetoed: bool
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


def _is_vetoed(el: ET.Element) -> bool:
    """The governor's line-item vetoes are marked lineVeto="yes" on text runs."""
    return any(r.get("lineVeto") == "yes" for r in el.iter(f"{NS}TextRun"))


def _amounts(dollar_el: ET.Element | None) -> tuple[int | None, int | None, bool]:
    """Return (struck_amount, current_amount, added_only) for a <DollarAmount>.

    added_only means the amount is new text with nothing struck, i.e. a line
    the amending bill adds (its prior amount is zero).
    """
    if dollar_el is None:
        return None, None, False
    runs = list(dollar_el.iter(f"{NS}TextRun"))
    struck = next((r.text for r in runs if r.get("amendingStyle") == "strike"), None)
    added = next((r.text for r in runs if r.get("amendingStyle") == "add"), None)
    plain = dollar_el.text if dollar_el.text and dollar_el.text.strip() else None
    if plain is None and not struck and not added:
        plain = _text(dollar_el)
    if not struck and not added and plain and not plain.startswith("$"):
        plain = None
    return dollars(struck), dollars(added or plain), bool(added and not struck)


def _biennium(fy: str) -> str:
    """Fiscal year 2026 (July 2025-June 2026) -> '2025-27'."""
    if not fy:
        return ""
    y = int(fy)
    start = y - 1 if y % 2 == 0 else y - 2
    return f"{start}-{str(start + 2)[-2:]}"


def chapter_of(xml_path: Path) -> str:
    """Session-law chapter of an enacted bill, e.g. '2024 c 376'."""
    m = re.search(r'<ChapterLaw year="(\d{4})">(\d+)</ChapterLaw>',
                  xml_path.read_text(encoding="utf-8-sig")[:5000])
    return f"{m.group(1)} c {m.group(2)}" if m else ""


def classify(account: str) -> str:
    """Budget bills also move money between funds and to local governments.

    Those aren't agency spending, and adding them to appropriations would
    double-count, so they're labeled.
    """
    low = account.lower()
    if "for transfer to" in low or "transfer to the" in low:
        return "transfer"
    if "distribution" in low:
        return "distribution"
    return "appropriation"


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

        # Capital sections name each project just before its blocks.
        project_names: dict[int, str] = {}
        current_name = ""
        for child in sec:
            if child.tag == f"{NS}CapitalProjectName":
                current_name = _text(child)
            elif child.tag == f"{NS}Appropriations":
                project_names[id(child)] = current_name

        for block in blocks:
            pending: Appropriation | None = None
            approp_type = block.get("appropType", "")
            for ap in block.findall(f"{NS}Appropriation"):
                account = _text(ap.find(f"{NS}AccountName"))
                struck, current, added_only = _amounts(ap.find(f"{NS}DollarAmount"))
                vetoed = _is_vetoed(ap)
                if not account and pending is not None:
                    # Continuation line carrying the amended amount.
                    pending.amount = current
                    pending.vetoed = pending.vetoed or vetoed
                    continue
                fund, source, fy = parse_account(account)
                row = Appropriation(
                    bill=bill, section=section, section_type=sec.get("type", ""),
                    amends=amends, biennium=_biennium(fy),
                    agency_code=block.get("agency", agency), department=department,
                    account=account,
                    kind={"reappropriation": "reappropriation", "biennia": "capital_context"}.get(
                        approp_type, classify(account)),
                    fund=fund,
                    fund_source=source, fiscal_year=fy,
                    prior_amount=(struck if struck is not None
                                  else 0 if added_only
                                  else current if sec.get("type") == "amendatory" else None),
                    amount=current if struck is None else None,
                    vetoed=vetoed,
                    project=block.get("project", ""),
                    project_name=project_names.get(id(block), ""),
                )
                printed = re.search(r"\((\d{6,})\)\s*$", row.project_name)
                if printed and printed.group(1) != row.project:
                    # The printed law wins over XML metadata (DECISIONS D-025).
                    row.xml_conflict = True
                    row.project = printed.group(1)
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
            p_vetoed = _is_vetoed(p)
            for m in PROVISO_RE.finditer(text):
                provisos.append(Proviso(
                    bill=bill, section=section, agency_code=agency,
                    department=department, amount=dollars(m["amount"]) or 0,
                    account=m["account"], fiscal_year=m["fy"] or "",
                    solely_for=bool(m["solely"]), vetoed=p_vetoed, text=text[:1000],
                ))
    return approps, provisos


def run(sample_rows: int = 400) -> None:
    for biennium, chamber, number, budget_biennium, label in BUDGET_BILLS:
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

"""Legislators, districts and roll-call votes from the Legislature's web services.

Docs: https://wslwebservices.leg.wa.gov/ (SOAP services with plain HTTP GET
endpoints returning XML; no key needed).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from .common import SAMPLES, fetch, write_csv

BASE = "https://wslwebservices.leg.wa.gov"
NS = "{http://WSLWebServices.leg.wa.gov/}"

# Budget bills whose votes we track: (legislative biennium, bill number, label)
BUDGET_BILLS = [
    ("2025-26", "5167", "2025-27 operating budget"),
    ("2025-26", "5998", "2026 supplemental operating budget"),
]


def _get(service: str, method: str, filename: str, **params: str) -> ET.Element:
    url = f"{BASE}/{service}.asmx/{method}?{urlencode(params)}"
    return ET.parse(fetch(url, "legislature", filename)).getroot()


def _t(el: ET.Element, path: str) -> str:
    found = el.find("/".join(f"{NS}{p}" for p in path.split("/")))
    return (found.text or "").strip() if found is not None else ""


def members(biennium: str) -> list[dict]:
    root = _get("SponsorService", "GetSponsors", f"sponsors_{biennium}.xml", biennium=biennium)
    return [{
        "biennium": biennium,
        "member_id": _t(m, "Id"),
        "name": _t(m, "Name"),
        "first_name": _t(m, "FirstName"),
        "last_name": _t(m, "LastName"),
        "chamber": _t(m, "Agency"),
        "party": _t(m, "Party"),
        "district": _t(m, "District"),
        "acronym": _t(m, "Acronym"),
    } for m in root.findall(f"{NS}Member")]


def roll_calls(biennium: str, bill_number: str) -> list[dict]:
    """One row per member per roll call."""
    root = _get("LegislationService", "GetRollCalls",
                f"rollcalls_{biennium}_{bill_number}.xml",
                biennium=biennium, billNumber=bill_number)
    rows = []
    for rc in root.findall(f"{NS}RollCall"):
        base = {
            "biennium": biennium,
            "bill_id": _t(rc, "BillId"),
            "chamber": _t(rc, "Agency"),
            "motion": " ".join(_t(rc, "Motion").split()),
            "sequence": _t(rc, "SequenceNumber"),
            "vote_date": _t(rc, "VoteDate")[:10],
        }
        for tag, position in [("YeaVotes", "yea"), ("NayVotes", "nay"),
                              ("AbsentVotes", "absent"), ("ExcusedVotes", "excused")]:
            names = _t(rc, f"{tag}/MembersVoting")
            for name in filter(None, (n.strip() for n in names.split(","))):
                rows.append({**base, "member": name, "position": position})
    return rows


def run() -> None:
    bienniums = sorted({b for b, _, _ in BUDGET_BILLS})
    all_members = [m for b in bienniums for m in members(b)]
    write_csv(SAMPLES / "legislators.csv", all_members)
    print(f"legislators: {len(all_members)}")

    votes = []
    for biennium, number, label in BUDGET_BILLS:
        rows = roll_calls(biennium, number)
        print(f"{label}: {len({(r['chamber'], r['sequence']) for r in rows})} roll calls, "
              f"{len(rows)} member votes")
        votes.extend(rows)
    write_csv(SAMPLES / "budget_bill_votes.csv", votes)

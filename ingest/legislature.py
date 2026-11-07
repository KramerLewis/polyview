"""Legislators, districts and roll-call votes from the Legislature's web services.

Docs: https://wslwebservices.leg.wa.gov/ (SOAP services with plain HTTP GET
endpoints returning XML; no key needed).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
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
    } for m in root.findall(f"{NS}Member") if _t(m, "LastName")]  # skip nameless placeholders


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
        base.update(classify_motion(base["motion"]))
        for tag, position in [("YeaVotes", "yea"), ("NayVotes", "nay"),
                              ("AbsentVotes", "absent"), ("ExcusedVotes", "excused")]:
            for name in split_names(_t(rc, f"{tag}/MembersVoting")):
                rows.append({**base, "member": name, "position": position})
    return rows


AMENDMENT = re.compile(r"^(?P<number>\d+)\s+(?P<sponsor>[A-Za-z'\- ]+?)\s+(?:Pg|Striker|$)")


def classify_motion(motion: str) -> dict:
    """Label a roll call so the site can separate enacting votes from the rest.

    final_passage: the vote that sent the final version to the governor
                   (conference report, or concurrence)
    passage:       a chamber passing its own version before negotiation
    amendment:     a floor amendment (number and sponsor parsed from the motion)
    procedural:    everything else
    """
    low = motion.lower()
    m = AMENDMENT.match(motion)
    if m:
        return {"vote_type": "amendment", "amendment": m["number"], "amendment_sponsor": m["sponsor"]}
    if "final passage" in low and ("conference" in low or "concur" in low):
        return {"vote_type": "final_passage", "amendment": "", "amendment_sponsor": ""}
    if "final passage" in low:
        return {"vote_type": "passage", "amendment": "", "amendment_sponsor": ""}
    return {"vote_type": "procedural", "amendment": "", "amendment_sponsor": ""}


def split_names(text: str) -> list[str]:
    """'Walsh, Wilson, C., Wilson, J.' -> ['Walsh', 'Wilson, C.', 'Wilson, J.'].

    Roll calls use last names, adding a first initial when two members share one.
    """
    out: list[str] = []
    for part in (p.strip() for p in text.split(",")):
        if not part:
            continue
        if re.fullmatch(r"[A-Z]\.", part) and out:
            out[-1] = f"{out[-1]}, {part}"
        else:
            out.append(part)
    return out


def match_members(votes: list[dict], members: list[dict]) -> int:
    """Add member_id/district/party to each vote row; return the number unmatched."""
    index = defaultdict(list)
    for m in members:
        index[(m["biennium"], m["chamber"], m["last_name"])].append(m)
    unmatched = 0
    for v in votes:
        last, _, initial = v["member"].partition(", ")
        cands = index.get((v["biennium"], v["chamber"], last), [])
        if initial:
            cands = [m for m in cands if m["first_name"].startswith(initial.rstrip("."))]
        if len(cands) == 1:
            m = cands[0]
            v.update(member_id=m["member_id"], district=m["district"], party=m["party"])
        else:
            v.update(member_id="", district="", party="")
            unmatched += 1
    return unmatched


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
    unmatched = match_members(votes, all_members)
    print(f"votes matched to members: {len(votes) - unmatched}/{len(votes)}")
    write_csv(SAMPLES / "budget_bill_votes.csv", votes)

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
def _budget_bills() -> list[tuple[str, str, str]]:
    """Every enacted budget bill we parse (ingest/budget_bills.py), as
    (legislative biennium, bill number, label)."""
    from .budget_bills import BUDGET_BILLS as BILLS
    return [(leg_bien, number, label) for leg_bien, _, number, _, label in BILLS]


BUDGET_BILLS = _budget_bills()


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


def _section(text: str, label: str, stops: tuple[str, ...]) -> str:
    """Pull 'EFFECT: …' style statements out of an amendment's text."""
    i = text.find(label)
    if i < 0:
        return ""
    body = text[i + len(label):]
    end = min([j for j in (body.find(s) for s in stops) if j >= 0] or [len(body)])
    return body[:end].strip(" :\u200e")


def amendments(years: list[int], bill_numbers: set[str]) -> list[dict]:
    """Floor amendments to the budget bills, with staff EFFECT / FISCAL IMPACT text.

    Effect statements are written by nonpartisan committee staff and printed at the
    end of each amendment; we quote them, never paraphrase (DECISIONS D-029).
    """
    import urllib.parse
    out = []
    for year in years:
        root = _get("AmendmentService", "GetAmendments", f"amendments_{year}.xml", year=str(year))
        for a in root.findall(f"{NS}Amendment"):
            if _t(a, "BillNumber") not in bill_numbers or _t(a, "Type") != "Floor":
                continue
            row = {
                "bill_id": _t(a, "BillId"), "chamber": _t(a, "Agency"), "name": _t(a, "Name"),
                "floor_number": _t(a, "FloorNumber"), "sponsor": _t(a, "SponsorName"),
                "location": _t(a, "Description"), "floor_action": _t(a, "FloorAction"),
                "action_date": _t(a, "FloorActionDate")[:10], "url": _t(a, "HtmUrl"),
                "effect": "", "fiscal_impact": "", "outlook_effect": "",
            }
            if _t(a, "DocumentExists") == "true" and row["url"]:
                url = row["url"].replace("http://", "https://")
                url = urllib.parse.quote(url, safe=":/")
                try:
                    path = fetch(url, "amendments", f"{row['name']}.htm".replace(" ", "_"))
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
                    text = re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ").replace("&#x200e;", " ")
                    text = re.sub(r"\s+", " ", text)
                    stops = ("FISCAL IMPACT", "FOUR-YEAR OUTLOOK EFFECT", "--- END ---")
                    row["effect"] = _section(text, "EFFECT:", stops)
                    row["fiscal_impact"] = _section(text, "FISCAL IMPACT:", stops[1:])
                    row["outlook_effect"] = _section(text, "FOUR-YEAR OUTLOOK EFFECT:", stops[2:])
                except OSError as e:
                    row["effect"] = f"(amendment text unavailable: {e})"
            out.append(row)
    return out


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

    years = sorted({int(b[:4]) for b, _, _ in BUDGET_BILLS} | {int(b[:4]) + 1 for b, _, _ in BUDGET_BILLS})
    amds = amendments(years, {n for _, n, _ in BUDGET_BILLS})
    recorded = {(v["bill_id"], v["chamber"], v["amendment"]) for v in votes if v["amendment"]}
    for a in amds:
        a["roll_call"] = (a["bill_id"], a["chamber"], a["floor_number"]) in recorded
    print(f"floor amendments: {len(amds)} ({sum(a['roll_call'] for a in amds)} with recorded votes, "
          f"{sum(1 for a in amds if a['effect'])} with an EFFECT statement)")
    write_csv(SAMPLES / "budget_amendments.csv", amds)

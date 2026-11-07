"""Build the static site's data files (web/data/*.json) from ingested sources.

Run after the ingesters:  python -m ingest && python -m publish
Every figure written here has a matching note in docs/DECISIONS.md.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ingest import budget_to_actual, budget_to_actual_detail
from ingest.budget_current import BUDGETS, build_all
from ingest.common import MANIFEST, RAW, ROOT, SAMPLES

import csv

OUT = ROOT / "web" / "data"
SMALL_WORDS = {"of", "and", "the", "for", "on", "to", "in", "a"}
ACRONYMS = {"wsu": "WSU", "uw": "UW", "ewu": "EWU", "cwu": "CWU", "wwu": "WWU", "ii": "II"}


# Fund-source suffixes as printed in bills ("—State", "—Federal", …). Anything
# else (unparsed or rare) is grouped as Other.
SOURCE_NAMES = {"state": "State", "federal": "Federal", "private/local": "Private/Local",
                "local": "Private/Local", "private": "Private/Local"}


def agency3(code: str) -> str:
    """Agency codes appear as '300', '3000', '103CSD', '3000302000'; join on 3 digits (D-023)."""
    m = re.match(r"\d{3}", code or "")
    return m.group(0) if m else ""


def nice(name: str) -> str:
    words = name.lower().split()
    out = []
    for i, w in enumerate(words):
        out.append(ACRONYMS.get(w, w if (i and w in SMALL_WORDS) else w.capitalize()))
    return " ".join(out)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def current_budget() -> tuple[list[dict], dict]:
    rows, issues = build_all()
    biennium = BUDGETS[0][0]
    rows = [r for r in rows if r["biennium"] == biennium]
    by_budget = []
    for _, budget, orig_bill, _, supps in BUDGETS:
        sub = [r for r in rows if r["budget"] == budget]
        new = [r for r in sub if r["kind"] == "appropriation"]
        by_budget.append({
            "budget": budget,
            "bills": [f"ESSB {orig_bill}"] + [f"ESSB {b} ({label})" for b, label in supps],
            "original": sum(r["original"] for r in new),
            "current": sum(r["current"] for r in new),
            "reappropriated": sum(r["current"] for r in sub if r["kind"] == "reappropriation"),
            "transfers": sum(r["current"] for r in sub if r["kind"] == "transfer"),
            "distributions": sum(r["current"] for r in sub if r["kind"] == "distribution"),
        })
    by_source: dict[str, dict] = defaultdict(lambda: {"original": 0, "current": 0})
    for r in rows:
        if r["kind"] == "appropriation":
            src = SOURCE_NAMES.get(r["fund_source"].lower(), "Other")
            by_source[src]["original"] += r["original"]
            by_source[src]["current"] += r["current"]
    from ingest.checks import ngfo
    meta = {
        "biennium": biennium,
        "ngfo": {"original": ngfo(rows, biennium, "original"), "current": ngfo(rows, biennium, "current")},
        "by_budget": by_budget,
        "by_fund_source": [{"source": k, **v} for k, v in
                           sorted(by_source.items(), key=lambda kv: -kv[1]["current"])],
        "overlay_issues": sum(len(v) for v in issues.values()),
    }
    return rows, meta


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # --- 2025-27 enacted budget, by agency ---------------------------------
    budget_rows, budget_meta = current_budget()
    agencies: dict[str, dict] = defaultdict(lambda: {"name": "", "programs": set(),
                                                    "orig_2527": 0, "curr_2527": 0,
                                                    "gfs_curr_2527": 0, "reapprop_2527": 0,
                                                    "by_budget_2527": defaultdict(int),
                                                    "projects": []})
    for r in budget_rows:
        a = agencies[agency3(r["agency_code"])]
        base, _, program = r["department"].partition("—")
        if not base.upper().startswith("SPECIAL APPROPRIATION"):
            a["name"] = a["name"] or nice(base)
        if r["kind"] == "reappropriation":
            a["reapprop_2527"] += r["current"]
        if r["kind"] != "appropriation":
            continue
        if program and r["budget"] == "operating":
            a["programs"].add(nice(program))
        a["orig_2527"] += r["original"]
        a["curr_2527"] += r["current"]
        a["by_budget_2527"][r["budget"]] += r["current"]
        if r["fund"] == "General Fund" and r["fund_source"] == "State":
            a["gfs_curr_2527"] += r["current"]
    # Capital projects: new money plus reappropriations, per project.
    projects: dict[tuple, dict] = {}
    for r in budget_rows:
        if r["budget"] != "capital" or r["kind"] not in ("appropriation", "reappropriation"):
            continue
        key = (agency3(r["agency_code"]), r["project"])
        p = projects.setdefault(key, {"name": re.sub(r"\s*\(\d+\)\s*$", "", r["project_name"]),
                                      "project": r["project"], "new": 0, "reapprop": 0})
        p["new" if r["kind"] == "appropriation" else "reapprop"] += r["current"]
    for (code, _), p in projects.items():
        agencies[code]["projects"].append(p)

    # --- 2025-27 payments so far (vendor payments; excludes payroll, D-024) --
    for r in read_csv(SAMPLES / "vendor_payments_by_agency_object_2527.csv"):
        a = agencies[agency3(r["agency_code"])]
        a["name"] = a["name"] or r["agency"].strip()
        a["paid_2527"] = a.get("paid_2527", 0) + round(float(r["amount"]))

    # --- 2023-25 final budget vs actual (OFM, FY2025 report, $K) -------------
    bta_path = RAW / "budget_to_actual" / budget_to_actual.FILE_VARIANTS[25]
    bta_rows, _ = budget_to_actual.parse_text(budget_to_actual.pdf_text(bta_path), 2025)
    completed = {"biennium": "2023-25", "source": "OFM Budget-to-Actual Detailed Report, FY2025",
                 "final_budget": 0, "actual": 0, "other_actual": 0}
    for r in bta_rows:
        if r.is_adjustment:
            continue
        a = agencies[agency3(r.agency_code)]
        a["name"] = a["name"] or r.agency
        if not r.authority_code:
            # Activity recorded with no expenditure-authority (appropriation) line,
            # e.g. bond debt service paid under statutory authority. Reported
            # separately so budget vs. actual compares like with like (D-026).
            completed["other_actual"] += r.actual_k * 1000
            a["other_actual_2325"] = a.get("other_actual_2325", 0) + r.actual_k * 1000
            continue
        completed["final_budget"] += r.final_budget_k * 1000
        completed["actual"] += r.actual_k * 1000
        a["budget_2325"] = a.get("budget_2325", 0) + r.final_budget_k * 1000
        a["actual_2325"] = a.get("actual_2325", 0) + r.actual_k * 1000

    agency_list = []
    for code, a in agencies.items():
        if not code:
            continue
        a["programs"] = sorted(a["programs"])
        a["by_budget_2527"] = dict(a["by_budget_2527"])
        a["projects"] = sorted(a["projects"], key=lambda p: -(p["new"] + p["reapprop"]))
        agency_list.append({"code": code, **a})
    agency_list.sort(key=lambda a: -(a.get("curr_2527") or a.get("budget_2325") or 0))

    # --- Revenue and spending by biennium (OFM detail reports, fund level) --
    history = []
    for yy in (21, 23):
        path = RAW / "budget_to_actual" / budget_to_actual.FILE_VARIANTS[yy]
        rows, _ = budget_to_actual_detail.parse_text(budget_to_actual.pdf_text(path), 2000 + yy)
        funds = [r for r in rows if r.level == "fund"]
        rev: dict[str, dict] = defaultdict(lambda: {"final": 0, "actual": 0})
        spend: dict[str, dict] = defaultdict(lambda: {"final": 0, "actual": 0})
        for r in funds:
            # Transfers between funds would double-count statewide totals (D-011).
            if r.line_code in ("DZ", "TR", "HZ"):
                continue
            target = rev if r.section == "resources" else spend if r.section == "charges" else None
            if target is not None:
                line = r.line[0].upper() + r.line[1:].lower()  # OFM capitalization varies
                target[line]["final"] += r.final
                target[line]["actual"] += r.actual
        history.append({
            "biennium": budget_to_actual._biennium(2000 + yy),
            "source": f"OFM Budget-to-Actual Detail Report, FY20{yy}",
            "revenue": [{"line": k, **v} for k, v in sorted(rev.items(), key=lambda kv: -kv[1]["actual"])],
            "spending": [{"line": k, **v} for k, v in sorted(spend.items(), key=lambda kv: -kv[1]["actual"])],
        })

    # --- Legislators and budget votes --------------------------------------
    members = read_csv(SAMPLES / "legislators.csv")
    votes = read_csv(SAMPLES / "budget_bill_votes.csv")
    roll_calls: dict[tuple, dict] = {}
    by_member: dict[str, list] = defaultdict(list)
    for v in votes:
        key = (v["bill_id"], v["chamber"], v["sequence"], v["vote_date"])
        rc = roll_calls.setdefault(key, {
            "id": "|".join(key), "bill": v["bill_id"], "chamber": v["chamber"], "date": v["vote_date"],
            "motion": v["motion"], "type": v["vote_type"], "amendment": v["amendment"],
            "sponsor": v["amendment_sponsor"], "yea": 0, "nay": 0, "other": 0})
        bucket = v["position"] if v["position"] in ("yea", "nay") else "other"
        rc[bucket] += 1
        if v["member_id"]:
            # Keyed by chamber too: a member who changed chambers mid-biennium
            # appears once per chamber, each with that chamber's votes (D-021).
            by_member[f'{v["member_id"]}|{v["chamber"]}'].append([rc["id"], v["position"]])
    # Floor amendments with staff EFFECT statements, joined to their roll calls.
    amendments = []
    for a in read_csv(SAMPLES / "budget_amendments.csv"):
        striker = " AMS " in a["name"] and not a["effect"] and "Striker" in " ".join(
            rc["motion"] for rc in roll_calls.values()
            if rc["bill"] == a["bill_id"] and rc["amendment"] == a["floor_number"])
        amendments.append({
            "bill": a["bill_id"], "chamber": a["chamber"], "number": a["floor_number"],
            "sponsor": a["sponsor"], "result": a["floor_action"].capitalize(), "date": a["action_date"],
            "effect": a["effect"] or ("Striking amendment: replaces the whole bill with an alternative budget."
                                      if striker else ""),
            "fiscal_impact": a["fiscal_impact"], "url": a["url"].replace("http://", "https://"),
            "recorded_vote": a["roll_call"] == "True",
        })
    by_amd = {(a["bill"], a["chamber"], a["number"]): a for a in amendments}
    for rc in roll_calls.values():
        a = by_amd.get((rc["bill"], rc["chamber"], rc["amendment"]))
        if a:
            rc["effect"], rc["result"], rc["url"] = a["effect"], a["result"], a["url"]

    legislators = [{
        "id": m["member_id"], "name": m["name"], "chamber": m["chamber"], "party": m["party"],
        "district": int(m["district"]) if m["district"].isdigit() else None,
        "votes": by_member.get(f'{m["member_id"]}|{m["chamber"]}', []),
    } for m in members]
    legislators.sort(key=lambda m: (m["district"] or 99, m["chamber"] != "Senate", m["name"]))

    # --- Provenance ---------------------------------------------------------
    sources = {}
    if MANIFEST.exists():
        for line in MANIFEST.read_text().splitlines():
            rec = json.loads(line)
            sources[rec["url"]] = {"fetched_at": rec["fetched_at"], "sha256": rec["sha256"][:12],
                                   "source": rec["source"]}

    # --- Official four-year outlook (ERFC), $ millions -----------------------
    from dataclasses import asdict as _asdict

    from ingest import outlook as outlook_mod
    ol = None
    for label, url in outlook_mod.OUTLOOKS:
        path = RAW / "outlook" / url.rsplit("/", 1)[-1]
        rows_, meta_ = outlook_mod.parse_text(budget_to_actual.pdf_text(path), label)
        ol = {"label": label, "url": url, "bienniums": meta_["bienniums"],
              "rows": [{k: v for k, v in _asdict(r).items() if k not in ("outlook", "order")}
                       for r in rows_]}

    data = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "budget": budget_meta,
        "agencies": agency_list,
        "completed": completed,
        "outlook": ol,
        "history": history,
        "roll_calls": sorted(roll_calls.values(), key=lambda r: (r["bill"], r["date"], r["chamber"])),
        "legislators": legislators,
        "amendments": sorted(amendments, key=lambda a: (a["bill"], a["date"], a["chamber"], a["number"])),
        "sources": [{"url": u, **v} for u, v in sorted(sources.items())],
    }
    (OUT / "site.json").write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {OUT / 'site.json'} ({(OUT / 'site.json').stat().st_size / 1024:,.0f} KB): "
          f"{len(agency_list)} agencies, {len(legislators)} legislators, {len(roll_calls)} roll calls")

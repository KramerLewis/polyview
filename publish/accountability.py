"""The "Follow the money" questions (DECISIONS D-046, D-047).

1. sweeps():    money moved between accounts by budget bills, grouped by direction
2. changes():   what later budget bills changed after a budget first passed
3. shortfall(): is there a shortfall, and what is driving it

Everything here is computed from parsed primary sources; wording on the site
states facts and leaves judgement to the reader.
"""

from __future__ import annotations

import re
from collections import defaultdict

# --- 1. Transfers between accounts -------------------------------------------
GENERAL_FUND = re.compile(r"^(state )?general fund$", re.I)
RAINY_DAY = re.compile(r"budget stabilization account", re.I)


def _clean_account(text: str) -> str:
    text = re.sub(r"^\(\d+\)\s*", "", text.strip())
    text = re.sub(r"\s*[—-]\s*(State|Federal|Private/Local)( Appropriation)?$", "", text, flags=re.I)
    text = re.sub(r"\s+Appropriation$", "", text, flags=re.I)
    return text.strip(" .,:")


def parse_transfer(account: str) -> tuple[str, str]:
    """'Public Works Assistance Account: For transfer to the state general fund, $288,000,000 …'
    -> ('Public Works Assistance Account', 'General Fund')"""
    head, _, tail = account.partition(":")
    src = _clean_account(head)
    m = re.search(r"for transfer to (?:the )?(.+?)(?:,|\s+\$|\s+for fiscal year|\s+on (?:or after )?[A-Z][a-z]+ \d|\s+in an amount"
                  r"|\s+created in|\s+as (?:full )?repayment|\s+pursuant|\s+for the purpose|\.|$)",
                  tail or account, re.I)
    dst = _clean_account(m.group(1)) if m else ""
    dst = re.sub(r"\b(account|fund)\s+for\s+.*$", r"\1", dst, flags=re.I)  # "…account for the X to do Y"
    if GENERAL_FUND.match(dst):
        dst = "General Fund"
    if GENERAL_FUND.match(src) or src.lower() == "general fund":
        src = "General Fund"
    return src, dst


def direction(src: str, dst: str) -> str:
    if dst == "General Fund" and RAINY_DAY.search(src):
        return "rainy_day_to_gf"
    if dst == "General Fund":
        return "dedicated_to_gf"
    if src == "General Fund":
        return "gf_to_other"
    if RAINY_DAY.search(dst):
        return "to_rainy_day"
    return "between_accounts"


DIRECTION_LABELS = {
    "dedicated_to_gf": "From other accounts into the General Fund",
    "rainy_day_to_gf": "From the rainy-day fund (Budget Stabilization Account) into the General Fund",
    "gf_to_other": "From the General Fund into other accounts",
    "to_rainy_day": "Into the rainy-day fund",
    "between_accounts": "Between other accounts",
}


def sweeps(rows: list[dict], bill_of: dict) -> dict:
    """rows: budget_current overlay rows. bill_of(biennium, budget, step) -> bill id/label."""
    items = []
    for r in rows:
        if r["kind"] != "transfer" or not r["current"]:
            continue
        src, dst = parse_transfer(r["account"])
        if not dst:
            continue
        text = r["account"]
        steps = [k[len("after_"):] for k in r if k.startswith("after_") and not k.endswith("_vetoed")]
        changed_by = [s for s in steps if r.get(f"after_{s}") != r["original"]]
        items.append({
            "biennium": r["biennium"], "budget": r["budget"], "section": r["section"],
            "from": src, "to": dst, "direction": direction(src, dst),
            "amount": r["current"], "original": r["original"],
            "is_cap": bool(re.search(r"lesser of|not to exceed|up to", text, re.I)),
            "statutory": bool(re.search(r"\bRCW\b|pursuant to", text, re.I)),
            "added_later": r["original"] == 0,
            "changed_by": changed_by,
            "bill": bill_of(r["biennium"], r["budget"], changed_by[-1] if changed_by else None),
            "text": text[:400],
        })
    items.sort(key=lambda x: -x["amount"])
    totals = defaultdict(lambda: defaultdict(int))
    for it in items:
        totals[it["biennium"]][it["direction"]] += it["amount"]
    return {"items": items, "totals": {b: dict(v) for b, v in totals.items()}, "labels": DIRECTION_LABELS}


# --- 2. Changes after a budget first passed ---------------------------------
def changes(rows: list[dict], bill_of) -> dict:
    """Net change by agency/program from the original enacted budget to now."""
    by: dict[tuple, dict] = {}
    for r in rows:
        if r["kind"] != "appropriation":
            continue
        dept = r["department"]
        key = (r["biennium"], r["budget"], r["agency_code"][:3], dept)
        x = by.setdefault(key, {"biennium": r["biennium"], "budget": r["budget"], "agency_code": r["agency_code"][:3],
                                "program": dept, "original": 0, "current": 0, "steps": defaultdict(int),
                                "lines_changed": 0, "vetoed": 0})
        x["original"] += r["original"]
        x["current"] += r["current"]
        prev = r["original"]
        for k in sorted(k for k in r if k.startswith("after_") and not k.endswith("_vetoed")):
            step = k[len("after_"):]
            x["steps"][step] += r[k] - prev
            prev = r[k]
        if r["current"] != r["original"]:
            x["lines_changed"] += 1
        if r.get("original_vetoed") or any(r.get(k) for k in r if k.endswith("_vetoed")):
            x["vetoed"] += 1
    out = []
    for x in by.values():
        x["change"] = x["current"] - x["original"]
        x["steps"] = {s: v for s, v in x["steps"].items() if v}
        x["bills"] = {s: bill_of(x["biennium"], x["budget"], s) for s in x["steps"]}
        if x["change"] or x["steps"]:
            out.append(x)
    out.sort(key=lambda x: -abs(x["change"]))
    summary = defaultdict(lambda: {"original": 0, "current": 0, "increases": 0, "decreases": 0})
    for x in by.values():
        s = summary[x["biennium"]]
        s["original"] += x["original"]
        s["current"] += x["current"]
        ch = x["current"] - x["original"]
        s["increases" if ch > 0 else "decreases"] += abs(ch) if ch else 0
    return {"items": out, "summary": dict(summary)}


# --- 3. Is there a shortfall, and what is driving it --------------------------
CATEGORY_ORDER = ["K-12 Education", "Low Income Health Care & Comm Behavioral Health", "Social & Health Services",
                  "Children, Youth, and Families", "Higher Education", "Corrections", "Debt Service",
                  "Compensation & Benefits", "All Other"]


def _budget_biennium(bienniums: list[str]) -> str:
    """Biennial outlooks show (prior, new, next); supplementals show (current, next)."""
    return bienniums[1] if len(bienniums) == 3 else bienniums[0]


def shortfall(outlooks: list, econ: dict) -> dict:
    """outlooks: ingest.outlook.load() result, oldest first. econ: ingest.econ.load()."""
    from ingest.outlook import enacted_level, get

    final: dict[str, dict] = {}       # latest outlook's view of each biennium
    first: dict[str, dict] = {}       # the view when the biennium's budget first passed
    drivers: dict[str, dict] = defaultdict(lambda: {"maintenance": defaultdict(float), "policy": defaultdict(float),
                                                    "carryforward": 0.0, "revenue_legislation": 0.0,
                                                    "base": None, "steps": []})
    for label, url, rows, bienniums in outlooks:
        own = _budget_biennium(bienniums)
        for b in bienniums:
            g = lambda name: (get(rows, name, b).total if get(rows, name, b) else None)  # noqa: E731
            view = {"outlook": label, "url": url, "enacted_level": enacted_level(rows, b),
                    "revised": g("Revised Appropriations"), "resources": g("Total Revenues and Resources"),
                    "forecast": g("Forecasted Revenues"), "ending": g("NGF-O Projected Ending Balance"),
                    "reversions": g("Reversions"), "reserves": g("Total Reserves"),
                    "beginning": g("NGF-O Beginning Balance"), "projected": b > own}
            final[b] = view
            if b == own and own not in first:
                first[b] = view
            if b > own:
                continue  # forward columns are projections, not decisions
            d = drivers[b]
            if b == own and len(bienniums) == 3 and d["base"] is None:
                base = get(rows, "Enacted Appropriations", b)
                d["base"] = base.total if base else None
            cf = get(rows, "Carryforward Level Adjustments", b)
            d["carryforward"] += cf.total if cf and cf.total else 0
            section = None
            changed = False
            for r in sorted((r for r in rows if r.biennium == b), key=lambda r: r.order):
                if not r.is_detail:
                    section = {"Maintenance Level Total": "maintenance", "Policy Level Total": "policy"}.get(r.label)
                    if section and r.total:
                        changed = True
                    continue
                if section and r.total:
                    d[section][r.label] += r.total
                if r.label.startswith("Revenue Legislation") and r.total:
                    d["revenue_legislation"] += r.total
            if changed:
                d["steps"].append(label)

    cpi = {y: v.value for y, v in econ.get("seattle_cpi_fy", {}).items()}
    pop = {y: v.value for y, v in econ.get("population", {}).items()}
    fc_years = {y for s in econ.values() for y, v in s.items() if v.forecast}

    def fy_pair(b: str) -> tuple[int, int]:
        y = int(b[:4])
        return y + 1, y + 2

    bienniums = sorted(final)
    ref = max((b for b in bienniums if all(y in cpi for y in fy_pair(b)) and not final[b]["projected"]), default=None)
    ref_cpi = sum(cpi[y] for y in fy_pair(ref)) / 2 if ref else None
    trend = []
    for b in bienniums:
        f = final[b]
        ys = fy_pair(b)
        if not all(y in cpi and y in pop for y in ys) or f["enacted_level"] is None:
            continue
        c = sum(cpi[y] for y in ys) / 2
        p = sum(pop[y] for y in ys) / 2 * 1000  # thousands -> people
        real = f["enacted_level"] * 1e6 * ref_cpi / c
        trend.append({
            "biennium": b, "spending": f["enacted_level"] * 1e6, "revenue": (f["forecast"] or 0) * 1e6,
            "population": p, "cpi": c, "per_resident_real": real / p,
            "revenue_per_resident_real": (f["forecast"] or 0) * 1e6 * ref_cpi / c / p,
            "projected": f["projected"] or any(y in fc_years for y in ys),
            "source": f["outlook"],
        })
    for prev, cur in zip(trend, trend[1:]):
        cur["growth"] = {
            "spending": cur["spending"] / prev["spending"] - 1,
            "population": cur["population"] / prev["population"] - 1,
            "inflation": cur["cpi"] / prev["cpi"] - 1,
            "per_resident_real": cur["per_resident_real"] / prev["per_resident_real"] - 1,
        }

    drivers_out = {}
    for b, d in drivers.items():
        cats = sorted({*d["maintenance"], *d["policy"]},
                      key=lambda c: (CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99, c))
        explained = (d["base"] or 0) + d["carryforward"] + sum(d["maintenance"].values()) + sum(d["policy"].values())
        drivers_out[b] = {
            "base": d["base"], "carryforward": d["carryforward"],
            "final": final[b]["enacted_level"] if b in final else None,
            # What the available outlooks don't break down (missing outlooks, older layouts).
            "not_broken_down": (final[b]["enacted_level"] - explained) if (b in final and d["base"] is not None) else None,
            "maintenance": sum(d["maintenance"].values()), "policy": sum(d["policy"].values()),
            "by_category": [{"category": c, "maintenance": d["maintenance"].get(c, 0), "policy": d["policy"].get(c, 0)}
                            for c in cats],
            "revenue_legislation": d["revenue_legislation"], "steps": d["steps"],
        }

    track = []
    for b in bienniums:
        if b in first and b in final:
            actual_end = None
            nxt = f"{int(b[:4]) + 2}-{str(int(b[:4]) + 4)[-2:]}"
            if (nxt in final and final[nxt].get("beginning") is not None and not final[b]["projected"]
                    and not final[nxt]["projected"]):
                actual_end = final[nxt]["beginning"]
            track.append({"biennium": b, "projected_at_passage": first[b]["ending"], "projected_by": first[b]["outlook"],
                          "latest": final[b]["ending"], "latest_by": final[b]["outlook"],
                          "next_beginning": actual_end, "projected": final[b]["projected"]})
    return {"reference_biennium": ref, "trend": trend, "drivers": drivers_out, "track_record": track,
            "final": final}

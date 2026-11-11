"""Money-flow (Sankey) data: revenue sources -> fund groups -> areas of government.

Built from OFM Budget-to-Actual fund-level pages (actuals, budgetary basis).
Rules (docs/PLAN.md item 7, DECISIONS D-039):
- Money is traced only as far as a fund. Money mixes inside a fund, so there are
  no direct source -> area links.
- Transfers between funds are left out (D-011). Each fund group's gap between
  revenue and spending is shown explicitly: spending above revenue draws on
  "bond proceeds, transfers in and balances"; revenue above spending goes to
  "added to balances and transfers out". That keeps every node balanced
  instead of quietly hiding the difference.
"""

from __future__ import annotations

from collections import defaultdict

TRANSFER_LINES = {"DZ", "TR", "HZ"}

SOURCE_OF_LINE = {
    "AB": "Taxes",
    "CG": "Federal grants",
    "CD": "Fees and charges",
    "CH": "Fees and charges",
}
OTHER_SOURCE = "Other revenue"  # contracts/grants, timber, interest, misc., unclaimed property
SOURCE_ORDER = ["Taxes", "Federal grants", "Fees and charges", OTHER_SOURCE]
DRAW = "Bonds, transfers & balances"
SURPLUS = "To balances & transfers out"

# OFM fund rollups -> fund groups shown in the middle column.
FUND_GROUP = {
    "AA": "General Fund", "AC": "General Fund",
    "BA": "Transportation funds", "BB": "Transportation funds",
    "CB": "Transportation funds", "CD": "Transportation funds",
    "BG": "Higher education funds", "DB": "Higher education funds",
    "BE": "Human services funds",
    "BF": "Natural resources funds",
    "DA": "Capital & construction funds", "BH": "Capital & construction funds",
    "CA": "Capital & construction funds",
}
OTHER_FUNDS = "Other funds"

AREA_OF_LINE = {
    "F1": "General government", "F2": "Human services", "F3": "Natural resources",
    "F4": "Transportation", "F5": "Education", "HC": "Capital projects",
}


def money_flow(fund_rows: list, biennium: str, source: str) -> dict:
    """fund_rows: DetailRow objects at level == 'fund' (actual amounts in dollars)."""
    src_to_fund: dict[tuple, int] = defaultdict(int)
    fund_to_area: dict[tuple, int] = defaultdict(int)
    for r in fund_rows:
        if r.line_code in TRANSFER_LINES or r.section not in ("resources", "charges"):
            continue
        group = FUND_GROUP.get(r.fund_code, OTHER_FUNDS)
        if r.section == "resources":
            src_to_fund[(SOURCE_OF_LINE.get(r.line_code, OTHER_SOURCE), group)] += r.actual
        else:
            area = AREA_OF_LINE.get(r.line_code)
            if area:
                fund_to_area[(group, area)] += r.actual

    groups = sorted({g for _, g in src_to_fund} | {g for g, _ in fund_to_area})
    links = []
    for g in groups:
        rev = sum(v for (s, gg), v in src_to_fund.items() if gg == g)
        spend = sum(v for (gg, a), v in fund_to_area.items() if gg == g)
        if spend > rev:
            src_to_fund[(DRAW, g)] += spend - rev
        elif rev > spend:
            fund_to_area[(g, SURPLUS)] += rev - spend
    for (s, g), v in src_to_fund.items():
        if v > 0:
            links.append({"from": s, "to": g, "value": v, "stage": 1})
    for (g, a), v in fund_to_area.items():
        if v > 0:
            links.append({"from": g, "to": a, "value": v, "stage": 2})

    def col_total(names, key):
        return {n: sum(l["value"] for l in links if l[key] == n) for n in names}

    sources = [s for s in SOURCE_ORDER + [DRAW] if any(l["from"] == s for l in links)]
    group_totals = col_total(groups, "to")
    groups = sorted(groups, key=lambda g: (g == OTHER_FUNDS, -group_totals[g]))
    areas = sorted({l["to"] for l in links if l["stage"] == 2},
                   key=lambda a: (a == SURPLUS, -sum(l["value"] for l in links if l["to"] == a)))
    revenue = sum(l["value"] for l in links if l["stage"] == 1 and l["from"] != DRAW)
    spending = sum(l["value"] for l in links if l["stage"] == 2 and l["to"] != SURPLUS)
    return {
        "biennium": biennium, "source": source,
        "columns": [sources, groups, areas],
        "links": links,
        "revenue": revenue, "spending": spending,
        "draw": sum(l["value"] for l in links if l["from"] == DRAW),
        "surplus": sum(l["value"] for l in links if l["to"] == SURPLUS),
        "balance_nodes": [DRAW, SURPLUS],
    }

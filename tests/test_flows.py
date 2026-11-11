from types import SimpleNamespace as R

from publish.flows import DRAW, SURPLUS, money_flow


def row(fund, section, code, actual):
    return R(fund_code=fund, section=section, line_code=code, actual=actual)


def test_flow_balances_every_fund_and_skips_transfers():
    rows = [
        row("AA", "resources", "AB", 100), row("AA", "resources", "CG", 50),
        row("AA", "resources", "DZ", 999),           # transfer in: ignored
        row("AA", "charges", "F2", 120), row("AA", "charges", "HZ", 999),  # transfer out: ignored
        row("DA", "resources", "CK", 1), row("DA", "charges", "HC", 41),   # bond-funded capital
    ]
    f = money_flow(rows, "2021-23", "test")
    links = {(l["from"], l["to"]): l["value"] for l in f["links"]}
    assert links[("Taxes", "General Fund")] == 100
    assert links[("Federal grants", "General Fund")] == 50
    assert links[("General Fund", "Human services")] == 120
    assert links[("General Fund", SURPLUS)] == 30          # revenue above spending
    assert links[(DRAW, "Capital & construction funds")] == 40  # spending above revenue
    assert not any(a in ("Taxes", "Federal grants") and b in ("Human services", "Capital projects")
                   for a, b in links)                      # never source -> area directly
    for g in ("General Fund", "Capital & construction funds"):
        assert sum(v for (a, b), v in links.items() if b == g) == sum(v for (a, b), v in links.items() if a == g)

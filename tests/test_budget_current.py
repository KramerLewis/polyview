from ingest.budget_bills import Appropriation
from ingest.budget_current import overlay


def line(section, account, amount, prior=None, amends="", stype="new", vetoed=False, fy="2026"):
    return Appropriation("b", section, stype, amends, "2025-27", "300", "DSHS", account,
                         "appropriation", "General Fund", "State", fy, prior, amount, vetoed)


def test_overlay_replaces_reprinted_sections_and_keeps_history():
    original = [
        line("203", "General Fund—State Appropriation (FY 2026)", 100),
        line("203", "General Fund—State Appropriation (FY 2026)", 50),  # second program block
        line("204", "General Fund—State Appropriation (FY 2026)", 10),
        line("205", "Old Account—State Appropriation", 7),
    ]
    supp = [
        line("203", "General Fund—State Appropriation (FY 2026)", 120, prior=100,
             amends="2025 c 424 s 203", stype="amendatory"),
        line("203", "General Fund—State Appropriation (FY 2026)", 40, prior=50,
             amends="2025 c 424 s 203", stype="amendatory"),
        line("205", "New Account—State Appropriation", 9, prior=0,
             amends="2025 c 424 s 205", stype="amendatory"),
    ]
    rows, issues = overlay("2025-27", original, "2025 c 424", [("2026 supplemental", supp)])
    current = [(r["section"], r["account"][:3], r["original"], r["current"]) for r in rows]
    assert ("203", "Gen", 100, 120) in current
    assert ("203", "Gen", 50, 40) in current
    assert ("204", "Gen", 10, 10) in current  # not reprinted: unchanged
    assert ("205", "Old", 7, 0) in current  # dropped from reprinted section
    assert ("205", "New", 0, 9) in current  # added
    assert not any("!=" in i for i in issues)  # struck amounts matched enacted ones


def test_ngfo_counts_only_state_appropriations_from_outlook_accounts():
    from ingest.checks import ngfo
    base = {"budget": "operating", "biennium": "2025-27", "original": 10, "current": 12}
    rows = [
        {**base, "kind": "appropriation", "fund": "General Fund", "fund_source": "State"},
        {**base, "kind": "appropriation", "fund": "Washington Opportunity Pathways Account", "fund_source": "State"},
        {**base, "kind": "appropriation", "fund": "General Fund", "fund_source": "Federal"},
        {**base, "kind": "distribution", "fund": "General Fund", "fund_source": ""},
        {**base, "kind": "appropriation", "fund": "Motor Vehicle Account", "fund_source": "State"},
    ]
    assert ngfo(rows, "2025-27", "original") == 20
    assert ngfo(rows, "2025-27", "current") == 24

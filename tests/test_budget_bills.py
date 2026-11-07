from pathlib import Path

from ingest.budget_bills import _biennium, parse_account, parse_bill

FIXTURE = Path(__file__).parent / "fixtures" / "budget_sections.xml"


def test_parse_account():
    assert parse_account("General Fund—State Appropriation (FY 2026)") == (
        "General Fund", "State", "2026")
    assert parse_account("General Fund—Private/Local Appropriation") == (
        "General Fund", "Private/Local", "")
    assert parse_account("Performance Audits of Government Account—State Appropriation") == (
        "Performance Audits of Government Account", "State", "")


def test_biennium_from_fiscal_year():
    assert _biennium("2026") == "2025-27"
    assert _biennium("2027") == "2025-27"
    assert _biennium("2025") == "2023-25"
    assert _biennium("") == ""


def test_new_section_from_original_budget():
    approps, provisos = parse_bill(FIXTURE, "test", "2025-27")
    jlarc = [a for a in approps if a.section == "103"]
    assert len(jlarc) == 1
    a = jlarc[0]
    assert a.agency_code == "014"
    assert a.department == "JOINT LEGISLATIVE AUDIT AND REVIEW COMMITTEE"
    assert a.account == "Performance Audits of Government Account—State Appropriation"
    assert a.amount == 13_910_000
    assert a.prior_amount is None
    assert a.biennium == "2025-27"  # biennial account, no FY: falls back to the bill's biennium
    assert any(p.section == "103" and p.amount == 400_000 for p in provisos)


def test_amendatory_section_keeps_prior_and_new_amounts():
    approps, provisos = parse_bill(FIXTURE, "test", "2025-27")
    senate = {a.fiscal_year: a for a in approps if a.section == "102"}
    assert senate["2026"].prior_amount == 45_521_000
    assert senate["2026"].amount == 45_533_000
    assert senate["2027"].prior_amount == 50_984_000
    assert senate["2027"].amount == 51_948_000
    assert all(a.amends == "2025 c 424 s 102" for a in senate.values())
    assert all(a.biennium == "2025-27" for a in senate.values())
    solely = [p for p in provisos if p.section == "102"]
    assert solely and solely[0].solely_for and solely[0].fiscal_year == "2027"

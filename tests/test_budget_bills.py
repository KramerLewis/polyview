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


def test_added_line_has_zero_prior_and_vetoes_flagged():
    from ingest.budget_bills import NS, _amounts, _is_vetoed
    import xml.etree.ElementTree as ET
    added = ET.fromstring(f'<DollarAmount xmlns="{NS[1:-1]}"><TextRun amendingStyle="add">$50,000</TextRun></DollarAmount>')
    assert _amounts(added) == (None, 50_000, True)
    vetoed = ET.fromstring(f'<Appropriation xmlns="{NS[1:-1]}"><DollarAmount><TextRun lineVeto="yes">$1,000</TextRun></DollarAmount></Appropriation>')
    assert _is_vetoed(vetoed)


def test_classify_transfers_and_distributions():
    from ingest.budget_bills import classify
    assert classify("General Fund—State Appropriation (FY 2026)") == "appropriation"
    assert classify("Personnel Service Account: For transfer to the state general fund, $3,827,000") == "transfer"
    assert classify("General Fund Appropriation for prosecuting attorney distributions") == "distribution"

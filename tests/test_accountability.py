from publish.accountability import direction, parse_transfer, shortfall


def test_parse_transfer_and_direction():
    src, dst = parse_transfer("Public Works Assistance Account: For transfer to the state general fund on June 30, "
                              "2026, $288,000,000 for fiscal year 2026")
    assert (src, dst) == ("Public Works Assistance Account", "General Fund")
    assert direction(src, dst) == "dedicated_to_gf"
    src, dst = parse_transfer("Budget Stabilization Account: For transfer to the general fund, $514,000,000")
    assert direction(src, dst) == "rainy_day_to_gf"
    src, dst = parse_transfer("General Fund: For transfer to the Washington rescue plan transition account created in "
                              "section 1902 of this act, $1,000,000,000")
    assert (src, dst) == ("General Fund", "Washington rescue plan transition account")
    assert direction(src, dst) == "gf_to_other"
    src, dst = parse_transfer("(28) Multimodal Transportation Account—State Appropriation: For transfer to the "
                              "Move Ahead WA Account—State")
    assert (src, dst) == ("Multimodal Transportation Account", "Move Ahead WA Account")
    _, dst = parse_transfer("Oil Spill Prevention Account: For transfer to the oil spill prevention account for the "
                            "military department to continue assisting")
    assert dst == "oil spill prevention account"


class Row:
    def __init__(self, label, b, total, detail=False, order=0):
        self.label, self.biennium, self.total, self.is_detail, self.order = label, b, total, detail, order
        self.fy_a = self.fy_b = None


class V:
    def __init__(self, value, forecast=False):
        self.value, self.forecast = value, forecast


def test_shortfall_per_resident_after_inflation():
    def outlook(b, level, base):
        rows = [Row("Enacted Appropriations", b, base, order=1), Row("Maintenance Level Total", b, level - base, order=2),
                Row("K-12 Education", b, level - base, detail=True, order=3), Row("Forecasted Revenues", b, level, order=4)]
        # A biennial outlook lists (prior, new, next); only the new biennium has rows here.
        return (f"Enacted {b}", "u", rows, ["1999-01", b, "2099-01"])
    o1 = outlook("2021-23", 60_000, 55_000)
    o2 = outlook("2023-25", 66_000, 60_000)
    econ = {"seattle_cpi_fy": {y: V(1.0 if y < 2024 else 1.1) for y in range(2022, 2026)},
            "population": {y: V(1000.0) for y in range(2022, 2026)}}
    sf = shortfall([o1, o2], econ)
    t = {x["biennium"]: x for x in sf["trend"]}
    # 60B -> 66B nominal (+10%), prices +10%, population flat: per resident after inflation is flat.
    assert abs(t["2023-25"]["growth"]["per_resident_real"]) < 1e-9
    assert sf["drivers"]["2023-25"]["maintenance"] == 6_000

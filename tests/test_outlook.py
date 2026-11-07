from ingest.outlook import arithmetic_errors, parse_text

TEXT = """\
                                                                                                     2025-27                           2027-29
                                                                                      FY 2026        FY 2027    2025-27    FY 2028     FY 2029     2027-29
        NGF-O Beginning Balance                                                            2,536        1,112      2,536        277         -802         277
        Forecasted Revenues                                                              36,714        38,562     75,276    39,408       40,973       80,381
            Feb 2026 Revenue Forecast (NGF-O)                                             36,714       38,562     75,276     39,408       40,973       80,381
        Other Resource Changes                                                             1,115         717       1,832       -331       2,036        1,706
        Total Revenues and Resources                                                     40,365        40,391     79,644    39,354       42,208       82,363
        Enacted Appropriations                                                           38,471        39,387     77,858    39,763       40,568       80,331
        Maintenance Level Total                                                               746        980       1,727      1,006          963       1,968
        Policy Level Total                                                                    502        118        620        -237          415         179
        Reversions                                                                           -466       -371       -837        -376         -392        -768
        Revised Appropriations                                                           39,253        40,114     79,367    40,156       41,554       81,710
        NGF-O Projected Ending Balance                                                     1,112         277        277        -802          653         653
            NGF-O                                                                            2.9%        0.7%                 -2.1%         1.5%
"""


def test_outlook_parses_and_balances():
    rows, bienniums = parse_text(TEXT, "test")
    assert bienniums == ["2025-27", "2027-29"]
    end = {r.biennium: r for r in rows if r.label == "NGF-O Projected Ending Balance"}
    assert (end["2025-27"].total, end["2027-29"].fy_a, end["2027-29"].total) == (277, -802, 653)
    detail = next(r for r in rows if r.label.startswith("Feb 2026"))
    assert detail.is_detail
    pct = next(r for r in rows if r.label == "NGF-O" and r.is_detail and r.biennium == "2027-29")
    assert pct.total is None and abs(pct.fy_a + 0.021) < 1e-9
    assert arithmetic_errors(rows, bienniums) == []


def test_three_biennium_outlook_layout():
    """Biennial outlooks add the prior biennium: nine numbers per row."""
    text = """                          FY 2024  FY 2025  2023-25  FY 2026  FY 2027  2025-27  FY 2028  FY 2029  2027-29
        Enacted Appropriations           34,670   37,275   71,945   38,000   39,857   77,857   40,000   40,330   80,330
"""
    rows, bienniums = parse_text(text, "t")
    assert bienniums == ["2023-25", "2025-27", "2027-29"]
    assert [r.total for r in rows] == [71945, 77857, 80330]

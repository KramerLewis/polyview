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
    rows, meta = parse_text(TEXT, "test")
    assert meta["bienniums"] == ["2025-27", "2027-29"]
    end = next(r for r in rows if r.label == "NGF-O Projected Ending Balance")
    assert (end.biennium1, end.fy3, end.biennium2) == (277, -802, 653)
    detail = next(r for r in rows if r.label.startswith("Feb 2026"))
    assert detail.is_detail
    pct = next(r for r in rows if r.label == "NGF-O" and r.is_detail)
    assert pct.biennium1 is None and abs(pct.fy3 + 0.021) < 1e-9
    assert arithmetic_errors(rows) == []

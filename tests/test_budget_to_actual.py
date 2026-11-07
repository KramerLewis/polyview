from ingest.budget_to_actual import _biennium
from ingest.budget_to_actual import parse_text as parse_summary
from ingest.budget_to_actual_detail import parse_text as parse_detail
from ingest.budget_to_actual_detail import place

SUMMARY = """\
Rollup Fund                          Account            Agency                                              Expenditure Authority                           Final Budget       Actual Amounts         Total Variance
FAA-General Fund - Basic Account     001-General Fund   0120-Senate                                         011-Salaries and Expenses - FY 1                         44,119                 38,801              5,318
FAA-General Fund - Basic Account     001-General Fund   0120-Senate                                         012-Salaries and Expenses - FY 2                         44,923                 40,938              3,985
FAA-General Fund - Basic Account     001-General Fund   0120-Senate                                         031-Membership Dues - FY1                                   260                    260
                                                        0120-Senate Total                                                                                            89,302                 79,999              9,303
FAA-General Fund - Basic Account     001-General Fund   0160-State Investment Board                                                                                        -               (31,340)             31,340
                                                        0160-State Investment Board Total                                                                                -               (31,340)             31,340
"""

DETAIL = """\
State of Washington
Budget-to-Actual Detail Report
June 30, 2023
                                                                General Fund - Basic Account (AA)
                                                            Dept of Social and Health Services (3000)
                                                                       General Fund (001)
                                                 Original                 Final
                                                 Budget                 Budget                Actual            Variance
Resources
CE    Other contracts and grants             89,707,000            89,707,000           84,729,505            (4,977,495)
CJ    Investment income (loss)                                      96,295,000                                 (96,295,000)
Charges to Appropriations
F2    Human services
                                          Exp. Auth.
                                          EA2          1,788,451,000        1,766,316,000         1,431,224,831         335,091,169
                                          EH2                           -      85,463,000           68,741,297           16,721,703
\f
State of Washington
Budget-to-Actual Detail Report
June 30, 2023
                                 SV1      66             66               66                         -
                                 EA1   1,427,152,000       1,344,596,000   1,197,243,787         147,352,213
"""


def test_biennium():
    assert _biennium(2025) == "2023-25"
    assert _biennium(2024) == "2023-25"


def test_summary_rows_blank_variance_and_negatives():
    rows, checks = parse_summary(SUMMARY, 2025)
    assert checks == []
    dues = next(r for r in rows if r.authority_code == "031")
    assert (dues.final_budget_k, dues.actual_k, dues.variance_k) == (260, 260, 0)
    sib = next(r for r in rows if r.agency_code == "0160")
    assert sib.actual_k == -31_340 and sib.authority_code == ""


def test_place_uses_variance_arithmetic():
    # Original and actual blank on a resources line: variance = actual - final.
    assert place(["96,295,000", "(96,295,000)"], "resources") == (0, 96_295_000, 0, -96_295_000)
    # Original blank on a charges line: variance = final - actual.
    assert place(["-", "85,463,000", "68,741,297", "16,721,703"], "charges") == (
        0, 85_463_000, 68_741_297, 16_721_703)


def test_detail_carries_context_across_continuation_pages():
    rows, unplaced = parse_detail(DETAIL, 2023)
    assert unplaced == 0
    auth = {r.authority_code: r for r in rows if r.authority_code}
    assert set(auth) == {"EA2", "EH2", "SV1", "EA1"}
    assert all(r.agency_code == "3000" and r.account_code == "001" and r.line_code == "F2"
               for r in auth.values())
    assert auth["SV1"].actual == 66
    assert auth["EA1"].actual == 1_197_243_787
    inv = next(r for r in rows if r.line_code == "CJ")
    assert (inv.final, inv.actual) == (96_295_000, 0)

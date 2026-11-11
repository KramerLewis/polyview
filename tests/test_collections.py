from ingest.collections import _latest_period, _months_back, check, Collection


def test_latest_period_and_month_alignment():
    text = "Revenue Forecast Variance\n...\nSeptember 11 - October 10, 2026\n"
    y, m, label = _latest_period(text)
    assert (y, m) == (2026, 9) and label == "September 11 - October 10, 2026"
    # A December-January period starts in the earlier year.
    assert _latest_period("Revenue Forecast Variance\nDecember 11 - January 10, 2026")[:2] == (2025, 12)
    assert _months_back(2026, 9, 13)[0] == "2025-09" and _months_back(2026, 2, 3) == ["2025-12", "2026-01", "2026-02"]


def test_check_requires_components_to_add_up():
    rows = [Collection("x", "2026-09", "Department of Revenue-Total", False, 100_000),
            Collection("x", "2026-09", "Revenue Act", False, 90_000),
            Collection("x", "2026-09", "Non-Revenue Act", False, 10_000)]
    assert check(rows) == []
    rows[2] = Collection("x", "2026-09", "Non-Revenue Act", False, 20_000)
    assert check(rows)

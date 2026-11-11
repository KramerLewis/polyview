from ingest.discover import is_enacted_outlook


def test_outlook_filter_keeps_adopted_outlooks_only():
    keep = ["20230613 FY2023-25EnactedOutlook.pdf", "FY 2024 Enacted Outlook_Final.pdf",
            "2025 Enacted Outlook Final.pdf", "20260422_Enacted_Sup_BO_Adopted.pdf"]
    drop = ["20260422_Enacted_Sup_BO_Adopted_ Metho_Final.pdf", "2025 Enacted Budget Outlook Methodology Final.pdf",
            "20220421 Alternative Enacted Sup Operating Budget Outlook.pdf",
            "Governor's Proposed 2026 Supp Outlook_Final.pdf", "20260414_Outlook_Guidance_Memo.pdf"]
    assert all(is_enacted_outlook(n) for n in keep)
    assert not any(is_enacted_outlook(n) for n in drop)

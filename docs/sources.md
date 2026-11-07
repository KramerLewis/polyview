# Data source inventory

Status as of Phase 0 (November 2026). **Verified** means we fetched it from a
script and parsed it. Everything else is a lead to confirm in Phase 1.

Legend: ✅ verified and ingested · 🟡 reachable, access method understood, ingester not built · 🔴 hard to get (interactive-only, needs reverse engineering)

## Legislature and legislators

| Source | Access | Format | Status | Notes |
|---|---|---|---|---|
| Legislature web services: members (`SponsorService/GetSponsors`) | HTTP GET, no key | XML | ✅ `ingest/legislature.py` | 158 members for 2025-26 with chamber, party, district. |
| Roll-call votes (`LegislationService/GetRollCalls`) | HTTP GET, no key | XML | ✅ | Every floor vote on a bill, including amendment votes, with member names per position. Names are last names (plus initials when ambiguous), so they need matching to member IDs. |
| Bill metadata (`LegislationService/GetLegislation`) | HTTP GET | XML | 🟡 | Sponsors, status, companions, and flags for fiscal notes and appropriations. |
| Bill text (lawfilesext.leg.wa.gov) | Static files | **XML**, HTM, PDF, DOCX | ✅ | Budget bills are structured XML: `<Appropriations agency="NNN">` and one `<Appropriation>` per account line. Supplementals mark struck and added amounts. See below. |

## Appropriations (allocated)

| Source | Access | Format | Status | Notes |
|---|---|---|---|---|
| Enacted budget bills, session-law XML | Static files | XML | ✅ `ingest/budget_bills.py` | 2025-27 original (ESSB 5167, 2025 c 424) and 2026 supplemental (ESSB 5998). Gives section, agency code, account, fund source (state/federal/private-local), fiscal year and amount, plus "$X … is provided solely for …" provisos. |
| Historic enacted operating budgets | fiscal.wa.gov `StateBudgets/OperatingEnactedBills.aspx` | PDF back to 1985; XML on lawfilesext for recent bienniums | 🟡 | For backfill. Check how far back lawfilesext has XML. Older years may need PDF parsing or LEAP summary docs. |
| Capital and transportation budgets | Same as above | XML | 🟡 | Same parser should mostly work. Capital project lists include legislative district. |
| fiscal.wa.gov "Operating Budget Data" search | Embedded Power BI | none | 🔴 | No download. Avoid it, and use bill XML instead. |
| LEAP documents | fiscal.wa.gov `/leapdocs/*.xlsx` | XLSX, PDF | 🟡 | Only a few are XLSX (mostly K-12). Useful for reconciling our parsed totals. |
| OFM enacted budget page | ofm.wa.gov `/budget/state-budget-2025-27/enacted/` | PDF and XLSX | 🟡 | Partial-veto messages (which lines the governor vetoed) and the central services model XLSX. |

**Parsed totals (sanity check, not yet reconciled to LEAP):** the original 2025-27
bill's appropriation lines sum to **$136.6B** across all funds for 2025-27
($72.7B of it General Fund–State). The same bill also amends **$128.6B** of
2023-25 appropriations. Phase 1 has to reconcile these with LEAP's published
totals and work out how to "overlay" a supplemental onto the original, since a
supplemental only re-enacts the sections it changes.

## Allotments (planned)

| Source | Status | Notes |
|---|---|---|
| OFM allotment data (AFRS) | 🔴 not found yet | Agency monthly spending plans. No public bulk file found in Phase 0. Next leads: OFM's Agency Financial Reporting System pages, a public records request, or fiscal.wa.gov's Power BI dataset. |

## Expenditures (actual spending)

| Source | Access | Format | Status | Notes |
|---|---|---|---|---|
| Vendor payments ("Open Checkbook") | fiscal.wa.gov `Spending/VendorPayments2527.xlsx` | XLSX, about 33 MB per biennium | ✅ `ingest/vendor_payments.py` | 586,697 rows so far for 2025-27 ($54.0B). Columns: agency, fiscal month, object/sub-object, vendor, amount. **No fund or program**, so it shows who got paid but can't be compared line-by-line with appropriations. Check for older bienniums' files (`VendorPayments2325.xlsx`, …). |
| **OFM Budget-to-Actual Detail Report** | ofm.wa.gov ACFR page, one PDF per fiscal year (FY2020+) | PDF | ✅ `ingest/budget_to_actual.py` (FY2025), `ingest/budget_to_actual_detail.py` (FY2021, FY2023) | **Final budget vs. actual** by fund, agency, account and expenditure authority. FY2020–23 also have **original budget** and **revenue by source**. Budgetary basis. FY2025 matches all printed subtotals. See DECISIONS D-002, D-010–D-014. |
| Spending by biennium and historical trends | fiscal.wa.gov | Embedded Power BI | 🔴 | No download. Replaced by the Budget-to-Actual reports above. |
| Distributions to local entities | fiscal.wa.gov `Spending/SpendDistributionSourceTotals.aspx` | SSRS report viewer (FY2013–2026) | 🟡 | Includes an **"All Legislative Districts"** view. SSRS supports CSV/Excel export after a form postback, which is scriptable. |
| Agency contracts | data.wa.gov `6fx9-ncas` (FY2025) | Socrata API | 🟡 | |
| Annual Comprehensive Financial Report (ACFR) | OFM | PDF | 🟡 | Audited fund-level actuals. Used as the reconciliation anchor. |

**Update (Phase 1):** the agency × fund gap is largely closed for completed
bienniums by OFM's Budget-to-Actual reports. Still missing: **program-level**
actuals, **allotments**, and **current-biennium** actuals until OFM publishes the
FY2026 report. See [DECISIONS.md](DECISIONS.md).

## Revenue (income)

| Source | Access | Format | Status | Notes |
|---|---|---|---|---|
| fiscal.wa.gov "Revenue by Biennium" | SSRS report viewer | Exportable report | 🟡 | Statewide revenue by source and fund, 2003-05 to 2025-27. Same SSRS export approach as distributions. |
| ERFC revenue forecasts | erfc.wa.gov | PDF (quarterly publications) | 🟡 | Check the forecast archive for XLSX tables. Quarterly vintages give forecast vs. actual. |
| ERFC monthly collection reports | erfc.wa.gov | PDF | 🟡 | |
| ERFC four-year balanced budget outlook | erfc.wa.gov/budget-outlook | PDF (1 page) | ✅ `ingest/outlook.py` | NGF-O balance sheet for the current and next biennium; arithmetic self-checked. |
| DOR statistics (tax collections, local taxes, levies) | dor.wa.gov | Mixed (PDF, XLSX, interactive) | 🟡 | Includes local sales tax by city and county, property tax levy detail, and tax incentives. |
| Tax structure guide | fiscal.wa.gov | PDF | reference | Use for plain-language explanations of each tax. |

## Forward-looking (proposed and hypothetical)

| Source | Access | Status | Notes |
|---|---|---|---|
| OFM fiscal notes (fnspublic.ofm.wa.gov) | HTML search form | 🟡 | Covers **bills and initiatives**. The form posts by JavaScript, so the request needs reverse-engineering. |
| Secretary of State voter pamphlet, fiscal impact statements | sos.wa.gov | 🟡 | Ballot measure fiscal impacts. |
| Governor's proposed budget and agency requests | ofm.wa.gov | 🟡 | Proposed supplementals and the next biennium (2027-29 instructions are already up). |

## Geography

| Source | Status | Notes |
|---|---|---|
| Census TIGER/Line 2025, state legislative districts (SLDU/SLDL, state 53) | ✅ `ingest/districts.py` | Shapefiles, about 1.9 MB each. Need to confirm which district map each vintage reflects (2022 redistricting, plus the 2024 Yakima Valley court-ordered remap). |
| WA Redistricting Commission | 🟡 | Official plans and historic maps for backfill. |
| OFM legislative district population tables | 🟡 | Per-capita figures by district. |

## Audits

| Source | Status | Notes |
|---|---|---|
| State Auditor's Office (sao.wa.gov) report search | 🟡 | Performance audits and accountability reports. Need to find whether there's an API or a bulk export. |
| SAO local government financial data (FIT) | 🟡 | data.wa.gov `dtm4-hsyt` links to these tools. |

## Not useful (checked)

- **data.wa.gov** has little state budget data. Searches for expenditure, revenue
  and budget return campaign finance (PDC), county roads, IT spend and Amazon spend.
  It is still useful for PDC data later.

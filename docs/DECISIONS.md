# Decisions, assumptions and weak points

A running log of choices that affect what the numbers mean. Newest entries go
at the top of each section. Anyone citing polyview data should read this.

Each entry has a status:
- **open**: a known weakness we haven't resolved
- **accepted**: a deliberate trade-off
- **resolved**: fixed, kept for history

---

## Data sources

### D-001 · Budget bills come from the Legislature's XML, not PDFs or Power BI (accepted)
The enacted budget bills on lawfilesext.leg.wa.gov are structured XML with agency
codes and one element per appropriation line. We parse those instead of the
PDFs or fiscal.wa.gov's Power BI report.
- **Upside:** exact, reproducible, and the official legal text.
- **Weak point:** XML is only confirmed for recent bienniums. Older budgets may
  need PDF parsing, which is less reliable.

### D-002 · Actual spending comes from OFM's Budget-to-Actual reports (accepted)
The fiscal.wa.gov spending history is Power BI only, with no download. Instead we use
OFM's annual **Budget-to-Actual Detail Report**, published alongside the
audited ACFR, FY2020 onward.
- **Upside:** it's the official, audited-context comparison of final budget vs. actual,
  by fund, agency, account and expenditure authority. The older layout also has
  **revenue by source** and **original** budget.
- **Weak points:**
  - **It's annual, so the current biennium lags.** The first 2025-27 report
    (FY2026) wasn't published as of November 2026. Until it is, current-biennium
    "spent" figures can only come from vendor payments (D-003).
  - **Budgetary basis, not GAAP.** These numbers differ from the ACFR's
    financial statements on purpose. We must say "budgetary basis" wherever we show them.
  - **Parsed from PDF.** We guard against errors with subtotal checks (D-010),
    but layout changes can break the parser. FY2025 already changed layout.
  - **Layouts differ by year.** FY2020–2023 use the long format (whole dollars, with
    revenue and original budget). FY2025 uses a summary format (thousands, final budget only, no
    revenue). FY2024 uses a third layout we don't parse yet.
  - **No program dimension.** Expenditure authority codes are close to, but not the same as,
    budget-bill sections and programs. That mapping lives in the crosswalk.

### D-003 · Vendor payments are "who got paid", not "budget vs. actual" (accepted)
The Open Checkbook file has agency, object and vendor, but **no fund or program**.
We use it to show payees and to give a current-biennium spending pace,
never for line-by-line comparison with appropriations.

### D-004 · Only odd-year Budget-to-Actual reports are used for completed bienniums (accepted)
The odd fiscal years (FY2021, FY2023, FY2025) close a biennium and are the complete
record. Even years are mid-biennium snapshots that the odd years supersede.
- **Weak point:** we lose the mid-biennium view for past years. It's recoverable later
  (FY2020/FY2022 parse with existing code; FY2024 needs work).

### D-005 · No public records requests (accepted)
Per the project owner, we only use publicly downloadable data.
- **Consequences:**
  - **No allotment (agency spending-plan) data yet.** The "planned" stage is missing
    until a public source is found.
  - **No program-level actuals.** Comparisons stop at agency × fund × expenditure authority.

### D-006 · Raw downloads aren't committed; CI can rebuild them (accepted)
Raw PDFs and XLSX (tens of MB) stay out of git. Every fetch is logged with URL,
time and SHA-256 in `data/raw/manifest.jsonl`. Samples and small derived files
are committed.
- **Weak point:** if an agency replaces or removes a file, rebuilding gives
  different results. Mitigation: we keep the hashes, and might archive raw files in a release later.

---

## Parsing and method

### D-010 · Parsers must check themselves against the source's own totals (accepted)
- **Budget-to-Actual FY2025:** parsed rows are summed per agency, account and
  rollup fund and compared with the report's printed subtotals. Up to $5K of
  difference is allowed, because each line is rounded to $1K. Result: **0 mismatches**.
- **Budget-to-Actual FY2021/FY2023:** fund pages are compared with the sum of their
  deepest detail pages. The remaining differences are written to
  `data/samples/budget_to_actual_detail_fy20XX_reconciliation.csv` and fall into
  known categories (D-011, D-012).

### D-011 · Transfers between funds are fund-level only (open)
The "HZ – Transfers to other funds" charges appear on fund pages but aren't
broken out by agency or account. Summing agency spending therefore leaves out
transfers, which is correct for "what did agencies spend" but must be labeled. Fund totals
include them, and that can double-count money that moves between funds if
fund totals are added together.

### D-012 · The "Administrative Accounts in the General Fund" (AC) group doesn't reconcile (open)
Its fund-level resources and charges differ from the sum of its agencies by up to
about $600M in transfers in, and about $150M in general-government spending. Likely cause:
interfund eliminations or entries recorded only at the fund level. Small
differences in noncash and reserve items (Z2/ZA) also appear in a few funds.
**Until we explain this, AC agency figures carry a warning.**

### D-013 · Accounting pseudo-agencies are flagged, not dropped (accepted)
"OFM Financial Statement Control" (7000) and "Treasurer's Transfers" (7010) appear
as agencies but are accounting entries. They're kept so totals reconcile, flagged
`is_adjustment`, and excluded from agency views.

### D-014 · Some accounts appear under two rollup funds with different numbers (open)
In FY2025, accounts 031 (State Investment Board Expense) and 19L (Charter
Schools Oversight) appear under both "Administrative Accts in the General Fund"
and "Central Admin and Regulatory Fund". **Never sum across rollup funds**
without deduplicating, and only show statewide totals at the account level.

### D-015 · A biennium is assigned from the fiscal year or the amended chapter (accepted)
Budget-bill lines with "(FY 2026)" get their biennium from the fiscal year. Lines
without one are biennial, and their biennium comes from the session-law chapter
the section amends (a hand-maintained table in `ingest/budget_bills.py`), or
from the bill's own biennium for new sections.
- **Weak point:** the chapter table must be extended for each new budget, or older
  amendatory lines come out blank.

### D-016 · The current budget is the original overlaid with supplementals (accepted)
Supplementals strike and replace amounts, and reprint only the sections they
change. `ingest/budget_current.py` starts from the original enacted lines,
replaces each reprinted section's lines with the supplemental version, and keeps
`original`, `after_<supplemental>` and `current` columns.
- **Matching:** lines are matched by section, normalized account name, and
  occurrence order within the section. Some DSHS sections repeat the same account
  across program blocks.
- **Self-check:** each supplemental line's struck amount must equal the
  enacted amount. For 2025-27 that holds for **every matched line**.
- **Result (2025-27):** agency appropriations go from **$133.78B original** to
  **$139.15B current** after the 2026 supplemental. Transfers and distributions are excluded (D-020).
- **Weak point:** when a supplemental rewords a line (a renamed account, a
  restructured transfer), it appears as one line removed and one added. Totals
  stay right, but that line's history is split. These are listed in
  `data/samples/budget_current_2025-27_issues.csv` (19 for 2025-27) and should
  be linked by hand in `crosswalk/`.

### D-017 · Parsed totals are reconciled to ERFC's adopted outlooks on every build (resolved for operating NGF-O)
The Legislature's headline figure is **NGF-O** (Near General Fund-Outlook: General Fund–State,
Education Legacy Trust, Washington Opportunity Pathways and Workforce Education Investment
accounts). `ingest/checks.py` recomputes it from the parsed bills at each step of the
amendment chain and compares it with `crosswalk/reference_totals.csv`, where every expected value
is the "enacted level" (enacted + carry-forward + maintenance + policy, before assumed reversions)
in the ERFC outlook adopted for that budget. **The site build fails if a check is out of tolerance.**

| Check | Parsed | ERFC | Off |
|---|---|---|---|
| 2023-25 original | $69.765B | $69.805B | 0.06% |
| 2023-25 after 2024 supplemental | $71.905B | $71.944B | 0.05% |
| 2023-25 after 2025 changes | $72.514B | $72.743B | **0.31%** |
| 2025-27 original | $77.874B | $77.857B | 0.02% |
| 2025-27 after 2026 supplemental | $80.206B | $80.205B | 0.00% |

- NGF-O counts appropriations only. Treasurer "appropriation for … distributions" lines are excluded.
- **Open:** the last 2023-25 step is $229M low (tolerance set to 0.5% and noted in the CSV). A
  steady ~$40M gap at every 2023-25 step suggests NGF-O appropriated in other bills. The
  extra ~$190M in 2025 was investigated and isn't an overlay mismatch: the flagged lines are
  non-NGF-O, transfers, or genuine removals. Likely cause: FY2025 NGF-O appropriated in other 2025 bills.
- All-funds totals can't be checked the same way. Published "total budgeted" includes
  appropriations in other bills and non-appropriated funds. Transportation and capital have no
  reference check yet.

### D-018 · Governor's line-item vetoes are applied (resolved)
The XML marks vetoed text with `lineVeto="yes"`. Vetoed appropriation lines
(5 in the original 2025-27 bill, 3 in the 2026 supplemental) count as $0 in
`current`, and vetoed provisos are flagged.
- **Weak point:** vetoes of whole sections, or of conditions that don't change a dollar
  line, affect meaning rather than totals. Only the flag records those.

### D-020 · Budget-bill lines are classified as appropriation, transfer or distribution (accepted)
Budget bills also move money between funds ("For transfer to the state general
fund, $X…") and make special distributions to local governments. Those aren't
agency spending, and adding them to appropriations double-counts. They're labeled
by keywords in the account text (`classify()` in `ingest/budget_bills.py`).
- **Weak point:** keyword rules may misclassify unusual wording.

### D-019 · Proviso extraction is pattern-based (accepted)
"$X of the … appropriation … is provided solely for …" is matched with a regular
expression. It catches the standard form but will miss unusual wording, and it
records references in a paragraph that aren't earmarks ("Of the amounts provided in
subsection (a), $X …"). Treat proviso counts as approximate.

### D-021 · Roll-call names are matched to legislators by chamber and last name (accepted)
Roll calls list last names, adding an initial when two members share one ("Wilson, C.").
We match on biennium, chamber, last name and initial. For 2025-26 budget votes **2,792 of
2,792** member votes matched.
- **Weak point:** a member who leaves mid-biennium and a replacement with the
  same last name would be ambiguous. Unmatched votes are left blank, never guessed.
- **Weak point:** the member list is the biennium roster, so the district is the
  member's district in that biennium.
- **Members who changed chambers** (e.g. appointed from the House to the Senate) appear
  once per chamber, each with only that chamber's votes.

### D-022 · Votes are classified by motion text (accepted)
`final_passage` = the vote sending the final (conference or concurrence) version to the
governor. `passage` = a chamber passing its own version. `amendment` = a numbered floor
amendment, with sponsor. `procedural` = everything else.
- Amendment content now comes from staff EFFECT statements (D-029).
- **Note:** roll-call sequence numbers aren't unique within a chamber, so a roll call is identified by
  bill, chamber, sequence **and** date.

### D-029 · Amendments are described by quoting staff EFFECT statements (accepted)
Each floor amendment's text ends with an "EFFECT:" statement (and usually "FISCAL IMPACT:"
and "FOUR-YEAR OUTLOOK EFFECT:"), written by nonpartisan committee staff. The site quotes
these verbatim, linked to the amendment text, and never paraphrases or characterizes an
amendment itself.
- 2025-26 budget bills: **103 floor amendments**, 100 with an EFFECT statement. **Only 22 had
  recorded roll calls.** The rest were voice votes, so individual positions don't exist.
- Striking amendments (whole alternative budgets) have no EFFECT statement and are labeled as such.
- **Weak point:** extraction relies on those labels appearing in the HTML text. Amendments
  without them show "—". Committee amendments aren't included yet.

### D-023 · Agencies are joined across sources by 3-digit code (accepted)
Budget bills and vendor payments use 3-digit agency codes ("300" = DSHS). OFM's
Budget-to-Actual uses 4 digits ("3000"). We join on the first three digits.
- **Weak point:** this has been spot-checked (House, Senate, DSHS, OSPI), not proven for
  every agency. A mismatch would show as an agency missing from one side.

### D-024 · Vendor payments are not shown as "budget spent so far" (accepted)
The Open Checkbook file has no salaries and benefits (objects A/B), and evidently omits
large payments to local governments. OSPI shows $0.87B paid against a ~$37B
budget because school apportionment isn't in it. Showing it as progress against the budget
would mislead badly, so it appears only on agency detail, labeled as payments to
vendors and grantees with an explicit "not a measure of budget spent" note.
- **Consequence:** the site has **no current-biennium spending pace** until OFM
  publishes the FY2026 Budget-to-Actual report.

### D-025 · When bill XML metadata contradicts the printed text, the printed text wins (accepted)
In the 2025-27 capital budgets, two projects' hidden `project` attributes disagree with the
project number printed in the law (e.g. ESSB 6003 sec. 1001: attribute 40000010,
printed "Point Whitney Appraisal (92000002)"). The printed number is used, and rows are flagged
`xml_conflict`. The agency attribute can also be wrong in these cases: that section is
printed as the Governor's special appropriation but tagged agency 085.

### D-026 · Budget vs. actual compares appropriated lines only (resolved)
"Over budget" agencies (State Treasurer/Bond Retirement +33%, UW +29% in 2023-25) were caused
by OFM report rows with **no expenditure authority**: activity recorded against an agency and
fund with no appropriation line, so the budget is $0. Examples: bond debt service paid from
transportation accounts ($516M from the Transportation Partnership Account), UW General Fund
activity ($263M). Statewide these rows held $12.6B actual vs $7.0B budget, including
adjustment pseudo-agencies.
- Budget vs. actual now uses **appropriated lines only**: 2023-25 statewide **$136.7B
  spent of $161.5B (84.7%)**. The other $3.1B (excluding adjustments) is shown separately.
- With that, Bond Retirement is at 99.9% and UW at 90.0%. **The only agency over budget on
  appropriated lines is Contributions to Retirement Systems (+4.9%)**, which is **open** to explain.
- **Weak point:** we infer "statutory or nonappropriated authority" from the missing
  authority line. OFM's report doesn't say why each row has none.

### D-027 · 2025-27 totals cover all three budgets; capital reappropriations are separate (accepted)
OFM's actuals cover operating, transportation and capital together, so 2025-27 figures
also combine all three bills (ESSB 5167/5998, 5161/6005, 5195/6003). Capital
reappropriations ($11.4B in 2025-27) are money already appropriated in earlier
bienniums and carried forward. They're excluded from "enacted" totals so the same dollars
aren't counted in two bienniums, and shown separately.
- **Weak point:** OFM's capital "final budget" for 2023-25 *includes* that biennium's
  reappropriations, so 2023-25 budget vs. 2025-27 enacted isn't an exact like-for-like
  comparison for capital-heavy agencies.

### D-028 · Statewide 2023-25 totals sum across rollup funds (open)
The overview's "share of final budget spent" sums every non-adjustment row of the FY2025
report. Accounts listed under two rollup funds (D-014) are counted twice. The effect is small
(tens of $M on $162B), but it's not zero.

### D-034 · Current-biennium income vs. spending comes from ERFC's adopted outlook (accepted)
ERFC publishes the four-year balanced budget outlook adopted for each enacted budget as
a one-page PDF ($ millions). We parse it (`ingest/outlook.py`) and check its own identities
on every build: resources = beginning + forecast + other, revised appropriations =
enacted + maintenance + policy + reversions, ending = resources − revised. The build fails
if any is off by more than $3M.
- It covers **NGF-O accounts only**, not federal or dedicated funds. The site says so.
- The second biennium (2027-29) is an **official projection**, labeled as such. It's the
  first "future" view on the site, and comes before any user scenarios (Phase 5).
- It also gives the primary-source references for D-017. Parsed NGF-O is within 0.02% of the
  outlook's "Enacted Appropriations" and 0.001% of enacted + maintenance + policy.
- **Weak points:** revenue here is the *forecast* (Feb 2026), not collections to date.
  Monthly collection reports are PDF-only and not parsed yet. Only one outlook vintage
  is ingested, so "how the forecast changed" isn't shown yet.

### D-035 · Capital projects by district come from a committed snapshot of LEAP's report (accepted)
LEAP's "capital projects by legislative district" report is an SSRS report viewer that only
works with JavaScript, so `scripts/fetch_capital_districts.js` drives a headless browser to
export each district's CSV. The CSVs are committed under `data/snapshots/capital_districts/`
with the version label and fetch time, and the weekly build reads the snapshot.
- **Why a snapshot:** a browser in CI is heavy and fragile, and enacted project lists only
  change when a budget passes. **Weak point:** someone has to re-run the script after
  each enacted capital budget. Add it to the release checklist.
- **Current snapshot:** the 2025 enacted capital budget (05/20/2025): 1,252 project rows,
  all 49 districts, every district's rows equal its printed total.
- The 2026 supplemental's list is now included (D-040).

### D-036 · District capital totals count location-specific amounts only (accepted)
LEAP marks with "$" any amount that funds an entire project spanning several locations.
Those ($0.63B of $4.10B) aren't attributed to the district they're listed under. They're shown
in the project list but left out of district totals and rankings. Other markers (alternative
financing, preliminary minor works, "only the local components") are shown as labels.
- **Interpretation:** totals mostly reflect where state facilities are (universities,
  hospitals, prisons). The site says so and doesn't present district totals as a
  fairness measure.

### D-037 · Supplemental citations are translated through the amendment chain (accepted)
A later supplemental cites sections by the *previous supplemental's* numbering, which
differs from the original's. For example, ESSB 5167 sec. 1103 amends "2024 c 376 s 112", which is section
112 of the 2024 supplemental, itself an amendment of a different original section. The overlay builds a
map (chapter, section) → original section as it processes each bill in order, using the chapter
number printed in each bill's XML.
- Each bill is parsed with **its own** budget biennium, so a 2025 bill's new 2025-27 sections are
  never mistaken for the 2023-25 sections it also amends. (This bug briefly doubled 2023-25 totals.)
- **Backfilled so far:** 2023-25 operating, transportation and capital, with the 2024 supplementals
  and the 2025 changes. Earlier bienniums need the same chain set up, and older
  bills may lack XML.

### D-038 · Each outlook's columns come from its fiscal-year header (accepted)
Supplemental outlooks show two bienniums. Biennial outlooks show three: prior, new, next. The
parser reads the bienniums from the "FY 2026 FY 2027 …" header row and stores values in long
format. An earlier version assumed six columns and silently mis-read the three-biennium
layout. Its arithmetic checks only covered the columns it kept, so it didn't catch the
problem. Now every biennium in every outlook must pass the identities, and a test covers
the nine-column layout.

### D-039 · The money-flow Sankey traces money only as far as a fund (accepted)
The overview's Sankey runs revenue sources → fund groups → areas of government, from OFM
Budget-to-Actual fund pages (actuals, budgetary basis; 2019-21 and 2021-23).
- **No source → area links.** Money mixes inside a fund. Link colors follow the revenue
  source only into the fund, and links out of funds are neutral gray, so the visual never
  implies "your sales tax paid for X".
- **Transfers between funds are netted out** (D-011). Each fund group's gap between revenue
  and spending is shown as a gray node: "Bonds, transfers & balances" ($3.9B in 2021-23,
  mostly capital funded by bond proceeds) or "To balances & transfers out" ($2.9B). Every
  node balances, and nothing is quietly dropped.
- Fund rollups are grouped by hand into 7 groups (`FUND_GROUP` in `publish/flows.py`).
- **Weak points:** "Other revenue" lumps contracts, timber, interest, miscellaneous and
  unclaimed property together. Fund grouping is a judgment call. The latest complete
  flow is 2021-23, because FY2025's report has no revenue. 2025-27 "as enacted" needs
  revenue by fund, which ERFC doesn't publish in this form.
- On phones the same three columns render as bar lists. Every view has a table.

### D-040 · District capital figures use the 2026 revised list; 2025 detail kept separately (accepted)
The current district list comes from LEAP's supplemental comparison report with format
"Biennial + Supp = Revised", fetched by `scripts/fetch_capital_districts.js supp`.
- **Report quirk:** with Version 1 and Version 2 set to the same version, the report
  double-counts every amount (e.g. $419K became $838K). Version 2 must differ, so we set it to
  "Passed Legislature" and use the Version 1 (Enacted, after vetoes) columns. Check: District 1's
  revised total equals the 2025 list plus the 2026 changes ($9,139K + $8,257K = $17,396K).
- The revised list is **program-level** for grant programs ("2026 Local and Community Projects").
  The 2025 list named individual local projects. The site shows current totals and the
  program-level list, with the 2025 project-by-project list underneath. They're never added together.
- 2026 revised: $4.47B listed by district, $3.68B location-specific (+$0.21B vs 2025). Most of the
  2026 supplemental's $1.8B capital increase isn't tied to a district.
- Every district's rows equal its printed total in both snapshots.

### D-041 · LEAP's two district reports flag some projects differently; we follow the current one (open)
Among 196 projects that appear in both the 2025 enacted and 2026 revised district lists, **12
($359M) changed their "$" multi-location flag**. Most are single-site facilities: Western State
Hospital's new forensic hospital ($282M), its water system ($27M), Monroe Correctional Complex
projects ($31M). That suggests the reports flag them differently rather than the projects
changing. District 28's location-specific total falls from $352M to $53M as a result.
- We follow the current report (it's the source for current totals) and mark each such
  project on the site with what the 2025 list said. We don't override LEAP's flags ourselves.
- **Open:** ask LEAP, or check the capital budget's project descriptions, which flag is right.

### D-042 · Tax collections come from ERFC's monthly updates, combined across issues (accepted)
Each monthly Economic & Revenue Update has 13 months of General Fund–State collections by tax.
We parse the Oct 2023–Oct 2026 issues (`ingest/collections.py`), and the newest issue wins for
each month, since ERFC revises history. Every month must satisfy Revenue Act + non-Revenue Act =
DOR total, or the build fails. Column alignment is anchored on the latest collection period named
in the variance table, and checked: the last column equals the variance table's "actual".
- **Shown:** collected so far this biennium (15 periods, $40.0B) vs. the same periods of 2023-25
  (+10.2%), each month with the same month two years earlier, by-tax change over 12 months, and
  ERFC's own variance against its latest forecast.
- **Deliberately not shown:** collections as a percentage of the biennial forecast. The outlook's
  forecast is NGF-O, a broader set of accounts on a different timing basis, so the ratio would
  mislead.
- **Caveats on the page:** periods are collection months (mostly the prior month's activity), and
  growth partly reflects 2025 tax increases. Only the General Fund is covered, not dedicated or
  transportation accounts.
- **Weak point:** the issue list is hand-maintained. Each new month needs its URL added (or a
  scraper of the listing page).

### D-043 · New source files are discovered weekly; only self-checking sources are used automatically (accepted)
`ingest/discover.py` runs first in every build and writes `data/samples/freshness.json`.
- **Used automatically:** ERFC monthly collection reports (the latest issue and the ones 12, 24 and
  36 months earlier) and adopted budget outlooks (file names containing "Enacted", excluding
  methodology, alternatives, memos and guidance). Both parsers check their own arithmetic.
  Pinned outlooks must pass; a newly found one that fails is skipped and logged, not published.
- **Flagged for a person:** enacted budget bills listed on fiscal.wa.gov that aren't configured
  (their amendment chain and reference checks need setting up), and new OFM Budget-to-Actual
  reports (layouts change). The build opens or updates one GitHub issue per item
  (`scripts/report_issues.py`).
- **Build failures** open or update a "Weekly site build failed" issue. The live site keeps the last
  good version.
- **Not automated:** LEAP's district project lists need a headless browser (D-035). Re-run
  `scripts/fetch_capital_districts.js` after each capital budget.
- Each section shows a "Data as of" line, and Data & methods has a freshness table.
- **Weak points:** discovery relies on ERFC and fiscal.wa.gov page structure and file naming. If a
  site is down, the build uses the files it already knows and reports the error in an issue.

### D-044 · Address lookup uses the U.S. Census Geocoder, called from the visitor's browser (accepted)
The Districts page turns an address (or the device's location) into a legislative district with the
Census Geocoder: `onelineaddress` or `coordinates`, layer 56 (state legislative districts, upper).
Washington uses the same 49 districts for both chambers.
- **Privacy:** the request goes straight from the visitor's browser to the Census Bureau. polyview has no
  server and never sees or stores the address. The page says so next to the box.
- **JSONP**, because the geocoder sends no CORS headers. It's a script include from a U.S. government domain.
- **Map vintage:** the geocoder returns "2026 State Legislative Districts", which reflect the 2024
  court-ordered Yakima Valley changes. Spot checks: Olympia → 22, Seattle (Space Needle) → 36,
  downtown Yakima → 14.
- **Weak points:** new or rural addresses may not match, and out-of-state results are rejected. Both
  cases link to the Legislature's official district finder. An address on a district boundary is
  resolved by Census geometry, which could differ from county election records in rare cases.

### D-045 · Backfill: 2019-21 and 2021-23 budget chains, and agency history (accepted, partly open)
Added the 2019-21 chains (1109 → 6168 → 2021 changes; 1160 → 2322 → 2021; 1102 → 6248 → 2021) and the
2021-23 chains (5092 → 5693 → 2023 changes; 5165 → 5689 → 5975 "additive" Move Ahead WA → 2023;
1080 → 5651 → 2023). All bills have Legislature XML. Bond-authorization bills (1101, 5084) are left out.
- **Reconciliation (D-017):** NGF-O at each step is within 0.11–0.72% of ERFC's enacted levels. Parsed
  values run *high* for 2019-21 after 2020 and for 2021-23, which points to vetoes of provisos not tied
  to a dollar line, and appropriations made or reduced in other bills. Tolerances are set just
  above today's values so regressions are caught. **Open.**
- The 2019-21 chain shows 32 "prior ≠ enacted" mismatches at the 2021 step: other bills (e.g. early
  2021 federal relief) amended 2019-21 between supplementals. Final values come from the 2021 bill's
  new amounts, so they're correct, but line history for that step is incomplete.
- **Agency history:** each agency page shows, per biennium, enacted in bills vs. OFM final budget vs.
  spent (appropriated lines only, D-026), for 2019-21, 2021-23 and 2023-25 (FY2021, FY2023 detail
  reports; FY2025 summary), plus 2025-27 enacted.
- **Finding to explain (open):** in 2021-23 OFM's final budget far exceeds what bills enacted for
  some agencies (DSHS $22.3B vs $17.9B, Commerce $11.6B vs $6.3B, DCYF $6.8B vs $4.2B), while
  2019-21 matches closely. Likely federal COVID funds added through unanticipated receipts and
  capital reappropriations. Confirm before presenting a cause.
- **Not done:** the FY2024 report layout (even years are superseded, D-004). Earlier bienniums
  (2017-19 and before) aren't on OFM's site in this report series.

---

## Presentation

### D-030 · Variance is shown as a question, not a verdict (accepted)
Underspending can mean savings, delays, lower caseloads, lapsed federal
authority, or a timing difference between years. Overspending (negative variance) can be
nonappropriated activity or accounting entries. Pages will say this next to every variance.

### D-032 · Party is shown as text, never as color (accepted)
Red/blue party coloring frames the data as partisan before anyone reads it. Party
appears as a plain "D"/"R" column. Charts use one neutral hue for amounts.

### D-033 · A dependency-free static site, rebuilt from public sources in CI (accepted)
The site is plain HTML/CSS/JS reading one JSON file. GitHub Actions re-fetches all
sources, runs the tests, rebuilds the data and deploys to GitHub Pages on every push
and weekly. Generated data isn't committed.
- **Upside:** anyone can audit and reproduce it, and there's no server to run.
- **Weak point:** if a state website is down or changes a file layout, the weekly build
  fails and the site keeps the last good version (the deploy step doesn't run).
- **Trade-off vs. the original plan:** no dbt/DuckDB yet. The Python transforms are small
  enough for now. Revisit when backfill adds many bienniums.

### D-031 · Geography only where the money really has a place (accepted)
Operating spending is mostly statewide (Medicaid, payroll, K-12 formula). We
attribute to legislative districts only capital projects, local distributions,
and other payments that carry a location. Everything else is shown as statewide.

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

### D-017 · Parsed bill totals aren't yet reconciled to LEAP's published totals (open)
The original 2025-27 operating budget's lines sum to $136.6B across all funds. LEAP's
published total is the reference we haven't matched yet. Possible reasons for differences:
special appropriations to the State Treasurer (distribution lines without a
fund-source suffix), nonappropriated amounts, and vetoes.

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

---

## Presentation

### D-030 · Variance is shown as a question, not a verdict (accepted)
Underspending can mean savings, delays, lower caseloads, lapsed federal
authority, or a timing difference between years. Overspending (negative variance) can be
nonappropriated activity or accounting entries. Pages will say this next to every variance.

### D-031 · Geography only where the money really has a place (accepted)
Operating spending is mostly statewide (Medicaid, payroll, K-12 formula). We
attribute to legislative districts only capital projects, local distributions,
and other payments that carry a location. Everything else is shown as statewide.

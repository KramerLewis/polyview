# polyview plan

## Goal

Follow Washington State money across five stages: **revenue in → appropriated → allotted → spent → impact**.
Map it to legislators and districts, for past budgets, the current one, and proposed or hypothetical ones.

Audiences:
- **Voters** need plain language, maps, and "what's in my district / on my ballot."
- **Legislators and staff** need variance tables, drill-downs and exports.

## Principles

- **Nonpartisan.** Show facts and methods, with no editorial scoring of legislators.
- **Provenance on every number.** Each figure links to its source document,
  row and fetch date (`data/raw/manifest.jsonl`).
- **Flags, not accusations.** Variance has legitimate causes, such as timing,
  federal match and lapsed funds.
- **Label the mode.** Every view says whether it shows *actual*, *enacted*,
  *official projection*, or *user scenario*.
- **Be honest about geography.** Most operating spending (Medicaid, payroll) is
  not district-attributable. Show it as statewide and never invent an allocation.

## Data model (target)

```
Biennium ─┬─ Revenue (source/tax, fund, period, amount) · RevenueForecast (vintage, fund, period, amount)
          ├─ BudgetBill ─ Section ─ Appropriation (agency, account/fund, fund source, FY, prior_amount, amount)
          │                       └ Proviso ("$X … solely for …")
          ├─ Allotment (agency, program, fund, object, month, amount)
          ├─ Expenditure (agency, program?, fund?, object, vendor?, location?, month, amount)
          └─ CapitalProject (project, agency, district, appropriated, reappropriated, spent)
Legislator ─ Term ─ District(geometry, map vintage)
RollCall ─ Vote (member, position) · Sponsorship
FiscalNote (bill/initiative, agency, fund, biennium, amount) · BallotMeasure
AuditFinding (entity, year, severity, url)
SourceRecord (url, fetched_at, sha256): attached to every row
```

The hardest part is the **crosswalk** between budget-bill accounts and accounting
codes (agency, program, fund). It lives in `crosswalk/` as versioned, reviewable
CSVs with a confidence flag on each match.

## Three modes for the future

1. **Official projections:** ERFC revenue forecasts, the four-year outlook, fiscal notes, and voter pamphlet fiscal impact statements. Sourced only; no modeling by us.
2. **"On my ballot / in session":** enter an address to see your district, your legislators, active bills with fiscal notes, and your ballot measures, plus which revenue or spending lines each one moves.
3. **Sandbox:** change tax rates or appropriations and see the effect on fund balances and the four-year outlook. It uses simple, visible models (baseline × change, with optional editable elasticities), runs fully in the browser, and saves scenarios in the URL. Results are always labeled as user estimates.

## Architecture

- **Ingest:** Python. One module per source in `ingest/`. Raw files are kept unchanged, with provenance.
- **Transform:** dbt on DuckDB producing Parquet (`models/`). DuckDB spatial handles the district overlays.
- **Publish:** a static site on GitHub Pages (`web/`) with MapLibre maps, DuckDB-WASM or JS for the sandbox, and downloadable CSV/Parquet.
- **Refresh:** a scheduled GitHub Actions job re-runs the pipeline and publishes a diff of changed numbers.
- **Later, if needed:** Postgres + PostGIS behind a small API.

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0. Discovery | Verify sources, sample pulls, inventory (`docs/sources.md`) | **done** |
| 1. MVP | 2025-27: revenue by source/fund, operating appropriations (original + supplemental overlay), spending, legislators and budget votes. First static pages. | next |
| 2. Districts | Capital budget by district, address lookup, local distributions by district, approximate local revenue overlay | |
| 3. Backfill | Earlier bienniums, inflation and per-capita adjustment, code crosswalk across years, historic district maps | |
| 4. Forward-looking | Forecasts, outlook, fiscal notes, ballot measures, "on my ballot" view | |
| 5. Sandbox | Interactive scenario builder | |
| 6. Audit depth | SAO findings, anomaly flags, proviso tracking, capital reappropriation chains | |

## Phase 1 to-do (from Phase 0 findings)

1. ~~**Actual expenditures by agency × fund.**~~ Done for completed bienniums via
   OFM's Budget-to-Actual reports (DECISIONS D-002). Program level and allotments
   remain open. No records requests (D-005).
2. **Supplemental overlay.** Combine the original budget with supplementals by
   section, so each line has *original*, *supplemental change*, and *current* values.
3. **Reconcile parsed totals** against LEAP/OFM published totals. Add this as a test.
4. **SSRS export scraper** for Revenue by Biennium and Distributions to Local
   Entities (the latter has an "All Legislative Districts" view).
5. **Match roll-call names to member IDs.**
6. **Vetoes.** Apply the governor's partial vetoes (OFM veto messages, `SeeVetoNote` in the XML).
7. **Agency code reference table** from bill XML plus vendor payment data.
8. **First static site:** agency pages (appropriated vs. paid), legislator vote pages.

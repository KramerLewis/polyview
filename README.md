# polyview

**Follow Washington State's money: where it comes from, what the Legislature
allocated, what was actually spent, and who voted for it.**

polyview is an open, nonpartisan transparency and audit tool for voters and
legislators. It connects state **revenue**, **appropriations** (budget bills),
**allotments** (agency spending plans) and **actual spending**, and maps them to
**legislators, votes and legislative districts**, for past bienniums, the
current one, and proposed or hypothetical budgets.

> Status: **Phase 0 (discovery) complete.** Ingesters exist for budget bills,
> legislators and votes, vendor payments, and district boundaries. No website yet.
> See [`docs/PLAN.md`](docs/PLAN.md) and [`docs/sources.md`](docs/sources.md).

## What it will do

- **Income:** state revenue by tax and fund, and forecast vs. actual collections.
- **Allocated vs. spent:** appropriations by agency and fund compared with actual payments, including supplemental changes and "provided solely for" provisos.
- **Accountability:** how each legislator voted on each budget bill and amendment.
- **Your district:** capital projects and local distributions in your legislative district.
- **Looking ahead:** official forecasts, fiscal notes on pending bills and ballot measures, and a sandbox to try your own scenarios.

Every number links back to its official source.

## Repository layout

```
ingest/      Python fetchers and parsers, one per data source (raw files → data/raw, with provenance)
models/      SQL transformations (dbt + DuckDB), Phase 1
crosswalk/   Reviewed mapping tables between budget-bill accounts and accounting codes
web/         Static site (GitHub Pages), Phase 1
data/samples Small committed samples of each ingested dataset
docs/        Plan, data source inventory, methodology
tests/       Parser tests with real XML fixtures
```

## Quick start

```bash
python -m pip install -e '.[dev]'
python -m ingest                 # all ingesters; or e.g. `python -m ingest budget_bills`
python -m pytest
```

Raw downloads go to `data/raw/` (git-ignored). `data/raw/manifest.jsonl` records
the URL, fetch time and SHA-256 of every file.

## Licenses

- **Code:** [MIT](LICENSE)
- **Derived data and documentation** (cleaned datasets, crosswalks, methodology): [CC BY 4.0](LICENSE-DATA)
- **Source data** remains under the terms of the publishing agency. Sources are credited in [`docs/sources.md`](docs/sources.md).

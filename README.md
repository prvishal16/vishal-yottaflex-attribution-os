# YottaFlex Attribution OS

A deterministic marketing attribution, ROI, and data-quality analytics platform built for the YottaFlex AI Forward Deployed Engineer challenge.

The project generates a synthetic multi-channel marketing dataset, resolves anonymous sessions to contacts using evidence-backed identity links, applies first-touch / last-touch / linear attribution, reconciles revenue and spend, detects deliberate data-quality fixtures, scores detection against held-out labels, and exposes everything through a FastAPI service and React console.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)
![React](https://img.shields.io/badge/React-19-61DAFB)
![DuckDB](https://img.shields.io/badge/DuckDB-1.1%2B-FFF000)

## What It Demonstrates

- **Deterministic generation** from a seeded RNG with canonical CSV hashing and manifest-level reproducibility checks.
- **Identity resolution** that links sessions through authenticated or verified evidence only, then applies consent and lookback rules.
- **Three attribution models** over the same canonical conversion set, with reconciled totals and model-specific credit shifts.
- **Financial integrity** where missing cost is never treated as zero, ROI/ROAS require complete month-level cost coverage with compatible currency, and source revenue reconciles to attributed revenue.
- **Five deliberate anomaly classes** detected by deterministic rules and evaluated against ground truth stored outside the detection path.
- **Chronological evaluation** with fixed train / validation / test boundaries rather than random row splits.
- **Operator console** with executive overview, campaign ledger, journey explainability, data-quality evidence packets, and a run registry.

## Quick Start

Prerequisites: Python 3.11+, Node.js 20.19+ (or 22.12+), npm.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

Set-Location frontend
npm install
npm run build
Set-Location ..

python -m yottaflex.cli generate --profile small
python -m yottaflex.cli serve --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The API documentation is available at <http://127.0.0.1:8000/docs>.

For frontend development, run the API in one terminal and Vite in another:

```powershell
python -m yottaflex.cli serve --host 127.0.0.1 --port 8000
```

```powershell
Set-Location frontend
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` to `127.0.0.1:8000`.

Helper scripts are available in `scripts/`:

```powershell
.\scripts\bootstrap.ps1
.\scripts\generate.ps1 -Profile small
.\scripts\verify.ps1
.\scripts\serve.ps1
```

## Profiles

All timestamps are UTC. The default seed is `20261022`, the reporting currency is EUR, and the lookback window is 90 days.

| Profile | Campaigns | Contacts | Touchpoints | Opportunities | Duplicate | Post-conv. | Currency | Missing cost | Unsupported link |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `small` | 30 | 500 | 2,000 | 200 | 2 | 2 | 2 | 2 | 2 |
| `demo` | 100 | 8,000 | 40,000 | 2,000 | 5 | 5 | 3 | 3 | 4 |
| `full` | 500 | 50,000 | 200,000 | 10,000 | 10 | 10 | 5 | 5 | 8 |

The checked-in workflow has been exercised on all three profiles. With seed `20261022`:

| Profile | Conversions | Attributed revenue | Exceptions | Validation |
| --- | ---: | ---: | ---: | --- |
| `small` | 102 | EUR 195,012.06 | 10 | PASS_WITH_WARNINGS |
| `demo` | 1,039 | EUR 2,139,665.00 | 20 | PASS_WITH_WARNINGS |
| `full` | 5,347 | EUR 11,224,486.73 | 38 | PASS_WITH_WARNINGS |

Warnings are expected: the anomaly fixtures intentionally violate a small number of validation rules. There are zero validation failures, and detection precision, recall, F1, and severity accuracy are 100% on each profile.

Financial ratios use only campaigns with complete month-level cost coverage and compatible currency. They are never calculated by mixing covered revenue with all recorded spend.

| Profile | Recorded spend | Covered spend | Covered attributed revenue | Covered ROAS | Covered ROI |
| --- | ---: | ---: | ---: | ---: | ---: |
| `small` | EUR 208,229.94 | EUR 195,131.42 | EUR 107,589.65 | 0.55x | -44.86% |
| `demo` | EUR 780,133.19 | EUR 748,908.96 | EUR 1,220,096.80 | 1.63x | 62.92% |
| `full` | EUR 3,884,384.40 | EUR 3,787,007.67 | EUR 6,399,698.08 | 1.69x | 68.99% |

The current checked-in active dataset is the full audited run: 246 of 256 budgeted campaigns have complete coverage, with 5 missing and 5 partial. Revenue coverage is 85.33% and conversion coverage is 84.96%.

Canonical hashes for seed `20261022`:

| Profile | Combined hash |
| --- | --- |
| `small` | `576476e6f0fa31d4c88572778fb7d5ce5325544d57151a7d087861c897aadf92` |
| `demo` | `d30a8784818c737e0e55ef52548d03fb98a8728cb19bbb5b22285ddcc163200c` |
| `full` | `ea303890c297e11b791f25e5f60e0fef4a43c54045231f25d08cd84ee1e7c9c1` |

The audit trail is in [docs/PRODUCT_AUDIT.md](docs/PRODUCT_AUDIT.md), metric contracts are in [docs/METRIC_DEFINITIONS.md](docs/METRIC_DEFINITIONS.md), and final evidence is in [docs/FINAL_REVIEW.md](docs/FINAL_REVIEW.md).

## Commands

| Command | Purpose |
| --- | --- |
| `python -m yottaflex.cli generate --profile small` | Generate the dataset and run the complete pipeline. |
| `python -m yottaflex.cli generate --profile demo --seed 20261022` | Generate a larger dashboard-ready run. |
| `python -m yottaflex.cli generate --profile full --strict` | Abort if any validation check does not pass. |
| `python -m yottaflex.cli verify --profile small` | Generate twice and compare canonical table hashes. |
| `python -m yottaflex.cli validate --run-id small-20261022` | Re-run validation against an existing run. |
| `python -m yottaflex.cli info` | Show paths, profiles, environment overrides, and the active run. |
| `python -m yottaflex.cli runs` | List indexed runs and their manifest hashes. |
| `python -m yottaflex.cli serve --host 127.0.0.1 --port 8000` | Serve the API and the built frontend. |
| `python -m pytest -q` | Run the backend test suite. |
| `python -m ruff check backend` | Run Python lint checks. |
| `npm run typecheck` | Type-check the React application. |
| `npm run build` | Build the production frontend. |

## Architecture

```text
Seeded generator
  ├─ reference data, campaigns, audiences, creatives, channels
  ├─ contacts and anonymous sessions
  ├─ evidence-backed identity links
  ├─ journeys and touchpoints
  ├─ leads, opportunities, recognized orders, cost records
  └─ controlled anomaly fixtures
        │
        ▼
Canonical CSV tables ──► DuckDB analytical index ──► typed views
        │
        ├─ attribution: first touch / last touch / linear
        ├─ detection: five deterministic rules
        ├─ analytics: campaign, channel, financial, executive aggregates
        ├─ validation: 119 structural / temporal / financial / attribution checks
        ├─ evaluation: held-out ground truth scoring
        └─ manifest: table hashes, combined canonical hash, run registry
        │
        ▼
FastAPI read models ──► React operator console
```

Pipeline order is intentional:

1. Core data is generated and written as deterministic CSV.
2. DuckDB is rebuilt from those CSVs.
3. Attribution runs and persists per-touchpoint credit and per-conversion outcomes.
4. Detection runs before analytics because campaign issue counts come from persisted exceptions.
5. Financial and executive analytics reconcile source revenue, attributed revenue, and spend.
6. Validation and evaluation run against the persisted dataset.
7. Manifests record canonical hashes and copy the run into the active registry.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design details and invariants.

## Data Model

Core tables: `channels`, `audiences`, `campaigns`, `campaign_channels`, `campaign_audiences`, `creatives`, `contacts`, `sessions`, `identity_links`, `touchpoints`, `leads`, `opportunities`, `orders`, `cost_records`, `lifecycle_events`.

Derived tables: `attribution_results`, `attribution_conversions`, `campaign_performance`, `channel_performance`, `exceptions`, `validation_results`, `financial_reconciliation`.

DuckDB convenience views use presentation-friendly column names such as `v_campaigns`, `v_orders`, `v_touchpoints`, `v_campaign_performance`, `v_channel_performance`, and `v_attribution_results`.

The full field-level contract is in [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).

## Attribution Rules

A conversion is a deduplicated recognized order:

- Included order statuses: `PAID`, `PARTIALLY_REFUNDED`.
- Revenue is `amount - refunded_amount`.
- Duplicate source transactions are deduplicated by `source_system_ref`, keeping the earliest ingested canonical order.
- Cancelled and fully refunded orders remain source evidence but do not enter attribution.

A touchpoint can receive credit only when all of the following hold:

- It resolved to the converting contact through a supported identity evidence type: `AUTHENTICATED_LOGIN`, `EMAIL_CLICK_SSO`, `FORM_SUBMIT_MATCH`, or `CRM_IMPORT_MATCH`.
- The contact's consent at conversion is `GRANTED`.
- The touch occurred within the 90-day lookback window.
- The touch occurred at or before the conversion timestamp and belongs to a campaign.

First-touch, last-touch, and linear models allocate 100% of each conversion's revenue. Total attributed revenue is therefore equal across models by design; model differences appear in campaign, channel, and touchpoint credit shares.

## Financial Rules

- Costs are summed only from compatible EUR cost records; incompatible-currency records are quarantined.
- `COMPLETE` requires a compatible cost for every month in the campaign window, with zero incompatible-currency costs.
- A missing month or incompatible currency produces `PARTIAL`; no compatible cost produces `MISSING`.
- `PARTIAL`, `MISSING`, or `NO_COST_BASIS` sets `roi_pct`, `roas`, and `cost_per_conversion` to null.
- Unknown spend stays blank/null in exports and APIs; it is never rendered as EUR 0.
- `NO_COST_BASIS` means the campaign has no paid-cost basis and is not penalized as missing cost.
- Covered ROAS and covered ROI use attributed revenue and spend from the same `COMPLETE`-coverage campaign set.
- Financial reconciliation compares eligible conversion revenue, attributed revenue, unattributed revenue, recorded spend, and covered spend.

## Data-Quality Fixtures

| Issue type | Detection rule | Severity | Expected disposition |
| --- | --- | --- | --- |
| Duplicate revenue | `DQ-DUP-001` | HIGH | Void duplicate revenue in analytics. |
| Post-conversion touch | `DQ-PCT-001` | MEDIUM | Exclude from credit. |
| Currency mismatch | `FIN-CUR-001` | MEDIUM | Quarantine incompatible cost. |
| Missing campaign cost | `FIN-COST-001` | HIGH | Suppress ROI; never treat missing as zero. |
| Unsupported identity link | `ID-LNK-001` | HIGH | Do not use temporal proximity as identity evidence. |

Ground truth is written to `ground_truth/<run_id>/labels.csv` after the dataset is generated. Detection reads only persisted records. The evaluator is the sole consumer of labels.

## Reproducibility

- Business records are sorted by stable primary keys before writing.
- Canonical CSV hashes exclude only genuine wall-clock columns: `attribution_results.computed_at`, `attribution_conversions.computed_at`, and `exceptions.detected_at`.
- A combined canonical hash is stored in each manifest.
- `yottaflex verify` generates the same profile and seed twice in isolated temporary roots and compares both canonical hashes.
- Verification does not mutate `data/`, `ground_truth/`, `reports/`, the active run, or its manifest timestamp.

Manifests live in `data/manifests/`. The registry entry points at the current run through `active_run.json`.

## API

Key read endpoints:

| Endpoint | Description |
| --- | --- |
| `GET /api/health` | Service and active dataset status. |
| `GET /api/runs` | Run registry and active run. |
| `GET /api/runs/{run_id}` | Full manifest for a run. |
| `POST /api/runs/generate` | Generate a profile from the console. |
| `POST /api/runs/validate` | Re-run validation against a run. |
| `GET /api/summary` | Executive KPIs, monthly trend, model comparison, and trust status. |
| `GET /api/campaigns` | Paginated campaign performance with filters and sorting. |
| `GET /api/campaigns/export` | Filtered campaign CSV with the same model, search, sort, and order as the ledger. |
| `GET /api/campaigns/{campaign_id}` | Campaign detail, model comparison, cost ledger, and monthly credit. |
| `GET /api/channels` | Channel options and performance. |
| `GET /api/attribution/compare` | Channel and campaign credit-share changes between two models. |
| `GET /api/demo/journey` | Representative converted journey with exclusions. |
| `GET /api/journeys/{reference}` | Order, opportunity, or contact journey replay. |
| `GET /api/exceptions` | Filterable exception queue. |
| `GET /api/exceptions/{issue_id}` | Evidence packet and suggested disposition. |
| `GET /api/validation/report` | Validation checks and summary. |
| `GET /api/evaluation` | Held-out detection evaluation. |
| `GET /api/exports/{dataset_name}` | CSV export for a canonical table. |

Every dataset-reading endpoint accepts an optional `run_id`. The full interactive contract is available in Swagger at `/docs`.

## Console

| Route | Purpose |
| --- | --- |
| `/` | Executive overview: revenue, covered ROI, conversions, exceptions, attribution trend, trust snapshot, channel shift, top campaigns, anomaly mix. |
| `/campaigns` | Filterable campaign ledger across models with cost coverage and ROI status. |
| `/campaigns/:campaignId` | Campaign detail with monthly credit, model comparison, budget, cost ledger, and linked exceptions. |
| `/journeys` | Search or load a sample journey; inspect identity, consent, eligibility, exclusions, and credit. |
| `/data-quality` | Exception queue, evidence packet, validation tabs, and detection evaluation. |
| `/runs` | Generate datasets, inspect manifests, copy hashes, compare runs, and re-run validation. |

## Tests

```powershell
python -m pytest -q
python -m ruff check backend scripts
Set-Location frontend
npm run typecheck
npm run build
```

The suite covers ID formats, split boundaries, attribution eligibility and allocation, financial suppression rules, identity evidence, end-to-end manifests, reproducibility, exports, and API contracts. Tests create isolated temporary runs and do not mutate the active dataset.

## Project Layout

```text
backend/yottaflex/
  api/                 FastAPI app, dependencies, read models
  domain/              attribution, financial, identity rules
  generation/          deterministic data generators
  validation/          validation contract
  analytics.py         campaign/channel/financial/executive aggregates
  attribution_pipeline.py
  detection.py
  evaluation.py
  generator.py
  manifest.py
  storage.py
  tables.py
  cli.py
backend/tests/         pytest suite
frontend/src/          React console
docs/                  architecture, data dictionary, audit and metric contracts
scripts/               bootstrap, verify, serve helpers
data/                  generated CSV, DuckDB, manifests
ground_truth/          held-out anomaly labels
reports/               evaluation reports
```

## Design Decisions and Limits

- **Synthetic only.** No real customer or personal data is included.
- **No FX conversion.** Non-EUR costs are quarantined as mismatches rather than silently converted.
- **No ML attribution.** The platform focuses on transparent, auditable rule-based models.
- **No authentication.** The console is a local operator tool, not a multi-tenant deployment.
- **Small-profile ROI can be negative.** The small dataset is optimized for fast validation and fixture coverage, not for a flattering aggregate return.
- **Full profile is compute-heavy.** The 200,000-touchpoint profile is intended for an assessment-scale run, not every test cycle.

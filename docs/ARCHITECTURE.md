# Architecture

## System Context

YottaFlex Attribution OS is a local analytical platform composed of four boundaries:

1. **Generation** creates a deterministic synthetic marketing dataset and controlled anomaly fixtures.
2. **Analytics** builds a canonical DuckDB index, attributes conversions, detects anomalies, reconciles financials, and evaluates detection.
3. **Serving** exposes read models and operational actions through FastAPI.
4. **Console** presents the dataset, quality evidence, and run reproducibility through a React SPA.

The platform is intentionally single-tenant and file-backed. Generated data, ground truth, reports, and manifests are local artifacts. The API is stateless apart from the active-run pointer and a process-level generation lock.

## Directory Map

```text
backend/yottaflex/
  api/
    deps.py              run resolution, query helpers, typed conversions
    services.py          read models for campaigns, journeys, quality, comparison
    main.py              FastAPI application, endpoints, SPA fallback
  domain/
    attribution.py       conversion and touch eligibility, credit allocation
    financials.py        cost coverage, ROI/ROAS, reconciliation
    identity.py          evidence-backed session resolution
  generation/
    context.py           seeded RNG and table accumulator
    master_data.py       channels, audiences, campaigns, creatives, contacts
    journey_generation.py sessions, identity links, touchpoints
    transaction_generation.py leads, opportunities, orders, costs, lifecycle
    anomaly_injection.py controlled fixtures and labels
  validation/
    engine.py            119 validation checks and summary contract
  analytics.py           campaign, channel, financial, summary aggregates
  attribution_pipeline.py
  detection.py
  evaluation.py
  generator.py
  manifest.py
  storage.py
  tables.py
  cli.py
```

## Generation Pipeline

`generate()` in `backend/yottaflex/generator.py` orchestrates the complete run:

1. Remove any previous directory for the same `run_id`.
2. Seed `random.Random(config.seed)` and generate reference/master data.
3. Generate sessions, evidence-backed identity links, and touchpoints.
4. Generate leads, opportunities, recognized orders, cost records, and lifecycle events.
5. Inject fixture anomalies and record held-out labels.
6. Write all core tables as deterministic CSV sorted by stable keys.
7. Write `run_config.json` and separate ground truth.
8. Build a DuckDB file from CSV and create typed views.
9. Persist attribution, detection, analytics, validation, and evaluation.
10. Hash canonical tables, write the manifest, and update the run registry.

The UI and API always read the persisted DuckDB index, never in-memory generator state.

## Determinism

Determinism relies on four mechanisms:

- **Seeded RNG.** Every random choice flows through the run's single `GenerationContext` RNG.
- **Deterministic ordering.** CSV rows are sorted by declared `sort_key` values before writing.
- **Canonical hashing.** Table hashes join non-timestamp columns with a unit separator, sort rows, and SHA-256 the result.
- **Nondeterministic exclusions.** Only execution timestamps are excluded: `computed_at` on attribution tables and `detected_at` on exceptions.

`combined_hash()` hashes the sorted table names and their canonical hashes. `yottaflex verify` generates the same profile and seed into isolated temporary directories, compares both combined hashes, and returns a non-zero exit code on any difference.

The manifest includes:

- generator and rule versions;
- profile specification, seed, date range, and split boundaries;
- table hashes, output file hashes, and combined canonical hash;
- table counts;
- detection and validation totals;
- financial metrics;
- evaluation summary;
- output paths.

## Identity Resolution

Identity is deliberately evidence-based:

- Sessions carry an anonymous ID, not a contact ID.
- `identity_links` is the only bridge from session to contact.
- A link is usable only when the evidence type is in `ALLOWED_IDENTITY_EVIDENCE`, the evidence reference is non-empty, and the link is `VERIFIED`.
- Temporal proximity, empty evidence, and unsupported types are excluded.
- A session with conflicting verified links is treated as unresolved rather than guessed.
- Contact consent is checked at conversion time, not at touch time.

The journey read model rebuilds resolution from persisted links and classifies each touch against the conversion. It also records a reconciliation check comparing recomputed attribution to persisted attribution rows.

## Attribution

### Canonical conversions

`backend/yottaflex/attribution_pipeline.py` selects recognized orders, deduplicates by source reference, and emits one conversion per canonical order. Each conversion is processed independently for all three models.

### Eligibility

`domain/attribution.py` classifies every candidate touch:

| Outcome | Meaning |
| --- | --- |
| `ELIGIBLE` | Within lookback, before conversion, consent granted, supported identity, and campaign present. |
| `POST_CONVERSION` | Occurred after the conversion timestamp. |
| `OUTSIDE_WINDOW` | Occurred before the 90-day lookback. |
| `IDENTITY_UNRESOLVED` | No supported identity resolution to the converting contact. |
| `CONSENT` | Contact consent was not `GRANTED`. |
| `NO_CAMPAIGN` | Touch has no campaign attribution context. |

### Allocation

| Model | Allocation |
| --- | --- |
| `first_touch` | 100% to the earliest eligible touch. |
| `last_touch` | 100% to the latest eligible touch. |
| `linear` | Equal fractions across all eligible touches. |

Amounts are rounded to two decimals per result row. Each conversion's allocation is reconciled against its revenue before persistence. Models intentionally share the same total attributed revenue, so model comparison focuses on credit distribution.

## Financial Logic

`domain/financials.py` determines cost coverage per campaign:

- Compatible costs are records in the campaign's budget currency (EUR for the checked-in profiles).
- `COMPLETE`: every month in the campaign's start-to-end window has a compatible cost, and no incompatible-currency cost is attached; ROI is reportable.
- `PARTIAL`: at least one scheduled month lacks a compatible cost, or an incompatible-currency cost is attached; ROI is suppressed.
- `MISSING`: a budget exists but no compatible cost exists; spend is unknown and ROI is suppressed.
- `NO_COST_BASIS`: no budget exists; this is not a financial anomaly.

A single cost record does not satisfy a multi-month campaign. Unknown spend remains blank in persisted performance rows and null in API payloads. ROI, ROAS, cost per conversion, and budget utilization are null when coverage is not complete or spend is zero.

Covered portfolio ROI/ROAS use attributed revenue and spend from the same `COMPLETE`-coverage campaign set. Recorded spend is never divided into covered revenue. The reconciliation row enforces:

```text
eligible conversion revenue = attributed revenue + unattributed revenue
```

Covered ROI reports only campaigns with complete cost coverage; this is why the headline "covered ROI" can differ from the recorded-spend ratio.

## Detection and Evaluation

Detection runs after attribution because post-conversion touches are identified by conversion timestamps. It writes five rule families:

| Rule | Detection logic |
| --- | --- |
| `DQ-DUP-001` | Duplicate `source_system_ref` groups in recognized orders. |
| `DQ-PCT-001` | Touchpoints later than their contact's recognized conversion. |
| `FIN-CUR-001` | Non-EUR cost records attached to campaigns. |
| `FIN-COST-001` | Budgeted campaigns without compatible cost coverage. |
| `ID-LNK-001` | Identity links without supported evidence or verification. |

Each exception stores an evidence JSON packet, affected records, severity, split, and suggested disposition.

Ground truth lives under `ground_truth/<run_id>/` and is never read by detection. `evaluation.py` matches detected exceptions to labels by issue type and affected record set, then calculates precision, recall, F1, and severity accuracy. On the checked-in profiles, detection matches all deliberately injected fixtures.

## Validation

`validation/engine.py` emits 119 checks across categories such as:

- structural and referential integrity;
- required columns and primary-key uniqueness;
- timestamp ordering and split boundaries;
- conversion and attribution reconciliation;
- financial coverage and currency consistency;
- identity evidence;
- manifest and table presence.

Each row has `PASS`, `WARNING`, or `FAIL`. Intentional fixtures produce warnings. `--strict` treats warnings as a failing run for CI-style use.

## Serving Layer

FastAPI is mounted at `/api`. Every dataset endpoint resolves a run ID, opens the DuckDB file read-only for the request, and closes it afterward. Read models shape API payloads without mutating stored tables.

Data export endpoints:

- `GET /api/exports/{dataset_name}` exports a canonical table.
- `GET /api/campaigns/export` applies the campaign ledger's model, search, coverage, channel, revenue, sort, and order parameters before writing CSV.
- Unknown spend is written as a blank field, not a numeric zero.

Operational endpoints:

- `POST /api/runs/generate` uses a process-wide non-blocking lock and returns `409` while another generation is active.
- `POST /api/runs/validate` re-runs validation, refreshes persisted results, and updates manifest hashes.
- `yottaflex verify` performs both reproducibility generations in isolated temporary roots.

The SPA fallback serves `frontend/dist`, including deep links and hashed assets. `/docs` exposes OpenAPI documentation.

## Frontend

The React console uses a run context backed by `localStorage`:

- The top bar selects any indexed run.
- Every page request passes the selected `run_id`.
- Selecting a run does not mutate the active dataset.
- Generating a new run updates the registry and selects it.

The UI uses Recharts for trend and comparison charts, React Router for deep links, and a custom CSS design system. It is responsive down to a 390px mobile viewport.

## Extension Points

- Add a new attribution model by extending `MODELS`, allocation logic, and typed views.
- Add a new detector by writing a rule in `detection.py`, adding a fixture in `anomaly_injection.py`, and extending evaluation matching.
- Add a new API read model in `services.py` and expose it in `main.py`.
- Add a new console view in `frontend/src/pages` and route it in `App.tsx`.

All extensions must preserve canonical table definitions, determinism, and the ground-truth separation boundary.

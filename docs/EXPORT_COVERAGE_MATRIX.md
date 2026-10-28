# Export Coverage Matrix

**Audit date:** 2026-10-28
**Scope:** every download/export control in the React console and every export
endpoint in the FastAPI service.
**Rule:** a control is only "verified" when the downloaded file itself has been
parsed and reconciled against the API response for the same scope.

## Inventory method

Searched `frontend/src` and `backend/yottaflex` for `Download`, `Export`,
`exportUrl`, `createObjectURL`, `Blob`, `Content-Disposition`, `attachment`,
`csv`, `json`, `xlsx`, `pdf`, `sql`, `zip`, `FileResponse` and
`StreamingResponse`. Every match was opened and classified. Download icons in
`lucide-react` import lists were traced to their render sites so a renamed
button could not hide.

## Page-by-page inventory

### Overview (`frontend/src/pages/OverviewPage.tsx`)

| Item | Detail |
| --- | --- |
| Control (pre-audit) | `Campaign CSV` anchor in the page header |
| Data represented | Raw `campaign_performance.csv` artifact from the run directory |
| Current behavior | `GET /api/exports/campaign_performance` returns the raw generated CSV (all three models, no filters, no metadata) |
| Formats | CSV only |
| Scope controls | None; the button ignored the visible model/date context and read like a whole-overview export |
| Works | Yes, file parses |
| Missing functionality | No KPI, monthly, channel, model-comparison or coverage data; no run/seed/model/timestamp context; label misrepresented the report |
| Fix implemented | Replaced with a multi-format **Executive overview** export generated from the same `summary()` read model used by the page: KPIs, monthly revenue/spend, channel contribution, model comparison, top campaigns, anomaly mix, validation/evaluation summary |
| Verification | See "Verification log" |

### Campaigns (`frontend/src/pages/CampaignsPage.tsx`)

| Item | Detail |
| --- | --- |
| Control | `Export` dropdown (`CampaignExportMenu`) |
| Data represented | Filtered campaign ledger at the selected attribution model |
| Formats | CSV, JSON, XLSX, PDF |
| Scope controls | Model, sort, order, channel, search, coverage |
| Works | Yes |
| Missing functionality | None found in this audit |
| Verification | CSV row set equals the unfiltered-by-page API result; JSON context carries model/filters/run; XLSX opens; PDF opens; empty filters handled |

### Campaign Detail (`frontend/src/pages/CampaignDetailPage.tsx`)

| Item | Detail |
| --- | --- |
| Control (pre-audit) | `All cost records CSV` anchor inside the Cost ledger panel |
| Data represented | Every cost record in the run, not the campaign on screen |
| Current behavior | `GET /api/exports/cost_records` raw artifact |
| Formats | CSV only |
| Scope controls | None; the panel heading implied campaign scope while the file contained the whole run |
| Works | Yes, but wrong scope for its placement |
| Fix implemented | (1) page-header **Campaign report** export (CSV/JSON/XLSX/PDF) containing campaign metadata, selected-model performance, monthly credit, model comparison, channel mix, cost records and linked issues; (2) the cost-ledger control is now campaign-scoped, correctly labelled `Campaign cost records CSV` |
| Verification | See "Verification log" |

### Journey Explorer (`frontend/src/pages/JourneyPage.tsx`)

| Item | Detail |
| --- | --- |
| Control (pre-audit) | None |
| Data represented | Journey touchpoints, eligibility/exclusion reasons, per-model credit, conversion/order, identity evidence |
| Missing functionality | No way to take the explained journey out of the browser |
| Fix implemented | **Journey** export (CSV/JSON/XLSX/PDF) for the currently inspected reference: touchpoint timeline, eligibility/exclusion reason, per-model credit allocations, conversion summary, exclusion counts, identity/consent evidence. No contact names or emails exist in the source data, so no personal identifiers are exported |
| Verification | Row counts equal `journey.touchpoints`; allocations equal `journey.touchpoints[*].credits`; timestamps preserved |

### Data Quality — exception queue (`frontend/src/pages/DataQualityPage.tsx`)

| Item | Detail |
| --- | --- |
| Control (pre-audit) | `Exception CSV` anchor in the page header |
| Data represented | Raw `exceptions.csv` artifact |
| Current behavior | `GET /api/exports/exceptions` raw artifact; ignored severity/issue-type/split/search filters |
| Formats | CSV only |
| Works | Yes, but wrong scope |
| Fix implemented | **Exception queue** export (CSV/JSON/XLSX/PDF) that applies the active severity, issue type, split and search filters, exports the complete matching set (not the visible 100), and separates detection output from ground truth |
| Verification | See "Verification log" |

### Data Quality — validation contract

| Item | Detail |
| --- | --- |
| Control (pre-audit) | None |
| Data represented | 119 validation checks, category summary, expected warnings |
| Fix implemented | **Validation report** export (CSV/JSON/XLSX/PDF) respecting status/category/search filters, with totals and category summary |
| Verification | Check count equals `/api/validation/report`; status filter applied in file |

### Data Quality — detection evaluation

| Item | Detail |
| --- | --- |
| Control (pre-audit) | None |
| Data represented | Detection metrics, per-issue-type and per-split results, matched fixtures |
| Sensitivity | Contains synthetic ground-truth labels |
| Fix implemented | **Evaluation artifact** export (CSV/JSON/XLSX/PDF) explicitly marked `artifact_type: evaluation_artifact`, `contains_ground_truth: true` in context, filename and PDF header; excluded from every ordinary dataset/run export |
| Verification | Totals equal `/api/evaluation`; matches count equal the API |

### Evidence packet (`DataQualityPage` detail panel)

| Item | Detail |
| --- | --- |
| Control (pre-audit) | `Copy JSON` only |
| Data represented | One exception packet: rule, severity, evidence, related records, suggested disposition |
| Fix implemented | **Evidence packet** export (JSON/CSV/XLSX/PDF) with packet fields, flattened evidence, related records, canonicalization details and an explicit `suggested disposition / applied: false` block |
| Verification | JSON packet equals `/api/exceptions/{id}`; suggested vs applied distinction present in every format |

### Runs & Reproducibility (`frontend/src/pages/RunsPage.tsx`)

| Item | Detail |
| --- | --- |
| Control (pre-audit) | `JSON` button in the manifest panel (client-side Blob) |
| Data represented | The selected run manifest |
| Current behavior | Serializes the loaded manifest only; no counts workbook, validation checks, run summary or SQL package |
| Formats | JSON only |
| Works | Yes |
| Missing functionality | No CSV/XLSX/PDF, no SQL seed/export, no artifact ZIP |
| Fix implemented | **Run export** menu: JSON manifest, CSV counts + validation summary, XLSX run report, PDF run/reproducibility summary, SQL package (schema + load script + data CSVs, ZIP) and artifacts ZIP (manifest, config, counts, validation, evaluation summary, README). SQL export is generated with DuckDB's own `EXPORT DATABASE`, not fabricated |
| Verification | ZIP opens; SQL package contains `schema.sql`, `load.sql` and CSVs; JSON equals `/api/runs/{run_id}`; counts equal the manifest |

## Backend endpoints

| Endpoint | Formats | Scoped by | Notes |
| --- | --- | --- | --- |
| `GET /api/campaigns/export` | CSV | model, sort, order, channel, search, coverage | Legacy single-format endpoint retained for API compatibility; no console control uses it |
| `GET /api/exports/campaign-performance` | CSV, JSON, XLSX, PDF | model, sort, order, channel, search, coverage | Complete filtered set + context |
| `GET /api/exports/overview` | CSV, JSON, XLSX, PDF | run | Executive report |
| `GET /api/exports/campaign/{campaign_id}` | CSV, JSON, XLSX, PDF | run, model | Campaign report |
| `GET /api/exports/cost-records` | CSV, JSON, XLSX | run, campaign | Campaign-scoped cost ledger |
| `GET /api/exports/exceptions` | CSV, JSON, XLSX, PDF | run, severity, issue type, split, status, search | Complete filtered set |
| `GET /api/exports/validation` | CSV, JSON, XLSX, PDF | run, status, category, search | Validation contract |
| `GET /api/exports/evaluation` | CSV, JSON, XLSX, PDF | run | Explicit evaluation artifact |
| `GET /api/exports/evidence/{issue_id}` | JSON, CSV, XLSX, PDF | run, issue | Evidence packet |
| `GET /api/exports/journey/{reference}` | CSV, JSON, XLSX, PDF | run, reference | Journey explainability |
| `GET /api/exports/run/{run_id}` | JSON, CSV, XLSX, PDF, SQL, ZIP | run | Run manifest / report / SQL package / artifact bundle |
| `GET /api/exports/formats` | — | — | Capability discovery |
| `GET /api/exports/{dataset_name}` | CSV | run | Raw generated artifact by table name; advanced/API-only |

## Scope and sensitivity rules

1. Ordinary exports never contain ground-truth labels. The evaluation export is
   the only artifact that does, and it announces that fact in the context block,
   filename, PDF header and XLSX Summary sheet.
2. Every export carries `run_id`, profile, seed, model (where relevant), active
   filters, row count, currency and generation time.
3. Suggested dispositions are exported as advisory text with `applied: false`.
   No export mutates source records.
4. Empty result sets produce a header-only CSV, empty `rows` in JSON, a
   header-only worksheet with `row_count: 0` in the summary, and an explicit
   "No records match" line in PDF.

## Verification log

Filled after the implementation pass. Each row must name the parser used and the
reconciliation performed; a visible menu item is not verification.

# ChatGPT Prompt History

## Scope and evidence status

ChatGPT was used in the user-confirmed workflow to analyse requirements,
structure implementation work, generate coding prompts for Claude and OpenCode,
and prepare review and QA checklists. ChatGPT did not directly edit files in
this repository.

No ChatGPT conversation export is stored in the repository. Entries below are
**reconstructed summaries** unless a short actual excerpt is explicitly
quoted. Large confidential assessment instructions are deliberately excluded;
only brief, project-specific task wording is reproduced. These summaries are
not presented as verbatim historical conversations.

## A. Challenge analysis and planning

### G-01 - Decomposing the assessment into workstreams

- **Prompt record:** Reconstructed summary. The task was to turn the assessment
  requirements into an implementation sequence covering data generation,
  identity resolution, attribution, financial semantics, anomaly detection,
  evaluation, validation, API, UI, exports, and documentation.
- **Contribution:** Work breakdown, dependency ordering, acceptance criteria,
  and identification of cross-cutting constraints such as deterministic seeds,
  ground-truth isolation, and no fabricated metrics.
- **Resulting work:** The repository separates generation, domain logic,
  validation, evaluation, API, and frontend layers, with tests and run
  manifests around them.
- **Verification:** The structure is visible in `backend/yottaflex/`,
  `frontend/src/`, `backend/tests/`, and `docs/`; behavior was exercised by the
  test suite and browser checks.

### G-02 - Architecture and data-flow planning

- **Prompt record:** Reconstructed summary. The task was to define how a
  generated run flows from source CSVs through DuckDB views, attribution
  results, API responses, and exports.
- **Contribution:** Suggested separation between raw/source tables, derived
  views, domain calculations, and presentation/export builders; identified
  points where ground truth must not enter detection or model inputs; and
  outlined page/component responsibilities for the operator console.
- **Resulting work:** `backend/yottaflex/tables.py`,
  `backend/yottaflex/domain/`, `backend/yottaflex/evaluation.py`, and the API
  report layer follow that separation.
- **Verification:** Code inspection and tests confirm evaluation is isolated
  from detection inputs and exports do not include ground-truth paths or
  labels.

## B. Coding prompt generation

### G-03 - Master implementation prompt

- **Prompt record:** Reconstructed summary. No ChatGPT transcript is stored in
  the repository. The long user-supplied corrected master prompt is
  deliberately not reproduced because it contains assessment-specific
  instructions. The accompanying instruction in the recorded session was:
  “Use this corrected master prompt.” The contribution below is therefore a
  task-level summary, not a verbatim ChatGPT prompt.
- **Contribution:** Converted the requirement set into implementation
  expectations: deterministic generation, three attribution models, financial
  coverage rules, anomaly fixtures, held-out evaluation, validation, API, React
  console, exports, and submission documentation.
- **Resulting work:** The corrected brief supplied to OpenCode was used as the
  build brief for the repository; implementation and verification were carried
  out in the OpenCode session.
- **Verification:** Requirement coverage is reflected in the implemented
  generation, domain, validation, evaluation, API, and UI layers. Supporting
  evidence is in tests, manifests, API responses, and the final review
  material; the latest checks recorded for this folder are listed in
  [AI_USAGE_LOG.md](AI_USAGE_LOG.md).

### G-04 - Scoped coding prompts for Claude

- **Prompt record:** Reconstructed summary. The task was to prepare focused
  instructions for selected React components, reusable UI patterns, API client
  work, and backend coding.
- **Contribution:** Clarified expected inputs, outputs, props, constraints,
  error handling, and verification steps so generated code could be integrated
  into the existing application instead of replacing it.
- **Resulting work:** Component-level work documented in
  [CLAUDE_PROMPTS.md](CLAUDE_PROMPTS.md), including the export menu, shared
  primitives, campaign views, API client, and export report handling.
- **Verification:** Integration was checked with TypeScript, build, tests, and
  browser QA as recorded in the usage log.

### G-05 - Scoped coding prompts for OpenCode

- **Prompt record:** Reconstructed summary. The task was to prepare
  repository-level instructions for inspection, implementation, debugging,
  testing, and evidence capture.
- **Contribution:** Defined the sequence: inspect first, preserve existing
  behavior, implement in the repository, run checks, then report exact results
  and unresolved items.
- **Resulting work:** The workflow documented in
  [OPENCODE_PROMPTS.md](OPENCODE_PROMPTS.md).
- **Verification:** Commands, test counts, build results, and browser findings
  are recorded in the final verification material.

## C. UI and UX prompt development

### G-06 - Console navigation and discoverability review

- **Prompt record:** Reconstructed summary. The task was to review screenshots
  and interaction issues, then specify improvements to navigation, dropdowns,
  filters, badges, labels, and page-level export placement.
- **Contribution:** Suggested consistent placement of export controls,
  clearer active-state indicators, explicit filter labels, and a shared visual
  language for warning and coverage badges.
- **Resulting work:** Export menus, model selectors, filters, and badges across
  the console use shared components and styling.
- **Verification:** Browser QA exercised navigation, menus, filters, model
  selection, evidence packets, dataset switching, error states, and mobile
  layout.

### G-07 - Responsive and accessibility review prompt

- **Prompt record:** Reconstructed summary. The task was to identify small
  screen overflow, keyboard gaps, and unclear labels.
- **Contribution:** A review checklist covering 390px and 1440px widths,
  keyboard opening/closing of menus, focus visibility, labelled inputs, and
  non-color status cues.
- **Resulting work:** Mobile export layout fix in `frontend/src/styles/global.css`
  and accessible control markup in the console.
- **Verification:** At 390px the export menu remained inside the viewport;
  keyboard ArrowDown/Escape behavior and labelled inputs were checked in the
  browser. No console errors were recorded.

### G-08 - Interface copy and state review

- **Prompt record:** Reconstructed summary. The task was to make unavailable
  metrics, ground-truth warnings, empty results, and failed requests
  understandable without overstating certainty.
- **Contribution:** Suggested wording such as explicit unavailable-reason
  labels, a visible ground-truth boundary notice, and error copy that names the
  failed view.
- **Resulting work:** Page banners, unavailable metric rendering, and error
  states in `frontend/src/pages/` and shared primitives.
- **Verification:** Browser QA observed the evaluation warning, invalid
  campaign error, and unavailable/empty states.

## D. API and backend planning

### G-09 - Export contract planning

- **Prompt record:** Reconstructed summary. The task was to define a consistent
  export contract for reports and run artifacts.
- **Contribution:** Suggested that each export declare its report scope,
  supported formats, filename, MIME type, and behavior on empty data; that
  ground truth be excluded; and that unsupported formats return an explicit
  error.
- **Resulting work:** Shared export helpers in
  `backend/yottaflex/api/exports.py`, report builders in `reports.py`, and
  route handling in `main.py`.
- **Verification:** Tests and live endpoint verification parsed CSV, JSON,
  XLSX, and PDF outputs; run bundles and SQL packages were inspected for
  expected entries and path leakage.

### G-10 - API error and integration planning

- **Prompt record:** Reconstructed summary. The task was to specify how the
  frontend should request filtered data and exports, and how failures should
  surface.
- **Contribution:** Request/response expectations, query-parameter handling,
  validation and error propagation, and the rule that the UI must not show a
  success state when a request fails.
- **Resulting work:** Typed frontend request helpers and API error handling.
- **Verification:** Invalid campaign requests display an error with retry;
  failed journeys no longer produce an unhandled server error; browser QA
  reported no console errors.

## E. Export coverage and quality assurance

### G-11 - Global export audit instruction

- **Prompt record:** Actual instruction theme supplied during the audit. A short
  excerpt is:
  “Every existing download/export button across the entire application must be
  audited and made genuinely useful.”
- **Contribution:** Defined the audit scope across Overview, Campaigns,
  Campaign Detail, Journey Explorer, Data Quality, Evidence Packets, Runs and
  Reproducibility, and any additional discovered export surface; required
  content inspection, appropriate CSV/JSON/XLSX/PDF and run SQL/ZIP outputs,
  active filter and dataset scope, and visible error handling.
- **Resulting work:** The export coverage matrix, shared export framework,
  non-converted journey handling, cost-record PDF support, run bundle, and SQL
  package.
- **Verification:** A live endpoint verifier parsed every report/format pair;
  browser QA checked every menu; a real campaign CSV download was parsed. The
  final verifier reported no failures.

## F. Testing and final review

### G-12 - Final quality review instruction

- **Prompt record:** Reconstructed summary. The task was to prepare a
  reviewer-oriented checklist covering functionality, attribution correctness,
  data validation, evidence integrity, exports, UX, end-to-end and regression
  testing, reproducibility, and documentation gaps.
- **Contribution:** Review categories and the requirement that every claim be
  backed by code, a test, a parsed artifact, or an observed browser result.
- **Resulting work:** Final review checklists and repository evidence notes,
  with unresolved limitations stated explicitly.
- **Verification:** Repository tests, lint, typecheck, build, API export
  checks, and browser QA were run; remaining documentation and provenance gaps
  are reported rather than hidden.

## Limits of this record

- ChatGPT's exact conversation history and model version are not stored in the
  repository and are not invented.
- ChatGPT is not credited with direct repository edits. Implementation was
  performed and verified in the repository workflow.
- The prompts above are task summaries, not a claim that every message was
  preserved verbatim.

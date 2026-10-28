# OpenCode Prompt History

## Scope and evidence status

OpenCode was the repository-level implementation agent used in recorded
sessions. Its work included inspecting the project, editing files, running the
application and checks, debugging API failures, building exports, and
performing browser QA. This document records the actual task prompts that are
short enough to reproduce and clearly labels task summaries where the full
conversation is not reproduced.

Long confidential assessment instructions are not copied here. The prompts
below are short excerpts or task-level summaries, not the complete assessment
brief.

## A. Repository inspection

### OC-01 - Initial build and baseline inspection

- **Prompt record:** Actual prompt title from the initial session:
  “MASTER BUILD PROMPT — YottaFlex AI Associate | AI Forward Deployed Engineer
  Challenge”. The full prompt is long and assessment-specific, so only the
  title is reproduced here.
- **Task:** Inspect the existing project, understand the stack and conventions,
  and implement the requested application end to end.
- **Actual work:** Inspected `backend/`, `frontend/`, `scripts/`, `docs/`, and
  `pyproject.toml`; established the FastAPI + DuckDB + React structure; used
  existing conventions rather than replacing the project layout.
- **Verification:** Repository structure, application startup, tests, and the
  built frontend were checked during the session.

### OC-02 - Continuation and scope recovery

- **Prompt record:** Actual prompt from the recorded session:
  “continueee from where u left...” (spelling preserved).
- **Task:** Reconstruct current state, completed work, active problems, and
  remaining steps from repository and session evidence.
- **Actual work:** Reviewed changed files, test state, running services, active
  run manifest, and outstanding audit requirements.
- **Verification:** Reported state was cross-checked against the repository,
  process list, health endpoint, and test output.

## B. Running frontend and backend together

### OC-03 - Service startup and availability

- **Prompt record:** Reconstructed summary. The task was to start the
  application and confirm it was usable for verification.
- **Actual work:** Started the FastAPI service on `127.0.0.1:8000` and served
  the built React application from `frontend/dist`. Confirmed the health
  endpoint reported the intended active run. The Vite development proxy exists
  for local frontend work, but the final browser checks used the built
  application served by FastAPI.
- **Verification:** Health response identified run `full-20261022`; browser QA
  loaded the console from the running service. Startup errors were checked
  rather than assumed absent.

### OC-04 - Dataset and active-run state

- **Prompt record:** Reconstructed summary. The task was to verify the active
  dataset and keep the intended full run active during final checks.
- **Actual work:** Inspected `data/manifests/active_run.json`, detected when a
  test-generated run replaced the active full run, restored the full manifest,
  and re-checked health.
- **Verification:** Health reported `full-20261022` with the full profile after
  restoration.

## C. Debugging and integration

### OC-05 - Journey export server error

- **Prompt record:** Reconstructed summary. The task was to investigate a
  failing journey export and fix it without hiding the failure.
- **Diagnosis:** An order with no recognized conversion produced an empty
  conversion frame and a server error in the report builder.
- **Actual work:** Updated `backend/yottaflex/api/reports.py` so a missing
  conversion produces `NO_RECOGNIZED_CONVERSION`, a clear Conversion-sheet
  message, empty model context, and no misleading model rows. Added
  `test_journey_export_handles_no_recognized_conversion` in
  `backend/tests/test_exports.py`.
- **Verification:** Regression test passes; live JSON, CSV, and PDF requests
  for a non-converted reference returned HTTP 200.

### OC-06 - Export format gap

- **Prompt record:** Reconstructed summary. The task was to verify every
  advertised report format and fix mismatches between the UI, route, and
  serializer.
- **Diagnosis:** Cost records advertised/expected PDF support but the route and
  format contract accepted only CSV, JSON, and XLSX, producing a validation
  error.
- **Actual work:** Added `pdf` to `COST_EXPORT_FORMATS` and the cost-record
  route pattern; added a PDF signature assertion to the export tests.
- **Verification:** Endpoint verification parsed the cost-record PDF; the
  export test suite passes.

### OC-07 - Mobile export-menu clipping

- **Prompt record:** Reconstructed summary. The task was to reproduce and fix
  an export menu that clipped at a 390px viewport.
- **Diagnosis:** The dropdown was positioned beyond the left viewport edge in
  the narrow layout.
- **Actual work:** Added responsive rules in `frontend/src/styles/global.css`
  to make the page-header export control full-width and center the trigger;
  rebuilt the frontend.
- **Verification:** The menu rectangle measured `left: 14px`, `right: 308.8px`
  at 390px, inside the viewport, with no console errors.

## D. End-to-end testing

### OC-08 - Global export verification

- **Prompt record:** Actual prompt title from the audit request:
  “YOTTAFLEX ATTRIBUTION OS — GLOBAL EXPORT COVERAGE + COMPLETE CHALLENGE
  COMPLIANCE + FINAL QA”. The full prompt is not reproduced. Two short actual
  excerpts are:
  “Work directly in my existing YottaFlex Attribution OS repository. Do not
  return only suggestions or a design plan.”
  “Every existing download/export button across the entire application must be
  audited and made genuinely useful.”
- **Task:** Audit and verify exports on Overview, Campaigns, Campaign Detail,
  Journey Explorer, Data Quality, Evidence Packets, and Runs, plus any other
  discovered export surface.
- **Actual work:** Implemented and verified CSV, JSON, XLSX, and PDF report
  exports; run JSON/CSV/XLSX/PDF artifact exports; SQL package ZIP; and the run
  artifact bundle. Parsed downloaded content, checked filenames and scope,
  confirmed empty/non-converted journeys, and ensured ground truth and local
  filesystem paths were not leaked.
- **Verification:** `verify_export_endpoints.py` parsed every report/format
  pair and reported no failures. Browser QA found the expected menu entries on
  every page. A real campaign CSV download
  (`campaign-CMP-2026-000001-linear.csv`) contained the expected four monthly
  rows. The SQL package contained the expected schema/load files and tables.

### OC-09 - Console interaction and responsive QA

- **Prompt record:** Reconstructed summary. The task was to verify navigation,
  campaign detail, attribution model selection, journey eligibility, evidence
  packets, data-quality filtering, dataset switching, validation, evaluation,
  error states, and responsive behavior.
- **Actual work:** Ran browser checks against the built application, including
  keyboard menu behavior, campaign search/filter/reset/sort, model switching,
  journey focus, severity filters, evidence packet actions, dataset switching,
  invalid campaign handling, and the 390px layout.
- **Verification:** `qa_part_c.py` reported no failures. Observed checks
  included campaign sort matching the sorted API order, dataset switching,
  invalid-campaign error with retry, ground-truth warning, and no console
  errors. Search reduced the API matching set from 500 to 100. Reproducibility
  is covered by `backend/tests/test_reproducibility.py` in the passing backend
  suite; the browser checks covered the run registry and dataset switching,
  not a separate CLI regeneration run.

### OC-10 - Test, lint, typecheck, and build

- **Prompt record:** Reconstructed summary. The task was to run the available
  checks after implementation rather than assume success.
- **Actual work and results:**
  - `python -m pytest -q backend/tests` - 98 passed.
  - `python -m ruff check backend` - clean.
  - `npm run typecheck` - passed.
  - `npm run build` - passed.
- **Verification:** These are the final recorded results in the session. They
  cover the current repository state after the export and responsive fixes.

## E. Regression and final verification

### OC-11 - Export regression coverage

- **Prompt record:** Reconstructed summary. The task was to lock in the
  non-converted journey behavior and the added PDF format.
- **Actual work:** Added the journey regression test, asserted the cost-record
  PDF signature, and reran the export test module and the full backend suite.
- **Verification:** Export tests passed; full backend suite passed with 98
  tests.

### OC-12 - Documentation and final review

- **Prompt record:** Actual short excerpt from the documentation request:
  “Create the complete AI prompt history and usage documentation for YottaFlex
  Attribution OS.”
- **Task:** Create a professional `prompts/` folder, record actual and
  reconstructed AI contributions, verify links and role consistency, and avoid
  fabricated prompts or results.
- **Actual work:** Created `prompts/README.md`, `AI_USAGE_LOG.md`,
  `CLAUDE_PROMPTS.md`, `CHATGPT_PROMPTS.md`, and this file; checked relative
  links; documented provenance limits and evidence sources.
- **Verification:** Folder contents and links were checked after creation. The
  repository is not a Git repository, so a Git diff was not available; the
  verification report states this explicitly.

## Limits of this record

- The complete OpenCode conversation is not reproduced; only short actual
  excerpts and task summaries are included.
- Large confidential assessment instructions are intentionally omitted.
- Commands and results listed here are those observed in the session. No
  additional test counts, timings, or model names are invented.
- OpenCode is not credited with independently designing the assessment or
  manually validating every requirement; it implemented and verified work in
  the repository under the user's direction.
- The checks recorded here are agent-executed checks. They are not presented as
  independent human manual QA. No unresolved code defects were recorded in the
  audited export and console scope, but requirements that were not exercised are
  left unclaimed.

# Claude Prompt History

## Scope and evidence status

Claude was part of the user-confirmed development workflow for selected
frontend components, reusable React patterns, interface copy, frontend API
request code, and selected backend coding where applicable. Claude was not the
sole author of the application and is not credited with every file.

No Claude session transcript is stored in this repository. The entries below
are **reconstructed summaries** of the work Claude assisted with. They describe
the task, the resulting files, how the output was integrated, and how the
result was verified. They are not presented as verbatim historical prompts.
Where a change can be verified in the repository, that is stated; where only
the user-confirmed workflow supports Claude's involvement, that is stated too.

## A. React component development

### C-01 - Reusable export menu and dropdown

- **Prompt record:** Reconstructed summary. The task was to add a reusable
  dropdown/menu component for report downloads that could be placed in page
  headers and reused across reports.
- **Relevant files:** `frontend/src/components/ExportMenu.tsx`,
  `frontend/src/components/Primitives.tsx`,
  `frontend/src/styles/global.css`.
- **Contribution:** Component composition, typed props for report-kind and
  format options, open/close state, outside-click handling, keyboard
  interaction, and consistent trigger styling.
- **Integration:** The menu was wired into Overview, Campaign Detail, Journey
  Explorer, Data Quality, Evaluation, Evidence, and Runs views through existing
  page-level export APIs.
- **Verification:** `npm run typecheck` and `npm run build` pass. Browser QA
  confirmed the expected menu entries on each page, keyboard ArrowDown/Escape
  behavior, and no console errors.

### C-02 - Reusable presentation primitives

- **Prompt record:** Reconstructed summary. The task was to consolidate badges,
  buttons, section headers, empty states, and table conventions so pages did
  not duplicate markup.
- **Relevant files:** `frontend/src/components/Primitives.tsx` and consuming
  pages under `frontend/src/pages/`.
- **Contribution:** Suggested prop shapes, TypeScript types, composition
  patterns, and event-handler placement for shared UI primitives.
- **Integration:** Existing pages were adapted to the shared primitives rather
  than introducing a parallel component library.
- **Verification:** TypeScript build passes; the components are rendered in the
  built application and exercised by browser QA.

### C-03 - Campaign ledger and detail composition

- **Prompt record:** Reconstructed summary. The task was to improve the
  campaign list/detail experience with sortable columns, badges, model
  selection, and linked campaign rows.
- **Relevant files:** `frontend/src/pages/CampaignsPage.tsx`,
  `frontend/src/pages/CampaignDetailPage.tsx`.
- **Contribution:** Component structure, typed campaign fields, sort-button
  behavior, model/first-touch/last-touch controls, and accessible row links.
- **Integration:** The pages use the existing API client and shared table
  styles; no duplicate data-fetching layer was added.
- **Verification:** Browser QA navigated from the ledger to
  `CMP-2026-000409`, switched attribution models, and confirmed the spend sort
  matched the sorted API response.

## B. UI and UX implementation

### C-04 - Responsive export controls

- **Prompt record:** Reconstructed summary. The task was to prevent export
  menus from overflowing or clipping on small screens.
- **Relevant files:** `frontend/src/styles/global.css`.
- **Contribution:** Suggested the mobile layout adjustment that makes the
  export control full-width, lets the dropdown flex, and centers the trigger.
- **Integration:** Applied in the existing 640px responsive block; desktop
  layout was left unchanged.
- **Verification:** At a true 390px viewport the menu rectangle measured
  left `14px`, right `308.8px`, within the viewport; desktop QA reported no
  regression.

### C-05 - Clear interface states and microcopy

- **Prompt record:** Reconstructed summary. The task was to make loading,
  empty, error, ground-truth, and unavailable-metric states explicit.
- **Relevant files:** Shared primitives, `DataQualityPage.tsx`,
  `CampaignDetailPage.tsx`, `JourneyPage.tsx`, and related styles.
- **Contribution:** Interface labels, helper text, warning/banner wording, and
  empty/error-state treatment.
- **Integration:** Copy and states were reviewed against actual API fields so
  the interface does not show a fabricated success state when a request fails.
- **Verification:** Browser QA observed the invalid-campaign error state, the
  detection ground-truth warning, and unavailable-metric rendering. Non-converted
  journey export handling was verified separately through API and export tests.
  No failed request was hidden as success.

## C. Frontend API request implementation

### C-06 - Typed API client and query parameters

- **Prompt record:** Reconstructed summary. The task was to centralize API
  request construction, query parameters, and response types used by the
  console.
- **Relevant files:** `frontend/src/api/client.ts` and consuming pages.
- **Contribution:** Typed request helpers, URL/query construction for report
  exports and filtered views, response parsing, and consistent error
  propagation.
- **Integration:** Pages call the shared client instead of embedding ad hoc
  fetch logic. Existing backend routes were reused.
- **Verification:** `npm run typecheck` passes; browser QA exercised campaign
  filtering, search, sorting, report exports, and error states through these
  request paths.

### C-07 - Export download handling

- **Prompt record:** Reconstructed summary. The task was to make exported
  files download with useful filenames and without false success messages.
- **Relevant files:** `frontend/src/components/ExportMenu.tsx`,
  `frontend/src/api/client.ts`.
- **Contribution:** Blob download handling, format labels, filename
  construction, and error feedback when a request fails.
- **Integration:** Used by the per-report export menus and run-bundle
  controls.
- **Verification:** Browser download produced
  `campaign-CMP-2026-000001-linear.csv`; parsed content contained the expected
  four monthly rows. Live endpoint verification parsed CSV, JSON, XLSX, and PDF
  outputs and reported no failures.

## D. Backend implementation

### C-08 - Report export assembly and formats

- **Prompt record:** Reconstructed summary. The task was to support a common
  set of report formats without duplicating serialization logic per report.
- **Relevant files:** `backend/yottaflex/api/exports.py`,
  `backend/yottaflex/api/reports.py`, `backend/yottaflex/api/main.py`.
- **Contribution:** Claude-assisted review and refinement of report/sheet
  structures, CSV/JSON/XLSX/PDF output handling, and route-level format
  validation where applicable.
- **Integration:** Final implementation was applied and verified in the
  repository during the OpenCode session. Business rules and existing report
  boundaries were preserved.
- **Verification:** `backend/tests/test_exports.py` passes; live endpoint
  verification parsed every supported report/format combination with no
  failures.

### C-09 - Graceful handling of non-converted journeys

- **Prompt record:** Reconstructed summary. The task was to stop a journey
  export from failing when an order has no recognized conversion.
- **Relevant files:** `backend/yottaflex/api/reports.py`,
  `backend/tests/test_exports.py`.
- **Contribution:** Claude-assisted review of the failure path and suggested
  explicit handling for a missing conversion instead of an exception.
- **Integration:** The report now returns `NO_RECOGNIZED_CONVERSION` with an
  explanatory workbook row and empty model context. The regression test was
  added during repository verification.
- **Verification:** Regression test passes; live JSON, CSV, and PDF requests
  for a non-converted reference returned HTTP 200.

### C-10 - Cost-report PDF support

- **Prompt record:** Reconstructed summary. The task was to close a format
  gap discovered during export verification.
- **Relevant files:** `backend/yottaflex/api/reports.py`,
  `backend/yottaflex/api/main.py`, `backend/tests/test_exports.py`.
- **Contribution:** Claude-assisted check of the supported-format contract and
  route validation.
- **Integration:** `pdf` was added to the cost-record format contract and the
  route pattern; the existing PDF exporter was reused.
- **Verification:** Export test asserts a `%PDF-` signature; live endpoint
  verification parsed the PDF successfully.

## E. Integration and refinement

### C-11 - Integration review

- **Prompt record:** Reconstructed summary. The task was to adapt generated
  suggestions to the actual repository rather than replacing existing
  architecture.
- **Relevant files:** Frontend pages/components and backend API modules listed
  above.
- **Contribution:** Suggested integration points, prop/type corrections, and
  consistency checks against existing conventions.
- **Integration:** Final changes were reviewed and applied in the repository;
  no parallel framework or duplicate service layer was introduced.
- **Verification:** Static checks, build, API tests, and browser QA were run
  after integration.

### C-12 - Test and edge-case review

- **Prompt record:** Reconstructed summary. The task was to review export and
  UI edge cases before final delivery.
- **Relevant files:** `backend/tests/test_exports.py`, export and page
  components.
- **Contribution:** Suggested regression scenarios around empty conversions,
  unsupported formats, failed requests, and mobile overflow.
- **Integration:** Relevant scenarios were turned into repository tests or
  browser checks during the OpenCode verification pass.
- **Verification:** The backend suite completed with 98 passing tests; export
  regression tests and browser QA covered the reviewed scenarios.

## Limits of this record

- Exact Claude prompts, model names, and session dates are not available in the
  repository and are not invented here.
- The repository verifies the resulting code and behavior, not the identity of
  the assistant that drafted each line.
- Claude is not credited with the complete application, the dataset generator,
  the attribution algorithm, or every test. Those areas were implemented and
  verified through the repository workflow documented elsewhere.

# AI Usage Log

This is a consolidated, reviewer-friendly record of AI assistance. It is not a
claim that every contribution below has an independent transcript. Exact prompt
history is documented in the linked tool files; entries marked **reconstructed**
describe the confirmed workflow without inventing verbatim wording.

| Tool | Role | Task category | Contribution | Source reference | Verification method | Verification status |
| --- | --- | --- | --- | --- | --- | --- |
| Claude | Selected frontend assistance | React components | Reusable export menu/dropdown, shared presentation primitives, campaign list/detail composition | [C-01 to C-03](CLAUDE_PROMPTS.md#a-react-component-development) | Typecheck, production build, browser QA | Implemented and verified in repo; prompt provenance reconstructed |
| Claude | Selected frontend assistance | UI/UX | Responsive export-control rules, labels, helper text, warning and error states | [C-04, C-05](CLAUDE_PROMPTS.md#b-ui-and-ux-implementation) | 390px and desktop browser checks, error/empty-state inspection | Implemented and verified; exact prompt unavailable |
| Claude | Selected frontend assistance | Frontend API requests | Typed API client helpers, query parameters, export downloads, error propagation | [C-06, C-07](CLAUDE_PROMPTS.md#c-frontend-api-request-implementation) | Typecheck, build, browser downloads, API-backed UI checks | Implemented and verified; prompt provenance reconstructed |
| Claude | Selected backend assistance | Backend coding | Review/refinement of report export assembly, non-converted journey handling, cost-record PDF support where applicable | [C-08 to C-10](CLAUDE_PROMPTS.md#d-backend-implementation) | Export tests, full backend suite, live endpoint parsing | Implemented and verified; line-level authorship not provable from repo |
| Claude | Integration review | Refinement and tests | Adaptation to existing architecture, edge-case review, regression scenarios | [C-11, C-12](CLAUDE_PROMPTS.md#e-integration-and-refinement) | Build, 98 passing backend tests, browser QA | Verified; reconstructed prompt record |
| ChatGPT | Requirement analysis | Analysis and planning | Decomposed requirements into workstreams, dependencies, acceptance criteria, and constraints | [G-01, G-02](CHATGPT_PROMPTS.md#a-challenge-analysis-and-planning) | Resulting repository structure, tests, docs | Used in workflow; no stored transcript |
| ChatGPT | Prompt generation | Coding prompts | Produced scoped implementation prompts for Claude/OpenCode, including inputs, outputs, constraints, verification | [G-03 to G-05](CHATGPT_PROMPTS.md#b-coding-prompt-generation) | Prompt files and implementation history; no direct file edits by ChatGPT | Prompt role confirmed; exact wording largely unavailable |
| ChatGPT | Prompt generation | UI/UX review | Navigation, badges, filters, export placement, responsive and state-review checklists | [G-06 to G-08](CHATGPT_PROMPTS.md#c-ui-and-ux-prompt-development) | Browser QA of navigation, filters, menus, error states, 390px layout | Design prompts reflected in UI; provenance reconstructed |
| ChatGPT | Prompt generation | API/backend planning | Export contract, request/response handling, error semantics, integration requirements | [G-09, G-10](CHATGPT_PROMPTS.md#d-api-and-backend-planning) | Export tests, live API checks, UI error-state checks | Reflected in implementation; no direct edits |
| ChatGPT | Quality assurance planning | Export audit | Defined application-wide export audit scope, format expectations, content verification, scope/error requirements | [G-11](CHATGPT_PROMPTS.md#e-export-coverage-and-quality-assurance) | Endpoint verifier, parsed files, browser menus, real CSV download | Audit executed and verified; no failures recorded |
| ChatGPT | Quality assurance planning | Final review | Prepared reviewer-oriented checklist and evidence standard | [G-12](CHATGPT_PROMPTS.md#f-testing-and-final-review) | Documentation, tests, QA notes | Checklist used; direct authorship not verifiable |
| OpenCode | Repository implementation | Inspection and setup | Inspected stack/conventions, preserved architecture, started service, verified health and active run | [OC-01 to OC-04](OPENCODE_PROMPTS.md#a-repository-inspection) | File inspection, health endpoint, running app | Verified in recorded session |
| OpenCode | Repository implementation | Debugging | Diagnosed and fixed non-converted journey export failure and cost-record PDF format gap | [OC-05, OC-06](OPENCODE_PROMPTS.md#c-debugging-and-integration) | Regression test, export tests, live HTTP responses | Verified |
| OpenCode | Repository implementation | Responsive fix | Fixed 390px export-menu clipping and rebuilt frontend | [OC-07](OPENCODE_PROMPTS.md#c-debugging-and-integration) | Browser geometry check, no console errors | Verified |
| OpenCode | Repository implementation | End-to-end testing | Audited report and run exports, parsed downloaded content, checked SQL/bundle contents and leakage | [OC-08](OPENCODE_PROMPTS.md#d-end-to-end-testing) | `verify_export_endpoints.py`: no failures; parsed CSV/JSON/XLSX/PDF/ZIP/JSON bundle | Verified in current session |
| OpenCode | Repository implementation | Browser QA | Exercised navigation, campaign search/filter/sort, models, journeys, evidence, validation, datasets, errors, mobile layout | [OC-09](OPENCODE_PROMPTS.md#d-end-to-end-testing) | `qa_part_c.py`: no failures; no console errors; screenshots retained locally | Verified in current session |
| OpenCode | Repository implementation | Regression checks | Ran backend tests, lint, typecheck, and production build | [OC-10, OC-11](OPENCODE_PROMPTS.md#d-end-to-end-testing) | 98 passed; Ruff clean; typecheck/build passed | Verified |
| OpenCode | Documentation | Final review | Created this prompt-history folder and checked links/provenance | [OC-12](OPENCODE_PROMPTS.md#e-regression-and-final-verification) | File listing, link/path checks, role consistency review | Verified after creation; no Git repo available for diff |

## Status definitions

- **Verified in repo / current session** - a source file, test result, API
  response, or recorded command supports the claim.
- **Implemented and verified; provenance reconstructed** - the feature is
  present and was checked, but no stored Claude/ChatGPT transcript proves which
  assistant drafted a specific line.
- **Reflected in implementation** - the planning or prompt theme is consistent
  with the resulting repository work; it is not a verbatim transcript claim.
- **No stored transcript** - the tool's exact conversation history is not
  available in the repository.

## Important limits

- ChatGPT did not directly modify repository files in the recorded workflow.
- Claude is documented at task/component level, not as author of the entire
  application.
- The repository can verify behavior and file contents. It cannot independently
  prove authorship where no transcript exists.
- No dates, model versions, percentages, commit hashes, or performance gains are
  invented in this log.

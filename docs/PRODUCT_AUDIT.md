# Product Audit

**Audit date:** 2026-10-27  
**Scope:** YottaFlex Attribution OS, Python/FastAPI backend, DuckDB analytics layer, React console, generated small/demo/full datasets, tests, scripts, and documentation.  
**Audited run:** `full-20261022` (seed `20261022`).  
**Outcome:** No unresolved P0 or P1 findings in the audited scope. The full-profile result is reproducible, the console has been browser-checked at desktop and 390px widths, and the regression suite passes.

## Audit Method

The audit followed the original priority order:

1. Reconnaissance and a running baseline before edits.
2. Financial-semantics and attribution review before visual polish.
3. Reproduce each suspected defect with a query, test, or browser observation.
4. Apply the smallest correct fix and add a regression check.
5. Regenerate evidence, verify determinism, and document the result.

The review deliberately separated three questions that are often conflated:

- **Is the data complete?** Coverage of identity, revenue, conversions, and spend.
- **Is the calculation valid?** Whether a ratio is defined for the available spend basis.
- **Is the UI explaining the calculation?** Scope labels, numerator/denominator, nullable states, and export parity.

No success state, warning, or ground-truth label was fabricated. Detection reads only persisted business records; evaluation is the sole consumer of labels.

## Findings and Resolutions

| ID | Severity | Finding | Resolution | Regression evidence |
| --- | --- | --- | --- | --- |
| A-01 | P0 | Missing spend could be serialized as a numeric zero at the API boundary. This made an unknown cost basis look like a known EUR 0. | `money()` and the campaign aggregator preserve null/blank for unknown spend. Zero is used only for a known zero aggregation. | API tests assert `MISSING` campaign spend is null/blank; UI shows "Unknown" rather than EUR 0. |
| A-02 | P0 | Cost coverage was considered complete after any compatible cost record, even if months in the campaign window were missing. | Coverage now requires compatible costs for every scheduled campaign month. Missing months make the campaign `PARTIAL`; no compatible costs make it `MISSING`; incompatible currency remains `PARTIAL`. | `test_cost_coverage_requires_every_campaign_month`; full profile has 256 budgeted campaigns, 251 with every month and 5 explicit missing-cost fixtures. |
| A-03 | P1 | A single "coverage" percentage mixed revenue completeness and conversion completeness. | Summary exposes `revenue_coverage_pct` and `conversion_coverage_pct` separately. | API and type checks; overview labels each percentage with its own denominator. |
| A-04 | P1 | Covered ROAS was reported without its exact numerator, denominator, and campaign scope. | The summary returns `covered_roas_numerator`, `covered_roas_denominator`, `covered_roi_pct`, and `covered_campaigns`; the UI displays all of them. | Full profile displays EUR 6,399,698.08 / EUR 3,787,007.67 = 1.69x. |
| A-05 | P1 | "Mean campaign ROI" looked like portfolio ROI, although it is an unweighted mean over ratio-eligible campaigns. | The label/description now states "Unweighted mean over N ROI-available campaigns"; portfolio covered ROI remains separate. | Full profile shows mean campaign ROI 159.22% over 246 campaigns versus covered portfolio ROI 68.99%. |
| A-06 | P1 | The campaign CSV export ignored active filters, search, model, sorting, and order. | `GET /api/campaigns/export` applies the same query contract as the table and emits only matching rows in the selected order. | Export parity test plus manual filtered export check. |
| A-07 | P1 | Campaign detail requested a non-existent export key (`cost_records` mismatch). | Detail export uses the canonical `cost_records` dataset and is labelled "All cost records CSV." | Campaign detail browser check and API export test. |
| A-08 | P1 | Campaign spend sorting used lexicographic/null-first behavior, placing unavailable spend ahead of numeric spend. | Aggregates use nullable numeric casts with deterministic `NULLS LAST` behavior. | Null-last sorting test and browser check. |
| A-09 | P1 | The run registry did not expose full counts or assurance fields needed on the Runs page. | The registry enriches manifests with all counts, validation/evaluation summaries, and volume fields. | Run registry API test and Runs page check. |
| A-10 | P1 | Detection evaluation UI used a stale sample count and could imply generalizable accuracy from fixture data. | The API/UI show the actual fixture sample (38) and label the result as synthetic fixture matching. | Evaluation endpoint and Data Quality browser check. |
| A-11 | P1 | The journey persistence claim was a badge without evidence. | Journey API returns per-model persisted versus recomputed credit, counts, differences, and a match flag; the UI displays them. | Journey persistence API test and browser check. |
| A-12 | P1 | Campaign aggregate copy said "unknown cost" and combined missing-cost campaigns with no-paid-basis campaigns. | Aggregates now expose `spend_missing_campaigns` and `spend_no_cost_basis_campaigns`; the UI renders both separately. | `NO_COST_BASIS` API test and Campaigns page check at 1440px and 390px. |
| A-13 | P1 | `yottaflex verify` regenerated in the live data root and could replace the active manifest's execution timestamp. | Verification runs twice in isolated temporary data/ground-truth/report roots and compares the two fresh manifests. | `test_verify_never_mutates_the_active_run`; CLI output shows `active_unchanged=True` for the manual small-profile check. |
| A-14 | P1 | Documentation described monthly cost coverage that the implementation did not actually enforce. | Documentation and implementation now agree: `COMPLETE` requires compatible cost coverage for every scheduled campaign month. | Architecture, data dictionary, and financial-rule tests updated. |

## What Was Not Changed

The following are intentional product boundaries, not hidden defects:

- Synthetic data only.
- No authentication; the console is a local operator tool.
- No FX conversion. Non-EUR cost records are quarantined rather than converted.
- `NO_COST_BASIS` is not an anomaly. A campaign with no paid budget is not ranked as a missing-cost failure.
- Detection is rule-based, not ML.
- The 100% fixture detection score is evidence of fixture matching only, not a claim about real-world precision or recall.

## Verification Snapshot

| Check | Result |
| --- | --- |
| Backend tests | 75 passed |
| Ruff | `All checks passed!` |
| Frontend typecheck | Passed |
| Production build | Passed |
| Small-profile determinism | Reproducible; hash `576476e6f0fa31d4c88572778fb7d5ce5325544d57151a7d087861c897aadf92` |
| Full-profile determinism | Reproducible; hash `ea303890c297e11b791f25e5f60e0fef4a43c54045231f25d08cd84ee1e7c9c1` |
| Mobile check | True 390px emulation; document width equals viewport with no page-level horizontal overflow |
| Active run | `full-20261022`; the audited canonical hash is stable |
| Unresolved P0/P1 findings | None in the audited scope |

See [FINAL_REVIEW.md](FINAL_REVIEW.md) for the full evidence table and residual risks.

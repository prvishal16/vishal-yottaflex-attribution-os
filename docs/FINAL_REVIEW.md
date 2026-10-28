# Final Review

**Review date:** 2026-10-27  
**Status:** Ready for review. No unresolved P0 or P1 findings in the audited scope.  
**Audited run:** `full-20261022`, seed `20261022`, synthetic data.

## Outcome

YottaFlex Attribution OS now has a consistent financial contract across generation, APIs, exports, UI, tests, and documentation:

- missing cost is unknown, never zero;
- spend coverage requires every scheduled campaign month and compatible currency;
- revenue coverage and conversion coverage are separate metrics;
- covered ROAS and ROI use matched campaign scope;
- campaign-level ratios are suppressed outside a complete cost basis;
- exports preserve the active filters, model, sort, and order;
- detection evaluation is clearly scoped to held-out synthetic fixtures;
- verification regenerates in isolation and does not mutate the active run;
- the full profile is reproducible at the documented canonical hash.

## Full-Profile Evidence

| Area | Evidence |
| --- | --- |
| Run | `full-20261022` |
| Generated at | `2026-10-27T11:02:16Z` UTC |
| Counts | 500 campaigns, 50,000 contacts, 200,000 touchpoints, 10,000 opportunities |
| Eligible conversion revenue | EUR 13,154,584.06 |
| Attributed revenue (linear) | EUR 11,224,486.73 |
| Unattributed revenue | EUR 1,930,097.33 |
| Revenue coverage | 85.33% |
| Attributed conversions | 4,543 |
| Conversion coverage | 84.96% |
| Recorded spend | EUR 3,884,384.40 |
| Covered spend | EUR 3,787,007.67 |
| Covered attributed revenue | EUR 6,399,698.08 |
| Covered ROAS | 1.69x |
| Covered ROI | 68.99% |
| Cost coverage | 246 complete / 256 budgeted campaigns; 5 missing, 5 partial; 5 incompatible cost records |
| Mean campaign ROI | 159.22% unweighted over 246 ROI-available campaigns |
| Data-quality issues | 38 open detections, 23 high severity |
| Validation | 119 checks, 0 failures, 7 expected warnings |
| Detection evaluation | 38/38 true positives, 0 false positives, 0 false negatives, 100% precision/recall/F1/severity accuracy |
| Canonical hash | `ea303890c297e11b791f25e5f60e0fef4a43c54045231f25d08cd84ee1e7c9c1` |

The full profile is the active dataset. The checked-in small and demo hashes are:

| Profile | Canonical hash |
| --- | --- |
| `small-20261022` | `576476e6f0fa31d4c88572778fb7d5ce5325544d57151a7d087861c897aadf92` |
| `demo-20261022` | `d30a8784818c737e0e55ef52548d03fb98a8728cb19bbb5b22285ddcc163200c` |
| `full-20261022` | `ea303890c297e11b791f25e5f60e0fef4a43c54045231f25d08cd84ee1e7c9c1` |

## Verification Log

| Command / check | Result |
| --- | --- |
| `python -m pytest -q` | 75 passed |
| `python -m ruff check backend scripts` | Passed |
| `npm run typecheck` | Passed |
| `npm run build` | Passed |
| `python -m yottaflex.cli verify --profile small --seed 20261022` | `REPRODUCIBLE`; matching hashes; active run unchanged |
| `python -m yottaflex.cli verify --profile demo --seed 20261022` | `REPRODUCIBLE`; matching hashes |
| `python -m yottaflex.cli verify --profile full --seed 20261022` | `REPRODUCIBLE`; matching hashes; active run unchanged |
| Full-profile regeneration | Same canonical hash as the audited full run |
| `GET /api/campaigns/export` | Filtered CSV, `text/csv; charset=utf-8`, correct attachment filename |
| Active run health | API live on `127.0.0.1:8000`, active run `full-20261022` |
| Browser QA | Overview, Campaigns, Campaign Detail, Journey, Data Quality, Runs checked |
| Mobile QA | True 390px device-metrics emulation; page width 390, document scroll width 390; table has local horizontal scroll |
| Console screenshots | Desktop 1440px and mobile 390px reviewed |

The mobile check used Chrome DevTools Protocol device emulation rather than a narrow headless window. Chrome enforces an internal minimum layout width when only `--window-size` is used, which produced an initial false-positive crop at 430px; true 390px emulation showed no page-level horizontal overflow.

## Delivered Changes

### Backend

- Nullable spend preservation and null-last campaign sorting.
- Month-level cost coverage enforcement in `domain/financials.py`.
- Split revenue/conversion coverage and matched covered ROAS scope.
- Campaign export endpoint with filter/model/sort/search parity.
- Run-registry enrichment with counts and assurance fields.
- Journey persisted-versus-recomputed credit evidence.
- Model-path sanitization and CSV content type/charset.
- Isolated, non-mutating reproducibility verification.

### Frontend

- Scope labels and formulas on overview and campaign metrics.
- Null/unknown spend rendering instead of zero.
- Mean campaign ROI eligibility count.
- Filter-aware CSV export.
- Campaign detail cost-ledger export and unavailable budget utilization state.
- Journey persistence evidence panel.
- Runs page volume counts, assurance metrics, and reproducibility command.
- Responsive fixes and true mobile verification at 390px.

### Tests and Documentation

- 75 backend tests, including financial scope, nullable spend, sorting, export parity, run counts, journey persistence, and isolated verification.
- Product audit, metric definitions, final review, architecture, data dictionary, and README updates.

## Scope and Residual Risks

These are documented boundaries, not hidden defects:

- **Synthetic data only.** The 38 fixtures are deliberately labelled. A 100% fixture score is not a production accuracy claim.
- **No authentication.** This is a local, single-operator console.
- **No FX conversion.** Non-EUR cost records are quarantined; no exchange rate is invented.
- **File-backed, single-tenant design.** Appropriate for this assessment, not a horizontally scaled service.
- **Browser QA is Chromium-focused.** The responsive layout and semantic controls were checked manually, but no formal screen-reader certification or automated axe run was performed.
- **The campaign table scrolls horizontally on narrow screens by design.** The page itself does not overflow; the table wrapper owns the scroll.
- **Full profile is compute-heavy.** It is intended for assessment-scale evidence, not every CI cycle.

## Acceptance Mapping

| Requirement | Evidence |
| --- | --- |
| Full dataset counts | 500 campaigns / 50,000 contacts / 200,000 touchpoints / 10,000 opportunities |
| Financial integrity | Nullable missing spend, month-level coverage, suppressed ratios outside complete basis |
| Attribution explainability | Three models, journey replay, excluded-touch reasons, persisted-vs-recomputed check |
| Data-quality evidence | Five rules, evidence packets, open dispositions, independent evaluation |
| Reproducibility | Matching small/full hashes, canonical manifests, isolated verify |
| Usability | Desktop and 390px responsive checks; explicit metric scope and unavailable states |
| Verification | 75 tests, ruff, typecheck, production build, browser QA |
| Documentation | Audit, metric definitions, final review, architecture, data dictionary, README |

## Related Documents

- [Product audit](PRODUCT_AUDIT.md)
- [Metric definitions](METRIC_DEFINITIONS.md)
- [Architecture](ARCHITECTURE.md)
- [Data dictionary](DATA_DICTIONARY.md)

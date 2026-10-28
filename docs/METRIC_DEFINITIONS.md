# Metric Definitions

This document is the financial and evaluation contract for the console and API. All monetary values are EUR unless stated otherwise. Percentages are rounded to two decimals at presentation time. The default model for headline numbers is `linear`.

The key rule is **scope before ratio**: a ratio is shown only when its numerator and denominator describe the same eligible population and the spend basis is complete and positive.

## Revenue and Coverage

### Eligible conversion

A recognized order that enters the canonical attribution population. Orders are recognized when their status is `PAID` or `PARTIALLY_REFUNDED`; source duplicates are removed first. Revenue is the order amount less any refund.

Eligible conversions are not automatically attributed. Identity resolution, consent, lookback, and touch eligibility still determine whether credit exists.

### Attributed revenue

The sum of eligible conversion revenue that received credit under a model. Each attributed conversion is allocated to one or more eligible touchpoints; the model allocations sum back to the conversion revenue.

### Unattributed revenue

```text
unattributed revenue = eligible conversion revenue - attributed revenue
```

This is revenue from eligible recognized orders that could not be credited because no touch passed identity, consent, lookback, or touch-eligibility checks.

### Revenue coverage

```text
revenue coverage % = attributed revenue / eligible conversion revenue * 100
```

This answers: **how much eligible revenue received credit?** It is not identity coverage and not conversion coverage.

### Attributed conversions

The count of eligible conversions with at least one credited touch under the selected model.

### Conversion coverage

```text
conversion coverage % = attributed conversions / eligible conversions * 100
```

An attributed conversion is allocated in full, but the two coverage percentages use different denominators: conversion coverage weights every eligible order equally, while revenue coverage weights by order value. They can therefore differ when attributed orders have a higher or lower average value than unattributed orders.

### Campaign conversion credits

The campaign ledger sums attributed conversions across campaign rows. One order can be credited to more than one campaign under a multi-touch model, so this figure is a **credit count**, not a count of unique orders. The full profile shows 19,051 campaign conversion credits against 4,543 uniquely attributed conversions.

## Cost Basis

### Budget

The planned campaign budget from campaign metadata. Budget is not spend and is never substituted for a missing cost record.

### Recorded spend

The sum of cost records whose currency equals the campaign's budget currency. Incompatible-currency records are quarantined and excluded from EUR spend. Recorded spend can include campaigns whose monthly cost coverage is incomplete, so it is a **known recorded total**, not a fully covered spend basis.

### Covered spend

The sum of recorded spend for campaigns whose cost coverage is `COMPLETE`. Covered spend is the denominator for covered ROAS and covered ROI.

### Covered attributed revenue

Attributed revenue from the same `COMPLETE`-coverage campaigns used for covered spend. This matched scope is essential: covered revenue and covered spend must come from the same campaign set.

### Cost-coverage statuses

| Status | Meaning | Ratio behavior |
| --- | --- | --- |
| `COMPLETE` | Budget is positive, every scheduled month has compatible cost coverage, and no incompatible-currency cost is attached. | ROI/ROAS/cost-per-conversion may be reported if spend is positive. |
| `PARTIAL` | At least one scheduled month lacks a compatible cost, or an incompatible-currency cost is attached. | ROI/ROAS/cost-per-conversion suppressed. |
| `MISSING` | Budget is positive but no compatible cost record exists. | ROI/ROAS/cost-per-conversion suppressed. Spend is unknown, not zero. |
| `NO_COST_BASIS` | Budget is zero or absent; there is no paid-cost basis. | ROI/ROAS/cost-per-conversion suppressed. Not counted as a missing-cost anomaly. |

The campaign window runs from the campaign start month through the campaign end month. A single cost record does not make a multi-month campaign `COMPLETE`.

## Profitability

### Campaign ROI

For a campaign with `COMPLETE` coverage and positive spend:

```text
roi_pct = (campaign attributed revenue - campaign spend) / campaign spend * 100
```

### Campaign ROAS

```text
roas = campaign attributed revenue / campaign spend
```

Both are suppressed when the campaign is `PARTIAL`, `MISSING`, `NO_COST_BASIS`, or has zero spend.

### Covered portfolio ROI

```text
covered ROI % = (covered attributed revenue - covered spend) / covered spend * 100
```

This is the headline portfolio return on the campaigns that have a complete cost basis. It is revenue-weighted by construction because it sums the numerator and denominator across campaigns.

### Covered portfolio ROAS

```text
covered ROAS = covered attributed revenue / covered spend
```

### Why the recorded-spend ratio is not reported

A ratio such as:

```text
attributed revenue / recorded spend
```

would mix revenue from campaigns **without** complete cost coverage with spend from campaigns that have partial or unknown coverage. It can look numerically valid while comparing different populations. It is therefore deliberately not a headline metric.

### Mean campaign ROI

```text
mean campaign ROI = arithmetic mean of campaign roi_pct for campaigns where roi_available = true
```

This is an **unweighted** mean of campaign percentages, not portfolio ROI. It is sensitive to small-spend campaigns and is displayed with its eligible campaign count. Example from the full profile: 159.22% over 246 eligible campaigns, while covered portfolio ROI is 68.99%.

### Cost per conversion

```text
cost per conversion = campaign spend / attributed conversions
```

Reported only for `COMPLETE` coverage campaigns with attributed conversions greater than zero.

### Budget utilization

```text
budget utilization % = spend / budget * 100
```

Reported only for `COMPLETE` coverage campaigns with a positive budget. A `MISSING`, `PARTIAL`, or `NO_COST_BASIS` campaign exposes no utilization bar because its spend basis is incomplete.

### Average order value

```text
average order value = attributed revenue / attributed conversions
```

Available whenever attributed conversions are greater than zero.

## Identity and Conversion Quality

### Touchpoint identity coverage

The share of touchpoints that resolve to a contact through a supported, verified identity link with non-empty evidence. It measures linkage coverage, not attribution or consent.

Identity is never inferred from temporal proximity. Consent is checked at conversion time.

### Summary conversion rate

```text
conversion rate % = eligible conversions / opportunities * 100
```

This is the executive funnel view, not attribution conversion coverage.

## Detection and Evaluation

Detection runs deterministic rules over persisted business records. The five fixture classes are:

- `DUPLICATE_REVENUE`
- `POST_CONVERSION_TOUCH`
- `CURRENCY_MISMATCH`
- `MISSING_CAMPAIGN_COST`
- `UNSUPPORTED_IDENTITY_LINK`

Ground truth is stored outside the detection path and is read only by evaluation. A fixture is matched when the issue type and affected record set agree.

### Precision

```text
precision = true positives / (true positives + false positives)
```

### Recall

```text
recall = true positives / (true positives + false negatives)
```

### F1

```text
F1 = 2 * precision * recall / (precision + recall)
```

### Severity accuracy

The share of matched detected issues whose severity equals the labelled fixture severity.

The full profile reports 38/38 true positives, zero false positives, zero false negatives, 100% precision/recall/F1, and 100% severity accuracy on the checked-in synthetic fixtures. This result demonstrates fixture and rule alignment only; it is not a generalizable production accuracy claim.

## Current Reference Values

These values are for the audited `full-20261022` run (seed `20261022`) and use the `linear` model:

| Metric | Value | Definition |
| --- | ---: | --- |
| Eligible conversion revenue | EUR 13,154,584.06 | Recognized-order revenue entering attribution |
| Attributed revenue | EUR 11,224,486.73 | Revenue receiving model credit |
| Unattributed revenue | EUR 1,930,097.33 | Eligible minus attributed revenue |
| Revenue coverage | 85.33% | Attributed / eligible revenue |
| Attributed conversions | 4,543 | Conversions with credited touches |
| Conversion coverage | 84.96% | Attributed / eligible conversions |
| Recorded spend | EUR 3,884,384.40 | Compatible EUR cost records |
| Covered spend | EUR 3,787,007.67 | Spend for `COMPLETE` campaigns only |
| Covered attributed revenue | EUR 6,399,698.08 | Revenue for the same `COMPLETE` campaigns |
| Covered ROAS | 1.69x | EUR 6,399,698.08 / EUR 3,787,007.67 |
| Covered ROI | 68.99% | EUR 2,612,690.41 profit / EUR 3,787,007.67 covered spend |
| Complete cost coverage | 246 / 256 budgeted campaigns | Month-complete and currency-compatible |
| Mean campaign ROI | 159.22% | Unweighted mean over 246 ROI-available campaigns |
| Data-quality issues | 38 open detections | Five synthetic fixture classes |
| Validation | 119 checks, 0 failures, 7 expected warnings | Pass with warnings |
| Detection | 38/38 TP, 0 FP, 0 FN | 100% fixture precision/recall/F1 |

For comparison, the small profile reports 75.44% revenue coverage, 87.25% conversion coverage, EUR 195,131.42 covered spend, EUR 107,589.65 covered attributed revenue, 0.55x covered ROAS, and -44.86% covered ROI. The negative result is retained deliberately; the small profile is a fixture-focused validation set, not a performance showcase.

## Interpretation Rules

- Never treat blank spend as zero.
- Never show a ROI/ROAS/cost-per-conversion ratio for `PARTIAL`, `MISSING`, or `NO_COST_BASIS`.
- Never compare recorded spend to covered revenue.
- Never average campaign ROI percentages and call the result portfolio ROI.
- Always show the count of campaigns behind an average.
- Always label synthetic detection results as fixture evaluation, not production accuracy.
- An open exception remains open until disposition is recorded; detection does not silently resolve it.

The detailed field contract is in [DATA_DICTIONARY.md](DATA_DICTIONARY.md).

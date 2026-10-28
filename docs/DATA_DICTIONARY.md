# Data Dictionary

All timestamps are UTC ISO-8601 values. Monetary source columns are stored as decimal strings in CSV and cast to decimal values in DuckDB. The reporting currency is EUR unless a column explicitly carries a different currency.

## Conventions

| Convention | Meaning |
| --- | --- |
| `*_id` | Stable synthetic identifier. |
| `*_at`, `*_ts` | Timestamp in UTC. |
| `*_date` | Calendar date. |
| `*_amount`, `*_revenue`, `spend` | Decimal monetary value in the row currency. `spend` is blank when the cost basis is unknown. |
| `currency` | ISO 4217 currency code. |
| `is_paid`, `is_offline` | Boolean stored as `true` / `false`. |
| `split` | Chronological evaluation split: `train`, `validation`, or `test`. |
| `model` | Attribution model: `first_touch`, `last_touch`, or `linear`. |
| `status` | Entity lifecycle, result, or check status. Case varies by table as documented below. |

### Identifier formats

| Entity | Pattern | Example |
| --- | --- | --- |
| Campaign | `CMP-<year>-<sequence>` | `CMP-2026-000001` |
| Channel | `CHN-<sequence>` | `CHN-000001` |
| Audience | `AUD-<sequence>` | `AUD-000001` |
| Creative | `CRE-<sequence>` | `CRE-000001` |
| Contact | `CON-<year>-<sequence>` | `CON-2026-000001` |
| Session | `SES-<year>-<sequence>` | `SES-2026-000001` |
| Lead | `LEAD-<year>-<sequence>` | `LEAD-2026-000001` |
| Opportunity | `OPP-<year>-<sequence>` | `OPP-2026-000001` |
| Order | `ORD-<year>-<sequence>` | `ORD-2026-000001` |
| Cost record | `COST-<year>-<sequence>` | `COST-2026-000001` |
| Attribution result | `ATTR-<year>-<sequence>` | `ATTR-2026-000001` |
| Attribution conversion | `CONV-<year>-<sequence>` | `CONV-2026-000001` |
| Lifecycle event | `EVT-<year>-<sequence>` | `EVT-2026-000001` |
| Identity link | `LNK-<year>-<sequence>` | `LNK-2026-000001` |
| Exception | `ISS-<year>-<sequence>` | `ISS-2026-000001` |
| Anonymous ID | `ANON-<sequence>` | `ANON-00000001` |

### Chronological splits

| Split | Starts | Ends (exclusive) |
| --- | --- | --- |
| `train` | 2025-09-01 | 2026-06-01 |
| `validation` | 2026-06-01 | 2026-07-15 |
| `test` | 2026-07-15 | 2026-10-01 |

## Core Tables

### channels

Marketing delivery channels and their categories.

Primary key: `channel_id`

Columns: `channel_id`, `name`, `category`, `channel_type`, `is_paid`

### audiences

Synthetic audience segments targeted by campaigns.

Primary key: `audience_id`

Columns: `audience_id`, `name`, `category`, `definition`, `effective_from`, `effective_to`, `status`

### campaigns

Campaign configuration, budget and lifecycle status.

Primary key: `campaign_id`

Columns: `campaign_id`, `name`, `campaign_type`, `objective`, `start_at`, `end_at`, `status`, `budget_amount`, `budget_currency`, `primary_channel_id`, `target_audience_id`, `created_at`, `updated_at`

`budget_amount` is the planned budget. It is not spend and is never used as a substitute for a cost record.

### campaign_channels

Bridge table for campaign/channel relationships.

Primary key: `campaign_id`, `channel_id`

Columns: `campaign_id`, `channel_id`, `is_primary`

### campaign_audiences

Bridge table for campaign/audience relationships.

Primary key: `campaign_id`, `audience_id`

Columns: `campaign_id`, `audience_id`

### creatives

Campaign creative assets tied to a campaign and channel.

Primary key: `creative_id`

Columns: `creative_id`, `campaign_id`, `channel_id`, `name`, `creative_type`, `start_at`, `end_at`, `status`, `created_at`

### contacts

Synthetic contacts with non-identifying attributes only.

Primary key: `contact_id`

Columns: `contact_id`, `created_at`, `region`, `country`, `segment`, `consent_status`, `lifecycle_status`, `acquisition_channel_id`

`consent_status` is evaluated at the conversion timestamp. A contact with `GRANTED` consent is eligible for attribution. Contact records contain no names, emails, phone numbers, or other direct identifiers.

### sessions

Web sessions. Contact identity is stored only in identity_links.

Primary key: `session_id`

Columns: `session_id`, `anonymous_id`, `started_at`, `ended_at`, `source`, `medium`, `landing_page`, `campaign_id`, `device_type`

### identity_links

Evidence-backed links between anonymous sessions and contacts.

Primary key: `link_id`

Columns: `link_id`, `session_id`, `contact_id`, `evidence_type`, `evidence_ref`, `linked_at`, `status`, `rule_id`

Supported evidence types:

- `AUTHENTICATED_LOGIN`
- `EMAIL_CLICK_SSO`
- `FORM_SUBMIT_MATCH`
- `CRM_IMPORT_MATCH`

A link requires non-empty evidence and `VERIFIED` status. `TEMPORAL_PROXIMITY`, `NONE`, empty evidence, and unverified links are not valid identity evidence.

### touchpoints

Marketing interactions, online and offline.

Primary key: `touchpoint_id`

Columns: `touchpoint_id`, `contact_id`, `session_id`, `campaign_id`, `channel_id`, `creative_id`, `occurred_at`, `touch_type`, `source_system`, `identity_status`, `consent_status`, `is_offline`, `created_at`

`contact_id` may be null for anonymous interactions; journey resolution can still recover it through `identity_links`. Post-conversion touchpoints remain persisted as source evidence and are excluded from attribution.

### leads

Leads created from marketing activity.

Primary key: `lead_id`

Columns: `lead_id`, `contact_id`, `created_at`, `source`, `status`, `qualified_at`, `source_session_id`

### opportunities

Sales opportunities and their lifecycle state.

Primary key: `opportunity_id`

Columns: `opportunity_id`, `lead_id`, `contact_id`, `created_at`, `stage`, `expected_value`, `currency`, `closed_at`, `outcome`, `owner_team`

### orders

Net order revenue and refund/cancellation status.

Primary key: `order_id`

Columns: `order_id`, `opportunity_id`, `contact_id`, `ordered_at`, `status`, `amount`, `refunded_amount`, `currency`, `source_system_ref`, `ingested_at`

Recognized statuses are `PAID` and `PARTIALLY_REFUNDED`. Recognized revenue is `amount - refunded_amount`. Duplicate source transactions are deduplicated by `source_system_ref`; the earliest ingested order is canonical. `CANCELLED` and `REFUNDED` orders do not become conversions.

### cost_records

Actual campaign spend records. Missing cost is not zero.

Primary key: `cost_id`

Columns: `cost_id`, `campaign_id`, `channel_id`, `creative_id`, `cost_date`, `amount`, `currency`, `cost_category`, `source_ref`, `period`

Only compatible EUR records contribute to spend. Incompatible currencies are quarantined by detection. A missing monthly record makes cost coverage incomplete; it is never imputed as zero.

### lifecycle_events

Append-only state transition history for core entities.

Primary key: `event_id`

Columns: `event_id`, `entity_type`, `entity_id`, `previous_state`, `new_state`, `occurred_at`, `reason`, `source`

## Derived Tables

### attribution_results

Credit allocated to one touchpoint for one conversion and model.

Primary key: `attribution_result_id`

Columns: `attribution_result_id`, `order_id`, `opportunity_id`, `contact_id`, `model`, `touchpoint_id`, `campaign_id`, `channel_id`, `credit_fraction`, `attributed_revenue`, `currency`, `attribution_run_id`, `rule_version`, `computed_at`

`credit_fraction` is the model-specific share of the conversion allocated to the touchpoint. `attributed_revenue = conversion_revenue * credit_fraction`, rounded to two decimal places. `computed_at` is excluded from canonical reproducibility hashes.

### attribution_conversions

One row per conversion and model, including unattributed outcomes.

Primary key: `conversion_result_id`

Columns: `conversion_result_id`, `order_id`, `opportunity_id`, `contact_id`, `model`, `status`, `conversion_revenue`, `eligible_touchpoints`, `excluded_post_conversion`, `excluded_outside_window`, `excluded_identity_unresolved`, `excluded_consent`, `excluded_no_campaign`, `attributed_touchpoints`, `attributed_revenue`, `exclusion_reason`, `attribution_run_id`, `rule_version`, `computed_at`

`status` is `ATTRIBUTED` or `UNATTRIBUTED`. The exclusion counters explain every touch candidate considered for the conversion. `computed_at` is excluded from canonical hashes.

### campaign_performance

Campaign-level financial and attribution metrics by model.

Primary key: `campaign_id`, `model`

Columns: `campaign_id`, `campaign_name`, `campaign_type`, `objective`, `primary_channel_id`, `primary_channel_name`, `start_at`, `end_at`, `status`, `budget_amount`, `budget_currency`, `model`, `spend`, `spend_currency`, `cost_coverage`, `attributed_revenue`, `conversions`, `unique_converting_contacts`, `touchpoints_credited`, `roi_pct`, `roas`, `roi_available`, `roi_status`, `budget_utilization`, `cost_per_conversion`, `average_order_value`, `issue_count`

`cost_coverage` values:

| Value | Meaning |
| --- | --- |
| `COMPLETE` | Every month in the campaign's scheduled start-to-end window has a compatible cost record, and no incompatible-currency cost is attached. ROI is reportable. |
| `PARTIAL` | At least one scheduled month lacks compatible cost coverage, or an incompatible-currency cost is attached. ROI is suppressed. |
| `MISSING` | A budget exists but no compatible cost records exist. `spend` is blank and ROI is suppressed. |
| `NO_COST_BASIS` | No paid budget exists; `spend` is blank and missing cost is not an anomaly. |

`spend` is blank for `MISSING` and `NO_COST_BASIS`; blank never means zero. `roi_pct`, `roas`, `cost_per_conversion`, and budget utilization are null unless `roi_available = true`. `conversions` counts conversion-campaign credit rows, so one order can appear under more than one campaign.

### channel_performance

Channel-level financial and attribution metrics by model.

Primary key: `channel_id`, `model`

Columns: `channel_id`, `channel_name`, `category`, `model`, `spend`, `spend_currency`, `cost_coverage`, `attributed_revenue`, `conversions`, `unique_converting_contacts`, `touchpoints_credited`, `roi_pct`, `roas`, `roi_available`, `roi_status`

### exceptions

Detected data-quality issues and their dispositions.

Primary key: `issue_id`

Columns: `issue_id`, `issue_type`, `severity`, `entity_type`, `affected_record_ids`, `primary_entity_id`, `detection_rule_id`, `detected_at`, `explanation`, `evidence`, `suggested_disposition`, `status`, `split`

`evidence` is a JSON object containing the specific records and values that triggered the rule. `affected_record_ids` is a pipe-separated list. `detected_at` is excluded from canonical hashes.

### validation_results

Individual structural, temporal, financial and attribution checks.

Primary key: `check_id`

Columns: `check_id`, `category`, `rule_id`, `description`, `status`, `severity`, `records_examined`, `failure_count`, `affected_record_ids`, `message`

`status` is `PASS`, `WARNING`, or `FAIL`. Intentional fixture violations are expected to produce warnings, not failures.

### financial_reconciliation

Reconciliation of source revenue, attributed revenue and spend.

Primary key: `scope`, `model`

Columns: `scope`, `model`, `currency`, `eligible_conversion_revenue`, `attributed_revenue`, `unattributed_revenue`, `recorded_spend`, `covered_spend`, `covered_attributed_revenue`, `roi_pct`, `roas`, `status`, `detail`

The invariant is `eligible_conversion_revenue = attributed_revenue + unattributed_revenue`, subject only to two-decimal rounding.

`scope = overall` contains the full eligible/attributed revenue split and recorded spend. Its `roi_pct` and `roas` are blank whenever any budgeted campaign has incomplete coverage; they are never calculated by mixing covered revenue with total recorded spend.

`scope = covered` contains matched `covered_attributed_revenue` and `covered_spend` for campaigns with `COMPLETE` coverage. Its `roi_pct` and `roas` are the reportable covered portfolio values and are blank when covered spend is zero.

## DuckDB Views

Views adapt canonical snake-case tables to stable API-friendly names and expose typed booleans and decimals.

| View | Purpose |
| --- | --- |
| `v_channels` | Channel reference with stable names. |
| `v_audiences` | Audience reference. |
| `v_creatives` | Creative reference. |
| `v_campaigns` | Campaign reference with timestamp and decimal aliases. |
| `v_contacts` | Contact reference. |
| `v_orders` | Orders with recognized revenue, timestamps, and decimal aliases. |
| `v_touchpoints` | Touchpoints with timestamp aliases. |
| `v_identity_links` | Verified identity links. |
| `v_cost_records` | Cost records with decimal amounts and date aliases. |
| `v_attribution_results` | Attribution result rows with decimal aliases. |
| `v_attribution_conversions` | Conversion-model outcomes with decimal aliases. |
| `v_campaign_performance` | Campaign metrics by model with typed ROI availability. |
| `v_channel_performance` | Channel metrics by model. |
| `v_campaign_issues` | Campaign-level exception counts. |
| `v_exceptions` | Exception queue with typed evidence. |
| `v_validation_results` | Validation checks. |
| `v_financial_reconciliation` | Financial reconciliation rows. |

DuckDB views are rebuilt after every generation, so the API always reads from the current canonical CSV state.

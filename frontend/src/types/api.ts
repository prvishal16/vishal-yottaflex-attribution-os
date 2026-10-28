export type ModelName = "first_touch" | "last_touch" | "linear";
export type Severity = "HIGH" | "MEDIUM" | "LOW";
export type SplitName = "train" | "validation" | "test";

export interface ValidationTotals {
  checks: number;
  failures: number;
  passed: number;
  warnings: number;
}

export interface ValidationSummary {
  attribution_checks_included: boolean;
  categories: Record<
    string,
    { checks: number; failures: number; passed: number; warnings: number }
  >;
  generated_at: string;
  mode: string;
  overall_status: "PASS" | "PASS_WITH_WARNINGS" | "FAIL";
  profile: string;
  rule_version: string;
  run_id: string;
  seed: number;
  totals: ValidationTotals;
  warning_details: Array<{ failure_count: number; message: string; rule_id: string }>;
}

export interface EvaluationTotals {
  detected: number;
  f1_pct: string;
  false_negatives: number;
  false_positives: number;
  ground_truth: number;
  precision_pct: string;
  recall_pct: string;
  severity_accuracy_pct: string;
  true_positives: number;
}

export interface SummaryResponse {
  anomaly_distribution: Array<{ count: number; issue_type: string; severity: Severity }>;
  attribution_by_model: Record<
    ModelName,
    {
      attributed_conversions: number;
      attributed_revenue: string;
      eligible_revenue: string;
      unattributed_conversions: number;
    }
  >;
  channel_contribution: Array<{
    attributed_revenue: string;
    category: string;
    channel_id: string;
    channel_name: string;
    conversions: number;
    roi_available: string | boolean;
    roi_pct: string;
    spend: string | null;
  }>;
  data_quality_status: "HEALTHY" | "ATTENTION_REQUIRED";
  financials: {
    budgeted_campaigns: number;
    coverage_detail: string;
    covered_attributed_revenue: string;
    covered_campaigns: number;
    covered_roas: string;
    covered_roas_denominator: string;
    covered_roas_numerator: string;
    covered_roi_pct: string;
    covered_spend: string;
    reconciliation_status: string;
    recorded_spend: string;
    roi_available: boolean;
    roi_status: string;
  };
  kpis: {
    attributed_conversions: number;
    attributed_revenue: string;
    attribution_results: number;
    budgeted_campaigns: number;
    campaigns: number;
    complete_cost_campaigns: number;
    contacts: number;
    conversion_coverage_pct: string;
    conversion_rate_pct: string;
    cost_coverage_pct: string;
    data_quality_issues: number;
    eligible_conversion_revenue: string;
    eligible_conversions: number;
    high_severity_issues: number;
    identity_coverage_pct: string;
    incompatible_cost_records: number;
    leads: number;
    missing_cost_campaigns: number;
    opportunities: number;
    orders: number;
    partial_cost_campaigns: number;
    recorded_spend: string;
    revenue_coverage_pct: string;
    roas: string;
    roi_available: boolean;
    roi_pct: string;
    roi_scope: string;
    roi_status: string;
    sessions: number;
    touchpoints: number;
    unattributed_conversions: number;
    unattributed_revenue: string;
  };
  lookback_days: number;
  model_comparison: Array<{
    attributed_conversions: number;
    attributed_revenue: string;
    eligible_revenue: string;
    model: ModelName;
    unattributed_conversions: number;
  }>;
  monthly: Array<{
    attributed_conversions: number;
    attributed_revenue: string;
    eligible_revenue: string;
    month: string;
    spend: string;
  }>;
  notice: string;
  profile: string;
  reporting_currency: string;
  run_id: string;
  run: {
    run_id: string;
    profile: string;
    seed: number;
    generated_at: string;
    status: string;
    combined_hash: string;
  };
  seed: number;
  splits: Array<{ end_exclusive: string; name: SplitName; start: string }>;
  top_campaigns: Array<{
    attributed_revenue: string;
    campaign_id: string;
    campaign_name: string;
    channel_name: string;
    cost_coverage: CostCoverage;
    roi_available: string | boolean;
    roi_pct: string;
    spend: string | null;
  }>;
  validation?: ValidationSummary;
  evaluation?: { status: string; totals: EvaluationTotals };
}

export type CostCoverage = "COMPLETE" | "PARTIAL" | "MISSING" | "NO_COST_BASIS";

export interface CampaignItem {
  campaign_id: string;
  campaign_name: string;
  campaign_type: string;
  objective: string;
  primary_channel_id: string;
  primary_channel_name: string;
  start_at: string;
  end_at: string;
  status: string;
  model: ModelName;
  budget_amount: number | null;
  budget_currency: string;
  spend: number | null;
  cost_coverage: CostCoverage;
  attributed_revenue: number;
  conversions: number;
  unique_converting_contacts: number;
  touchpoints_credited: number;
  roi_pct: number | null;
  roas: number | null;
  roi_available: boolean;
  roi_status: string;
  budget_utilization: number | null;
  cost_per_conversion: number | null;
  average_order_value: number | null;
  issue_count: number;
}

export interface CampaignListResponse {
  items: CampaignItem[];
  total: number;
  limit: number;
  offset: number;
  model: ModelName;
  currency: string;
  aggregates: {
    attributed_revenue: number;
    spend: number | null;
    spend_known_campaigns: number;
    spend_missing_campaigns: number;
    spend_no_cost_basis_campaigns: number;
    conversions: number;
    average_roi_pct: number | null;
    roi_campaigns: number;
  };
}

export interface CampaignDetailResponse {
  campaign: {
    campaign_id: string;
    campaign_name: string;
    campaign_type: string;
    objective: string;
    primary_channel_id: string;
    target_audience_id: string;
    start_at: string;
    end_at: string;
    status: string;
    budget_amount: number | null;
    budget_currency: string;
  };
  performance: {
    model: ModelName;
    spend: number | null;
    cost_coverage: CostCoverage;
    attributed_revenue: number;
    conversions: number;
    unique_converting_contacts: number;
    touchpoints_credited: number;
    roi_pct: number | null;
    roas: number | null;
    roi_available: boolean;
    roi_status: string;
    budget_utilization: number | null;
    cost_per_conversion: number | null;
    average_order_value: number | null;
    issue_count: number;
  };
  model_comparison: Array<{
    model: ModelName;
    attributed_revenue: number;
    conversions: number;
    unique_converting_contacts: number;
    touchpoints_credited: number;
    roi_pct: number | null;
    roi_available: boolean;
  }>;
  cost_records: Array<{
    cost_id: string;
    cost_date: string;
    amount: number;
    currency: string;
    cost_category: string;
    source_ref: string;
    period: string;
  }>;
  channel_mix: Array<{
    channel_id: string;
    channel_name: string;
    category: string;
    attributed_revenue: number;
    conversions: number;
    touchpoints: number;
  }>;
  creatives: Array<{
    creative_id: string;
    name: string;
    creative_type: string;
    status: string;
  }>;
  monthly: Array<{ month: string; attributed_revenue: number; conversions: number }>;
  issues: Array<{
    issue_id: string;
    issue_type: string;
    severity: Severity;
    primary_entity_id: string;
    affected_record_ids: string;
    explanation: string;
    suggested_disposition: string;
    status: string;
    split: SplitName;
  }>;
  run_id: string;
}

export interface ChannelOption {
  channel_id: string;
  channel_name: string;
  category: string;
  spend: number | null;
  attributed_revenue: number | null;
  cost_coverage: CostCoverage | null;
  roi_pct: number | null;
  roi_available: boolean | null;
}

export interface ChannelListResponse {
  items: ChannelOption[];
  model: ModelName;
  run_id: string;
}

export interface CompareResponse {
  model_a: ModelName;
  model_b: ModelName;
  totals: Record<ModelName, { attributed_revenue: number; conversions: number }>;
  share_basis: {
    definition: string;
    delta_definition: string;
    unit: string;
    model_a_total: number;
    model_b_total: number;
    reconciles_to_model_totals: boolean;
  };
  campaign_changes: Array<{
    campaign_id: string;
    label: string;
    channel_name: string;
    first_touch: number;
    last_touch: number;
    linear: number;
    delta: number;
    share_a_pct: number;
    share_b_pct: number;
    share_delta_pct: number;
  }>;
  campaign_count: number;
  channel_changes: Array<{
    channel_id: string;
    label: string;
    channel_name: string;
    first_touch: number;
    last_touch: number;
    linear: number;
    delta: number;
    share_a_pct: number;
    share_b_pct: number;
    share_delta_pct: number;
  }>;
  channel_count: number;
  channel_sort: string;
  run_id: string;
}

export interface CampaignListContext {
  model: ModelName;
  sort: string;
  order: "asc" | "desc";
  channel: string;
  coverage: string;
  search: string;
  page: number;
  total: number;
}

export interface ExceptionItem {
  issue_id: string;
  issue_type: string;
  severity: Severity;
  entity_type: string;
  affected_record_ids: string;
  primary_entity_id: string;
  detection_rule_id: string;
  detected_at: string;
  explanation: string;
  suggested_disposition: string;
  status: string;
  split: SplitName;
}

export interface ExceptionListResponse {
  items: ExceptionItem[];
  total: number;
  limit: number;
  offset: number;
  facets: Record<string, Array<{ value: string; count: number }>>;
  run_id: string;
}

export interface ExceptionDetailResponse extends ExceptionItem {
  evidence: Record<string, unknown>;
  related: {
    campaign?: {
      campaign_id: string;
      campaign_name: string;
      status: string;
      budget_amount: number | null;
      budget_currency: string;
    };
    records?: Array<Record<string, unknown>>;
  };
  run_id: string;
}

export interface ValidationCheck {
  affected_record_ids: string;
  category: string;
  check_id: string;
  description: string;
  failure_count: number;
  message: string;
  records_examined: number;
  rule_id: string;
  severity: string;
  status: "PASS" | "WARNING" | "FAIL";
}

export interface ValidationResponse {
  run_id: string;
  summary: ValidationSummary;
  checks: ValidationCheck[];
  total_checks: number;
}

export interface EvaluationMatch {
  explanation: string;
  issue_type: string;
  matched_issue_id: string;
  expected_record_ids: string;
  expected_severity: Severity;
  detected_severity: Severity;
  scenario_id: string;
  severity_match: boolean | string;
  detected_split: SplitName;
  ground_truth_split: SplitName;
}

export interface EvaluationResponse {
  run_id: string;
  status: string;
  totals: EvaluationTotals;
  by_type: Array<{
    issue_type: string;
    detected: number;
    ground_truth: number;
    true_positives: number;
    false_positives: number;
    false_negatives: number;
    precision_pct: string;
    recall_pct: string;
    f1_pct: string;
    severity_accuracy_pct: string;
  }>;
  by_split: Array<{
    split: SplitName;
    detected: number;
    ground_truth: number;
    true_positives: number;
    false_positives: number;
    false_negatives: number;
    precision_pct: string;
    recall_pct: string;
  }>;
  matches: EvaluationMatch[];
}

export interface JourneyTouch {
  touchpoint_id: string;
  occurred_at: string;
  minutes_from_conversion: number;
  campaign_id: string;
  campaign_name: string;
  channel_id: string;
  channel_name: string;
  creative_name: string | null;
  touch_type: string;
  source_system: string;
  identity_status: string;
  resolution_status: string;
  resolution_rule_id: string;
  resolved_contact_id: string | null;
  consent_status: string;
  outcome: string;
  outcome_reason: string;
  eligible: boolean;
  credits: Record<string, { credit_fraction: number; attributed_revenue: number }>;
}

export interface JourneyResponse {
  run_id: string;
  reference: string;
  status: "CONVERTED" | "NO_RECOGNIZED_CONVERSION";
  opportunity: {
    opportunity_id: string;
    lead_id: string;
    contact_id: string;
    created_at: string;
    stage: string;
    outcome: string;
    expected_value: number;
    currency: string;
    closed_at: string | null;
    owner_team: string;
  } | null;
  contact: {
    contact_id: string;
    created_at: string;
    region: string;
    country: string;
    segment: string;
    consent_status: string;
    lifecycle_status: string;
    acquisition_channel_id: string;
  } | null;
  conversion: {
    order_id: string;
    opportunity_id: string;
    contact_id: string;
    ordered_at: string;
    revenue: number;
    currency: string;
    split: SplitName;
    lookback_days: number;
    consent_status: string;
    source_system_ref: string;
    duplicate_orders: Array<{
      order_id: string;
      status: string;
      amount: number;
      ingested_at: string;
      canonical: boolean;
    }>;
  } | null;
  exclusions?: {
    excluded_post_conversion: number;
    excluded_outside_window: number;
    excluded_identity_unresolved: number;
    excluded_consent: number;
    excluded_no_campaign: number;
  };
  counts?: {
    total_touches: number;
    eligible_touches: number;
    excluded_touches: number;
    credited_touchpoints: Record<ModelName, number>;
    exclusion_semantics: string;
  };
  models: Array<{
    model: ModelName;
    status: "ATTRIBUTED" | "UNATTRIBUTED";
    attributed_revenue: number;
    credited_touchpoints: number;
    eligible_touchpoints: number;
    reconciliation_difference: number;
  }>;
  persisted_consistent: boolean;
  persisted_check?: {
    consistent: boolean;
    difference_count: number;
    models: Array<{
      model: ModelName;
      computed_status: string;
      persisted_status: string | null;
      computed_revenue: number;
      persisted_revenue: number | null;
      status_match: boolean;
      revenue_match: boolean;
      difference: number | null;
      absolute_difference: number | null;
      tolerance: number;
      comparison: string;
      matched: boolean;
    }>;
    allocations?: Array<{
      model: ModelName;
      matched: boolean;
      difference_count: number;
      differences: Array<{
        touchpoint_id: string;
        reason: string;
        credit_fraction_delta?: number;
        attributed_revenue_delta?: number;
        recomputed_revenue?: number;
        persisted_revenue?: number;
      }>;
      tolerance: { attributed_revenue: number; credit_fraction: number };
      basis: string;
      comparison: string;
      recomputed_allocations: number;
      persisted_allocations: number;
      compared_touchpoints: number;
    }>;
    allocations_consistent?: boolean;
    tolerance?: number;
    comparison_basis?: string;
    scope?: string;
    population?: {
      order_id: string;
      conversion_revenue: number;
      eligible_touchpoints: number;
      candidate_touchpoints: number;
    };
  };
  touchpoints: JourneyTouch[];
  message?: string;
}

export interface RunManifest {
  run_id: string;
  profile: string;
  seed: number;
  generated_at: string;
  status: string;
  combined_hash: string;
  counts: Record<string, number>;
  attribution: {
    attributed_revenue: string;
    conversions: number;
    unattributed_conversions: number;
    eligibility_rate_pct?: string;
  };
  validation: {
    overall_status: string;
    totals: ValidationTotals;
  };
  evaluation: { totals: EvaluationTotals; status: string };
  versions?: Record<string, string>;
  config?: Record<string, unknown>;
}

export interface RunIndexEntry {
  run_id: string;
  profile: string;
  seed: number;
  generated_at: string;
  status: string;
  combined_hash: string;
  touchpoints?: number;
  campaigns?: number;
  contacts?: number;
  opportunities?: number;
  issues?: number;
  attributed_revenue?: string;
  counts?: Record<string, number>;
}

export interface RunsResponse {
  active_run_id: string | null;
  runs: RunIndexEntry[];
}

export interface VerifyJob {
  job_id: string;
  status: "RUNNING" | "REPRODUCIBLE" | "NOT_REPRODUCIBLE" | "FAILED";
  profile: string;
  seed: number;
  started_at: string;
  finished_at: string | null;
  note: string;
  error: string | null;
  result: {
    reproducible: boolean;
    left_run: string;
    right_run: string;
    left_combined_hash: string;
    right_combined_hash: string;
    differences: Array<{
      table: string;
      left_sha256: string | null;
      right_sha256: string | null;
      left_rows: number | null;
      right_rows: number | null;
    }>;
    excluded_nondeterministic_columns: Record<string, string[]>;
  } | null;
}

export interface HealthResponse {
  status: string;
  service: string;
  dataset: {
    run_id: string;
    profile: string;
    seed: number;
    generated_at: string;
    status: string;
  } | null;
}

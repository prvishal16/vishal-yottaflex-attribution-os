import type {
  CampaignDetailResponse,
  CampaignListResponse,
  ChannelListResponse,
  CompareResponse,
  EvaluationResponse,
  ExceptionDetailResponse,
  ExceptionListResponse,
  HealthResponse,
  JourneyResponse,
  ModelName,
  RunManifest,
  RunsResponse,
  SummaryResponse,
  ValidationResponse,
  VerifyJob,
} from "../types/api";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type QueryValue = string | number | boolean | null | undefined;

export type ExportFileFormat = "csv" | "json" | "xlsx" | "pdf";
export type RunExportFileFormat = ExportFileFormat | "sql" | "zip";

function withRun(path: string, runId: string | null, params: Record<string, QueryValue> = {}) {
  const search = new URLSearchParams();
  if (runId) search.set("run_id", runId);
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return `${API_BASE}${path}${query ? `?${query}` : ""}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("The analytics API is unreachable. Start it with `yottaflex serve`.", 0);
  }
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the fallback message for non-JSON error bodies.
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>(`${API_BASE}/api/health`),
  summary: (runId: string | null) => request<SummaryResponse>(withRun("/api/summary", runId)),

  campaigns: (
    runId: string | null,
    options: {
      model?: ModelName;
      limit?: number;
      offset?: number;
      sort?: string;
      order?: "asc" | "desc";
      channelId?: string | null;
      search?: string;
      coverage?: string;
      minRevenue?: number | null;
    } = {},
  ) =>
    request<CampaignListResponse>(
      withRun("/api/campaigns", runId, {
        model: options.model ?? "linear",
        limit: options.limit ?? 25,
        offset: options.offset ?? 0,
        sort: options.sort ?? "attributed_revenue",
        order: options.order ?? "desc",
        channel_id: options.channelId,
        search: options.search,
        coverage: options.coverage,
        min_revenue: options.minRevenue,
      }),
    ),

  campaign: (campaignId: string, model: ModelName, runId: string | null) =>
    request<CampaignDetailResponse>(
      withRun(`/api/campaigns/${encodeURIComponent(campaignId)}`, runId, { model }),
    ),

  channels: (model: ModelName, runId: string | null) =>
    request<ChannelListResponse>(withRun("/api/channels", runId, { model })),

  compare: (modelA: ModelName, modelB: ModelName, runId: string | null, limit = 15) =>
    request<CompareResponse>(
      withRun("/api/attribution/compare", runId, {
        model_a: modelA,
        model_b: modelB,
        limit,
      }),
    ),

  journey: (reference: string, runId: string | null) =>
    request<JourneyResponse>(
      withRun(`/api/journeys/${encodeURIComponent(reference)}`, runId),
    ),

  sampleJourney: (runId: string | null) =>
    request<JourneyResponse>(withRun("/api/demo/journey", runId)),

  exceptions: (
    runId: string | null,
    options: {
      severity?: string;
      issueType?: string;
      split?: string;
      status?: string;
      search?: string;
      limit?: number;
      offset?: number;
    } = {},
  ) =>
    request<ExceptionListResponse>(
      withRun("/api/exceptions", runId, {
        severity: options.severity,
        issue_type: options.issueType,
        split: options.split,
        status: options.status,
        search: options.search,
        limit: options.limit ?? 50,
        offset: options.offset ?? 0,
      }),
    ),

  exception: (issueId: string, runId: string | null) =>
    request<ExceptionDetailResponse>(
      withRun(`/api/exceptions/${encodeURIComponent(issueId)}`, runId),
    ),

  validation: (
    runId: string | null,
    status?: string,
    category?: string,
    search?: string,
  ) =>
    request<ValidationResponse>(
      withRun("/api/validation/report", runId, { status, category, search }),
    ),

  evaluation: (runId: string | null) =>
    request<EvaluationResponse>(withRun("/api/evaluation", runId)),

  runs: () => request<RunsResponse>(`${API_BASE}/api/runs`),

  run: (runId: string) =>
    request<RunManifest>(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`),

  generate: (profile: string, seed: number, strictValidation: boolean) =>
    request<RunManifest>(`${API_BASE}/api/runs/generate`, {
      method: "POST",
      body: JSON.stringify({
        profile,
        seed,
        strict_validation: strictValidation,
      }),
    }),

  validate: (runId: string | null, strict = false) =>
    request<ValidationResponse>(`${API_BASE}/api/runs/validate`, {
      method: "POST",
      body: JSON.stringify({ run_id: runId, strict }),
    }),

  startVerify: (profile: string, seed: number) =>
    request<VerifyJob>(`${API_BASE}/api/runs/verify`, {
      method: "POST",
      body: JSON.stringify({ profile, seed }),
    }),

  verifyJob: (jobId: string) =>
    request<VerifyJob>(`${API_BASE}/api/runs/verify/${encodeURIComponent(jobId)}`),

  campaignExportUrl: (
    runId: string | null,
    options: {
      model?: ModelName;
      sort?: string;
      order?: "asc" | "desc";
      channelId?: string | null;
      search?: string;
      coverage?: string;
      minRevenue?: number | null;
    } = {},
  ) =>
    withRun("/api/campaigns/export", runId, {
      model: options.model ?? "linear",
      sort: options.sort ?? "attributed_revenue",
      order: options.order ?? "desc",
      channel_id: options.channelId,
      search: options.search,
      coverage: options.coverage,
      min_revenue: options.minRevenue,
    }),

  exportUrl: (dataset: string, runId: string | null) => {
    const search = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
    return `${API_BASE}/api/exports/${encodeURIComponent(dataset)}${search}`;
  },

  campaignPerformanceExportUrl: (
    runId: string | null,
    format: ExportFileFormat,
    options: {
      model?: ModelName;
      sort?: string;
      order?: "asc" | "desc";
      channelId?: string | null;
      search?: string;
      coverage?: string;
      minRevenue?: number | null;
    } = {},
  ) =>
    withRun("/api/exports/campaign-performance", runId, {
      format,
      model: options.model ?? "linear",
      sort: options.sort ?? "attributed_revenue",
      order: options.order ?? "desc",
      channel_id: options.channelId,
      search: options.search,
      coverage: options.coverage,
      min_revenue: options.minRevenue,
    }),

  overviewExportUrl: (runId: string | null, format: ExportFileFormat) =>
    withRun("/api/exports/overview", runId, { format }),

  campaignReportExportUrl: (
    campaignId: string,
    model: ModelName,
    runId: string | null,
    format: ExportFileFormat,
  ) =>
    withRun(`/api/exports/campaign/${encodeURIComponent(campaignId)}`, runId, {
      format,
      model,
    }),

  costRecordsExportUrl: (
    campaignId: string,
    runId: string | null,
    format: ExportFileFormat = "csv",
  ) =>
    withRun("/api/exports/cost-records", runId, {
      format,
      campaign_id: campaignId,
    }),

  exceptionsExportUrl: (
    runId: string | null,
    format: ExportFileFormat,
    options: {
      severity?: string;
      issueType?: string;
      split?: string;
      status?: string;
      search?: string;
    } = {},
  ) =>
    withRun("/api/exports/exceptions", runId, {
      format,
      severity: options.severity,
      issue_type: options.issueType,
      split: options.split,
      status: options.status,
      search: options.search,
    }),

  validationExportUrl: (
    runId: string | null,
    format: ExportFileFormat,
    options: { status?: string; category?: string; search?: string } = {},
  ) =>
    withRun("/api/exports/validation", runId, {
      format,
      status: options.status,
      category: options.category,
      search: options.search,
    }),

  evaluationExportUrl: (runId: string | null, format: ExportFileFormat) =>
    withRun("/api/exports/evaluation", runId, { format }),

  evidenceExportUrl: (
    issueId: string,
    runId: string | null,
    format: ExportFileFormat,
  ) =>
    withRun(`/api/exports/evidence/${encodeURIComponent(issueId)}`, runId, {
      format,
    }),

  journeyExportUrl: (
    reference: string,
    runId: string | null,
    format: ExportFileFormat,
  ) =>
    withRun(`/api/exports/journey/${encodeURIComponent(reference)}`, runId, {
      format,
    }),

  runExportUrl: (runId: string, format: RunExportFileFormat) => {
    const search = new URLSearchParams({ format });
    return `${API_BASE}/api/exports/run/${encodeURIComponent(runId)}?${search.toString()}`;
  },
};

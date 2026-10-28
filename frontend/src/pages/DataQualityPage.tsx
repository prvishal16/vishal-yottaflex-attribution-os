import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ClipboardCheck,
  Fingerprint,
  Gauge,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { SeverityBadge, SplitBadge, ValidationBadge } from "../components/Badges";
import { ExportMenu, formatOptions } from "../components/ExportMenu";
import {
  Badge,
  Button,
  CopyButton,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pager,
  ProgressBar,
  SectionCard,
  SegmentedControl,
  StatCard,
} from "../components/Primitives";
import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../hooks/useRunContext";
import type {
  EvaluationResponse,
  ExceptionDetailResponse,
  ExceptionItem,
  ValidationCheck,
  ValidationResponse,
  ValidationSummary,
} from "../types/api";
import {
  classNames,
  formatDateTime,
  formatNumber,
  formatPercent,
  humanize,
  issueLabel,
  splitLabel,
} from "../utils/format";

type QualityTab = "queue" | "validation" | "evaluation";
type CheckStatus = "" | "WARNING" | "FAIL";

const CHECK_PAGE_SIZE = 18;

export function DataQualityPage() {
  const { effectiveRunId, refreshRuns } = useRunContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<QualityTab>("queue");
  const [severity, setSeverity] = useState("");
  const [issueType, setIssueType] = useState("");
  const [split, setSplit] = useState("");
  const [search, setSearch] = useState("");
  const [selectedIssue, setSelectedIssue] = useState<string | null>(
    () => searchParams.get("issue"),
  );
  const [checkStatus, setCheckStatus] = useState<CheckStatus>("");
  const [checkCategory, setCheckCategory] = useState("");
  const [checkSearch, setCheckSearch] = useState("");
  const [checkPage, setCheckPage] = useState(1);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);

  const exceptions = useAsync(
    () =>
      api.exceptions(effectiveRunId, {
        severity: severity || undefined,
        issueType: issueType || undefined,
        split: split || undefined,
        search: search || undefined,
        limit: 100,
      }),
    [effectiveRunId, severity, issueType, split, search],
    { enabled: Boolean(effectiveRunId) },
  );
  const validation = useAsync(
    () => api.validation(effectiveRunId),
    [effectiveRunId],
    { enabled: Boolean(effectiveRunId) },
  );
  const evaluation = useAsync(
    () => api.evaluation(effectiveRunId),
    [effectiveRunId],
    { enabled: Boolean(effectiveRunId) },
  );
  const detail = useAsync(
    () => api.exception(selectedIssue ?? "", effectiveRunId),
    [selectedIssue, effectiveRunId],
    { enabled: Boolean(selectedIssue && effectiveRunId) },
  );

  const items = exceptions.data?.items ?? [];
  useEffect(() => {
    if (!selectedIssue && items.length) setSelectedIssue(items[0].issue_id);
  }, [items, selectedIssue]);

  useEffect(() => {
    setCheckPage(1);
  }, [checkStatus, checkCategory, checkSearch]);

  function chooseIssue(item: ExceptionItem) {
    setSelectedIssue(item.issue_id);
    setSearchParams({ issue: item.issue_id }, { replace: true });
  }

  async function refreshValidation() {
    setRefreshing(true);
    setRefreshMessage(null);
    try {
      await api.validate(effectiveRunId);
      validation.reload();
      await refreshRuns();
      setRefreshMessage("Validation re-ran with the current analytical views.");
    } catch (reason) {
      setRefreshMessage(reason instanceof Error ? reason.message : "Validation failed.");
    } finally {
      setRefreshing(false);
    }
  }

  const exceptionsTotal = exceptions.data?.total ?? 0;
  const highSeverity =
    exceptions.data?.facets.severity?.find((facet) => facet.value === "HIGH")?.count ?? 0;
  const validationWarnings = validation.data?.summary.totals.warnings ?? 0;
  const f1 = evaluation.data?.totals.f1_pct ?? "—";

  const checks = validation.data?.checks ?? [];
  const categories = validation.data?.summary.categories ?? {};
  const filteredChecks = useMemo(() => {
    const needle = checkSearch.trim().toLowerCase();
    return checks.filter((check) => {
      if (checkStatus && check.status !== checkStatus) return false;
      if (checkCategory && check.category !== checkCategory) return false;
      if (
        needle &&
        !`${check.check_id} ${check.rule_id} ${check.description} ${check.message}`
          .toLowerCase()
          .includes(needle)
      ) {
        return false;
      }
      return true;
    });
  }, [checks, checkStatus, checkCategory, checkSearch]);
  const visibleChecks = filteredChecks.slice(
    (checkPage - 1) * CHECK_PAGE_SIZE,
    checkPage * CHECK_PAGE_SIZE,
  );

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Trust layer"
        title="Trust nothing until it reconciles."
        description="Inspect the exception queue, the validation contract, and held-out detection performance without confusing a deliberate fixture for an undetected failure."
        meta={
          <>
            <ValidationBadge status={validation.data?.summary.overall_status} />
            <span>Ground truth isolated from detection</span>
            <span>Deterministic rule set</span>
          </>
        }
        actions={
          <>
            <ExportMenu
              options={formatOptions(
                (format) =>
                  api.exceptionsExportUrl(effectiveRunId, format, {
                    severity: severity || undefined,
                    issueType: issueType || undefined,
                    split: split || undefined,
                    search: search || undefined,
                  }),
                {
                  csv: "Every matching exception, not only the visible page.",
                  json: "Issues plus severity, type and split summaries with run context.",
                  xlsx: "Summary, full issue list and breakdowns.",
                  pdf: "Printable issue list with detection rules and explanations.",
                },
              )}
              rowCount={exceptionsTotal}
              note="No ground-truth labels"
            />
            <Button
              variant="primary"
              size="md"
              icon={RefreshCw}
              onClick={() => void refreshValidation()}
              disabled={refreshing}
            >
              {refreshing ? "Re-running…" : "Re-run validation"}
            </Button>
          </>
        }
      />

      {refreshMessage ? (
        <div className="inline-alert inline-alert--info">
          <ClipboardCheck size={17} />
          <div>
            <strong>Validation action complete</strong>
            <span>{refreshMessage}</span>
          </div>
        </div>
      ) : null}

      <section className="stat-grid stat-grid--compact">
        <StatCard
          label="Detected exceptions"
          value={formatNumber(exceptionsTotal)}
          detail="All deliberate fixture types"
          accent="amber"
          icon={ShieldAlert}
        />
        <StatCard
          label="High severity"
          value={formatNumber(highSeverity)}
          detail="Duplicate revenue, missing cost, identity"
          accent="rose"
          icon={AlertTriangle}
        />
        <StatCard
          label="Detection F1"
          value={`${f1}%`}
          detail={`${evaluation.data?.totals.true_positives ?? "—"} of ${evaluation.data?.totals.ground_truth ?? "—"} fixtures matched`}
          accent="lime"
          icon={Gauge}
        />
        <StatCard
          label="Validation warnings"
          value={formatNumber(validationWarnings)}
          detail={`${validation.data?.summary.totals.failures ?? "—"} failures · ${validation.data?.summary.totals.checks ?? "—"} checks`}
          accent="cyan"
          icon={ShieldCheck}
        />
      </section>

      <div className="quality-tabs">
        <SegmentedControl
          label="Data-quality view"
          value={tab}
          onChange={setTab}
          options={[
            { value: "queue", label: "Exception queue" },
            { value: "validation", label: "Validation contract" },
            { value: "evaluation", label: "Detection evaluation" },
          ]}
        />
        <span className="quality-tabs__hint">
          {tab === "queue"
            ? "Fixtures are intentionally present; dispositions explain the correct treatment."
            : tab === "validation"
              ? "Warnings correspond to labelled anomalies; failures would block the run."
              : "Labels are scored after detection and are never read by the detector."}
        </span>
      </div>

      {tab === "queue" ? (
        <>
          <SectionCard className="filter-panel" flush>
            <div className="filter-bar filter-bar--quality">
              <label className="search-field">
                <Search size={15} />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search issue, entity or explanation"
                  aria-label="Search exceptions"
                />
              </label>
              <label className="select-field">
                <select
                  value={severity}
                  onChange={(event) => setSeverity(event.target.value)}
                  aria-label="Filter by severity"
                >
                  <option value="">Any severity</option>
                  {exceptions.data?.facets.severity?.map((facet) => (
                    <option key={facet.value} value={facet.value}>
                      {humanize(facet.value)} ({facet.count})
                    </option>
                  ))}
                </select>
              </label>
              <label className="select-field">
                <select
                  value={issueType}
                  onChange={(event) => setIssueType(event.target.value)}
                  aria-label="Filter by issue type"
                >
                  <option value="">All issue types</option>
                  {exceptions.data?.facets.issue_type?.map((facet) => (
                    <option key={facet.value} value={facet.value}>
                      {issueLabel(facet.value)} ({facet.count})
                    </option>
                  ))}
                </select>
              </label>
              <label className="select-field">
                <select
                  value={split}
                  onChange={(event) => setSplit(event.target.value)}
                  aria-label="Filter by data split"
                >
                  <option value="">All splits</option>
                  <option value="train">Train</option>
                  <option value="validation">Validation</option>
                  <option value="test">Test</option>
                </select>
              </label>
              <span className="filter-count">
                {formatNumber(exceptionsTotal)} result{exceptionsTotal === 1 ? "" : "s"}
              </span>
            </div>
          </SectionCard>

          <div className="quality-layout">
            <SectionCard
              title="Exception queue"
              description="Ranked by severity, then rule. Select an issue to inspect evidence."
              className="queue-panel"
              flush
            >
              {exceptions.error ? (
                <div className="panel-pad">
                  <ErrorState
                    compact
                    message={exceptions.error.message}
                    onRetry={exceptions.reload}
                  />
                </div>
              ) : exceptions.loading && !exceptions.data ? (
                <div className="panel-pad">
                  <LoadingState rows={6} />
                </div>
              ) : items.length === 0 ? (
                <EmptyState
                  icon={ShieldCheck}
                  title="No exceptions match"
                  description="Broaden the filters to inspect the labelled fixture set."
                />
              ) : (
                <div className="queue-list">
                  {items.map((item) => (
                    <button
                      type="button"
                      key={item.issue_id}
                      className={classNames(
                        "queue-item",
                        selectedIssue === item.issue_id && "is-active",
                      )}
                      onClick={() => chooseIssue(item)}
                    >
                      <div className="queue-item__top">
                        <SeverityBadge severity={item.severity} />
                        <span className="queue-item__type">{issueLabel(item.issue_type)}</span>
                        <code>{item.issue_id}</code>
                      </div>
                      <p>{item.explanation}</p>
                      <div className="queue-item__meta">
                        <span>{item.primary_entity_id}</span>
                        <SplitBadge split={item.split} />
                        <span>{item.detection_rule_id}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </SectionCard>

            <SectionCard
              className="issue-detail-panel"
              title="Evidence packet"
              description={
                detail.data
                  ? `${detail.data.issue_id} · detected ${formatDateTime(detail.data.detected_at)}`
                  : "Select an exception to inspect its detection evidence."
              }
              actions={
                detail.data ? (
                  <Badge tone={detail.data.status === "OPEN" ? "warning" : "neutral"}>
                    {detail.data.status.toLowerCase()}
                  </Badge>
                ) : undefined
              }
            >
              {detail.error ? (
                <ErrorState compact message={detail.error.message} onRetry={detail.reload} />
              ) : detail.loading && !detail.data ? (
                <LoadingState rows={6} />
              ) : detail.data ? (
                <IssueDetail data={detail.data} runId={effectiveRunId} />
              ) : (
                <EmptyState
                  icon={ShieldQuestion}
                  title="Awaiting selection"
                  description="Choose an exception from the queue."
                />
              )}
            </SectionCard>
          </div>
        </>
      ) : null}

      {tab === "validation" ? (
        <ValidationTab
          runId={effectiveRunId}
          data={validation.data}
          loading={validation.loading}
          error={validation.error}
          onRetry={validation.reload}
          checks={visibleChecks}
          filteredTotal={filteredChecks.length}
          totalChecks={checks.length}
          checkPage={checkPage}
          setCheckPage={setCheckPage}
          checkStatus={checkStatus}
          setCheckStatus={setCheckStatus}
          checkCategory={checkCategory}
          setCheckCategory={setCheckCategory}
          checkSearch={checkSearch}
          setCheckSearch={setCheckSearch}
          categories={categories}
        />
      ) : null}

      {tab === "evaluation" ? (
        <EvaluationTab
          runId={effectiveRunId}
          data={evaluation.data}
          loading={evaluation.loading}
          error={evaluation.error}
          onRetry={evaluation.reload}
        />
      ) : null}
    </div>
  );
}

function IssueDetail({
  data,
  runId,
}: {
  data: ExceptionDetailResponse;
  runId: string | null;
}) {
  const relatedRecords = data.related.records ?? [];
  return (
    <div className="issue-detail">
      <div className="issue-detail__head">
        <SeverityBadge severity={data.severity} />
        <Badge tone="neutral">{issueLabel(data.issue_type)}</Badge>
        <SplitBadge split={data.split} />
      </div>

      <p className="issue-detail__explanation">{data.explanation}</p>

      <div className="disposition-box">
        <span className="eyebrow">Suggested disposition</span>
        <p>{data.suggested_disposition}</p>
        <span className="disposition-box__note">
          Advisory only. Source records are preserved; financial totals apply the treatment in the
          pipeline.
        </span>
      </div>

      <dl className="definition-grid">
        <div>
          <dt>Entity type</dt>
          <dd>{humanize(data.entity_type)}</dd>
        </div>
        <div>
          <dt>Primary entity</dt>
          <dd>
            {data.related.campaign ? (
              <Link to={`/campaigns/${data.related.campaign.campaign_id}`}>
                {data.related.campaign.campaign_name} <ArrowUpRight size={11} />
              </Link>
            ) : (
              <span className="mono">{data.primary_entity_id}</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Detection rule</dt>
          <dd className="mono">{data.detection_rule_id}</dd>
        </div>
        <div>
          <dt>Affected records</dt>
          <dd className="mono wrap">{data.affected_record_ids || "?"}</dd>
        </div>
      </dl>

      <div className="evidence-block">
        <div className="evidence-block__head">
          <Fingerprint size={14} />
          <span>Evidence</span>
          <div className="evidence-block__actions">
            <CopyButton value={JSON.stringify(data.evidence, null, 2)} label="Copy JSON" />
            <ExportMenu
              buttonLabel="Download packet"
              size="sm"
              variant="ghost"
              options={formatOptions(
                (format) => api.evidenceExportUrl(data.issue_id, runId, format),
                {
                  csv: "Evidence fields, packet metadata and disposition state.",
                  json: "Full packet including evidence and related records.",
                  xlsx: "Evidence, packet and related-record sheets.",
                  pdf: "Printable investigation packet.",
                },
              )}
              note="No ground-truth labels"
            />
          </div>
        </div>
        <dl className="evidence-grid">
          {Object.entries(data.evidence).map(([key, value]) => (
            <div key={key}>
              <dt>{humanize(key)}</dt>
              <dd>{formatEvidence(value)}</dd>
            </div>
          ))}
        </dl>
      </div>

      {relatedRecords.length ? (
        <div className="related-block">
          <span className="eyebrow">Related records</span>
          <div className="related-list">
            {relatedRecords.map((record, index) => (
              <RelatedRecord record={record} key={String(record.order_id ?? record.touchpoint_id ?? record.link_id ?? record.session_id ?? index)} />
            ))}
          </div>
        </div>
      ) : null}

      <div className="issue-detail__footer">
        <Badge tone="neutral">{data.issue_id}</Badge>
        <span>Detected {formatDateTime(data.detected_at)}</span>
      </div>
    </div>
  );
}

function RelatedRecord({ record }: { record: Record<string, unknown> }) {
  const type = String(record.type ?? "RECORD");
  const identifier =
    record.order_id ??
    record.touchpoint_id ??
    record.link_id ??
    record.session_id ??
    record.record_id ??
    "?";
  return (
    <div className="related-record">
      <div className="related-record__head">
        <Badge tone="info">{humanize(type)}</Badge>
        {type === "ORDER" && typeof record.order_id === "string" ? (
          <Link to={`/journeys`} className="mono">
            {record.order_id}
          </Link>
        ) : (
          <code>{String(identifier)}</code>
        )}
      </div>
      <div className="related-record__fields">
        {Object.entries(record)
          .filter(([key]) => key !== "type" && !["order_id", "touchpoint_id", "link_id", "session_id"].includes(key))
          .slice(0, 6)
          .map(([key, value]) => (
            <div key={key}>
              <span>{humanize(key)}</span>
              <strong>{formatEvidence(value)}</strong>
            </div>
          ))}
      </div>
    </div>
  );
}

function formatEvidence(value: unknown): string {
  if (value === null || value === undefined || value === "") return "?";
  if (Array.isArray(value)) return value.map((item) => formatEvidence(item)).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

interface ValidationTabProps {
  runId: string | null;
  data: ValidationResponse | null;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
  checks: ValidationCheck[];
  filteredTotal: number;
  totalChecks: number;
  checkPage: number;
  setCheckPage: (page: number) => void;
  checkStatus: CheckStatus;
  setCheckStatus: (status: CheckStatus) => void;
  checkCategory: string;
  setCheckCategory: (category: string) => void;
  checkSearch: string;
  setCheckSearch: (search: string) => void;
  categories: ValidationSummary["categories"];
}

function ValidationTab({
  runId,
  data,
  loading,
  error,
  onRetry,
  checks,
  filteredTotal,
  totalChecks,
  checkPage,
  setCheckPage,
  checkStatus,
  setCheckStatus,
  checkCategory,
  setCheckCategory,
  checkSearch,
  setCheckSearch,
  categories,
}: ValidationTabProps) {
  if (error) {
    return <ErrorState message={error.message} onRetry={onRetry} />;
  }
  if (loading && !data) {
    return <LoadingState rows={8} />;
  }
  if (!data) return null;
  const summary = data.summary;
  return (
    <div className="validation-tab">
      <div className="validation-hero">
        <div className="validation-hero__status">
          {summary.overall_status === "PASS" ? (
            <CheckCircle2 size={22} />
          ) : summary.overall_status === "PASS_WITH_WARNINGS" ? (
            <AlertTriangle size={22} />
          ) : (
            <XCircle size={22} />
          )}
          <div>
            <span className="eyebrow">Overall contract status</span>
            <strong>{summary.overall_status.replaceAll("_", " ")}</strong>
            <span>
              {summary.totals.checks} checks ? {summary.totals.passed} passed ?{" "}
              {summary.totals.warnings} warnings ? {summary.totals.failures} failures
            </span>
          </div>
        </div>
        <div className="validation-hero__meta">
          <span>{summary.mode} mode</span>
          <span>{summary.rule_version}</span>
          <span>{formatDateTime(summary.generated_at)}</span>
        </div>
      </div>

      <div className="validation-categories">
        {Object.entries(categories).map(([name, category]) => {
          const passed = category.passed + category.warnings;
          return (
            <article className="validation-category" key={name}>
              <div className="validation-category__head">
                <strong>{humanize(name)}</strong>
                <span>{category.checks} checks</span>
              </div>
              <div className="validation-category__values">
                <span className="value--positive">{category.passed} pass</span>
                {category.warnings > 0 ? (
                  <span className="value--warning">{category.warnings} warn</span>
                ) : null}
                {category.failures > 0 ? (
                  <span className="value--negative">{category.failures} fail</span>
                ) : null}
              </div>
              <ProgressBar
                value={(passed / category.checks) * 100}
                tone={category.failures ? "rose" : category.warnings ? "amber" : "lime"}
                label={`${name} pass rate`}
              />
            </article>
          );
        })}
      </div>

      {summary.warning_details.length ? (
        <div className="warning-list">
          <div className="warning-list__head">
            <AlertTriangle size={15} />
            <strong>Expected warnings</strong>
            <span>Each maps to an intentional fixture or duplicate-source condition.</span>
          </div>
          {summary.warning_details.map((warning) => (
            <div className="warning-row" key={warning.rule_id}>
              <code>{warning.rule_id}</code>
              <span>{warning.message}</span>
              <Badge tone="warning">{warning.failure_count}</Badge>
            </div>
          ))}
        </div>
      ) : null}

      <SectionCard
        title="All validation checks"
        description={`${filteredTotal} of ${totalChecks} checks match the current filter.`}
        actions={
          <>
            <ExportMenu
              buttonLabel="Export checks"
              size="sm"
              variant="ghost"
              options={formatOptions(
                (format) =>
                  api.validationExportUrl(runId, format, {
                    status: checkStatus || undefined,
                    category: checkCategory || undefined,
                    search: checkSearch || undefined,
                  }),
                {
                  csv: "Every matching check with rule, status and message.",
                  json: "Checks plus category and warning summaries.",
                  xlsx: "Summary, checks, categories and warnings.",
                  pdf: "Printable validation contract.",
                },
              )}
              rowCount={filteredTotal}
            />
            <Badge tone="neutral">{summary.attribution_checks_included ? "Attribution included" : "Pre-attribution"}</Badge>
          </>
        }
        flush
      >
        <div className="validation-filters">
          <SegmentedControl
            label="Check status"
            value={checkStatus || "ALL"}
            onChange={(value) => setCheckStatus(value === "ALL" ? "" : (value as CheckStatus))}
            options={[
              { value: "ALL" as const, label: "All" },
              { value: "WARNING", label: "Warnings" },
              { value: "FAIL", label: "Failures" },
            ]}
          />
          <label className="select-field">
            <select
              value={checkCategory}
              onChange={(event) => setCheckCategory(event.target.value)}
              aria-label="Filter by validation category"
            >
              <option value="">All categories</option>
              {Object.keys(categories).map((name) => (
                <option key={name} value={name}>{humanize(name)}</option>
              ))}
            </select>
          </label>
          <label className="search-field">
            <Search size={15} />
            <input
              value={checkSearch}
              onChange={(event) => setCheckSearch(event.target.value)}
              placeholder="Search rule or description"
              aria-label="Search validation checks"
            />
          </label>
        </div>

        {checks.length ? (
          <>
            <div className="table-wrap">
              <table className="data-table data-table--checks">
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Category</th>
                    <th>Status</th>
                    <th className="is-numeric">Records</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {checks.map((check) => (
                    <tr key={check.check_id}>
                      <td>
                        <div className="check-cell">
                          <code>{check.check_id}</code>
                          <span>{check.description}</span>
                          <small>{check.rule_id}</small>
                        </div>
                      </td>
                      <td><Badge tone="neutral">{humanize(check.category)}</Badge></td>
                      <td>
                        <Badge
                          tone={
                            check.status === "PASS"
                              ? "positive"
                              : check.status === "WARNING"
                                ? "warning"
                                : "danger"
                          }
                          dot
                        >
                          {check.status.toLowerCase()}
                        </Badge>
                      </td>
                      <td className="is-numeric">{formatNumber(check.records_examined)}</td>
                      <td className="message-cell">{check.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              page={checkPage}
              pageSize={CHECK_PAGE_SIZE}
              total={filteredTotal}
              onChange={setCheckPage}
            />
          </>
        ) : (
          <EmptyState
            icon={ShieldCheck}
            title="No checks match"
            description="Clear the status, category or search filter."
          />
        )}
      </SectionCard>
    </div>
  );
}

function EvaluationTab({
  runId,
  data,
  loading,
  error,
  onRetry,
}: {
  runId: string | null;
  data: EvaluationResponse | null;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  if (error) return <ErrorState message={error.message} onRetry={onRetry} />;
  if (loading && !data) return <LoadingState rows={8} />;
  if (!data) return null;
  return (
    <div className="evaluation-tab">
      <div className="evaluation-banner">
        <ShieldCheck size={20} />
        <div>
          <strong>Detection is scored after the fact.</strong>
          <span>
            This run uses {data.totals.ground_truth} labelled synthetic fixtures. Ground-truth
            labels live outside the run directory and are only read by the evaluator; the detector
            uses record-level evidence and deterministic rules.
          </span>
        </div>
        <div className="evaluation-banner__aside">
          <Badge tone="positive" dot>{data.status.toLowerCase()}</Badge>
          <ExportMenu
            buttonLabel="Export artifact"
            size="sm"
            variant="ghost"
            options={formatOptions(
              (format) => api.evaluationExportUrl(runId, format),
              {
                csv: "Per-issue-type precision, recall and F1.",
                json: "Full evaluation including labelled match rows.",
                xlsx: "Metrics, split breakdown and ground-truth matches.",
                pdf: "Printable evaluation summary with a label warning.",
              },
            )}
            rowCount={data.by_type.length}
            note="Contains ground-truth labels"
          />
        </div>
      </div>

      <div className="evaluation-metrics">
        <EvaluationMetric label="Precision" value={data.totals.precision_pct} detail={`${data.totals.true_positives} of ${data.totals.detected} detections`} />
        <EvaluationMetric label="Recall" value={data.totals.recall_pct} detail={`${data.totals.true_positives} of ${data.totals.ground_truth} labels`} />
        <EvaluationMetric label="F1 score" value={data.totals.f1_pct} detail={`${data.totals.true_positives} of ${data.totals.ground_truth} labels matched`} />
        <EvaluationMetric label="Severity accuracy" value={data.totals.severity_accuracy_pct} detail="Expected vs detected" />
      </div>

      <div className="evaluation-grid">
        <SectionCard title="Performance by issue type" description={`${data.by_type.length} issue types across ${data.totals.ground_truth} synthetic labels.`} flush>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Issue type</th>
                  <th className="is-numeric">Labels</th>
                  <th className="is-numeric">TP</th>
                  <th className="is-numeric">FP</th>
                  <th className="is-numeric">FN</th>
                  <th className="is-numeric">F1</th>
                </tr>
              </thead>
              <tbody>
                {data.by_type.map((row) => (
                  <tr key={row.issue_type}>
                    <td>{issueLabel(row.issue_type)}</td>
                    <td className="is-numeric">{row.ground_truth}</td>
                    <td className="is-numeric">{row.true_positives}</td>
                    <td className="is-numeric">{row.false_positives}</td>
                    <td className="is-numeric">{row.false_negatives}</td>
                    <td className="is-numeric"><span className="value--positive">{row.f1_pct}%</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        <SectionCard title="Chronological splits" description="Labels are not concentrated in one period." flush>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Split</th>
                  <th className="is-numeric">Labels</th>
                  <th className="is-numeric">Detected</th>
                  <th className="is-numeric">Precision</th>
                  <th className="is-numeric">Recall</th>
                </tr>
              </thead>
              <tbody>
                {data.by_split.map((row) => (
                  <tr key={row.split}>
                    <td><Badge tone="neutral">{splitLabel(row.split)}</Badge></td>
                    <td className="is-numeric">{row.ground_truth}</td>
                    <td className="is-numeric">{row.detected}</td>
                    <td className="is-numeric">{formatPercent(row.precision_pct)}</td>
                    <td className="is-numeric">{formatPercent(row.recall_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Matched fixtures"
        description="One-to-one matches were established using overlapping affected record IDs."
        actions={<Badge tone="neutral">{data.matches.length} matches</Badge>}
      >
        <div className="match-list">
          {data.matches.map((match) => (
            <div className="match-row" key={match.scenario_id}>
              <div className="match-row__type">
                <Badge tone={match.expected_severity === "HIGH" ? "danger" : "warning"}>
                  {match.expected_severity.toLowerCase()}
                </Badge>
                <strong>{issueLabel(match.issue_type)}</strong>
                <span>{match.scenario_id}</span>
              </div>
              <p>{match.explanation}</p>
              <div className="match-row__meta">
                <span>{splitLabel(match.detected_split)}</span>
                <code>{match.matched_issue_id}</code>
                <span>{match.expected_record_ids}</span>
                <Badge tone={match.severity_match === true || match.severity_match === "true" ? "positive" : "danger"}>
                  severity {match.severity_match === true || match.severity_match === "true" ? "matched" : "differs"}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

function EvaluationMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="evaluation-metric">
      <span>{label}</span>
      <strong>{value}<small>%</small></strong>
      <span>{detail}</span>
    </div>
  );
}

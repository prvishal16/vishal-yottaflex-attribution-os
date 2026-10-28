import {
  ArrowUpRight,
  CircleDollarSign,
  Gauge,
  ShieldAlert,
  ShoppingCart,
  Table2,
  Target,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api/client";
import { ValidationBadge } from "../components/Badges";
import { ChartTooltip } from "../components/ChartTooltip";
import { ExportMenu, formatOptions } from "../components/ExportMenu";
import {
  Badge,
  Button,
  CopyButton,
  ErrorState,
  LoadingState,
  PageHeader,
  SectionCard,
  SegmentedControl,
  StatCard,
} from "../components/Primitives";
import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../hooks/useRunContext";
import {
  classNames,
  formatCurrency,
  formatDate,
  formatDecimal,
  formatMonth,
  formatNumber,
  formatPercent,
  formatPp,
  formatSignedCurrency,
  issueLabel,
  modelLabel,
  truncateHash,
} from "../utils/format";

export function OverviewPage() {
  const { effectiveRunId } = useRunContext();
  const [creditSort, setCreditSort] = useState<"share" | "revenue">("share");
  const [showCreditTable, setShowCreditTable] = useState(false);
  const summaryState = useAsync(
    () => api.summary(effectiveRunId),
    [effectiveRunId],
    { enabled: Boolean(effectiveRunId) },
  );
  const compareState = useAsync(
    () => api.compare("first_touch", "linear", effectiveRunId),
    [effectiveRunId],
    { enabled: Boolean(effectiveRunId) },
  );

  if (!effectiveRunId) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Executive overview"
          title="No dataset selected"
          description="Generate a synthetic dataset or select a run to open the attribution console."
          actions={
            <Link className="button button--primary button--md" to="/runs">
              Open runs <ArrowUpRight size={15} />
            </Link>
          }
        />
        <ErrorState message="No active run is available." />
      </div>
    );
  }

  if (summaryState.loading && !summaryState.data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Executive overview" title="Performance, with the receipts." />
        <LoadingState rows={6} />
      </div>
    );
  }

  if (summaryState.error || !summaryState.data) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Executive overview" title="Performance, with the receipts." />
        <ErrorState
          message={summaryState.error?.message ?? "Summary data is unavailable."}
          onRetry={summaryState.reload}
        />
      </div>
    );
  }

  const summary = summaryState.data;
  const kpis = summary.kpis;
  const compare = compareState.data;
  const validationStatus = summary.validation?.overall_status;
  const evaluation = summary.evaluation;
  const maxCampaignRevenue = Math.max(...summary.top_campaigns.map((item) => Number(item.attributed_revenue)), 1);
  const maxChannelRevenue = Math.max(
    ...summary.channel_contribution.map((item) => Number(item.attributed_revenue)),
    1,
  );
  const maxIssueCount = Math.max(...summary.anomaly_distribution.map((item) => item.count), 1);
  const revenueCoverage = Number(kpis.revenue_coverage_pct);
  const conversionCoverage = Number(kpis.conversion_coverage_pct);
  const issueTypeCount = summary.anomaly_distribution.length;
  const fixtureCount = evaluation?.totals.ground_truth ?? 0;
  const matchedFixtures = evaluation?.totals.true_positives ?? 0;
  const roiAvailable = kpis.roi_available;
  const coveredRoas = summary.financials.covered_roas;
  const roasNumerator = summary.financials.covered_roas_numerator;
  const roasDenominator = summary.financials.covered_roas_denominator;
  const dateFirst = summary.monthly[0]?.month;
  const dateLast = summary.monthly.at(-1)?.month;
  const monthlyData = summary.monthly.map((month) => ({
    ...month,
    attributed_revenue: Number(month.attributed_revenue),
    eligible_revenue: Number(month.eligible_revenue),
    spend: Number(month.spend),
  }));

  const creditChannels = (compare?.channel_changes ?? [])
    .filter((channel) => channel.share_a_pct > 0 || channel.share_b_pct > 0)
    .slice()
    .sort((left, right) =>
      creditSort === "share"
        ? Math.abs(right.share_delta_pct) - Math.abs(left.share_delta_pct)
        : Math.abs(right.delta) - Math.abs(left.delta),
    );
  const maxCreditDelta = Math.max(
    ...creditChannels.map((channel) => Math.abs(channel.share_delta_pct)),
    0.01,
  );

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Executive overview"
        title="Performance, with the receipts."
        description={
          <>
            Revenue, cost and identity signals reconciled across three attribution models. Every
            number is traceable to a persisted record.
          </>
        }
        meta={
          <>
            <Badge tone="accent" dot>
              {summary.profile} profile
            </Badge>
            <span>
              {dateFirst ? formatMonth(dateFirst) : "—"} → {dateLast ? formatMonth(dateLast) : "—"}
            </span>
            <span>{summary.lookback_days}-day lookback</span>
            <span>Reported in {summary.reporting_currency}</span>
          </>
        }
        actions={
          <>
            <ValidationBadge status={validationStatus} />
            <ExportMenu
              options={formatOptions(
                (format) => api.overviewExportUrl(effectiveRunId, format),
                {
                  csv: "Monthly attribution, eligible revenue and spend for every month.",
                  json: "KPI, monthly, channel, model and credit-movement data with run context.",
                  xlsx: "Summary plus monthly, channel, model, credit-movement, campaign and issue sheets.",
                  pdf: "Printable monthly performance with reconciliation summary.",
                },
              )}
              rowCount={summary.monthly.length}
            />
          </>
        }
      />

      <section className="stat-grid" aria-label="Key performance indicators">
        <StatCard
          label="Attributed revenue"
          value={formatCurrency(kpis.attributed_revenue)}
          detail={`${formatPercent(revenueCoverage)} of eligible revenue`}
          accent="lime"
          icon={CircleDollarSign}
        />
        <StatCard
          label="Covered ROAS"
          value={roiAvailable ? `${formatDecimal(coveredRoas, 2)}×` : "Not available"}
          detail={`${formatCurrency(roasNumerator)} attributed ÷ ${formatCurrency(roasDenominator)} covered spend`}
          accent="cyan"
          icon={Target}
        />
        <StatCard
          label="Attributed conversions"
          value={formatNumber(kpis.attributed_conversions)}
          detail={`${formatPercent(conversionCoverage)} of eligible conversions · ${kpis.unattributed_conversions} unattributed`}
          accent="violet"
          icon={ShoppingCart}
        />
        <StatCard
          label="Data-quality exceptions"
          value={formatNumber(kpis.data_quality_issues)}
          detail={`${kpis.high_severity_issues} high severity · ${matchedFixtures}/${fixtureCount} labelled fixtures matched`}
          accent="amber"
          icon={ShieldAlert}
        />
      </section>

      <div className="overview-grid overview-grid--hero">
        <SectionCard
          title="Revenue vs. qualified demand"
          description="Monthly recognized revenue, eligible revenue before identity/consent filters, and recorded media spend."
          className="overview-chart"
          actions={
            <div className="chart-legend">
              <span><i className="swatch swatch--lime" />Attributed</span>
              <span><i className="swatch swatch--cyan" />Eligible</span>
              <span><i className="swatch swatch--muted" />Spend</span>
            </div>
          }
        >
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={322}>
              <ComposedChart
                data={monthlyData}
                margin={{ top: 8, right: 4, bottom: 0, left: -14 }}
              >
                <defs>
                  <linearGradient id="attributedFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#c8ff5e" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="#c8ff5e" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="eligibleFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#5eead4" stopOpacity={0.12} />
                    <stop offset="100%" stopColor="#5eead4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="rgba(148, 163, 184, 0.09)" />
                <XAxis
                  dataKey="month"
                  tickFormatter={formatMonth}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#7f8b9d", fontSize: 11 }}
                  dy={8}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#7f8b9d", fontSize: 11 }}
                  tickFormatter={(value: number) => formatCurrency(value, { compact: true })}
                  width={58}
                />
                <Tooltip
                  cursor={{ stroke: "rgba(200, 255, 94, 0.2)", strokeWidth: 1 }}
                  content={<ChartTooltip labelRenderer={(label) => formatMonth(String(label))} />}
                />
                <Bar
                  dataKey="spend"
                  name="Recorded spend"
                  fill="rgba(148, 163, 184, 0.17)"
                  radius={[3, 3, 0, 0]}
                  maxBarSize={22}
                />
                <Area
                  type="monotone"
                  dataKey="eligible_revenue"
                  name="Eligible revenue"
                  stroke="#5eead4"
                  strokeWidth={1.6}
                  strokeDasharray="4 4"
                  fill="url(#eligibleFill)"
                />
                <Area
                  type="monotone"
                  dataKey="attributed_revenue"
                  name="Attributed revenue"
                  stroke="#c8ff5e"
                  strokeWidth={2.2}
                  fill="url(#attributedFill)"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-footnotes">
            <div>
              <span>Eligible revenue</span>
              <strong>{formatCurrency(kpis.eligible_conversion_revenue)}</strong>
            </div>
            <div>
              <span>Unattributed</span>
              <strong>{formatCurrency(kpis.unattributed_revenue)}</strong>
            </div>
            <div>
              <span>Recorded spend</span>
              <strong>{formatCurrency(kpis.recorded_spend)}</strong>
            </div>
            <div>
              <span>Covered ROI · {summary.financials.covered_campaigns}/{summary.financials.budgeted_campaigns}</span>
              <strong className={Number(kpis.roi_pct) < 0 ? "value--negative" : "value--positive"}>
                {roiAvailable ? formatPercent(kpis.roi_pct, { signed: true }) : "Not available"}
              </strong>
            </div>
          </div>
          <p className="chart-scope-note">
            Covered returns use only the {summary.financials.covered_campaigns} campaigns with
            complete cost bases; recorded spend includes all compatible cost records.
          </p>
        </SectionCard>

        <SectionCard
          title="Trust snapshot"
          description="The guardrails behind the headline numbers."
          actions={<Badge tone={validationStatus === "PASS" ? "positive" : "warning"}>{validationStatus?.replaceAll("_", " ") ?? "UNKNOWN"}</Badge>}
          className="trust-panel"
        >
          <div className="trust-score">
            <div>
              <span className="eyebrow">Detection evaluation</span>
              <strong>{matchedFixtures}/{fixtureCount}</strong>
              <span>labelled synthetic fixtures matched</span>
            </div>
            <div className="trust-score__ring" aria-label={`F1 score ${evaluation?.totals.f1_pct ?? "unavailable"} percent`}>
              <span>{evaluation?.totals.f1_pct ?? "—"}</span>
              <small>F1</small>
            </div>
          </div>

          <div className="trust-eval-metrics" aria-label="Detection metrics">
            <div>
              <span>Precision</span>
              <strong>{formatPercent(evaluation?.totals.precision_pct)}</strong>
              <small>{matchedFixtures}/{evaluation?.totals.detected ?? 0} detections</small>
            </div>
            <div>
              <span>Recall</span>
              <strong>{formatPercent(evaluation?.totals.recall_pct)}</strong>
              <small>{matchedFixtures}/{fixtureCount} labels</small>
            </div>
            <div>
              <span>F1</span>
              <strong>{formatPercent(evaluation?.totals.f1_pct)}</strong>
              <small>Harmonic mean</small>
            </div>
          </div>

          <div className="metric-list">
            <MetricRow label="Revenue coverage" value={formatPercent(revenueCoverage)} progress={revenueCoverage} />
            <MetricRow label="Conversion coverage" value={formatPercent(conversionCoverage)} progress={conversionCoverage} />
            <MetricRow label="Identity coverage" value={formatPercent(kpis.identity_coverage_pct)} progress={Number(kpis.identity_coverage_pct)} tone="cyan" />
            <MetricRow label="Complete cost coverage" value={formatPercent(kpis.cost_coverage_pct)} progress={Number(kpis.cost_coverage_pct)} tone="violet" />
          </div>

          <div className="trust-callout">
            <ShieldAlert size={16} />
            <div>
              <strong>{kpis.data_quality_issues} detected exceptions remain open</strong>
              <span>
                {summary.validation?.totals.warnings ?? 0} intentional validation warnings ·{" "}
                {summary.validation?.totals.failures ?? 0} failures
              </span>
            </div>
            <Link to="/data-quality">Review</Link>
          </div>

          <div className="hash-line">
            <span>Manifest</span>
            <code>{truncateHash(summary.run.combined_hash, 18)}</code>
            <CopyButton value={summary.run.combined_hash} />
          </div>
        </SectionCard>
      </div>

      <div className="overview-grid overview-grid--split">
        <SectionCard
          title="Where credit moves"
          description="Channel revenue share under first-touch vs. linear credit. Totals reconcile; the shape of the story does not."
          actions={
            compareState.loading ? (
              <span className="muted">Computing…</span>
            ) : (
              <div className="credit-chart__controls">
                <SegmentedControl
                  label="Sort channels by"
                  value={creditSort}
                  onChange={setCreditSort}
                  options={[
                    { value: "share", label: "Share shift" },
                    { value: "revenue", label: "Revenue shift" },
                  ]}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  icon={Table2}
                  onClick={() => setShowCreditTable((current) => !current)}
                  aria-pressed={showCreditTable}
                >
                  {showCreditTable ? "Hide table" : "Table view"}
                </Button>
                <div className="model-legend">
                  <span><i className="swatch swatch--cyan" />First touch</span>
                  <span><i className="swatch swatch--lime" />Linear</span>
                </div>
              </div>
            )
          }
        >
          {compare ? (
            <div className="diverging-chart">
              <div className="diverging-chart__head">
                <span>Channel</span>
                <span className="diverging-chart__axis-label">
                  First touch <span aria-hidden="true">←</span> 0 pp baseline{" "}
                  <span aria-hidden="true">→</span> Linear
                </span>
                <span>Δ share</span>
              </div>
              {creditChannels.map((channel) => {
                const magnitude = (Math.abs(channel.share_delta_pct) / maxCreditDelta) * 50;
                const positive = channel.share_delta_pct >= 0;
                const direction = positive ? "gains" : "loses";
                return (
                  <div
                    className="diverging-row"
                    key={channel.channel_id}
                    role="group"
                    aria-label={`${channel.label}: first touch ${formatPercent(
                      channel.share_a_pct,
                    )}, linear ${formatPercent(channel.share_b_pct)}, ${direction} ${formatPp(
                      Math.abs(channel.share_delta_pct),
                    )} of channel revenue share`}
                  >
                    <div className="diverging-row__label">
                      <strong>{channel.label}</strong>
                      <span>
                        {formatPercent(channel.share_a_pct)} → {formatPercent(channel.share_b_pct)}
                      </span>
                    </div>
                    <div className="diverging-row__track">
                      <span className="diverging-row__axis" />
                      <span
                        className={classNames(
                          "diverging-row__bar",
                          positive ? "is-positive" : "is-negative",
                        )}
                        style={{ width: `${magnitude}%`, [positive ? "left" : "right"]: "50%" }}
                        title={`${channel.label}: ${formatCurrency(channel.first_touch)} first touch → ${formatCurrency(
                          channel.linear,
                        )} linear (${formatPp(channel.share_delta_pct, { signed: true })})`}
                      />
                    </div>
                    <span
                      className={classNames(
                        "diverging-row__value",
                        positive ? "value--positive" : "value--negative",
                      )}
                    >
                      {formatPp(channel.share_delta_pct, { signed: true })}
                    </span>
                  </div>
                );
              })}
              <div className="diverging-chart__note">
                <span>
                  {compare.share_basis?.definition ??
                    "Channel share = channel attributed revenue / total attributed revenue for the same model."}
                  {" "}Bars are scaled to the largest absolute shift, so a zero baseline is the vertical
                  rule in the middle of every track.
                </span>
                <Link to="/campaigns">Explore campaign credit <ArrowUpRight size={13} /></Link>
              </div>
              {showCreditTable ? (
                <div className="table-wrap credit-chart__table">
                  <table className="data-table">
                    <caption className="sr-only">
                      Channel revenue share under first-touch and linear attribution, with the
                      percentage-point difference.
                    </caption>
                    <thead>
                      <tr>
                        <th>Channel</th>
                        <th className="is-numeric">First touch</th>
                        <th className="is-numeric">Linear</th>
                        <th className="is-numeric">Δ share</th>
                        <th className="is-numeric">Revenue shift</th>
                      </tr>
                    </thead>
                    <tbody>
                      {creditChannels.map((channel) => (
                        <tr key={channel.channel_id}>
                          <td>{channel.label}</td>
                          <td className="is-numeric">{formatPercent(channel.share_a_pct)}</td>
                          <td className="is-numeric">{formatPercent(channel.share_b_pct)}</td>
                          <td className="is-numeric">
                            {formatPp(channel.share_delta_pct, { signed: true })}
                          </td>
                          <td className="is-numeric">
                            {formatSignedCurrency(channel.delta)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          ) : compareState.error ? (
            <ErrorState compact message={compareState.error.message} onRetry={compareState.reload} />
          ) : (
            <LoadingState rows={5} />
          )}
        </SectionCard>

        <SectionCard
          title="Model posture"
          description="Revenue totals are equal by design. Credit allocation is the variable."
          className="model-posture"
        >
          <div className="model-list">
            {summary.model_comparison.map((model) => (
              <div className="model-row" key={model.model}>
                <div>
                  <span className="model-row__dot" />
                  <strong>{modelLabel(model.model)}</strong>
                  <span>{model.attributed_conversions} attributed conversions</span>
                </div>
                <div>
                  <strong>{formatCurrency(model.attributed_revenue)}</strong>
                  <span>{formatPercent((model.attributed_conversions / summary.kpis.eligible_conversions) * 100)} conversion coverage</span>
                </div>
              </div>
            ))}
          </div>
          <div className="model-posture__note">
            <Gauge size={16} />
            <p>
              Compare channel mix, not totals. Allocation differences expose where acquisition and
              nurture each claim influence.
            </p>
          </div>
        </SectionCard>
      </div>

      <div className="overview-grid overview-grid--split">
        <SectionCard
          title="Channel contribution"
          description="Linear-attributed revenue, media spend and coverage-aware returns."
          actions={<Link className="text-link" to="/campaigns">Campaign ledger <ArrowUpRight size={13} /></Link>}
          flush
        >
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Channel</th>
                  <th className="is-numeric">Revenue</th>
                  <th className="is-numeric">Spend</th>
                  <th className="is-numeric">Conv.</th>
                  <th className="is-numeric">ROI</th>
                </tr>
              </thead>
              <tbody>
                {summary.channel_contribution.map((channel) => (
                  <tr key={channel.channel_id}>
                    <td>
                      <Link
                        className="channel-cell"
                        to={`/campaigns?channel=${channel.channel_id}`}
                      >
                        <span className="channel-cell__mark" />
                        <span>
                          <strong>{channel.channel_name}</strong>
                          <small>{channel.category}</small>
                        </span>
                      </Link>
                    </td>
                    <td className="is-numeric">
                      <div className="revenue-cell">
                        <span>{formatCurrency(channel.attributed_revenue)}</span>
                        <i
                          style={{
                            width: `${(Number(channel.attributed_revenue) / maxChannelRevenue) * 70}px`,
                          }}
                        />
                      </div>
                    </td>
                    <td className="is-numeric muted">{formatCurrency(channel.spend)}</td>
                    <td className="is-numeric">{channel.conversions}</td>
                    <td className="is-numeric">
                      {channel.roi_available === "true" || channel.roi_available === true ? (
                        <span
                          className={
                            Number(channel.roi_pct) < 0 ? "value--negative" : "value--positive"
                          }
                        >
                          {Number(channel.roi_pct) > 0 ? "+" : ""}
                          {formatDecimal(channel.roi_pct, 1)}%
                        </span>
                      ) : (
                        <span className="roi-unavailable">Not available</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        <SectionCard
          title="Top campaigns"
          description="Linear credit. ROI only renders where cost coverage is complete."
          actions={<Link className="text-link" to="/campaigns">All campaigns <ArrowUpRight size={13} /></Link>}
          className="top-campaigns"
          flush
        >
          <div className="ranked-list">
            {summary.top_campaigns.slice(0, 6).map((campaign, index) => (
              <Link
                to={`/campaigns/${campaign.campaign_id}`}
                className="ranked-row"
                key={campaign.campaign_id}
              >
                <span className="ranked-row__index">{String(index + 1).padStart(2, "0")}</span>
                <div className="ranked-row__main">
                  <strong>{campaign.campaign_name}</strong>
                  <span>
                    {campaign.channel_name} · {campaign.cost_coverage.replaceAll("_", " ").toLowerCase()}
                  </span>
                  <i
                    style={{
                      width: `${(Number(campaign.attributed_revenue) / maxCampaignRevenue) * 100}%`,
                    }}
                  />
                </div>
                <div className="ranked-row__value">
                  <strong>{formatCurrency(campaign.attributed_revenue)}</strong>
                  {campaign.roi_available === "true" ? (
                    <span className={Number(campaign.roi_pct) < 0 ? "value--negative" : "value--positive"}>
                      {formatPercent(campaign.roi_pct, { signed: true })} ROI
                    </span>
                  ) : (
                    <span className="roi-unavailable">ROI unavailable</span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        </SectionCard>
      </div>

      <div className="overview-grid overview-grid--split">
        <SectionCard
          title="Anomaly mix"
          description={`${issueTypeCount} issue types · ${matchedFixtures}/${fixtureCount} labelled synthetic fixtures matched by rule-based detection.`}
          actions={<Link className="text-link" to="/data-quality">Open exception queue <ArrowUpRight size={13} /></Link>}
        >
          <div className="issue-bars">
            {summary.anomaly_distribution.map((issue) => (
              <div className="issue-bar" key={issue.issue_type}>
                <div className="issue-bar__label">
                  <span>{issueLabel(issue.issue_type)}</span>
                  <Badge tone={issue.severity === "HIGH" ? "danger" : "warning"}>
                    {issue.severity.toLowerCase()}
                  </Badge>
                </div>
                <div className="issue-bar__track">
                  <span
                    style={{ width: `${(issue.count / maxIssueCount) * 100}%` }}
                    className={issue.severity === "HIGH" ? "is-high" : "is-medium"}
                  />
                </div>
                <strong>{issue.count}</strong>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Attribution hygiene"
          description="Controls applied before a touch is allowed to earn credit."
          className="hygiene-panel"
        >
          <div className="hygiene-grid">
            <HygieneItem label="Consent gated" value="Required" detail="Contact and touch consent must be granted" />
            <HygieneItem label="Post-conversion" value={`${summary.attribution_by_model.linear.unattributed_conversions} unattributed`} detail="No credit after the recognized order" />
            <HygieneItem label="Deduplication" value="Source-keyed" detail="Earliest ingested transaction becomes canonical" />
            <HygieneItem label="Identity" value={formatPercent(kpis.identity_coverage_pct)} detail="Evidence-backed session links only" />
          </div>
          <div className="hygiene-footer">
            <Users size={15} />
            <span>
              {formatNumber(kpis.contacts)} contacts · {formatNumber(kpis.touchpoints)} touchpoints ·{" "}
              {formatNumber(kpis.sessions)} sessions
            </span>
            <span>Generated {formatDate(summary.run.generated_at)}</span>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}

function MetricRow({
  label,
  value,
  progress,
  tone = "lime",
}: {
  label: string;
  value: string;
  progress: number;
  tone?: "lime" | "cyan" | "violet";
}) {
  return (
    <div className="metric-row">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className={classNames("metric-row__track", `metric-row__track--${tone}`)}>
        <span style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} />
      </div>
    </div>
  );
}

function HygieneItem({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="hygiene-item">
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}

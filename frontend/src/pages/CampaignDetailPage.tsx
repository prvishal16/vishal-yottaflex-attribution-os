import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Calendar,
  CircleDollarSign,
  Download,
  Layers,
  ReceiptText,
  Target,
} from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api/client";
import { CoverageBadge, RoiValue, SeverityBadge } from "../components/Badges";
import { ChartTooltip } from "../components/ChartTooltip";
import { ExportMenu, formatOptions } from "../components/ExportMenu";
import {
  Badge,
  CopyButton,
  ErrorState,
  LoadingState,
  PageHeader,
  ProgressBar,
  SectionCard,
  SegmentedControl,
  StatCard,
} from "../components/Primitives";
import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../hooks/useRunContext";
import type { CampaignListContext, ModelName } from "../types/api";
import {
  coverageLabel,
  formatCurrency,
  formatDate,
  formatDecimal,
  formatMonth,
  formatNumber,
  formatPercent,
  issueLabel,
  modelLabel,
  splitLabel,
} from "../utils/format";

export function CampaignDetailPage() {
  const { campaignId = "" } = useParams();
  const { effectiveRunId } = useRunContext();
  const location = useLocation();
  const ledger = (location.state as { ledger?: CampaignListContext } | null)?.ledger;
  const [model, setModel] = useState<ModelName>(ledger?.model ?? "linear");
  const state = useAsync(
    () => api.campaign(campaignId, model, effectiveRunId),
    [campaignId, model, effectiveRunId],
    { enabled: Boolean(effectiveRunId && campaignId) },
  );

  const backLink = (
    <Link
      className="back-link"
      to="/campaigns"
      state={ledger ? { ledger } : undefined}
    >
      <ArrowLeft size={14} /> Campaign ledger
    </Link>
  );

  const restoredSummary = ledger
    ? `${ledger.total} campaigns · ${modelLabel(ledger.model).toLowerCase()} credit`
    : null;

  if (state.loading && !state.data) {
    return (
      <div className="page-stack">
        {backLink}
        <LoadingState rows={8} />
      </div>
    );
  }

  if (state.error || !state.data) {
    return (
      <div className="page-stack">
        {backLink}
        <ErrorState
          message={state.error?.message ?? "Campaign not found."}
          onRetry={state.reload}
        />
      </div>
    );
  }

  const { campaign, performance, model_comparison: modelComparison } = state.data;
  const roiUnavailable = !performance.roi_available;
  const maxChannelRevenue = Math.max(
    ...state.data.channel_mix.map((channel) => channel.attributed_revenue),
    1,
  );

  return (
    <div className="page-stack">
      <div className="back-context">
        {backLink}
        {restoredSummary ? (
          <span className="back-context__summary">
            Returning to {restoredSummary}
            {ledger?.search ? ` · search “${ledger.search}”` : ""}
            {ledger?.coverage ? ` · ${ledger.coverage.toLowerCase()} coverage` : ""}
          </span>
        ) : null}
      </div>

      <PageHeader
        eyebrow={`${campaign.campaign_type} · ${campaign.objective}`}
        title={campaign.campaign_name}
        description={
          <>
            {campaign.primary_channel_id} · {formatDate(campaign.start_at)} →{" "}
            {formatDate(campaign.end_at)} · target audience {campaign.target_audience_id}
          </>
        }
        meta={
          <>
            <Badge tone="accent" dot>{campaign.status.toLowerCase()}</Badge>
            <CoverageBadge value={performance.cost_coverage} />
            <span className="mono">{campaign.campaign_id}</span>
            <CopyButton value={campaign.campaign_id} label="Copy ID" />
          </>
        }
        actions={
          <>
            <SegmentedControl
              label="Attribution model"
              value={model}
              onChange={setModel}
              options={[
                { value: "linear", label: "Linear" },
                { value: "first_touch", label: "First touch" },
                { value: "last_touch", label: "Last touch" },
              ]}
            />
            <ExportMenu
              options={formatOptions(
                (format) =>
                  api.campaignReportExportUrl(campaignId, model, effectiveRunId, format),
                {
                  csv: "Monthly attributed revenue and conversions for this campaign and model.",
                  json: "Full campaign detail plus every workbook sheet and run context.",
                  xlsx: "Summary, monthly credit, model comparison, channel mix, costs and issues.",
                  pdf: "Printable campaign report with scope and model stated up front.",
                },
              )}
              rowCount={state.data.monthly.length}
            />
          </>
        }
      />

      <section className="stat-grid stat-grid--compact">
        <StatCard
          label="Attributed revenue"
          value={formatCurrency(performance.attributed_revenue, { decimals: true })}
          detail={`${performance.conversions} conversions · ${modelLabel(model)}`}
          accent="lime"
          icon={CircleDollarSign}
        />
        <StatCard
          label="Known spend"
          value={formatCurrency(performance.spend)}
          detail={`${coverageLabel(performance.cost_coverage)} cost coverage`}
          accent="cyan"
          icon={ReceiptText}
        />
        <StatCard
          label="ROI / ROAS"
          value={
            <span className="stat-inline">
              <RoiValue
                value={performance.roi_pct}
                available={performance.roi_available}
                status={performance.roi_status}
              />
              <small>
                {performance.roi_available ? `${formatDecimal(performance.roas, 2)}×` : "Suppressed"}
              </small>
            </span>
          }
          detail={roiUnavailable ? performance.roi_status.replaceAll("_", " ").toLowerCase() : "Covered spend basis"}
          accent="violet"
          icon={Target}
        />
        <StatCard
          label="Average order value"
          value={formatCurrency(performance.average_order_value, { decimals: true })}
          detail={`${performance.unique_converting_contacts} unique buyers`}
          accent="amber"
          icon={Layers}
        />
      </section>

      {roiUnavailable ? (
        <div className="inline-alert inline-alert--warning">
          <AlertTriangle size={17} />
          <div>
            <strong>Financial return is intentionally suppressed for this campaign.</strong>
            <span>
              Coverage status: {coverageLabel(performance.cost_coverage)}. ROI and cost-per-conversion
              require every budgeted month to have complete, compatible EUR costs. Missing records are
              never treated as zero.
            </span>
          </div>
          <Link to="/data-quality">Review exceptions</Link>
        </div>
      ) : null}

      <div className="detail-grid">
        <SectionCard
          title="Monthly credit"
          description={`Revenue and conversions credited under ${modelLabel(model).toLowerCase()} across recognized orders.`}
          className="detail-chart"
        >
          {state.data.monthly.length ? (
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={280}>
                <ComposedChart
                  data={state.data.monthly}
                  margin={{ top: 10, right: 0, bottom: 0, left: -10 }}
                >
                  <defs>
                    <linearGradient id="campaignBar" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#c8ff5e" stopOpacity={0.9} />
                      <stop offset="100%" stopColor="#c8ff5e" stopOpacity={0.28} />
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
                    yAxisId="revenue"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#7f8b9d", fontSize: 11 }}
                    tickFormatter={(value: number) => formatCurrency(value, { compact: true })}
                    width={56}
                  />
                  <YAxis
                    yAxisId="conversions"
                    orientation="right"
                    allowDecimals={false}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#5eead4", fontSize: 10 }}
                    width={28}
                  />
                  <Tooltip
                    content={
                      <ChartTooltip
                        labelRenderer={(label) => formatMonth(String(label))}
                      />
                    }
                  />
                  <Bar
                    yAxisId="revenue"
                    dataKey="attributed_revenue"
                    name="Attributed revenue"
                    fill="url(#campaignBar)"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={30}
                  />
                  <Line
                    yAxisId="conversions"
                    type="monotone"
                    dataKey="conversions"
                    name="Conversions"
                    stroke="#5eead4"
                    strokeWidth={1.8}
                    dot={{ r: 2, fill: "#5eead4" }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="empty-state empty-state--compact">
              <Calendar size={20} />
              <h3>No credited revenue</h3>
              <p>No recognized conversions earned credit from this campaign under this model.</p>
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="Model comparison"
          description="Same conversions, different credit shape."
          className="model-compare-panel"
        >
          <div className="model-compare">
            {modelComparison.map((entry) => {
              const max = Math.max(...modelComparison.map((item) => item.attributed_revenue), 1);
              return (
                <button
                  key={entry.model}
                  type="button"
                  className={`model-compare__row ${entry.model === model ? "is-active" : ""}`}
                  onClick={() => setModel(entry.model)}
                >
                  <div>
                    <strong>{modelLabel(entry.model)}</strong>
                    <span>{entry.conversions} conv. · {entry.touchpoints_credited} touches</span>
                  </div>
                  <div className="model-compare__value">
                    <strong>{formatCurrency(entry.attributed_revenue)}</strong>
                    <span className="model-compare__track">
                      <i style={{ width: `${(entry.attributed_revenue / max) * 100}%` }} />
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
          <div className="budget-block">
            <div className="budget-block__head">
              <span>Budget utilization</span>
              <strong>{formatPercent(performance.budget_utilization)}</strong>
            </div>
            {performance.budget_utilization === null ? (
              <p className="budget-block__unavailable">
                Not available without a complete known-spend basis.
              </p>
            ) : (
              <ProgressBar value={performance.budget_utilization} label="Budget utilization" />
            )}
            <div className="budget-block__meta">
              <span>Known spend {formatCurrency(performance.spend)}</span>
              <span>Budget {formatCurrency(campaign.budget_amount)}</span>
            </div>
          </div>
          <div className="mini-meta-grid">
            <div>
              <span>Cost / conversion</span>
              <strong>{formatCurrency(performance.cost_per_conversion, { decimals: true })}</strong>
            </div>
            <div>
              <span>Credited touchpoints</span>
              <strong>{formatNumber(performance.touchpoints_credited)}</strong>
            </div>
            <div>
              <span>Open issues</span>
              <strong>{performance.issue_count}</strong>
            </div>
            <div>
              <span>Model versions</span>
              <strong>3</strong>
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="detail-grid detail-grid--lower">
        <SectionCard title="Channel mix" description="Credit distributed across channels under the selected model.">
          {state.data.channel_mix.length ? (
            <div className="channel-mix">
              {state.data.channel_mix.map((channel) => (
                <div className="channel-mix__row" key={channel.channel_id}>
                  <div className="channel-mix__label">
                    <span className="channel-cell__mark" />
                    <div>
                      <strong>{channel.channel_name}</strong>
                      <span>{channel.category} · {channel.conversions} conversions</span>
                    </div>
                  </div>
                  <div className="channel-mix__bar">
                    <i style={{ width: `${(channel.attributed_revenue / maxChannelRevenue) * 100}%` }} />
                  </div>
                  <strong>{formatCurrency(channel.attributed_revenue)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No channel-level credit exists for this campaign under the selected model.</p>
          )}
          {state.data.creatives.length ? (
            <div className="creative-list">
              {state.data.creatives.map((creative) => (
                <span className="creative-tag" key={creative.creative_id}>
                  <span>{creative.creative_type.toLowerCase()}</span>
                  {creative.name}
                </span>
              ))}
            </div>
          ) : null}
        </SectionCard>

        <SectionCard
          title="Exceptions touching this campaign"
          description="Detection evidence remains inspectable at the record level."
          actions={
            state.data.issues.length ? (
              <Link className="text-link" to="/data-quality">
                Queue <ArrowUpRight size={13} />
              </Link>
            ) : undefined
          }
        >
          {state.data.issues.length ? (
            <div className="issue-list">
              {state.data.issues.map((issue) => (
                <Link
                  key={issue.issue_id}
                  to={`/data-quality?issue=${issue.issue_id}`}
                  className="issue-list__row"
                >
                  <div>
                    <SeverityBadge severity={issue.severity} />
                    <strong>{issueLabel(issue.issue_type)}</strong>
                    <span>{issue.explanation}</span>
                  </div>
                  <div className="issue-list__meta">
                    <span>{splitLabel(issue.split)}</span>
                    <code>{issue.issue_id}</code>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="empty-state empty-state--compact">
              <Layers size={20} />
              <h3>No exceptions linked</h3>
              <p>This campaign is not referenced by any detected anomaly fixture.</p>
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Cost ledger"
        description="Compatible EUR costs are summed. Incompatible currencies are quarantined and excluded from spend."
        actions={
          <>
            <a
              className="button button--ghost button--sm"
              href={api.costRecordsExportUrl(campaignId, effectiveRunId, "csv")}
              title="Only this campaign's cost records"
            >
              <Download size={14} /> Campaign cost records CSV
            </a>
            <Badge tone="neutral">{state.data.cost_records.length} records</Badge>
          </>
        }
        flush
      >
        {state.data.cost_records.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Category</th>
                  <th>Source reference</th>
                  <th>Period</th>
                  <th className="is-numeric">Amount</th>
                  <th>Currency</th>
                </tr>
              </thead>
              <tbody>
                {state.data.cost_records.map((cost) => (
                  <tr key={cost.cost_id}>
                    <td>{formatDate(cost.cost_date)}</td>
                    <td>{cost.cost_category}</td>
                    <td className="mono">{cost.source_ref}</td>
                    <td>{cost.period}</td>
                    <td className="is-numeric">{formatCurrency(cost.amount, { decimals: true })}</td>
                    <td>
                      <Badge tone={cost.currency === "EUR" ? "neutral" : "danger"}>
                        {cost.currency}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state empty-state--compact">
            <ReceiptText size={20} />
            <h3>No cost records</h3>
            <p>This campaign has no compatible cost ledger entries. ROI remains unavailable.</p>
          </div>
        )}
      </SectionCard>
    </div>
  );
}

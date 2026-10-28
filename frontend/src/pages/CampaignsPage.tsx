import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronRight,
  FilterX,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { CoverageBadge, RoiValue } from "../components/Badges";
import { CampaignExportMenu } from "../components/ExportMenu";
import {
  Badge,
  Button,
  ErrorState,
  LoadingState,
  PageHeader,
  Pager,
  SectionCard,
  SegmentedControl,
  StatCard,
} from "../components/Primitives";
import { useAsync, useDebouncedValue } from "../hooks/useAsync";
import { useRunContext } from "../hooks/useRunContext";
import type { CampaignListContext, ModelName } from "../types/api";
import {
  classNames,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  modelLabel,
} from "../utils/format";

type SortKey =
  | "attributed_revenue"
  | "spend"
  | "roi_pct"
  | "conversions"
  | "issue_count"
  | "campaign_name";

const PAGE_SIZE = 20;

export function CampaignsPage() {
  const { effectiveRunId } = useRunContext();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const restored = (location.state as { ledger?: CampaignListContext } | null)?.ledger;
  const [model, setModel] = useState<ModelName>(restored?.model ?? "linear");
  const [search, setSearch] = useState(restored?.search ?? "");
  const [channel, setChannel] = useState(
    () => restored?.channel ?? searchParams.get("channel") ?? "",
  );
  const [coverage, setCoverage] = useState(restored?.coverage ?? "");
  const [page, setPage] = useState(restored?.page ?? 1);
  const [sort, setSort] = useState<SortKey>((restored?.sort as SortKey) ?? "attributed_revenue");
  const [order, setOrder] = useState<"asc" | "desc">(restored?.order ?? "desc");
  const debouncedSearch = useDebouncedValue(search, 320);

  useEffect(() => {
    setPage(1);
  }, [model, debouncedSearch, channel, coverage, sort, order]);

  const campaigns = useAsync(
    () =>
      api.campaigns(effectiveRunId, {
        model,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        sort,
        order,
        channelId: channel || undefined,
        search: debouncedSearch || undefined,
        coverage: coverage || undefined,
      }),
    [effectiveRunId, model, page, sort, order, channel, coverage, debouncedSearch],
    { enabled: Boolean(effectiveRunId) },
  );

  const channels = useAsync(
    () => api.channels(model, effectiveRunId),
    [effectiveRunId, model],
    { enabled: Boolean(effectiveRunId) },
  );

  function changeSort(next: SortKey) {
    if (sort === next) {
      setOrder((current) => (current === "desc" ? "asc" : "desc"));
    } else {
      setSort(next);
      setOrder(next === "campaign_name" ? "asc" : "desc");
    }
  }

  function resetFilters() {
    setSearch("");
    setChannel("");
    setCoverage("");
    setModel("linear");
    setPage(1);
  }

  const activeFilters = Boolean(search || channel || coverage || model !== "linear");
  const activeFilterCount = [search, channel, coverage, model !== "linear" ? model : ""].filter(
    Boolean,
  ).length;
  const data = campaigns.data;

  const listContext = useMemo<CampaignListContext>(
    () => ({
      model,
      sort,
      order,
      channel,
      coverage,
      search: debouncedSearch,
      page,
      total: data?.total ?? 0,
    }),
    [model, sort, order, channel, coverage, debouncedSearch, page, data?.total],
  );

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Campaign ledger"
        title="Every campaign, accountable."
        description="Compare credit allocation, inspect cost coverage, and separate commercial performance from instrumentation gaps."
        meta={
          <>
            <Badge tone="neutral">{modelLabel(model)} credit</Badge>
            <span>{data ? formatNumber(data.total) : "—"} campaigns in scope</span>
            <span>Cost-aware ROI only</span>
          </>
        }
        actions={
          <CampaignExportMenu
            runId={effectiveRunId}
            model={model}
            sort={sort}
            order={order}
            channelId={channel || undefined}
            search={debouncedSearch || undefined}
            coverage={coverage || undefined}
            rowCount={data?.total}
          />
        }
      />

      <section className="stat-grid stat-grid--compact">
        <StatCard
          label="Revenue in view"
          value={formatCurrency(data?.aggregates.attributed_revenue ?? 0)}
          detail="Linear credit across filtered campaigns"
          accent="lime"
        />
        <StatCard
          label="Known spend"
          value={formatCurrency(data?.aggregates.spend)}
          detail={
            data
              ? `Known across ${data.aggregates.spend_known_campaigns} campaigns · ${data.aggregates.spend_missing_campaigns} missing cost · ${data.aggregates.spend_no_cost_basis_campaigns} no paid basis`
              : "Compatible EUR cost records"
          }
          accent="cyan"
        />
        <StatCard
          label="Campaign conversion credits"
          value={formatNumber(data?.aggregates.conversions ?? 0)}
          detail="Orders can be credited to multiple campaigns"
          accent="violet"
        />
        <StatCard
          label="Mean campaign ROI"
          value={
            data?.aggregates.average_roi_pct === null || data?.aggregates.average_roi_pct === undefined
              ? "Not available"
              : formatPercent(data.aggregates.average_roi_pct, { signed: true })
          }
          detail={`Unweighted mean over ${data?.aggregates.roi_campaigns ?? 0} ROI-available campaigns`}
          accent="amber"
          className={
            data?.aggregates.average_roi_pct !== null &&
            data?.aggregates.average_roi_pct !== undefined &&
            data.aggregates.average_roi_pct < 0
              ? "stat-card--negative"
              : undefined
          }
        />
      </section>

      <SectionCard className="filter-panel" flush>
        <div className="filter-bar">
          <div className="filter-bar__legend">
            <SlidersHorizontal size={13} aria-hidden="true" />
            <strong>Filters</strong>
            <span className="filter-bar__hint">
              These narrow the rows below. Badges describe each row and never filter.
            </span>
            {activeFilterCount > 0 ? (
              <span className="filter-bar__active">{activeFilterCount} active</span>
            ) : null}
          </div>
          <div className="filter-bar__group">
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
          </div>
          <label className="search-field">
            <Search size={15} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search campaign name or ID"
              aria-label="Search campaigns"
            />
          </label>
          <label className="select-field">
            <span className="select-field__label">Channel</span>
            <select
              value={channel}
              onChange={(event) => setChannel(event.target.value)}
              aria-label="Filter by channel"
            >
              <option value="">All channels</option>
              {channels.data?.items.map((item) => (
                <option key={item.channel_id} value={item.channel_id}>
                  {item.channel_name}
                </option>
              ))}
            </select>
          </label>
          <label className="select-field">
            <span className="select-field__label">Cost coverage</span>
            <select
              value={coverage}
              onChange={(event) => setCoverage(event.target.value)}
              aria-label="Filter by cost coverage"
            >
              <option value="">Any coverage</option>
              <option value="COMPLETE">Complete</option>
              <option value="PARTIAL">Partial</option>
              <option value="MISSING">Missing</option>
              <option value="NO_COST_BASIS">No cost basis</option>
            </select>
          </label>
          <Button
            variant="ghost"
            size="sm"
            icon={FilterX}
            onClick={resetFilters}
            disabled={!activeFilters}
          >
            Reset
          </Button>
        </div>
      </SectionCard>

      <SectionCard
        title="Campaign performance"
        description={
          data
            ? `Showing ${data.items.length} of ${data.total} matching campaigns · sorted by ${sort.replaceAll("_", " ")} ${order}`
            : "Loading campaign ledger"
        }
        actions={
          <div className="table-legend">
            <Badge tone="neutral">{data?.currency ?? "EUR"}</Badge>
            <span className="table-legend-hint">
              Coverage and issue badges describe each row; they do not filter.
            </span>
          </div>
        }
        flush
      >
        {campaigns.error ? (
          <div className="panel-pad">
            <ErrorState message={campaigns.error.message} onRetry={campaigns.reload} />
          </div>
        ) : campaigns.loading && !data ? (
          <div className="panel-pad">
            <LoadingState rows={8} />
          </div>
        ) : data && data.items.length === 0 ? (
          <div className="empty-state">
            <FilterX size={22} />
            <h3>No campaigns match these filters</h3>
            <p>Clear a filter or choose a different attribution model.</p>
            <Button variant="secondary" size="sm" onClick={resetFilters}>
              Reset filters
            </Button>
          </div>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table data-table--campaigns">
                <thead>
                  <tr>
                    <th>
                      <SortButton
                        label="Campaign"
                        active={sort === "campaign_name"}
                        order={order}
                        onClick={() => changeSort("campaign_name")}
                      />
                    </th>
                    <th>Channel</th>
                    <th>Coverage</th>
                    <th className="is-numeric">
                      <SortButton
                        label="Spend"
                        active={sort === "spend"}
                        order={order}
                        onClick={() => changeSort("spend")}
                        numeric
                      />
                    </th>
                    <th className="is-numeric">
                      <SortButton
                        label="Attributed"
                        active={sort === "attributed_revenue"}
                        order={order}
                        onClick={() => changeSort("attributed_revenue")}
                        numeric
                      />
                    </th>
                    <th className="is-numeric">
                      <SortButton
                        label="Conv."
                        active={sort === "conversions"}
                        order={order}
                        onClick={() => changeSort("conversions")}
                        numeric
                      />
                    </th>
                    <th className="is-numeric">
                      <SortButton
                        label="ROI"
                        active={sort === "roi_pct"}
                        order={order}
                        onClick={() => changeSort("roi_pct")}
                        numeric
                      />
                    </th>
                    <th className="is-numeric">
                      <SortButton
                        label="Issues"
                        active={sort === "issue_count"}
                        order={order}
                        onClick={() => changeSort("issue_count")}
                        numeric
                      />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((campaign) => (
                    <tr key={campaign.campaign_id} className="row-link">
                      <td className="row-link__cell">
                        <Link
                          className="campaign-cell"
                          to={`/campaigns/${campaign.campaign_id}`}
                          state={{ ledger: listContext }}
                          aria-label={`Open campaign ${campaign.campaign_name} (${campaign.campaign_id})`}
                        >
                          <strong>{campaign.campaign_name}</strong>
                          <span>
                            {campaign.campaign_id} · {formatDate(campaign.start_at)} →{" "}
                            {formatDate(campaign.end_at)}
                          </span>
                        </Link>
                      </td>
                      <td>
                        <span className="muted">{campaign.primary_channel_name}</span>
                      </td>
                      <td>
                        <CoverageBadge value={campaign.cost_coverage} />
                      </td>
                      <td className="is-numeric">{formatCurrency(campaign.spend)}</td>
                      <td className="is-numeric">
                        <strong>{formatCurrency(campaign.attributed_revenue)}</strong>
                      </td>
                      <td className="is-numeric">{formatNumber(campaign.conversions)}</td>
                      <td className="is-numeric">
                        <RoiValue
                          value={campaign.roi_pct}
                          available={campaign.roi_available}
                          status={campaign.roi_status}
                        />
                      </td>
                      <td className="is-numeric">
                        {campaign.issue_count > 0 ? (
                          <Badge tone="danger">{campaign.issue_count}</Badge>
                        ) : (
                          <span className="muted">0</span>
                        )}
                      </td>
                      <td className="row-link__chevron" aria-hidden="true">
                        <ChevronRight size={14} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data ? (
              <Pager
                page={page}
                pageSize={PAGE_SIZE}
                total={data.total}
                onChange={setPage}
              />
            ) : null}
          </>
        )}
      </SectionCard>

      <div className="table-note">
        <ArrowUpDown size={13} />
        <span>
          ROI and cost-per-conversion are suppressed unless every budgeted month has complete,
          compatible cost coverage. Missing data is never coerced to zero.
        </span>
      </div>
    </div>
  );
}

function SortButton({
  label,
  active,
  order,
  onClick,
  numeric = false,
}: {
  label: string;
  active: boolean;
  order: "asc" | "desc";
  onClick: () => void;
  numeric?: boolean;
}) {
  return (
    <button
      type="button"
      className={classNames("sort-button", active && "is-active", numeric && "is-numeric")}
      onClick={onClick}
    >
      {label}
      {active ? (
        order === "desc" ? <ArrowDown size={12} /> : <ArrowUp size={12} />
      ) : (
        <ArrowUpDown size={12} />
      )}
    </button>
  );
}

import {
  ArrowRight,
  CheckCircle2,
  CircleSlash2,
  Clock3,
  Fingerprint,
  Route,
  Search,
  ShieldCheck,
  Sparkles,
  UserRound,
  XCircle,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
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
} from "../components/Primitives";
import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../hooks/useRunContext";
import type { JourneyTouch, ModelName } from "../types/api";
import {
  classNames,
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPercent,
  initials,
  modelLabel,
  outcomeLabel,
  splitLabel,
} from "../utils/format";

type TimelineItem =
  | { kind: "touch"; at: string; touch: JourneyTouch }
  | { kind: "conversion"; at: string };

export function JourneyPage() {
  const { effectiveRunId } = useRunContext();
  const [input, setInput] = useState("");
  const [reference, setReference] = useState("");
  const [touchFilter, setTouchFilter] = useState<"all" | "eligible">("all");
  const [showAllTouches, setShowAllTouches] = useState(false);
  const [focusModel, setFocusModel] = useState<ModelName | "all">("all");

  const state = useAsync(
    () =>
      reference
        ? api.journey(reference, effectiveRunId)
        : api.sampleJourney(effectiveRunId),
    [reference, effectiveRunId],
    { enabled: Boolean(effectiveRunId) },
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    setReference(input.trim().toUpperCase());
  }

  function loadSample() {
    setReference("");
    setInput("");
    state.reload();
  }

  function inspect(value: string) {
    setInput(value);
    setReference(value);
  }

  const data = state.data;
  const touches = data?.touchpoints ?? [];
  const eligibleTouches = touches.filter((touch) => touch.eligible);
  const visibleTouches = touchFilter === "eligible" ? eligibleTouches : touches;
  const displayedTouches = showAllTouches ? visibleTouches : visibleTouches.slice(-6);
  const collapsibleTouches = Math.max(0, visibleTouches.length - 6);
  const hiddenTouches = showAllTouches ? 0 : collapsibleTouches;
  const totalExclusions = data?.exclusions
    ? Object.values(data.exclusions).reduce((sum, value) => sum + value, 0)
    : 0;

  const timeline = useMemo(() => {
    const items: TimelineItem[] = displayedTouches.map((touch) => ({
      kind: "touch",
      at: touch.occurred_at,
      touch,
    }));
    if (data?.conversion) {
      items.push({ kind: "conversion", at: data.conversion.ordered_at });
    }
    return items.sort((left, right) => {
      const byTime = left.at.localeCompare(right.at);
      if (byTime !== 0) return byTime;
      return left.kind === "conversion" ? -1 : 1;
    });
  }, [displayedTouches, data?.conversion]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Journey explorer"
        title="Follow the money to the touch."
        description="Replay any conversion through identity resolution, consent, lookback, and all three attribution models. Excluded touches stay visible."
        meta={
          <>
            <Badge tone="accent" dot>
              Interactive explainability
            </Badge>
            <span>Order, opportunity or contact ID</span>
            <span>Persisted vs. recomputed check</span>
          </>
        }
        actions={
          <>
            <Button variant="secondary" size="md" icon={Sparkles} onClick={loadSample}>
              Load sample journey
            </Button>
            {data ? (
              <ExportMenu
                buttonLabel="Export journey"
                options={formatOptions(
                  (format) =>
                    api.journeyExportUrl(data.reference, effectiveRunId, format),
                  {
                    csv: "Every candidate touchpoint with eligibility and per-model credit.",
                    json: "Full journey, allocation and persisted-check payload.",
                    xlsx: "Touchpoints, allocations, exclusions, model totals and conversion.",
                    pdf: "Printable touchpoint replay with exclusion outcomes.",
                  },
                )}
                rowCount={touches.length}
              />
            ) : null}
          </>
        }
      />

      <form className="journey-search" onSubmit={submit}>
        <Route size={17} />
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="e.g. ORD-2026-000052, OPP-2026-000118 or CON-2026-000341"
          aria-label="Journey reference"
          spellCheck={false}
        />
        <Button type="submit" variant="primary" size="sm" icon={Search}>
          Inspect journey
        </Button>
      </form>

      {data ? (
        <div className="journey-quick-ids">
          <span>Jump to</span>
          {data.reference.startsWith("ORD-") ? null : (
            <button type="button" onClick={() => inspect(data.reference)}>
              {data.reference}
            </button>
          )}
          {data.conversion?.order_id ? (
            <button type="button" onClick={() => inspect(data.conversion!.order_id)}>
              {data.conversion.order_id}
            </button>
          ) : null}
          {data.opportunity?.opportunity_id ? (
            <button type="button" onClick={() => inspect(data.opportunity!.opportunity_id)}>
              {data.opportunity.opportunity_id}
            </button>
          ) : null}
          {data.contact?.contact_id ? (
            <button type="button" onClick={() => inspect(data.contact!.contact_id)}>
              {data.contact.contact_id}
            </button>
          ) : null}
        </div>
      ) : null}

      {state.error ? (
        <ErrorState
          message={state.error.message}
          onRetry={state.reload}
        />
      ) : state.loading && !data ? (
        <LoadingState rows={8} />
      ) : data ? (
        <>
          <div className="journey-overview">
            <SectionCard className="journey-person" flush>
              <div className="journey-person__body">
                <span className="avatar">{contactMark(data.contact?.contact_id)}</span>
                <div>
                  <span className="eyebrow">Contact</span>
                  <h2>{data.contact?.contact_id ?? "Unknown contact"}</h2>
                  <p>
                    {data.contact
                      ? `${data.contact.segment} · ${data.contact.region} · ${data.contact.country}`
                      : "No resolved contact record"}
                  </p>
                </div>
                <div className="person-badges">
                  {data.contact ? (
                    <>
                      <Badge tone={data.contact.consent_status === "GRANTED" ? "positive" : "danger"} dot>
                        Consent {data.contact.consent_status.toLowerCase()}
                      </Badge>
                      <Badge tone="neutral">{data.contact.lifecycle_status.replaceAll("_", " ").toLowerCase()}</Badge>
                    </>
                  ) : null}
                </div>
              </div>
              <div className="journey-person__meta">
                <div>
                  <span>Opportunity</span>
                  <strong>{data.opportunity?.opportunity_id ?? "—"}</strong>
                </div>
                <div>
                  <span>Owner team</span>
                  <strong>{data.opportunity?.owner_team ?? "—"}</strong>
                </div>
                <div>
                  <span>Acquisition channel</span>
                  <strong>{data.contact?.acquisition_channel_id ?? "—"}</strong>
                </div>
                <div>
                  <span>Contact created</span>
                  <strong>{formatDateTime(data.contact?.created_at)}</strong>
                </div>
              </div>
            </SectionCard>

            <SectionCard className="journey-conversion" flush>
              <div className="conversion-card">
                <div>
                  <span className="eyebrow">Recognized conversion</span>
                  <strong className="conversion-card__value">
                    {data.conversion
                      ? formatCurrency(data.conversion.revenue, { decimals: true })
                      : "No revenue"}
                  </strong>
                  <span className="conversion-card__sub">
                    {data.conversion
                      ? `${data.conversion.currency} · ${splitLabel(data.conversion.split)} split · ${data.conversion.lookback_days}-day lookback`
                      : "Attribution does not apply to this journey"}
                  </span>
                </div>
                <div className="conversion-card__status">
                  {data.status === "CONVERTED" ? (
                    <Badge tone="positive" dot>Converted</Badge>
                  ) : (
                    <Badge tone="warning" dot>No recognized revenue</Badge>
                  )}
                  <Badge tone={data.persisted_consistent ? "positive" : "warning"}>
                    {data.persisted_consistent ? "Persisted check passed" : "Persisted check differs"}
                  </Badge>
                </div>
              </div>
              {data.conversion ? (
                <div className="conversion-card__meta">
                  <div>
                    <span>Order</span>
                    <strong>{data.conversion.order_id}</strong>
                  </div>
                  <div>
                    <span>Ordered at</span>
                    <strong>{formatDateTime(data.conversion.ordered_at)}</strong>
                  </div>
                  <div>
                    <span>Source ref</span>
                    <strong className="mono">{data.conversion.source_system_ref}</strong>
                  </div>
                  <div>
                    <span>Consent at conversion</span>
                    <strong>{data.conversion.consent_status}</strong>
                  </div>
                </div>
              ) : null}
            </SectionCard>
          </div>

          {data.conversion && data.conversion.duplicate_orders.length > 1 ? (
            <div className="inline-alert inline-alert--info">
              <CircleSlash2 size={17} />
              <div>
                <strong>Duplicate source transactions detected for this order.</strong>
                <span>
                  Revenue uses the canonical order only.{" "}
                  {data.conversion.duplicate_orders
                    .map(
                      (duplicate) =>
                        `${duplicate.order_id}${duplicate.canonical ? " (canonical)" : ""}`,
                    )
                    .join(" · ")}
                </span>
              </div>
              <Link to="/data-quality">Inspect exception</Link>
            </div>
          ) : null}

          {data.status === "CONVERTED" ? (
            <>
              <div className="journey-model-grid">
                {data.models.map((model) => (
                  <article className="model-outcome" key={model.model}>
                    <div className="model-outcome__head">
                      <span className="model-row__dot" />
                      <strong>{modelLabel(model.model)}</strong>
                      <Badge tone={model.status === "ATTRIBUTED" ? "positive" : "warning"}>
                        {model.status.toLowerCase()}
                      </Badge>
                    </div>
                    <strong className="model-outcome__value">
                      {formatCurrency(model.attributed_revenue, { decimals: true })}
                    </strong>
                    <div className="model-outcome__meta">
                      <span>{model.credited_touchpoints} credited touches</span>
                      <span>{model.eligible_touchpoints} eligible</span>
                      <span>Δ {formatCurrency(model.reconciliation_difference, { decimals: true })}</span>
                    </div>
                  </article>
                ))}
              </div>

              {data.persisted_check ? (
                <SectionCard
                  title="Persisted vs. recomputed"
                  description="Recomputed credit from the persisted journey is compared model-by-model with the stored attribution conversion."
                  actions={
                    <Badge tone={data.persisted_check.consistent ? "positive" : "warning"} dot>
                      {data.persisted_check.consistent
                        ? "All models match"
                        : `${data.persisted_check.difference_count} model differences`}
                    </Badge>
                  }
                  className="persisted-panel"
                >
                  <div className="persisted-grid">
                    {data.persisted_check.models.map((check) => (
                      <div
                        className={classNames("persisted-row", !check.matched && "is-different")}
                        key={check.model}
                      >
                        <div className="persisted-row__head">
                          <strong>{modelLabel(check.model)}</strong>
                          <Badge tone={check.matched ? "positive" : "warning"}>
                            {check.matched ? "Match" : "Differs"}
                          </Badge>
                        </div>
                        <div className="persisted-row__values">
                          <div>
                            <span>Recomputed</span>
                            <strong>{formatCurrency(check.computed_revenue, { decimals: true })}</strong>
                            <small>{check.computed_status}</small>
                          </div>
                          <ArrowRight size={14} />
                          <div>
                            <span>Persisted</span>
                            <strong>{formatCurrency(check.persisted_revenue, { decimals: true })}</strong>
                            <small>{check.persisted_status ?? "MISSING ROW"}</small>
                          </div>
                        </div>
                        <div className="persisted-row__meta">
                          <span>
                            {check.difference === null
                              ? "No persisted value"
                              : `Δ ${formatCurrency(check.difference, { decimals: true })}`}
                          </span>
                          <span>
                            Status {check.status_match ? "matches" : "differs"} · revenue{" "}
                            {check.revenue_match ? "matches" : "differs"}
                          </span>
                        </div>
                        {check.absolute_difference !== null &&
                        check.absolute_difference !== undefined ? (
                          <div className="persisted-row__meta">
                            <span>
                              |Δ| {formatCurrency(check.absolute_difference, { decimals: true })}{" "}
                              · tolerance {formatCurrency(check.tolerance, { decimals: true })}
                            </span>
                            <span>{check.comparison.replaceAll("_", " ")}</span>
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                  {data.persisted_check.allocations?.length ? (
                    <div className="allocation-check">
                      <div className="allocation-check__head">
                        <strong>Touchpoint allocation check</strong>
                        <Badge
                          tone={
                            data.persisted_check.allocations_consistent ? "positive" : "warning"
                          }
                          dot
                        >
                          {data.persisted_check.allocations_consistent
                            ? "Every allocated touch matches"
                            : "Allocation differences found"}
                        </Badge>
                      </div>
                      <p>
                        Conversion totals can reconcile while individual touchpoint credit does
                        not. Each recomputed allocation is compared with the stored attribution
                        row for the same order, model and touchpoint.
                      </p>
                      <div className="allocation-check__grid">
                        {data.persisted_check.allocations.map((check) => (
                          <div
                            className={classNames(
                              "allocation-check__row",
                              !check.matched && "is-different",
                            )}
                            key={check.model}
                          >
                            <span>{modelLabel(check.model)}</span>
                            <strong>
                              {check.matched
                                ? `${check.compared_touchpoints} touch${
                                    check.compared_touchpoints === 1 ? "" : "es"
                                  } match`
                                : `${check.difference_count} of ${check.compared_touchpoints} differ`}
                            </strong>
                            <small>
                              ±{formatCurrency(check.tolerance.attributed_revenue, {
                                decimals: true,
                              })}{" "}
                              revenue · ±{check.tolerance.credit_fraction} fraction
                            </small>
                          </div>
                        ))}
                      </div>
                      {data.persisted_check.allocations.some(
                        (check) => !check.matched && check.differences.length,
                      ) ? (
                        <div className="allocation-check__differences">
                          {data.persisted_check.allocations
                            .filter((check) => !check.matched)
                            .map((check) => (
                              <div key={check.model}>
                                <strong>{modelLabel(check.model)}</strong>
                                {check.differences.map((difference) => (
                                  <div className="allocation-diff" key={difference.touchpoint_id}>
                                    <code>{difference.touchpoint_id}</code>
                                    <span>{difference.reason.replaceAll("_", " ").toLowerCase()}</span>
                                    {difference.recomputed_revenue !== undefined ? (
                                      <span>
                                        recomputed{" "}
                                        {formatCurrency(difference.recomputed_revenue, {
                                          decimals: true,
                                        })}
                                        {" · persisted "}
                                        {formatCurrency(difference.persisted_revenue, {
                                          decimals: true,
                                        })}
                                      </span>
                                    ) : null}
                                  </div>
                                ))}
                              </div>
                            ))}
                        </div>
                      ) : null}
                      {data.persisted_check.population ? (
                        <p className="allocation-check__scope">
                          Scope: {data.persisted_check.scope ?? "this conversion only"} · order{" "}
                          {data.persisted_check.population.order_id} ·{" "}
                          {data.persisted_check.population.eligible_touchpoints} eligible of{" "}
                          {data.persisted_check.population.candidate_touchpoints} candidate
                          touchpoints.
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </SectionCard>
              ) : null}

              {data.exclusions ? (
                <SectionCard
                  title="Filtered before attribution"
                  description="These touches exist in the journey record but cannot earn credit under the platform rules."
                  actions={
                    <Badge tone="neutral">
                      {formatNumber(data.counts?.total_touches ?? touches.length)} candidate
                      touches
                    </Badge>
                  }
                  className="exclusion-panel"
                >
                  <div className="exclusion-grid">
                    {Object.entries(data.exclusions).map(([key, value]) => (
                      <div className="exclusion-item" key={key}>
                        <span>{outcomeLabel(key.replace("excluded_", "").toUpperCase())}</span>
                        <strong>{formatNumber(value)}</strong>
                      </div>
                    ))}
                    <div className="exclusion-item exclusion-item--total">
                      <span>Total excluded</span>
                      <strong>{formatNumber(totalExclusions)}</strong>
                    </div>
                    <div className="exclusion-item exclusion-item--total">
                      <span>Eligible for credit</span>
                      <strong>
                        {formatNumber(
                          data.counts?.eligible_touches ?? eligibleTouches.length,
                        )}
                      </strong>
                    </div>
                  </div>
                  <p className="exclusion-note">
                    {data.counts?.exclusion_semantics ??
                      "Each candidate touch receives exactly one primary exclusion reason, so the total excluded equals unique excluded touches."}
                  </p>
                </SectionCard>
              ) : null}

              <SectionCard
                title="Touchpoint timeline"
                description="Chronological interactions that resolved to this contact. The conversion sits at its real position in time, so post-conversion touches appear after it. Credit is recalculated from the same rules used by the pipeline."
                actions={
                  <div className="timeline-actions">
                    <Badge tone="neutral">
                      {displayedTouches.length === visibleTouches.length
                        ? `${visibleTouches.length} matching`
                        : `${displayedTouches.length} of ${visibleTouches.length} shown`}
                    </Badge>
                    <SegmentedControl
                      label="Touchpoint filter"
                      value={touchFilter}
                      onChange={setTouchFilter}
                      options={[
                        { value: "all", label: "All" },
                        { value: "eligible", label: "Eligible" },
                      ]}
                    />
                    <SegmentedControl
                      label="Highlight attribution model"
                      value={focusModel}
                      onChange={setFocusModel}
                      options={[
                        { value: "all", label: "All models" },
                        { value: "linear", label: "Linear" },
                        { value: "first_touch", label: "First touch" },
                        { value: "last_touch", label: "Last touch" },
                      ]}
                    />
                  </div>
                }
                flush
              >
                {visibleTouches.length ? (
                  <div className="timeline">
                    {hiddenTouches > 0 ? (
                      <button
                        type="button"
                        className="timeline-more"
                        onClick={() => setShowAllTouches(true)}
                      >
                        Show {hiddenTouches} earlier touchpoint{hiddenTouches === 1 ? "" : "s"}
                      </button>
                    ) : null}
                    {timeline.map((item) =>
                      item.kind === "conversion" ? (
                        <div className="timeline-event timeline-event--conversion" key="conversion">
                          <span className="timeline-event__marker">
                            <CheckCircle2 size={15} />
                          </span>
                          <div>
                            <span className="eyebrow">Conversion</span>
                            <strong>{data.conversion?.order_id}</strong>
                            <span>{formatDateTime(data.conversion?.ordered_at)}</span>
                          </div>
                          <strong>{formatCurrency(data.conversion?.revenue, { decimals: true })}</strong>
                        </div>
                      ) : (
                        <TimelineTouch
                          key={item.touch.touchpoint_id}
                          touch={item.touch}
                          revenue={data.conversion?.revenue ?? 0}
                          focusModel={focusModel}
                        />
                      ),
                    )}
                    {showAllTouches && collapsibleTouches > 0 ? (
                      <button
                        type="button"
                        className="timeline-more timeline-more--collapse"
                        onClick={() => setShowAllTouches(false)}
                      >
                        Collapse to the 6 most recent touches
                      </button>
                    ) : null}
                  </div>
                ) : (
                  <div className="empty-state">
                    <Route size={22} />
                    <h3>No touches match this filter</h3>
                    <p>Switch to “All” to inspect excluded interactions.</p>
                  </div>
                )}
              </SectionCard>
            </>
          ) : (
            <div className="inline-alert inline-alert--warning">
              <CircleSlash2 size={17} />
              <div>
                <strong>No recognized conversion revenue.</strong>
                <span>{data.message ?? "This journey cannot be attributed."}</span>
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

function TimelineTouch({
  touch,
  revenue,
  focusModel,
}: {
  touch: JourneyTouch;
  revenue: number;
  focusModel: ModelName | "all";
}) {
  const [expanded, setExpanded] = useState(false);
  const credits = useMemo(() => Object.entries(touch.credits), [touch.credits]);
  const maxCredit = Math.max(...credits.map(([, credit]) => credit.attributed_revenue), 0);
  const outcomeClass = touch.eligible
    ? "is-eligible"
    : touch.outcome === "POST_CONVERSION"
      ? "is-post"
      : "is-excluded";

  return (
    <div className={classNames("timeline-event", outcomeClass)}>
      <span className="timeline-event__marker">
        {touch.eligible ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
      </span>
      <div className="timeline-event__body">
        <div className="timeline-event__head">
          <div>
            <span className="timeline-event__time">
              <Clock3 size={12} />
              {formatOffset(touch.minutes_from_conversion)}
            </span>
            <strong>{touch.campaign_name ?? touch.campaign_id}</strong>
          </div>
          <div className="timeline-event__badges">
            <Badge tone={touch.eligible ? "positive" : "danger"}>
              {outcomeLabel(touch.outcome)}
            </Badge>
            <Badge tone="neutral">{touch.channel_name}</Badge>
          </div>
        </div>

        <div className="timeline-event__meta">
          <span>{touch.touch_type.replaceAll("_", " ").toLowerCase()}</span>
          <span>{formatDateTime(touch.occurred_at)}</span>
          <span>{touch.source_system}</span>
          <span>{touch.creative_name ?? "No creative"}</span>
        </div>

        {touch.outcome_reason ? (
          <p className="timeline-event__reason">{touch.outcome_reason}</p>
        ) : null}

        {credits.length ? (
          <div className="credit-block">
            {credits.map(([model, credit]) => (
              <div
                className={classNames(
                  "credit-row",
                  focusModel === model && "is-focused",
                )}
                key={model}
              >
                <span>{modelLabel(model)}</span>
                <div className="credit-row__track">
                  <i
                    style={{
                      width: `${maxCredit ? (credit.attributed_revenue / maxCredit) * 100 : 0}%`,
                    }}
                  />
                </div>
                <span>{formatPercent(credit.credit_fraction * 100)}</span>
                <strong>{formatCurrency(credit.attributed_revenue, { decimals: true })}</strong>
              </div>
            ))}
            <div className="credit-block__revenue">
              Share of {formatCurrency(revenue, { decimals: true })} recognized revenue
            </div>
          </div>
        ) : (
          <div className="credit-block credit-block--empty">
            <CircleSlash2 size={13} /> No credit assigned
          </div>
        )}

        <button
          type="button"
          className="timeline-event__expand"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? "Hide evidence" : "Identity & consent evidence"}
        </button>
        {expanded ? (
          <div className="timeline-event__evidence">
            <div>
              <Fingerprint size={13} />
              <span>Identity</span>
              <strong>{touch.identity_status}</strong>
              <span>{touch.resolution_status.replaceAll("_", " ").toLowerCase()}</span>
              <code>{touch.resolution_rule_id}</code>
            </div>
            <div>
              <ShieldCheck size={13} />
              <span>Consent</span>
              <strong>{touch.consent_status}</strong>
            </div>
            <div>
              <UserRound size={13} />
              <span>Resolved contact</span>
              <strong>{touch.resolved_contact_id ?? "Unresolved"}</strong>
            </div>
            <div>
              <ArrowRight size={13} />
              <span>Touchpoint</span>
              <strong className="mono">{touch.touchpoint_id}</strong>
              <CopyButton value={touch.touchpoint_id} label="Copy" />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function contactMark(value?: string) {
  const digits = value?.match(/\d+$/)?.[0];
  return digits ? digits.slice(-2) : initials(value ?? "Unknown");
}

function formatOffset(minutes: number) {
  const absolute = Math.abs(minutes);
  const suffix = minutes <= 0 ? "before" : "after";
  if (absolute < 60) return `${Math.round(absolute)} min ${suffix}`;
  if (absolute < 1440) return `${(absolute / 60).toFixed(1)} hr ${suffix}`;
  return `${(absolute / 1440).toFixed(1)} days ${suffix}`;
}

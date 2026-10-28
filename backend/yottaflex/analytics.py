"""Aggregated campaign, channel, financial and executive analytics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import duckdb

from yottaflex.config import MODELS, SPLITS, RunConfig
from yottaflex.domain.financials import (
    average_order_value,
    conversion_rate,
    cost_coverage,
    cost_per_conversion,
    roas,
    roi,
)
from yottaflex.storage import create_typed_views, refresh_table
from yottaflex.tables import DERIVED_TABLES
from yottaflex.util import iso, write_csv, write_json


def d(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value))


def ds(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _pct(numerator: int | Decimal, denominator: int | Decimal) -> str:
    if not denominator:
        return ""
    return ds(Decimal(numerator) * Decimal(100) / Decimal(denominator))


def _known_spend(spend: Decimal, coverage: str) -> str:
    """Return blank for unknown spend; zero is reserved for a known zero basis."""

    if coverage in ("MISSING", "NO_COST_BASIS"):
        return ""
    return ds(spend)


def _expected_periods(start: Any, end: Any) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _fetch(conn: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cursor = conn.execute(sql)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _campaign_issue_counts(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    if not _table_exists(conn, "exceptions"):
        return counts
    rows = _fetch(
        conn,
        "SELECT issue_type, primary_entity_id FROM exceptions",
    )
    cost_campaign = dict(
        conn.execute("SELECT cost_id, campaign_id FROM cost_records").fetchall()
    )
    for row in rows:
        if row["issue_type"] == "MISSING_CAMPAIGN_COST":
            counts[row["primary_entity_id"]] += 1
        elif row["issue_type"] == "CURRENCY_MISMATCH":
            campaign_id = cost_campaign.get(row["primary_entity_id"])
            if campaign_id:
                counts[campaign_id] += 1
    return counts


def _table_exists(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()
    return bool(row and row[0])


def compute_campaign_performance(
    conn: duckdb.DuckDBPyConnection, run_dir: Path
) -> list[dict[str, Any]]:
    campaigns = _fetch(conn, "SELECT * FROM v_campaigns ORDER BY campaign_id")
    channels = {row["channel_id"]: row for row in _fetch(conn, "SELECT * FROM channels")}
    cost_rows = _fetch(
        conn,
        """
        SELECT c.campaign_id,
               SUM(CASE WHEN co.currency = c.budget_currency THEN co.amount_dec ELSE 0 END) AS spend,
               COUNT(CASE WHEN co.currency = c.budget_currency THEN 1 END) AS compatible_count,
               COUNT(DISTINCT CASE WHEN co.currency = c.budget_currency THEN co.period END) AS compatible_periods,
               COUNT(CASE WHEN co.currency <> c.budget_currency THEN 1 END) AS incompatible_count
        FROM v_campaigns c
        LEFT JOIN v_costs co ON co.campaign_id = c.campaign_id
        GROUP BY c.campaign_id
        """,
    )
    cost_map = {row["campaign_id"]: row for row in cost_rows}
    attribution = _fetch(
        conn,
        """
        SELECT campaign_id, model, SUM(attributed_revenue_dec) AS attributed_revenue,
               COUNT(DISTINCT order_id) AS conversions,
               COUNT(DISTINCT contact_id) AS unique_contacts,
               COUNT(DISTINCT touchpoint_id) AS touchpoints
        FROM v_attribution_results
        GROUP BY campaign_id, model
        """,
    )
    attribution_map = {(row["campaign_id"], row["model"]): row for row in attribution}
    issue_counts = _campaign_issue_counts(conn)

    rows: list[dict[str, Any]] = []
    for campaign in campaigns:
        cost = cost_map.get(
            campaign["campaign_id"],
            {"spend": Decimal("0.00"), "compatible_count": 0, "incompatible_count": 0},
        )
        budget = d(campaign["budget_dec"])
        spend = d(cost["spend"])
        coverage = cost_coverage(
            budget,
            int(cost["compatible_count"]),
            int(cost["incompatible_count"]),
            _expected_periods(campaign["start_ts"], campaign["end_ts"]),
            int(cost["compatible_periods"] or 0),
        )
        for model in MODELS:
            attr = attribution_map.get(
                (campaign["campaign_id"], model),
                {
                    "attributed_revenue": Decimal("0.00"),
                    "conversions": 0,
                    "unique_contacts": 0,
                    "touchpoints": 0,
                },
            )
            attributed_revenue = d(attr["attributed_revenue"])
            conversions = int(attr["conversions"])
            roi_result = roi(attributed_revenue, spend, coverage)
            roas_result = roas(attributed_revenue, spend, coverage)
            utilization = (
                ds(spend * Decimal(100) / budget)
                if budget > 0 and coverage == "COMPLETE"
                else ""
            )
            cpc = cost_per_conversion(spend, conversions, coverage)
            aov = average_order_value(attributed_revenue, conversions)
            rows.append(
                {
                    "campaign_id": campaign["campaign_id"],
                    "campaign_name": campaign["name"],
                    "campaign_type": campaign["campaign_type"],
                    "objective": campaign["objective"],
                    "primary_channel_id": campaign["primary_channel_id"],
                    "primary_channel_name": channels[campaign["primary_channel_id"]]["name"],
                    "start_at": iso(campaign["start_ts"]),
                    "end_at": iso(campaign["end_ts"]),
                    "status": campaign["status"],
                    "budget_amount": ds(budget),
                    "budget_currency": campaign["budget_currency"],
                    "model": model,
                    "spend": _known_spend(spend, coverage),
                    "spend_currency": campaign["budget_currency"],
                    "cost_coverage": coverage,
                    "attributed_revenue": ds(attributed_revenue),
                    "conversions": conversions,
                    "unique_converting_contacts": int(attr["unique_contacts"]),
                    "touchpoints_credited": int(attr["touchpoints"]),
                    "roi_pct": ds(roi_result.value) if roi_result.available else "",
                    "roas": ds(roas_result.value) if roas_result.available else "",
                    "roi_available": "true" if roi_result.available else "false",
                    "roi_status": roi_result.status,
                    "budget_utilization": utilization,
                    "cost_per_conversion": ds(cpc) if cpc is not None else "",
                    "average_order_value": ds(aov) if aov is not None else "",
                    "issue_count": issue_counts.get(campaign["campaign_id"], 0),
                }
            )

    spec = DERIVED_TABLES["campaign_performance"]
    write_csv(run_dir / "campaign_performance.csv", spec.columns, rows, spec.sort_key)
    refresh_table(conn, run_dir, "campaign_performance")
    create_typed_views(conn)
    return rows


def compute_channel_performance(
    conn: duckdb.DuckDBPyConnection, run_dir: Path, campaign_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    channels = _fetch(conn, "SELECT * FROM channels ORDER BY channel_id")
    spend_by_channel = {
        row["channel_id"]: d(row["spend"])
        for row in _fetch(
            conn,
            """
            SELECT co.channel_id, SUM(co.amount_dec) AS spend
            FROM v_costs co
            JOIN v_campaigns cmp ON cmp.campaign_id = co.campaign_id
            WHERE co.currency = cmp.budget_currency
            GROUP BY co.channel_id
            """,
        )
    }
    coverage_by_channel: dict[str, list[str]] = defaultdict(list)
    budgeted_by_channel: dict[str, int] = defaultdict(int)
    for row in campaign_rows:
        if row["model"] != "linear":
            continue
        if d(row["budget_amount"]) > 0:
            budgeted_by_channel[row["primary_channel_id"]] += 1
            coverage_by_channel[row["primary_channel_id"]].append(row["cost_coverage"])

    attribution = _fetch(
        conn,
        """
        SELECT channel_id, model, SUM(attributed_revenue_dec) AS attributed_revenue,
               COUNT(DISTINCT order_id) AS conversions,
               COUNT(DISTINCT contact_id) AS unique_contacts,
               COUNT(DISTINCT touchpoint_id) AS touchpoints
        FROM v_attribution_results
        GROUP BY channel_id, model
        """,
    )
    attribution_map = {(row["channel_id"], row["model"]): row for row in attribution}

    rows: list[dict[str, Any]] = []
    for channel in channels:
        channel_id = channel["channel_id"]
        spend = spend_by_channel.get(channel_id, Decimal("0.00"))
        statuses = coverage_by_channel.get(channel_id, [])
        if not budgeted_by_channel.get(channel_id, 0):
            coverage = "NO_COST_BASIS"
        elif all(status == "COMPLETE" for status in statuses):
            coverage = "COMPLETE"
        elif all(status == "MISSING" for status in statuses):
            coverage = "MISSING"
        else:
            coverage = "PARTIAL"
        for model in MODELS:
            attr = attribution_map.get(
                (channel_id, model),
                {
                    "attributed_revenue": Decimal("0.00"),
                    "conversions": 0,
                    "unique_contacts": 0,
                    "touchpoints": 0,
                },
            )
            attributed_revenue = d(attr["attributed_revenue"])
            roi_result = roi(attributed_revenue, spend, coverage)
            roas_result = roas(attributed_revenue, spend, coverage)
            rows.append(
                {
                    "channel_id": channel_id,
                    "channel_name": channel["name"],
                    "category": channel["category"],
                    "model": model,
                    "spend": _known_spend(spend, coverage),
                    "spend_currency": "EUR",
                    "cost_coverage": coverage,
                    "attributed_revenue": ds(attributed_revenue),
                    "conversions": int(attr["conversions"]),
                    "unique_converting_contacts": int(attr["unique_contacts"]),
                    "touchpoints_credited": int(attr["touchpoints"]),
                    "roi_pct": ds(roi_result.value) if roi_result.available else "",
                    "roas": ds(roas_result.value) if roas_result.available else "",
                    "roi_available": "true" if roi_result.available else "false",
                    "roi_status": roi_result.status,
                }
            )

    spec = DERIVED_TABLES["channel_performance"]
    write_csv(run_dir / "channel_performance.csv", spec.columns, rows, spec.sort_key)
    refresh_table(conn, run_dir, "channel_performance")
    create_typed_views(conn)
    return rows


def compute_financial_reconciliation(
    conn: duckdb.DuckDBPyConnection,
    run_dir: Path,
    campaign_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    linear_rows = [row for row in campaign_rows if row["model"] == "linear"]
    budgeted = [row for row in linear_rows if d(row["budget_amount"]) > 0]
    complete_ids = {row["campaign_id"] for row in budgeted if row["cost_coverage"] == "COMPLETE"}
    missing_count = sum(1 for row in budgeted if row["cost_coverage"] == "MISSING")
    partial_count = sum(1 for row in budgeted if row["cost_coverage"] == "PARTIAL")
    recorded_spend = sum((d(row["spend"]) for row in linear_rows), Decimal("0.00"))
    covered_spend = sum(
        (d(row["spend"]) for row in linear_rows if row["campaign_id"] in complete_ids), Decimal("0.00")
    )
    incompatible_costs = conn.execute(
        "SELECT COUNT(*) FROM v_costs co JOIN v_campaigns c ON c.campaign_id = co.campaign_id "
        "WHERE co.currency <> c.budget_currency"
    ).fetchone()[0]

    rows: list[dict[str, Any]] = []
    for model in MODELS:
        totals = conn.execute(
            """
            SELECT COALESCE(SUM(conversion_revenue_dec), 0), COALESCE(SUM(attributed_revenue_dec), 0)
            FROM v_attribution_conversions WHERE model = ?
            """,
            [model],
        ).fetchone()
        eligible_revenue = d(totals[0])
        attributed_revenue = d(totals[1])
        covered_attributed = d(
            conn.execute(
                """
                SELECT COALESCE(SUM(attributed_revenue_dec), 0)
                FROM v_attribution_results WHERE model = ?
                """,
                [model],
            ).fetchone()[0]
        )
        if complete_ids:
            placeholders = ", ".join("?" for _ in complete_ids)
            covered_attributed = d(
                conn.execute(
                    f"SELECT COALESCE(SUM(attributed_revenue_dec), 0) FROM v_attribution_results "
                    f"WHERE model = ? AND campaign_id IN ({placeholders})",
                    [model, *sorted(complete_ids)],
                ).fetchone()[0]
            )
        status = "COVERAGE_COMPLETE" if not missing_count and not partial_count else "COVERAGE_INCOMPLETE"
        covered_roi = roi(covered_attributed, covered_spend, "COMPLETE")
        covered_roas = roas(covered_attributed, covered_spend, "COMPLETE")
        overall_roi = roi(attributed_revenue, recorded_spend, "COMPLETE" if status == "COVERAGE_COMPLETE" else "PARTIAL")
        overall_roas = roas(attributed_revenue, recorded_spend, "COMPLETE" if status == "COVERAGE_COMPLETE" else "PARTIAL")
        detail = (
            f"{len(complete_ids)}/{len(budgeted)} budgeted campaigns have complete compatible cost coverage; "
            f"{missing_count} missing, {partial_count} partial, {incompatible_costs} incompatible cost records quarantined."
        )
        rows.append(
            {
                "scope": "overall",
                "model": model,
                "currency": "EUR",
                "eligible_conversion_revenue": ds(eligible_revenue),
                "attributed_revenue": ds(attributed_revenue),
                "unattributed_revenue": ds(eligible_revenue - attributed_revenue),
                "recorded_spend": ds(recorded_spend),
                "covered_spend": ds(covered_spend),
                "covered_attributed_revenue": ds(covered_attributed),
                "roi_pct": ds(overall_roi.value) if overall_roi.available else "",
                "roas": ds(overall_roas.value) if overall_roas.available else "",
                "status": status,
                "detail": detail,
            }
        )
        rows.append(
            {
                "scope": "fully_covered_campaigns",
                "model": model,
                "currency": "EUR",
                "eligible_conversion_revenue": ds(eligible_revenue),
                "attributed_revenue": ds(attributed_revenue),
                "unattributed_revenue": ds(eligible_revenue - attributed_revenue),
                "recorded_spend": ds(recorded_spend),
                "covered_spend": ds(covered_spend),
                "covered_attributed_revenue": ds(covered_attributed),
                "roi_pct": ds(covered_roi.value) if covered_roi.available else "",
                "roas": ds(covered_roas.value) if covered_roas.available else "",
                "status": "COMPLETE_COST_BASIS" if covered_spend > 0 else "NO_COVERED_SPEND",
                "detail": (
                    "ROI is scoped to campaigns whose actual spend coverage is complete. "
                    + detail
                ),
            }
        )

    spec = DERIVED_TABLES["financial_reconciliation"]
    write_csv(run_dir / "financial_reconciliation.csv", spec.columns, rows, spec.sort_key)
    refresh_table(conn, run_dir, "financial_reconciliation")
    create_typed_views(conn)
    return rows


def compute_summary(
    conn: duckdb.DuckDBPyConnection,
    config: RunConfig,
    run_dir: Path,
    campaign_rows: list[dict[str, Any]],
    channel_rows: list[dict[str, Any]],
    reconciliation: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = _fetch(
        conn,
        """
        SELECT
          (SELECT COUNT(*) FROM campaigns) AS campaigns,
          (SELECT COUNT(*) FROM contacts) AS contacts,
          (SELECT COUNT(*) FROM touchpoints) AS touchpoints,
          (SELECT COUNT(*) FROM sessions) AS sessions,
          (SELECT COUNT(*) FROM opportunities) AS opportunities,
          (SELECT COUNT(*) FROM orders) AS orders,
          (SELECT COUNT(*) FROM cost_records) AS cost_records,
          (SELECT COUNT(*) FROM leads) AS leads,
          (SELECT COUNT(*) FROM attribution_results) AS attribution_results
        """,
    )[0]

    conversion_stats = _fetch(
        conn,
        """
        SELECT model, COUNT(*) AS outcomes,
               SUM(CASE WHEN status = 'ATTRIBUTED' THEN 1 ELSE 0 END) AS attributed,
               SUM(CASE WHEN status = 'UNATTRIBUTED' THEN 1 ELSE 0 END) AS unattributed,
               SUM(conversion_revenue_dec) AS eligible_revenue,
               SUM(attributed_revenue_dec) AS attributed_revenue
        FROM v_attribution_conversions GROUP BY model ORDER BY model
        """,
    )
    conversion_by_model = {row["model"]: row for row in conversion_stats}
    linear_conversions = conversion_by_model.get("linear", {})

    issues = _fetch(
        conn,
        "SELECT issue_type, severity, COUNT(*) AS count FROM exceptions GROUP BY issue_type, severity "
        "ORDER BY issue_type",
    )
    total_issues = sum(int(row["count"]) for row in issues)
    high_issues = sum(int(row["count"]) for row in issues if row["severity"] == "HIGH")

    identity = conn.execute(
        """
        WITH supported AS (
            SELECT session_id, contact_id FROM v_identity_links
            WHERE status = 'VERIFIED' AND trim(evidence_ref) <> ''
              AND evidence_type IN ('AUTHENTICATED_LOGIN', 'EMAIL_CLICK_SSO', 'FORM_SUBMIT_MATCH', 'CRM_IMPORT_MATCH')
        )
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN t.contact_id IS NOT NULL OR s.contact_id IS NOT NULL THEN 1 ELSE 0 END) AS resolved
        FROM v_touchpoints t LEFT JOIN supported s ON s.session_id = t.session_id
        """
    ).fetchone()
    identity_coverage = _pct(int(identity[1] or 0), int(identity[0] or 0))

    cost = _fetch(
        conn,
        """
        SELECT
          SUM(CASE WHEN co.currency = c.budget_currency THEN co.amount_dec ELSE 0 END) AS spend,
          COUNT(CASE WHEN co.currency <> c.budget_currency THEN 1 END) AS incompatible
        FROM v_costs co JOIN v_campaigns c ON c.campaign_id = co.campaign_id
        """,
    )[0]
    recorded_spend = d(cost["spend"])
    budgeted = [row for row in campaign_rows if row["model"] == "linear" and d(row["budget_amount"]) > 0]
    complete = [row for row in budgeted if row["cost_coverage"] == "COMPLETE"]
    missing = [row for row in budgeted if row["cost_coverage"] == "MISSING"]
    partial = [row for row in budgeted if row["cost_coverage"] == "PARTIAL"]
    covered_rows = [row for row in campaign_rows if row["model"] == "linear" and row["cost_coverage"] == "COMPLETE"]
    covered_spend = sum((d(row["spend"]) for row in covered_rows), Decimal("0.00"))
    covered_revenue = sum((d(row["attributed_revenue"]) for row in covered_rows), Decimal("0.00"))
    covered_roi = roi(covered_revenue, covered_spend, "COMPLETE")
    covered_roas = roas(covered_revenue, covered_spend, "COMPLETE")

    monthly_revenue = {
        row["month"]: row
        for row in _fetch(
            conn,
            """
            SELECT strftime(o.ordered_ts, '%Y-%m') AS month,
                   SUM(ac.attributed_revenue_dec) AS attributed_revenue,
                   SUM(ac.conversion_revenue_dec) AS eligible_revenue,
                   SUM(CASE WHEN ac.status = 'ATTRIBUTED' THEN 1 ELSE 0 END) AS attributed_conversions
            FROM v_attribution_conversions ac
            JOIN v_orders o ON o.order_id = ac.order_id
            WHERE ac.model = 'linear'
            GROUP BY 1 ORDER BY 1
            """,
        )
    }
    monthly_spend = {
        row["month"]: d(row["spend"])
        for row in _fetch(
            conn,
            """
            SELECT strftime(co.cost_date_d, '%Y-%m') AS month, SUM(co.amount_dec) AS spend
            FROM v_costs co JOIN v_campaigns c ON c.campaign_id = co.campaign_id
            WHERE co.currency = c.budget_currency
            GROUP BY 1 ORDER BY 1
            """,
        )
    }
    month_cursor = date(2025, 9, 1)
    months: list[str] = []
    while month_cursor <= date(2026, 9, 1):
        months.append(month_cursor.strftime("%Y-%m"))
        month_cursor = date(
            month_cursor.year + (1 if month_cursor.month == 12 else 0),
            1 if month_cursor.month == 12 else month_cursor.month + 1,
            1,
        )
    monthly = [
        {
            "month": month,
            "attributed_revenue": ds(d(monthly_revenue.get(month, {}).get("attributed_revenue"))),
            "eligible_revenue": ds(d(monthly_revenue.get(month, {}).get("eligible_revenue"))),
            "spend": ds(monthly_spend.get(month, Decimal("0.00"))),
            "attributed_conversions": int(monthly_revenue.get(month, {}).get("attributed_conversions") or 0),
        }
        for month in months
    ]

    model_comparison = []
    for model in MODELS:
        row = conversion_by_model.get(model, {})
        model_comparison.append(
            {
                "model": model,
                "eligible_revenue": ds(d(row.get("eligible_revenue"))),
                "attributed_revenue": ds(d(row.get("attributed_revenue"))),
                "attributed_conversions": int(row.get("attributed") or 0),
                "unattributed_conversions": int(row.get("unattributed") or 0),
            }
        )

    channel_contribution = [
        {
            "channel_id": row["channel_id"],
            "channel_name": row["channel_name"],
            "category": row["category"],
            "attributed_revenue": row["attributed_revenue"],
            "conversions": row["conversions"],
            "spend": row["spend"] or None,
            "roi_pct": row["roi_pct"],
            "roi_available": row["roi_available"],
        }
        for row in sorted(
            (item for item in channel_rows if item["model"] == "linear"),
            key=lambda item: d(item["attributed_revenue"]),
            reverse=True,
        )
    ]
    top_campaigns = [
        {
            "campaign_id": row["campaign_id"],
            "campaign_name": row["campaign_name"],
            "channel_name": row["primary_channel_name"],
            "attributed_revenue": row["attributed_revenue"],
            "spend": row["spend"] or None,
            "roi_pct": row["roi_pct"],
            "roi_available": row["roi_available"],
            "cost_coverage": row["cost_coverage"],
        }
        for row in sorted(
            (item for item in campaign_rows if item["model"] == "linear"),
            key=lambda item: d(item["attributed_revenue"]),
            reverse=True,
        )[:10]
    ]

    eligible_revenue = d(linear_conversions.get("eligible_revenue"))
    attributed_revenue = d(linear_conversions.get("attributed_revenue"))
    eligible_conversions = int(linear_conversions.get("outcomes") or 0)
    attributed_conversions = int(linear_conversions.get("attributed") or 0)
    revenue_coverage = _pct(attributed_revenue, eligible_revenue)
    conversion_coverage = _pct(attributed_conversions, eligible_conversions)
    summary = {
        "run_id": config.run_id,
        "profile": config.profile,
        "seed": config.seed,
        "reporting_currency": config.reporting_currency,
        "lookback_days": config.lookback_days,
        "splits": [
            {"name": split.name, "start": split.start.isoformat(), "end_exclusive": split.end_exclusive.isoformat()}
            for split in SPLITS
        ],
        "kpis": {
            "campaigns": int(counts["campaigns"]),
            "contacts": int(counts["contacts"]),
            "touchpoints": int(counts["touchpoints"]),
            "sessions": int(counts["sessions"]),
            "leads": int(counts["leads"]),
            "opportunities": int(counts["opportunities"]),
            "orders": int(counts["orders"]),
            "eligible_conversions": eligible_conversions,
            "attributed_conversions": attributed_conversions,
            "attributed_revenue": ds(attributed_revenue),
            "eligible_conversion_revenue": ds(eligible_revenue),
            "recorded_spend": ds(recorded_spend),
            "roi_pct": ds(covered_roi.value) if covered_roi.available else "",
            "roas": ds(covered_roas.value) if covered_roas.available else "",
            "roi_available": covered_roi.available,
            "roi_scope": "fully_costed_campaigns",
            "roi_status": covered_roi.status,
            "unattributed_conversions": int(linear_conversions.get("unattributed") or 0),
            "unattributed_revenue": ds(eligible_revenue - attributed_revenue),
            "revenue_coverage_pct": revenue_coverage,
            "conversion_coverage_pct": conversion_coverage,
            "conversion_rate_pct": ds(conversion_rate(eligible_conversions, int(counts["opportunities"])) or Decimal("0")),
            "data_quality_issues": total_issues,
            "high_severity_issues": high_issues,
            "identity_coverage_pct": identity_coverage,
            "cost_coverage_pct": _pct(len(complete), len(budgeted)),
            "complete_cost_campaigns": len(complete),
            "partial_cost_campaigns": len(partial),
            "missing_cost_campaigns": len(missing),
            "budgeted_campaigns": len(budgeted),
            "incompatible_cost_records": int(cost["incompatible"] or 0),
            "attribution_results": int(counts["attribution_results"]),
        },
        "financials": {
            "recorded_spend": ds(recorded_spend),
            "covered_spend": ds(covered_spend),
            "covered_attributed_revenue": ds(covered_revenue),
            "covered_roas_numerator": ds(covered_revenue),
            "covered_roas_denominator": ds(covered_spend),
            "covered_campaigns": len(complete),
            "budgeted_campaigns": len(budgeted),
            "covered_roi_pct": ds(covered_roi.value) if covered_roi.available else "",
            "covered_roas": ds(covered_roas.value) if covered_roas.available else "",
            "roi_available": covered_roi.available,
            "roi_status": covered_roi.status,
            "reconciliation_status": reconciliation[0]["status"] if reconciliation else "",
            "coverage_detail": reconciliation[0]["detail"] if reconciliation else "",
        },
        "attribution_by_model": {
            model: {
                "eligible_revenue": ds(d(conversion_by_model.get(model, {}).get("eligible_revenue"))),
                "attributed_revenue": ds(d(conversion_by_model.get(model, {}).get("attributed_revenue"))),
                "attributed_conversions": int(conversion_by_model.get(model, {}).get("attributed") or 0),
                "unattributed_conversions": int(conversion_by_model.get(model, {}).get("unattributed") or 0),
            }
            for model in MODELS
        },
        "model_comparison": model_comparison,
        "monthly": monthly,
        "channel_contribution": channel_contribution,
        "top_campaigns": top_campaigns,
        "anomaly_distribution": [
            {
                "issue_type": row["issue_type"],
                "severity": row["severity"],
                "count": int(row["count"]),
            }
            for row in issues
        ],
        "data_quality_status": "ATTENTION_REQUIRED" if total_issues else "OK",
        "notice": (
            "All records are synthetic. Exceptions include deliberate, ground-truth-labelled "
            "fixtures used to evaluate detection quality."
        ),
    }
    write_json(run_dir / "summary.json", summary)
    return summary


def compute_analytics(
    conn: duckdb.DuckDBPyConnection, config: RunConfig, run_dir: Path
) -> dict[str, Any]:
    campaign_rows = compute_campaign_performance(conn, run_dir)
    channel_rows = compute_channel_performance(conn, run_dir, campaign_rows)
    reconciliation = compute_financial_reconciliation(conn, run_dir, campaign_rows)
    summary = compute_summary(conn, config, run_dir, campaign_rows, channel_rows, reconciliation)
    return {
        "campaigns": len({row["campaign_id"] for row in campaign_rows}),
        "channels": len({row["channel_id"] for row in channel_rows}),
        "summary": summary,
    }

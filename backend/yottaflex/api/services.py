"""Read models used by the API. Queries keep presentation shaping out of routes."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import duckdb

from yottaflex.api.deps import (
    RunContext,
    boolean,
    integer,
    money,
    number,
    one,
    read_json_file,
    rows,
    split_evidence,
)
from yottaflex.config import MODELS, split_for_timestamp
from yottaflex.domain.attribution import (
    EXCLUDED_COUNT_FIELDS,
    Conversion,
    TouchCandidate,
    allocate_credit,
    classify_touch,
    exclusion_counts,
    reconciliation_difference,
)
from yottaflex.domain.identity import IdentityLink, build_session_resolution

RECONCILIATION_TOLERANCE = Decimal("0.005")
CREDIT_FRACTION_TOLERANCE = Decimal("0.000001")


def _round_pct(value: float) -> float:
    """Round a percentage without producing a signed negative zero."""

    rounded = round(value, 2)
    return 0.0 if rounded == 0 else rounded


def _allocation_check(
    conn: duckdb.DuckDBPyConnection,
    conversion: Conversion,
    model: str,
    eligible: list[Any],
) -> dict[str, Any]:
    """Compare recomputed allocations against persisted allocation rows.

    Equal conversion-level revenue does not prove that every touchpoint credit
    matches, so each recomputed allocation is compared with the persisted
    `attribution_results` row for the same order, model and touchpoint.
    """

    computed = allocate_credit(conversion, eligible, model)
    persisted_rows = {
        row["touchpoint_id"]: row
        for row in rows(
            conn,
            "SELECT * FROM v_attribution_results WHERE order_id = ? AND model = ?",
            [conversion.order_id, model],
        )
    }
    computed_map = {row.touchpoint_id: row for row in computed}
    differences: list[dict[str, Any]] = []
    for touchpoint_id in sorted(set(computed_map) | set(persisted_rows)):
        recomputed = computed_map.get(touchpoint_id)
        stored = persisted_rows.get(touchpoint_id)
        if recomputed is None or stored is None:
            differences.append(
                {
                    "touchpoint_id": touchpoint_id,
                    "reason": "MISSING_ON_PERSISTED" if recomputed else "MISSING_ON_RECOMPUTED",
                }
            )
            continue
        fraction_delta = abs(
            recomputed.credit_fraction - Decimal(str(stored["credit_fraction_dec"]))
        )
        revenue_delta = abs(
            recomputed.attributed_revenue - Decimal(str(stored["attributed_revenue_dec"]))
        )
        if fraction_delta > CREDIT_FRACTION_TOLERANCE or revenue_delta > RECONCILIATION_TOLERANCE:
            differences.append(
                {
                    "touchpoint_id": touchpoint_id,
                    "reason": "VALUE_MISMATCH",
                    "credit_fraction_delta": float(fraction_delta),
                    "attributed_revenue_delta": float(revenue_delta),
                    "recomputed_revenue": float(recomputed.attributed_revenue),
                    "persisted_revenue": float(stored["attributed_revenue_dec"]),
                }
            )
    return {
        "model": model,
        "recomputed_allocations": len(computed),
        "persisted_allocations": len(persisted_rows),
        "compared_touchpoints": len(set(computed_map) | set(persisted_rows)),
        "matched": not differences,
        "difference_count": len(differences),
        "differences": differences[:10],
        "tolerance": {
            "attributed_revenue": float(RECONCILIATION_TOLERANCE),
            "credit_fraction": float(CREDIT_FRACTION_TOLERANCE),
        },
        "basis": "per-touchpoint allocation comparison (order + model + touchpoint)",
        "comparison": "full_precision_absolute_difference",
    }


def summary(run: RunContext) -> dict[str, Any]:
    payload = read_json_file(run.run_dir / "summary.json")
    payload["run"] = {
        "run_id": run.run_id,
        "profile": run.manifest.get("profile"),
        "seed": run.manifest.get("seed"),
        "generated_at": run.manifest.get("generated_at"),
        "status": run.manifest.get("status"),
        "combined_hash": run.manifest.get("combined_hash"),
    }
    validation_path = run.run_dir / "validation_report.json"
    if validation_path.exists():
        validation = read_json_file(validation_path)
        payload["validation"] = validation.get("summary")
    evaluation_path = run.run_dir / "evaluation.json"
    if evaluation_path.exists():
        evaluation = read_json_file(evaluation_path)
        payload["evaluation"] = {
            "status": evaluation.get("status"),
            "totals": evaluation.get("totals"),
        }
    return payload


CAMPAIGN_SORTS = {
    "attributed_revenue": "TRY_CAST(attributed_revenue AS DECIMAL(18,2))",
    "spend": "TRY_CAST(spend AS DECIMAL(18,2))",
    "roi_pct": "TRY_CAST(roi_pct AS DECIMAL(18,2))",
    "conversions": "TRY_CAST(conversions AS INTEGER)",
    "issue_count": "TRY_CAST(issue_count AS INTEGER)",
    "campaign_name": "campaign_name",
}


def _campaign_filters(
    model: str,
    channel_id: str | None,
    search: str | None,
    coverage: str | None,
    min_revenue: float | None,
) -> tuple[str, list[Any]]:
    clauses = ["model = ?"]
    params: list[Any] = [model]
    if channel_id:
        clauses.append("primary_channel_id = ?")
        params.append(channel_id)
    if search:
        clauses.append("(lower(campaign_name) LIKE ? OR lower(campaign_id) LIKE ?)")
        needle = f"%{search.lower()}%"
        params.extend([needle, needle])
    if coverage:
        clauses.append("cost_coverage = ?")
        params.append(coverage)
    if min_revenue is not None:
        clauses.append("CAST(attributed_revenue AS DECIMAL(18,2)) >= ?")
        params.append(min_revenue)
    return " AND ".join(clauses), params


def list_campaigns(
    conn: duckdb.DuckDBPyConnection,
    model: str,
    limit: int = 50,
    offset: int = 0,
    sort: str = "attributed_revenue",
    order: str = "desc",
    channel_id: str | None = None,
    search: str | None = None,
    coverage: str | None = None,
    min_revenue: float | None = None,
) -> dict[str, Any]:
    model = model if model in MODELS else "linear"
    where, params = _campaign_filters(model, channel_id, search, coverage, min_revenue)
    sort_expression = CAMPAIGN_SORTS.get(sort, CAMPAIGN_SORTS["attributed_revenue"])
    direction = "ASC" if order.lower() == "asc" else "DESC"
    total = conn.execute(
        f"SELECT COUNT(*) FROM v_campaign_performance WHERE {where}", params
    ).fetchone()[0]
    aggregates = one(
        conn,
        f"""
        SELECT COALESCE(SUM(CAST(attributed_revenue AS DECIMAL(18,2))), 0) AS revenue,
               SUM(TRY_CAST(spend AS DECIMAL(18,2))) AS spend,
               COALESCE(SUM(CAST(conversions AS INTEGER)), 0) AS conversions,
               COUNT(CASE WHEN spend IS NOT NULL THEN 1 END) AS spend_known_campaigns,
               COUNT(CASE WHEN cost_coverage = 'MISSING' THEN 1 END) AS spend_missing_campaigns,
               COUNT(CASE WHEN cost_coverage = 'NO_COST_BASIS' THEN 1 END) AS spend_no_cost_basis_campaigns,
               COUNT(CASE WHEN roi_available THEN 1 END) AS roi_campaigns,
               AVG(CASE WHEN roi_available THEN TRY_CAST(roi_pct AS DOUBLE) END) AS avg_roi
        FROM v_campaign_performance WHERE {where}
        """,
        params,
    ) or {}
    records = rows(
        conn,
        f"""
        SELECT * FROM v_campaign_performance
        WHERE {where}
        ORDER BY {sort_expression} {direction} NULLS LAST, campaign_id ASC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    )
    items = []
    for record in records:
        items.append(
            {
                "campaign_id": record["campaign_id"],
                "campaign_name": record["campaign_name"],
                "campaign_type": record["campaign_type"],
                "objective": record["objective"],
                "primary_channel_id": record["primary_channel_id"],
                "primary_channel_name": record["primary_channel_name"],
                "start_at": record["start_at"],
                "end_at": record["end_at"],
                "status": record["status"],
                "model": record["model"],
                "budget_amount": money(record["budget_amount"]),
                "budget_currency": record["budget_currency"],
                "spend": money(record["spend"]),
                "cost_coverage": record["cost_coverage"],
                "attributed_revenue": money(record["attributed_revenue"]),
                "conversions": integer(record["conversions"]),
                "unique_converting_contacts": integer(record["unique_converting_contacts"]),
                "touchpoints_credited": integer(record["touchpoints_credited"]),
                "roi_pct": number(record["roi_pct"]),
                "roas": number(record["roas"]),
                "roi_available": boolean(record["roi_available"]),
                "roi_status": record["roi_status"],
                "budget_utilization": number(record["budget_utilization"]),
                "cost_per_conversion": number(record["cost_per_conversion"]),
                "average_order_value": number(record["average_order_value"]),
                "issue_count": integer(record["issue_count"]),
            }
        )
    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "model": model,
        "currency": run_currency(conn),
        "aggregates": {
            "attributed_revenue": money(aggregates.get("revenue")),
            "spend": money(aggregates.get("spend")),
            "spend_known_campaigns": integer(aggregates.get("spend_known_campaigns")),
            "spend_missing_campaigns": integer(aggregates.get("spend_missing_campaigns")),
            "spend_no_cost_basis_campaigns": integer(
                aggregates.get("spend_no_cost_basis_campaigns")
            ),
            "conversions": integer(aggregates.get("conversions")),
            "average_roi_pct": number(aggregates.get("avg_roi")),
            "roi_campaigns": integer(aggregates.get("roi_campaigns")),
        },
    }


CAMPAIGN_EXPORT_COLUMNS = (
    "campaign_id",
    "campaign_name",
    "campaign_type",
    "objective",
    "primary_channel_id",
    "primary_channel_name",
    "start_at",
    "end_at",
    "status",
    "model",
    "budget_amount",
    "budget_currency",
    "spend",
    "spend_currency",
    "cost_coverage",
    "attributed_revenue",
    "conversions",
    "unique_converting_contacts",
    "touchpoints_credited",
    "roi_pct",
    "roas",
    "roi_status",
    "cost_per_conversion",
    "average_order_value",
    "issue_count",
)


def campaign_export(
    conn: duckdb.DuckDBPyConnection,
    model: str,
    sort: str = "attributed_revenue",
    order: str = "desc",
    channel_id: str | None = None,
    search: str | None = None,
    coverage: str | None = None,
    min_revenue: float | None = None,
) -> tuple[tuple[str, ...], list[list[str]]]:
    """Return the same filtered, sorted campaign view that the table displays."""

    model = model if model in MODELS else "linear"
    where, params = _campaign_filters(model, channel_id, search, coverage, min_revenue)
    sort_expression = CAMPAIGN_SORTS.get(sort, CAMPAIGN_SORTS["attributed_revenue"])
    direction = "ASC" if order.lower() == "asc" else "DESC"
    records = rows(
        conn,
        f"""
        SELECT {", ".join(CAMPAIGN_EXPORT_COLUMNS)}
        FROM v_campaign_performance
        WHERE {where}
        ORDER BY {sort_expression} {direction} NULLS LAST, campaign_id ASC
        """,
        params,
    )
    output = [
        ["" if record[column] is None else str(record[column]) for column in CAMPAIGN_EXPORT_COLUMNS]
        for record in records
    ]
    return CAMPAIGN_EXPORT_COLUMNS, output


CAMPAIGN_EXPORT_NUMERIC_COLUMNS = {
    "budget_amount",
    "spend",
    "attributed_revenue",
    "conversions",
    "unique_converting_contacts",
    "touchpoints_credited",
    "roi_pct",
    "roas",
    "cost_per_conversion",
    "average_order_value",
    "issue_count",
}


def campaign_export_records(
    conn: duckdb.DuckDBPyConnection,
    model: str,
    sort: str = "attributed_revenue",
    order: str = "desc",
    channel_id: str | None = None,
    search: str | None = None,
    coverage: str | None = None,
    min_revenue: float | None = None,
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    """Return the filtered campaign view with typed values for analyst exports."""

    model = model if model in MODELS else "linear"
    where, params = _campaign_filters(model, channel_id, search, coverage, min_revenue)
    sort_expression = CAMPAIGN_SORTS.get(sort, CAMPAIGN_SORTS["attributed_revenue"])
    direction = "ASC" if order.lower() == "asc" else "DESC"
    raw = rows(
        conn,
        f"""
        SELECT {", ".join(CAMPAIGN_EXPORT_COLUMNS)}
        FROM v_campaign_performance
        WHERE {where}
        ORDER BY {sort_expression} {direction} NULLS LAST, campaign_id ASC
        """,
        params,
    )
    records: list[dict[str, Any]] = []
    for record in raw:
        item: dict[str, Any] = {}
        for column in CAMPAIGN_EXPORT_COLUMNS:
            value = record[column]
            if column in CAMPAIGN_EXPORT_NUMERIC_COLUMNS:
                item[column] = number(value) if value is not None else None
            elif isinstance(value, Decimal):
                item[column] = float(value)
            else:
                item[column] = value
        records.append(item)
    return CAMPAIGN_EXPORT_COLUMNS, records


def export_summary_rows(
    records: list[dict[str, Any]], model: str, totals: dict[str, Any]
) -> list[tuple[str, Any]]:
    """Reconciliation summary for the exported (filtered) campaign set."""

    spend_total = sum(record["spend"] for record in records if record.get("spend") is not None)
    unknown_spend = sum(1 for record in records if record.get("spend") is None)
    attributed = sum(
        record["attributed_revenue"]
        for record in records
        if record.get("attributed_revenue") is not None
    )
    conversions = sum(record["conversions"] or 0 for record in records)
    coverage_counts: dict[str, int] = {}
    for record in records:
        key = record.get("cost_coverage") or "UNKNOWN"
        coverage_counts[key] = coverage_counts.get(key, 0) + 1
    roi_values = [
        record["roi_pct"]
        for record in records
        if record.get("roi_pct") is not None and record.get("roi_available", True)
    ]
    mean_roi = round(sum(roi_values) / len(roi_values), 2) if roi_values else None
    return [
        ("Campaigns in export", len(records)),
        ("Attribution model", model),
        ("Attributed revenue (filtered set)", round(attributed, 2)),
        ("Attributed conversions (filtered set)", conversions),
        ("Recorded spend (filtered set)", round(spend_total, 2)),
        ("Campaigns with unknown spend", unknown_spend),
        ("Campaigns with eligible ROI", len(roi_values)),
        ("Mean campaign ROI % (unweighted)", mean_roi),
        ("Cost coverage mix", ", ".join(f"{key}={value}" for key, value in sorted(coverage_counts.items()))),
        (
            "Model total attributed revenue (unfiltered)",
            round(float(totals.get("attributed_revenue") or 0), 2),
        ),
        (
            "Model total conversions (unfiltered)",
            totals.get("conversions"),
        ),
        (
            "Filtered share of model revenue %",
            round(attributed * 100 / float(totals.get("attributed_revenue") or 1), 2),
        ),
    ]


def export_attribution_sheet(
    conn: duckdb.DuckDBPyConnection, model: str
) -> tuple[list[str], list[dict[str, Any]]]:
    """Per-model, per-channel attributed revenue with share of model revenue."""

    channel_rows = rows(
        conn,
        """
        SELECT model, channel_id, channel_name,
               CAST(attributed_revenue AS DECIMAL(18,2)) AS attributed_revenue,
               CAST(conversions AS INTEGER) AS conversions
        FROM v_channel_performance
        ORDER BY model, CAST(attributed_revenue AS DECIMAL(18,2)) DESC
        """,
    )
    totals: dict[str, float] = {}
    for record in channel_rows:
        totals[record["model"]] = totals.get(record["model"], 0.0) + float(
            record["attributed_revenue"] or 0
        )
    records = []
    for record in channel_rows:
        total = totals.get(record["model"]) or 0.0
        revenue = float(record["attributed_revenue"] or 0)
        records.append(
            {
                "model": record["model"],
                "channel_id": record["channel_id"],
                "channel_name": record["channel_name"],
                "attributed_revenue": round(revenue, 2),
                "conversions": int(record["conversions"] or 0),
                "share_of_model_pct": round(revenue * 100 / total, 2) if total else None,
            }
        )
    header = [
        "model",
        "channel_id",
        "channel_name",
        "attributed_revenue",
        "conversions",
        "share_of_model_pct",
    ]
    return header, records


def export_data_quality_sheet(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Open issue counts by type and severity for the exported run."""

    type_rows = rows(
        conn,
        "SELECT issue_type, severity, COUNT(*) AS count FROM v_exceptions "
        "GROUP BY issue_type, severity ORDER BY count DESC, issue_type",
    )
    records = [
        {
            "issue_type": record["issue_type"],
            "severity": record["severity"],
            "count": int(record["count"] or 0),
        }
        for record in type_rows
    ]
    return ["issue_type", "severity", "count"], records


def run_currency(conn: duckdb.DuckDBPyConnection) -> str:
    row = conn.execute("SELECT currency FROM financial_reconciliation LIMIT 1").fetchone()
    return row[0] if row else "EUR"


def list_channel_options(conn: duckdb.DuckDBPyConnection, model: str = "linear") -> list[dict[str, Any]]:
    records = rows(
        conn,
        """
        SELECT c.channel_id, c.name, c.category,
               CAST(p.spend AS DECIMAL(18,2)) AS spend,
               CAST(p.attributed_revenue AS DECIMAL(18,2)) AS attributed_revenue,
               p.cost_coverage,
               CAST(p.roi_pct AS DECIMAL(18,2)) AS roi_pct,
               p.roi_available
        FROM v_channels c
        LEFT JOIN v_channel_performance p ON p.channel_id = c.channel_id AND p.model = ?
        ORDER BY CAST(p.attributed_revenue AS DECIMAL(18,2)) DESC NULLS LAST, c.name
        """,
        [model],
    )
    return [
        {
            "channel_id": record["channel_id"],
            "channel_name": record["name"],
            "category": record["category"],
            "spend": money(record["spend"]),
            "attributed_revenue": money(record["attributed_revenue"]),
            "cost_coverage": record["cost_coverage"],
            "roi_pct": number(record["roi_pct"]),
            "roi_available": boolean(record["roi_available"]),
        }
        for record in records
    ]


def campaign_detail(
    conn: duckdb.DuckDBPyConnection, campaign_id: str, model: str
) -> dict[str, Any] | None:
    model = model if model in MODELS else "linear"
    campaign = one(
        conn,
        """
        SELECT campaign_id, name AS campaign_name, campaign_type, objective,
               primary_channel_id, target_audience_id, start_ts AS start_at, end_ts AS end_at,
               status, budget_dec AS budget_amount, budget_currency
        FROM v_campaigns WHERE campaign_id = ?
        """,
        [campaign_id],
    )
    if not campaign:
        return None
    model_rows = rows(
        conn,
        "SELECT * FROM v_campaign_performance WHERE campaign_id = ? ORDER BY model",
        [campaign_id],
    )
    selected = next((row for row in model_rows if row["model"] == model), None)
    costs = rows(
        conn,
        """
        SELECT cost_id, cost_date_d AS cost_date,
               CAST(amount_dec AS DECIMAL(18,2)) AS amount_value,
               currency, cost_category, source_ref, period
        FROM v_costs WHERE campaign_id = ? ORDER BY cost_date_d, cost_id
        """,
        [campaign_id],
    )
    channels = rows(
        conn,
        """
        SELECT r.channel_id, ch.name AS channel_name, ch.category,
               SUM(CAST(r.attributed_revenue_dec AS DECIMAL(18,2))) AS attributed_revenue,
               COUNT(DISTINCT r.order_id) AS conversions,
               COUNT(DISTINCT r.touchpoint_id) AS touchpoints
        FROM v_attribution_results r
        JOIN v_channels ch ON ch.channel_id = r.channel_id
        WHERE r.campaign_id = ? AND r.model = ?
        GROUP BY r.channel_id, ch.name, ch.category
        ORDER BY attributed_revenue DESC
        """,
        [campaign_id, model],
    )
    creatives = rows(
        conn,
        "SELECT creative_id, name, creative_type, status FROM creatives WHERE campaign_id = ? "
        "ORDER BY creative_id",
        [campaign_id],
    )
    issues = rows(
        conn,
        """
        SELECT issue_id, issue_type, severity, primary_entity_id, affected_record_ids,
               explanation, suggested_disposition, status, split
        FROM v_exceptions
        WHERE primary_entity_id = ? OR list_contains(string_split(affected_record_ids, '|'), ?)
        ORDER BY CASE severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END, issue_id
        """,
        [campaign_id, campaign_id],
    )
    monthly = rows(
        conn,
        """
        SELECT strftime(o.ordered_ts, '%Y-%m') AS month,
               SUM(CAST(r.attributed_revenue_dec AS DECIMAL(18,2))) AS attributed_revenue,
               COUNT(DISTINCT r.order_id) AS conversions
        FROM v_attribution_results r
        JOIN v_orders o ON o.order_id = r.order_id
        WHERE r.campaign_id = ? AND r.model = ?
        GROUP BY 1 ORDER BY 1
        """,
        [campaign_id, model],
    )
    if not selected:
        return None
    return {
        "campaign": {
            "campaign_id": campaign["campaign_id"],
            "campaign_name": campaign["campaign_name"],
            "campaign_type": campaign["campaign_type"],
            "objective": campaign["objective"],
            "primary_channel_id": campaign["primary_channel_id"],
            "target_audience_id": campaign["target_audience_id"],
            "start_at": campaign["start_at"],
            "end_at": campaign["end_at"],
            "status": campaign["status"],
            "budget_amount": money(campaign["budget_amount"]),
            "budget_currency": campaign["budget_currency"],
        },
        "performance": {
            "model": selected["model"],
            "spend": money(selected["spend"]),
            "cost_coverage": selected["cost_coverage"],
            "attributed_revenue": money(selected["attributed_revenue"]),
            "conversions": integer(selected["conversions"]),
            "unique_converting_contacts": integer(selected["unique_converting_contacts"]),
            "touchpoints_credited": integer(selected["touchpoints_credited"]),
            "roi_pct": number(selected["roi_pct"]),
            "roas": number(selected["roas"]),
            "roi_available": boolean(selected["roi_available"]),
            "roi_status": selected["roi_status"],
            "budget_utilization": number(selected["budget_utilization"]),
            "cost_per_conversion": number(selected["cost_per_conversion"]),
            "average_order_value": number(selected["average_order_value"]),
            "issue_count": integer(selected["issue_count"]),
        },
        "model_comparison": [
            {
                "model": row["model"],
                "attributed_revenue": money(row["attributed_revenue"]),
                "conversions": integer(row["conversions"]),
                "unique_converting_contacts": integer(row["unique_converting_contacts"]),
                "touchpoints_credited": integer(row["touchpoints_credited"]),
                "roi_pct": number(row["roi_pct"]),
                "roi_available": boolean(row["roi_available"]),
            }
            for row in model_rows
        ],
        "cost_records": [
            {
                "cost_id": cost["cost_id"],
                "cost_date": str(cost["cost_date"]),
                "amount": money(cost["amount_value"]),
                "currency": cost["currency"],
                "cost_category": cost["cost_category"],
                "source_ref": cost["source_ref"],
                "period": cost["period"],
            }
            for cost in costs
        ],
        "channel_mix": [
            {
                "channel_id": row["channel_id"],
                "channel_name": row["channel_name"],
                "category": row["category"],
                "attributed_revenue": money(row["attributed_revenue"]),
                "conversions": integer(row["conversions"]),
                "touchpoints": integer(row["touchpoints"]),
            }
            for row in channels
        ],
        "creatives": [
            {
                "creative_id": creative["creative_id"],
                "name": creative["name"],
                "creative_type": creative["creative_type"],
                "status": creative["status"],
            }
            for creative in creatives
        ],
        "monthly": [
            {
                "month": row["month"],
                "attributed_revenue": money(row["attributed_revenue"]),
                "conversions": integer(row["conversions"]),
            }
            for row in monthly
        ],
        "issues": [
            {
                "issue_id": issue["issue_id"],
                "issue_type": issue["issue_type"],
                "severity": issue["severity"],
                "primary_entity_id": issue["primary_entity_id"],
                "affected_record_ids": issue["affected_record_ids"],
                "explanation": issue["explanation"],
                "suggested_disposition": issue["suggested_disposition"],
                "status": issue["status"],
                "split": issue["split"],
            }
            for issue in issues
        ],
    }


def compare_models(
    conn: duckdb.DuckDBPyConnection, model_a: str, model_b: str, limit: int = 15
) -> dict[str, Any]:
    if model_a not in MODELS or model_b not in MODELS:
        raise ValueError("Unsupported attribution model.")
    if model_a == model_b:
        raise ValueError("Choose two different models to compare.")
    campaign_rows = rows(
        conn,
        """
        SELECT campaign_id, campaign_name, primary_channel_name, model,
               CAST(attributed_revenue AS DECIMAL(18,2)) AS attributed_revenue,
               CAST(conversions AS INTEGER) AS conversions
        FROM v_campaign_performance WHERE model IN (?, ?)
        """,
        [model_a, model_b],
    )
    channel_rows = rows(
        conn,
        """
        SELECT channel_id, channel_name, model,
               CAST(attributed_revenue AS DECIMAL(18,2)) AS attributed_revenue,
               CAST(conversions AS INTEGER) AS conversions,
               CAST(spend AS DECIMAL(18,2)) AS spend
        FROM v_channel_performance WHERE model IN (?, ?)
        """,
        [model_a, model_b],
    )

    def pivot(source: list[dict[str, Any]], key: str, label: str | None = None) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for record in source:
            item = grouped.setdefault(
                record[key],
                {
                    key: record[key],
                    "label": record.get(label) if label else record[key],
                    "channel_name": record.get("primary_channel_name")
                    or record.get("channel_name"),
                    model_a: 0.0,
                    model_b: 0.0,
                },
            )
            item[record["model"]] = money(record["attributed_revenue"]) or 0.0
        combined = list(grouped.values())
        total_a = sum(item[model_a] for item in combined)
        total_b = sum(item[model_b] for item in combined)
        denominator_a = total_a or 1.0
        denominator_b = total_b or 1.0
        for item in combined:
            share_a = item[model_a] * 100 / denominator_a
            share_b = item[model_b] * 100 / denominator_b
            item["delta"] = round(item[model_b] - item[model_a], 2)
            item["share_a_pct"] = _round_pct(share_a)
            item["share_b_pct"] = _round_pct(share_b)
            item["share_delta_pct"] = _round_pct(share_b - share_a)
            item["revenue_a"] = item[model_a]
            item["revenue_b"] = item[model_b]
        combined.sort(key=lambda item: abs(item["share_delta_pct"]), reverse=True)
        return combined

    campaigns = pivot(campaign_rows, "campaign_id", "campaign_name")
    channels = pivot(channel_rows, "channel_id", "channel_name")
    channel_total_a = sum(item[model_a] for item in channels)
    channel_total_b = sum(item[model_b] for item in channels)
    summary_a = one(
        conn,
        "SELECT COUNT(DISTINCT order_id) AS conversions, "
        "SUM(CAST(attributed_revenue_dec AS DECIMAL(18,2))) AS revenue "
        "FROM v_attribution_results WHERE model = ?",
        [model_a],
    ) or {}
    summary_b = one(
        conn,
        "SELECT COUNT(DISTINCT order_id) AS conversions, "
        "SUM(CAST(attributed_revenue_dec AS DECIMAL(18,2))) AS revenue "
        "FROM v_attribution_results WHERE model = ?",
        [model_b],
    ) or {}
    return {
        "model_a": model_a,
        "model_b": model_b,
        "totals": {
            "model_a": {
                "attributed_revenue": money(summary_a.get("revenue")),
                "conversions": integer(summary_a.get("conversions")),
            },
            "model_b": {
                "attributed_revenue": money(summary_b.get("revenue")),
                "conversions": integer(summary_b.get("conversions")),
            },
        },
        "share_basis": {
            "definition": (
                "Channel share = channel attributed revenue / total attributed revenue "
                "for the same model across all channels."
            ),
            "delta_definition": "Linear share percentage - First-touch share percentage",
            "unit": "percentage_points",
            "model_a_total": money(channel_total_a),
            "model_b_total": money(channel_total_b),
            "reconciles_to_model_totals": (
                abs((channel_total_a or 0) - float(summary_a.get("revenue") or 0)) < 0.01
                and abs((channel_total_b or 0) - float(summary_b.get("revenue") or 0)) < 0.01
            ),
        },
        "campaign_changes": campaigns[:limit],
        "campaign_count": len(campaigns),
        "channel_changes": channels,
        "channel_count": len(channels),
        "channel_sort": "absolute_share_delta_desc",
    }


def _identity_links(conn: duckdb.DuckDBPyConnection) -> dict[str, list[IdentityLink]]:
    records = rows(conn, "SELECT * FROM v_identity_links ORDER BY link_id")
    grouped: dict[str, list[IdentityLink]] = {}
    for record in records:
        link = IdentityLink(
            link_id=record["link_id"],
            session_id=record["session_id"],
            contact_id=record["contact_id"],
            evidence_type=record["evidence_type"] or "",
            evidence_ref=record["evidence_ref"] or "",
            status=record["status"] or "",
            rule_id=record["rule_id"] or "",
        )
        grouped.setdefault(link.session_id, []).append(link)
    return grouped


def _resolve_reference(
    conn: duckdb.DuckDBPyConnection, reference: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    opportunity = None
    order = None
    if reference.startswith("ORD-"):
        order = one(conn, "SELECT * FROM v_orders WHERE order_id = ?", [reference])
        if order:
            opportunity = one(
                conn,
                "SELECT * FROM v_opportunities WHERE opportunity_id = ?",
                [order["opportunity_id"]],
            )
    elif reference.startswith("OPP-"):
        opportunity = one(
            conn, "SELECT * FROM v_opportunities WHERE opportunity_id = ?", [reference]
        )
        if opportunity:
            order = one(
                conn,
                """
                SELECT * FROM v_orders
                WHERE opportunity_id = ? AND status IN ('PAID', 'PARTIALLY_REFUNDED')
                ORDER BY CASE status WHEN 'PAID' THEN 0 ELSE 1 END, ingested_ts, order_id
                LIMIT 1
                """,
                [reference],
            )
    elif reference.startswith("CON-"):
        order = one(
            conn,
            """
            SELECT * FROM v_orders
            WHERE contact_id = ? AND status IN ('PAID', 'PARTIALLY_REFUNDED')
            ORDER BY ordered_ts DESC, order_id DESC LIMIT 1
            """,
            [reference],
        )
        if order:
            opportunity = one(
                conn,
                "SELECT * FROM v_opportunities WHERE opportunity_id = ?",
                [order["opportunity_id"]],
            )
    else:
        return None, None, None
    contact = None
    contact_id = (order or {}).get("contact_id") or (opportunity or {}).get("contact_id")
    if contact_id:
        contact = one(conn, "SELECT * FROM v_contacts WHERE contact_id = ?", [contact_id])
    return opportunity, order, contact


def sample_journey(conn: duckdb.DuckDBPyConnection, lookback_days: int = 90) -> dict[str, Any] | None:
    record = one(
        conn,
        """
        SELECT o.order_id
        FROM v_orders o
        JOIN v_attribution_results r ON r.order_id = o.order_id
        LEFT JOIN v_touchpoints t
          ON t.contact_id = o.contact_id
         AND t.occurred_ts > o.ordered_ts
         AND t.occurred_ts <= o.ordered_ts + INTERVAL 30 DAY
        WHERE o.status = 'PAID'
        GROUP BY o.order_id
        ORDER BY COUNT(DISTINCT t.touchpoint_id) DESC,
                 COUNT(DISTINCT r.touchpoint_id) DESC,
                 o.order_id
        LIMIT 1
        """,
    )
    if not record:
        return None
    return journey(conn, record["order_id"], lookback_days)


def journey(conn: duckdb.DuckDBPyConnection, reference: str, lookback_days: int = 90) -> dict[str, Any] | None:
    opportunity, order, contact = _resolve_reference(conn, reference)
    if not opportunity and not order:
        return None
    if not order or order["status"] not in ("PAID", "PARTIALLY_REFUNDED"):
        return {
            "reference": reference,
            "status": "NO_RECOGNIZED_CONVERSION",
            "opportunity": _opportunity_payload(opportunity),
            "contact": _contact_payload(contact),
            "conversion": None,
            "touchpoints": [],
            "models": [],
            "message": "This opportunity has no recognized order revenue, so attribution does not apply.",
        }
    if not contact:
        return None
    conversion = Conversion(
        order_id=order["order_id"],
        opportunity_id=order["opportunity_id"],
        contact_id=order["contact_id"],
        ordered_at=order["ordered_ts"],
        revenue=Decimal(order["recognized_revenue_dec"]),
        currency=order["currency"],
    )
    all_links = _identity_links(conn)
    resolutions = build_session_resolution(
        [link for links in all_links.values() for link in links]
    )
    candidate_rows = rows(
        conn,
        """
        WITH any_link AS (
            SELECT session_id, MIN(contact_id) AS contact_id
            FROM identity_links
            WHERE contact_id IS NOT NULL AND trim(contact_id) <> ''
            GROUP BY session_id
        )
        SELECT DISTINCT t.touchpoint_id, t.contact_id, t.session_id, t.campaign_id, t.channel_id,
               t.creative_id, t.occurred_ts, t.touch_type, t.source_system, t.identity_status,
               t.consent_status, t.is_offline_bool, c.name AS campaign_name,
               ch.name AS channel_name, cr.name AS creative_name
        FROM v_touchpoints t
        LEFT JOIN any_link l ON l.session_id = t.session_id
        LEFT JOIN v_campaigns c ON c.campaign_id = t.campaign_id
        LEFT JOIN v_channels ch ON ch.channel_id = t.channel_id
        LEFT JOIN creatives cr ON cr.creative_id = t.creative_id
        WHERE COALESCE(t.contact_id, l.contact_id) = ?
          AND t.occurred_ts >= ? - INTERVAL 365 DAY
          AND t.occurred_ts <= ? + INTERVAL 30 DAY
        ORDER BY t.occurred_ts, t.touchpoint_id
        """,
        [conversion.contact_id, conversion.ordered_at, conversion.ordered_at],
    )
    classifications = []
    for record in candidate_rows:
        resolved_contact = record["contact_id"]
        resolution_status = "DIRECT" if resolved_contact else "UNRESOLVED"
        resolution_rule = "IDR-DIRECT-CONTACT" if resolved_contact else "IDR-NO-SESSION"
        if not resolved_contact and record["session_id"]:
            resolved = resolutions.get(
                record["session_id"],
                None,
            )
            if resolved:
                resolved_contact = resolved.contact_id
                resolution_status = resolved.status
                resolution_rule = resolved.rule_id
        touch = TouchCandidate(
            touchpoint_id=record["touchpoint_id"],
            campaign_id=record["campaign_id"] or "",
            channel_id=record["channel_id"] or "",
            occurred_at=record["occurred_ts"],
            consent_status=record["consent_status"] or "UNKNOWN",
            resolved_contact_id=resolved_contact,
            resolution_status=resolution_status,
            resolution_rule_id=resolution_rule,
            identity_status=record["identity_status"] or "",
        )
        classification = classify_touch(
            touch, conversion, lookback_days, contact["consent_status"] or "UNKNOWN"
        )
        classifications.append((classification, record, resolved_contact))
    eligible = [
        item[0].touch for item in classifications if item[0].outcome == "ELIGIBLE"
    ]
    counts = exclusion_counts([item[0] for item in classifications])

    credit_lookup: dict[str, dict[str, dict[str, Any]]] = {}
    model_summaries = []
    computed_by_model: dict[str, Decimal] = {}
    computed_status: dict[str, str] = {}
    for model in MODELS:
        allocations = allocate_credit(conversion, eligible, model)
        allocated = sum((row.attributed_revenue for row in allocations), Decimal("0.00"))
        computed_by_model[model] = allocated
        computed_status[model] = "ATTRIBUTED" if allocations else "UNATTRIBUTED"
        model_summaries.append(
            {
                "model": model,
                "status": computed_status[model],
                "attributed_revenue": float(allocated),
                "credited_touchpoints": len(allocations),
                "eligible_touchpoints": len(eligible),
                "reconciliation_difference": float(
                    reconciliation_difference(conversion.revenue, allocations)
                ),
            }
        )
        for allocation in allocations:
            credit_lookup.setdefault(allocation.touchpoint_id, {})[model] = {
                "credit_fraction": float(allocation.credit_fraction),
                "attributed_revenue": float(allocation.attributed_revenue),
            }

    persisted = {
        row["model"]: row
        for row in rows(
            conn,
            "SELECT * FROM v_attribution_conversions WHERE order_id = ?",
            [conversion.order_id],
        )
    }
    persisted_checks = []
    allocation_checks = []
    for model_summary in model_summaries:
        model = model_summary["model"]
        record = persisted.get(model)
        persisted_status = record["status"] if record else None
        persisted_raw = (
            Decimal(str(record["attributed_revenue_dec"])) if record else None
        )
        computed_raw = computed_by_model[model]
        status_match = persisted_status == model_summary["status"]
        revenue_match = (
            persisted_raw is not None
            and abs(persisted_raw - computed_raw) <= RECONCILIATION_TOLERANCE
        )
        difference = (
            computed_raw - persisted_raw if persisted_raw is not None else None
        )
        persisted_checks.append(
            {
                "model": model,
                "computed_status": model_summary["status"],
                "persisted_status": persisted_status,
                "computed_revenue": float(computed_raw),
                "persisted_revenue": float(persisted_raw) if persisted_raw is not None else None,
                "status_match": status_match,
                "revenue_match": revenue_match,
                "difference": float(difference) if difference is not None else None,
                "absolute_difference": (
                    float(abs(difference)) if difference is not None else None
                ),
                "tolerance": float(RECONCILIATION_TOLERANCE),
                "comparison": "full_precision_absolute_difference",
                "matched": bool(record) and status_match and revenue_match,
            }
        )
        allocation_checks.append(
            _allocation_check(conn, conversion, model, eligible)
        )
    persisted_consistent = all(check["matched"] for check in persisted_checks)
    allocations_consistent = all(check["matched"] for check in allocation_checks)

    touchpoints = []
    for classification, record, resolved_contact in classifications:
        seconds = (record["occurred_ts"] - conversion.ordered_at).total_seconds()
        touchpoints.append(
            {
                "touchpoint_id": record["touchpoint_id"],
                "occurred_at": record["occurred_ts"].isoformat() + "Z",
                "minutes_from_conversion": round(seconds / 60, 2),
                "campaign_id": record["campaign_id"],
                "campaign_name": record["campaign_name"],
                "channel_id": record["channel_id"],
                "channel_name": record["channel_name"],
                "creative_name": record["creative_name"],
                "touch_type": record["touch_type"],
                "source_system": record["source_system"],
                "identity_status": record["identity_status"],
                "resolution_status": classification.touch.resolution_status,
                "resolution_rule_id": classification.touch.resolution_rule_id,
                "resolved_contact_id": resolved_contact,
                "consent_status": record["consent_status"],
                "outcome": classification.outcome,
                "outcome_reason": classification.reason,
                "eligible": classification.outcome == "ELIGIBLE",
                "credits": credit_lookup.get(record["touchpoint_id"], {}),
            }
        )
    source_ref = order["source_system_ref"]
    duplicates = rows(
        conn,
        "SELECT order_id, status, amount_dec, ingested_ts FROM v_orders "
        "WHERE source_system_ref = ? ORDER BY ingested_ts, order_id",
        [source_ref],
    )
    return {
        "reference": reference,
        "status": "CONVERTED",
        "opportunity": _opportunity_payload(opportunity),
        "contact": _contact_payload(contact),
        "conversion": {
            "order_id": conversion.order_id,
            "opportunity_id": conversion.opportunity_id,
            "contact_id": conversion.contact_id,
            "ordered_at": conversion.ordered_at.isoformat() + "Z",
            "revenue": float(conversion.revenue),
            "currency": conversion.currency,
            "split": split_for_timestamp(conversion.ordered_at),
            "lookback_days": lookback_days,
            "consent_status": contact["consent_status"],
            "source_system_ref": source_ref,
            "duplicate_orders": [
                {
                    "order_id": duplicate["order_id"],
                    "status": duplicate["status"],
                    "amount": money(duplicate["amount_dec"]),
                    "ingested_at": duplicate["ingested_ts"].isoformat() + "Z",
                    "canonical": duplicate["order_id"] == conversion.order_id,
                }
                for duplicate in duplicates
            ],
        },
        "exclusions": {
            field: counts[field] for field in EXCLUDED_COUNT_FIELDS.values()
        },
        "counts": {
            "total_touches": len(classifications),
            "eligible_touches": len(eligible),
            "excluded_touches": sum(counts[field] for field in EXCLUDED_COUNT_FIELDS.values()),
            "credited_touchpoints": {
                model: next(
                    item["credited_touchpoints"]
                    for item in model_summaries
                    if item["model"] == model
                )
                for model in MODELS
            },
            "exclusion_semantics": (
                "Each candidate touch receives exactly one primary exclusion reason "
                "(checked in order: after conversion, outside lookback, unresolved identity, "
                "consent, no campaign). Total excluded therefore equals unique excluded "
                "touches, not a sum of overlapping categories."
            ),
        },
        "models": model_summaries,
        "persisted_consistent": persisted_consistent,
        "persisted_check": {
            "consistent": persisted_consistent and allocations_consistent,
            "difference_count": sum(1 for check in persisted_checks if not check["matched"]),
            "models": persisted_checks,
            "allocations": allocation_checks,
            "allocations_consistent": allocations_consistent,
            "tolerance": float(RECONCILIATION_TOLERANCE),
            "comparison_basis": (
                "Full-precision absolute difference between recomputed and persisted "
                "attributed revenue, plus a per-touchpoint allocation comparison for "
                "the same order and model."
            ),
            "scope": "This conversion only",
            "population": {
                "order_id": conversion.order_id,
                "conversion_revenue": float(conversion.revenue),
                "eligible_touchpoints": len(eligible),
                "candidate_touchpoints": len(classifications),
            },
        },
        "touchpoints": touchpoints,
    }


def _opportunity_payload(opportunity: dict[str, Any] | None) -> dict[str, Any] | None:
    if not opportunity:
        return None
    return {
        "opportunity_id": opportunity["opportunity_id"],
        "lead_id": opportunity["lead_id"],
        "contact_id": opportunity["contact_id"],
        "created_at": opportunity["created_ts"].isoformat() + "Z",
        "stage": opportunity["stage"],
        "outcome": opportunity["outcome"],
        "expected_value": money(opportunity["expected_value_dec"]),
        "currency": opportunity["currency"],
        "closed_at": (
            opportunity["closed_ts"].isoformat() + "Z" if opportunity["closed_ts"] else None
        ),
        "owner_team": opportunity["owner_team"],
    }


def _contact_payload(contact: dict[str, Any] | None) -> dict[str, Any] | None:
    if not contact:
        return None
    return {
        "contact_id": contact["contact_id"],
        "created_at": contact["created_ts"].isoformat() + "Z",
        "region": contact["region"],
        "country": contact["country"],
        "segment": contact["segment"],
        "consent_status": contact["consent_status"],
        "lifecycle_status": contact["lifecycle_status"],
        "acquisition_channel_id": contact["acquisition_channel_id"],
    }


def list_exceptions(
    conn: duckdb.DuckDBPyConnection,
    severity: str | None = None,
    issue_type: str | None = None,
    split: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if issue_type:
        clauses.append("issue_type = ?")
        params.append(issue_type)
    if split:
        clauses.append("split = ?")
        params.append(split)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if search:
        clauses.append(
            "(lower(issue_id) LIKE ? OR lower(primary_entity_id) LIKE ? OR lower(explanation) LIKE ?)"
        )
        needle = f"%{search.lower()}%"
        params.extend([needle, needle, needle])
    where = " AND ".join(clauses)
    total = conn.execute(f"SELECT COUNT(*) FROM v_exceptions WHERE {where}", params).fetchone()[0]
    records = rows(
        conn,
        f"""
        SELECT * FROM v_exceptions WHERE {where}
        ORDER BY CASE severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,
                 issue_type, issue_id
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    )
    facets = {
        "issue_type": rows(
            conn,
            "SELECT issue_type AS value, COUNT(*) AS count FROM v_exceptions GROUP BY 1 ORDER BY 2 DESC",
        ),
        "severity": rows(
            conn,
            "SELECT severity AS value, COUNT(*) AS count FROM v_exceptions GROUP BY 1 "
            "ORDER BY CASE severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END",
        ),
        "split": rows(
            conn,
            "SELECT split AS value, COUNT(*) AS count FROM v_exceptions GROUP BY 1 ORDER BY 1",
        ),
        "status": rows(
            conn,
            "SELECT status AS value, COUNT(*) AS count FROM v_exceptions GROUP BY 1 ORDER BY 1",
        ),
    }
    return {
        "items": [
            {
                "issue_id": record["issue_id"],
                "issue_type": record["issue_type"],
                "severity": record["severity"],
                "entity_type": record["entity_type"],
                "affected_record_ids": record["affected_record_ids"],
                "primary_entity_id": record["primary_entity_id"],
                "detection_rule_id": record["detection_rule_id"],
                "detected_at": record["detected_ts"].isoformat() + "Z",
                "explanation": record["explanation"],
                "suggested_disposition": record["suggested_disposition"],
                "status": record["status"],
                "split": record["split"],
            }
            for record in records
        ],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "facets": {
            key: [
                {"value": item["value"], "count": int(item["count"])}
                for item in values
            ]
            for key, values in facets.items()
        },
    }


def exception_detail(conn: duckdb.DuckDBPyConnection, issue_id: str) -> dict[str, Any] | None:
    record = one(conn, "SELECT * FROM v_exceptions WHERE issue_id = ?", [issue_id])
    if not record:
        return None
    related: dict[str, Any] = {}
    if record["entity_type"] == "campaign":
        campaign = one(
            conn,
            "SELECT * FROM v_campaigns WHERE campaign_id = ?",
            [record["primary_entity_id"]],
        )
        if campaign:
            related["campaign"] = {
                "campaign_id": campaign["campaign_id"],
                "campaign_name": campaign["name"],
                "status": campaign["status"],
                "budget_amount": money(campaign["budget_dec"]),
                "budget_currency": campaign["budget_currency"],
            }
        else:
            related["missing_references"] = [
                {
                    "type": "CAMPAIGN",
                    "record_id": record["primary_entity_id"],
                    "reason": "Campaign referenced by this exception no longer exists.",
                }
            ]
    if record["entity_type"] in ("order", "touchpoint", "identity_link", "campaign"):
        related.setdefault("records", [])
        for record_id in [item for item in record["affected_record_ids"].split("|") if item][:10]:
            related["records"].append(_related_record(conn, record_id))
    if record["entity_type"] == "order":
        related["canonicalization"] = _duplicate_canonicalization(conn, record)
    related["disposition_state"] = {
        "status": record["status"],
        "applied": False,
        "label": "Advisory only - not applied",
        "detail": (
            "The suggested disposition has not been applied to source records or "
            "financial totals by this read model."
        ),
    }
    return {
        "issue_id": record["issue_id"],
        "issue_type": record["issue_type"],
        "severity": record["severity"],
        "entity_type": record["entity_type"],
        "affected_record_ids": record["affected_record_ids"],
        "primary_entity_id": record["primary_entity_id"],
        "detection_rule_id": record["detection_rule_id"],
        "detected_at": record["detected_ts"].isoformat() + "Z",
        "explanation": record["explanation"],
        "evidence": split_evidence(record["evidence"]),
        "suggested_disposition": record["suggested_disposition"],
        "status": record["status"],
        "split": record["split"],
        "related": related,
    }


def _duplicate_canonicalization(
    conn: duckdb.DuckDBPyConnection, record: dict[str, Any]
) -> dict[str, Any]:
    """Explain the duplicate-revenue business key and its effect on revenue."""

    evidence = split_evidence(record["evidence"])
    if not isinstance(evidence, dict):
        evidence = {}
    source_ref = evidence.get("source_system_ref")
    orders = rows(
        conn,
        "SELECT * FROM v_orders WHERE source_system_ref = ? ORDER BY ingested_ts, order_id",
        [source_ref],
    ) if source_ref else []
    canonical = orders[0] if orders else None
    excluded = orders[1:]
    excluded_revenue = sum(
        (Decimal(str(order["recognized_revenue_dec"] or 0)) for order in excluded),
        Decimal("0.00"),
    )
    return {
        "business_key": "source_system_ref",
        "business_key_value": source_ref,
        "rule": (
            "Copies are matched on the source transaction reference, not on amount. "
            "The earliest ingested copy is canonical; later copies are excluded from "
            "attribution so revenue is never counted twice."
        ),
        "amount_match_is_not_evidence": True,
        "canonical_order_id": canonical["order_id"] if canonical else None,
        "canonical_ingested_at": (
            canonical["ingested_ts"].isoformat() + "Z" if canonical else None
        ),
        "copy_count": len(orders),
        "excluded_order_ids": [order["order_id"] for order in excluded],
        "excluded_recognized_revenue": money(excluded_revenue),
        "revenue_effect": (
            "Excluded copies contribute EUR 0.00 to eligible and attributed revenue."
        ),
        "source_records_preserved": True,
    }


def _related_record(conn: duckdb.DuckDBPyConnection, record_id: str) -> dict[str, Any]:
    if record_id.startswith("CMP-"):
        campaign = one(
            conn,
            "SELECT * FROM v_campaigns WHERE campaign_id = ?",
            [record_id],
        )
        if campaign:
            return {
                "type": "CAMPAIGN",
                "campaign_id": campaign["campaign_id"],
                "campaign_name": campaign["name"],
                "status": campaign["status"],
                "budget_amount": money(campaign["budget_dec"]),
                "budget_currency": campaign["budget_currency"],
                "start_at": campaign["start_ts"].isoformat() + "Z",
                "end_at": campaign["end_ts"].isoformat() + "Z",
            }
        return {
            "type": "REFERENCE",
            "record_id": record_id,
            "reason": "Referenced campaign no longer exists.",
        }
    if record_id.startswith("ORD-"):
        order = one(conn, "SELECT * FROM v_orders WHERE order_id = ?", [record_id])
        if order:
            return {
                "type": "ORDER",
                "order_id": order["order_id"],
                "status": order["status"],
                "amount": money(order["amount_dec"]),
                "recognized_revenue": money(order["recognized_revenue_dec"]),
                "currency": order["currency"],
                "ordered_at": order["ordered_ts"].isoformat() + "Z",
                "source_system_ref": order["source_system_ref"],
                "opportunity_id": order["opportunity_id"],
            }
    if record_id.startswith("TOUCH-"):
        touch = one(conn, "SELECT * FROM v_touchpoints WHERE touchpoint_id = ?", [record_id])
        if touch:
            campaign = one(conn, "SELECT name FROM v_campaigns WHERE campaign_id = ?", [touch["campaign_id"]])
            return {
                "type": "TOUCHPOINT",
                "touchpoint_id": touch["touchpoint_id"],
                "campaign_id": touch["campaign_id"],
                "campaign_name": campaign["name"] if campaign else None,
                "occurred_at": touch["occurred_ts"].isoformat() + "Z",
                "touch_type": touch["touch_type"],
                "consent_status": touch["consent_status"],
            }
    if record_id.startswith("LNK-"):
        link = one(conn, "SELECT * FROM v_identity_links WHERE link_id = ?", [record_id])
        if link:
            return {
                "type": "IDENTITY_LINK",
                "link_id": link["link_id"],
                "session_id": link["session_id"],
                "contact_id": link["contact_id"],
                "evidence_type": link["evidence_type"],
                "evidence_ref": link["evidence_ref"],
                "status": link["status"],
            }
    if record_id.startswith("SES-"):
        session = one(conn, "SELECT * FROM v_sessions WHERE session_id = ?", [record_id])
        if session:
            return {
                "type": "SESSION",
                "session_id": session["session_id"],
                "anonymous_id": session["anonymous_id"],
                "started_at": session["started_ts"].isoformat() + "Z",
                "source": session["source"],
                "medium": session["medium"],
            }
    return {"type": "REFERENCE", "record_id": record_id}

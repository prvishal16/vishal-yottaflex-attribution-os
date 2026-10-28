"""Pipeline stage that computes first-touch, last-touch and linear attribution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from yottaflex.config import (
    ATTRIBUTION_RULE_VERSION,
    MODELS,
    RECOGNIZED_ORDER_STATUSES,
    RunConfig,
)
from yottaflex.domain.attribution import (
    CONVERSION_REASON_NO_TOUCHES,
    Conversion,
    TouchCandidate,
    allocate_credit,
    classify_touch,
    exclusion_counts,
    sort_eligible_touches,
)
from yottaflex.domain.identity import (
    IdentityLink,
    build_session_resolution,
)
from yottaflex.storage import create_typed_views, refresh_table
from yottaflex.tables import DERIVED_TABLES
from yottaflex.util import IdSequence, iso, write_csv


def _fetch_dicts(conn: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cursor = conn.execute(sql)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _canonical_conversions(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    statuses = ", ".join(f"'{value}'" for value in RECOGNIZED_ORDER_STATUSES)
    sql = f"""
        WITH ranked AS (
            SELECT order_id, opportunity_id, contact_id, ordered_ts, currency,
                   recognized_revenue_dec, status,
                   ROW_NUMBER() OVER (
                       PARTITION BY source_system_ref ORDER BY ingested_ts, order_id
                   ) AS rn
            FROM v_orders
            WHERE status IN ({statuses})
        )
        SELECT order_id, opportunity_id, contact_id, ordered_ts, currency,
               recognized_revenue_dec
        FROM ranked
        WHERE rn = 1 AND recognized_revenue_dec > 0
        ORDER BY order_id
    """
    return _fetch_dicts(conn, sql)


def _journey_candidates(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Touches related to a converting contact through direct IDs or any link.

    Unsupported links are included here only so that exclusion counts can show an
    unresolved identity. They are never treated as resolved contact IDs.
    """

    conn.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE tmp_conversions AS
        WITH ranked AS (
            SELECT order_id, opportunity_id, contact_id, ordered_ts, currency,
                   recognized_revenue_dec, status,
                   ROW_NUMBER() OVER (
                       PARTITION BY source_system_ref ORDER BY ingested_ts, order_id
                   ) AS rn
            FROM v_orders
            WHERE status IN ({", ".join(f"'{value}'" for value in RECOGNIZED_ORDER_STATUSES)})
        )
        SELECT order_id, opportunity_id, contact_id, ordered_ts, currency,
               recognized_revenue_dec
        FROM ranked WHERE rn = 1 AND recognized_revenue_dec > 0
        """
    )
    sql = """
        WITH any_link AS (
            SELECT session_id, MIN(contact_id) AS contact_id
            FROM identity_links
            WHERE contact_id IS NOT NULL AND trim(contact_id) <> ''
            GROUP BY session_id
        ),
        resolved AS (
            SELECT t.touchpoint_id, t.contact_id, t.session_id, t.campaign_id, t.channel_id,
                   t.occurred_ts, t.consent_status,
                   COALESCE(t.contact_id, l.contact_id) AS any_contact
            FROM v_touchpoints t
            LEFT JOIN any_link l ON l.session_id = t.session_id
        )
        SELECT DISTINCT c.order_id, c.contact_id AS conversion_contact,
               c.recognized_revenue_dec, c.ordered_ts,
               r.touchpoint_id, r.contact_id, r.session_id, r.campaign_id, r.channel_id,
               r.occurred_ts, r.consent_status
        FROM tmp_conversions c
        JOIN resolved r ON r.any_contact = c.contact_id
        WHERE r.occurred_ts >= c.ordered_ts - INTERVAL 365 DAY
          AND r.occurred_ts <= c.ordered_ts + INTERVAL 30 DAY
        ORDER BY c.order_id, r.occurred_ts, r.touchpoint_id
    """
    return _fetch_dicts(conn, sql)


def _identity_links(conn: duckdb.DuckDBPyConnection) -> list[IdentityLink]:
    rows = _fetch_dicts(
        conn,
        "SELECT link_id, session_id, contact_id, evidence_type, evidence_ref, status, rule_id "
        "FROM identity_links ORDER BY link_id",
    )
    return [
        IdentityLink(
            link_id=row["link_id"],
            session_id=row["session_id"],
            contact_id=row["contact_id"],
            evidence_type=row["evidence_type"] or "",
            evidence_ref=row["evidence_ref"] or "",
            status=row["status"] or "",
            rule_id=row["rule_id"] or "",
        )
        for row in rows
    ]


def compute_attribution(
    conn: duckdb.DuckDBPyConnection, config: RunConfig, run_dir: Path
) -> dict[str, Any]:
    computed_at = iso(datetime.now(UTC))
    conversions_raw = _canonical_conversions(conn)
    candidates_raw = _journey_candidates(conn)
    links = _identity_links(conn)
    session_resolution = build_session_resolution(links)

    contact_consent = dict(
        conn.execute("SELECT contact_id, consent_status FROM contacts").fetchall()
    )

    candidates_by_order: dict[str, list[dict[str, Any]]] = {}
    for row in candidates_raw:
        candidates_by_order.setdefault(row["order_id"], []).append(row)

    result_rows: list[dict[str, Any]] = []
    outcome_rows: list[dict[str, Any]] = []
    result_sequence = IdSequence("ATTR", year=2026)
    outcome_sequence = IdSequence("CONV", year=2026)
    attributed_by_model: dict[str, Decimal] = {model: Decimal("0.00") for model in MODELS}
    unattributed_by_model: dict[str, int] = {model: 0 for model in MODELS}
    post_conversion_exclusions = 0
    reconciliation_violations = 0

    for raw in conversions_raw:
        conversion = Conversion(
            order_id=raw["order_id"],
            opportunity_id=raw["opportunity_id"],
            contact_id=raw["contact_id"],
            ordered_at=raw["ordered_ts"],
            revenue=Decimal(str(raw["recognized_revenue_dec"])),
            currency=raw["currency"],
        )
        rows = candidates_by_order.get(conversion.order_id, [])
        classified = []
        for row in rows:
            direct_contact = row["contact_id"] or None
            session_id = row["session_id"] or None
            if direct_contact:
                resolved_contact = direct_contact
                resolution_status = "DIRECT"
                resolution_rule = "IDR-DIRECT-CONTACT"
            elif session_id and session_id in session_resolution:
                resolution = session_resolution[session_id]
                resolved_contact = resolution.contact_id
                resolution_status = resolution.status
                resolution_rule = resolution.rule_id
            else:
                resolved_contact = None
                resolution_status = "UNRESOLVED"
                resolution_rule = "IDR-NO-SESSION"
            touch = TouchCandidate(
                touchpoint_id=row["touchpoint_id"],
                campaign_id=row["campaign_id"] or "",
                channel_id=row["channel_id"] or "",
                occurred_at=row["occurred_ts"],
                consent_status=row["consent_status"] or "UNKNOWN",
                resolved_contact_id=resolved_contact,
                resolution_status=resolution_status,
                resolution_rule_id=resolution_rule,
                identity_status="DIRECT" if direct_contact else "ANONYMOUS",
            )
            classified.append(
                classify_touch(
                    touch,
                    conversion,
                    config.lookback_days,
                    contact_consent_status=contact_consent.get(conversion.contact_id, "UNKNOWN"),
                )
            )

        eligible = sort_eligible_touches(
            [row.touch for row in classified if row.outcome == "ELIGIBLE"]
        )
        counts = exclusion_counts(classified)
        post_conversion_exclusions += counts["excluded_post_conversion"]

        if not rows:
            exclusion_reason = CONVERSION_REASON_NO_TOUCHES
        elif not eligible:
            reasons = [
                f"{name}={counts[field]}"
                for name, field in (
                    ("POST_CONVERSION", "excluded_post_conversion"),
                    ("OUTSIDE_WINDOW", "excluded_outside_window"),
                    ("IDENTITY_UNRESOLVED", "excluded_identity_unresolved"),
                    ("CONSENT_DENIED", "excluded_consent"),
                    ("NO_CAMPAIGN", "excluded_no_campaign"),
                )
                if counts[field] > 0
            ]
            exclusion_reason = "NO_ELIGIBLE_TOUCHPOINTS:" + "|".join(reasons or ["UNKNOWN"])
        else:
            exclusion_reason = ""

        for model in MODELS:
            allocations = allocate_credit(conversion, eligible, model)
            attributed_revenue = sum(
                (allocation.attributed_revenue for allocation in allocations), Decimal("0.00")
            )
            if allocations:
                status = "ATTRIBUTED"
                attributed_by_model[model] += attributed_revenue
                if attributed_revenue != conversion.revenue:
                    reconciliation_violations += 1
            else:
                status = "UNATTRIBUTED"
                unattributed_by_model[model] += 1
            outcome_rows.append(
                {
                    "conversion_result_id": outcome_sequence.next(),
                    "order_id": conversion.order_id,
                    "opportunity_id": conversion.opportunity_id,
                    "contact_id": conversion.contact_id,
                    "model": model,
                    "status": status,
                    "conversion_revenue": str(conversion.revenue),
                    "eligible_touchpoints": len(eligible),
                    "excluded_post_conversion": counts["excluded_post_conversion"],
                    "excluded_outside_window": counts["excluded_outside_window"],
                    "excluded_identity_unresolved": counts["excluded_identity_unresolved"],
                    "excluded_consent": counts["excluded_consent"],
                    "excluded_no_campaign": counts["excluded_no_campaign"],
                    "attributed_touchpoints": len(allocations),
                    "attributed_revenue": str(attributed_revenue),
                    "exclusion_reason": exclusion_reason,
                    "attribution_run_id": config.run_id,
                    "rule_version": ATTRIBUTION_RULE_VERSION,
                    "computed_at": computed_at,
                }
            )
            for allocation in allocations:
                result_rows.append(
                    {
                        "attribution_result_id": result_sequence.next(),
                        "order_id": conversion.order_id,
                        "opportunity_id": conversion.opportunity_id,
                        "contact_id": conversion.contact_id,
                        "model": model,
                        "touchpoint_id": allocation.touchpoint_id,
                        "campaign_id": allocation.campaign_id,
                        "channel_id": allocation.channel_id,
                        "credit_fraction": str(allocation.credit_fraction),
                        "attributed_revenue": str(allocation.attributed_revenue),
                        "currency": conversion.currency,
                        "attribution_run_id": config.run_id,
                        "rule_version": ATTRIBUTION_RULE_VERSION,
                        "computed_at": computed_at,
                    }
                )

    results_spec = DERIVED_TABLES["attribution_results"]
    outcomes_spec = DERIVED_TABLES["attribution_conversions"]
    write_csv(run_dir / "attribution_results.csv", results_spec.columns, result_rows, results_spec.sort_key)
    write_csv(
        run_dir / "attribution_conversions.csv",
        outcomes_spec.columns,
        outcome_rows,
        outcomes_spec.sort_key,
    )
    refresh_table(conn, run_dir, "attribution_results")
    refresh_table(conn, run_dir, "attribution_conversions")
    create_typed_views(conn)

    eligible_conversions = len(conversions_raw)
    eligible_revenue = sum(
        (Decimal(str(row["recognized_revenue_dec"])) for row in conversions_raw), Decimal("0.00")
    )
    default_model = "linear"
    return {
        "conversions": eligible_conversions,
        "eligible_revenue": str(eligible_revenue),
        "attributed_revenue": str(attributed_by_model[default_model]),
        "attributed_revenue_by_model": {
            model: str(value) for model, value in attributed_by_model.items()
        },
        "unattributed_conversions": unattributed_by_model[default_model],
        "unattributed_conversions_by_model": {
            model: value for model, value in unattributed_by_model.items()
        },
        "unattributed_revenue": str(eligible_revenue - attributed_by_model[default_model]),
        "attribution_results": len(result_rows),
        "attribution_outcomes": len(outcome_rows),
        "post_conversion_exclusions": post_conversion_exclusions,
        "reconciliation_violations": reconciliation_violations,
        "models": list(MODELS),
    }

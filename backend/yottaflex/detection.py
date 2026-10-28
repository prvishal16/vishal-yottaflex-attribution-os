"""Rule-based anomaly detection.

Detection reads only analytical inputs (not ground-truth labels). Every rule is
deterministic and emits evidence that a reviewer can inspect in the UI.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from yottaflex.config import ALLOWED_IDENTITY_EVIDENCE, split_for_date
from yottaflex.storage import create_typed_views, refresh_table
from yottaflex.tables import DERIVED_TABLES, TableSpec
from yottaflex.util import IdSequence, iso, parse_iso, write_csv

DETECTION_RULE_VERSION = "1.0.0"

RULES = {
    "DUPLICATE_REVENUE": {
        "severity": "HIGH",
        "entity_type": "order",
        "rule_id": "DQ-DUP-001",
        "disposition": "VOID_DUPLICATE_REVENUE",
    },
    "POST_CONVERSION_TOUCH": {
        "severity": "MEDIUM",
        "entity_type": "touchpoint",
        "rule_id": "DQ-PCT-001",
        "disposition": "EXCLUDE_FROM_ATTRIBUTION",
    },
    "CURRENCY_MISMATCH": {
        "severity": "MEDIUM",
        "entity_type": "cost_record",
        "rule_id": "FIN-CUR-001",
        "disposition": "QUARANTINE_COST_RECORD",
    },
    "MISSING_CAMPAIGN_COST": {
        "severity": "HIGH",
        "entity_type": "campaign",
        "rule_id": "FIN-COST-001",
        "disposition": "REQUEST_COST_DATA",
    },
    "UNSUPPORTED_IDENTITY_LINK": {
        "severity": "HIGH",
        "entity_type": "identity_link",
        "rule_id": "ID-LNK-001",
        "disposition": "DO_NOT_USE_FOR_RESOLUTION",
    },
}


def _evidence(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _issue(
    issue_type: str,
    primary_entity_id: str,
    affected: list[str],
    timestamp: datetime,
    explanation: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    rule = RULES[issue_type]
    return {
        "issue_type": issue_type,
        "severity": rule["severity"],
        "entity_type": rule["entity_type"],
        "affected_record_ids": "|".join(dict.fromkeys(affected)),
        "primary_entity_id": primary_entity_id,
        "detection_rule_id": rule["rule_id"],
        "detected_at": iso(datetime.now(UTC)),
        "explanation": explanation,
        "evidence": _evidence(evidence),
        "suggested_disposition": rule["disposition"],
        "status": "OPEN",
        "split": split_for_date(timestamp.date()),
    }


def detect_duplicate_revenue(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT source_system_ref,
               COUNT(*) AS copies,
               list(order_id ORDER BY ingested_ts, order_id) AS order_ids,
               list(order_id ORDER BY ingested_ts, order_id)[1] AS canonical_order_id,
               MIN(ordered_ts) AS first_ordered_ts,
               SUM(amount_dec) AS total_amount,
               list(status ORDER BY ingested_ts, order_id) AS statuses
        FROM v_orders
        WHERE status IN ('PAID', 'PARTIALLY_REFUNDED')
        GROUP BY source_system_ref
        HAVING COUNT(*) > 1
        ORDER BY source_system_ref
        """
    ).fetchall()
    issues: list[dict[str, Any]] = []
    for row in rows:
        source_ref, copies, order_ids, canonical, first_ordered, total_amount, statuses = row
        issues.append(
            _issue(
                "DUPLICATE_REVENUE",
                canonical,
                [str(order_id) for order_id in order_ids],
                first_ordered,
                f"Source reference {source_ref} was received {copies} times as recognized revenue; "
                "recognizing every copy would double-count revenue.",
                {
                    "source_system_ref": source_ref,
                    "copies": int(copies),
                    "order_ids": [str(order_id) for order_id in order_ids],
                    "canonical_order_id": canonical,
                    "statuses": list(statuses),
                    "total_amount": str(total_amount),
                },
            )
        )
    return issues


def detect_post_conversion_touches(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT t.touchpoint_id, t.contact_id, t.occurred_ts AS touch_ts, t.campaign_id,
               o.order_id, o.ordered_ts,
               date_diff('minute', o.ordered_ts, t.occurred_ts) AS minutes_after
        FROM v_touchpoints t
        JOIN v_orders o ON o.contact_id = t.contact_id
        WHERE o.status IN ('PAID', 'PARTIALLY_REFUNDED')
          AND t.occurred_ts > o.ordered_ts
          AND t.occurred_ts <= o.ordered_ts + INTERVAL 14 DAY
        ORDER BY t.touchpoint_id
        """
    ).fetchall()
    issues: list[dict[str, Any]] = []
    for touchpoint_id, contact_id, touch_ts, campaign_id, order_id, ordered_ts, minutes_after in rows:
        issues.append(
            _issue(
                "POST_CONVERSION_TOUCH",
                touchpoint_id,
                [touchpoint_id, order_id],
                touch_ts,
                f"Touch occurred {minutes_after} minutes after order {order_id}; it must never receive "
                "credit for that conversion.",
                {
                    "touchpoint_id": touchpoint_id,
                    "order_id": order_id,
                    "contact_id": contact_id,
                    "campaign_id": campaign_id,
                    "ordered_at": iso(ordered_ts),
                    "touched_at": iso(touch_ts),
                    "minutes_after": int(minutes_after),
                },
            )
        )
    return issues


def detect_currency_mismatch(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT co.cost_id, co.campaign_id, co.currency, c.budget_currency,
               co.amount_dec, co.cost_date_d
        FROM v_costs co
        JOIN v_campaigns c ON c.campaign_id = co.campaign_id
        WHERE co.currency <> c.budget_currency
        ORDER BY co.cost_id
        """
    ).fetchall()
    issues: list[dict[str, Any]] = []
    for cost_id, campaign_id, currency, budget_currency, amount, cost_date in rows:
        issues.append(
            _issue(
                "CURRENCY_MISMATCH",
                cost_id,
                [cost_id, campaign_id],
                parse_iso(f"{cost_date}T00:00:00") or datetime.combine(cost_date, datetime.min.time()),
                f"Cost record is in {currency} but campaign budget is in {budget_currency}; "
                "no FX conversion is applied, so the record is quarantined.",
                {
                    "cost_id": cost_id,
                    "campaign_id": campaign_id,
                    "cost_currency": currency,
                    "budget_currency": budget_currency,
                    "amount": str(amount),
                    "cost_date": cost_date.isoformat(),
                },
            )
        )
    return issues


def detect_missing_campaign_cost(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.campaign_id, c.name, c.budget_dec, c.budget_currency, c.end_ts,
               COUNT(co.cost_id) AS cost_rows,
               COUNT(CASE WHEN co.currency = c.budget_currency THEN 1 END) AS compatible_rows
        FROM v_campaigns c
        LEFT JOIN v_costs co ON co.campaign_id = c.campaign_id
        WHERE c.budget_dec > 0
        GROUP BY c.campaign_id, c.name, c.budget_dec, c.budget_currency, c.end_ts
        HAVING COUNT(CASE WHEN co.currency = c.budget_currency THEN 1 END) = 0
        ORDER BY c.campaign_id
        """
    ).fetchall()
    issues: list[dict[str, Any]] = []
    for campaign_id, name, budget, currency, end_ts, cost_rows, compatible_rows in rows:
        issues.append(
            _issue(
                "MISSING_CAMPAIGN_COST",
                campaign_id,
                [campaign_id],
                end_ts,
                f"Campaign {name} has a {currency} budget of {budget} but no compatible cost records; "
                "spend is unknown, not zero.",
                {
                    "campaign_id": campaign_id,
                    "campaign_name": name,
                    "budget": str(budget),
                    "budget_currency": currency,
                    "campaign_end": iso(end_ts),
                    "cost_rows_seen": int(cost_rows),
                    "compatible_cost_rows": int(compatible_rows),
                },
            )
        )
    return issues


def detect_unsupported_identity_links(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT link_id, session_id, evidence_type, evidence_ref, status, linked_ts
        FROM v_identity_links
        WHERE evidence_type NOT IN ({placeholders})
           OR trim(evidence_ref) = ''
           OR status <> 'VERIFIED'
        ORDER BY link_id
        """.format(placeholders=", ".join("?" for _ in ALLOWED_IDENTITY_EVIDENCE)),
        list(ALLOWED_IDENTITY_EVIDENCE),
    ).fetchall()
    issues: list[dict[str, Any]] = []
    for link_id, session_id, evidence_type, evidence_ref, status, created_at in rows:
        issues.append(
            _issue(
                "UNSUPPORTED_IDENTITY_LINK",
                link_id,
                [link_id, session_id],
                created_at,
                f"Identity link uses evidence type {evidence_type or '(missing)'} with status {status}; "
                "it cannot be used to connect anonymous activity to a contact.",
                {
                    "link_id": link_id,
                    "session_id": session_id,
                    "evidence_type": evidence_type,
                    "evidence_ref": evidence_ref,
                    "status": status,
                    "allowed_evidence_types": list(ALLOWED_IDENTITY_EVIDENCE),
                },
            )
        )
    return issues


RULES_BY_TYPE = {
    "DUPLICATE_REVENUE": detect_duplicate_revenue,
    "POST_CONVERSION_TOUCH": detect_post_conversion_touches,
    "CURRENCY_MISMATCH": detect_currency_mismatch,
    "MISSING_CAMPAIGN_COST": detect_missing_campaign_cost,
    "UNSUPPORTED_IDENTITY_LINK": detect_unsupported_identity_links,
}


def run_detection(conn: duckdb.DuckDBPyConnection, run_dir: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for issue_type in sorted(RULES_BY_TYPE):
        issues.extend(RULES_BY_TYPE[issue_type](conn))
    issues.sort(key=lambda item: (item["issue_type"], item["primary_entity_id"], item["affected_record_ids"]))
    sequence = IdSequence("ISS", year=2026)
    for issue in issues:
        issue["issue_id"] = sequence.next()
    spec: TableSpec = DERIVED_TABLES["exceptions"]
    ordered = [{column: issue.get(column, "") for column in spec.columns} for issue in issues]
    write_csv(run_dir / "exceptions.csv", spec.columns, ordered, spec.sort_key)
    refresh_table(conn, run_dir, "exceptions")
    create_typed_views(conn)
    counts: dict[str, int] = {}
    severity: dict[str, int] = {}
    for issue in issues:
        counts[issue["issue_type"]] = counts.get(issue["issue_type"], 0) + 1
        severity[issue["severity"]] = severity.get(issue["severity"], 0) + 1
    return {
        "rule_version": DETECTION_RULE_VERSION,
        "issues": len(issues),
        "by_type": counts,
        "by_severity": severity,
    }

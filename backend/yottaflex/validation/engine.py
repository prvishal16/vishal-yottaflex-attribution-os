"""Reusable validation engine.

Checks are expressed as SQL against the analytical database plus one Python
lifecycle-history walk. Deliberate anomaly fixtures are reported as warnings;
structural corruption is reported as a failure.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import duckdb

from yottaflex.config import (
    ALLOWED_IDENTITY_EVIDENCE,
    VALIDATION_RULE_VERSION,
    RunConfig,
)
from yottaflex.domain.lifecycle import is_valid_transition
from yottaflex.tables import CORE_TABLES
from yottaflex.util import iso, json_dumps

SAMPLE_LIMIT = 25


def _scalar(conn: duckdb.DuckDBPyConnection, sql: str) -> int:
    value = conn.execute(sql).fetchone()[0]
    return int(value or 0)


def _sample_rows(conn: duckdb.DuckDBPyConnection, sql: str) -> str:
    rows = conn.execute(sql).fetchall()
    parts: list[str] = []
    for row in rows[:SAMPLE_LIMIT]:
        values = [str(value) for value in row if value not in (None, "")]
        if values:
            parts.append(":".join(values))
    text = "|".join(parts)
    return text[:1800]


class ValidationEngine:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self.conn = conn
        self.checks: list[dict[str, Any]] = []

    def add(
        self,
        *,
        category: str,
        rule_id: str,
        description: str,
        severity: str,
        examined: int,
        failure_count: int,
        affected_ids: str,
        pass_message: str,
        fail_message: str,
    ) -> None:
        if failure_count == 0:
            status = "PASS"
            message = pass_message
        elif severity == "ERROR":
            status = "FAIL"
            message = fail_message
        else:
            status = "WARNING"
            message = fail_message
        check_id = f"CHK-{len(self.checks) + 1:04d}"
        self.checks.append(
            {
                "check_id": check_id,
                "category": category,
                "rule_id": rule_id,
                "description": description,
                "status": status,
                "severity": severity,
                "records_examined": examined,
                "failure_count": failure_count,
                "affected_record_ids": affected_ids,
                "message": message,
            }
        )

    def add_sql(
        self,
        *,
        category: str,
        rule_id: str,
        description: str,
        severity: str,
        examined_sql: str,
        count_sql: str,
        ids_sql: str,
        pass_message: str,
        fail_template: str,
    ) -> None:
        failure_count = _scalar(self.conn, count_sql)
        examined = _scalar(self.conn, examined_sql)
        affected = _sample_rows(self.conn, ids_sql) if failure_count else ""
        self.add(
            category=category,
            rule_id=rule_id,
            description=description,
            severity=severity,
            examined=examined,
            failure_count=failure_count,
            affected_ids=affected,
            pass_message=pass_message.format(examined=examined),
            fail_message=fail_template.format(count=failure_count, sample=affected),
        )


ID_FORMATS: dict[str, str] = {
    "channels": "channel_id|^CHN-[0-9]{6}$",
    "audiences": "audience_id|^AUD-[0-9]{6}$",
    "campaigns": "campaign_id|^CMP-2026-[0-9]{6}$",
    "creatives": "creative_id|^CRE-[0-9]{6}$",
    "contacts": "contact_id|^CON-2026-[0-9]{6}$",
    "sessions": "session_id|^SES-2026-[0-9]{6}$",
    "identity_links": "link_id|^LNK-2026-[0-9]{6}$",
    "touchpoints": "touchpoint_id|^TOUCH-2026-[0-9]{6}$",
    "leads": "lead_id|^LEAD-2026-[0-9]{6}$",
    "opportunities": "opportunity_id|^OPP-2026-[0-9]{6}$",
    "orders": "order_id|^ORD-2026-[0-9]{6}$",
    "cost_records": "cost_id|^COST-2026-[0-9]{6}$",
    "lifecycle_events": "event_id|^EVT-2026-[0-9]{6}$",
    "attribution_results": "attribution_result_id|^ATTR-2026-[0-9]{6}$",
    "attribution_conversions": "conversion_result_id|^CONV-2026-[0-9]{6}$",
    "exceptions": "issue_id|^ISS-2026-[0-9]{6}$",
}

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "channels": ("channel_id", "name", "category", "channel_type", "is_paid"),
    "audiences": ("audience_id", "name", "category", "definition", "status"),
    "campaigns": (
        "campaign_id",
        "name",
        "campaign_type",
        "objective",
        "start_at",
        "end_at",
        "status",
        "budget_amount",
        "budget_currency",
        "primary_channel_id",
        "target_audience_id",
    ),
    "creatives": ("creative_id", "campaign_id", "channel_id", "name", "creative_type", "status"),
    "contacts": (
        "contact_id",
        "created_at",
        "region",
        "country",
        "segment",
        "consent_status",
        "lifecycle_status",
        "acquisition_channel_id",
    ),
    "sessions": ("session_id", "anonymous_id", "started_at", "ended_at", "source", "medium", "landing_page"),
    "identity_links": ("link_id", "session_id", "contact_id", "evidence_type", "linked_at", "status", "rule_id"),
    "touchpoints": (
        "touchpoint_id",
        "campaign_id",
        "channel_id",
        "occurred_at",
        "touch_type",
        "source_system",
        "identity_status",
        "consent_status",
    ),
    "leads": ("lead_id", "contact_id", "created_at", "source", "status"),
    "opportunities": (
        "opportunity_id",
        "lead_id",
        "contact_id",
        "created_at",
        "stage",
        "expected_value",
        "currency",
        "outcome",
    ),
    "orders": (
        "order_id",
        "opportunity_id",
        "contact_id",
        "ordered_at",
        "status",
        "amount",
        "refunded_amount",
        "currency",
        "source_system_ref",
        "ingested_at",
    ),
    "cost_records": (
        "cost_id",
        "campaign_id",
        "cost_date",
        "amount",
        "currency",
        "cost_category",
        "source_ref",
    ),
    "lifecycle_events": ("event_id", "entity_type", "entity_id", "new_state", "occurred_at"),
    "campaign_channels": ("campaign_id", "channel_id", "is_primary"),
    "campaign_audiences": ("campaign_id", "audience_id"),
}

ENUM_CHECKS: dict[str, dict[str, tuple[str, ...]]] = {
    "channels": {
        "category": ("paid", "owned", "organic", "earned", "direct", "offline"),
        "channel_type": ("search", "social", "email", "referral", "display", "direct", "event"),
    },
    "campaigns": {
        "campaign_type": ("ACQUISITION", "NURTURE", "RETENTION", "BRAND", "PRODUCT_LAUNCH"),
        "objective": ("LEAD_GENERATION", "REVENUE", "AWARENESS", "RETENTION"),
        "status": ("PLANNED", "ACTIVE", "PAUSED", "COMPLETED"),
        "budget_currency": ("EUR", "USD", "GBP", "INR"),
    },
    "contacts": {
        "consent_status": ("GRANTED", "DENIED", "UNKNOWN"),
        "lifecycle_status": ("NEW", "ENGAGED", "QUALIFIED", "CUSTOMER", "DORMANT"),
    },
    "touchpoints": {
        "consent_status": ("GRANTED", "DENIED", "UNKNOWN"),
        "identity_status": ("DIRECT", "SESSION_LINKED", "UNRESOLVED"),
        "touch_type": (
            "IMPRESSION",
            "CLICK",
            "EMAIL_OPEN",
            "EMAIL_CLICK",
            "WEBINAR",
            "OFFLINE_EVENT",
            "PHONE_CALL",
            "FORM_SUBMIT",
        ),
    },
    "leads": {"status": ("NEW", "WORKING", "QUALIFIED", "DISQUALIFIED", "CONVERTED")},
    "opportunities": {
        "stage": ("OPEN", "QUALIFIED", "PROPOSAL", "NEGOTIATION", "CLOSED_WON", "CLOSED_LOST"),
        "outcome": ("OPEN", "WON", "LOST"),
        "currency": ("EUR", "USD", "GBP", "INR"),
    },
    "orders": {
        "status": ("PAID", "PARTIALLY_REFUNDED", "REFUNDED", "CANCELLED"),
        "currency": ("EUR", "USD", "GBP", "INR"),
    },
    "cost_records": {
        "currency": ("EUR", "USD", "GBP", "INR"),
        "cost_category": ("MEDIA", "PLATFORM_FEE", "CREATIVE", "EVENT", "INFLUENCER"),
    },
    "identity_links": {"status": ("VERIFIED", "REVERSED", "UNVERIFIED")},
}

FOREIGN_KEYS: tuple[tuple[str, str, str, str], ...] = (
    ("campaigns", "primary_channel_id", "channels", "channel_id"),
    ("campaigns", "target_audience_id", "audiences", "audience_id"),
    ("campaign_channels", "campaign_id", "campaigns", "campaign_id"),
    ("campaign_channels", "channel_id", "channels", "channel_id"),
    ("campaign_audiences", "campaign_id", "campaigns", "campaign_id"),
    ("campaign_audiences", "audience_id", "audiences", "audience_id"),
    ("creatives", "campaign_id", "campaigns", "campaign_id"),
    ("creatives", "channel_id", "channels", "channel_id"),
    ("sessions", "campaign_id", "campaigns", "campaign_id"),
    ("identity_links", "session_id", "sessions", "session_id"),
    ("identity_links", "contact_id", "contacts", "contact_id"),
    ("touchpoints", "contact_id", "contacts", "contact_id"),
    ("touchpoints", "session_id", "sessions", "session_id"),
    ("touchpoints", "campaign_id", "campaigns", "campaign_id"),
    ("touchpoints", "channel_id", "channels", "channel_id"),
    ("touchpoints", "creative_id", "creatives", "creative_id"),
    ("leads", "contact_id", "contacts", "contact_id"),
    ("leads", "source_session_id", "sessions", "session_id"),
    ("opportunities", "lead_id", "leads", "lead_id"),
    ("opportunities", "contact_id", "contacts", "contact_id"),
    ("orders", "opportunity_id", "opportunities", "opportunity_id"),
    ("orders", "contact_id", "contacts", "contact_id"),
    ("cost_records", "campaign_id", "campaigns", "campaign_id"),
    ("cost_records", "channel_id", "channels", "channel_id"),
)


def _pk_checks(engine: ValidationEngine) -> None:
    for table, spec in CORE_TABLES.items():
        columns = ", ".join(spec.primary_key)
        group = ", ".join(spec.primary_key)
        engine.add_sql(
            category="STRUCTURAL",
            rule_id="STR-PK-001",
            description=f"Primary key is unique in {table}",
            severity="ERROR",
            examined_sql=f'SELECT COUNT(*) FROM "{table}"',
            count_sql=(
                f'SELECT COUNT(*) FROM (SELECT {columns} FROM "{table}" '
                f"GROUP BY {group} HAVING COUNT(*) > 1) duplicate_keys"
            ),
            ids_sql=(
                f'SELECT {columns} FROM "{table}" GROUP BY {group} '
                f"HAVING COUNT(*) > 1 ORDER BY {columns} LIMIT {SAMPLE_LIMIT}"
            ),
            pass_message=f"All {{examined}} rows in {table} have unique primary keys.",
            fail_template=f"{{count}} duplicate primary keys found in {table}: {{sample}}",
        )


def _required_checks(engine: ValidationEngine) -> None:
    for table, fields in REQUIRED_FIELDS.items():
        if table not in CORE_TABLES:
            continue
        pk = CORE_TABLES[table].primary_key[0]
        clauses = " OR ".join(f"({field} IS NULL OR trim({field}) = '')" for field in fields)
        engine.add_sql(
            category="STRUCTURAL",
            rule_id="STR-REQ-001",
            description=f"Required fields are populated in {table}",
            severity="ERROR",
            examined_sql=f'SELECT COUNT(*) FROM "{table}"',
            count_sql=f'SELECT COUNT(*) FROM "{table}" WHERE {clauses}',
            ids_sql=f'SELECT {pk} FROM "{table}" WHERE {clauses} ORDER BY {pk} LIMIT {SAMPLE_LIMIT}',
            pass_message=f"All {{examined}} rows in {table} contain required fields.",
            fail_template=f"{{count}} rows in {table} have missing required fields: {{sample}}",
        )


def _enum_checks(engine: ValidationEngine) -> None:
    for table, fields in ENUM_CHECKS.items():
        if table not in CORE_TABLES:
            continue
        pk = CORE_TABLES[table].primary_key[0]
        for field, allowed in fields.items():
            values = ", ".join(f"'{value}'" for value in allowed)
            condition = f"{field} NOT IN ({values}) OR {field} IS NULL"
            engine.add_sql(
                category="STRUCTURAL",
                rule_id="STR-ENUM-001",
                description=f"Enum values for {table}.{field} are valid",
                severity="ERROR",
                examined_sql=f'SELECT COUNT(*) FROM "{table}"',
                count_sql=f'SELECT COUNT(*) FROM "{table}" WHERE {condition}',
                ids_sql=(
                    f'SELECT {pk}, {field} FROM "{table}" WHERE {condition} '
                    f"ORDER BY {pk} LIMIT {SAMPLE_LIMIT}"
                ),
                pass_message=f"All {{examined}} {table}.{field} values are valid.",
                fail_template=f"{{count}} invalid {table}.{field} values: {{sample}}",
            )


def _id_checks(engine: ValidationEngine) -> None:
    for table, definition in ID_FORMATS.items():
        if not _table_exists(engine.conn, table):
            continue
        field, pattern = definition.split("|", 1)
        condition = f"NOT regexp_matches({field}, '{pattern}') OR {field} IS NULL"
        engine.add_sql(
            category="STRUCTURAL",
            rule_id="STR-ID-001",
            description=f"Identifiers in {table} follow the documented format",
            severity="ERROR",
            examined_sql=f'SELECT COUNT(*) FROM "{table}"',
            count_sql=f'SELECT COUNT(*) FROM "{table}" WHERE {condition}',
            ids_sql=f'SELECT {field} FROM "{table}" WHERE {condition} ORDER BY 1 LIMIT {SAMPLE_LIMIT}',
            pass_message=f"All {{examined}} identifiers in {table} match the canonical format.",
            fail_template=f"{{count}} malformed identifiers in {table}: {{sample}}",
        )


def _fk_checks(engine: ValidationEngine) -> None:
    for child, child_col, parent, parent_col in FOREIGN_KEYS:
        pk = CORE_TABLES[child].primary_key[0]
        missing_condition = (
            f"{child}.{child_col} IS NOT NULL AND trim({child}.{child_col}) <> '' "
            f"AND {parent}.{parent_col} IS NULL"
        )
        engine.add_sql(
            category="STRUCTURAL",
            rule_id="STR-FK-001",
            description=f"{child}.{child_col} references {parent}.{parent_col}",
            severity="ERROR",
            examined_sql=(
                f'SELECT COUNT(*) FROM "{child}" WHERE {child_col} IS NOT NULL AND trim({child_col}) <> \'\''
            ),
            count_sql=(
                f'SELECT COUNT(*) FROM "{child}" LEFT JOIN "{parent}" '
                f'ON "{parent}".{parent_col} = "{child}".{child_col} WHERE {missing_condition}'
            ),
            ids_sql=(
                f'SELECT "{child}".{pk} FROM "{child}" LEFT JOIN "{parent}" '
                f'ON "{parent}".{parent_col} = "{child}".{child_col} WHERE {missing_condition} '
                f'ORDER BY 1 LIMIT {SAMPLE_LIMIT}'
            ),
            pass_message=f"All {{examined}} non-null {child}.{child_col} references resolve.",
            fail_template=f"{{count}} unresolved {child}.{child_col} references: {{sample}}",
        )


def _duplicate_business_key_check(engine: ValidationEngine) -> None:
    engine.add_sql(
        category="STRUCTURAL",
        rule_id="STR-DUP-001",
        description="Order source transaction keys identify one economic transaction",
        severity="WARNING",
        examined_sql="SELECT COUNT(*) FROM orders",
        count_sql=(
            "SELECT COUNT(*) FROM orders WHERE source_system_ref IN "
            "(SELECT source_system_ref FROM orders GROUP BY source_system_ref HAVING COUNT(*) > 1)"
        ),
        ids_sql=(
            "SELECT order_id FROM orders WHERE source_system_ref IN "
            "(SELECT source_system_ref FROM orders GROUP BY source_system_ref HAVING COUNT(*) > 1) "
            f"ORDER BY order_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} orders have a unique source transaction key.",
        fail_template=(
            "{count} order rows share a source transaction key (expected anomaly fixture): {sample}"
        ),
    )


def _temporal_checks(engine: ValidationEngine) -> None:
    checks = [
        (
            "TMP-CAMPAIGN-001",
            "Campaign end timestamp follows start timestamp",
            "v_campaigns",
            "campaign_id",
            "end_ts <= start_ts",
            "All {examined} campaigns have valid effective dates.",
        ),
        (
            "TMP-LEAD-001",
            "Lead qualification timestamp follows lead creation",
            "v_leads",
            "lead_id",
            "qualified_ts IS NOT NULL AND qualified_ts < created_ts",
            "All {examined} qualified leads have chronological qualification timestamps.",
        ),
        (
            "TMP-OPP-001",
            "Opportunity close timestamp follows creation",
            "v_opportunities",
            "opportunity_id",
            "closed_ts IS NOT NULL AND closed_ts < created_ts",
            "All {examined} closed opportunities have chronological close timestamps.",
        ),
        (
            "TMP-ORDER-001",
            "Order ingestion timestamp follows order timestamp",
            "v_orders",
            "order_id",
            "ingested_ts < ordered_ts",
            "All {examined} orders have ingestion after the business event.",
        ),
    ]
    for rule_id, description, view, pk, condition, pass_message in checks:
        engine.add_sql(
            category="TEMPORAL",
            rule_id=rule_id,
            description=description,
            severity="ERROR",
            examined_sql=f"SELECT COUNT(*) FROM {view}",
            count_sql=f"SELECT COUNT(*) FROM {view} WHERE {condition}",
            ids_sql=f"SELECT {pk} FROM {view} WHERE {condition} ORDER BY {pk} LIMIT {SAMPLE_LIMIT}",
            pass_message=pass_message,
            fail_template=f"{{count}} records violate {rule_id}: {{sample}}",
        )

    engine.add_sql(
        category="TEMPORAL",
        rule_id="TMP-ORDER-002",
        description="Orders occur after their opportunity is created",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_orders",
        count_sql=(
            "SELECT COUNT(*) FROM v_orders o JOIN v_opportunities p "
            "ON p.opportunity_id = o.opportunity_id WHERE o.ordered_ts < p.created_ts"
        ),
        ids_sql=(
            "SELECT o.order_id FROM v_orders o JOIN v_opportunities p "
            "ON p.opportunity_id = o.opportunity_id WHERE o.ordered_ts < p.created_ts "
            f"ORDER BY o.order_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} orders occur after their parent opportunity.",
        fail_template="{count} orders precede their opportunity creation: {sample}",
    )
    engine.add_sql(
        category="TEMPORAL",
        rule_id="TMP-COST-001",
        description="Cost dates fall within the campaign effective period",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_costs",
        count_sql=(
            "SELECT COUNT(*) FROM v_costs c JOIN v_campaigns p ON p.campaign_id = c.campaign_id "
            "WHERE c.cost_date_d < CAST(p.start_ts AS DATE) OR c.cost_date_d > CAST(p.end_ts AS DATE)"
        ),
        ids_sql=(
            "SELECT c.cost_id FROM v_costs c JOIN v_campaigns p ON p.campaign_id = c.campaign_id "
            "WHERE c.cost_date_d < CAST(p.start_ts AS DATE) OR c.cost_date_d > CAST(p.end_ts AS DATE) "
            f"ORDER BY c.cost_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} cost records fall inside campaign effective dates.",
        fail_template="{count} cost records fall outside campaign dates: {sample}",
    )
    engine.add_sql(
        category="TEMPORAL",
        rule_id="TMP-TOUCH-001",
        description="Touchpoints occur within their campaign effective period",
        severity="WARNING",
        examined_sql="SELECT COUNT(*) FROM v_touchpoints",
        count_sql=(
            "SELECT COUNT(*) FROM v_touchpoints t JOIN v_campaigns c ON c.campaign_id = t.campaign_id "
            "WHERE t.occurred_ts < c.start_ts OR t.occurred_ts > c.end_ts"
        ),
        ids_sql=(
            "SELECT t.touchpoint_id FROM v_touchpoints t JOIN v_campaigns c "
            "ON c.campaign_id = t.campaign_id WHERE t.occurred_ts < c.start_ts OR t.occurred_ts > c.end_ts "
            f"ORDER BY t.touchpoint_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} touchpoints fall within campaign effective dates.",
        fail_template="{count} touchpoints fall outside campaign dates: {sample}",
    )
    engine.add_sql(
        category="TEMPORAL",
        rule_id="TMP-POST-001",
        description="Touchpoints after a conversion are detected and visible",
        severity="WARNING",
        examined_sql="SELECT COUNT(*) FROM v_touchpoints",
        count_sql=(
            "WITH supported AS ("
            " SELECT session_id, contact_id FROM v_identity_links"
            " WHERE status = 'VERIFIED' AND trim(evidence_ref) <> ''"
            " AND evidence_type IN (" + ", ".join(f"'{item}'" for item in ALLOWED_IDENTITY_EVIDENCE) + ")"
            "), resolved AS ("
            " SELECT t.touchpoint_id, COALESCE(t.contact_id, s.contact_id) AS contact_id, t.occurred_ts"
            " FROM v_touchpoints t LEFT JOIN supported s ON s.session_id = t.session_id"
            ") SELECT COUNT(DISTINCT r.touchpoint_id) FROM resolved r"
            " JOIN v_orders o ON o.contact_id = r.contact_id"
            " WHERE o.status IN ('PAID', 'PARTIALLY_REFUNDED') AND r.occurred_ts > o.ordered_ts"
        ),
        ids_sql=(
            "WITH supported AS ("
            " SELECT session_id, contact_id FROM v_identity_links"
            " WHERE status = 'VERIFIED' AND trim(evidence_ref) <> ''"
            " AND evidence_type IN (" + ", ".join(f"'{item}'" for item in ALLOWED_IDENTITY_EVIDENCE) + ")"
            "), resolved AS ("
            " SELECT t.touchpoint_id, COALESCE(t.contact_id, s.contact_id) AS contact_id, t.occurred_ts"
            " FROM v_touchpoints t LEFT JOIN supported s ON s.session_id = t.session_id"
            ") SELECT DISTINCT r.touchpoint_id FROM resolved r"
            " JOIN v_orders o ON o.contact_id = r.contact_id"
            " WHERE o.status IN ('PAID', 'PARTIALLY_REFUNDED') AND r.occurred_ts > o.ordered_ts"
            f" ORDER BY r.touchpoint_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="No post-conversion touches were found among {examined} touchpoints.",
        fail_template="{count} post-conversion touches detected (expected injected fixtures): {sample}",
    )


def _financial_checks(engine: ValidationEngine) -> None:
    engine.add_sql(
        category="FINANCIAL",
        rule_id="FIN-AMOUNT-001",
        description="Order amounts and refunds are financially valid",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_orders",
        count_sql=(
            "SELECT COUNT(*) FROM v_orders WHERE amount_dec < 0 OR refunded_dec < 0 "
            "OR refunded_dec > amount_dec"
        ),
        ids_sql=(
            "SELECT order_id FROM v_orders WHERE amount_dec < 0 OR refunded_dec < 0 "
            f"OR refunded_dec > amount_dec ORDER BY order_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} orders have valid amounts and refunds.",
        fail_template="{count} orders have invalid amounts or refunds: {sample}",
    )
    engine.add_sql(
        category="FINANCIAL",
        rule_id="FIN-AMOUNT-002",
        description="Cost records and campaign budgets are non-negative",
        severity="ERROR",
        examined_sql="SELECT (SELECT COUNT(*) FROM v_costs) + (SELECT COUNT(*) FROM v_campaigns)",
        count_sql=(
            "SELECT (SELECT COUNT(*) FROM v_costs WHERE amount_dec < 0) "
            "+ (SELECT COUNT(*) FROM v_campaigns WHERE budget_dec < 0)"
        ),
        ids_sql=(
            "SELECT cost_id AS entity_id FROM v_costs WHERE amount_dec < 0 "
            "UNION ALL SELECT campaign_id FROM v_campaigns WHERE budget_dec < 0 "
            f"ORDER BY entity_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} financial source records are non-negative.",
        fail_template="{count} financial records contain negative amounts: {sample}",
    )
    engine.add_sql(
        category="FINANCIAL",
        rule_id="FIN-CURMISMATCH-001",
        description="Cost currency matches the campaign budget currency",
        severity="WARNING",
        examined_sql="SELECT COUNT(*) FROM v_costs",
        count_sql=(
            "SELECT COUNT(*) FROM v_costs c JOIN v_campaigns p ON p.campaign_id = c.campaign_id "
            "WHERE c.currency <> p.budget_currency"
        ),
        ids_sql=(
            "SELECT c.cost_id FROM v_costs c JOIN v_campaigns p ON p.campaign_id = c.campaign_id "
            f"WHERE c.currency <> p.budget_currency ORDER BY c.cost_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} cost records use the campaign currency.",
        fail_template=(
            "{count} cost records have incompatible currencies and are quarantined (fixtures): {sample}"
        ),
    )
    engine.add_sql(
        category="FINANCIAL",
        rule_id="FIN-MISSINGCOST-001",
        description="Budgeted campaigns have compatible actual-spend records",
        severity="WARNING",
        examined_sql="SELECT COUNT(*) FROM v_campaigns WHERE budget_dec > 0",
        count_sql=(
            "SELECT COUNT(*) FROM v_campaigns c WHERE c.budget_dec > 0 AND NOT EXISTS ("
            " SELECT 1 FROM v_costs co WHERE co.campaign_id = c.campaign_id "
            " AND co.currency = c.budget_currency)"
        ),
        ids_sql=(
            "SELECT c.campaign_id FROM v_campaigns c WHERE c.budget_dec > 0 AND NOT EXISTS ("
            " SELECT 1 FROM v_costs co WHERE co.campaign_id = c.campaign_id "
            f" AND co.currency = c.budget_currency) ORDER BY c.campaign_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} budgeted campaigns have compatible cost coverage.",
        fail_template="{count} budgeted campaigns have missing compatible costs (fixtures): {sample}",
    )
    engine.add_sql(
        category="FINANCIAL",
        rule_id="FIN-DUPREV-001",
        description="Duplicate economic transactions are detected",
        severity="WARNING",
        examined_sql="SELECT COUNT(*) FROM v_orders",
        count_sql=(
            "SELECT COUNT(*) FROM orders WHERE source_system_ref IN "
            "(SELECT source_system_ref FROM orders GROUP BY source_system_ref HAVING COUNT(*) > 1)"
        ),
        ids_sql=(
            "SELECT order_id FROM orders WHERE source_system_ref IN "
            "(SELECT source_system_ref FROM orders GROUP BY source_system_ref HAVING COUNT(*) > 1) "
            f"ORDER BY order_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="No duplicate source transactions were found among {examined} orders.",
        fail_template="{count} duplicate order rows share a source key (fixtures): {sample}",
    )
    if _table_exists(engine.conn, "attribution_conversions"):
        engine.add_sql(
            category="FINANCIAL",
            rule_id="FIN-ATTRRECON-001",
            description="Attributed revenue reconciles to conversion revenue per order and model",
            severity="ERROR",
            examined_sql="SELECT COUNT(*) FROM v_attribution_conversions",
            count_sql=(
                "SELECT COUNT(*) FROM ("
                " SELECT ac.order_id, ac.model, ac.status, ac.conversion_revenue_dec,"
                " ac.attributed_revenue_dec, COALESCE(SUM(ar.attributed_revenue_dec), 0) AS credit_sum"
                " FROM v_attribution_conversions ac LEFT JOIN v_attribution_results ar"
                " ON ar.order_id = ac.order_id AND ar.model = ac.model"
                " GROUP BY ac.order_id, ac.model, ac.status, ac.conversion_revenue_dec, ac.attributed_revenue_dec"
                " HAVING ac.attributed_revenue_dec <> credit_sum"
                " OR (ac.status = 'ATTRIBUTED' AND ac.conversion_revenue_dec <> credit_sum)"
                " OR (ac.status = 'UNATTRIBUTED' AND credit_sum <> 0)"
                ") mismatches"
            ),
            ids_sql=(
                "SELECT ac.order_id, ac.model FROM v_attribution_conversions ac"
                " LEFT JOIN v_attribution_results ar ON ar.order_id = ac.order_id AND ar.model = ac.model"
                " GROUP BY ac.order_id, ac.model, ac.status, ac.conversion_revenue_dec, ac.attributed_revenue_dec"
                " HAVING ac.attributed_revenue_dec <> COALESCE(SUM(ar.attributed_revenue_dec), 0)"
                " OR (ac.status = 'ATTRIBUTED' AND ac.conversion_revenue_dec <> COALESCE(SUM(ar.attributed_revenue_dec), 0))"
                " OR (ac.status = 'UNATTRIBUTED' AND COALESCE(SUM(ar.attributed_revenue_dec), 0) <> 0)"
                f" ORDER BY ac.order_id, ac.model LIMIT {SAMPLE_LIMIT}"
            ),
            pass_message="All {examined} conversion/model results reconcile to the cent.",
            fail_template="{count} attribution reconciliation mismatches: {sample}",
        )
        engine.add_sql(
            category="FINANCIAL",
            rule_id="FIN-CREDSUM-001",
            description="Attribution credit fractions sum to one for attributed conversions",
            severity="ERROR",
            examined_sql="SELECT COUNT(*) FROM v_attribution_conversions",
            count_sql=(
                "SELECT COUNT(*) FROM ("
                " SELECT ac.order_id, ac.model, MAX(ac.status) AS status,"
                " COALESCE(SUM(ar.credit_fraction_dec), 0) AS credit_sum"
                " FROM v_attribution_conversions ac LEFT JOIN v_attribution_results ar"
                " ON ar.order_id = ac.order_id AND ar.model = ac.model"
                " GROUP BY ac.order_id, ac.model"
                " HAVING (MAX(ac.status) = 'ATTRIBUTED' AND ABS(credit_sum - 1) > 0.000001)"
                " OR (MAX(ac.status) = 'UNATTRIBUTED' AND ABS(credit_sum) > 0.000001)"
                ") mismatches"
            ),
            ids_sql=(
                "SELECT ac.order_id, ac.model FROM v_attribution_conversions ac"
                " LEFT JOIN v_attribution_results ar ON ar.order_id = ac.order_id AND ar.model = ac.model"
                " GROUP BY ac.order_id, ac.model"
                " HAVING (MAX(ac.status) = 'ATTRIBUTED' AND ABS(COALESCE(SUM(ar.credit_fraction_dec), 0) - 1) > 0.000001)"
                " OR (MAX(ac.status) = 'UNATTRIBUTED' AND ABS(COALESCE(SUM(ar.credit_fraction_dec), 0)) > 0.000001)"
                f" ORDER BY ac.order_id, ac.model LIMIT {SAMPLE_LIMIT}"
            ),
            pass_message="All {examined} credit-fraction sums are valid.",
            fail_template="{count} credit-fraction totals violate the invariant: {sample}",
        )
        if _table_exists(engine.conn, "campaign_performance"):
            engine.add_sql(
                category="FINANCIAL",
                rule_id="FIN-ROI-001",
                description="ROI and ROAS are withheld when cost coverage is insufficient",
                severity="ERROR",
                examined_sql="SELECT COUNT(*) FROM campaign_performance",
                count_sql=(
                "SELECT COUNT(*) FROM campaign_performance WHERE"
                " (cost_coverage <> 'COMPLETE' AND roi_available = 'true')"
                " OR (roi_available = 'true' AND (roi_pct IS NULL OR trim(roi_pct) = ''))"
                " OR (roi_available = 'true' AND CAST(spend AS DECIMAL(18,2)) <= 0)"
                ),
                ids_sql=(
                "SELECT campaign_id, model FROM campaign_performance WHERE"
                " (cost_coverage <> 'COMPLETE' AND roi_available = 'true')"
                " OR (roi_available = 'true' AND (roi_pct IS NULL OR trim(roi_pct) = ''))"
                " OR (roi_available = 'true' AND CAST(spend AS DECIMAL(18,2)) <= 0)"
                f" ORDER BY campaign_id, model LIMIT {SAMPLE_LIMIT}"
                ),
                pass_message="ROI availability is correctly withheld across {examined} campaign/model rows.",
                fail_template="{count} rows report ROI with an invalid cost basis: {sample}",
        )

def _identity_checks(engine: ValidationEngine) -> None:
    allowed = ", ".join(f"'{item}'" for item in ALLOWED_IDENTITY_EVIDENCE)
    engine.add_sql(
        category="IDENTITY",
        rule_id="IDN-EVIDENCE-001",
        description="Identity links use supported evidence and a reference",
        severity="WARNING",
        examined_sql="SELECT COUNT(*) FROM v_identity_links",
        count_sql=(
            f"SELECT COUNT(*) FROM v_identity_links WHERE status = 'VERIFIED' AND "
            f"(evidence_type NOT IN ({allowed}) OR evidence_ref IS NULL OR trim(evidence_ref) = '')"
        ),
        ids_sql=(
            "SELECT link_id, session_id FROM v_identity_links WHERE status = 'VERIFIED' AND "
            "(evidence_type NOT IN ("
            + allowed
            + ") OR evidence_ref IS NULL OR trim(evidence_ref) = '')"
            f" ORDER BY link_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} verified identity links have supported evidence.",
        fail_template=(
            "{count} verified identity links lack supported evidence (fixtures): {sample}"
        ),
    )
    engine.add_sql(
        category="IDENTITY",
        rule_id="IDN-AMBIGUOUS-001",
        description="Each session has at most one supported contact resolution",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM sessions",
        count_sql=(
            "SELECT COUNT(*) FROM (SELECT session_id FROM v_identity_links"
            f" WHERE status = 'VERIFIED' AND evidence_type IN ({allowed})"
            " AND trim(evidence_ref) <> '' GROUP BY session_id"
            " HAVING COUNT(DISTINCT contact_id) > 1) ambiguous"
        ),
        ids_sql=(
            "SELECT session_id FROM v_identity_links"
            f" WHERE status = 'VERIFIED' AND evidence_type IN ({allowed})"
            " AND trim(evidence_ref) <> '' GROUP BY session_id"
            f" HAVING COUNT(DISTINCT contact_id) > 1 ORDER BY session_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} sessions have unambiguous identity resolution.",
        fail_template="{count} sessions have conflicting supported identity links: {sample}",
    )


def _attribution_checks(engine: ValidationEngine) -> None:
    allowed = ", ".join(f"'{item}'" for item in ALLOWED_IDENTITY_EVIDENCE)
    engine.add_sql(
        category="ATTRIBUTION",
        rule_id="ATT-TEMPORAL-001",
        description="No post-conversion touchpoint receives attribution credit",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_attribution_results",
        count_sql=(
            "SELECT COUNT(*) FROM v_attribution_results ar"
            " JOIN v_touchpoints t ON t.touchpoint_id = ar.touchpoint_id"
            " JOIN v_orders o ON o.order_id = ar.order_id"
            " WHERE t.occurred_ts > o.ordered_ts"
        ),
        ids_sql=(
            "SELECT ar.attribution_result_id FROM v_attribution_results ar"
            " JOIN v_touchpoints t ON t.touchpoint_id = ar.touchpoint_id"
            " JOIN v_orders o ON o.order_id = ar.order_id"
            f" WHERE t.occurred_ts > o.ordered_ts ORDER BY 1 LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="No post-conversion touchpoint receives credit across {examined} results.",
        fail_template="{count} attribution results credit a post-conversion touch: {sample}",
    )
    engine.add_sql(
        category="ATTRIBUTION",
        rule_id="ATT-LOOKBACK-001",
        description="No touchpoint outside the lookback window receives credit",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_attribution_results",
        count_sql=(
            "SELECT COUNT(*) FROM v_attribution_results ar"
            " JOIN v_touchpoints t ON t.touchpoint_id = ar.touchpoint_id"
            " JOIN v_orders o ON o.order_id = ar.order_id"
            " WHERE t.occurred_ts < o.ordered_ts - INTERVAL 90 DAY"
        ),
        ids_sql=(
            "SELECT ar.attribution_result_id FROM v_attribution_results ar"
            " JOIN v_touchpoints t ON t.touchpoint_id = ar.touchpoint_id"
            " JOIN v_orders o ON o.order_id = ar.order_id"
            " WHERE t.occurred_ts < o.ordered_ts - INTERVAL 90 DAY"
            f" ORDER BY 1 LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} credited touches are inside the 90-day window.",
        fail_template="{count} credited touches are outside the lookback window: {sample}",
    )
    engine.add_sql(
        category="ATTRIBUTION",
        rule_id="ATT-CONSENT-001",
        description="Only consent-eligible touchpoints receive attribution credit",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_attribution_results",
        count_sql=(
            "SELECT COUNT(*) FROM v_attribution_results ar"
            " JOIN v_touchpoints t ON t.touchpoint_id = ar.touchpoint_id"
            " JOIN v_orders o ON o.order_id = ar.order_id"
            " JOIN v_contacts c ON c.contact_id = o.contact_id"
            " WHERE t.consent_status <> 'GRANTED' OR c.consent_status <> 'GRANTED'"
        ),
        ids_sql=(
            "SELECT ar.attribution_result_id FROM v_attribution_results ar"
            " JOIN v_touchpoints t ON t.touchpoint_id = ar.touchpoint_id"
            " JOIN v_orders o ON o.order_id = ar.order_id"
            " JOIN v_contacts c ON c.contact_id = o.contact_id"
            " WHERE t.consent_status <> 'GRANTED' OR c.consent_status <> 'GRANTED'"
            f" ORDER BY 1 LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} credited touches are consent-eligible.",
        fail_template="{count} credited touches lack consent eligibility: {sample}",
    )
    engine.add_sql(
        category="ATTRIBUTION",
        rule_id="ATT-IDENTITY-001",
        description="Credited touchpoints resolve to the converting contact with supported evidence",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_attribution_results",
        count_sql=(
            "WITH supported AS (SELECT session_id, contact_id FROM v_identity_links"
            f" WHERE status = 'VERIFIED' AND evidence_type IN ({allowed}) AND trim(evidence_ref) <> ''),"
            " resolved AS (SELECT t.touchpoint_id, COALESCE(t.contact_id, s.contact_id) AS resolved_contact"
            " FROM v_touchpoints t LEFT JOIN supported s ON s.session_id = t.session_id)"
            " SELECT COUNT(*) FROM v_attribution_results ar"
            " JOIN resolved r ON r.touchpoint_id = ar.touchpoint_id"
            " JOIN v_orders o ON o.order_id = ar.order_id"
            " WHERE r.resolved_contact IS DISTINCT FROM o.contact_id"
        ),
        ids_sql=(
            "WITH supported AS (SELECT session_id, contact_id FROM v_identity_links"
            f" WHERE status = 'VERIFIED' AND evidence_type IN ({allowed}) AND trim(evidence_ref) <> ''),"
            " resolved AS (SELECT t.touchpoint_id, COALESCE(t.contact_id, s.contact_id) AS resolved_contact"
            " FROM v_touchpoints t LEFT JOIN supported s ON s.session_id = t.session_id)"
            " SELECT ar.attribution_result_id FROM v_attribution_results ar"
            " JOIN resolved r ON r.touchpoint_id = ar.touchpoint_id"
            " JOIN v_orders o ON o.order_id = ar.order_id"
            " WHERE r.resolved_contact IS DISTINCT FROM o.contact_id"
            f" ORDER BY 1 LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} credited touches have supported identity resolution.",
        fail_template="{count} credited touches lack supported identity evidence: {sample}",
    )
    engine.add_sql(
        category="ATTRIBUTION",
        rule_id="ATT-REFERENCES-001",
        description="Attribution results reference valid orders, touchpoints and campaigns",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_attribution_results",
        count_sql=(
            "SELECT COUNT(*) FROM v_attribution_results ar"
            " LEFT JOIN v_orders o ON o.order_id = ar.order_id"
            " LEFT JOIN v_touchpoints t ON t.touchpoint_id = ar.touchpoint_id"
            " LEFT JOIN v_campaigns c ON c.campaign_id = ar.campaign_id"
            " WHERE o.order_id IS NULL OR t.touchpoint_id IS NULL OR c.campaign_id IS NULL"
        ),
        ids_sql=(
            "SELECT ar.attribution_result_id FROM v_attribution_results ar"
            " LEFT JOIN v_orders o ON o.order_id = ar.order_id"
            " LEFT JOIN v_touchpoints t ON t.touchpoint_id = ar.touchpoint_id"
            " LEFT JOIN v_campaigns c ON c.campaign_id = ar.campaign_id"
            " WHERE o.order_id IS NULL OR t.touchpoint_id IS NULL OR c.campaign_id IS NULL"
            f" ORDER BY 1 LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} attribution records have valid source references.",
        fail_template="{count} attribution records contain broken references: {sample}",
    )
    engine.add_sql(
        category="ATTRIBUTION",
        rule_id="ATT-COMPLETE-001",
        description="Every canonical conversion has all three attribution models",
        severity="ERROR",
        examined_sql=(
            "WITH ranked AS (SELECT order_id, ROW_NUMBER() OVER ("
            " PARTITION BY source_system_ref ORDER BY ingested_ts, order_id) AS rn"
            " FROM v_orders WHERE status IN ('PAID', 'PARTIALLY_REFUNDED')"
            ") SELECT COUNT(*) FROM ranked r JOIN v_orders o ON o.order_id = r.order_id"
            " WHERE r.rn = 1 AND o.recognized_revenue_dec > 0"
        ),
        count_sql=(
            "WITH canonical AS (SELECT order_id, ROW_NUMBER() OVER ("
            " PARTITION BY source_system_ref ORDER BY ingested_ts, order_id) AS rn"
            " FROM v_orders WHERE status IN ('PAID', 'PARTIALLY_REFUNDED')"
            "), expected AS (SELECT c.order_id FROM canonical c JOIN v_orders o"
            " ON o.order_id = c.order_id WHERE c.rn = 1 AND o.recognized_revenue_dec > 0),"
            " actual AS (SELECT order_id, COUNT(DISTINCT model) AS model_count"
            " FROM v_attribution_conversions GROUP BY order_id)"
            " SELECT (SELECT COUNT(*) FROM expected e LEFT JOIN actual a USING (order_id)"
            " WHERE COALESCE(a.model_count, 0) <> 3) + (SELECT COUNT(*) FROM actual a"
            " LEFT JOIN expected e USING (order_id) WHERE e.order_id IS NULL)"
        ),
        ids_sql=(
            "WITH canonical AS (SELECT order_id, ROW_NUMBER() OVER ("
            " PARTITION BY source_system_ref ORDER BY ingested_ts, order_id) AS rn"
            " FROM v_orders WHERE status IN ('PAID', 'PARTIALLY_REFUNDED')"
            "), expected AS (SELECT c.order_id FROM canonical c JOIN v_orders o"
            " ON o.order_id = c.order_id WHERE c.rn = 1 AND o.recognized_revenue_dec > 0),"
            " actual AS (SELECT order_id, COUNT(DISTINCT model) AS model_count"
            " FROM v_attribution_conversions GROUP BY order_id)"
            " SELECT e.order_id FROM expected e LEFT JOIN actual a USING (order_id)"
            " WHERE COALESCE(a.model_count, 0) <> 3"
            " UNION ALL SELECT a.order_id FROM actual a LEFT JOIN expected e USING (order_id)"
            " WHERE e.order_id IS NULL"
            f" ORDER BY 1 LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} canonical conversions have complete model coverage.",
        fail_template="{count} conversions have missing or extra model results: {sample}",
    )
    engine.add_sql(
        category="ATTRIBUTION",
        rule_id="ATT-DUPREV-001",
        description="Duplicate source transactions never receive attribution",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_attribution_results",
        count_sql=(
            "WITH ranked AS (SELECT order_id, ROW_NUMBER() OVER ("
            " PARTITION BY source_system_ref ORDER BY ingested_ts, order_id) AS rn FROM v_orders)"
            " SELECT COUNT(*) FROM v_attribution_results ar JOIN ranked r"
            " ON r.order_id = ar.order_id WHERE r.rn > 1"
        ),
        ids_sql=(
            "WITH ranked AS (SELECT order_id, ROW_NUMBER() OVER ("
            " PARTITION BY source_system_ref ORDER BY ingested_ts, order_id) AS rn FROM v_orders)"
            " SELECT ar.attribution_result_id FROM v_attribution_results ar JOIN ranked r"
            " ON r.order_id = ar.order_id WHERE r.rn > 1"
            f" ORDER BY 1 LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="No duplicate source transaction receives credit across {examined} results.",
        fail_template="{count} attribution results reference duplicate revenue: {sample}",
    )
    engine.add_sql(
        category="ATTRIBUTION",
        rule_id="ATT-UNATTRIBUTED-001",
        description="Unattributed conversions are explicitly identified",
        severity="ERROR",
        examined_sql="SELECT COUNT(*) FROM v_attribution_conversions",
        count_sql=(
            "SELECT COUNT(*) FROM v_attribution_conversions WHERE"
            " (status = 'UNATTRIBUTED' AND (exclusion_reason IS NULL OR trim(exclusion_reason) = ''))"
            " OR (status = 'ATTRIBUTED' AND attributed_touchpoints_int = 0)"
            " OR (status = 'UNATTRIBUTED' AND attributed_touchpoints_int > 0)"
        ),
        ids_sql=(
            "SELECT order_id, model FROM v_attribution_conversions WHERE"
            " (status = 'UNATTRIBUTED' AND (exclusion_reason IS NULL OR trim(exclusion_reason) = ''))"
            " OR (status = 'ATTRIBUTED' AND attributed_touchpoints_int = 0)"
            " OR (status = 'UNATTRIBUTED' AND attributed_touchpoints_int > 0)"
            f" ORDER BY order_id LIMIT {SAMPLE_LIMIT}"
        ),
        pass_message="All {examined} conversion outcomes have consistent attribution status.",
        fail_template="{count} conversion outcomes have inconsistent status: {sample}",
    )


def _lifecycle_checks(engine: ValidationEngine) -> None:
    rows = engine.conn.execute(
        "SELECT event_id, entity_type, entity_id, previous_state, new_state, occurred_ts "
        "FROM v_lifecycle_events ORDER BY entity_type, entity_id, occurred_ts, event_id"
    ).fetchall()
    status_maps: dict[str, dict[str, str]] = {
        "CAMPAIGN": dict(engine.conn.execute("SELECT campaign_id, status FROM campaigns").fetchall()),
        "CONTACT": dict(
            engine.conn.execute("SELECT contact_id, lifecycle_status FROM contacts").fetchall()
        ),
        "LEAD": dict(engine.conn.execute("SELECT lead_id, status FROM leads").fetchall()),
        "OPPORTUNITY": dict(
            engine.conn.execute("SELECT opportunity_id, stage FROM opportunities").fetchall()
        ),
        "ORDER": dict(engine.conn.execute("SELECT order_id, status FROM orders").fetchall()),
    }

    invalid_transitions: dict[str, list[str]] = defaultdict(list)
    status_mismatches: dict[str, list[str]] = defaultdict(list)
    latest: dict[tuple[str, str], tuple[str, datetime]] = {}
    current_entity: tuple[str, str] | None = None
    previous_state = ""
    last_ts: datetime | None = None

    for _event_id, entity_type, entity_id, previous, new_state, occurred_ts in rows:
        key = (entity_type, entity_id)
        if key != current_entity:
            current_entity = key
            previous_state = ""
            last_ts = None
        previous = previous or ""
        problems = []
        if previous != previous_state:
            problems.append(f"previous_state {previous!r} does not match {previous_state!r}")
        if last_ts is not None and occurred_ts < last_ts:
            problems.append("timestamp is earlier than the prior event")
        if not is_valid_transition(entity_type, previous, new_state):
            problems.append(f"transition {previous!r}->{new_state!r} is not allowed")
        if problems:
            invalid_transitions[entity_type].append(f"{entity_id} ({'; '.join(problems)})")
        previous_state = new_state
        last_ts = occurred_ts
        latest[key] = (new_state, occurred_ts)

    for entity_type, status_map in status_maps.items():
        for entity_id, current_status in status_map.items():
            event = latest.get((entity_type, entity_id))
            if event is None:
                status_mismatches[entity_type].append(f"{entity_id} (no lifecycle events)")
            elif event[0] != current_status:
                status_mismatches[entity_type].append(
                    f"{entity_id} (last event {event[0]!r}, current {current_status!r})"
                )

    total_invalid = sum(len(values) for values in invalid_transitions.values())
    samples = "|".join(
        f"{entity_type}:{value}" for entity_type, values in invalid_transitions.items() for value in values
    )[:1800]
    engine.add(
        category="TEMPORAL",
        rule_id="TMP-LIFECYCLE-001",
        description="Lifecycle transitions follow the documented state machines",
        severity="ERROR",
        examined=len(rows),
        failure_count=total_invalid,
        affected_ids=samples,
        pass_message=f"All {len(rows)} lifecycle events form valid transition chains.",
        fail_message=f"{total_invalid} invalid lifecycle transitions detected: {samples}",
    )

    total_status = sum(len(values) for values in status_mismatches.values())
    status_samples = "|".join(
        f"{entity_type}:{value}" for entity_type, values in status_mismatches.items() for value in values
    )[:1800]
    engine.add(
        category="TEMPORAL",
        rule_id="TMP-LIFECYCLE-002",
        description="Current entity status matches the latest lifecycle event",
        severity="ERROR",
        examined=sum(len(status_map) for status_map in status_maps.values()),
        failure_count=total_status,
        affected_ids=status_samples,
        pass_message="All entity current states reconcile with lifecycle history.",
        fail_message=f"{total_status} entities conflict with their lifecycle history: {status_samples}",
    )


def _table_exists(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()
    return bool(row and row[0])


def run_validation(
    conn: duckdb.DuckDBPyConnection, config: RunConfig, strict: bool = False
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    engine = ValidationEngine(conn)
    _pk_checks(engine)
    _required_checks(engine)
    _enum_checks(engine)
    _id_checks(engine)
    _fk_checks(engine)
    _duplicate_business_key_check(engine)
    _temporal_checks(engine)
    _financial_checks(engine)
    _identity_checks(engine)
    _lifecycle_checks(engine)

    attribution_available = _table_exists(conn, "attribution_results")
    if attribution_available:
        _attribution_checks(engine)

    failures = sum(1 for check in engine.checks if check["status"] == "FAIL")
    warnings = sum(1 for check in engine.checks if check["status"] == "WARNING")
    passed = sum(1 for check in engine.checks if check["status"] == "PASS")
    failed_empty = failures > 0 or (strict and warnings > 0)
    overall = "FAILED" if failed_empty else ("PASS_WITH_WARNINGS" if warnings else "PASS")

    categories: dict[str, dict[str, int]] = {}
    for check in engine.checks:
        bucket = categories.setdefault(
            check["category"], {"checks": 0, "passed": 0, "warnings": 0, "failures": 0}
        )
        bucket["checks"] += 1
        if check["status"] == "PASS":
            bucket["passed"] += 1
        elif check["status"] == "WARNING":
            bucket["warnings"] += 1
        else:
            bucket["failures"] += 1

    summary = {
        "overall_status": overall,
        "mode": "strict" if strict else "evaluation",
        "run_id": config.run_id,
        "profile": config.profile,
        "seed": config.seed,
        "generated_at": iso(datetime.now(UTC)),
        "rule_version": VALIDATION_RULE_VERSION,
        "attribution_checks_included": attribution_available,
        "totals": {
            "checks": len(engine.checks),
            "passed": passed,
            "warnings": warnings,
            "failures": failures,
        },
        "categories": categories,
        "warning_details": [
            {
                "rule_id": check["rule_id"],
                "message": check["message"],
                "failure_count": check["failure_count"],
            }
            for check in engine.checks
            if check["status"] in ("WARNING", "FAIL")
        ],
    }
    return engine.checks, summary


def validation_report_json(summary: dict[str, Any], checks: Iterable[dict[str, Any]]) -> str:
    return json_dumps({"summary": summary, "checks": list(checks)})

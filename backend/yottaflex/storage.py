"""Analytical storage: deterministic CSV files plus a DuckDB database.

CSV is the portable, human-readable export. DuckDB is a disposable analytical
index rebuilt from the CSV files; it is never the only copy of business data.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from yottaflex.tables import ALL_TABLES, CORE_TABLES, TableSpec
from yottaflex.util import write_csv, write_json


def _sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def connect(db_path: Path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=read_only)


def load_csv_table(conn: duckdb.DuckDBPyConnection, table: str, path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(f"Missing data file for table '{table}': {path}")
    path_sql = _sql_path(path)
    conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.execute(
        f"""
        CREATE TABLE "{table}" AS
        SELECT * FROM read_csv(
            '{path_sql}',
            header = true,
            all_varchar = true,
            delim = ',',
            quote = '"',
            escape = '"',
            nullstr = ''
        )
        """
    )
    count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    return int(count)


def build_database(db_path: Path, run_dir: Path, tables: Iterable[str] | None = None) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", ".wal"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    conn = connect(db_path)
    for name in tables if tables is not None else CORE_TABLES.keys():
        load_csv_table(conn, name, run_dir / f"{name}.csv")
    create_typed_views(conn)
    return conn


def refresh_table(conn: duckdb.DuckDBPyConnection, run_dir: Path, table: str) -> int:
    return load_csv_table(conn, table, run_dir / f"{table}.csv")


def table_exists(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()
    return bool(row and row[0])


def _ts(column: str) -> str:
    return f"CAST(strptime(replace({column}, 'Z', ''), '%Y-%m-%dT%H:%M:%S') AS TIMESTAMP)"


def _date(column: str) -> str:
    return f"CAST({column} AS DATE)"


def create_typed_views(conn: duckdb.DuckDBPyConnection) -> None:
    """Typed views keep cast logic in one place for SQL analytics and the API."""

    conn.execute(
        """
        CREATE OR REPLACE VIEW v_channels AS
        SELECT channel_id, name, category, channel_type,
               (is_paid = 'true') AS is_paid_bool
        FROM channels
        """
    )
    conn.execute(
        """
        CREATE OR REPLACE VIEW v_audiences AS
        SELECT audience_id, name, category, definition,
               CAST(effective_from AS DATE) AS effective_from,
               CAST(effective_to AS DATE) AS effective_to, status
        FROM audiences
        """
    )
    conn.execute(
        """
        CREATE OR REPLACE VIEW v_creatives AS
        SELECT creative_id, campaign_id, channel_id, name, creative_type,
               {start} AS start_at, {end} AS end_at, status, {created} AS created_at
        FROM creatives
        """.format(start=_ts("start_at"), end=_ts("end_at"), created=_ts("created_at"))
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_campaigns AS
        SELECT campaign_id, name, campaign_type, objective,
               {_ts("start_at")} AS start_ts, {_ts("end_at")} AS end_ts,
               status, CAST(budget_amount AS DECIMAL(18,2)) AS budget_dec,
               budget_currency, primary_channel_id, target_audience_id,
               {_ts("created_at")} AS created_ts, {_ts("updated_at")} AS updated_ts
        FROM campaigns
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_contacts AS
        SELECT contact_id, {_ts("created_at")} AS created_ts, region, country, segment,
               consent_status, lifecycle_status, acquisition_channel_id
        FROM contacts
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_sessions AS
        SELECT session_id, anonymous_id, {_ts("started_at")} AS started_ts,
               {_ts("ended_at")} AS ended_ts, source, medium, landing_page,
               campaign_id, device_type
        FROM sessions
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_identity_links AS
        SELECT link_id, session_id, contact_id, evidence_type, evidence_ref,
               {_ts("linked_at")} AS linked_ts, status, rule_id
        FROM identity_links
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_touchpoints AS
        SELECT touchpoint_id, contact_id, session_id, campaign_id, channel_id, creative_id,
               {_ts("occurred_at")} AS occurred_ts, touch_type, source_system,
               identity_status, consent_status, (is_offline = 'true') AS is_offline_bool,
               {_ts("created_at")} AS created_ts
        FROM touchpoints
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_leads AS
        SELECT lead_id, contact_id, {_ts("created_at")} AS created_ts, source, status,
               {_ts("qualified_at")} AS qualified_ts, source_session_id
        FROM leads
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_opportunities AS
        SELECT opportunity_id, lead_id, contact_id, {_ts("created_at")} AS created_ts,
               stage, CAST(expected_value AS DECIMAL(18,2)) AS expected_value_dec,
               currency, {_ts("closed_at")} AS closed_ts, outcome, owner_team
        FROM opportunities
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_orders AS
        SELECT order_id, opportunity_id, contact_id, {_ts("ordered_at")} AS ordered_ts,
               status, CAST(amount AS DECIMAL(18,2)) AS amount_dec,
               CAST(refunded_amount AS DECIMAL(18,2)) AS refunded_dec,
               currency, source_system_ref, {_ts("ingested_at")} AS ingested_ts,
               CASE WHEN status = 'PAID' THEN CAST(amount AS DECIMAL(18,2))
                    WHEN status = 'PARTIALLY_REFUNDED'
                         THEN CAST(amount AS DECIMAL(18,2)) - CAST(refunded_amount AS DECIMAL(18,2))
                    ELSE CAST(0 AS DECIMAL(18,2)) END AS recognized_revenue_dec
        FROM orders
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_costs AS
        SELECT cost_id, campaign_id, channel_id, creative_id, {_date("cost_date")} AS cost_date_d,
               CAST(amount AS DECIMAL(18,2)) AS amount_dec, currency, cost_category,
               source_ref, period
        FROM cost_records
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW v_lifecycle_events AS
        SELECT event_id, entity_type, entity_id, previous_state, new_state,
               {_ts("occurred_at")} AS occurred_ts, reason, source
        FROM lifecycle_events
        """
    )
    if table_exists(conn, "attribution_results"):
        conn.execute(
            f"""
            CREATE OR REPLACE VIEW v_attribution_results AS
            SELECT attribution_result_id, order_id, opportunity_id, contact_id, model,
                   touchpoint_id, campaign_id, channel_id,
                   CAST(credit_fraction AS DECIMAL(12,6)) AS credit_fraction_dec,
                   CAST(attributed_revenue AS DECIMAL(18,2)) AS attributed_revenue_dec,
                   currency, attribution_run_id, rule_version, {_ts("computed_at")} AS computed_ts
            FROM attribution_results
            """
        )
    if table_exists(conn, "attribution_conversions"):
        conn.execute(
            f"""
            CREATE OR REPLACE VIEW v_attribution_conversions AS
            SELECT conversion_result_id, order_id, opportunity_id, contact_id, model, status,
                   CAST(conversion_revenue AS DECIMAL(18,2)) AS conversion_revenue_dec,
                   CAST(eligible_touchpoints AS INTEGER) AS eligible_touchpoints_int,
                   CAST(excluded_post_conversion AS INTEGER) AS excluded_post_conversion_int,
                   CAST(excluded_outside_window AS INTEGER) AS excluded_outside_window_int,
                   CAST(excluded_identity_unresolved AS INTEGER) AS excluded_identity_unresolved_int,
                   CAST(excluded_consent AS INTEGER) AS excluded_consent_int,
                   CAST(excluded_no_campaign AS INTEGER) AS excluded_no_campaign_int,
                   CAST(attributed_touchpoints AS INTEGER) AS attributed_touchpoints_int,
                   CAST(attributed_revenue AS DECIMAL(18,2)) AS attributed_revenue_dec,
                   exclusion_reason, attribution_run_id, rule_version, {_ts("computed_at")} AS computed_ts
            FROM attribution_conversions
            """
        )
    if table_exists(conn, "campaign_performance"):
        conn.execute(
            f"""
            CREATE OR REPLACE VIEW v_campaign_performance AS
            SELECT campaign_id, campaign_name, campaign_type, objective, primary_channel_id,
                   primary_channel_name, {_ts("start_at")} AS start_at, {_ts("end_at")} AS end_at,
                   status, CAST(budget_amount AS DECIMAL(18,2)) AS budget_amount, budget_currency,
                   model, CAST(spend AS DECIMAL(18,2)) AS spend, spend_currency, cost_coverage,
                   CAST(attributed_revenue AS DECIMAL(18,2)) AS attributed_revenue,
                   CAST(conversions AS INTEGER) AS conversions,
                   CAST(unique_converting_contacts AS INTEGER) AS unique_converting_contacts,
                   CAST(touchpoints_credited AS INTEGER) AS touchpoints_credited,
                   CAST(roi_pct AS DECIMAL(18,2)) AS roi_pct,
                   CAST(roas AS DECIMAL(18,2)) AS roas,
                   (roi_available = 'true') AS roi_available, roi_status,
                   CAST(budget_utilization AS DECIMAL(18,2)) AS budget_utilization,
                   CAST(cost_per_conversion AS DECIMAL(18,2)) AS cost_per_conversion,
                   CAST(average_order_value AS DECIMAL(18,2)) AS average_order_value,
                   CAST(issue_count AS INTEGER) AS issue_count
            FROM campaign_performance
            """
        )
    if table_exists(conn, "channel_performance"):
        conn.execute(
            """
            CREATE OR REPLACE VIEW v_channel_performance AS
            SELECT channel_id, channel_name, category, model,
                   CAST(spend AS DECIMAL(18,2)) AS spend, spend_currency, cost_coverage,
                   CAST(attributed_revenue AS DECIMAL(18,2)) AS attributed_revenue,
                   CAST(conversions AS INTEGER) AS conversions,
                   CAST(unique_converting_contacts AS INTEGER) AS unique_converting_contacts,
                   CAST(touchpoints_credited AS INTEGER) AS touchpoints_credited,
                   CAST(roi_pct AS DECIMAL(18,2)) AS roi_pct,
                   CAST(roas AS DECIMAL(18,2)) AS roas,
                   (roi_available = 'true') AS roi_available, roi_status
            FROM channel_performance
            """
        )
    if table_exists(conn, "exceptions"):
        conn.execute(
            f"""
            CREATE OR REPLACE VIEW v_exceptions AS
            SELECT issue_id, issue_type, severity, entity_type, affected_record_ids,
                   primary_entity_id, detection_rule_id, {_ts("detected_at")} AS detected_ts,
                   explanation, evidence, suggested_disposition, status, split
            FROM exceptions
            """
        )
    if table_exists(conn, "financial_reconciliation"):
        conn.execute(
            """
            CREATE OR REPLACE VIEW v_financial_reconciliation AS
            SELECT scope, model, currency,
                   CAST(eligible_conversion_revenue AS DECIMAL(18,2)) AS eligible_conversion_revenue,
                   CAST(attributed_revenue AS DECIMAL(18,2)) AS attributed_revenue,
                   CAST(unattributed_revenue AS DECIMAL(18,2)) AS unattributed_revenue,
                   CAST(recorded_spend AS DECIMAL(18,2)) AS recorded_spend,
                   CAST(covered_spend AS DECIMAL(18,2)) AS covered_spend,
                   CAST(covered_attributed_revenue AS DECIMAL(18,2)) AS covered_attributed_revenue,
                   CAST(roi_pct AS DECIMAL(18,2)) AS roi_pct,
                   CAST(roas AS DECIMAL(18,2)) AS roas,
                   status, detail
            FROM financial_reconciliation
            """
        )
    if table_exists(conn, "validation_results"):
        conn.execute(
            """
            CREATE OR REPLACE VIEW v_validation_results AS
            SELECT check_id, category, rule_id, description, status, severity,
                   CAST(records_examined AS BIGINT) AS records_examined_int,
                   CAST(failure_count AS BIGINT) AS failure_count_int,
                   affected_record_ids, message
            FROM validation_results
            """
        )


def dataframe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    cleaned = frame.astype(object).where(pd.notnull(frame), None)
    return cleaned.to_dict(orient="records")


def write_query_csv(
    conn: duckdb.DuckDBPyConnection, query: str, path: Path, spec: TableSpec
) -> int:
    frame = conn.execute(query).fetchdf()
    records = dataframe_records(frame[list(spec.columns)])
    return write_csv(path, spec.columns, records, sort_key=spec.sort_key)


def write_table(
    path: Path, spec: TableSpec, rows: Sequence[dict[str, Any]] | pd.DataFrame
) -> int:
    records = dataframe_records(rows[list(spec.columns)]) if isinstance(rows, pd.DataFrame) else rows
    return write_csv(path, spec.columns, records, sort_key=spec.sort_key)


def write_reference_json(run_dir: Path, name: str, value: Any) -> Path:
    path = run_dir / name
    write_json(path, value)
    return path


def all_table_specs() -> dict[str, TableSpec]:
    return ALL_TABLES

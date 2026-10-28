from __future__ import annotations

import csv
import json
from collections import Counter

import duckdb
import pytest
from yottaflex.config import MODELS


@pytest.fixture(scope="module")
def conn(bundle: dict):
    connection = duckdb.connect(str(bundle["run_dir"] / "analytics.duckdb"), read_only=True)
    yield connection
    connection.close()


def scalar(conn: duckdb.DuckDBPyConnection, sql: str, params: list | None = None):
    return conn.execute(sql, params or []).fetchone()[0]


def test_generated_profile_sizes(bundle: dict) -> None:
    manifest = bundle["manifest"]
    counts = manifest["counts"]
    assert manifest["profile"] == "small"
    assert manifest["seed"] == 20261022
    assert counts["campaigns"] == 30
    assert counts["contacts"] == 500
    assert counts["touchpoints"] == 2000
    assert counts["opportunities"] == 200
    assert counts["orders"] >= 100
    assert counts["attribution_conversions"] == manifest["attribution"]["conversions"] * 3


def test_reference_tables_and_fixture_counts(conn: duckdb.DuckDBPyConnection) -> None:
    assert scalar(conn, "SELECT COUNT(*) FROM v_channels") == 8
    assert scalar(conn, "SELECT COUNT(*) FROM v_audiences") == 12
    assert scalar(conn, "SELECT COUNT(*) FROM v_campaigns") == 30
    assert scalar(conn, "SELECT COUNT(*) FROM v_contacts") == 500
    assert scalar(conn, "SELECT COUNT(*) FROM v_touchpoints") == 2000


def test_ground_truth_is_separate_and_never_in_run_directory(bundle: dict) -> None:
    run_dir = bundle["run_dir"]
    labels = bundle["ground_truth_dir"] / "labels.csv"
    assert labels.exists()
    assert not (run_dir / "labels.csv").exists()
    assert not (run_dir / "ground_truth.csv").exists()
    rows = list(csv.DictReader(labels.open(encoding="utf-8")))
    assert len(rows) == 10
    counts = Counter(row["issue_type"] for row in rows)
    assert counts == {
        "DUPLICATE_REVENUE": 2,
        "POST_CONVERSION_TOUCH": 2,
        "CURRENCY_MISMATCH": 2,
        "MISSING_CAMPAIGN_COST": 2,
        "UNSUPPORTED_IDENTITY_LINK": 2,
    }
    assert all(row["scenario_id"].startswith("GT-") for row in rows)
    assert all(row["record_ids"] for row in rows)


def test_attribution_has_three_models_and_reconciles(
    conn: duckdb.DuckDBPyConnection, bundle: dict
) -> None:
    models = {row[0] for row in conn.execute("SELECT DISTINCT model FROM v_attribution_results").fetchall()}
    assert models == set(MODELS)
    eligible = bundle["manifest"]["attribution"]["conversions"]
    assert scalar(conn, "SELECT COUNT(*) FROM v_attribution_conversions") == eligible * 3
    mismatch = scalar(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT r.order_id, r.model,
                   SUM(r.attributed_revenue_dec) AS credited,
                   ANY_VALUE(c.conversion_revenue_dec) AS revenue
            FROM v_attribution_results r
            JOIN v_attribution_conversions c
              ON c.order_id = r.order_id AND c.model = r.model
            GROUP BY r.order_id, r.model
            HAVING credited <> revenue
        )
        """,
    )
    assert mismatch == 0
    outcomes = conn.execute(
        "SELECT status, COUNT(*) FROM v_attribution_conversions GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert dict(outcomes)["ATTRIBUTED"] > 0
    assert dict(outcomes)["UNATTRIBUTED"] > 0


def test_no_post_conversion_or_consent_violating_credit(conn: duckdb.DuckDBPyConnection) -> None:
    post_conversion = scalar(
        conn,
        """
        SELECT COUNT(*) FROM v_attribution_results r
        JOIN v_touchpoints t ON t.touchpoint_id = r.touchpoint_id
        JOIN v_orders o ON o.order_id = r.order_id
        WHERE t.occurred_ts > o.ordered_ts
        """,
    )
    assert post_conversion == 0
    consent_violations = scalar(
        conn,
        """
        SELECT COUNT(*) FROM v_attribution_results r
        JOIN v_touchpoints t ON t.touchpoint_id = r.touchpoint_id
        JOIN v_contacts c ON c.contact_id = r.contact_id
        WHERE t.consent_status <> 'GRANTED' OR c.consent_status <> 'GRANTED'
        """,
    )
    assert consent_violations == 0
    assert scalar(conn, "SELECT COUNT(*) FROM v_attribution_results") > 0


def test_unsupported_identity_link_is_not_used(conn: duckdb.DuckDBPyConnection) -> None:
    used = scalar(
        conn,
        """
        SELECT COUNT(DISTINCT r.touchpoint_id)
        FROM v_attribution_results r
        JOIN v_touchpoints t ON t.touchpoint_id = r.touchpoint_id
        JOIN v_identity_links l ON l.session_id = t.session_id
        WHERE t.contact_id IS NULL
          AND l.status = 'VERIFIED'
          AND (l.evidence_type NOT IN (
                'AUTHENTICATED_LOGIN', 'EMAIL_CLICK_SSO', 'FORM_SUBMIT_MATCH', 'CRM_IMPORT_MATCH'
              ) OR trim(l.evidence_ref) = '')
        """,
    )
    assert used == 0


def test_detection_finds_each_fixture_type(bundle: dict) -> None:
    counts = bundle["manifest"]["detection"]["by_type"]
    assert counts == {
        "DUPLICATE_REVENUE": 2,
        "POST_CONVERSION_TOUCH": 2,
        "CURRENCY_MISMATCH": 2,
        "MISSING_CAMPAIGN_COST": 2,
        "UNSUPPORTED_IDENTITY_LINK": 2,
    }
    issues = list(csv.DictReader((bundle["run_dir"] / "exceptions.csv").open(encoding="utf-8")))
    assert len(issues) == 10
    for issue in issues:
        evidence = json.loads(issue["evidence"])
        assert isinstance(evidence, dict) and evidence
        assert issue["issue_id"].startswith("ISS-2026-")
        assert issue["severity"] in {"HIGH", "MEDIUM", "LOW"}


def test_evaluation_is_perfect_on_small_fixture_set(bundle: dict) -> None:
    evaluation = json.loads((bundle["run_dir"] / "evaluation.json").read_text(encoding="utf-8"))
    totals = evaluation["totals"]
    assert totals["ground_truth"] == 10
    assert totals["true_positives"] == 10
    assert totals["false_positives"] == 0
    assert totals["false_negatives"] == 0
    assert totals["precision_pct"] == "100.00"
    assert totals["recall_pct"] == "100.00"
    assert evaluation["status"] == "COMPLETE"


def test_validation_passes_with_expected_fixture_warnings(bundle: dict) -> None:
    report = json.loads((bundle["run_dir"] / "validation_report.json").read_text(encoding="utf-8"))
    summary = report["summary"]
    assert summary["overall_status"] == "PASS_WITH_WARNINGS"
    assert summary["totals"]["failures"] == 0
    assert summary["totals"]["warnings"] == 6
    assert summary["attribution_checks_included"] is True
    check_ids = {check["check_id"] for check in report["checks"]}
    assert "CHK-0108" in check_ids or any(
        check["rule_id"] == "IDN-EVIDENCE-001" for check in report["checks"]
    )


def test_financial_rules_hide_roi_without_complete_costs(conn: duckdb.DuckDBPyConnection) -> None:
    invalid = scalar(
        conn,
        """
        SELECT COUNT(*) FROM v_campaign_performance
        WHERE cost_coverage <> 'COMPLETE' AND roi_available = true
        """,
    )
    assert invalid == 0
    missing = scalar(
        conn,
        "SELECT COUNT(*) FROM v_campaign_performance WHERE cost_coverage = 'MISSING' AND model = 'linear'",
    )
    assert missing == 2
    incomplete = conn.execute(
        "SELECT scope, status, roi_pct FROM v_financial_reconciliation"
        " WHERE model = 'linear' ORDER BY scope"
    ).fetchall()
    assert len(incomplete) == 2
    statuses = {row[0]: row[1] for row in incomplete}
    assert statuses["overall"] == "COVERAGE_INCOMPLETE"


def test_summary_contains_required_analytics(bundle: dict) -> None:
    summary = json.loads((bundle["run_dir"] / "summary.json").read_text(encoding="utf-8"))
    kpis = summary["kpis"]
    assert kpis["campaigns"] == 30
    assert kpis["contacts"] == 500
    assert float(kpis["attributed_revenue"]) >= 0
    assert float(kpis["eligible_conversion_revenue"]) >= float(kpis["attributed_revenue"])
    assert len(summary["monthly"]) == 13
    assert len(summary["channel_contribution"]) == 8
    assert len(summary["model_comparison"]) == 3
    assert summary["data_quality_status"] == "ATTENTION_REQUIRED"
    assert summary["kpis"]["data_quality_issues"] == 10

from __future__ import annotations

import csv
import io
import time
from decimal import Decimal

import duckdb


def test_health_and_summary(client, bundle: dict) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["dataset"]["run_id"] == bundle["config"].run_id
    summary = client.get("/api/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["kpis"]["campaigns"] == 30
    assert body["kpis"]["data_quality_issues"] == 10
    assert body["validation"]["overall_status"] == "PASS_WITH_WARNINGS"
    assert body["evaluation"]["totals"]["precision_pct"] == "100.00"
    assert len(body["monthly"]) == 13


def test_summary_separates_revenue_and_conversion_coverage(client) -> None:
    body = client.get("/api/summary").json()
    kpis = body["kpis"]
    assert "attribution_coverage_pct" not in kpis
    assert kpis["revenue_coverage_pct"] != kpis["conversion_coverage_pct"]
    expected_revenue = (
        Decimal(kpis["attributed_revenue"])
        * Decimal("100")
        / Decimal(kpis["eligible_conversion_revenue"])
    )
    expected_conversions = (
        Decimal(kpis["attributed_conversions"])
        * Decimal("100")
        / Decimal(kpis["eligible_conversions"])
    )
    assert Decimal(kpis["revenue_coverage_pct"]) == expected_revenue.quantize(Decimal("0.01"))
    assert Decimal(kpis["conversion_coverage_pct"]) == expected_conversions.quantize(Decimal("0.01"))


def test_summary_exposes_covered_roas_scope(client) -> None:
    body = client.get("/api/summary").json()
    financials = body["financials"]
    assert financials["covered_roas_numerator"] == financials["covered_attributed_revenue"]
    assert financials["covered_roas_denominator"] == financials["covered_spend"]
    assert financials["covered_campaigns"] <= financials["budgeted_campaigns"]
    assert Decimal(financials["covered_roas"]) == (
        Decimal(financials["covered_roas_numerator"])
        / Decimal(financials["covered_roas_denominator"])
    ).quantize(Decimal("0.01"))


def test_run_registry(client, bundle: dict) -> None:
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert response.json()["active_run_id"] == bundle["config"].run_id
    run = next(
        item for item in response.json()["runs"] if item["run_id"] == bundle["config"].run_id
    )
    assert {"campaigns", "contacts", "touchpoints", "opportunities"} <= set(run["counts"])
    assert run["campaigns"] == run["counts"]["campaigns"] == 30
    assert run["contacts"] == run["counts"]["contacts"] == 500
    assert run["touchpoints"] == run["counts"]["touchpoints"] == 2_000
    assert run["opportunities"] == run["counts"]["opportunities"] == 200
    manifest = client.get(f"/api/runs/{bundle['config'].run_id}")
    assert manifest.status_code == 200
    assert manifest.json()["combined_hash"]


def test_campaign_list_and_detail(client, bundle: dict) -> None:
    response = client.get("/api/campaigns?limit=5&model=linear")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 30
    assert len(body["items"]) == 5
    item = body["items"][0]
    assert item["model"] == "linear"
    assert isinstance(item["attributed_revenue"], float)
    detail = client.get(f"/api/campaigns/{item['campaign_id']}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["campaign"]["campaign_id"] == item["campaign_id"]
    assert len(payload["model_comparison"]) == 3
    assert payload["run_id"] == bundle["config"].run_id
    assert client.get("/api/campaigns/CMP-2026-999999").status_code == 404


def test_campaign_filters(client) -> None:
    response = client.get("/api/campaigns?channel_id=CHN-000003&limit=100")
    assert response.status_code == 200
    assert all(item["primary_channel_id"] == "CHN-000003" for item in response.json()["items"])
    filtered = client.get("/api/campaigns?coverage=MISSING&limit=100")
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 2
    no_basis = client.get("/api/campaigns?coverage=NO_COST_BASIS&limit=100")
    assert no_basis.status_code == 200
    assert no_basis.json()["total"] == 10
    assert no_basis.json()["aggregates"]["spend_no_cost_basis_campaigns"] == 10
    assert no_basis.json()["aggregates"]["spend_missing_campaigns"] == 0


def test_campaign_view_keeps_unknown_spend_null(client) -> None:
    response = client.get("/api/campaigns?coverage=MISSING&limit=100")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert all(item["spend"] is None for item in body["items"])
    assert body["aggregates"]["spend"] is None
    assert body["aggregates"]["spend_known_campaigns"] == 0
    assert body["aggregates"]["spend_missing_campaigns"] == 2
    assert body["aggregates"]["spend_no_cost_basis_campaigns"] == 0


def test_campaign_spend_sort_places_unknown_last(client) -> None:
    response = client.get("/api/campaigns?sort=spend&order=asc&limit=100")
    assert response.status_code == 200
    spends = [item["spend"] for item in response.json()["items"]]
    known = [spend for spend in spends if spend is not None]
    assert known == sorted(known)
    first_null = next(index for index, spend in enumerate(spends) if spend is None)
    assert all(spend is None for spend in spends[first_null:])


def test_campaign_export_matches_filtered_view(client) -> None:
    query = "model=linear&coverage=MISSING&sort=spend&order=asc"
    table = client.get(f"/api/campaigns?{query}&limit=100").json()
    response = client.get(f"/api/campaigns/export?{query}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    records = list(csv.DictReader(io.StringIO(response.text)))
    assert len(records) == table["total"] == 2
    assert [record["campaign_id"] for record in records] == [
        item["campaign_id"] for item in table["items"]
    ]
    assert all(record["spend"] == "" for record in records)
    assert all(record["cost_coverage"] == "MISSING" for record in records)


def test_export_formats_are_discoverable(client) -> None:
    response = client.get("/api/exports/formats")
    assert response.status_code == 200
    body = response.json()
    assert [item["format"] for item in body["formats"]] == ["csv", "json", "xlsx", "pdf"]
    assert all(item["description"] for item in body["formats"])


def test_campaign_performance_export_formats_carry_the_same_rows(client) -> None:
    query = "model=linear&coverage=MISSING"
    table = client.get(f"/api/campaigns?{query}&limit=100").json()
    expected_ids = [item["campaign_id"] for item in table["items"]]

    csv_response = client.get(f"/api/exports/campaign-performance?format=csv&{query}")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    csv_records = list(csv.DictReader(io.StringIO(csv_response.text)))
    assert [record["campaign_id"] for record in csv_records] == expected_ids

    json_response = client.get(f"/api/exports/campaign-performance?format=json&{query}")
    assert json_response.status_code == 200
    assert json_response.headers["content-type"].startswith("application/json")
    payload = json_response.json()
    assert [row["campaign_id"] for row in payload["rows"]] == expected_ids
    context = payload["context"]
    assert context["model"] == "linear"
    assert context["row_count"] == len(expected_ids)
    assert context["filters"]["coverage"] == "MISSING"
    assert context["run_id"]
    assert context["generated_at"]
    assert payload["rows"][0]["spend"] is None

    xlsx_response = client.get(f"/api/exports/campaign-performance?format=xlsx&{query}")
    assert xlsx_response.status_code == 200
    assert xlsx_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert xlsx_response.content[:2] == b"PK"

    pdf_response = client.get(f"/api/exports/campaign-performance?format=pdf&{query}")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert pdf_response.content[:5] == b"%PDF-"


def test_campaign_performance_export_reconciles_with_model_total(client) -> None:
    response = client.get("/api/exports/campaign-performance?format=json&model=linear")
    assert response.status_code == 200
    payload = response.json()
    rows = payload["rows"]
    attributed = sum(row["attributed_revenue"] for row in rows if row["attributed_revenue"] is not None)
    comparison = client.get("/api/attribution/compare?model_a=linear&model_b=first_touch").json()
    model_total = comparison["totals"]["model_a"]["attributed_revenue"]
    assert abs(attributed - model_total) < 0.01


def test_export_rejects_unknown_format(client) -> None:
    assert client.get("/api/exports/campaign-performance?format=docx").status_code == 422


def test_verify_job_runs_and_leaves_the_active_run_untouched(client, bundle: dict) -> None:
    before = client.get("/api/health").json()["dataset"]
    started = client.post("/api/runs/verify", json={"profile": "small", "seed": 20261022})
    assert started.status_code == 202
    job = started.json()
    assert job["status"] == "RUNNING"
    assert job["note"]

    final = None
    for _ in range(240):
        final = client.get(f"/api/runs/verify/{job['job_id']}").json()
        if final["status"] != "RUNNING":
            break
        time.sleep(0.5)
    assert final is not None
    assert final["status"] == "REPRODUCIBLE", final
    assert final["result"]["reproducible"] is True
    assert final["result"]["differences"] == []
    assert (
        final["result"]["left_combined_hash"] == final["result"]["right_combined_hash"]
    )

    after = client.get("/api/health").json()["dataset"]
    assert after["run_id"] == before["run_id"]
    assert after["generated_at"] == before["generated_at"]
    assert client.get("/api/runs/verify/does-not-exist").status_code == 404


def test_verify_rejects_unknown_profile(client) -> None:
    response = client.post("/api/runs/verify", json={"profile": "gigantic", "seed": 1})
    assert response.status_code == 422


def test_channels_and_model_comparison(client) -> None:
    channels = client.get("/api/channels")
    assert channels.status_code == 200
    assert len(channels.json()["items"]) == 8
    comparison = client.get("/api/attribution/compare?model_a=first_touch&model_b=linear")
    assert comparison.status_code == 200
    payload = comparison.json()
    assert payload["model_a"] == "first_touch"
    assert payload["model_b"] == "linear"
    assert len(payload["channel_changes"]) == 8
    assert len(payload["campaign_changes"]) > 0
    assert client.get("/api/attribution/compare?model_a=first_touch&model_b=first_touch").status_code == 400


def test_exception_list_and_detail(client) -> None:
    response = client.get("/api/exceptions?limit=100")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 10
    assert len(body["items"]) == 10
    assert body["facets"]["issue_type"]
    issue_id = body["items"][0]["issue_id"]
    detail = client.get(f"/api/exceptions/{issue_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["issue_id"] == issue_id
    assert isinstance(payload["evidence"], dict)
    assert payload["suggested_disposition"]
    assert client.get("/api/exceptions/ISS-2026-999999").status_code == 404


def test_every_exception_detail_loads(client) -> None:
    """Regression: every evidence packet must render, not just the first one."""

    items = client.get("/api/exceptions?limit=100").json()["items"]
    assert len(items) == 10
    by_type: dict[str, str] = {}
    for item in items:
        detail = client.get(f"/api/exceptions/{item['issue_id']}")
        assert detail.status_code == 200, f"{item['issue_id']} returned {detail.status_code}"
        payload = detail.json()
        assert payload["issue_id"] == item["issue_id"]
        assert payload["related"]
        by_type.setdefault(item["issue_type"], item["issue_id"])

    assert "MISSING_CAMPAIGN_COST" in by_type
    assert "DUPLICATE_REVENUE" in by_type
    assert "UNSUPPORTED_IDENTITY_LINK" in by_type
    assert "POST_CONVERSION_TOUCH" in by_type
    assert "CURRENCY_MISMATCH" in by_type


def test_campaign_exception_evidence_packet_returns_campaign_context(client) -> None:
    """Regression: campaign-type exceptions previously raised HTTP 500.

    The read model read `campaign_name` from `v_campaigns`, which exposes the
    column as `name`, so every MISSING_CAMPAIGN_COST packet failed.
    """

    items = client.get("/api/exceptions?issue_type=MISSING_CAMPAIGN_COST&limit=100").json()
    assert items["total"] == 2
    for item in items["items"]:
        response = client.get(f"/api/exceptions/{item['issue_id']}")
        assert response.status_code == 200
        payload = response.json()
        campaign = payload["related"]["campaign"]
        assert campaign["campaign_id"] == item["primary_entity_id"]
        assert campaign["campaign_name"]
        assert campaign["budget_currency"] == "EUR"
        assert payload["related"]["records"][0]["type"] == "CAMPAIGN"


def test_duplicate_revenue_packet_explains_canonicalization(client) -> None:
    items = client.get("/api/exceptions?issue_type=DUPLICATE_REVENUE&limit=100").json()
    assert items["total"] == 2
    for item in items["items"]:
        payload = client.get(f"/api/exceptions/{item['issue_id']}").json()
        canonicalization = payload["related"]["canonicalization"]
        assert canonicalization["business_key"] == "source_system_ref"
        assert canonicalization["business_key_value"]
        assert canonicalization["canonical_order_id"]
        assert canonicalization["copy_count"] >= 2
        assert canonicalization["excluded_order_ids"]
        assert canonicalization["excluded_recognized_revenue"] is not None
        assert canonicalization["source_records_preserved"] is True
        assert payload["related"]["disposition_state"]["applied"] is False
        assert payload["related"]["disposition_state"]["label"].startswith("Advisory")


def test_exception_detail_handles_missing_and_malformed_references(
    client, bundle: dict
) -> None:
    conn = duckdb.connect(str(bundle["run_dir"] / "analytics.duckdb"))
    try:
        issue_id, original_evidence, original_ids, original_primary = conn.execute(
            "SELECT issue_id, evidence, affected_record_ids, primary_entity_id "
            "FROM v_exceptions WHERE entity_type = 'campaign' LIMIT 1"
        ).fetchone()
        conn.execute(
            "UPDATE exceptions SET evidence = 'not-json', "
            "affected_record_ids = 'CMP-2026-999999' WHERE issue_id = ?",
            [issue_id],
        )
    finally:
        conn.close()
    try:
        response = client.get(f"/api/exceptions/{issue_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["evidence"] == "not-json"
        assert payload["related"]["records"][0]["type"] == "REFERENCE"
        assert payload["related"]["records"][0]["reason"]
    finally:
        conn = duckdb.connect(str(bundle["run_dir"] / "analytics.duckdb"))
        try:
            conn.execute(
                "UPDATE exceptions SET evidence = ?, affected_record_ids = ? WHERE issue_id = ?",
                [original_evidence, original_ids, issue_id],
            )
        finally:
            conn.close()

    conn = duckdb.connect(str(bundle["run_dir"] / "analytics.duckdb"))
    try:
        conn.execute(
            "UPDATE exceptions SET primary_entity_id = 'CMP-2026-999999' WHERE issue_id = ?",
            [issue_id],
        )
    finally:
        conn.close()
    try:
        response = client.get(f"/api/exceptions/{issue_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["related"]["missing_references"][0]["record_id"] == "CMP-2026-999999"
        assert "campaign" not in payload["related"]
    finally:
        conn = duckdb.connect(str(bundle["run_dir"] / "analytics.duckdb"))
        try:
            conn.execute(
                "UPDATE exceptions SET primary_entity_id = ? WHERE issue_id = ?",
                [original_primary, issue_id],
            )
        finally:
            conn.close()


def test_validation_and_evaluation_endpoints(client) -> None:
    validation = client.get("/api/validation/report")
    assert validation.status_code == 200
    body = validation.json()
    assert body["summary"]["totals"]["failures"] == 0
    assert body["total_checks"] >= 100
    warnings = client.get("/api/validation/report?status=WARNING")
    assert warnings.status_code == 200
    assert all(check["status"] == "WARNING" for check in warnings.json()["checks"])
    evaluation = client.get("/api/evaluation")
    assert evaluation.status_code == 200
    assert evaluation.json()["totals"]["true_positives"] == 10
    assert len(evaluation.json()["matches"]) == 10


def test_journey_explanation(client, bundle: dict) -> None:
    conn = duckdb.connect(str(bundle["run_dir"] / "analytics.duckdb"), read_only=True)
    try:
        opportunity_id = conn.execute(
            "SELECT opportunity_id FROM v_orders WHERE status = 'PAID' ORDER BY order_id LIMIT 1"
        ).fetchone()[0]
        order_id = conn.execute(
            "SELECT order_id FROM v_orders WHERE opportunity_id = ? LIMIT 1", [opportunity_id]
        ).fetchone()[0]
    finally:
        conn.close()
    response = client.get(f"/api/opportunities/{opportunity_id}/journey")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "CONVERTED"
    assert payload["persisted_consistent"] is True
    assert len(payload["models"]) == 3
    check = payload["persisted_check"]
    assert check["consistent"] is True
    assert check["difference_count"] == 0
    assert len(check["models"]) == 3
    assert all(
        model["matched"]
        and model["status_match"]
        and model["revenue_match"]
        and model["difference"] == 0
        for model in check["models"]
    )
    assert payload["touchpoints"]
    assert all("outcome" in touch for touch in payload["touchpoints"])
    by_order = client.get(f"/api/journeys/{order_id}")
    assert by_order.status_code == 200
    assert by_order.json()["conversion"]["order_id"] == order_id
    assert client.get("/api/journeys/UNKNOWN-1").status_code == 404
    sample = client.get("/api/demo/journey")
    assert sample.status_code == 200
    assert sample.json()["status"] == "CONVERTED"
    assert sample.json()["reference"].startswith("ORD-")
    assert any(not touch["eligible"] for touch in sample.json()["touchpoints"])


def test_journey_reports_exclusion_counts_and_allocation_checks(client) -> None:
    response = client.get("/api/demo/journey")
    assert response.status_code == 200
    payload = response.json()

    counts = payload["counts"]
    exclusions = payload["exclusions"]
    assert counts["total_touches"] == len(payload["touchpoints"])
    assert counts["eligible_touches"] + counts["excluded_touches"] == counts["total_touches"]
    assert counts["excluded_touches"] == sum(exclusions.values())
    assert counts["exclusion_semantics"]

    check = payload["persisted_check"]
    assert check["allocations_consistent"] is True
    assert check["tolerance"] == 0.005
    assert check["comparison_basis"]
    assert len(check["allocations"]) == 3
    for allocation in check["allocations"]:
        assert allocation["matched"] is True
        assert allocation["difference_count"] == 0
        assert allocation["compared_touchpoints"] > 0
        assert allocation["tolerance"] == {
            "attributed_revenue": 0.005,
            "credit_fraction": 1e-06,
        }
        assert allocation["comparison"] == "full_precision_absolute_difference"
    assert check["population"]["order_id"] == payload["conversion"]["order_id"]


def test_journey_touchpoints_are_chronological(client) -> None:
    payload = client.get("/api/demo/journey").json()
    ordered_at = payload["conversion"]["ordered_at"]
    occurred = [touch["occurred_at"] for touch in payload["touchpoints"]]
    assert occurred == sorted(occurred)
    after = [touch for touch in payload["touchpoints"] if touch["occurred_at"] > ordered_at]
    assert all(touch["outcome"] == "POST_CONVERSION" for touch in after)


def test_export_whitelist(client) -> None:
    response = client.get("/api/exports/campaigns")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert client.get("/api/exports/not_a_table").status_code == 404


def test_validation_action(client, bundle: dict) -> None:
    response = client.post("/api/runs/validate", json={"run_id": bundle["config"].run_id})
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["totals"]["failures"] == 0
    assert body["summary"]["overall_status"] in {"PASS", "PASS_WITH_WARNINGS"}


def test_unknown_run_returns_404(client) -> None:
    assert client.get("/api/summary?run_id=missing-123").status_code == 404

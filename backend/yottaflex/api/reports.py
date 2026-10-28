"""Report assembly for every export entry point in the console.

`exports.py` owns serialization; this module owns *what* each report contains.
Every function returns a `Report` built from the same service layer the API
and UI read, so a download cannot drift from what is on screen.

Sensitivity rules enforced here:

* detection and analytical exports never contain ground-truth labels;
* the evaluation artifact is the only export with label rows and is explicitly
  flagged in its context, summary and PDF banner;
* the run bundle omits ground-truth metadata and evaluation match rows.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from yottaflex.api import services
from yottaflex.api.deps import RunContext, connect, read_json_file
from yottaflex.api.exports import (
    PdfColumn,
    PdfSpec,
    Sheet,
    build_context,
    number,
)
from yottaflex.config import MODELS
from yottaflex.util import read_json


@dataclass(frozen=True)
class Report:
    context: dict[str, Any]
    sheets: list[Sheet]
    summary_rows: list[tuple[str, Any]]
    pdf_spec: PdfSpec
    json_primary: dict[str, Any] | None = None


COST_EXPORT_FORMATS = ("csv", "json", "xlsx", "pdf")


def _kv_sheet(name: str, pairs: list[tuple[str, Any]]) -> Sheet:
    return Sheet(
        name=name,
        columns=["field", "value"],
        records=[{"field": key, "value": value} for key, value in pairs],
    )


def _run_context(
    run: RunContext,
    *,
    report: str,
    stem: str,
    model: str | None,
    filters: dict[str, Any],
    row_count: int,
    scope: str,
    artifact_type: str = "analytical_export",
    contains_ground_truth: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = run.manifest
    return build_context(
        run_id=run.run_id,
        profile=manifest.get("profile"),
        seed=manifest.get("seed"),
        model=model,
        filters=filters,
        row_count=row_count,
        scope=scope,
        generated_at=manifest.get("generated_at"),
        report=report,
        stem=stem,
        currency=manifest.get("config", {}).get("reporting_currency", "EUR"),
        artifact_type=artifact_type,
        contains_ground_truth=contains_ground_truth,
        extra=extra,
    )


def overview_report(run: RunContext) -> Report:
    data = services.summary(run)
    kpis = data["kpis"]
    financials = data["financials"]
    model_a, model_b = "first_touch", "linear"
    conn = connect(run)
    try:
        comparison = services.compare_models(conn, model_a, model_b, 100)
    finally:
        conn.close()
    channel_rows = [
        {
            "channel_id": row["channel_id"],
            "channel_name": row["channel_name"],
            "model_a_revenue": row["revenue_a"],
            "model_b_revenue": row["revenue_b"],
            "delta": row["delta"],
            "model_a_share_pct": row["share_a_pct"],
            "model_b_share_pct": row["share_b_pct"],
            "share_delta_pct": row["share_delta_pct"],
        }
        for row in comparison["channel_changes"]
    ]
    model_rows = [
        {
            "model": name,
            "attributed_revenue": values["attributed_revenue"],
            "eligible_revenue": values["eligible_revenue"],
            "attributed_conversions": values["attributed_conversions"],
            "unattributed_conversions": values["unattributed_conversions"],
        }
        for name, values in data["attribution_by_model"].items()
    ]
    monthly_rows = [
        {
            "month": row["month"],
            "attributed_revenue": row["attributed_revenue"],
            "eligible_revenue": row["eligible_revenue"],
            "spend": row["spend"],
            "attributed_conversions": row["attributed_conversions"],
        }
        for row in data["monthly"]
    ]
    channel_contribution = [
        {
            "channel_id": row["channel_id"],
            "channel_name": row["channel_name"],
            "category": row["category"],
            "attributed_revenue": row["attributed_revenue"],
            "spend": row["spend"],
            "conversions": row["conversions"],
            "roi_pct": row["roi_pct"],
            "roi_available": row["roi_available"],
        }
        for row in data["channel_contribution"]
    ]
    anomaly_rows = [
        {
            "issue_type": row["issue_type"],
            "severity": row["severity"],
            "count": row["count"],
        }
        for row in data["anomaly_distribution"]
    ]
    summary_rows = [
        ("Attributed revenue (EUR)", kpis["attributed_revenue"]),
        ("Eligible conversion revenue (EUR)", kpis["eligible_conversion_revenue"]),
        ("Unattributed revenue (EUR)", kpis["unattributed_revenue"]),
        ("Revenue coverage", f"{kpis['revenue_coverage_pct']}%"),
        ("Attributed conversions", kpis["attributed_conversions"]),
        ("Eligible conversions", kpis["eligible_conversions"]),
        ("Conversion coverage", f"{kpis['conversion_coverage_pct']}%"),
        ("Recorded spend (EUR)", kpis["recorded_spend"]),
        ("Covered spend (EUR)", financials["covered_spend"]),
        ("Covered ROAS", f"{financials['covered_roas']} (numerator / denominator shown in context)"),
        ("Covered ROI", f"{financials['covered_roi_pct']}%"),
        ("ROI scope", kpis["roi_scope"]),
        ("Cost coverage", financials["coverage_detail"]),
        ("Data-quality status", data["data_quality_status"]),
        ("Open issues", f"{kpis['data_quality_issues']} ({kpis['high_severity_issues']} high)"),
        ("Model comparison", f"{model_a} vs {model_b}; share basis in context"),
        ("Interpretation", data["notice"]),
    ]
    sheets = [
        Sheet(
            name="Monthly",
            columns=["month", "attributed_revenue", "eligible_revenue", "spend", "attributed_conversions"],
            records=monthly_rows,
            numeric=frozenset({"attributed_revenue", "eligible_revenue", "spend", "attributed_conversions"}),
        ),
        Sheet(
            name="Channel contribution",
            columns=[
                "channel_id",
                "channel_name",
                "category",
                "attributed_revenue",
                "spend",
                "conversions",
                "roi_pct",
                "roi_available",
            ],
            records=channel_contribution,
            numeric=frozenset({"attributed_revenue", "spend", "conversions", "roi_pct"}),
        ),
        Sheet(
            name="Model comparison",
            columns=[
                "model",
                "attributed_revenue",
                "eligible_revenue",
                "attributed_conversions",
                "unattributed_conversions",
            ],
            records=model_rows,
            numeric=frozenset(
                {"attributed_revenue", "eligible_revenue", "attributed_conversions", "unattributed_conversions"}
            ),
        ),
        Sheet(
            name=f"Credit movement {model_a} to {model_b}",
            columns=[
                "channel_id",
                "channel_name",
                "model_a_revenue",
                "model_b_revenue",
                "delta",
                "model_a_share_pct",
                "model_b_share_pct",
                "share_delta_pct",
            ],
            records=channel_rows,
            numeric=frozenset(
                {
                    "model_a_revenue",
                    "model_b_revenue",
                    "delta",
                    "model_a_share_pct",
                    "model_b_share_pct",
                    "share_delta_pct",
                }
            ),
        ),
        Sheet(
            name="Top campaigns",
            columns=[
                "campaign_id",
                "campaign_name",
                "channel_name",
                "cost_coverage",
                "spend",
                "attributed_revenue",
                "roi_pct",
                "roi_available",
            ],
            records=data["top_campaigns"],
            numeric=frozenset({"spend", "attributed_revenue", "roi_pct"}),
        ),
        Sheet(
            name="Anomaly mix",
            columns=["issue_type", "severity", "count"],
            records=anomaly_rows,
            numeric=frozenset({"count"}),
        ),
    ]
    context = _run_context(
        run,
        report="Executive overview",
        stem=f"executive-overview-{run.run_id}",
        model="linear (headline) + all models",
        filters={},
        row_count=len(monthly_rows),
        scope="Monthly attribution, eligible revenue and recorded spend for the full dataset.",
        extra={
            "model_a": model_a,
            "model_b": model_b,
            "share_basis": comparison["share_basis"],
            "financial_contract": {
                "roi_scope": kpis["roi_scope"],
                "covered_roas_numerator": financials["covered_roas_numerator"],
                "covered_roas_denominator": financials["covered_roas_denominator"],
                "coverage_detail": financials["coverage_detail"],
            },
        },
    )
    pdf_spec = PdfSpec(
        columns=[
            PdfColumn("month", "Month", 12),
            PdfColumn("attributed_revenue", "Attributed", 20, "R", "money"),
            PdfColumn("eligible_revenue", "Eligible", 20, "R", "money"),
            PdfColumn("spend", "Recorded spend", 22, "R", "money"),
            PdfColumn("attributed_conversions", "Conv.", 12, "R", "number"),
        ],
        table_heading="Monthly performance",
    )
    return Report(context=context, sheets=sheets, summary_rows=summary_rows, pdf_spec=pdf_spec)


def campaign_report(run: RunContext, campaign_id: str, model: str) -> Report | None:
    conn = connect(run)
    try:
        detail = services.campaign_detail(conn, campaign_id, model)
    finally:
        conn.close()
    if detail is None:
        return None
    campaign = detail["campaign"]
    performance = detail["performance"]
    monthly = detail["monthly"]
    comparison = detail["model_comparison"]
    model_rows = []
    for row in comparison:
        roi = row["roi_pct"] if row.get("roi_available") else "n/a"
        model_rows.append(
            {
                "model": row["model"],
                "attributed_revenue": row["attributed_revenue"],
                "conversions": row["conversions"],
                "unique_converting_contacts": row["unique_converting_contacts"],
                "touchpoints_credited": row["touchpoints_credited"],
                "roi_pct": roi,
                "roi_available": row["roi_available"],
            }
        )
    summary_rows = [
        ("Campaign", campaign["campaign_name"]),
        ("Campaign id", campaign["campaign_id"]),
        ("Model", performance["model"]),
        ("Channel", campaign["primary_channel_id"]),
        ("Status", campaign["status"]),
        ("Active window", f"{campaign['start_at']} to {campaign['end_at']}"),
        (f"Budget ({campaign['budget_currency']})", campaign["budget_amount"]),
        ("Spend (reporting currency)", performance["spend"] if performance["spend"] is not None else "unknown"),
        ("Cost coverage", performance["cost_coverage"]),
        ("Attributed revenue (EUR)", performance["attributed_revenue"]),
        ("Attributed conversions", performance["conversions"]),
        ("Unique converting contacts", performance["unique_converting_contacts"]),
        ("Credited touchpoints", performance["touchpoints_credited"]),
        ("ROI", f"{performance['roi_pct']}%" if performance["roi_available"] else performance["roi_status"]),
        ("ROAS", performance["roas"] if performance["roi_available"] else "suppressed"),
        ("Cost per conversion", performance["cost_per_conversion"]),
        ("Average order value", performance["average_order_value"]),
        ("Budget utilization", f"{performance['budget_utilization']}%"),
        ("Open issues", performance["issue_count"]),
        ("ROI availability note", performance["roi_status"]),
    ]
    sheets = [
        Sheet(
            name="Monthly credit",
            columns=["month", "attributed_revenue", "conversions"],
            records=[
                {
                    "month": row["month"],
                    "attributed_revenue": row["attributed_revenue"],
                    "conversions": row["conversions"],
                }
                for row in monthly
            ],
            numeric=frozenset({"attributed_revenue", "conversions"}),
        ),
        Sheet(
            name="Campaign summary",
            columns=["field", "value"],
            records=[
                {"field": label, "value": value}
                for label, value in summary_rows
            ],
        ),
        Sheet(
            name="Model comparison",
            columns=[
                "model",
                "attributed_revenue",
                "conversions",
                "unique_converting_contacts",
                "touchpoints_credited",
                "roi_pct",
                "roi_available",
            ],
            records=model_rows,
            numeric=frozenset(
                {
                    "attributed_revenue",
                    "conversions",
                    "unique_converting_contacts",
                    "touchpoints_credited",
                    "roi_pct",
                }
            ),
        ),
        Sheet(
            name="Channel mix",
            columns=[
                "channel_id",
                "channel_name",
                "category",
                "attributed_revenue",
                "conversions",
                "touchpoints",
            ],
            records=detail["channel_mix"],
            numeric=frozenset({"attributed_revenue", "conversions", "touchpoints"}),
        ),
        Sheet(
            name="Cost records",
            columns=["cost_id", "cost_date", "amount", "currency", "cost_category", "source_ref", "period"],
            records=detail["cost_records"],
            numeric=frozenset({"amount"}),
            dates=frozenset({"cost_date"}),
        ),
        Sheet(
            name="Issues",
            columns=[
                "issue_id",
                "issue_type",
                "severity",
                "status",
                "split",
                "detection_rule_id",
                "explanation",
                "suggested_disposition",
            ],
            records=detail["issues"],
        ),
    ]
    context = _run_context(
        run,
        report=f"Campaign report - {campaign['campaign_name']}",
        stem=f"campaign-{campaign['campaign_id']}-{model}",
        model=model,
        filters={"campaign_id": campaign["campaign_id"]},
        row_count=len(monthly),
        scope="Monthly attributed revenue and conversions for this campaign under one attribution model.",
        extra={
            "campaign_id": campaign["campaign_id"],
            "campaign_name": campaign["campaign_name"],
            "cost_coverage": performance["cost_coverage"],
            "roi_available": performance["roi_available"],
        },
    )
    pdf_spec = PdfSpec(
        columns=[
            PdfColumn("month", "Month", 20),
            PdfColumn("attributed_revenue", "Attributed revenue", 35, "R", "money"),
            PdfColumn("conversions", "Conversions", 20, "R", "number"),
        ],
        table_heading="Monthly attributed credit",
    )
    return Report(
        context=context,
        sheets=sheets,
        summary_rows=summary_rows,
        pdf_spec=pdf_spec,
        json_primary={"campaign": detail},
    )


def cost_records_report(run: RunContext, campaign_id: str, model: str) -> Report | None:
    conn = connect(run)
    try:
        detail = services.campaign_detail(conn, campaign_id, model)
    finally:
        conn.close()
    if detail is None:
        return None
    campaign = detail["campaign"]
    performance = detail["performance"]
    records = detail["cost_records"]
    total = round(sum(number(row["amount"]) or 0 for row in records), 2)
    summary_rows = [
        ("Campaign", campaign["campaign_name"]),
        ("Campaign id", campaign["campaign_id"]),
        ("Cost coverage", performance["cost_coverage"]),
        ("Cost records", len(records)),
        ("Total amount of listed records", total),
        ("Recorded spend (reporting currency)", performance["spend"] if performance["spend"] is not None else "unknown"),
        ("Interpretation", "Listed records are the source cost rows behind the campaign spend figure."),
    ]
    sheet = Sheet(
        name="Cost records",
        columns=[
            "cost_id",
            "cost_date",
            "amount",
            "currency",
            "cost_category",
            "source_ref",
            "period",
        ],
        records=records,
        numeric=frozenset({"amount"}),
        dates=frozenset({"cost_date"}),
    )
    context = _run_context(
        run,
        report=f"Cost records - {campaign['campaign_name']}",
        stem=f"cost-records-{campaign['campaign_id']}",
        model=model,
        filters={"campaign_id": campaign["campaign_id"]},
        row_count=len(records),
        scope="Every cost record linked to this campaign; no other campaign's spend is included.",
    )
    pdf_spec = PdfSpec(
        columns=[
            PdfColumn("cost_id", "Cost id", 16),
            PdfColumn("cost_date", "Date", 12),
            PdfColumn("amount", "Amount", 12, "R", "money"),
            PdfColumn("currency", "Ccy", 6),
            PdfColumn("cost_category", "Category", 16),
            PdfColumn("period", "Period", 10),
            PdfColumn("source_ref", "Source ref", 22),
        ],
        table_heading="Campaign cost records",
    )
    return Report(
        context=context,
        sheets=[sheet],
        summary_rows=summary_rows,
        pdf_spec=pdf_spec,
    )


def exceptions_report(
    run: RunContext,
    *,
    severity: str | None,
    issue_type: str | None,
    split: str | None,
    status: str | None,
    search: str | None,
) -> Report:
    conn = connect(run)
    try:
        data = services.list_exceptions(
            conn,
            severity=severity,
            issue_type=issue_type,
            split=split,
            status=status,
            search=search,
            limit=1_000_000,
            offset=0,
        )
    finally:
        conn.close()
    items = data["items"]
    by_type = Counter(item["issue_type"] for item in items)
    by_severity = Counter(item["severity"] for item in items)
    by_split = Counter(item["split"] for item in items)
    summary_rows = [
        ("Matching issues", len(items)),
        ("Severity mix", ", ".join(f"{key}={value}" for key, value in sorted(by_severity.items())) or "none"),
        ("Split mix", ", ".join(f"{key}={value}" for key, value in sorted(by_split.items())) or "none"),
        ("Issue types", ", ".join(f"{key}={value}" for key, value in sorted(by_type.items())) or "none"),
        (
            "Sensitivity",
            "Detection output only. Expected anomaly labels and ground truth are not included.",
        ),
        (
            "Status semantics",
            "Suggested dispositions are advisory and have not been applied to source data or financial totals.",
        ),
    ]
    sheets = [
        Sheet(
            name="Issues",
            columns=[
                "issue_id",
                "issue_type",
                "severity",
                "entity_type",
                "primary_entity_id",
                "affected_record_ids",
                "detection_rule_id",
                "detected_at",
                "status",
                "split",
                "explanation",
                "suggested_disposition",
            ],
            records=[
                {
                    "issue_id": item["issue_id"],
                    "issue_type": item["issue_type"],
                    "severity": item["severity"],
                    "entity_type": item["entity_type"],
                    "primary_entity_id": item["primary_entity_id"],
                    "affected_record_ids": item["affected_record_ids"],
                    "detection_rule_id": item["detection_rule_id"],
                    "detected_at": item["detected_at"],
                    "status": item["status"],
                    "split": item["split"],
                    "explanation": item["explanation"],
                    "suggested_disposition": item["suggested_disposition"],
                }
                for item in items
            ],
            numeric=frozenset(),
        ),
        Sheet(
            name="By type",
            columns=["issue_type", "count"],
            records=[{"issue_type": key, "count": value} for key, value in sorted(by_type.items())],
            numeric=frozenset({"count"}),
        ),
        Sheet(
            name="By severity",
            columns=["severity", "count"],
            records=[{"severity": key, "count": value} for key, value in sorted(by_severity.items())],
            numeric=frozenset({"count"}),
        ),
        Sheet(
            name="By split",
            columns=["split", "count"],
            records=[{"split": key, "count": value} for key, value in sorted(by_split.items())],
            numeric=frozenset({"count"}),
        ),
    ]
    context = _run_context(
        run,
        report="Data-quality exception export",
        stem=f"exceptions-{run.run_id}",
        model=None,
        filters={
            "severity": severity,
            "issue_type": issue_type,
            "split": split,
            "status": status,
            "search": search,
        },
        row_count=len(items),
        scope="Every detected exception matching the active filters; not limited to the visible page.",
        artifact_type="detection_output",
        extra={"notice": "Detection output only; contains no ground-truth labels."},
    )
    pdf_spec = PdfSpec(
        columns=[
            PdfColumn("severity", "Sev.", 7),
            PdfColumn("issue_id", "Issue", 12),
            PdfColumn("issue_type", "Type", 15),
            PdfColumn("primary_entity_id", "Entity", 13),
            PdfColumn("split", "Split", 7),
            PdfColumn("detection_rule_id", "Rule", 12),
            PdfColumn("explanation", "Explanation", 40),
        ],
        table_heading="Detected exceptions",
        max_rows=120,
    )
    return Report(context=context, sheets=sheets, summary_rows=summary_rows, pdf_spec=pdf_spec)


def validation_report(
    run: RunContext,
    *,
    status: str | None,
    category: str | None,
    search: str | None,
) -> Report:
    report = read_json_file(run.run_dir / "validation_report.json")
    checks = report.get("checks", [])
    selection = checks
    if status:
        selection = [check for check in selection if check["status"] == status.upper()]
    if category:
        selection = [check for check in selection if check["category"] == category.upper()]
    if search:
        needle = search.lower()
        selection = [
            check
            for check in selection
            if needle
            in (
                f"{check['check_id']} {check['rule_id']} {check['description']} "
                f"{check.get('message', '')}"
            ).lower()
        ]
    summary = report.get("summary", {})
    totals = summary.get("totals", {})
    summary_rows = [
        ("Overall status", summary.get("overall_status")),
        ("Mode", summary.get("mode")),
        ("Rule version", summary.get("rule_version")),
        ("Generated at", summary.get("generated_at")),
        ("Checks (all / filtered)", f"{totals.get('checks')} / {len(selection)}"),
        ("Passed / warnings / failures", f"{totals.get('passed')} / {totals.get('warnings')} / {totals.get('failures')}"),
        (
            "Interpretation",
            "Warnings are expected injected anomaly fixtures, not hidden failures. "
            "The full check list below carries every rule result.",
        ),
    ]
    category_rows = [
        {
            "category": name,
            "checks": values["checks"],
            "passed": values["passed"],
            "warnings": values["warnings"],
            "failures": values["failures"],
        }
        for name, values in summary.get("categories", {}).items()
    ]
    sheets = [
        Sheet(
            name="Checks",
            columns=[
                "check_id",
                "category",
                "rule_id",
                "description",
                "status",
                "severity",
                "records_examined",
                "failure_count",
                "affected_record_ids",
                "message",
            ],
            records=[
                {
                    key: check.get(key)
                    for key in (
                        "check_id",
                        "category",
                        "rule_id",
                        "description",
                        "status",
                        "severity",
                        "records_examined",
                        "failure_count",
                        "affected_record_ids",
                        "message",
                    )
                }
                for check in selection
            ],
            numeric=frozenset({"records_examined", "failure_count"}),
        ),
        Sheet(
            name="Categories",
            columns=["category", "checks", "passed", "warnings", "failures"],
            records=category_rows,
            numeric=frozenset({"checks", "passed", "warnings", "failures"}),
        ),
        Sheet(
            name="Warnings",
            columns=["rule_id", "failure_count", "message"],
            records=summary.get("warning_details", []),
            numeric=frozenset({"failure_count"}),
        ),
    ]
    context = _run_context(
        run,
        report="Validation report",
        stem=f"validation-{run.run_id}",
        model=None,
        filters={"status": status, "category": category, "search": search},
        row_count=len(selection),
        scope="Every validation check matching the active filters, including expected warnings.",
        artifact_type="validation_report",
    )
    pdf_spec = PdfSpec(
        columns=[
            PdfColumn("check_id", "Check", 9),
            PdfColumn("category", "Category", 13),
            PdfColumn("rule_id", "Rule", 16),
            PdfColumn("status", "Status", 9),
            PdfColumn("failure_count", "Rows", 7, "R", "number"),
            PdfColumn("message", "Message", 48),
        ],
        table_heading="Validation checks",
        max_rows=250,
    )
    return Report(context=context, sheets=sheets, summary_rows=summary_rows, pdf_spec=pdf_spec)


def evaluation_report(run: RunContext) -> Report:
    evaluation = read_json_file(run.run_dir / "evaluation.json")
    totals = evaluation.get("totals", {})
    type_rows = [
        {
            "issue_type": row["issue_type"],
            "ground_truth": row["ground_truth"],
            "detected": row["detected"],
            "true_positives": row["true_positives"],
            "false_positives": row["false_positives"],
            "false_negatives": row["false_negatives"],
            "precision_pct": row["precision_pct"],
            "recall_pct": row["recall_pct"],
            "f1_pct": row["f1_pct"],
            "severity_accuracy_pct": row["severity_accuracy_pct"],
        }
        for row in evaluation.get("by_type", [])
    ]
    split_rows = [
        {
            "split": row["split"],
            "ground_truth": row["ground_truth"],
            "detected": row["detected"],
            "true_positives": row["true_positives"],
            "false_positives": row["false_positives"],
            "false_negatives": row["false_negatives"],
            "precision_pct": row["precision_pct"],
            "recall_pct": row["recall_pct"],
        }
        for row in evaluation.get("by_split", [])
    ]
    summary_rows = [
        ("Status", evaluation.get("status")),
        ("Ground-truth fixtures", totals.get("ground_truth")),
        ("Detected", totals.get("detected")),
        ("True positives / false positives / false negatives", f"{totals.get('true_positives')} / {totals.get('false_positives')} / {totals.get('false_negatives')}"),
        ("Precision / recall / F1", f"{totals.get('precision_pct')}% / {totals.get('recall_pct')}% / {totals.get('f1_pct')}%"),
        ("Severity accuracy", f"{totals.get('severity_accuracy_pct')}%"),
        (
            "Interpretation",
            "Synthetic-fixture evaluation. These are not production accuracy measurements.",
        ),
        (
            "Ground-truth handling",
            "Labels are loaded after detection from a separate directory and are not present in analytical tables.",
        ),
    ]
    sheets = [
        Sheet(
            name="By issue type",
            columns=[
                "issue_type",
                "ground_truth",
                "detected",
                "true_positives",
                "false_positives",
                "false_negatives",
                "precision_pct",
                "recall_pct",
                "f1_pct",
                "severity_accuracy_pct",
            ],
            records=type_rows,
            numeric=frozenset(
                {
                    "ground_truth",
                    "detected",
                    "true_positives",
                    "false_positives",
                    "false_negatives",
                    "precision_pct",
                    "recall_pct",
                    "f1_pct",
                    "severity_accuracy_pct",
                }
            ),
        ),
        Sheet(
            name="By split",
            columns=[
                "split",
                "ground_truth",
                "detected",
                "true_positives",
                "false_positives",
                "false_negatives",
                "precision_pct",
                "recall_pct",
            ],
            records=split_rows,
            numeric=frozenset(
                {
                    "ground_truth",
                    "detected",
                    "true_positives",
                    "false_positives",
                    "false_negatives",
                    "precision_pct",
                    "recall_pct",
                }
            ),
        ),
        Sheet(
            name="Counts",
            columns=["metric", "value"],
            records=[
                {
                    "metric": key,
                    "value": totals.get(key),
                }
                for key in (
                    "ground_truth",
                    "detected",
                    "true_positives",
                    "false_positives",
                    "false_negatives",
                    "precision_pct",
                    "recall_pct",
                    "f1_pct",
                    "severity_accuracy_pct",
                )
            ],
            numeric=frozenset(),
        ),
        Sheet(
            name="Ground truth matches",
            columns=[
                "scenario_id",
                "issue_type",
                "ground_truth_split",
                "detected_split",
                "expected_record_ids",
                "matched_issue_id",
                "matched_primary_entity_id",
                "expected_severity",
                "detected_severity",
                "severity_match",
                "detection_rule_id",
                "expected_disposition",
                "detected_disposition",
                "explanation",
            ],
            records=evaluation.get("matches", []),
        ),
        Sheet(
            name="Unmatched",
            columns=["scenario_id", "issue_type", "reason"],
            records=[
                {"scenario_id": scenario, "issue_type": "", "reason": "Ground-truth fixture not detected"}
                for scenario in evaluation.get("missed_scenario_ids", [])
            ],
        ),
    ]
    context = _run_context(
        run,
        report="Evaluation artifact",
        stem=f"evaluation-artifact-{run.run_id}",
        model=None,
        filters={},
        row_count=len(type_rows),
        scope="Synthetic-fixture evaluation by issue type and split, with label rows for reproducibility.",
        artifact_type="evaluation_artifact",
        contains_ground_truth=True,
        extra={
            "notice": (
                "This is the only export that carries ground-truth label rows. It is an "
                "evaluation artifact, not a detection output and not a production accuracy claim."
            ),
            "label_source": evaluation.get("ground_truth", {}).get("label_source"),
        },
    )
    pdf_spec = PdfSpec(
        columns=[
            PdfColumn("issue_type", "Issue type", 18),
            PdfColumn("ground_truth", "Truth", 8, "R", "number"),
            PdfColumn("detected", "Detected", 10, "R", "number"),
            PdfColumn("true_positives", "TP", 6, "R", "number"),
            PdfColumn("false_positives", "FP", 6, "R", "number"),
            PdfColumn("false_negatives", "FN", 6, "R", "number"),
            PdfColumn("precision_pct", "Precision", 11, "R", "number"),
            PdfColumn("recall_pct", "Recall", 10, "R", "number"),
            PdfColumn("f1_pct", "F1", 8, "R", "number"),
        ],
        table_heading="Evaluation by issue type",
    )
    return Report(
        context=context,
        sheets=sheets,
        summary_rows=summary_rows,
        pdf_spec=pdf_spec,
        json_primary={"evaluation": evaluation},
    )


def evidence_report(run: RunContext, issue_id: str) -> Report | None:
    conn = connect(run)
    try:
        detail = services.exception_detail(conn, issue_id)
    finally:
        conn.close()
    if detail is None:
        return None
    related = detail.get("related", {})
    disposition = related.get("disposition_state", {})
    evidence_rows = _flatten_evidence(detail)
    related_records = [
        {
            "record_type": record.get("type", ""),
            "record_id": record.get("order_id")
            or record.get("touchpoint_id")
            or record.get("campaign_id")
            or record.get("link_id")
            or record.get("contact_id")
            or "",
            "fields": json.dumps(record, default=str, sort_keys=True),
        }
        for record in related.get("records", [])
        if isinstance(record, dict)
    ]
    campaign = related.get("campaign")
    if isinstance(campaign, dict):
        related_records.insert(
            0,
            {
                "record_type": "CAMPAIGN",
                "record_id": str(campaign.get("campaign_id", "")),
                "fields": json.dumps(campaign, default=str, sort_keys=True),
            },
        )
    summary_rows = [
        ("Issue", detail["issue_id"]),
        ("Issue type", detail["issue_type"]),
        ("Severity", detail["severity"]),
        ("Status", detail["status"]),
        ("Split", detail["split"]),
        ("Detected at", detail["detected_at"]),
        ("Rule", detail["detection_rule_id"]),
        ("Primary entity", f"{detail['entity_type']} {detail['primary_entity_id']}"),
        ("Affected records", detail["affected_record_ids"]),
        ("Explanation", detail["explanation"]),
        ("Suggested disposition", detail["suggested_disposition"]),
        ("Disposition state", disposition.get("label", "Advisory only")),
        ("Disposition detail", disposition.get("detail", "")),
    ]
    sheets = [
        Sheet(
            name="Evidence",
            columns=["field", "value"],
            records=evidence_rows,
        ),
        Sheet(
            name="Packet",
            columns=["field", "value"],
            records=[{"field": label, "value": value} for label, value in summary_rows],
        ),
        Sheet(
            name="Related records",
            columns=["record_type", "record_id", "fields"],
            records=related_records,
        ),
    ]
    context = _run_context(
        run,
        report=f"Evidence packet - {detail['issue_id']}",
        stem=f"evidence-{detail['issue_id']}",
        model=None,
        filters={"issue_id": detail["issue_id"]},
        row_count=len(evidence_rows),
        scope="One issue with its evidence, related records and disposition state. No label data.",
        artifact_type="evidence_packet",
        extra={
            "issue_id": detail["issue_id"],
            "disposition_applied": False,
            "notice": "Suggested dispositions are advisory and have not been applied.",
        },
    )
    pdf_spec = PdfSpec(
        columns=[
            PdfColumn("field", "Field", 34),
            PdfColumn("value", "Value", 66),
        ],
        table_heading="Evidence fields",
    )
    return Report(
        context=context,
        sheets=sheets,
        summary_rows=summary_rows,
        pdf_spec=pdf_spec,
        json_primary={"packet": detail},
    )


def _flatten_evidence(detail: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(f"{prefix}.{key}" if prefix else str(key), item)
        elif isinstance(value, list):
            output.append({"field": prefix, "value": json.dumps(value, default=str)})
        else:
            output.append({"field": prefix, "value": value})

    for key in (
        "issue_id",
        "issue_type",
        "severity",
        "entity_type",
        "primary_entity_id",
        "affected_record_ids",
        "detection_rule_id",
        "detected_at",
        "status",
        "split",
        "explanation",
        "suggested_disposition",
    ):
        output.append({"field": key, "value": detail.get(key)})
    walk("evidence", detail.get("evidence", {}))
    related = detail.get("related", {})
    for key, value in related.items():
        if key == "records":
            continue
        walk(f"related.{key}", value)
    return output


def journey_report(run: RunContext, reference: str, lookback_days: int) -> Report | None:
    conn = connect(run)
    try:
        payload = services.journey(conn, reference, lookback_days)
    finally:
        conn.close()
    if payload is None:
        return None
    touchpoints = payload.get("touchpoints", [])
    conversion = payload.get("conversion") or {}
    counts = payload.get("counts", {})
    persisted_check = payload.get("persisted_check", {})
    exclusions = payload.get("exclusions", {})
    models = {row["model"]: row for row in payload.get("models", [])}
    persisted = {
        row["model"]: row for row in persisted_check.get("models", [])
    }
    touchpoint_rows = []
    allocation_rows = []
    for touchpoint in touchpoints:
        credits = touchpoint.get("credits", {})
        row = {
            "touchpoint_id": touchpoint["touchpoint_id"],
            "occurred_at": touchpoint["occurred_at"],
            "minutes_from_conversion": touchpoint["minutes_from_conversion"],
            "campaign_id": touchpoint["campaign_id"],
            "campaign_name": touchpoint["campaign_name"],
            "channel_name": touchpoint["channel_name"],
            "touch_type": touchpoint["touch_type"],
            "source_system": touchpoint["source_system"],
            "identity_status": touchpoint["identity_status"],
            "resolution_rule_id": touchpoint["resolution_rule_id"],
            "consent_status": touchpoint["consent_status"],
            "outcome": touchpoint["outcome"],
            "outcome_reason": touchpoint["outcome_reason"],
            "eligible": touchpoint["eligible"],
        }
        for model in MODELS:
            credit = credits.get(model)
            row[f"credit_{model}"] = credit["credit_fraction"] if credit else None
            row[f"attributed_{model}"] = credit["attributed_revenue"] if credit else None
            if credit:
                allocation_rows.append(
                    {
                        "model": model,
                        "touchpoint_id": touchpoint["touchpoint_id"],
                        "campaign_name": touchpoint["campaign_name"],
                        "channel_name": touchpoint["channel_name"],
                        "credit_fraction": credit["credit_fraction"],
                        "attributed_revenue": credit["attributed_revenue"],
                    }
                )
        touchpoint_rows.append(row)
    model_rows = []
    for model in MODELS if models else ():
        computed = models.get(model, {})
        stored = persisted.get(model, {})
        model_rows.append(
            {
                "model": model,
                "status": computed.get("status"),
                "attributed_revenue": computed.get("attributed_revenue"),
                "credited_touchpoints": computed.get("credited_touchpoints"),
                "eligible_touchpoints": computed.get("eligible_touchpoints"),
                "reconciliation_difference": computed.get("reconciliation_difference"),
                "persisted_revenue": stored.get("persisted_revenue"),
                "persisted_match": stored.get("matched"),
            }
        )
    summary_rows = [
        ("Reference", payload.get("reference")),
        ("Status", payload.get("status")),
        ("Contact", (payload.get("contact") or {}).get("contact_id", "n/a")),
    ]
    if conversion:
        summary_rows.extend(
            [
                ("Order", conversion.get("order_id")),
                ("Opportunity", conversion.get("opportunity_id")),
                ("Ordered at", conversion.get("ordered_at")),
                (
                    f"Revenue ({conversion.get('currency', 'EUR')})",
                    conversion.get("revenue"),
                ),
                ("Split", conversion.get("split")),
                ("Lookback days", conversion.get("lookback_days")),
                ("Consent", conversion.get("consent_status")),
            ]
        )
    else:
        summary_rows.append(
            ("Message", payload.get("message", "No recognized conversion for this journey."))
        )
    if counts:
        summary_rows.extend(
            [
                ("Total touches", counts.get("total_touches")),
                ("Eligible touches", counts.get("eligible_touches")),
                ("Excluded touches", counts.get("excluded_touches")),
                ("Exclusion semantics", counts.get("exclusion_semantics")),
            ]
        )
    if persisted_check:
        summary_rows.extend(
            [
                (
                    "Persisted allocations consistent",
                    persisted_check.get("consistent"),
                ),
                (
                    "Allocation difference count",
                    persisted_check.get("difference_count"),
                ),
                ("Reconciliation basis", persisted_check.get("comparison_basis")),
            ]
        )
    sheets = [
        Sheet(
            name="Touchpoints",
            columns=list(touchpoint_rows[0].keys()) if touchpoint_rows else [
                "touchpoint_id",
                "occurred_at",
                "minutes_from_conversion",
                "campaign_id",
                "campaign_name",
                "channel_name",
                "touch_type",
                "source_system",
                "identity_status",
                "resolution_rule_id",
                "consent_status",
                "outcome",
                "outcome_reason",
                "eligible",
                "credit_first_touch",
                "attributed_first_touch",
                "credit_last_touch",
                "attributed_last_touch",
                "credit_linear",
                "attributed_linear",
            ],
            records=touchpoint_rows,
            numeric=frozenset(
                {
                    "minutes_from_conversion",
                    "credit_first_touch",
                    "attributed_first_touch",
                    "credit_last_touch",
                    "attributed_last_touch",
                    "credit_linear",
                    "attributed_linear",
                }
            ),
        ),
        Sheet(
            name="Allocations",
            columns=[
                "model",
                "touchpoint_id",
                "campaign_name",
                "channel_name",
                "credit_fraction",
                "attributed_revenue",
            ],
            records=allocation_rows,
            numeric=frozenset({"credit_fraction", "attributed_revenue"}),
        ),
        Sheet(
            name="Exclusions",
            columns=["reason", "count"],
            records=[
                {"reason": key, "count": value}
                for key, value in exclusions.items()
            ],
            numeric=frozenset({"count"}),
        ),
        Sheet(
            name="Models",
            columns=[
                "model",
                "status",
                "attributed_revenue",
                "credited_touchpoints",
                "eligible_touchpoints",
                "reconciliation_difference",
                "persisted_revenue",
                "persisted_match",
            ],
            records=model_rows,
            numeric=frozenset(
                {
                    "attributed_revenue",
                    "credited_touchpoints",
                    "eligible_touchpoints",
                    "reconciliation_difference",
                    "persisted_revenue",
                }
            ),
        ),
        Sheet(
            name="Conversion",
            columns=["field", "value"],
            records=(
                [
                    {"field": key, "value": value}
                    for key, value in conversion.items()
                    if key != "duplicate_orders"
                ]
                + [
                    {
                        "field": "duplicate_orders",
                        "value": json.dumps(
                            conversion.get("duplicate_orders", []), default=str
                        ),
                    }
                ]
                if conversion
                else [
                    {"field": "status", "value": payload.get("status")},
                    {"field": "message", "value": payload.get("message")},
                ]
            ),
        ),
    ]
    context = _run_context(
        run,
        report=f"Journey reconstruction - {payload['reference']}",
        stem=f"journey-{payload['reference']}",
        model="first_touch, last_touch, linear",
        filters={"reference": payload.get("reference"), "lookback_days": lookback_days},
        row_count=len(touchpoints),
        scope=(
            "Every candidate touchpoint evaluated for this conversion, including exclusions."
            if conversion
            else "No recognized conversion revenue; the export records why attribution does not apply."
        ),
        artifact_type="journey_reconstruction",
        extra={
            "reference": payload.get("reference"),
            "persisted_consistent": payload.get("persisted_consistent"),
            "exclusion_semantics": counts.get("exclusion_semantics"),
        },
    )
    pdf_spec = PdfSpec(
        columns=[
            PdfColumn("occurred_at", "Occurred at", 18),
            PdfColumn("touchpoint_id", "Touchpoint", 15),
            PdfColumn("campaign_name", "Campaign", 26),
            PdfColumn("channel_name", "Channel", 13),
            PdfColumn("outcome", "Outcome", 15),
            PdfColumn("outcome_reason", "Reason", 25),
            PdfColumn("credit_linear", "Linear credit", 10, "R", "number"),
        ],
        table_heading="Candidate touchpoints",
        max_rows=150,
    )
    return Report(
        context=context,
        sheets=sheets,
        summary_rows=summary_rows,
        pdf_spec=pdf_spec,
        json_primary={"journey": payload},
    )


def run_report(run: RunContext) -> Report:
    manifest = run.manifest
    validation = read_json_file(run.run_dir / "validation_report.json")
    evaluation_path = run.run_dir / "evaluation.json"
    evaluation = read_json(evaluation_path) if evaluation_path.exists() else {}
    summary_path = run.run_dir / "summary.json"
    summary = read_json(summary_path) if summary_path.exists() else {}
    counts = manifest.get("counts", {})
    config = manifest.get("config", {})
    count_rows = [{"entity": key, "count": value} for key, value in sorted(counts.items())]
    generation_rows = [
        {"field": key, "value": value}
        for key, value in {
            "run_id": run.run_id,
            "profile": manifest.get("profile"),
            "seed": manifest.get("seed"),
            "status": manifest.get("status"),
            "generated_at": manifest.get("generated_at"),
            "combined_hash": manifest.get("combined_hash"),
            "generator_version": config.get("generator_version"),
            "attribution_rule_version": config.get("attribution_rule_version"),
            "validation_rule_version": manifest.get("versions", {}).get("validation"),
            "dataset_start": config.get("dataset_start"),
            "dataset_end": config.get("dataset_end"),
            "lookback_days": config.get("lookback_days"),
            "reporting_currency": config.get("reporting_currency"),
            "models": ", ".join(config.get("models", [])),
            "splits": json.dumps(config.get("splits", [])),
        }.items()
    ]
    attribution_rows = [
        {
            "model": name,
            "attributed_revenue": values["attributed_revenue"],
            "eligible_revenue": values["eligible_revenue"],
            "attributed_conversions": values["attributed_conversions"],
            "unattributed_conversions": values["unattributed_conversions"],
        }
        for name, values in summary.get("attribution_by_model", {}).items()
    ]
    validation_rows = [
        {
            key: check.get(key)
            for key in (
                "check_id",
                "category",
                "rule_id",
                "description",
                "status",
                "severity",
                "records_examined",
                "failure_count",
                "affected_record_ids",
                "message",
            )
        }
        for check in validation.get("checks", [])
    ]
    totals = validation.get("summary", {}).get("totals", {})
    eval_totals = evaluation.get("totals", {})
    summary_rows = [
        ("Run", run.run_id),
        ("Profile", manifest.get("profile")),
        ("Seed", manifest.get("seed")),
        ("Status", manifest.get("status")),
        ("Generated at", manifest.get("generated_at")),
        ("Combined hash", manifest.get("combined_hash")),
        ("Validation", f"{totals.get('checks')} checks / {totals.get('failures')} failures / {totals.get('warnings')} warnings"),
        (
            "Evaluation",
            (
                f"{eval_totals.get('ground_truth')} fixtures / "
                f"{eval_totals.get('precision_pct')}% precision / "
                f"{eval_totals.get('recall_pct')}% recall"
            )
            if eval_totals
            else "not available",
        ),
        (
            "Bundle contents",
            "Run manifest, configuration, entity counts, every validation check and "
            "aggregate evaluation metrics. Ground-truth label rows are excluded.",
        ),
    ]
    sheets = [
        Sheet(
            name="Entity counts",
            columns=["entity", "count"],
            records=count_rows,
            numeric=frozenset({"count"}),
        ),
        Sheet(
            name="Generation",
            columns=["field", "value"],
            records=generation_rows,
        ),
        Sheet(
            name="Attribution",
            columns=[
                "model",
                "attributed_revenue",
                "eligible_revenue",
                "attributed_conversions",
                "unattributed_conversions",
            ],
            records=attribution_rows,
            numeric=frozenset(
                {
                    "attributed_revenue",
                    "eligible_revenue",
                    "attributed_conversions",
                    "unattributed_conversions",
                }
            ),
        ),
        Sheet(
            name="Validation",
            columns=[
                "check_id",
                "category",
                "rule_id",
                "description",
                "status",
                "severity",
                "records_examined",
                "failure_count",
                "affected_record_ids",
                "message",
            ],
            records=validation_rows,
            numeric=frozenset({"records_examined", "failure_count"}),
        ),
        Sheet(
            name="Evaluation summary",
            columns=["issue_type", "ground_truth", "detected", "true_positives", "false_positives", "false_negatives", "precision_pct", "recall_pct", "f1_pct"],
            records=evaluation.get("by_type", []),
            numeric=frozenset(
                {
                    "ground_truth",
                    "detected",
                    "true_positives",
                    "false_positives",
                    "false_negatives",
                    "precision_pct",
                    "recall_pct",
                    "f1_pct",
                }
            ),
        ),
    ]
    context = _run_context(
        run,
        report="Run manifest",
        stem=f"run-{run.run_id}",
        model=None,
        filters={},
        row_count=len(count_rows),
        scope="Manifest, configuration, counts, validation and aggregate evaluation for the active run.",
        artifact_type="run_manifest",
        extra={
            "notice": (
                "The run bundle excludes ground-truth label rows. The evaluation artifact "
                "is the only export that carries them."
            ),
            "combined_hash": manifest.get("combined_hash"),
        },
    )
    pdf_spec = PdfSpec(
        columns=[
            PdfColumn("entity", "Entity", 50),
            PdfColumn("count", "Rows", 20, "R", "number"),
        ],
        table_heading="Entity counts",
    )
    return Report(context=context, sheets=sheets, summary_rows=summary_rows, pdf_spec=pdf_spec)


RUN_BUNDLE_README = """YottaFlex run bundle
=====================

This bundle contains the run manifest, configuration, entity counts, the full
validation check list and aggregate evaluation metrics for {run_id}.

It deliberately excludes ground-truth label rows. To download the labelled
evaluation fixture, use the explicit Evaluation artifact export in the console
or GET /api/exports/evaluation?format=json.

Ground truth is loaded after detection from a separate directory and is never
present in analytical tables. Detection results in this bundle are synthetic
fixture results, not production accuracy claims.
"""


def run_bundle_bytes(run: RunContext) -> bytes:
    manifest = dict(run.manifest)
    manifest.pop("ground_truth", None)
    manifest.pop("evaluation", None)
    manifest.pop("paths", None)
    evaluation_path = run.run_dir / "evaluation.json"
    evaluation = read_json(evaluation_path) if evaluation_path.exists() else {}
    sanitized_evaluation = {
        key: evaluation[key]
        for key in ("run_id", "profile", "seed", "status", "totals", "by_type", "by_split")
        if key in evaluation
    }
    validation = read_json_file(run.run_dir / "validation_report.json")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("README.txt", RUN_BUNDLE_README.format(run_id=run.run_id))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
        archive.writestr("run_config.json", json.dumps(manifest.get("config", {}), indent=2, default=str))
        archive.writestr(
            "evaluation_summary.json",
            json.dumps(sanitized_evaluation, indent=2, default=str),
        )
        counts = manifest.get("counts", {})
        counts_csv = io.StringIO(newline="")
        writer = csv.writer(counts_csv, lineterminator="\n")
        writer.writerow(["entity", "count"])
        for entity, count in sorted(counts.items()):
            writer.writerow([entity, count])
        archive.writestr("counts.csv", counts_csv.getvalue())
        checks = validation.get("checks", [])
        checks_csv = io.StringIO(newline="")
        writer = csv.writer(checks_csv, lineterminator="\n")
        columns = [
            "check_id",
            "category",
            "rule_id",
            "description",
            "status",
            "severity",
            "records_examined",
            "failure_count",
            "affected_record_ids",
            "message",
        ]
        writer.writerow(columns)
        for check in checks:
            writer.writerow(["" if check.get(column) is None else check.get(column) for column in columns])
        archive.writestr("validation_checks.csv", checks_csv.getvalue())
        archive.writestr(
            "validation_summary.json",
            json.dumps(validation.get("summary", {}), indent=2, default=str),
        )
    return buffer.getvalue()


_LOAD_SOURCE = re.compile(r"FROM '[^']*[\\/]([^\\/']+)'")


def write_sql_package(run: RunContext, target_dir: Path) -> Path:
    """Export the DuckDB database as schema.sql + load.sql + CSV data."""

    target_dir.mkdir(parents=True, exist_ok=True)
    duckdb_target = target_dir / "database"
    duckdb_target.mkdir()
    conn = duckdb.connect(str(run.db_path), read_only=True)
    try:
        conn.execute(
            f"EXPORT DATABASE '{duckdb_target.as_posix()}' (FORMAT CSV, HEADER)"
        )
    finally:
        conn.close()
    load_path = duckdb_target / "load.sql"
    text = load_path.read_text(encoding="utf-8")
    text = _LOAD_SOURCE.sub(r"FROM '\1'", text)
    header = (
        f"-- YottaFlex SQL package for run {run.run_id}\n"
        f"-- Generated {datetime.now(UTC).isoformat().replace('+00:00', 'Z')}\n"
        "-- Load into a new database, from this directory:\n"
        "--   duckdb analytics.duckdb \".read schema.sql\" \".read load.sql\"\n"
    )
    load_path.write_text(header + text, encoding="utf-8")
    readme = (
        "YottaFlex SQL package\n"
        "=====================\n\n"
        f"Run: {run.run_id}\n\n"
        "schema.sql creates every table; load.sql copies the bundled CSV files into\n"
        "those tables using relative paths. From this directory:\n\n"
        "  duckdb analytics.duckdb \".read schema.sql\" \".read load.sql\"\n\n"
        "Computed views are not part of DuckDB's EXPORT DATABASE output; the API and\n"
        "the console build them from the same base tables. The CSV data is complete.\n"
    )
    (duckdb_target / "README.txt").write_text(readme, encoding="utf-8")
    archive_path = target_dir / f"sql-package-{run.run_id}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(duckdb_target.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(duckdb_target).as_posix())
    shutil.rmtree(duckdb_target, ignore_errors=True)
    return archive_path


def cleanup_export_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def temp_export_dir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"yottaflex-{prefix}-"))

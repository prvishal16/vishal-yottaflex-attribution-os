"""End-to-end dataset generation and analytical pipeline orchestration."""

from __future__ import annotations

import random
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yottaflex.analytics import compute_analytics
from yottaflex.attribution_pipeline import compute_attribution
from yottaflex.config import (
    ANOMALY_RULE_VERSION,
    ANOMALY_TYPES,
    ATTRIBUTION_RULE_VERSION,
    GENERATOR_VERSION,
    VALIDATION_RULE_VERSION,
    RunConfig,
    Settings,
)
from yottaflex.detection import DETECTION_RULE_VERSION, run_detection
from yottaflex.evaluation import evaluate_detection
from yottaflex.generation.anomaly_injection import inject_anomalies
from yottaflex.generation.context import GenerationContext
from yottaflex.generation.journey_generation import generate_touchpoints
from yottaflex.generation.master_data import (
    CHANNELS,
    generate_audiences,
    generate_campaigns,
    generate_contacts,
    generation_metadata,
)
from yottaflex.generation.transaction_generation import generate_transactions
from yottaflex.manifest import combined_hash, file_hashes, table_hashes, write_manifest
from yottaflex.storage import build_database, create_typed_views, refresh_table
from yottaflex.tables import ALL_TABLES, CORE_TABLES, DERIVED_TABLES
from yottaflex.util import iso, read_json, write_csv, write_json
from yottaflex.validation.engine import run_validation, validation_report_json

Progress = Callable[[str], None]


def _noop(message: str) -> None:
    return


def _write_core_tables(ctx: GenerationContext, run_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, spec in CORE_TABLES.items():
        if name not in ctx.tables:
            raise KeyError(f"Generator did not produce required table '{name}'")
        counts[name] = write_csv(
            run_dir / f"{name}.csv", spec.columns, ctx.tables[name], spec.sort_key
        )
    return counts


def _write_ground_truth(
    config: RunConfig, settings: Settings, ctx: GenerationContext
) -> Path:
    label_dir = settings.ground_truth_dir(config.run_id)
    if label_dir.exists():
        shutil.rmtree(label_dir)
    label_dir.mkdir(parents=True, exist_ok=True)
    columns = [
        "scenario_id",
        "issue_type",
        "severity",
        "entity_type",
        "record_ids",
        "split",
        "expected_disposition",
        "notes",
        "fixture_version",
    ]
    write_csv(
        label_dir / "labels.csv",
        columns,
        ctx.anomaly_labels,
        sort_key=("scenario_id",),
    )
    spec = config.spec
    expected = {
        "DUPLICATE_REVENUE": spec.duplicate_orders,
        "POST_CONVERSION_TOUCH": spec.post_conversion_touches,
        "CURRENCY_MISMATCH": spec.currency_mismatch_costs,
        "MISSING_CAMPAIGN_COST": spec.missing_cost_campaigns,
        "UNSUPPORTED_IDENTITY_LINK": spec.unsupported_links,
    }
    write_json(
        label_dir / "manifest.json",
        {
            "run_id": config.run_id,
            "profile": config.profile,
            "seed": config.seed,
            "fixture_version": ANOMALY_RULE_VERSION,
            "label_count": len(ctx.anomaly_labels),
            "expected_fixtures": expected,
            "actual_fixtures": ctx.fixture_counts,
            "all_fixtures_injected": all(
                ctx.fixture_counts.get(issue_type, 0) == expected[issue_type]
                for issue_type in ANOMALY_TYPES
            ),
            "notice": "Ground truth is stored outside the analytical dataset and is read only by the evaluator.",
        },
    )
    return label_dir


def _write_validation(
    conn, checks: list[dict[str, Any]], summary: dict[str, Any], run_dir: Path
) -> None:
    spec = DERIVED_TABLES["validation_results"]
    rows = [{column: check.get(column, "") for column in spec.columns} for check in checks]
    write_csv(run_dir / "validation_results.csv", spec.columns, rows, spec.sort_key)
    refresh_table(conn, run_dir, "validation_results")
    create_typed_views(conn)
    write_json(run_dir / "validation_report.json", {"summary": summary, "checks": checks})
    report_path = run_dir / "validation_report.txt"
    report_path.write_text(validation_report_json(summary, checks), encoding="utf-8")


def refresh_validation(
    conn, config: RunConfig, settings: Settings | None = None, strict: bool = False
) -> dict[str, Any]:
    """Re-run validation, persist artifacts and refresh manifest hashes."""

    from yottaflex.manifest import combined_hash, file_hashes, table_hashes, write_manifest

    settings = settings or Settings.from_env()
    checks, summary = run_validation(conn, config, strict=strict)
    _write_validation(conn, checks, summary, settings.run_dir(config.run_id))
    manifest_path = settings.manifest_path(config.run_id)
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        hashes = table_hashes(settings.run_dir(config.run_id))
        manifest["table_hashes"] = hashes
        manifest["combined_hash"] = combined_hash(hashes)
        manifest["output_files"] = file_hashes(settings.run_dir(config.run_id))
        manifest["validation"] = {
            "overall_status": summary["overall_status"],
            "totals": summary["totals"],
            "attribution_checks_included": summary["attribution_checks_included"],
        }
        write_manifest(settings.manifests_root, config.run_id, manifest)
    return summary


def _db_counts(conn) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in ALL_TABLES:
        row = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]
        ).fetchone()
        if row and row[0]:
            counts[name] = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
    return counts


def generate(
    config: RunConfig,
    settings: Settings | None = None,
    progress: Progress | None = None,
    strict_validation: bool = False,
) -> dict[str, Any]:
    report = progress or _noop
    settings = settings or Settings.from_env()
    run_dir = settings.run_dir(config.run_id)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    report("generate: reference data and campaigns")
    rng = random.Random(config.seed)
    ctx = GenerationContext(config, rng)
    channels = [dict(row) for row in CHANNELS]
    audiences = generate_audiences()
    campaigns, campaign_channels, campaign_audiences, creatives = generate_campaigns(
        rng, config.spec, channels, audiences
    )
    contacts = generate_contacts(rng, config.spec, channels)
    ctx.tables.update(
        {
            "channels": channels,
            "audiences": audiences,
            "campaigns": campaigns,
            "campaign_channels": campaign_channels,
            "campaign_audiences": campaign_audiences,
            "creatives": creatives,
            "contacts": contacts,
            "sessions": [],
            "identity_links": [],
            "touchpoints": [],
            "leads": [],
            "opportunities": [],
            "orders": [],
            "cost_records": [],
            "lifecycle_events": [],
        }
    )

    report("generate: journeys and touchpoints")
    generate_touchpoints(ctx)
    report("generate: opportunities, orders, costs and lifecycle")
    generate_transactions(ctx)
    report("generate: controlled anomaly fixtures")
    inject_anomalies(ctx)

    report("write: deterministic CSV tables")
    core_counts = _write_core_tables(ctx, run_dir)
    generation_info = generation_metadata()
    write_json(
        run_dir / "run_config.json",
        {
            **config.to_dict(),
            **generation_info,
            "attribution_rule_version": ATTRIBUTION_RULE_VERSION,
            "validation_rule_version": VALIDATION_RULE_VERSION,
            "detection_rule_version": DETECTION_RULE_VERSION,
            "generated_at": iso(datetime.now(UTC)),
            "core_counts": core_counts,
        },
    )
    ground_truth_dir = _write_ground_truth(config, settings, ctx)

    report("build: DuckDB analytical index from CSV")
    db_path = run_dir / "analytics.duckdb"
    conn = build_database(db_path, run_dir)

    try:
        report("attribution: canonical conversions and three models")
        attribution = compute_attribution(conn, config, run_dir)

        report("detection: rule-based anomaly detection")
        detection = run_detection(conn, run_dir)

        report("analytics: campaign, channel, financial and executive aggregates")
        analytics = compute_analytics(conn, config, run_dir)

        report("validation: structural, temporal, financial and attribution checks")
        checks, validation = run_validation(conn, config, strict=strict_validation)
        _write_validation(conn, checks, validation, run_dir)

        report("evaluation: score detection against separate ground truth")
        evaluation = evaluate_detection(
            config, config.run_id, run_dir, ground_truth_dir, settings.reports_root
        )

        report("manifest: canonical hashes and run registry")
        hashes = table_hashes(run_dir)
        counts = _db_counts(conn)
        summary = analytics["summary"]
        metrics = {
            "eligible_conversions": summary["kpis"]["eligible_conversions"],
            "eligible_conversion_revenue": summary["kpis"]["eligible_conversion_revenue"],
            "attributed_revenue": summary["kpis"]["attributed_revenue"],
            "recorded_spend": summary["kpis"]["recorded_spend"],
            "roi_pct": summary["kpis"]["roi_pct"],
            "roas": summary["kpis"]["roas"],
            "roi_available": summary["kpis"]["roi_available"],
            "unattributed_conversions": summary["kpis"]["unattributed_conversions"],
            "data_quality_issues": summary["kpis"]["data_quality_issues"],
        }
        manifest = {
            "run_id": config.run_id,
            "profile": config.profile,
            "seed": config.seed,
            "status": "COMPLETE",
            "generated_at": iso(datetime.now(UTC)),
            "config": config.to_dict(),
            "versions": {
                "generator": GENERATOR_VERSION,
                "attribution": ATTRIBUTION_RULE_VERSION,
                "detection": DETECTION_RULE_VERSION,
                "validation": VALIDATION_RULE_VERSION,
                "anomaly_fixtures": ANOMALY_RULE_VERSION,
            },
            "counts": counts,
            "metrics": metrics,
            "attribution": attribution,
            "detection": detection,
            "analytics": {
                "campaigns": analytics["campaigns"],
                "channels": analytics["channels"],
            },
            "validation": {
                "overall_status": validation["overall_status"],
                "totals": validation["totals"],
                "attribution_checks_included": validation["attribution_checks_included"],
            },
            "evaluation": {
                "status": evaluation["status"],
                "totals": evaluation["totals"],
                "by_type": evaluation["by_type"],
                "by_split": evaluation["by_split"],
            },
            "ground_truth": {
                "path": str(ground_truth_dir),
                "labels": len(ctx.anomaly_labels),
                "loaded_into_analytical_tables": False,
            },
            "paths": {
                "run_dir": str(run_dir),
                "database": str(db_path),
                "validation_report": str(run_dir / "validation_report.json"),
                "evaluation": str(run_dir / "evaluation.json"),
            },
            "table_hashes": hashes,
            "combined_hash": combined_hash(hashes),
            "output_files": file_hashes(run_dir),
            "notice": "Synthetic data only. Contains deliberate labelled anomalies for quality evaluation.",
        }
        write_manifest(settings.manifests_root, config.run_id, manifest)
    finally:
        conn.close()

    return manifest


def rerun_and_compare(
    config: RunConfig,
    settings: Settings | None = None,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Generate twice in isolated roots and compare canonical hashes.

    Verification must not overwrite the active run, its manifest, or its
    execution timestamps.
    """

    import tempfile
    from pathlib import Path

    from yottaflex.manifest import compare_manifests

    with tempfile.TemporaryDirectory(prefix="yottaflex-verify-") as temp:
        root = Path(temp)
        manifests = []
        for side in ("left", "right"):
            side_settings = Settings(
                data_root=root / side / "data",
                ground_truth_root=root / side / "ground_truth",
                reports_root=root / side / "reports",
            )
            manifests.append(generate(config, side_settings, progress=progress))
    return compare_manifests(manifests[0], manifests[1])

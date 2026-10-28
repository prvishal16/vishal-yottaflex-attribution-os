"""FastAPI application for the YottaFlex attribution analytics platform."""

from __future__ import annotations

import csv
import io
import threading
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from yottaflex.api import exports, reports, services
from yottaflex.api.deps import RunContext, active_run_id, connect, resolve_run
from yottaflex.config import (
    DEFAULT_SEED,
    MODELS,
    PROFILES,
    PROJECT_ROOT,
    RunConfig,
    Settings,
)
from yottaflex.generator import generate, refresh_validation, rerun_and_compare
from yottaflex.tables import ALL_TABLES
from yottaflex.util import read_json

GENERATION_LOCK = threading.Lock()


@dataclass
class DatabaseHandle:
    run: RunContext
    conn: duckdb.DuckDBPyConnection


def database(
    run_id: str | None = Query(default=None, description="Dataset run; defaults to active run."),
) -> Iterator[DatabaseHandle]:
    run = resolve_run(run_id)
    conn = connect(run)
    try:
        yield DatabaseHandle(run=run, conn=conn)
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="YottaFlex Attribution Analytics API",
    version="1.0.0",
    description=(
        "Deterministic synthetic marketing data, identity resolution, multi-touch attribution, "
        "financial reconciliation, data-quality exceptions and evaluation."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    profile: Literal["small", "demo", "full"] = "demo"
    seed: int = Field(default=DEFAULT_SEED, ge=0, le=2_147_483_647)
    strict_validation: bool = False


class ValidateRequest(BaseModel):
    run_id: str | None = None
    strict: bool = False


class VerifyRequest(BaseModel):
    profile: Literal["small", "demo", "full"] = "small"
    seed: int = Field(default=DEFAULT_SEED, ge=0, le=2_147_483_647)


VERIFY_JOBS: dict[str, dict[str, Any]] = {}


@app.get("/api/health", tags=["system"])
def health() -> dict[str, Any]:
    settings = Settings.from_env()
    run_id = active_run_id(settings)
    if not run_id:
        return {"status": "ok", "dataset": None, "service": "yottaflex-api"}
    try:
        run = resolve_run(run_id, settings)
    except HTTPException:
        return {"status": "degraded", "dataset": run_id, "service": "yottaflex-api"}
    return {
        "status": "ok",
        "service": "yottaflex-api",
        "dataset": {
            "run_id": run.run_id,
            "profile": run.manifest.get("profile"),
            "seed": run.manifest.get("seed"),
            "generated_at": run.manifest.get("generated_at"),
            "status": run.manifest.get("status"),
        },
    }


@app.get("/api/runs", tags=["runs"])
def list_runs() -> dict[str, Any]:
    settings = Settings.from_env()
    index_path = settings.run_index_path()
    runs = read_json(index_path)["runs"] if index_path.exists() else []
    for run in runs:
        manifest_path = settings.manifest_path(str(run.get("run_id", "")))
        if not manifest_path.exists():
            continue
        manifest = read_json(manifest_path)
        run["counts"] = manifest.get("counts", {})
        run["seed"] = run.get("seed", manifest.get("seed"))
        run["status"] = run.get("status", manifest.get("status"))
        run["combined_hash"] = run.get("combined_hash", manifest.get("combined_hash"))
    return {"active_run_id": active_run_id(settings), "runs": runs}


@app.get("/api/runs/{run_id}", tags=["runs"])
def get_run(run_id: str) -> dict[str, Any]:
    run = resolve_run(run_id)
    return run.manifest


@app.post("/api/runs/generate", status_code=201, tags=["runs"])
def generate_run(request: GenerateRequest) -> dict[str, Any]:
    if request.profile not in PROFILES:
        raise HTTPException(status_code=400, detail="Unknown profile.")
    if not GENERATION_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A dataset generation is already running.")
    try:
        manifest = generate(
            RunConfig(profile=request.profile, seed=request.seed),
            strict_validation=request.strict_validation,
        )
        return manifest
    except Exception as exc:  # surfaced for local operations; details in server log
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}") from exc
    finally:
        GENERATION_LOCK.release()


@app.post("/api/runs/validate", tags=["runs"])
def validate_run(request: ValidateRequest) -> dict[str, Any]:
    run = resolve_run(request.run_id)
    conn = duckdb.connect(str(run.db_path))
    try:
        summary = refresh_validation(
            conn,
            RunConfig(profile=run.manifest["profile"], seed=run.manifest["seed"]),
            settings=run.settings,
            strict=request.strict,
        )
        report = read_json(run.run_dir / "validation_report.json")
        return {"summary": summary, "checks": report.get("checks", [])}
    finally:
        conn.close()


@app.post("/api/runs/verify", status_code=202, tags=["runs"])
def start_verify(request: VerifyRequest) -> dict[str, Any]:
    """Start a reproducibility check that regenerates the run twice in isolation.

    The active run, its manifest and its timestamps are never touched: both
    sides are generated into a temporary directory and only their canonical
    hashes are compared.
    """

    if request.profile not in PROFILES:
        raise HTTPException(status_code=400, detail="Unknown profile.")
    job_id = uuid.uuid4().hex[:12]
    job: dict[str, Any] = {
        "job_id": job_id,
        "status": "RUNNING",
        "profile": request.profile,
        "seed": request.seed,
        "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "finished_at": None,
        "result": None,
        "error": None,
        "note": (
            "Two isolated generations are produced and their canonical hashes are "
            "compared. The active dataset is not modified."
        ),
    }
    VERIFY_JOBS[job_id] = job

    def worker() -> None:
        try:
            comparison = rerun_and_compare(
                RunConfig(profile=request.profile, seed=request.seed)
            )
            job["result"] = comparison
            job["status"] = (
                "REPRODUCIBLE" if comparison.get("reproducible") else "NOT_REPRODUCIBLE"
            )
        except Exception as exc:
            job["status"] = "FAILED"
            job["error"] = str(exc)
        finally:
            job["finished_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    threading.Thread(target=worker, name=f"verify-{job_id}", daemon=True).start()
    return job


@app.get("/api/runs/verify/{job_id}", tags=["runs"])
def get_verify(job_id: str) -> dict[str, Any]:
    job = VERIFY_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Verification job not found.")
    return job


@app.get("/api/summary", tags=["analytics"])
def get_summary(run_id: str | None = None) -> dict[str, Any]:
    run = resolve_run(run_id)
    return services.summary(run)


@app.get("/api/campaigns", tags=["analytics"])
def get_campaigns(
    model: str = Query(default="linear"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="attributed_revenue"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    channel_id: str | None = None,
    search: str | None = None,
    coverage: str | None = None,
    min_revenue: float | None = None,
    db: DatabaseHandle = Depends(database),
) -> dict[str, Any]:
    data = services.list_campaigns(
        db.conn,
        model=model,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
        channel_id=channel_id,
        search=search,
        coverage=coverage,
        min_revenue=min_revenue,
    )
    return data


@app.get("/api/campaigns/export", tags=["analytics"])
def export_campaigns(
    model: str = Query(default="linear"),
    sort: str = Query(default="attributed_revenue"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    channel_id: str | None = None,
    search: str | None = None,
    coverage: str | None = None,
    min_revenue: float | None = None,
    db: DatabaseHandle = Depends(database),
) -> Response:
    model = model if model in MODELS else "linear"
    columns, records = services.campaign_export(
        db.conn,
        model=model,
        sort=sort,
        order=order,
        channel_id=channel_id,
        search=search,
        coverage=coverage,
        min_revenue=min_revenue,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(records)
    filename = f"{db.run.run_id}_{model}_campaigns.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/exports/campaign-performance", tags=["analytics"])
def export_campaign_performance(
    format: str = Query(default="csv", pattern="^(csv|json|xlsx|pdf)$"),
    model: str = Query(default="linear"),
    sort: str = Query(default="attributed_revenue"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    channel_id: str | None = None,
    search: str | None = None,
    coverage: str | None = None,
    min_revenue: float | None = None,
    db: DatabaseHandle = Depends(database),
) -> Response:
    """Analyst export of the filtered campaign ledger in the requested format.

    Every matching record is exported - the visible page is never a limit - and
    the response carries the run, model, filter and timestamp context so a
    downloaded file can be traced back to the dataset that produced it.
    """

    model = model if model in MODELS else "linear"
    columns, records = services.campaign_export_records(
        db.conn,
        model=model,
        sort=sort,
        order=order,
        channel_id=channel_id,
        search=search,
        coverage=coverage,
        min_revenue=min_revenue,
    )
    totals = services.compare_models(db.conn, model, "last_touch" if model != "last_touch" else "first_touch", 1)
    model_totals = totals["totals"]["model_a" if model != "last_touch" else "model_b"]
    summary_rows = services.export_summary_rows(records, model, model_totals)
    attribution_header, attribution_records = services.export_attribution_sheet(db.conn, model)
    quality_header, quality_records = services.export_data_quality_sheet(db.conn)
    context = exports.build_context(
        run_id=db.run.run_id,
        profile=db.run.manifest.get("profile"),
        seed=db.run.manifest.get("seed"),
        model=model,
        sort=sort,
        order=order,
        filters={
            "channel_id": channel_id,
            "search": search,
            "coverage": coverage,
            "min_revenue": min_revenue,
        },
        row_count=len(records),
    )
    payload, content_type, filename = exports.build_export(
        format,
        context=context,
        columns=list(columns),
        records=records,
        extras={
            "Attribution": (attribution_header, attribution_records),
            "Data Quality": (quality_header, quality_records),
        },
        summary_rows=summary_rows,
    )
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/exports/formats", tags=["analytics"])
def export_formats() -> dict[str, Any]:
    """The export formats the console can offer, with what each one contains."""

    return {
        "formats": [
            {
                "format": key,
                "label": exports.FORMAT_LABELS[key],
                "description": exports.FORMAT_DESCRIPTIONS[key],
                "content_type": exports.FORMAT_CONTENT_TYPES[key],
            }
            for key in exports.EXPORT_FORMATS
        ],
        "run_formats": [
            {
                "format": key,
                "label": exports.FORMAT_LABELS[key],
                "description": exports.FORMAT_DESCRIPTIONS[key],
                "content_type": exports.FORMAT_CONTENT_TYPES[key],
            }
            for key in exports.RUN_EXPORT_FORMATS
        ],
        "run_bundle": {
            "contains_ground_truth": False,
            "note": (
                "The run bundle contains the manifest, configuration, counts, validation "
                "and aggregate evaluation metrics. Ground-truth label rows are excluded."
            ),
        },
        "semantics": (
            "Exports contain every record matching the active filters, not only the "
            "visible page. Run id, model, filters and generation time travel with the "
            "file in the filename, the JSON context block and the XLSX Summary sheet."
        ),
    }


@app.get("/api/campaigns/{campaign_id}", tags=["analytics"])
def get_campaign(
    campaign_id: str,
    model: str = "linear",
    db: DatabaseHandle = Depends(database),
) -> dict[str, Any]:
    detail = services.campaign_detail(db.conn, campaign_id, model)
    if detail is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    detail["run_id"] = db.run.run_id
    return detail


@app.get("/api/channels", tags=["analytics"])
def get_channels(
    model: str = "linear",
    db: DatabaseHandle = Depends(database),
) -> dict[str, Any]:
    return {
        "items": services.list_channel_options(db.conn, model),
        "model": model,
        "run_id": db.run.run_id,
    }


@app.get("/api/attribution/compare", tags=["attribution"])
def compare_attribution(
    model_a: str = "first_touch",
    model_b: str = "last_touch",
    limit: int = Query(default=15, ge=1, le=100),
    db: DatabaseHandle = Depends(database),
) -> dict[str, Any]:
    try:
        data = services.compare_models(db.conn, model_a, model_b, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data["run_id"] = db.run.run_id
    return data


@app.get("/api/opportunities/{opportunity_id}/journey", tags=["journeys"])
def get_opportunity_journey(
    opportunity_id: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    run = resolve_run(run_id)
    conn = connect(run)
    try:
        lookback = int(run.manifest.get("config", {}).get("lookback_days", 90))
        payload = services.journey(conn, opportunity_id, lookback)
        if payload is None:
            raise HTTPException(status_code=404, detail="Opportunity not found.")
        payload["run_id"] = run.run_id
        return payload
    finally:
        conn.close()


@app.get("/api/demo/journey", tags=["journeys"])
def get_sample_journey(run_id: str | None = None) -> dict[str, Any]:
    run = resolve_run(run_id)
    conn = connect(run)
    try:
        lookback = int(run.manifest.get("config", {}).get("lookback_days", 90))
        payload = services.sample_journey(conn, lookback)
        if payload is None:
            raise HTTPException(status_code=404, detail="No recognized conversion is available.")
        payload["run_id"] = run.run_id
        return payload
    finally:
        conn.close()


@app.get("/api/journeys/{reference}", tags=["journeys"])
def get_journey(reference: str, run_id: str | None = None) -> dict[str, Any]:
    run = resolve_run(run_id)
    conn = connect(run)
    try:
        lookback = int(run.manifest.get("config", {}).get("lookback_days", 90))
        payload = services.journey(conn, reference, lookback)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail="No journey found for that opportunity, order or contact identifier.",
            )
        payload["run_id"] = run.run_id
        return payload
    finally:
        conn.close()


@app.get("/api/exceptions", tags=["data-quality"])
def get_exceptions(
    severity: str | None = None,
    issue_type: str | None = None,
    split: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: DatabaseHandle = Depends(database),
) -> dict[str, Any]:
    data = services.list_exceptions(
        db.conn,
        severity=severity,
        issue_type=issue_type,
        split=split,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )
    data["run_id"] = db.run.run_id
    return data


@app.get("/api/exceptions/{issue_id}", tags=["data-quality"])
def get_exception(issue_id: str, db: DatabaseHandle = Depends(database)) -> dict[str, Any]:
    detail = services.exception_detail(db.conn, issue_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Exception not found.")
    detail["run_id"] = db.run.run_id
    return detail


@app.get("/api/validation/report", tags=["validation"])
def get_validation_report(
    run_id: str | None = None,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    run = resolve_run(run_id)
    report = read_json(run.run_dir / "validation_report.json")
    checks = report.get("checks", [])
    if status:
        checks = [check for check in checks if check["status"] == status.upper()]
    if category:
        checks = [check for check in checks if check["category"] == category.upper()]
    if search:
        needle = search.lower()
        checks = [
            check
            for check in checks
            if needle
            in (
                f"{check['check_id']} {check['rule_id']} {check['description']} "
                f"{check.get('message', '')}"
            ).lower()
        ]
    return {
        "run_id": run.run_id,
        "summary": report.get("summary"),
        "checks": checks,
        "total_checks": len(report.get("checks", [])),
    }


@app.get("/api/evaluation", tags=["validation"])
def get_evaluation(run_id: str | None = None) -> dict[str, Any]:
    run = resolve_run(run_id)
    path = run.run_dir / "evaluation.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Evaluation artifact not found.")
    evaluation = read_json(path)
    evaluation["run_id"] = run.run_id
    return evaluation


def _report_response(report: reports.Report, export_format: str) -> Response:
    payload, content_type, filename = exports.build_report_export(
        export_format,
        context=report.context,
        sheets=report.sheets,
        summary_rows=report.summary_rows,
        pdf_spec=report.pdf_spec,
        json_primary=report.json_primary,
    )
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/exports/overview", tags=["exports"])
def export_overview(
    format: str = Query(default="csv", pattern="^(csv|json|xlsx|pdf)$"),
    db: DatabaseHandle = Depends(database),
) -> Response:
    """Executive overview: KPI summary plus monthly, channel and model sheets."""

    return _report_response(reports.overview_report(db.run), format)


@app.get("/api/exports/campaign/{campaign_id}", tags=["exports"])
def export_campaign(
    campaign_id: str,
    format: str = Query(default="csv", pattern="^(csv|json|xlsx|pdf)$"),
    model: str = Query(default="linear"),
    db: DatabaseHandle = Depends(database),
) -> Response:
    """One campaign under one attribution model.

    The campaign scope is part of the endpoint path, so another campaign's
    revenue or spend can never be included by accident.
    """

    model = model if model in MODELS else "linear"
    report = reports.campaign_report(db.run, campaign_id, model)
    if report is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return _report_response(report, format)


@app.get("/api/exports/cost-records", tags=["exports"])
def export_cost_records(
    campaign_id: str,
    format: str = Query(default="csv", pattern="^(csv|json|xlsx|pdf)$"),
    model: str = Query(default="linear"),
    db: DatabaseHandle = Depends(database),
) -> Response:
    """Every cost record linked to one campaign, with its own total."""

    model = model if model in MODELS else "linear"
    report = reports.cost_records_report(db.run, campaign_id, model)
    if report is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return _report_response(report, format)


@app.get("/api/exports/exceptions", tags=["exports"])
def export_exceptions(
    format: str = Query(default="csv", pattern="^(csv|json|xlsx|pdf)$"),
    severity: str | None = None,
    issue_type: str | None = None,
    split: str | None = None,
    status: str | None = None,
    search: str | None = None,
    db: DatabaseHandle = Depends(database),
) -> Response:
    """All exceptions matching the active queue filters - never only the page."""

    report = reports.exceptions_report(
        db.run,
        severity=severity,
        issue_type=issue_type,
        split=split,
        status=status,
        search=search,
    )
    return _report_response(report, format)


@app.get("/api/exports/validation", tags=["exports"])
def export_validation(
    format: str = Query(default="csv", pattern="^(csv|json|xlsx|pdf)$"),
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    db: DatabaseHandle = Depends(database),
) -> Response:
    """Validation checks matching the active filters, including expected warnings."""

    report = reports.validation_report(
        db.run,
        status=status,
        category=category,
        search=search,
    )
    return _report_response(report, format)


@app.get("/api/exports/evaluation", tags=["exports"])
def export_evaluation(
    format: str = Query(default="json", pattern="^(csv|json|xlsx|pdf)$"),
    db: DatabaseHandle = Depends(database),
) -> Response:
    """Labelled evaluation artifact.

    This is the only download that carries ground-truth label rows. Its context,
    summary and PDF banner say so explicitly.
    """

    return _report_response(reports.evaluation_report(db.run), format)


@app.get("/api/exports/evidence/{issue_id}", tags=["exports"])
def export_evidence(
    issue_id: str,
    format: str = Query(default="csv", pattern="^(csv|json|xlsx|pdf)$"),
    db: DatabaseHandle = Depends(database),
) -> Response:
    """One issue's evidence packet, related records and disposition state."""

    report = reports.evidence_report(db.run, issue_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Exception not found.")
    return _report_response(report, format)


@app.get("/api/exports/journey/{reference}", tags=["exports"])
def export_journey(
    reference: str,
    format: str = Query(default="csv", pattern="^(csv|json|xlsx|pdf)$"),
    db: DatabaseHandle = Depends(database),
) -> Response:
    """Every candidate touchpoint, allocation and exclusion for one conversion."""

    lookback = int(db.run.manifest.get("config", {}).get("lookback_days", 90))
    report = reports.journey_report(db.run, reference, lookback)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No journey found for that opportunity, order or contact identifier.",
        )
    return _report_response(report, format)


@app.get("/api/exports/run/{run_id}", tags=["exports"])
def export_run(
    run_id: str,
    format: str = Query(default="json", pattern="^(json|csv|xlsx|pdf|sql|zip)$"),
) -> Response:
    """Run manifest export, plus portable SQL and ZIP artifact bundles."""

    run = resolve_run(run_id)
    if format == "zip":
        filename = f"run-bundle-{run.run_id}.zip"
        return Response(
            content=reports.run_bundle_bytes(run),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if format == "sql":
        export_dir = reports.temp_export_dir("sql")
        archive = reports.write_sql_package(run, export_dir)
        return FileResponse(
            archive,
            media_type="application/zip",
            filename=archive.name,
            background=BackgroundTask(reports.cleanup_export_dir, export_dir),
        )
    return _report_response(reports.run_report(run), format)


@app.get("/api/exports/{dataset_name}", tags=["exports"])
def export_dataset(dataset_name: str, run_id: str | None = None) -> FileResponse:
    run = resolve_run(run_id)
    if dataset_name not in ALL_TABLES:
        raise HTTPException(status_code=404, detail="Unknown export.")
    path = run.run_dir / f"{dataset_name}.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export file not found.")
    return FileResponse(
        path,
        media_type="text/csv",
        filename=f"{run.run_id}_{dataset_name}.csv",
    )


_frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles

    _assets = _frontend_dist / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=_assets), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        if full_path:
            candidate = (_frontend_dist / full_path).resolve()
            if candidate.is_relative_to(_frontend_dist.resolve()) and candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(_frontend_dist / "index.html")

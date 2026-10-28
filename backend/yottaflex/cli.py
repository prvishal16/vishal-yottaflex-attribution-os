"""Command line interface for data generation, validation and serving."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from yottaflex.config import DEFAULT_SEED, PROFILES, RunConfig, Settings
from yottaflex.generator import generate, rerun_and_compare
from yottaflex.util import read_json


def _progress(message: str) -> None:
    print(f"[yottaflex] {message}", flush=True)


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def command_generate(args: argparse.Namespace) -> int:
    config = RunConfig(profile=args.profile, seed=args.seed)
    manifest = generate(config, progress=_progress, strict_validation=args.strict)
    print(
        f"\nRun {manifest['run_id']} complete | profile={manifest['profile']} "
        f"campaigns={manifest['counts']['campaigns']} contacts={manifest['counts']['contacts']} "
        f"touchpoints={manifest['counts']['touchpoints']} opportunities={manifest['counts']['opportunities']}"
    )
    print(
        f"Attributed revenue (linear) EUR {manifest['metrics']['attributed_revenue']} | "
        f"ROI {manifest['metrics']['roi_pct'] or 'unavailable'}% | "
        f"exceptions {manifest['detection']['issues']} | "
        f"validation {manifest['validation']['overall_status']} | "
        f"precision {manifest['evaluation']['totals']['precision_pct']}%"
    )
    print(f"Manifest: {Settings.from_env().manifest_path(manifest['run_id'])}")
    return 0 if manifest["validation"]["overall_status"] != "FAILED" else 1


def command_validate(args: argparse.Namespace) -> int:
    import duckdb

    from yottaflex.generator import refresh_validation

    settings = Settings.from_env()
    run_id = args.run_id
    if not run_id:
        active = read_json(settings.active_run_path())["run_id"] if settings.active_run_path().exists() else None
        run_id = active
    if not run_id:
        print("No run available. Generate a dataset first.", file=sys.stderr)
        return 2
    run_dir = settings.run_dir(run_id)
    manifest_path = settings.manifest_path(run_id)
    if not run_dir.exists() or not manifest_path.exists():
        print(f"Run '{run_id}' not found.", file=sys.stderr)
        return 2
    manifest = read_json(manifest_path)
    config = RunConfig(profile=manifest["profile"], seed=manifest["seed"])
    conn = duckdb.connect(str(run_dir / "analytics.duckdb"))
    try:
        summary = refresh_validation(conn, config, settings)
    finally:
        conn.close()
    print(json.dumps(summary["totals"], indent=2))
    print(f"Validation status: {summary['overall_status']}")
    return 0 if summary["overall_status"] != "FAILED" else 1


def command_verify(args: argparse.Namespace) -> int:
    config = RunConfig(profile=args.profile, seed=args.seed)
    result = rerun_and_compare(config, progress=_progress)
    _print_json(result)
    print("REPRODUCIBLE" if result["reproducible"] else "NON-DETERMINISTIC")
    return 0 if result["reproducible"] else 1


def command_info(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    active_path = settings.active_run_path()
    active = read_json(active_path) if active_path.exists() else None
    index_path = settings.run_index_path()
    index = read_json(index_path) if index_path.exists() else {"runs": []}
    _print_json(
        {
            "project_root": str(settings.data_root.parent),
            "data_root": str(settings.data_root),
            "ground_truth_root": str(settings.ground_truth_root),
            "reports_root": str(settings.reports_root),
            "profiles": list(PROFILES),
            "active_run": active,
            "runs": index.get("runs", []),
            "environment_overrides": {
                "YOTTAFLEX_DATA_ROOT": "data directory",
                "YOTTAFLEX_GROUND_TRUTH_ROOT": "ground truth directory",
                "YOTTAFLEX_REPORTS_ROOT": "reports directory",
            },
        }
    )
    return 0


def command_runs(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    index_path = settings.run_index_path()
    index = read_json(index_path) if index_path.exists() else {"runs": []}
    active_path = settings.active_run_path()
    active = read_json(active_path) if active_path.exists() else None
    _print_json({"active_run_id": (active or {}).get("run_id"), "runs": index.get("runs", [])})
    return 0


def command_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "yottaflex.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yottaflex",
        description="Deterministic marketing attribution, ROI and data-quality platform.",
    )
    parser.add_argument("--version", action="version", version="yottaflex 1.0.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate a dataset and run the full pipeline.")
    generate_parser.add_argument("--profile", choices=sorted(PROFILES), default="small")
    generate_parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    generate_parser.add_argument("--strict", action="store_true", help="Treat validation warnings as failures.")
    generate_parser.set_defaults(handler=command_generate)

    validate_parser = subparsers.add_parser("validate", help="Re-run validation on an existing dataset.")
    validate_parser.add_argument("--run-id", default=None)
    validate_parser.set_defaults(handler=command_validate)

    verify_parser = subparsers.add_parser(
        "verify", help="Generate twice and prove canonical reproducibility."
    )
    verify_parser.add_argument("--profile", choices=sorted(PROFILES), default="small")
    verify_parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    verify_parser.set_defaults(handler=command_verify)

    info_parser = subparsers.add_parser("info", help="Show configured paths and active run.")
    info_parser.set_defaults(handler=command_info)

    runs_parser = subparsers.add_parser("runs", help="List generated runs.")
    runs_parser.set_defaults(handler=command_runs)

    serve_parser = subparsers.add_parser("serve", help="Run the FastAPI backend.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.set_defaults(handler=command_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

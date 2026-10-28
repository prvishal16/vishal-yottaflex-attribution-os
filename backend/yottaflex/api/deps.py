"""API dependencies: run selection, database access and safe serialization."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
from fastapi import HTTPException

from yottaflex.config import Settings
from yottaflex.util import read_json


@dataclass(frozen=True)
class RunContext:
    settings: Settings
    run_id: str
    run_dir: Path
    manifest: dict[str, Any]

    @property
    def db_path(self) -> Path:
        return self.run_dir / "analytics.duckdb"


def active_run_id(settings: Settings) -> str | None:
    active_path = settings.active_run_path()
    if active_path.exists():
        active = read_json(active_path)
        if active.get("run_id"):
            return str(active["run_id"])
    index_path = settings.run_index_path()
    if index_path.exists():
        runs = read_json(index_path).get("runs", [])
        if runs:
            return str(runs[-1].get("run_id"))
    return None


def resolve_run(run_id: str | None, settings: Settings | None = None) -> RunContext:
    settings = settings or Settings.from_env()
    selected = run_id or active_run_id(settings)
    if not selected:
        raise HTTPException(status_code=404, detail="No dataset has been generated yet.")
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in selected):
        raise HTTPException(status_code=400, detail="Invalid run_id.")
    run_dir = settings.run_dir(selected)
    manifest_path = settings.manifest_path(selected)
    if not run_dir.exists() or not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{selected}' was not found.")
    manifest = read_json(manifest_path)
    if not (run_dir / "analytics.duckdb").exists():
        raise HTTPException(status_code=409, detail=f"Run '{selected}' has no analytical database.")
    return RunContext(settings=settings, run_id=selected, run_dir=run_dir, manifest=manifest)


def connect(run: RunContext) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(run.db_path), read_only=True)


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {path.name}")
    return read_json(path)


def rows(conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params or [])
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def one(conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    result = rows(conn, sql, params)
    return result[0] if result else None


def number(value: Any, digits: int = 2) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def integer(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes"}


def money(value: Any) -> float | None:
    """Serialize money without turning an unknown value into zero."""

    return number(value)


def split_evidence(value: Any) -> dict[str, Any] | str:
    if not value:
        return {}
    try:
        import json

        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (TypeError, ValueError):
        return str(value)


def safe_records(records: list[dict[str, Any]], numeric: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    numeric_set = set(numeric)
    output: list[dict[str, Any]] = []
    for record in records:
        cleaned: dict[str, Any] = {}
        for key, value in record.items():
            if key in numeric_set:
                cleaned[key] = number(value)
            elif isinstance(value, Decimal):
                cleaned[key] = float(value)
            else:
                cleaned[key] = value
        output.append(cleaned)
    return output

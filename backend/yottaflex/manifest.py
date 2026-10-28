"""Dataset manifests, canonical table hashes and reproducibility comparisons."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from yottaflex.tables import ALL_TABLES, NONDETERMINISTIC_COLUMNS
from yottaflex.util import read_csv_text, read_json, sha256_file, write_json


def canonical_table_hash(table: str, path: Path) -> dict[str, Any]:
    spec = ALL_TABLES[table]
    excluded = set(NONDETERMINISTIC_COLUMNS.get(table, ()))
    columns = [column for column in spec.columns if column not in excluded]
    digest = hashlib.sha256()
    rows = read_csv_text(path)
    lines: list[str] = []
    for row in rows:
        lines.append(
            "\u001f".join(str(row.get(column, "")) for column in columns)
        )
    lines.sort()
    for line in lines:
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return {
        "table": table,
        "rows": len(rows),
        "sha256": digest.hexdigest(),
        "excluded_columns": sorted(excluded),
    }


def table_hashes(run_dir: Path) -> dict[str, dict[str, Any]]:
    hashes: dict[str, dict[str, Any]] = {}
    for table, spec in ALL_TABLES.items():
        path = run_dir / f"{spec.name}.csv"
        if path.exists():
            hashes[table] = canonical_table_hash(table, path)
    return hashes


def combined_hash(hashes: dict[str, dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for table in sorted(hashes):
        digest.update(table.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(hashes[table]["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def file_hashes(run_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path in sorted(run_dir.glob("*.csv")):
        result[path.name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    return result


def compare_manifests(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_hashes = left.get("table_hashes", {})
    right_hashes = right.get("table_hashes", {})
    differences = []
    for table in sorted(set(left_hashes) | set(right_hashes)):
        left_hash = left_hashes.get(table, {}).get("sha256")
        right_hash = right_hashes.get(table, {}).get("sha256")
        if left_hash != right_hash:
            differences.append(
                {
                    "table": table,
                    "left_sha256": left_hash,
                    "right_sha256": right_hash,
                    "left_rows": left_hashes.get(table, {}).get("rows"),
                    "right_rows": right_hashes.get(table, {}).get("rows"),
                }
            )
    return {
        "reproducible": not differences,
        "left_run": left.get("run_id"),
        "right_run": right.get("run_id"),
        "left_combined_hash": left.get("combined_hash"),
        "right_combined_hash": right.get("combined_hash"),
        "differences": differences,
        "excluded_nondeterministic_columns": NONDETERMINISTIC_COLUMNS,
    }


def load_manifest(settings_manifests: Path, run_id: str) -> dict[str, Any] | None:
    path = settings_manifests / f"{run_id}.json"
    if not path.exists():
        return None
    return read_json(path)


def write_manifest(manifests_root: Path, run_id: str, manifest: dict[str, Any]) -> Path:
    manifests_root.mkdir(parents=True, exist_ok=True)
    path = manifests_root / f"{run_id}.json"
    write_json(path, manifest)
    active_path = manifests_root / "active_run.json"
    write_json(
        active_path,
        {
            "run_id": run_id,
            "profile": manifest.get("profile"),
            "seed": manifest.get("seed"),
            "manifest_path": str(path),
            "updated_at": manifest.get("generated_at"),
        },
    )
    index_path = manifests_root / "index.json"
    index = read_json(index_path) if index_path.exists() else {"runs": []}
    runs = [item for item in index.get("runs", []) if item.get("run_id") != run_id]
    runs.append(
        {
            "run_id": run_id,
            "profile": manifest.get("profile"),
            "seed": manifest.get("seed"),
            "generated_at": manifest.get("generated_at"),
            "combined_hash": manifest.get("combined_hash"),
            "status": manifest.get("status"),
            "counts": manifest.get("counts", {}),
            "campaigns": manifest.get("counts", {}).get("campaigns"),
            "contacts": manifest.get("counts", {}).get("contacts"),
            "touchpoints": manifest.get("counts", {}).get("touchpoints"),
            "opportunities": manifest.get("counts", {}).get("opportunities"),
            "attributed_revenue": manifest.get("metrics", {}).get("attributed_revenue"),
            "issues": manifest.get("detection", {}).get("issues"),
        }
    )
    runs.sort(key=lambda item: (str(item.get("generated_at") or ""), str(item.get("run_id") or "")))
    write_json(index_path, {"runs": runs})
    return path

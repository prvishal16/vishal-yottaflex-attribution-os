"""Shared deterministic helpers: IDs, timestamps, CSV serialization and hashing."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

UTC = UTC


class IdSequence:
    """Deterministic zero-padded identifier generator."""

    def __init__(self, prefix: str, year: int | None = 2026, width: int = 6) -> None:
        self.prefix = prefix
        self.year = year
        self.width = width
        self._value = 0

    def next(self) -> str:
        self._value += 1
        body = str(self._value).zfill(self.width)
        if self.year is None:
            return f"{self.prefix}-{body}"
        return f"{self.prefix}-{self.year}-{body}"

    @property
    def count(self) -> int:
        return self._value


def iso(dt: datetime) -> str:
    """Serialize a naive UTC datetime in canonical ISO-8601 form."""

    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.replace(microsecond=0).isoformat() + "Z"


def parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1]
    return datetime.fromisoformat(text)


def iso_date(value: datetime) -> str:
    return value.date().isoformat()


def money(value: Decimal | str | int | float) -> Decimal:
    """Quantize an amount to two decimal places using decimal arithmetic."""

    return Decimal(str(value)).quantize(Decimal("0.01"))


def decimal_str(value: Decimal | str | int | float, places: int = 2) -> str:
    quantum = Decimal(1).scaleb(-places)
    return str(Decimal(str(value)).quantize(quantum))


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


def write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    sort_key: Sequence[str] | None = None,
) -> int:
    """Write deterministic CSV: fixed column order, LF newlines, sorted rows."""

    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = [dict(row) for row in rows]
    if sort_key:
        materialized.sort(key=lambda row: tuple(str(row.get(col, "")) for col in sort_key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in materialized:
            writer.writerow({col: _csv_value(row.get(col)) for col in columns})
    return len(materialized)


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return iso(value)
    return value


def read_csv_text(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ndjson(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True)
        handle.write("\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def chunked(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]

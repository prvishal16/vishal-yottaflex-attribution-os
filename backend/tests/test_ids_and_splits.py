from datetime import date

import pytest
from yottaflex.config import RunConfig, split_for_date, split_for_timestamp
from yottaflex.util import IdSequence, iso, parse_iso, write_csv


def test_id_sequences_are_zero_padded_and_include_year() -> None:
    sequence = IdSequence("ATTR", year=2026)
    assert sequence.next() == "ATTR-2026-000001"
    assert sequence.next() == "ATTR-2026-000002"
    anonymous = IdSequence("ANON", year=None, width=8)
    assert anonymous.next() == "ANON-00000001"


def test_run_id_is_profile_and_seed() -> None:
    assert RunConfig("small", 42).run_id == "small-42"


def test_unknown_profile_raises() -> None:
    with pytest.raises(ValueError):
        _ = RunConfig("gigantic").spec


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2025, 8, 31), "train"),
        (date(2025, 9, 1), "train"),
        (date(2026, 5, 31), "train"),
        (date(2026, 6, 1), "validation"),
        (date(2026, 7, 14), "validation"),
        (date(2026, 7, 15), "test"),
        (date(2026, 10, 1), "test"),
    ],
)
def test_chronological_split_boundaries(value: date, expected: str) -> None:
    assert split_for_date(value) == expected


def test_timestamp_split_uses_event_date() -> None:
    assert split_for_timestamp(parse_iso("2026-07-15T00:00:01Z")) == "test"


def test_iso_round_trip_is_utc_second_precision() -> None:
    value = parse_iso("2026-01-02T03:04:05Z")
    assert iso(value) == "2026-01-02T03:04:05Z"


def test_write_csv_is_deterministic_and_sorted(tmp_path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    rows = [{"b": "2", "a": "z"}, {"b": "1", "a": "y"}]
    write_csv(first, ("a", "b"), rows, sort_key=("b",))
    write_csv(second, ("a", "b"), list(reversed(rows)), sort_key=("b",))
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().splitlines()[0] == b"a,b"

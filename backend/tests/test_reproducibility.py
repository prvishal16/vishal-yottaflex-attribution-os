from __future__ import annotations

from pathlib import Path

from yottaflex.generator import generate, rerun_and_compare
from yottaflex.manifest import combined_hash, compare_manifests, table_hashes


def test_same_seed_reproduces_identical_canonical_tables(bundle: dict) -> None:
    settings = bundle["settings"]
    run_dir: Path = bundle["run_dir"]
    first_manifest = bundle["manifest"]
    first_hashes = first_manifest["table_hashes"]
    first_combined = first_manifest["combined_hash"]

    second_manifest = generate(bundle["config"], settings=settings)
    second_hashes = table_hashes(run_dir)
    second_combined = combined_hash(second_hashes)

    assert first_combined == second_combined
    assert first_hashes == second_hashes
    comparison = compare_manifests(first_manifest, second_manifest)
    assert comparison["reproducible"] is True
    assert comparison["differences"] == []


def test_verify_never_mutates_the_active_run(bundle: dict) -> None:
    manifest_path = bundle["settings"].manifest_path(bundle["config"].run_id)
    before_manifest = manifest_path.read_bytes()
    before_active = bundle["settings"].active_run_path().read_bytes()

    result = rerun_and_compare(bundle["config"], settings=bundle["settings"])

    assert result["reproducible"] is True
    assert result["differences"] == []
    assert manifest_path.read_bytes() == before_manifest
    assert bundle["settings"].active_run_path().read_bytes() == before_active


def test_different_seed_changes_business_data(bundle: dict, tmp_path: Path) -> None:
    from yottaflex.config import RunConfig, Settings

    base = bundle["settings"]
    alt_settings = Settings(
        data_root=tmp_path / "data",
        ground_truth_root=tmp_path / "ground_truth",
        reports_root=tmp_path / "reports",
    )
    other = generate(RunConfig(profile="small", seed=7), settings=alt_settings)
    assert other["combined_hash"] != bundle["manifest"]["combined_hash"]
    assert other["run_id"] == "small-7"
    assert base.run_dir("small-7").exists() is False

from __future__ import annotations

import os
from pathlib import Path

import pytest
from yottaflex.config import RunConfig, Settings
from yottaflex.generator import generate


@pytest.fixture(scope="session")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("yottaflex-e2e")
    settings = Settings(
        data_root=root / "data",
        ground_truth_root=root / "ground_truth",
        reports_root=root / "reports",
    )
    os.environ["YOTTAFLEX_DATA_ROOT"] = str(settings.data_root)
    os.environ["YOTTAFLEX_GROUND_TRUTH_ROOT"] = str(settings.ground_truth_root)
    os.environ["YOTTAFLEX_REPORTS_ROOT"] = str(settings.reports_root)
    config = RunConfig(profile="small")
    manifest = generate(config, settings=settings)
    return {
        "root": root,
        "settings": settings,
        "config": config,
        "manifest": manifest,
        "run_dir": settings.run_dir(config.run_id),
        "ground_truth_dir": settings.ground_truth_dir(config.run_id),
    }


@pytest.fixture(scope="session")
def client(bundle: dict):
    from fastapi.testclient import TestClient
    from yottaflex.api.main import app

    return TestClient(app)


@pytest.fixture(scope="session")
def run_paths(bundle: dict) -> dict[str, Path]:
    run_dir = bundle["run_dir"]
    return {
        "run_dir": run_dir,
        "db": run_dir / "analytics.duckdb",
        "exceptions": run_dir / "exceptions.csv",
        "labels": bundle["ground_truth_dir"] / "labels.csv",
        "manifest": bundle["settings"].manifest_path(bundle["config"].run_id),
    }

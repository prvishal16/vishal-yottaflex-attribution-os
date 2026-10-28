"""Detection-quality evaluation against the held-out ground-truth labels.

The evaluator is the only component that reads ground truth. Detection and
attribution code never do, so evaluation measures independent outcomes.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from yottaflex.config import ANOMALY_TYPES, RunConfig
from yottaflex.util import read_json, write_json


def _read_labels(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _records(value: str) -> set[str]:
    return {item for item in value.split("|") if item}


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator * 100 / denominator, 2)


def _ratio(numerator: int, denominator: int) -> str:
    value = _pct(numerator, denominator)
    return "" if value is None else f"{value:.2f}"


def _f1(precision: str, recall: str) -> str:
    if not precision or not recall:
        return ""
    p = float(precision)
    r = float(recall)
    if p + r == 0:
        return "0.00"
    return f"{(2 * p * r / (p + r)):.2f}"


def evaluate_detection(
    config: RunConfig,
    run_id: str,
    run_dir: Path,
    ground_truth_dir: Path,
    reports_root: Path,
) -> dict[str, Any]:
    labels_path = ground_truth_dir / "labels.csv"
    labels = _read_labels(labels_path)
    exceptions_path = run_dir / "exceptions.csv"
    detections = _read_labels(exceptions_path)
    detection_by_type: dict[str, list[dict[str, str]]] = defaultdict(list)
    for detection in detections:
        detection_by_type[detection["issue_type"]].append(detection)
    labels_by_type: dict[str, list[dict[str, str]]] = defaultdict(list)
    for label in labels:
        labels_by_type[label["issue_type"]].append(label)

    used_detections: set[str] = set()
    matches: list[dict[str, Any]] = []
    missed: list[dict[str, str]] = []
    tp_by_type: dict[str, int] = defaultdict(int)
    for issue_type in ANOMALY_TYPES:
        for label in sorted(labels_by_type.get(issue_type, []), key=lambda row: row["scenario_id"]):
            label_records = _records(label["record_ids"])
            matched: dict[str, str] | None = None
            for detection in sorted(detection_by_type.get(issue_type, []), key=lambda row: row["issue_id"]):
                if detection["issue_id"] in used_detections:
                    continue
                detection_records = _records(detection["affected_record_ids"]) | {
                    detection["primary_entity_id"]
                }
                if label_records & detection_records:
                    matched = detection
                    break
            if matched is None:
                missed.append(label)
                continue
            used_detections.add(matched["issue_id"])
            tp_by_type[issue_type] += 1
            matches.append(
                {
                    "scenario_id": label["scenario_id"],
                    "issue_type": issue_type,
                    "ground_truth_split": label["split"],
                    "detected_split": matched["split"],
                    "expected_record_ids": label["record_ids"],
                    "matched_issue_id": matched["issue_id"],
                    "matched_primary_entity_id": matched["primary_entity_id"],
                    "expected_severity": label["severity"],
                    "detected_severity": matched["severity"],
                    "severity_match": "true" if label["severity"] == matched["severity"] else "false",
                    "expected_disposition": label["expected_disposition"],
                    "detected_disposition": matched["suggested_disposition"],
                    "detection_rule_id": matched["detection_rule_id"],
                    "explanation": matched["explanation"],
                }
            )

    false_positives = [
        detection
        for detection in sorted(detections, key=lambda row: row["issue_id"])
        if detection["issue_id"] not in used_detections
    ]

    by_type: list[dict[str, Any]] = []
    total_tp = total_fp = total_fn = 0
    for issue_type in ANOMALY_TYPES:
        label_count = len(labels_by_type.get(issue_type, []))
        detection_count = len(detection_by_type.get(issue_type, []))
        tp = tp_by_type.get(issue_type, 0)
        fp = detection_count - tp
        fn = label_count - tp
        total_tp += tp
        total_fp += fp
        total_fn += fn
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        severity_hits = sum(
            1
            for match in matches
            if match["issue_type"] == issue_type and match["severity_match"] == "true"
        )
        by_type.append(
            {
                "issue_type": issue_type,
                "ground_truth": label_count,
                "detected": detection_count,
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "precision_pct": precision,
                "recall_pct": recall,
                "f1_pct": _f1(precision, recall),
                "severity_accuracy_pct": _ratio(severity_hits, tp),
            }
        )

    by_split: list[dict[str, Any]] = []
    for split in ("train", "validation", "test"):
        split_labels = [label for label in labels if label["split"] == split]
        split_tp = sum(1 for match in matches if match["ground_truth_split"] == split)
        split_detections = [item for item in detections if item["split"] == split]
        split_fp = sum(1 for item in false_positives if item["split"] == split)
        by_split.append(
            {
                "split": split,
                "ground_truth": len(split_labels),
                "detected": len(split_detections),
                "true_positives": split_tp,
                "false_positives": split_fp,
                "false_negatives": len(split_labels) - split_tp,
                "precision_pct": _ratio(split_tp, split_tp + split_fp),
                "recall_pct": _ratio(split_tp, len(split_labels)),
            }
        )

    total_detected = len(detections)
    total_labels = len(labels)
    precision = _ratio(total_tp, total_tp + total_fp)
    recall = _ratio(total_tp, total_tp + total_fn)
    severity_hits = sum(1 for match in matches if match["severity_match"] == "true")
    summary = {
        "run_id": run_id,
        "profile": config.profile,
        "seed": config.seed,
        "status": "COMPLETE" if labels else "NO_GROUND_TRUTH",
        "ground_truth": {
            "labels_path": str(labels_path),
            "labels": total_labels,
            "labels_in_analytical_tables": False,
            "label_source": "separate load, after detection",
        },
        "totals": {
            "ground_truth": total_labels,
            "detected": total_detected,
            "true_positives": total_tp,
            "false_positives": total_fp,
            "false_negatives": total_fn,
            "precision_pct": precision,
            "recall_pct": recall,
            "f1_pct": _f1(precision, recall),
            "severity_accuracy_pct": _ratio(severity_hits, total_tp),
        },
        "by_type": by_type,
        "by_split": by_split,
        "false_positive_issue_ids": [item["issue_id"] for item in false_positives],
        "missed_scenario_ids": [label["scenario_id"] for label in missed],
        "matches": matches,
        "missed": [
            {
                "scenario_id": label["scenario_id"],
                "issue_type": label["issue_type"],
                "split": label["split"],
                "record_ids": label["record_ids"],
                "notes": label["notes"],
            }
            for label in missed
        ],
        "false_positives": [
            {
                "issue_id": item["issue_id"],
                "issue_type": item["issue_type"],
                "primary_entity_id": item["primary_entity_id"],
                "split": item["split"],
                "explanation": item["explanation"],
            }
            for item in false_positives
        ],
    }
    write_json(run_dir / "evaluation.json", summary)
    reports_root.mkdir(parents=True, exist_ok=True)
    write_json(reports_root / f"evaluation_{run_id}.json", summary)
    return summary


def load_evaluation(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "evaluation.json"
    if not path.exists():
        return None
    return read_json(path)

# Ground Truth

This directory contains held-out anomaly labels, written only after the analytical dataset has been generated.

Each run has its own folder:

```text
ground_truth/<run_id>/
  labels.csv
  manifest.json
```

`labels.csv` records the fixture scenario, issue type, severity, affected records, split, expected disposition, and notes.

The detection pipeline never reads this directory. Only the evaluator consumes labels, after detection has already persisted its results. This boundary is required to keep precision, recall, and severity scoring honest.

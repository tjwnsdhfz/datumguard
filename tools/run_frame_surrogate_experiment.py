"""Run the research-only FrameGuard pooled ridge baseline experiment."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from datumguard.frame_dataset import (
    FrameDatasetSplit,
    FrameGraphDataset,
    RidgeBaselineResult,
    generate_frame_dataset,
    group_holdout_split,
    run_ridge_baseline,
    topology_counts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate exact-solver graph labels and evaluate a NumPy pooled ridge baseline. "
            "This experiment is not a GNN and is not production inference."
        )
    )
    parser.add_argument("--cases", type=int, default=90, help="Number of valid graph cases")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic generator seed")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Optional JSON summary path or output directory. When provided, a JSONL record "
            "file is written beside the summary. By default no files are written."
        ),
    )
    return parser


def experiment_summary(
    dataset: FrameGraphDataset,
    split: FrameDatasetSplit,
    baseline: RidgeBaselineResult,
) -> dict[str, Any]:
    return {
        "schema_version": "frame-surrogate-experiment-v1",
        "experiment_kind": "numpy_pooled_ridge_baseline_not_gnn",
        "dataset": {
            "seed": dataset.seed,
            "requested_cases": dataset.requested_cases,
            "valid_cases": len(dataset.records),
            "attempted_cases": dataset.attempted_cases,
            "excluded_singular": dataset.excluded_singular,
            "topology_groups": topology_counts(dataset.records),
        },
        "split": {
            "strategy": "topology_group_holdout",
            "train_count": len(split.train),
            "test_count": len(split.test),
            "train_groups": split.train_groups,
            "test_groups": split.test_groups,
            "leakage_group_count": split.leakage_group_count,
        },
        "label_provenance": {
            "solver_id": dataset.solver_id,
            "official_label_source": "deterministic_solve_frame",
            "learned_labels": False,
            "main_api_connected": False,
        },
        "baseline": baseline.model_dump(mode="json", exclude={"predictions"}),
        "claims": {
            "is_gnn": False,
            "is_production_inference": False,
            "is_safety_certification": False,
            "performance_threshold_enforced": False,
            "metrics_are_unclipped_observations": True,
        },
    }


def run_experiment(*, cases: int, seed: int) -> tuple[dict[str, Any], FrameGraphDataset]:
    dataset = generate_frame_dataset(cases=cases, seed=seed)
    split = group_holdout_split(dataset.records)
    baseline = run_ridge_baseline(split)
    return experiment_summary(dataset, split, baseline), dataset


def _output_paths(output: Path) -> tuple[Path, Path]:
    if output.suffix.lower() == ".json":
        return output, output.with_name(f"{output.stem}.records.jsonl")
    return output / "summary.json", output / "records.jsonl"


def write_outputs(
    output: Path,
    summary: dict[str, Any],
    dataset: FrameGraphDataset,
) -> tuple[Path, Path]:
    summary_path, records_path = _output_paths(output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    records_path.write_text(
        "".join(record.model_dump_json() + "\n" for record in dataset.records),
        encoding="utf-8",
    )
    return summary_path, records_path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary, dataset = run_experiment(cases=args.cases, seed=args.seed)
    if args.output is not None:
        summary_path, records_path = write_outputs(args.output, summary, dataset)
        summary["outputs"] = {
            "summary_json": str(summary_path),
            "records_jsonl": str(records_path),
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

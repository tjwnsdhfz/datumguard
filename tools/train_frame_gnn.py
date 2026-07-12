"""Train and compare FrameGuard GraphSAGE/GAT research ensembles."""

from __future__ import annotations

import argparse
import json
import platform
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch_geometric

from datumguard.frame_dataset import (
    _contract_to_record,
    generate_frame_dataset,
    generate_pipe_rack_contract,
    topology_counts,
)
from datumguard.frame_gnn import (
    build_graphsage_artifact,
    predict_members,
    topology_holdout_partitions,
    train_architecture_ensemble,
    write_json,
)
from datumguard.frame_surrogate import predict_frame_surrogate

ROOT = Path(__file__).resolve().parents[1]


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate exact-solver labels, compare GraphSAGE and GAT on a topology "
            "holdout, and export a NumPy-only GraphSAGE ensemble. Research only."
        )
    )
    parser.add_argument("--cases", type=int, default=120)
    parser.add_argument("--dataset-seed", type=int, default=20260712)
    parser.add_argument("--split-seed", type=int, default=314159)
    parser.add_argument("--model-seeds", type=int, nargs="+", default=[7, 17, 29])
    parser.add_argument("--epochs", type=int, default=160)
    parser.add_argument("--hidden-channels", type=int, default=32)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "models" / "frame-gnn",
    )
    parser.add_argument(
        "--package-artifact",
        type=Path,
        default=ROOT / "src" / "datumguard" / "data" / "frame_graphsage_ensemble_v1.json",
    )
    parser.add_argument(
        "--package-benchmark",
        type=Path,
        default=ROOT / "src" / "datumguard" / "data" / "frame_gnn_benchmark.json",
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.cases < 30:
        raise ValueError("at least 30 cases are required for the three-way benchmark")
    if len(set(args.model_seeds)) < 2:
        raise ValueError("at least two distinct model seeds are required")
    dataset = generate_frame_dataset(cases=args.cases, seed=args.dataset_seed)
    partitions = topology_holdout_partitions(
        dataset.records,
        split_seed=args.split_seed,
        test_group="pipe_rack_4_bay",
    )
    reports: dict[str, Any] = {}
    sage_members = None
    sage_stats = None
    for architecture in ("graphsage", "gat"):
        members, stats, report = train_architecture_ensemble(
            architecture,
            partitions,
            seeds=args.model_seeds,
            epochs=args.epochs,
            hidden_channels=args.hidden_channels,
        )
        reports[architecture] = report
        if architecture == "graphsage":
            sage_members = members
            sage_stats = stats
    if sage_members is None or sage_stats is None:
        raise RuntimeError("GraphSAGE training did not run")
    calibration = reports["graphsage"]["uncertainty_calibration"]
    portable = build_graphsage_artifact(
        sage_members,
        sage_stats,
        calibration,
        partitions.train,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    research_model_path = args.output_dir / "frame_graphsage_ensemble_v1.json"
    research_model_hash = write_json(research_model_path, portable)
    package_model_hash = write_json(args.package_artifact, portable)
    if research_model_hash != package_model_hash:
        raise RuntimeError("research and package model artifact hashes differ")
    parity_cases: list[dict[str, Any]] = []
    for bay_count in (2, 3, 4):
        contract = generate_pipe_rack_contract(bays=bay_count, seed=8100 + bay_count)
        record = _contract_to_record(
            contract,
            case_id=f"portable-parity-{bay_count}-bay",
            topology_group=f"pipe_rack_{bay_count}_bay",
        )
        pyg_prediction = np.mean(predict_members(sage_members, [record], sage_stats), axis=0)[0]
        portable_prediction = predict_frame_surrogate(contract, model_path=research_model_path)
        if (
            portable_prediction.max_displacement_mm is None
            or portable_prediction.max_utilization is None
        ):
            raise RuntimeError("portable inference did not return predictions")
        absolute_errors = [
            abs(portable_prediction.max_displacement_mm - float(pyg_prediction[0])),
            abs(portable_prediction.max_utilization - float(pyg_prediction[1])),
        ]
        if max(absolute_errors) > 1e-4:
            raise RuntimeError("NumPy and PyG GraphSAGE inference differ beyond tolerance")
        parity_cases.append(
            {
                "topology_group": record.topology_group,
                "portable_status": portable_prediction.status,
                "max_abs_error": max(absolute_errors),
            }
        )
    benchmark: dict[str, Any] = {
        "schema_version": "frame-gnn-benchmark-v1",
        "benchmark_kind": "frame_gnn_benchmark_v1",
        "experiment_kind": "pyg_topology_holdout_deep_ensemble",
        "dataset": {
            "seed": dataset.seed,
            "requested_cases": dataset.requested_cases,
            "attempted_cases": dataset.attempted_cases,
            "excluded_singular": dataset.excluded_singular,
            "topology_counts": topology_counts(dataset.records),
            "label_solver": dataset.solver_id,
        },
        "split": {
            "seed": args.split_seed,
            "strategy": "4_bay_topology_test_holdout_with_stratified_validation",
            "train_count": len(partitions.train),
            "validation_count": len(partitions.validation),
            "test_count": len(partitions.test),
            "train_groups": partitions.train_groups,
            "validation_groups": partitions.validation_groups,
            "test_groups": partitions.test_groups,
            "case_id_leakage": 0,
            "contract_hash_leakage": 0,
            "test_used_for_threshold_calibration": False,
        },
        "training": {
            "model_seeds": list(args.model_seeds),
            "epochs_cap": args.epochs,
            "hidden_channels": args.hidden_channels,
            "target_transform": "log1p_then_train_standardization",
            "device": "cpu",
        },
        "models": reports,
        "portable_artifact": {
            "selected_architecture": "graphsage",
            "selection_reason": (
                "deterministic NumPy parity and base-image portability; not a claim that "
                "GraphSAGE has the best test score"
            ),
            "research_path": _display_path(research_model_path),
            "package_path": _display_path(args.package_artifact),
            "sha256": research_model_hash,
            "torch_required_at_inference": False,
            "pyg_numpy_parity": {
                "tolerance": 1e-4,
                "cases": parity_cases,
                "all_within_tolerance": True,
            },
        },
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_geometric": torch_geometric.__version__,
        },
        "claims": {
            "is_gnn": True,
            "is_safety_certification": False,
            "is_authoritative_pass_source": False,
            "official_solver_remains_separate": True,
            "metrics_are_unclipped_observations": True,
        },
    }
    benchmark_hash = write_json(args.output_dir / "benchmark.json", benchmark)
    package_benchmark_hash = write_json(args.package_benchmark, benchmark)
    if benchmark_hash != package_benchmark_hash:
        raise RuntimeError("research and package benchmark hashes differ")
    return benchmark


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    benchmark = run(args)
    print(json.dumps(benchmark, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

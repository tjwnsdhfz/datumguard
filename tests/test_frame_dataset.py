from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from datumguard import frame_dataset
from datumguard.frame_dataset import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    SOLVER_ID,
    generate_frame_dataset,
    group_holdout_split,
    run_ridge_baseline,
)
from datumguard.frame_models import FrameAnalysisResult
from datumguard.frame_solver import solve_frame

ROOT = Path(__file__).resolve().parents[1]


def load_tool_module(name: str) -> ModuleType:
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load tool module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_generation_is_seed_deterministic() -> None:
    first = generate_frame_dataset(cases=9, seed=20260712)
    second = generate_frame_dataset(cases=9, seed=20260712)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.excluded_singular > 0
    assert first.attempted_cases == len(first.records) + first.excluded_singular


def test_graph_schema_shapes_and_values_are_finite() -> None:
    dataset = generate_frame_dataset(cases=9, seed=17)
    assert len({record.topology_group for record in dataset.records}) == 3
    for record in dataset.records:
        assert record.solver_id == SOLVER_ID
        assert record.contract_hash.startswith("sha256:")
        assert len(record.node_ids) == len(record.node_features)
        assert all(len(row) == len(NODE_FEATURE_NAMES) for row in record.node_features)
        source, target = record.edge_index
        assert len(source) == len(target) == len(record.edge_features)
        assert len(source) == len(record.edge_member_ids)
        assert all(len(row) == len(EDGE_FEATURE_NAMES) for row in record.edge_features)
        values = np.asarray([*record.node_features, *record.edge_features], dtype=object)
        flattened = [
            value
            for collection in (record.node_features, record.edge_features)
            for row in collection
            for value in row
        ]
        assert values.size > 0
        assert all(math.isfinite(value) for value in flattened)
        assert math.isfinite(record.targets.max_displacement_mm)
        assert math.isfinite(record.targets.max_utilization)
        assert record.targets.governing_member_id in record.edge_member_ids


def test_topology_group_holdout_has_zero_leakage() -> None:
    dataset = generate_frame_dataset(cases=12, seed=41)
    split = group_holdout_split(dataset.records, holdout_group="pipe_rack_3_bay")
    assert split.leakage_group_count == 0
    assert not (set(split.train_groups) & set(split.test_groups))
    assert split.test_groups == ["pipe_rack_3_bay"]
    assert all(record.topology_group == "pipe_rack_3_bay" for record in split.test)


def test_numpy_ridge_baseline_reports_unclipped_finite_metrics() -> None:
    dataset = generate_frame_dataset(cases=18, seed=73)
    split = group_holdout_split(dataset.records)
    baseline = run_ridge_baseline(split, alpha=1.0)
    assert baseline.is_gnn is False
    assert set(baseline.metrics) == {"max_displacement_mm", "max_utilization"}
    for metric in baseline.metrics.values():
        assert math.isfinite(metric.mae)
        assert math.isfinite(metric.r2)
        assert metric.mae >= 0
    assert len(baseline.predictions) == len(split.test)


def test_exact_solver_is_invoked_as_the_only_label_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    exact_solver = solve_frame

    def tracked_solver(contract: frame_dataset.StructuralFrameContract) -> FrameAnalysisResult:
        nonlocal calls
        calls += 1
        return exact_solver(contract)

    monkeypatch.setattr(frame_dataset, "solve_frame", tracked_solver)
    dataset = generate_frame_dataset(cases=6, seed=101)
    assert calls == dataset.attempted_cases
    assert dataset.solver_id == SOLVER_ID
    assert {record.solver_id for record in dataset.records} == {SOLVER_ID}


def test_cli_default_writes_nothing_and_output_writes_summary_and_jsonl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    experiment = load_tool_module("run_frame_surrogate_experiment")
    monkeypatch.chdir(tmp_path)
    assert experiment.main(["--cases", "6", "--seed", "11"]) == 0
    stdout_summary = json.loads(capsys.readouterr().out)
    assert stdout_summary["claims"]["is_gnn"] is False
    assert stdout_summary["label_provenance"]["main_api_connected"] is False
    assert list(tmp_path.iterdir()) == []

    output = tmp_path / "experiment.json"
    assert experiment.main(["--cases", "6", "--seed", "11", "--output", str(output)]) == 0
    capsys.readouterr()
    records_path = tmp_path / "experiment.records.jsonl"
    assert output.is_file()
    assert records_path.is_file()
    stored = json.loads(output.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
    assert stored["experiment_kind"] == "numpy_pooled_ridge_baseline_not_gnn"
    assert len(records) == 6

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from datumguard.frame_dataset import EDGE_FEATURE_NAMES, NODE_FEATURE_NAMES
from datumguard.frame_models import StructuralFrameContract
from datumguard.frame_service import validate_frame_contract
from datumguard.frame_surrogate import (
    DEFAULT_MODEL_PATH,
    MODEL_SCHEMA_VERSION,
    FrameSurrogateStatus,
    predict_frame_surrogate,
)

ROOT = Path(__file__).resolve().parents[1]


def contract() -> StructuralFrameContract:
    return StructuralFrameContract.model_validate_json(
        (ROOT / "fixtures" / "examples" / "frame_pipe_rack.json").read_text(encoding="utf-8")
    )


def linear(out_features: int, in_features: int, bias: float = 0.0) -> dict[str, Any]:
    return {
        "weight": [[0.0] * in_features for _ in range(out_features)],
        "bias": [bias] * out_features,
    }


def member(output_bias: tuple[float, float]) -> dict[str, Any]:
    hidden = 2
    return {
        "seed": int(output_bias[0] * 1000),
        "node_encoder": linear(hidden, len(NODE_FEATURE_NAMES), 0.1),
        "edge_encoder": linear(hidden, len(EDGE_FEATURE_NAMES), 0.1),
        "conv1": {
            "neighbour_weight": [[0.0] * hidden for _ in range(hidden)],
            "neighbour_bias": [0.1] * hidden,
            "root_weight": [[0.0] * hidden for _ in range(hidden)],
        },
        "conv2": {
            "neighbour_weight": [[0.0] * hidden for _ in range(hidden)],
            "neighbour_bias": [0.1] * hidden,
            "root_weight": [[0.0] * hidden for _ in range(hidden)],
        },
        "head_hidden": linear(hidden, hidden, 0.1),
        "head_output": {
            "weight": [[0.0] * hidden for _ in range(2)],
            "bias": list(output_bias),
        },
    }


def artifact(*, threshold: float = 10.0, narrow_ood: bool = False) -> dict[str, Any]:
    lower = [-1e12] * len(NODE_FEATURE_NAMES)
    upper = [1e12] * len(NODE_FEATURE_NAMES)
    if narrow_ood:
        upper[0] = 1.0
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_id": "test_graphsage_ensemble",
        "architecture": "graphsage",
        "runtime": "numpy_graphsage_ensemble_v1",
        "target_transform": "log1p_then_standardize",
        "target_names": ["max_displacement_mm", "max_utilization"],
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "normalization": {
            "node_mean": [0.0] * len(NODE_FEATURE_NAMES),
            "node_scale": [1.0] * len(NODE_FEATURE_NAMES),
            "edge_mean": [0.0] * len(EDGE_FEATURE_NAMES),
            "edge_scale": [1.0] * len(EDGE_FEATURE_NAMES),
            "target_log_mean": [0.0, 0.0],
            "target_log_scale": [1.0, 1.0],
        },
        "uncertainty_calibration": {
            "source_partition": "validation_only",
            "relative_floors": [0.001, 0.00001],
            "relative_score_threshold": threshold,
            "conformal_multipliers": [2.0, 2.0],
        },
        "ood_bounds": {
            "source_partition": "training_only",
            "node_lower": lower,
            "node_upper": upper,
            "edge_lower": [-1e20] * len(EDGE_FEATURE_NAMES),
            "edge_upper": [1e20] * len(EDGE_FEATURE_NAMES),
            "counts": {"nodes": [1, 120], "directed_edges": [1, 480]},
        },
        "ensemble_members": [member((0.2, 0.1)), member((0.22, 0.11))],
        "claims": {
            "authoritative": False,
            "exact_solver_required": True,
            "safety_certification": False,
        },
    }


def write_artifact(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "model.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_numpy_inference_is_deterministic_and_never_authoritative(tmp_path: Path) -> None:
    model_path = write_artifact(tmp_path, artifact())
    first = predict_frame_surrogate(contract(), model_path=model_path)
    second = predict_frame_surrogate(contract(), model_path=model_path)
    assert first == second
    assert first.status == FrameSurrogateStatus.PREDICTED
    assert first.authoritative is False
    assert first.exact_solver_required is True
    assert first.model_hash and first.model_hash.startswith("sha256:")
    assert first.input_hash == validate_frame_contract(contract()).contract_hash
    assert first.max_displacement_mm is not None
    assert first.max_utilization is not None


def test_missing_or_invalid_model_fails_closed(tmp_path: Path) -> None:
    missing = predict_frame_surrogate(contract(), model_path=tmp_path / "missing.json")
    assert missing.status == FrameSurrogateStatus.REVIEW_REQUIRED
    assert missing.review_reasons == ["DG_FRAME_SURROGATE_MODEL_MISSING"]

    invalid = write_artifact(tmp_path, {"schema_version": "wrong"})
    rejected = predict_frame_surrogate(contract(), model_path=invalid)
    assert rejected.status == FrameSurrogateStatus.REVIEW_REQUIRED
    assert rejected.review_reasons == ["DG_FRAME_SURROGATE_MODEL_INVALID"]


def test_invalid_member_reference_fails_closed_before_inference(tmp_path: Path) -> None:
    payload = contract().model_dump(mode="json")
    payload["members"][0]["start_node_id"] = "UNKNOWN-NODE"
    invalid_contract = StructuralFrameContract.model_validate(payload)
    result = predict_frame_surrogate(
        invalid_contract, model_path=write_artifact(tmp_path, artifact())
    )
    assert result.status == FrameSurrogateStatus.REVIEW_REQUIRED
    assert result.review_reasons == ["DG_FRAME_SURROGATE_INVALID_INPUT"]
    assert result.max_displacement_mm is None


def test_high_uncertainty_is_review_required(tmp_path: Path) -> None:
    payload = artifact(threshold=1e-12)
    path = write_artifact(tmp_path, payload)
    result = predict_frame_surrogate(contract(), model_path=path)
    assert result.status == FrameSurrogateStatus.REVIEW_REQUIRED
    assert "DG_FRAME_SURROGATE_HIGH_UNCERTAINTY" in result.review_reasons
    assert result.max_displacement_mm is not None


def test_out_of_distribution_input_is_review_required(tmp_path: Path) -> None:
    path = write_artifact(tmp_path, artifact(narrow_ood=True))
    result = predict_frame_surrogate(contract(), model_path=path)
    assert result.status == FrameSurrogateStatus.REVIEW_REQUIRED
    assert result.review_reasons == ["DG_FRAME_SURROGATE_OOD"]
    assert any(reason.startswith("node.x_mm outside") for reason in result.ood_reasons)


def test_corrupt_feature_schema_is_review_required(tmp_path: Path) -> None:
    payload = deepcopy(artifact())
    payload["node_feature_names"] = ["wrong"]
    result = predict_frame_surrogate(contract(), model_path=write_artifact(tmp_path, payload))
    assert result.status == FrameSurrogateStatus.REVIEW_REQUIRED
    assert result.review_reasons == ["DG_FRAME_SURROGATE_MODEL_INVALID"]


def test_packaged_model_and_benchmark_are_available_to_base_runtime() -> None:
    benchmark_path = DEFAULT_MODEL_PATH.with_name("frame_gnn_benchmark.json")
    assert DEFAULT_MODEL_PATH.is_file()
    assert benchmark_path.is_file()
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    assert benchmark["benchmark_kind"] == "frame_gnn_benchmark_v1"
    result = predict_frame_surrogate(contract())
    assert result.model_id == "frame_graphsage_ensemble_v1"
    assert result.status in {
        FrameSurrogateStatus.PREDICTED,
        FrameSurrogateStatus.REVIEW_REQUIRED,
    }
    assert result.authoritative is False

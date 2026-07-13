"""Lightweight, non-authoritative FrameGuard GraphSAGE ensemble inference.

This module intentionally depends only on NumPy and Pydantic.  PyTorch and
PyTorch Geometric are research/training dependencies and are not imported by
the deployed API process.
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from .frame_dataset import EDGE_FEATURE_NAMES, NODE_FEATURE_NAMES
from .frame_models import StructuralFrameContract
from .models import StrictModel

FloatArray = NDArray[np.float64]
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "data" / "frame_graphsage_ensemble_v1.json"
MODEL_SCHEMA_VERSION = "frame-gnn-numpy-ensemble-v1"
HASH_GRID_MM = 0.001


class FrameSurrogateStatus(StrEnum):
    PREDICTED = "PREDICTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class FrameSurrogateUncertainty(StrictModel):
    max_displacement_std_mm: float | None = Field(default=None, ge=0)
    max_utilization_std: float | None = Field(default=None, ge=0)
    relative_score: float | None = Field(default=None, ge=0)
    calibrated_threshold: float | None = Field(default=None, ge=0)
    displacement_interval_mm: tuple[float, float] | None = None
    utilization_interval: tuple[float, float] | None = None


class FrameSurrogateResult(StrictModel):
    status: FrameSurrogateStatus
    model_id: str | None = None
    model_hash: str | None = None
    input_hash: str
    max_displacement_mm: float | None = Field(default=None, ge=0)
    max_utilization: float | None = Field(default=None, ge=0)
    uncertainty: FrameSurrogateUncertainty = Field(default_factory=FrameSurrogateUncertainty)
    ood_reasons: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    authoritative: Literal[False] = False
    exact_solver_required: Literal[True] = True
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class _GraphInput(StrictModel):
    node_features: list[list[float]]
    edge_index: tuple[list[int], list[int]]
    edge_features: list[list[float]]


def _quantize(value: Any) -> Any:
    if isinstance(value, float):
        result = round(value / HASH_GRID_MM) * HASH_GRID_MM
        return 0.0 if abs(result) < HASH_GRID_MM / 2 else round(result, 9)
    if isinstance(value, list):
        items = [_quantize(item) for item in value]
        if all(isinstance(item, dict) and "id" in item for item in items):
            return sorted(items, key=lambda item: str(item["id"]))
        return items
    if isinstance(value, tuple):
        return [_quantize(item) for item in value]
    if isinstance(value, dict):
        return {key: _quantize(value[key]) for key in sorted(value)}
    return value


def _canonical_hash(contract: StructuralFrameContract) -> str:
    data = contract.model_dump(mode="json", exclude={"contract_hash", "intent_text"})
    if data.get("provenance") is None:
        data.pop("provenance", None)
    encoded = json.dumps(
        _quantize(data), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _fallback_input_hash(value: object) -> str:
    try:
        encoded = json.dumps(value, default=str, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError):
        encoded = repr(value).encode("utf-8", errors="replace")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _graph_from_contract(contract: StructuralFrameContract) -> _GraphInput:
    nodes = sorted(contract.nodes, key=lambda item: item.id)
    node_index = {node.id: index for index, node in enumerate(nodes)}
    restraint_by_node = {node.id: [False, False, False] for node in nodes}
    for support in contract.supports:
        if support.node_id not in restraint_by_node:
            raise ValueError(f"support {support.id} references unknown node {support.node_id}")
        restraint = restraint_by_node[support.node_id]
        restraint[0] = restraint[0] or support.ux
        restraint[1] = restraint[1] or support.uy
        restraint[2] = restraint[2] or support.rz
    load_by_node = {node.id: [0.0, 0.0, 0.0] for node in nodes}
    for load in contract.loads:
        if load.node_id not in load_by_node:
            raise ValueError(f"load {load.id} references unknown node {load.node_id}")
        combined = load_by_node[load.node_id]
        combined[0] += load.fx_n
        combined[1] += load.fy_n
        combined[2] += load.mz_nmm
    node_features = [
        [
            node.point[0],
            node.point[1],
            *(1.0 if value else 0.0 for value in restraint_by_node[node.id]),
            *load_by_node[node.id],
        ]
        for node in nodes
    ]
    source: list[int] = []
    target: list[int] = []
    edge_features: list[list[float]] = []
    for member in sorted(contract.members, key=lambda item: item.id):
        if member.start_node_id not in node_index or member.end_node_id not in node_index:
            raise ValueError(f"member {member.id} references an unknown node")
        start = nodes[node_index[member.start_node_id]]
        end = nodes[node_index[member.end_node_id]]
        dx = end.point[0] - start.point[0]
        dy = end.point[1] - start.point[1]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            raise ValueError(f"member {member.id} has zero length")
        allowable = member.allowable_stress_mpa or contract.limits.allowable_stress_mpa
        common = [
            length,
            dx / length,
            dy / length,
            member.area_mm2,
            member.inertia_mm4,
            member.elastic_modulus_mpa,
            member.section_depth_mm,
            allowable,
        ]
        source.extend([node_index[start.id], node_index[end.id]])
        target.extend([node_index[end.id], node_index[start.id]])
        edge_features.extend([common, [common[0], -common[1], -common[2], *common[3:]]])
    values = [value for row in [*node_features, *edge_features] for value in row]
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("frame graph contains non-finite or empty features")
    return _GraphInput(
        node_features=node_features,
        edge_index=(source, target),
        edge_features=edge_features,
    )


def _array(value: object, *, name: str, ndim: int | None = None) -> FloatArray:
    result = np.asarray(value, dtype=np.float64)
    if ndim is not None and result.ndim != ndim:
        raise ValueError(f"model field {name} must have {ndim} dimensions")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"model field {name} contains non-finite values")
    return result


def _linear(x: FloatArray, layer: dict[str, object]) -> FloatArray:
    weight = _array(layer["weight"], name="weight", ndim=2)
    bias = _array(layer["bias"], name="bias", ndim=1)
    return x @ weight.T + bias


def _relu(x: FloatArray) -> FloatArray:
    return np.maximum(x, 0.0)


def _mean_messages(
    values: FloatArray,
    source: NDArray[np.int64],
    target: NDArray[np.int64],
    node_count: int,
) -> FloatArray:
    result = np.zeros((node_count, values.shape[1]), dtype=np.float64)
    counts = np.zeros((node_count, 1), dtype=np.float64)
    np.add.at(result, target, values[source])
    np.add.at(counts[:, 0], target, 1.0)
    counts[counts == 0] = 1.0
    return result / counts


def _predict_member(
    graph: _GraphInput,
    member: dict[str, object],
    normalization: dict[str, object],
) -> FloatArray:
    nodes = _array(graph.node_features, name="node_features", ndim=2)
    edges = _array(graph.edge_features, name="edge_features", ndim=2)
    node_mean = _array(normalization["node_mean"], name="node_mean", ndim=1)
    node_scale = _array(normalization["node_scale"], name="node_scale", ndim=1)
    edge_mean = _array(normalization["edge_mean"], name="edge_mean", ndim=1)
    edge_scale = _array(normalization["edge_scale"], name="edge_scale", ndim=1)
    nodes = (nodes - node_mean) / node_scale
    edges = (edges - edge_mean) / edge_scale
    source = np.asarray(graph.edge_index[0], dtype=np.int64)
    target = np.asarray(graph.edge_index[1], dtype=np.int64)

    node_encoded = _linear(nodes, cast(dict[str, object], member["node_encoder"]))
    edge_encoded = _relu(_linear(edges, cast(dict[str, object], member["edge_encoder"])))
    aggregated_edges = np.zeros_like(node_encoded)
    counts = np.zeros((nodes.shape[0], 1), dtype=np.float64)
    np.add.at(aggregated_edges, target, edge_encoded)
    np.add.at(counts[:, 0], target, 1.0)
    counts[counts == 0] = 1.0
    hidden = _relu(node_encoded + aggregated_edges / counts)
    for key in ("conv1", "conv2"):
        layer = cast(dict[str, object], member[key])
        neighbour = _mean_messages(hidden, source, target, nodes.shape[0])
        neighbour_weight = _array(layer["neighbour_weight"], name=f"{key}.neighbour_weight", ndim=2)
        neighbour_bias = _array(layer["neighbour_bias"], name=f"{key}.neighbour_bias", ndim=1)
        root_weight = _array(layer["root_weight"], name=f"{key}.root_weight", ndim=2)
        hidden = _relu(neighbour @ neighbour_weight.T + neighbour_bias + hidden @ root_weight.T)
    pooled = np.mean(hidden, axis=0, keepdims=True)
    head_hidden = _relu(_linear(pooled, cast(dict[str, object], member["head_hidden"])))
    output = _linear(head_hidden, cast(dict[str, object], member["head_output"]))
    return _array(output[0], name="member_output", ndim=1)


def _outside_bounds(
    values: FloatArray,
    lower: FloatArray,
    upper: FloatArray,
    names: tuple[str, ...],
    prefix: str,
) -> list[str]:
    observed_min = np.min(values, axis=0)
    observed_max = np.max(values, axis=0)
    return [
        f"{prefix}.{name} outside [{lower[index]:.6g}, {upper[index]:.6g}]"
        for index, name in enumerate(names)
        if observed_min[index] < lower[index] or observed_max[index] > upper[index]
    ]


def _ood_reasons(graph: _GraphInput, payload: dict[str, object]) -> list[str]:
    bounds = cast(dict[str, object], payload["ood_bounds"])
    nodes = _array(graph.node_features, name="node_features", ndim=2)
    edges = _array(graph.edge_features, name="edge_features", ndim=2)
    reasons = _outside_bounds(
        nodes,
        _array(bounds["node_lower"], name="node_lower", ndim=1),
        _array(bounds["node_upper"], name="node_upper", ndim=1),
        NODE_FEATURE_NAMES,
        "node",
    )
    reasons.extend(
        _outside_bounds(
            edges,
            _array(bounds["edge_lower"], name="edge_lower", ndim=1),
            _array(bounds["edge_upper"], name="edge_upper", ndim=1),
            EDGE_FEATURE_NAMES,
            "edge",
        )
    )
    count_bounds = cast(dict[str, object], bounds["counts"])
    node_range = cast(list[float], count_bounds["nodes"])
    edge_range = cast(list[float], count_bounds["directed_edges"])
    if not node_range[0] <= len(graph.node_features) <= node_range[1]:
        reasons.append("graph.node_count outside training bounds")
    if not edge_range[0] <= len(graph.edge_features) <= edge_range[1]:
        reasons.append("graph.directed_edge_count outside training bounds")
    return sorted(reasons)


def _review_result(
    *,
    input_hash: str,
    reason: str,
    model_id: str | None = None,
    model_hash: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> FrameSurrogateResult:
    return FrameSurrogateResult(
        status=FrameSurrogateStatus.REVIEW_REQUIRED,
        input_hash=input_hash,
        model_id=model_id,
        model_hash=model_hash,
        review_reasons=[reason],
        evidence=evidence or [],
    )


def predict_frame_surrogate(
    contract: StructuralFrameContract,
    *,
    model_path: str | Path | None = None,
) -> FrameSurrogateResult:
    """Predict two screening quantities without ever granting engineering approval.

    ``PREDICTED`` means only that the model input passed the model's uncertainty and
    OOD gates.  An exact deterministic solve remains required in every case.
    """

    try:
        input_hash = _canonical_hash(contract)
        graph = _graph_from_contract(contract)
    except Exception as exc:  # invalid external contracts must fail closed
        return _review_result(
            input_hash=_fallback_input_hash(contract),
            reason="DG_FRAME_SURROGATE_INVALID_INPUT",
            evidence=[{"type": "invalid_input", "message": str(exc)}],
        )
    path = Path(model_path) if model_path is not None else DEFAULT_MODEL_PATH
    if not path.is_file():
        return _review_result(
            input_hash=input_hash,
            reason="DG_FRAME_SURROGATE_MODEL_MISSING",
            evidence=[{"type": "model_missing", "path": str(path)}],
        )
    try:
        model_bytes = path.read_bytes()
        payload = cast(dict[str, object], json.loads(model_bytes))
        if payload.get("schema_version") != MODEL_SCHEMA_VERSION:
            raise ValueError("unsupported model schema")
        if payload.get("architecture") != "graphsage":
            raise ValueError("NumPy runtime supports only exported GraphSAGE ensembles")
        if payload.get("node_feature_names") != list(NODE_FEATURE_NAMES):
            raise ValueError("node feature schema differs from the runtime")
        if payload.get("edge_feature_names") != list(EDGE_FEATURE_NAMES):
            raise ValueError("edge feature schema differs from the runtime")
        members = cast(list[dict[str, object]], payload["ensemble_members"])
        if len(members) < 2:
            raise ValueError("deep ensemble requires at least two members")
        normalization = cast(dict[str, object], payload["normalization"])
        normalized = np.vstack(
            [_predict_member(graph, member, normalization) for member in members]
        )
        target_mean = _array(normalization["target_log_mean"], name="target_log_mean")
        target_scale = _array(normalization["target_log_scale"], name="target_log_scale")
        physical = np.maximum(np.expm1(normalized * target_scale + target_mean), 0.0)
        predictions = np.mean(physical, axis=0)
        deviations = np.std(physical, axis=0, ddof=0)
        calibration = cast(dict[str, object], payload["uncertainty_calibration"])
        floors = _array(calibration["relative_floors"], name="relative_floors")
        score = float(np.max(deviations / np.maximum(np.abs(predictions), floors)))
        threshold_value = calibration["relative_score_threshold"]
        if not isinstance(threshold_value, int | float):
            raise ValueError("uncertainty threshold must be numeric")
        threshold = float(threshold_value)
        conformal = _array(calibration["conformal_multipliers"], name="conformal")
        ood = _ood_reasons(graph, payload)
        review_reasons: list[str] = []
        if ood:
            review_reasons.append("DG_FRAME_SURROGATE_OOD")
        if score > threshold:
            review_reasons.append("DG_FRAME_SURROGATE_HIGH_UNCERTAINTY")
        status = (
            FrameSurrogateStatus.REVIEW_REQUIRED
            if review_reasons
            else FrameSurrogateStatus.PREDICTED
        )
        lower = np.maximum(predictions - conformal * deviations, 0.0)
        upper = predictions + conformal * deviations
        model_hash = f"sha256:{hashlib.sha256(model_bytes).hexdigest()}"
        return FrameSurrogateResult(
            status=status,
            model_id=str(payload["model_id"]),
            model_hash=model_hash,
            input_hash=input_hash,
            max_displacement_mm=float(predictions[0]),
            max_utilization=float(predictions[1]),
            uncertainty=FrameSurrogateUncertainty(
                max_displacement_std_mm=float(deviations[0]),
                max_utilization_std=float(deviations[1]),
                relative_score=score,
                calibrated_threshold=threshold,
                displacement_interval_mm=(float(lower[0]), float(upper[0])),
                utilization_interval=(float(lower[1]), float(upper[1])),
            ),
            ood_reasons=ood,
            review_reasons=review_reasons,
            evidence=[
                {
                    "type": "surrogate_boundary",
                    "model_role": "preview_only",
                    "threshold_source": "validation_partition_only",
                    "official_solver_required": True,
                    "safety_certification": False,
                }
            ],
        )
    except Exception as exc:
        return _review_result(
            input_hash=input_hash,
            reason="DG_FRAME_SURROGATE_MODEL_INVALID",
            model_hash=(
                f"sha256:{hashlib.sha256(model_bytes).hexdigest()}"
                if "model_bytes" in locals()
                else None
            ),
            evidence=[{"type": "model_invalid", "message": str(exc), "path": str(path)}],
        )


__all__ = [
    "DEFAULT_MODEL_PATH",
    "FrameSurrogateResult",
    "FrameSurrogateStatus",
    "FrameSurrogateUncertainty",
    "MODEL_SCHEMA_VERSION",
    "predict_frame_surrogate",
]

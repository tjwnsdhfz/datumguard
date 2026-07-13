# mypy: ignore-errors
"""Optional PyTorch Geometric training utilities for the FrameGuard surrogate.

The deployed DatumGuard package never imports this module.  Install the ``ml``
extra to run experiments.  All labels come from ``frame_dataset`` records,
which in turn are produced only by the deterministic frame solver.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import torch
from torch import Tensor, nn
from torch_geometric.data import Batch, Data
from torch_geometric.loader import DataLoader
from torch_geometric.nn import GATConv, SAGEConv, global_mean_pool

from .frame_dataset import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    SOLVER_ID,
    FrameGraphRecord,
)
from .frame_surrogate import MODEL_SCHEMA_VERSION

Architecture = Literal["graphsage", "gat"]
TARGET_NAMES = ("max_displacement_mm", "max_utilization")


@dataclass(frozen=True)
class RecordPartitions:
    train: list[FrameGraphRecord]
    validation: list[FrameGraphRecord]
    test: list[FrameGraphRecord]
    train_groups: list[str]
    validation_groups: list[str]
    test_groups: list[str]


@dataclass(frozen=True)
class GraphNormalization:
    node_mean: np.ndarray
    node_scale: np.ndarray
    edge_mean: np.ndarray
    edge_scale: np.ndarray
    target_log_mean: np.ndarray
    target_log_scale: np.ndarray

    def as_json(self) -> dict[str, list[float]]:
        return {
            "node_mean": self.node_mean.tolist(),
            "node_scale": self.node_scale.tolist(),
            "edge_mean": self.edge_mean.tolist(),
            "edge_scale": self.edge_scale.tolist(),
            "target_log_mean": self.target_log_mean.tolist(),
            "target_log_scale": self.target_log_scale.tolist(),
        }


@dataclass
class TrainedMember:
    architecture: Architecture
    seed: int
    model: FrameGNN
    best_validation_loss: float
    epochs_trained: int


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


def topology_holdout_partitions(
    records: Sequence[FrameGraphRecord],
    *,
    split_seed: int,
    test_group: str = "pipe_rack_4_bay",
    validation_fraction: float = 0.2,
) -> RecordPartitions:
    """Hold one topology family out for test and stratify validation by train family.

    Contract hashes and case IDs are used only for split integrity assertions.  They
    are never encoded as model features.
    """

    if not 0.05 <= validation_fraction <= 0.5:
        raise ValueError("validation_fraction must be between 0.05 and 0.5")
    test = [record for record in records if record.topology_group == test_group]
    remaining = [record for record in records if record.topology_group != test_group]
    if not test or not remaining:
        raise ValueError("topology holdout produced an empty train/validation or test set")
    rng = random.Random(split_seed)
    train: list[FrameGraphRecord] = []
    validation: list[FrameGraphRecord] = []
    for group in sorted({record.topology_group for record in remaining}):
        group_records = sorted(
            (record for record in remaining if record.topology_group == group),
            key=lambda record: record.case_id,
        )
        rng.shuffle(group_records)
        val_count = max(2, int(round(len(group_records) * validation_fraction)))
        if val_count >= len(group_records):
            val_count = len(group_records) - 1
        if val_count <= 0:
            raise ValueError(f"not enough {group} records for validation")
        validation.extend(group_records[:val_count])
        train.extend(group_records[val_count:])
    train.sort(key=lambda record: record.case_id)
    validation.sort(key=lambda record: record.case_id)
    test.sort(key=lambda record: record.case_id)
    partitions = [train, validation, test]
    case_sets = [{record.case_id for record in partition} for partition in partitions]
    hash_sets = [{record.contract_hash for record in partition} for partition in partitions]
    if any(case_sets[i] & case_sets[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("case ID leakage detected")
    if any(hash_sets[i] & hash_sets[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("contract hash leakage detected")
    return RecordPartitions(
        train=train,
        validation=validation,
        test=test,
        train_groups=sorted({record.topology_group for record in train}),
        validation_groups=sorted({record.topology_group for record in validation}),
        test_groups=sorted({record.topology_group for record in test}),
    )


def fit_normalization(records: Sequence[FrameGraphRecord]) -> GraphNormalization:
    if not records:
        raise ValueError("normalization requires at least one training record")
    nodes = np.vstack([np.asarray(record.node_features, dtype=np.float64) for record in records])
    edges = np.vstack([np.asarray(record.edge_features, dtype=np.float64) for record in records])
    targets = np.asarray(
        [
            [record.targets.max_displacement_mm, record.targets.max_utilization]
            for record in records
        ],
        dtype=np.float64,
    )

    def safe_scale(values: np.ndarray) -> np.ndarray:
        scales = np.std(values, axis=0)
        return np.where(scales > np.finfo(np.float64).eps, scales, 1.0)

    target_log = np.log1p(targets)
    return GraphNormalization(
        node_mean=np.mean(nodes, axis=0),
        node_scale=safe_scale(nodes),
        edge_mean=np.mean(edges, axis=0),
        edge_scale=safe_scale(edges),
        target_log_mean=np.mean(target_log, axis=0),
        target_log_scale=safe_scale(target_log),
    )


def record_to_pyg(record: FrameGraphRecord, stats: GraphNormalization) -> Data:
    """Convert the solver-labelled graph to a genuine torch_geometric Data object."""

    nodes = (np.asarray(record.node_features) - stats.node_mean) / stats.node_scale
    edges = (np.asarray(record.edge_features) - stats.edge_mean) / stats.edge_scale
    targets = np.asarray(
        [record.targets.max_displacement_mm, record.targets.max_utilization],
        dtype=np.float64,
    )
    normalized_target = (np.log1p(targets) - stats.target_log_mean) / stats.target_log_scale
    return Data(
        x=torch.tensor(nodes, dtype=torch.float32),
        edge_index=torch.tensor(record.edge_index, dtype=torch.long),
        edge_attr=torch.tensor(edges, dtype=torch.float32),
        y=torch.tensor(normalized_target[None, :], dtype=torch.float32),
        raw_y=torch.tensor(targets[None, :], dtype=torch.float32),
        case_id=record.case_id,
        topology_group=record.topology_group,
    )


def records_to_batch(records: Sequence[FrameGraphRecord], stats: GraphNormalization) -> Batch:
    return Batch.from_data_list([record_to_pyg(record, stats) for record in records])


class FrameGNN(nn.Module):
    def __init__(
        self,
        architecture: Architecture,
        *,
        hidden_channels: int = 32,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.architecture = architecture
        self.dropout = dropout
        self.node_encoder = nn.Linear(len(NODE_FEATURE_NAMES), hidden_channels)
        self.edge_encoder = nn.Linear(len(EDGE_FEATURE_NAMES), hidden_channels)
        if architecture == "graphsage":
            self.conv1 = SAGEConv(hidden_channels, hidden_channels)
            self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        elif architecture == "gat":
            self.conv1 = GATConv(
                hidden_channels,
                hidden_channels,
                heads=2,
                concat=False,
                edge_dim=hidden_channels,
                dropout=dropout,
            )
            self.conv2 = GATConv(
                hidden_channels,
                hidden_channels,
                heads=2,
                concat=False,
                edge_dim=hidden_channels,
                dropout=dropout,
            )
        else:
            raise ValueError(f"unsupported architecture: {architecture}")
        self.head_hidden = nn.Linear(hidden_channels, hidden_channels)
        self.head_output = nn.Linear(hidden_channels, len(TARGET_NAMES))

    @staticmethod
    def _edge_mean(edge_values: Tensor, edge_index: Tensor, node_count: int) -> Tensor:
        target = edge_index[1]
        result = torch.zeros(
            (node_count, edge_values.shape[1]),
            dtype=edge_values.dtype,
            device=edge_values.device,
        )
        counts = torch.zeros((node_count, 1), dtype=edge_values.dtype, device=edge_values.device)
        result.index_add_(0, target, edge_values)
        counts.index_add_(
            0,
            target,
            torch.ones((target.shape[0], 1), dtype=edge_values.dtype, device=edge_values.device),
        )
        return result / counts.clamp_min(1.0)

    def forward(self, batch: Data | Batch) -> Tensor:
        edge_hidden = torch.relu(self.edge_encoder(batch.edge_attr))
        edge_context = self._edge_mean(edge_hidden, batch.edge_index, batch.x.shape[0])
        hidden = torch.relu(self.node_encoder(batch.x) + edge_context)
        if self.architecture == "gat":
            hidden = torch.relu(self.conv1(hidden, batch.edge_index, edge_attr=edge_hidden))
            hidden = nn.functional.dropout(hidden, p=self.dropout, training=self.training)
            hidden = torch.relu(self.conv2(hidden, batch.edge_index, edge_attr=edge_hidden))
        else:
            hidden = torch.relu(self.conv1(hidden, batch.edge_index))
            hidden = nn.functional.dropout(hidden, p=self.dropout, training=self.training)
            hidden = torch.relu(self.conv2(hidden, batch.edge_index))
        graph_batch = getattr(
            batch,
            "batch",
            torch.zeros(batch.x.shape[0], dtype=torch.long, device=batch.x.device),
        )
        pooled = global_mean_pool(hidden, graph_batch)
        pooled = torch.relu(self.head_hidden(pooled))
        pooled = nn.functional.dropout(pooled, p=self.dropout, training=self.training)
        return self.head_output(pooled)


def _validation_loss(
    model: FrameGNN,
    records: Sequence[FrameGraphRecord],
    stats: GraphNormalization,
) -> float:
    model.eval()
    with torch.no_grad():
        batch = records_to_batch(records, stats)
        return float(nn.functional.smooth_l1_loss(model(batch), batch.y).item())


def train_member(
    architecture: Architecture,
    train_records: Sequence[FrameGraphRecord],
    validation_records: Sequence[FrameGraphRecord],
    stats: GraphNormalization,
    *,
    seed: int,
    epochs: int,
    hidden_channels: int = 32,
    dropout: float = 0.1,
    batch_size: int = 24,
    patience: int = 35,
) -> TrainedMember:
    _seed_everything(seed)
    model = FrameGNN(architecture, hidden_channels=hidden_channels, dropout=dropout)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.003, weight_decay=1e-4)
    generator = torch.Generator().manual_seed(seed)
    data = [record_to_pyg(record, stats) for record in train_records]
    loader = DataLoader(
        data,
        batch_size=min(batch_size, len(data)),
        shuffle=True,
        generator=generator,
    )
    best_loss = math.inf
    best_state: dict[str, Tensor] | None = None
    stale = 0
    trained = 0
    for epoch in range(epochs):
        model.train()
        for batch in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.smooth_l1_loss(model(batch), batch.y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
        trained = epoch + 1
        validation_loss = _validation_loss(model, validation_records, stats)
        if validation_loss < best_loss - 1e-6:
            best_loss = validation_loss
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= patience:
            break
    if best_state is None:
        raise RuntimeError("training did not produce a finite validation checkpoint")
    model.load_state_dict(best_state)
    model.eval()
    return TrainedMember(
        architecture=architecture,
        seed=seed,
        model=model,
        best_validation_loss=best_loss,
        epochs_trained=trained,
    )


def predict_members(
    members: Sequence[TrainedMember],
    records: Sequence[FrameGraphRecord],
    stats: GraphNormalization,
) -> np.ndarray:
    """Return physical-space predictions shaped [ensemble, graph, target]."""

    if not members or not records:
        raise ValueError("prediction requires members and records")
    batch = records_to_batch(records, stats)
    outputs: list[np.ndarray] = []
    with torch.no_grad():
        for member in members:
            member.model.eval()
            normalized = member.model(batch).cpu().numpy().astype(np.float64)
            physical = np.maximum(
                np.expm1(
                    normalized * stats.target_log_scale[None, :] + stats.target_log_mean[None, :]
                ),
                0.0,
            )
            outputs.append(physical)
    return np.stack(outputs, axis=0)


def _targets(records: Sequence[FrameGraphRecord]) -> np.ndarray:
    return np.asarray(
        [
            [record.targets.max_displacement_mm, record.targets.max_utilization]
            for record in records
        ],
        dtype=np.float64,
    )


def _r2(actual: np.ndarray, predicted: np.ndarray) -> float:
    denominator = float(np.sum((actual - np.mean(actual)) ** 2))
    if denominator <= np.finfo(np.float64).eps:
        return 0.0
    return 1.0 - float(np.sum((actual - predicted) ** 2)) / denominator


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, dict[str, float]]:
    return {
        target: {
            "mae": float(np.mean(np.abs(actual[:, index] - predicted[:, index]))),
            "r2": _r2(actual[:, index], predicted[:, index]),
        }
        for index, target in enumerate(TARGET_NAMES)
    }


def calibrate_uncertainty(
    ensemble_predictions: np.ndarray,
    validation_records: Sequence[FrameGraphRecord],
) -> dict[str, Any]:
    """Calibrate the review threshold and intervals on validation data only."""

    actual = _targets(validation_records)
    mean = np.mean(ensemble_predictions, axis=0)
    std = np.std(ensemble_predictions, axis=0, ddof=0)
    floors = np.maximum(np.median(np.abs(actual), axis=0) * 0.02, [1e-3, 1e-5])
    relative = std / np.maximum(np.abs(mean), floors[None, :])
    case_scores = np.max(relative, axis=1)
    threshold = max(float(np.quantile(case_scores, 0.95)), 1e-6)
    ratios = np.abs(actual - mean) / np.maximum(std, floors[None, :] * 0.01)
    conformal = np.maximum(np.quantile(ratios, 0.9, axis=0), 1.0)
    lower = np.maximum(mean - conformal[None, :] * std, 0.0)
    upper = mean + conformal[None, :] * std
    coverage = np.mean((actual >= lower) & (actual <= upper), axis=0)
    return {
        "source_partition": "validation_only",
        "relative_floors": floors.tolist(),
        "relative_score_quantile": 0.95,
        "relative_score_threshold": threshold,
        "conformal_quantile": 0.9,
        "conformal_multipliers": conformal.tolist(),
        "validation_interval_coverage": {
            target: float(coverage[index]) for index, target in enumerate(TARGET_NAMES)
        },
    }


def _partition_report(
    members: Sequence[TrainedMember],
    records: Sequence[FrameGraphRecord],
    stats: GraphNormalization,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    predictions = predict_members(members, records, stats)
    mean = np.mean(predictions, axis=0)
    std = np.std(predictions, axis=0, ddof=0)
    actual = _targets(records)
    multipliers = np.asarray(calibration["conformal_multipliers"], dtype=np.float64)
    lower = np.maximum(mean - multipliers[None, :] * std, 0.0)
    upper = mean + multipliers[None, :] * std
    return {
        "count": len(records),
        "ensemble_metrics": regression_metrics(actual, mean),
        "mean_interval_width": {
            target: float(np.mean(upper[:, index] - lower[:, index]))
            for index, target in enumerate(TARGET_NAMES)
        },
        "interval_coverage": {
            target: float(
                np.mean(
                    (actual[:, index] >= lower[:, index]) & (actual[:, index] <= upper[:, index])
                )
            )
            for index, target in enumerate(TARGET_NAMES)
        },
        "mean_predictive_std": {
            target: float(np.mean(std[:, index])) for index, target in enumerate(TARGET_NAMES)
        },
    }


def train_architecture_ensemble(
    architecture: Architecture,
    partitions: RecordPartitions,
    *,
    seeds: Sequence[int],
    epochs: int,
    hidden_channels: int,
) -> tuple[list[TrainedMember], GraphNormalization, dict[str, Any]]:
    if len(set(seeds)) < 2:
        raise ValueError("deep ensemble requires at least two distinct seeds")
    stats = fit_normalization(partitions.train)
    members = [
        train_member(
            architecture,
            partitions.train,
            partitions.validation,
            stats,
            seed=seed,
            epochs=epochs,
            hidden_channels=hidden_channels,
        )
        for seed in seeds
    ]
    validation_predictions = predict_members(members, partitions.validation, stats)
    calibration = calibrate_uncertainty(validation_predictions, partitions.validation)
    report = {
        "architecture": architecture,
        "ensemble_seeds": list(seeds),
        "seed_runs": [
            {
                "seed": member.seed,
                "epochs_trained": member.epochs_trained,
                "best_validation_loss": member.best_validation_loss,
                "test_metrics": regression_metrics(
                    _targets(partitions.test),
                    predict_members([member], partitions.test, stats)[0],
                ),
            }
            for member in members
        ],
        "uncertainty_calibration": calibration,
        "partitions": {
            "train": _partition_report(members, partitions.train, stats, calibration),
            "validation": _partition_report(members, partitions.validation, stats, calibration),
            "test": _partition_report(members, partitions.test, stats, calibration),
        },
    }
    return members, stats, report


def _linear_export(layer: nn.Linear) -> dict[str, list[Any]]:
    return {
        "weight": layer.weight.detach().cpu().double().numpy().tolist(),
        "bias": layer.bias.detach().cpu().double().numpy().tolist(),
    }


def _sage_export(layer: SAGEConv) -> dict[str, list[Any]]:
    return {
        "neighbour_weight": layer.lin_l.weight.detach().cpu().double().numpy().tolist(),
        "neighbour_bias": layer.lin_l.bias.detach().cpu().double().numpy().tolist(),
        "root_weight": layer.lin_r.weight.detach().cpu().double().numpy().tolist(),
    }


def _member_export(member: TrainedMember) -> dict[str, Any]:
    if member.architecture != "graphsage":
        raise ValueError("the lightweight runtime supports GraphSAGE only")
    model = member.model
    return {
        "seed": member.seed,
        "node_encoder": _linear_export(model.node_encoder),
        "edge_encoder": _linear_export(model.edge_encoder),
        "conv1": _sage_export(cast(SAGEConv, model.conv1)),
        "conv2": _sage_export(cast(SAGEConv, model.conv2)),
        "head_hidden": _linear_export(model.head_hidden),
        "head_output": _linear_export(model.head_output),
    }


def _ood_bounds(
    records: Sequence[FrameGraphRecord], margin_fraction: float = 0.1
) -> dict[str, Any]:
    nodes = np.vstack([np.asarray(record.node_features, dtype=np.float64) for record in records])
    edges = np.vstack([np.asarray(record.edge_features, dtype=np.float64) for record in records])

    def bounds(values: np.ndarray) -> tuple[list[float], list[float]]:
        lower = np.min(values, axis=0)
        upper = np.max(values, axis=0)
        margin = np.maximum((upper - lower) * margin_fraction, 1e-9)
        return (lower - margin).tolist(), (upper + margin).tolist()

    node_lower, node_upper = bounds(nodes)
    edge_lower, edge_upper = bounds(edges)
    node_counts = [len(record.node_features) for record in records]
    edge_counts = [len(record.edge_features) for record in records]
    return {
        "source_partition": "training_only",
        "margin_fraction": margin_fraction,
        "node_lower": node_lower,
        "node_upper": node_upper,
        "edge_lower": edge_lower,
        "edge_upper": edge_upper,
        "counts": {
            "nodes": [min(node_counts), max(node_counts)],
            "directed_edges": [min(edge_counts), max(edge_counts)],
        },
    }


def build_graphsage_artifact(
    members: Sequence[TrainedMember],
    stats: GraphNormalization,
    calibration: dict[str, Any],
    training_records: Sequence[FrameGraphRecord],
    *,
    model_id: str = "frame_graphsage_ensemble_v1",
) -> dict[str, Any]:
    if len(members) < 2 or any(member.architecture != "graphsage" for member in members):
        raise ValueError("portable artifact requires a GraphSAGE deep ensemble")
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_id": model_id,
        "architecture": "graphsage",
        "runtime": "numpy_graphsage_ensemble_v1",
        "target_transform": "log1p_then_standardize",
        "target_names": list(TARGET_NAMES),
        "label_provenance": {
            "solver_id": SOLVER_ID,
            "learned_or_surrogate_labels": False,
            "official_deterministic_solver": True,
        },
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "normalization": stats.as_json(),
        "uncertainty_calibration": calibration,
        "ood_bounds": _ood_bounds(training_records),
        "ensemble_members": [_member_export(member) for member in members],
        "claims": {
            "authoritative": False,
            "exact_solver_required": True,
            "safety_certification": False,
            "test_partition_used_for_calibration": False,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    path.write_bytes(encoded)
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


__all__ = [
    "Architecture",
    "FrameGNN",
    "GraphNormalization",
    "RecordPartitions",
    "TARGET_NAMES",
    "TrainedMember",
    "build_graphsage_artifact",
    "calibrate_uncertainty",
    "fit_normalization",
    "predict_members",
    "record_to_pyg",
    "records_to_batch",
    "regression_metrics",
    "topology_holdout_partitions",
    "train_architecture_ensemble",
    "train_member",
    "write_json",
]

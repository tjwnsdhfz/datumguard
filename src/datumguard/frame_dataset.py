from __future__ import annotations

import math
import random
from collections import Counter
from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, model_validator

from .frame_models import StructuralFrameContract
from .frame_service import validate_frame_contract
from .frame_solver import FrameSolverError, solve_frame
from .models import ContractStatus, StrictModel

SOLVER_ID: Literal["datumguard_numpy_2d_frame_v1"] = "datumguard_numpy_2d_frame_v1"
TOPOLOGY_FAMILIES: tuple[tuple[str, int], ...] = (
    ("pipe_rack_2_bay", 2),
    ("pipe_rack_3_bay", 3),
    ("pipe_rack_4_bay", 4),
)
NODE_FEATURE_NAMES: tuple[str, ...] = (
    "x_mm",
    "y_mm",
    "restraint_ux",
    "restraint_uy",
    "restraint_rz",
    "fx_n",
    "fy_n",
    "mz_nmm",
)
EDGE_FEATURE_NAMES: tuple[str, ...] = (
    "length_mm",
    "direction_x",
    "direction_y",
    "area_mm2",
    "inertia_mm4",
    "elastic_modulus_mpa",
    "section_depth_mm",
    "allowable_stress_mpa",
)
POOLED_FEATURE_NAMES: tuple[str, ...] = (
    "node_count",
    "member_count",
    "span_x_mm",
    "span_y_mm",
    "restrained_dof_count",
    "total_abs_fx_n",
    "total_abs_fy_n",
    "total_abs_mz_nmm",
    "resultant_nodal_force_n",
    "mean_member_length_mm",
    "max_member_length_mm",
    "mean_area_mm2",
    "min_area_mm2",
    "mean_inertia_mm4",
    "min_inertia_mm4",
    "mean_elastic_modulus_mpa",
    "mean_section_depth_mm",
    "mean_allowable_stress_mpa",
    "sum_axial_stiffness_n_per_mm",
    "sum_bending_stiffness_n_per_mm",
)

FloatArray = NDArray[np.float64]


class FrameGraphTargets(StrictModel):
    max_displacement_mm: float = Field(ge=0)
    max_utilization: float = Field(ge=0)
    governing_member_id: str
    screening_pass: bool


class FrameGraphRecord(StrictModel):
    case_id: str
    topology_group: str
    node_ids: list[str]
    node_features: list[list[float]]
    edge_index: tuple[list[int], list[int]]
    edge_member_ids: list[str]
    edge_features: list[list[float]]
    targets: FrameGraphTargets
    solver_id: Literal["datumguard_numpy_2d_frame_v1"] = SOLVER_ID
    contract_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_graph_shapes(self) -> FrameGraphRecord:
        if not self.node_ids or len(self.node_ids) != len(self.node_features):
            raise ValueError("node_ids and node_features must have the same non-zero length")
        if len(set(self.node_ids)) != len(self.node_ids):
            raise ValueError("node_ids must be unique")
        if any(len(row) != len(NODE_FEATURE_NAMES) for row in self.node_features):
            raise ValueError("each node feature row must match NODE_FEATURE_NAMES")
        source, target = self.edge_index
        edge_count = len(source)
        if not (
            edge_count
            and edge_count == len(target)
            and edge_count == len(self.edge_features)
            and edge_count == len(self.edge_member_ids)
        ):
            raise ValueError("edge_index, edge_member_ids, and edge_features must align")
        if any(len(row) != len(EDGE_FEATURE_NAMES) for row in self.edge_features):
            raise ValueError("each edge feature row must match EDGE_FEATURE_NAMES")
        if any(index < 0 or index >= len(self.node_ids) for index in [*source, *target]):
            raise ValueError("edge_index contains an out-of-range node index")
        numeric_values = [
            value for row in [*self.node_features, *self.edge_features] for value in row
        ]
        numeric_values.extend([self.targets.max_displacement_mm, self.targets.max_utilization])
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("graph records may contain only finite numeric values")
        if self.targets.governing_member_id not in self.edge_member_ids:
            raise ValueError("governing_member_id must identify an encoded edge")
        return self


class FrameGraphDataset(StrictModel):
    schema_version: Literal["frame-graph-dataset-v1"] = "frame-graph-dataset-v1"
    seed: int
    requested_cases: int = Field(ge=3)
    attempted_cases: int = Field(ge=3)
    excluded_singular: int = Field(ge=0)
    records: list[FrameGraphRecord] = Field(min_length=3)
    solver_id: Literal["datumguard_numpy_2d_frame_v1"] = SOLVER_ID

    @model_validator(mode="after")
    def validate_counts_and_families(self) -> FrameGraphDataset:
        if len(self.records) != self.requested_cases:
            raise ValueError("record count must equal requested_cases")
        if self.attempted_cases != len(self.records) + self.excluded_singular:
            raise ValueError("attempted_cases must equal valid plus excluded cases")
        groups = {record.topology_group for record in self.records}
        if len(groups) < 3:
            raise ValueError("the synthetic dataset must contain at least three topology groups")
        return self


class FrameDatasetSplit(StrictModel):
    train: list[FrameGraphRecord] = Field(min_length=1)
    test: list[FrameGraphRecord] = Field(min_length=1)
    train_groups: list[str] = Field(min_length=1)
    test_groups: list[str] = Field(min_length=1)
    leakage_group_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_group_holdout(self) -> FrameDatasetSplit:
        actual_train = sorted({record.topology_group for record in self.train})
        actual_test = sorted({record.topology_group for record in self.test})
        if actual_train != self.train_groups or actual_test != self.test_groups:
            raise ValueError("declared split groups do not match record groups")
        leakage = len(set(actual_train) & set(actual_test))
        if leakage != self.leakage_group_count:
            raise ValueError("leakage_group_count is inconsistent")
        if leakage:
            raise ValueError("topology groups may not leak between train and test")
        return self


class RegressionMetric(StrictModel):
    mae: float = Field(ge=0)
    r2: float


class RidgeBaselineResult(StrictModel):
    baseline_id: Literal["numpy_pooled_ridge_v1"] = "numpy_pooled_ridge_v1"
    is_gnn: Literal[False] = False
    alpha: float = Field(ge=0)
    feature_names: list[str]
    target_names: list[str]
    train_count: int = Field(ge=1)
    test_count: int = Field(ge=1)
    train_groups: list[str]
    test_groups: list[str]
    metrics: dict[str, RegressionMetric]
    predictions: list[dict[str, float]]

    @model_validator(mode="after")
    def validate_metrics(self) -> RidgeBaselineResult:
        expected = {"max_displacement_mm", "max_utilization"}
        if set(self.metrics) != expected or set(self.target_names) != expected:
            raise ValueError("ridge baseline must evaluate both continuous targets")
        metric_values = [
            value for metric in self.metrics.values() for value in (metric.mae, metric.r2)
        ]
        prediction_values = [value for row in self.predictions for value in row.values()]
        if not all(math.isfinite(value) for value in [*metric_values, *prediction_values]):
            raise ValueError("baseline outputs must be finite")
        return self


def _member_properties(
    rng: random.Random,
    *,
    member_kind: Literal["column", "beam", "brace"],
) -> tuple[float, float, float]:
    if member_kind == "column":
        return (
            rng.uniform(3_800.0, 7_200.0),
            rng.uniform(55_000_000.0, 165_000_000.0),
            rng.uniform(280.0, 420.0),
        )
    if member_kind == "beam":
        return (
            rng.uniform(2_800.0, 5_800.0),
            rng.uniform(35_000_000.0, 125_000_000.0),
            rng.uniform(240.0, 380.0),
        )
    return (
        rng.uniform(1_400.0, 3_600.0),
        rng.uniform(4_000_000.0, 24_000_000.0),
        rng.uniform(100.0, 190.0),
    )


def generate_pipe_rack_contract(
    *,
    bays: Literal[2, 3, 4],
    seed: int,
    singular: bool = False,
) -> StructuralFrameContract:
    """Generate one deterministic two-level portal/pipe-rack screening contract."""

    rng = random.Random(seed)
    span = rng.uniform(3_500.0, 6_000.0)
    level_height = rng.uniform(2_800.0, 4_200.0)
    elastic_modulus = rng.uniform(195_000.0, 210_000.0)
    allowable = rng.uniform(180.0, 285.0)
    nodes: list[dict[str, object]] = []
    for level in range(3):
        for column in range(bays + 1):
            nodes.append(
                {
                    "id": f"N-L{level}-C{column}",
                    "point": [column * span, level * level_height],
                    "locked": True,
                }
            )

    members: list[dict[str, object]] = []
    for level in range(2):
        for column in range(bays + 1):
            area, inertia, depth = _member_properties(rng, member_kind="column")
            members.append(
                {
                    "id": f"COL-L{level}-C{column}",
                    "start_node_id": f"N-L{level}-C{column}",
                    "end_node_id": f"N-L{level + 1}-C{column}",
                    "area_mm2": area,
                    "inertia_mm4": inertia,
                    "elastic_modulus_mpa": elastic_modulus,
                    "section_depth_mm": depth,
                    "locked": True,
                }
            )
    for level in (1, 2):
        for bay in range(bays):
            area, inertia, depth = _member_properties(rng, member_kind="beam")
            members.append(
                {
                    "id": f"BEAM-L{level}-B{bay}",
                    "start_node_id": f"N-L{level}-C{bay}",
                    "end_node_id": f"N-L{level}-C{bay + 1}",
                    "area_mm2": area,
                    "inertia_mm4": inertia,
                    "elastic_modulus_mpa": elastic_modulus,
                    "section_depth_mm": depth,
                    "locked": True,
                }
            )
    for bay in range(bays):
        area, inertia, depth = _member_properties(rng, member_kind="brace")
        left_to_right = bay % 2 == 0
        start_column = bay if left_to_right else bay + 1
        end_column = bay + 1 if left_to_right else bay
        members.append(
            {
                "id": f"BRACE-B{bay}",
                "start_node_id": f"N-L0-C{start_column}",
                "end_node_id": f"N-L1-C{end_column}",
                "area_mm2": area,
                "inertia_mm4": inertia,
                "elastic_modulus_mpa": elastic_modulus,
                "section_depth_mm": depth,
                "locked": True,
            }
        )

    vertical_total = rng.uniform(90_000.0, 360_000.0)
    lateral_total = rng.uniform(8_000.0, 85_000.0)
    loads: list[dict[str, object]] = []
    for column in range(bays + 1):
        share = rng.uniform(0.75, 1.25) / (bays + 1)
        loads.append(
            {
                "id": f"LOAD-TOP-C{column}",
                "node_id": f"N-L2-C{column}",
                "fx_n": lateral_total / (bays + 1),
                "fy_n": -vertical_total * share,
                "mz_nmm": rng.uniform(-1_500_000.0, 1_500_000.0),
            }
        )
    supports = (
        []
        if singular
        else [
            {
                "id": f"SUPPORT-C{column}",
                "node_id": f"N-L0-C{column}",
                "ux": True,
                "uy": True,
                "rz": True,
            }
            for column in range(bays + 1)
        ]
    )
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "design_kind": "structural_frame",
        "units": "mm",
        "nodes": nodes,
        "members": members,
        "loads": loads,
        "supports": supports,
        "limits": {
            "max_displacement_mm": rng.uniform(2.0, 22.0),
            "allowable_stress_mpa": allowable,
        },
        "free_parameters": [],
        "metadata": {
            "project_name": f"Synthetic {bays}-bay pipe rack",
            "revision": "DATASET",
            "notes": "Research-only exact-solver label generation; not a safety certification.",
        },
    }
    return StructuralFrameContract.model_validate(payload)


def _contract_to_record(
    contract: StructuralFrameContract,
    *,
    case_id: str,
    topology_group: str,
) -> FrameGraphRecord:
    analysis = solve_frame(contract)
    validation = validate_frame_contract(contract)
    if validation.status != ContractStatus.READY:
        codes = [violation.code for violation in validation.violations]
        raise RuntimeError(f"generated frame contract did not validate: {codes}")
    nodes = sorted(contract.nodes, key=lambda item: item.id)
    node_index = {node.id: index for index, node in enumerate(nodes)}
    restraint_by_node = {node.id: [False, False, False] for node in nodes}
    for support in contract.supports:
        restraint = restraint_by_node[support.node_id]
        restraint[0] = restraint[0] or support.ux
        restraint[1] = restraint[1] or support.uy
        restraint[2] = restraint[2] or support.rz
    load_by_node = {node.id: [0.0, 0.0, 0.0] for node in nodes}
    for load in contract.loads:
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
    edge_member_ids: list[str] = []
    edge_features: list[list[float]] = []
    for member in sorted(contract.members, key=lambda item: item.id):
        start = next(node for node in nodes if node.id == member.start_node_id)
        end = next(node for node in nodes if node.id == member.end_node_id)
        dx = end.point[0] - start.point[0]
        dy = end.point[1] - start.point[1]
        length = math.hypot(dx, dy)
        allowable_stress = member.allowable_stress_mpa or contract.limits.allowable_stress_mpa
        common = [
            length,
            dx / length,
            dy / length,
            member.area_mm2,
            member.inertia_mm4,
            member.elastic_modulus_mpa,
            member.section_depth_mm,
            allowable_stress,
        ]
        reverse = [common[0], -common[1], -common[2], *common[3:]]
        source.extend([node_index[start.id], node_index[end.id]])
        target.extend([node_index[end.id], node_index[start.id]])
        edge_member_ids.extend([member.id, member.id])
        edge_features.extend([common, reverse])
    governing = analysis.critical_member_id
    if governing is None:
        raise RuntimeError("exact frame solver returned no governing member")
    screening_pass = (
        analysis.max_displacement_mm <= contract.limits.max_displacement_mm
        and analysis.max_member_utilization <= 1.0
    )
    return FrameGraphRecord(
        case_id=case_id,
        topology_group=topology_group,
        node_ids=[node.id for node in nodes],
        node_features=node_features,
        edge_index=(source, target),
        edge_member_ids=edge_member_ids,
        edge_features=edge_features,
        targets=FrameGraphTargets(
            max_displacement_mm=analysis.max_displacement_mm,
            max_utilization=analysis.max_member_utilization,
            governing_member_id=governing,
            screening_pass=screening_pass,
        ),
        solver_id=analysis.solver,
        contract_hash=validation.contract_hash,
    )


def generate_frame_dataset(*, cases: int, seed: int) -> FrameGraphDataset:
    """Build deterministic graph records labelled only by the exact frame solver."""

    if cases < 3:
        raise ValueError("cases must be at least 3 to cover all topology families")
    if cases > 10_000:
        raise ValueError("cases exceeds the research generator limit of 10,000")
    records: list[FrameGraphRecord] = []
    attempted = 0
    excluded_singular = 0
    maximum_attempts = cases * 2 + 100
    while len(records) < cases and attempted < maximum_attempts:
        topology_group, bay_count = TOPOLOGY_FAMILIES[attempted % len(TOPOLOGY_FAMILIES)]
        case_seed = seed * 1_000_003 + attempted * 97 + bay_count
        intentionally_singular = attempted % 17 == 0
        attempted += 1
        contract = generate_pipe_rack_contract(
            bays=cast(Literal[2, 3, 4], bay_count),
            seed=case_seed,
            singular=intentionally_singular,
        )
        try:
            record = _contract_to_record(
                contract,
                case_id=f"frame-{seed:08d}-{len(records):05d}",
                topology_group=topology_group,
            )
        except FrameSolverError as exc:
            if exc.code != "DG_FRAME_SINGULAR":
                raise
            excluded_singular += 1
            continue
        records.append(record)
    if len(records) != cases:
        raise RuntimeError("unable to generate the requested number of valid frame cases")
    return FrameGraphDataset(
        seed=seed,
        requested_cases=cases,
        attempted_cases=attempted,
        excluded_singular=excluded_singular,
        records=records,
    )


def group_holdout_split(
    records: list[FrameGraphRecord],
    *,
    holdout_group: str | None = None,
) -> FrameDatasetSplit:
    groups = sorted({record.topology_group for record in records})
    if len(groups) < 2:
        raise ValueError("at least two topology groups are required for group holdout")
    selected = holdout_group or groups[-1]
    if selected not in groups:
        raise ValueError(f"unknown holdout topology group: {selected}")
    train = [record for record in records if record.topology_group != selected]
    test = [record for record in records if record.topology_group == selected]
    if not train or not test:
        raise ValueError("group holdout produced an empty train or test partition")
    train_groups = sorted({record.topology_group for record in train})
    test_groups = sorted({record.topology_group for record in test})
    return FrameDatasetSplit(
        train=train,
        test=test,
        train_groups=train_groups,
        test_groups=test_groups,
        leakage_group_count=len(set(train_groups) & set(test_groups)),
    )


def pooled_global_features(record: FrameGraphRecord) -> FloatArray:
    nodes = np.asarray(record.node_features, dtype=np.float64)
    member_rows: list[list[float]] = []
    seen_members: set[str] = set()
    for member_id, features in zip(record.edge_member_ids, record.edge_features, strict=True):
        if member_id not in seen_members:
            seen_members.add(member_id)
            member_rows.append(features)
    edges = np.asarray(member_rows, dtype=np.float64)
    span_x = float(np.ptp(nodes[:, 0]))
    span_y = float(np.ptp(nodes[:, 1]))
    resultant = np.hypot(nodes[:, 5], nodes[:, 6])
    axial_stiffness = edges[:, 5] * edges[:, 3] / edges[:, 0]
    bending_stiffness = 12.0 * edges[:, 5] * edges[:, 4] / edges[:, 0] ** 3
    values = np.array(
        [
            float(nodes.shape[0]),
            float(edges.shape[0]),
            span_x,
            span_y,
            float(np.sum(nodes[:, 2:5])),
            float(np.sum(np.abs(nodes[:, 5]))),
            float(np.sum(np.abs(nodes[:, 6]))),
            float(np.sum(np.abs(nodes[:, 7]))),
            float(np.sum(resultant)),
            float(np.mean(edges[:, 0])),
            float(np.max(edges[:, 0])),
            float(np.mean(edges[:, 3])),
            float(np.min(edges[:, 3])),
            float(np.mean(edges[:, 4])),
            float(np.min(edges[:, 4])),
            float(np.mean(edges[:, 5])),
            float(np.mean(edges[:, 6])),
            float(np.mean(edges[:, 7])),
            float(np.sum(axial_stiffness)),
            float(np.sum(bending_stiffness)),
        ],
        dtype=np.float64,
    )
    if values.shape != (len(POOLED_FEATURE_NAMES),) or not np.all(np.isfinite(values)):
        raise ValueError("pooled frame features are invalid")
    return values


def _target_array(records: list[FrameGraphRecord]) -> FloatArray:
    return np.asarray(
        [
            [record.targets.max_displacement_mm, record.targets.max_utilization]
            for record in records
        ],
        dtype=np.float64,
    )


def _r2_score(actual: FloatArray, predicted: FloatArray) -> float:
    residual_sum = float(np.sum((actual - predicted) ** 2))
    total_sum = float(np.sum((actual - np.mean(actual)) ** 2))
    if total_sum <= np.finfo(np.float64).eps:
        return 0.0
    return 1.0 - residual_sum / total_sum


def run_ridge_baseline(
    split: FrameDatasetSplit,
    *,
    alpha: float = 1.0,
) -> RidgeBaselineResult:
    """Fit a pooled-feature multi-output ridge baseline; this is not a GNN."""

    if alpha < 0:
        raise ValueError("alpha must be non-negative")
    train_x = np.vstack([pooled_global_features(record) for record in split.train])
    test_x = np.vstack([pooled_global_features(record) for record in split.test])
    train_y = _target_array(split.train)
    test_y = _target_array(split.test)
    means = np.mean(train_x, axis=0)
    scales = np.std(train_x, axis=0)
    scales = np.where(scales > np.finfo(np.float64).eps, scales, 1.0)
    normalized_train = (train_x - means) / scales
    normalized_test = (test_x - means) / scales
    design_train = np.column_stack(
        [np.ones(normalized_train.shape[0], dtype=np.float64), normalized_train]
    )
    design_test = np.column_stack(
        [np.ones(normalized_test.shape[0], dtype=np.float64), normalized_test]
    )
    penalty = np.eye(design_train.shape[1], dtype=np.float64) * alpha
    penalty[0, 0] = 0.0
    coefficients = np.linalg.pinv(design_train.T @ design_train + penalty) @ (
        design_train.T @ train_y
    )
    predicted = cast(FloatArray, design_test @ coefficients)
    target_names = ["max_displacement_mm", "max_utilization"]
    metrics: dict[str, RegressionMetric] = {}
    for index, target_name in enumerate(target_names):
        actual_column = test_y[:, index]
        predicted_column = predicted[:, index]
        metrics[target_name] = RegressionMetric(
            mae=float(np.mean(np.abs(actual_column - predicted_column))),
            r2=_r2_score(actual_column, predicted_column),
        )
    predictions = [
        {
            "max_displacement_mm": float(row[0]),
            "max_utilization": float(row[1]),
        }
        for row in predicted
    ]
    return RidgeBaselineResult(
        alpha=alpha,
        feature_names=list(POOLED_FEATURE_NAMES),
        target_names=target_names,
        train_count=len(split.train),
        test_count=len(split.test),
        train_groups=split.train_groups,
        test_groups=split.test_groups,
        metrics=metrics,
        predictions=predictions,
    )


def topology_counts(records: list[FrameGraphRecord]) -> dict[str, int]:
    return dict(sorted(Counter(record.topology_group for record in records).items()))


__all__ = [
    "EDGE_FEATURE_NAMES",
    "FrameDatasetSplit",
    "FrameGraphDataset",
    "FrameGraphRecord",
    "FrameGraphTargets",
    "NODE_FEATURE_NAMES",
    "POOLED_FEATURE_NAMES",
    "RegressionMetric",
    "RidgeBaselineResult",
    "SOLVER_ID",
    "TOPOLOGY_FAMILIES",
    "generate_frame_dataset",
    "generate_pipe_rack_contract",
    "group_holdout_split",
    "pooled_global_features",
    "run_ridge_baseline",
    "topology_counts",
]

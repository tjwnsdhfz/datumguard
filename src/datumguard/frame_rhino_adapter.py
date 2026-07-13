from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import Field, ValidationError, field_validator, model_validator

from .frame_models import (
    FrameAnalysisLimits,
    FrameMember,
    FrameNodalLoad,
    FrameNode,
    FrameSupport,
    StructuralFrameContract,
)
from .frame_provenance import build_source_provenance
from .frame_service import validate_frame_contract
from .models import ContractMetadata, ContractStatus, Evidence, StrictModel, Violation

EXCHANGE_SCHEMA_VERSION = "1.0.0"
COORDINATE_GRID_MM = 0.001
PLANARITY_TOLERANCE_MM = 0.001
AXIS_TOLERANCE = 1.0e-9

_UNIT_TO_MM: dict[str, float] = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "ft": 304.8,
}

Vector3 = tuple[float, float, float]


def _finite_vector(value: Vector3) -> Vector3:
    if not all(math.isfinite(item) for item in value):
        raise ValueError("coordinates and datum vectors must be finite")
    return value


class RhinoDatum(StrictModel):
    """World-space Rhino datum used to express the structural XY work plane."""

    origin: Vector3
    x_axis: Vector3
    y_axis: Vector3
    z_axis: Vector3

    _validate_origin = field_validator("origin")(_finite_vector)
    _validate_x_axis = field_validator("x_axis")(_finite_vector)
    _validate_y_axis = field_validator("y_axis")(_finite_vector)
    _validate_z_axis = field_validator("z_axis")(_finite_vector)


class RhinoDocumentContext(StrictModel):
    document_id: str = Field(default="rhino-document", min_length=1, max_length=200)
    units: str = Field(default="unset", min_length=1, max_length=32)
    datum: RhinoDatum


class RhinoFrameSection(StrictModel):
    """Section geometry in powers of the Rhino document length unit."""

    id: str = Field(min_length=1, max_length=80)
    area: float = Field(gt=0, allow_inf_nan=False)
    inertia: float = Field(gt=0, allow_inf_nan=False)
    depth: float = Field(gt=0, allow_inf_nan=False)
    elastic_modulus_mpa: float = Field(default=200_000.0, gt=0, allow_inf_nan=False)
    allowable_stress_mpa: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class RhinoCenterlineMember(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    start: Vector3
    end: Vector3
    section_id: str = Field(min_length=1, max_length=80)
    locked: bool = True
    source_object_id: UUID | None = None

    _validate_start = field_validator("start")(_finite_vector)
    _validate_end = field_validator("end")(_finite_vector)


class RhinoSupportPoint(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    point: Vector3
    ux: bool = False
    uy: bool = False
    rz: bool = False
    source_object_id: UUID | None = None

    _validate_point = field_validator("point")(_finite_vector)


class RhinoLoadPoint(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    point: Vector3
    fx_n: float = 0.0
    fy_n: float = 0.0
    mz_n_document_unit: float = 0.0
    source_object_id: UUID | None = None

    _validate_point = field_validator("point")(_finite_vector)

    @field_validator("fx_n", "fy_n", "mz_n_document_unit")
    @classmethod
    def validate_load(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("loads must be finite")
        return value


class RhinoFrameLimits(StrictModel):
    max_displacement: float = Field(gt=0, allow_inf_nan=False)
    allowable_stress_mpa: float = Field(gt=0, allow_inf_nan=False)


class RhinoExchangeMetadata(StrictModel):
    project_name: str = Field(min_length=1, max_length=120)
    revision: str = Field(default="A", min_length=1, max_length=16)
    notes: str = Field(default="", max_length=1000)


class RhinoFrameExchange(StrictModel):
    """Versioned, Rhino-independent neutral exchange for straight 2D frame objects."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    design_kind: Literal["structural_frame_exchange"] = "structural_frame_exchange"
    document: RhinoDocumentContext
    sections: list[RhinoFrameSection] = Field(min_length=1, max_length=240)
    members: list[RhinoCenterlineMember] = Field(min_length=1, max_length=240)
    supports: list[RhinoSupportPoint] = Field(default_factory=list, max_length=120)
    loads: list[RhinoLoadPoint] = Field(default_factory=list, max_length=120)
    limits: RhinoFrameLimits
    metadata: RhinoExchangeMetadata
    node_merge_tolerance: float = Field(default=0.0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_ids_and_sections(self) -> RhinoFrameExchange:
        entity_ids = [item.id for item in self.sections]
        entity_ids.extend(item.id for item in self.members)
        entity_ids.extend(item.id for item in self.supports)
        entity_ids.extend(item.id for item in self.loads)
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("all Rhino exchange identifiers must be unique")
        section_ids = {item.id for item in self.sections}
        missing = sorted(
            {item.section_id for item in self.members if item.section_id not in section_ids}
        )
        if missing:
            raise ValueError(f"members reference unknown sections: {', '.join(missing)}")
        source_ids = [
            item.source_object_id for item in self.members if item.source_object_id is not None
        ]
        source_ids.extend(
            item.source_object_id for item in self.supports if item.source_object_id is not None
        )
        source_ids.extend(
            item.source_object_id for item in self.loads if item.source_object_id is not None
        )
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Rhino source object identifiers must be unique")
        return self


class RhinoAdapterResult(StrictModel):
    status: ContractStatus
    exchange_hash: str
    contract_hash: str | None = None
    normalized_exchange: RhinoFrameExchange | None = None
    structural_contract: StructuralFrameContract | None = None
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class RhinoExchangeError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        entity_ids: list[str] | None = None,
        details: dict[str, Any] | None = None,
        needs_confirmation: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.entity_ids = entity_ids or []
        self.details = details or {}
        self.needs_confirmation = needs_confirmation


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return cast(Vector3, tuple(a - b for a, b in zip(left, right, strict=True)))


def _length(value: Vector3) -> float:
    return math.sqrt(_dot(value, value))


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _quantize_mm(value: float) -> float:
    quantized = round(value / COORDINATE_GRID_MM) * COORDINATE_GRID_MM
    return 0.0 if abs(quantized) < COORDINATE_GRID_MM / 2 else round(quantized, 9)


def _canonical_json(value: Any) -> bytes:
    if isinstance(value, float):
        value = _canonical_value(value)
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list):
        value = [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        value = {key: _canonical_value(value[key]) for key in sorted(value)}
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _canonical_value(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            return f"nonfinite:{value}"
        return _quantize_mm(value)
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        items = [_canonical_value(item) for item in value]
        if all(isinstance(item, dict) and "id" in item for item in items):
            return sorted(items, key=lambda item: str(item["id"]))
        return items
    if isinstance(value, dict):
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    return value


def _exchange_hash(payload: RhinoFrameExchange | dict[str, Any]) -> str:
    if isinstance(payload, RhinoFrameExchange):
        value: Any = payload.model_dump(mode="json")
    else:
        value = payload
    return f"sha256:{hashlib.sha256(_canonical_json(value)).hexdigest()}"


def _exact_canonical_value(value: Any) -> Any:
    """Canonicalize source exchange identity without applying the 0.001 mm grid.

    The exchange hash represents the exact declared Rhino payload after schema defaults,
    while the downstream structural contract intentionally keeps its 0.001 mm hash grid.
    Datum axes, source-unit values, and load magnitudes therefore cannot collide merely
    because their difference is smaller than the normalized contract grid.
    """

    if isinstance(value, float):
        return value if math.isfinite(value) else f"nonfinite:{value}"
    if isinstance(value, tuple):
        return [_exact_canonical_value(item) for item in value]
    if isinstance(value, list):
        items = [_exact_canonical_value(item) for item in value]
        if all(isinstance(item, dict) and "id" in item for item in items):
            return sorted(items, key=lambda item: str(item["id"]))
        return items
    if isinstance(value, dict):
        return {key: _exact_canonical_value(value[key]) for key in sorted(value)}
    return value


def _exact_exchange_hash(exchange: RhinoFrameExchange) -> str:
    payload = json.dumps(
        _exact_canonical_value(exchange.model_dump(mode="json")),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _validate_datum(datum: RhinoDatum) -> None:
    axes = (datum.x_axis, datum.y_axis, datum.z_axis)
    if any(abs(_length(axis) - 1.0) > AXIS_TOLERANCE for axis in axes):
        raise RhinoExchangeError(
            "DG_FRAME_RHINO_DATUM_NONORTHONORMAL",
            "Rhino datum axes must be unit vectors.",
        )
    if any(
        abs(_dot(left, right)) > AXIS_TOLERANCE
        for left, right in (
            (datum.x_axis, datum.y_axis),
            (datum.x_axis, datum.z_axis),
            (datum.y_axis, datum.z_axis),
        )
    ):
        raise RhinoExchangeError(
            "DG_FRAME_RHINO_DATUM_NONORTHONORMAL",
            "Rhino datum axes must be mutually orthogonal.",
        )
    cross = _cross(datum.x_axis, datum.y_axis)
    if _dot(cross, datum.z_axis) < 1.0 - AXIS_TOLERANCE:
        raise RhinoExchangeError(
            "DG_FRAME_RHINO_DATUM_LEFT_HANDED",
            "Rhino datum must be right-handed.",
        )
    # FrameGuard MVP accepts an in-plane rotation, but not a tilted work plane.
    if (
        abs(datum.x_axis[2]) > AXIS_TOLERANCE
        or abs(datum.y_axis[2]) > AXIS_TOLERANCE
        or abs(datum.z_axis[0]) > AXIS_TOLERANCE
        or abs(datum.z_axis[1]) > AXIS_TOLERANCE
        or abs(datum.z_axis[2] - 1.0) > AXIS_TOLERANCE
    ):
        raise RhinoExchangeError(
            "DG_FRAME_RHINO_DATUM_NOT_XY",
            "FrameGuard MVP requires a datum parallel to the Rhino World XY plane.",
        )


def _to_local_mm(point: Vector3, datum: RhinoDatum, scale: float, entity_id: str) -> Vector3:
    relative = _subtract(point, datum.origin)
    local = (
        _dot(relative, datum.x_axis) * scale,
        _dot(relative, datum.y_axis) * scale,
        _dot(relative, datum.z_axis) * scale,
    )
    if abs(local[2]) > PLANARITY_TOLERANCE_MM:
        raise RhinoExchangeError(
            "DG_FRAME_RHINO_OUT_OF_PLANE",
            "A Rhino frame object is outside the structural XY work plane.",
            entity_ids=[entity_id],
            details={"local_z_mm": local[2], "tolerance_mm": PLANARITY_TOLERANCE_MM},
        )
    return local


def _distance_xy(left: Vector3, right: Vector3) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _node_id(point: tuple[float, float]) -> str:
    payload = f"{point[0]:.3f},{point[1]:.3f}".encode()
    return f"node-{hashlib.sha256(payload).hexdigest()[:16]}"


def _cluster_member_points(
    entries: list[tuple[str, str, Vector3]], tolerance_mm: float
) -> tuple[
    list[tuple[float, float]],
    list[list[Vector3]],
    dict[tuple[str, str], int],
]:
    count = len(entries)
    parents = list(range(count))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    exact_tolerance = max(tolerance_mm, 1.0e-12)
    for left in range(count):
        for right in range(left + 1, count):
            if _distance_xy(entries[left][2], entries[right][2]) <= exact_tolerance:
                union(left, right)

    groups: dict[int, list[int]] = {}
    for index in range(count):
        groups.setdefault(find(index), []).append(index)
    for indices in groups.values():
        diameter = max(
            (
                _distance_xy(entries[left][2], entries[right][2])
                for offset, left in enumerate(indices)
                for right in indices[offset + 1 :]
            ),
            default=0.0,
        )
        if diameter > exact_tolerance:
            raise RhinoExchangeError(
                "DG_FRAME_RHINO_NODE_CLUSTER_AMBIGUOUS",
                "Transitive point merging would exceed the explicit node tolerance.",
                entity_ids=sorted({entries[index][0] for index in indices}),
                details={"diameter_mm": diameter, "node_merge_tolerance_mm": tolerance_mm},
            )

    ordered_groups = sorted(
        groups.values(),
        key=lambda indices: min(
            (entries[index][2][0], entries[index][2][1], entries[index][0], entries[index][1])
            for index in indices
        ),
    )
    points: list[tuple[float, float]] = []
    samples: list[list[Vector3]] = []
    lookup: dict[tuple[str, str], int] = {}
    quantized_owner: dict[tuple[float, float], list[int]] = {}
    for group_index, indices in enumerate(ordered_groups):
        representative = min(
            (entries[index][2] for index in indices), key=lambda point: (point[0], point[1])
        )
        point = (_quantize_mm(representative[0]), _quantize_mm(representative[1]))
        quantized_owner.setdefault(point, []).append(group_index)
        points.append(point)
        samples.append([entries[index][2] for index in indices])
        for index in indices:
            lookup[(entries[index][0], entries[index][1])] = group_index
    collision = next(
        ((point, owners) for point, owners in quantized_owner.items() if len(owners) > 1), None
    )
    if collision:
        raise RhinoExchangeError(
            "DG_FRAME_RHINO_QUANTIZATION_COLLISION",
            "Distinct Rhino nodes collapse on the 0.001 mm contract grid.",
            details={"point_mm": collision[0], "node_merge_tolerance_mm": tolerance_mm},
        )
    return points, samples, lookup


def _find_node(
    point: Vector3,
    node_samples: list[list[Vector3]],
    tolerance_mm: float,
    entity_id: str,
) -> int:
    exact_tolerance = max(tolerance_mm, 1.0e-12)
    matches = [
        index
        for index, samples in enumerate(node_samples)
        if any(_distance_xy(point, sample) <= exact_tolerance for sample in samples)
    ]
    if not matches:
        raise RhinoExchangeError(
            "DG_FRAME_RHINO_POINT_NOT_ON_NODE",
            "A Rhino support or load point does not match a member endpoint.",
            entity_ids=[entity_id],
            details={"node_merge_tolerance_mm": tolerance_mm},
        )
    if len(matches) > 1:
        raise RhinoExchangeError(
            "DG_FRAME_RHINO_POINT_AMBIGUOUS",
            "A Rhino support or load point matches more than one structural node.",
            entity_ids=[entity_id],
            details={"candidate_count": len(matches)},
        )
    return matches[0]


def _parse_exchange(payload: RhinoFrameExchange | dict[str, Any]) -> RhinoFrameExchange:
    if isinstance(payload, RhinoFrameExchange):
        return payload
    return RhinoFrameExchange.model_validate(payload)


def _validation_violations(exc: ValidationError) -> list[Violation]:
    return [
        Violation(
            code="DG_FRAME_RHINO_SCHEMA_INVALID",
            message="Rhino frame exchange does not match schema version 1.0.0.",
            details={"errors": exc.errors(include_url=False)},
        )
    ]


def _iter_exchange_points(exchange: RhinoFrameExchange) -> Iterable[tuple[str, Vector3]]:
    for member in exchange.members:
        yield member.id, member.start
        yield member.id, member.end
    for support in exchange.supports:
        yield support.id, support.point
    for load in exchange.loads:
        yield load.id, load.point


def adapt_rhino_frame_exchange(
    payload: RhinoFrameExchange | dict[str, Any],
    *,
    provenance_bound: bool = False,
) -> RhinoAdapterResult:
    """Validate and deterministically normalize Rhino/Grasshopper data into FrameGuard.

    No unit, datum, topology, or proximity value is inferred. Unsupported units return
    ``needs_confirmation`` and all other geometry ambiguity fails closed.
    """

    exchange_hash = _exchange_hash(payload)
    try:
        exchange = _parse_exchange(payload)
    except ValidationError as exc:
        return RhinoAdapterResult(
            status=ContractStatus.INFEASIBLE,
            exchange_hash=exchange_hash,
            violations=_validation_violations(exc),
        )
    # The legacy adapter retains its v0.3 quantized identity. The new one-step round-trip
    # opts into an exact source identity so sub-grid source changes remain detectable.
    exchange_hash = (
        _exact_exchange_hash(exchange) if provenance_bound else _exchange_hash(exchange)
    )

    unit_key = exchange.document.units.strip().lower()
    if unit_key not in _UNIT_TO_MM:
        return RhinoAdapterResult(
            status=ContractStatus.NEEDS_CONFIRMATION,
            exchange_hash=exchange_hash,
            normalized_exchange=exchange,
            violations=[
                Violation(
                    code="DG_FRAME_RHINO_UNIT_CONFIRMATION_REQUIRED",
                    message="Rhino document units must be explicitly mm, cm, m, in, or ft.",
                    details={
                        "provided": exchange.document.units,
                        "supported": sorted(_UNIT_TO_MM),
                    },
                )
            ],
            evidence=[
                Evidence(
                    type="unit_gate",
                    source="rhino_frame_exchange_adapter",
                    details={"inferred": False, "official_contract_created": False},
                )
            ],
        )

    scale = _UNIT_TO_MM[unit_key]
    try:
        _validate_datum(exchange.document.datum)
        local_points = {
            (entity_id, occurrence): _to_local_mm(point, exchange.document.datum, scale, entity_id)
            for occurrence, (entity_id, point) in enumerate(_iter_exchange_points(exchange))
        }
        member_entries: list[tuple[str, str, Vector3]] = []
        occurrence = 0
        for member in exchange.members:
            member_entries.append((member.id, "start", local_points[(member.id, occurrence)]))
            occurrence += 1
            member_entries.append((member.id, "end", local_points[(member.id, occurrence)]))
            occurrence += 1
        tolerance_mm = exchange.node_merge_tolerance * scale
        node_points, node_samples, member_lookup = _cluster_member_points(
            member_entries, tolerance_mm
        )
        node_ids = [_node_id(point) for point in node_points]
        sections = {section.id: section for section in exchange.sections}
        members: list[FrameMember] = []
        for member in exchange.members:
            start_index = member_lookup[(member.id, "start")]
            end_index = member_lookup[(member.id, "end")]
            if start_index == end_index:
                raise RhinoExchangeError(
                    "DG_FRAME_RHINO_ZERO_LENGTH",
                    "A Rhino centerline collapses to one structural node.",
                    entity_ids=[member.id],
                )
            section = sections[member.section_id]
            members.append(
                FrameMember(
                    id=member.id,
                    start_node_id=node_ids[start_index],
                    end_node_id=node_ids[end_index],
                    area_mm2=_quantize_mm(section.area * scale**2),
                    inertia_mm4=_quantize_mm(section.inertia * scale**4),
                    elastic_modulus_mpa=section.elastic_modulus_mpa,
                    section_depth_mm=_quantize_mm(section.depth * scale),
                    allowable_stress_mpa=section.allowable_stress_mpa,
                    locked=member.locked,
                )
            )

        member_point_count = len(exchange.members) * 2
        supports: list[FrameSupport] = []
        for offset, support in enumerate(exchange.supports):
            point = local_points[(support.id, member_point_count + offset)]
            node_index = _find_node(point, node_samples, tolerance_mm, support.id)
            supports.append(
                FrameSupport(
                    id=support.id,
                    node_id=node_ids[node_index],
                    ux=support.ux,
                    uy=support.uy,
                    rz=support.rz,
                )
            )
        loads: list[FrameNodalLoad] = []
        load_start = member_point_count + len(exchange.supports)
        for offset, load in enumerate(exchange.loads):
            point = local_points[(load.id, load_start + offset)]
            node_index = _find_node(point, node_samples, tolerance_mm, load.id)
            loads.append(
                FrameNodalLoad(
                    id=load.id,
                    node_id=node_ids[node_index],
                    fx_n=load.fx_n,
                    fy_n=load.fy_n,
                    mz_nmm=load.mz_n_document_unit * scale,
                )
            )

        provenance = (
            build_source_provenance(exchange, exchange_hash) if provenance_bound else None
        )
        contract = StructuralFrameContract(
            nodes=[
                FrameNode(id=node_id, point=point, locked=True)
                for node_id, point in zip(node_ids, node_points, strict=True)
            ],
            members=members,
            supports=supports,
            loads=loads,
            limits=FrameAnalysisLimits(
                max_displacement_mm=_quantize_mm(exchange.limits.max_displacement * scale),
                allowable_stress_mpa=exchange.limits.allowable_stress_mpa,
            ),
            metadata=ContractMetadata(
                project_name=exchange.metadata.project_name,
                revision=exchange.metadata.revision,
                notes=exchange.metadata.notes,
            ),
            provenance=provenance,
        )
        validation = validate_frame_contract(contract)
        normalized = validation.normalized_contract
        return RhinoAdapterResult(
            status=validation.status,
            exchange_hash=exchange_hash,
            contract_hash=validation.contract_hash,
            normalized_exchange=exchange,
            structural_contract=normalized,
            violations=validation.violations,
            evidence=[
                Evidence(
                    type="rhino_frame_exchange_normalization",
                    source="rhino_frame_exchange_adapter",
                    details={
                        "schema_version": EXCHANGE_SCHEMA_VERSION,
                        "source_unit": unit_key,
                        "target_unit": "mm",
                        "unit_scale": scale,
                        "coordinate_grid_mm": COORDINATE_GRID_MM,
                        "planarity_tolerance_mm": PLANARITY_TOLERANCE_MM,
                        "node_merge_tolerance_mm": tolerance_mm,
                        "datum_inferred": False,
                        "unit_inferred": False,
                        "exchange_hash": exchange_hash,
                        "source_document_id": exchange.document.document_id,
                        "source_object_count": (
                            len(provenance.objects) if provenance is not None else 0
                        ),
                        "provenance_complete": (
                            provenance.complete if provenance is not None else False
                        ),
                        "provenance_bound": provenance_bound,
                    },
                ),
                *validation.evidence,
            ],
        )
    except RhinoExchangeError as exc:
        return RhinoAdapterResult(
            status=(
                ContractStatus.NEEDS_CONFIRMATION
                if exc.needs_confirmation
                else ContractStatus.INFEASIBLE
            ),
            exchange_hash=exchange_hash,
            normalized_exchange=exchange,
            violations=[
                Violation(
                    code=exc.code,
                    message=exc.message,
                    entity_ids=exc.entity_ids,
                    details=exc.details,
                )
            ],
            evidence=[
                Evidence(
                    type="rhino_frame_exchange_rejected",
                    source="rhino_frame_exchange_adapter",
                    details={"official_contract_created": False, "fail_closed": True},
                )
            ],
        )
    except ValidationError as exc:
        return RhinoAdapterResult(
            status=ContractStatus.INFEASIBLE,
            exchange_hash=exchange_hash,
            normalized_exchange=exchange,
            violations=[
                Violation(
                    code="DG_FRAME_RHINO_NORMALIZATION_INVALID",
                    message="Rhino values cannot form a valid normalized structural contract.",
                    details={"errors": exc.errors(include_url=False)},
                )
            ],
            evidence=[
                Evidence(
                    type="rhino_frame_exchange_rejected",
                    source="rhino_frame_exchange_adapter",
                    details={"official_contract_created": False, "fail_closed": True},
                )
            ],
        )


__all__ = [
    "AXIS_TOLERANCE",
    "COORDINATE_GRID_MM",
    "EXCHANGE_SCHEMA_VERSION",
    "PLANARITY_TOLERANCE_MM",
    "RhinoAdapterResult",
    "RhinoCenterlineMember",
    "RhinoDatum",
    "RhinoDocumentContext",
    "RhinoExchangeMetadata",
    "RhinoFrameExchange",
    "RhinoFrameLimits",
    "RhinoFrameSection",
    "RhinoLoadPoint",
    "RhinoSupportPoint",
    "adapt_rhino_frame_exchange",
]

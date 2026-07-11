from __future__ import annotations

import io
import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from ezdxf import units
from ezdxf.entities.circle import Circle
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.filemanagement import read
from ezdxf.lldxf.const import DXFError, DXFValueError
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry

from .artifacts import DXF_LAYERS, XDATA_APP_ID
from .core import compute_artifact_hash
from .models import (
    CircularPattern,
    DesignContract,
    Evidence,
    LinearPattern,
    Measurement,
    RunStatus,
    Violation,
)

VERIFY_EPSILON_MM = 0.001


class DxfReadError(ValueError):
    """Raised when a DXF cannot be parsed into the independent evidence model."""


@dataclass(frozen=True)
class RemeasuredEntity:
    feature_id: str
    feature_type: str
    geometry: BaseGeometry
    values: dict[str, float]


@dataclass(frozen=True)
class VerificationResult:
    status: RunStatus
    contract_hash: str
    artifact_hash: str
    measurements: list[Measurement]
    violations: list[Violation]
    evidence: list[Evidence]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "contract_hash": self.contract_hash,
            "artifact_hash": self.artifact_hash,
            "measurements": [item.model_dump(mode="json") for item in self.measurements],
            "violations": [item.model_dump(mode="json") for item in self.violations],
            "evidence": [item.model_dump(mode="json") for item in self.evidence],
            "error": None,
        }


def _xdata(entity: Circle | LWPolyline) -> dict[str, str]:
    try:
        tags = entity.get_xdata(XDATA_APP_ID)
    except DXFValueError:
        return {}
    result: dict[str, str] = {}
    for tag in tags:
        if tag.code == 1000 and isinstance(tag.value, str) and "=" in tag.value:
            key, value = tag.value.split("=", 1)
            result[key] = value
    return result


def _oriented_dimensions(polygon: Polygon) -> tuple[float, float]:
    rectangle = polygon.minimum_rotated_rectangle
    points = list(rectangle.exterior.coords)
    lengths = [
        math.dist(points[index], points[index + 1]) for index in range(min(4, len(points) - 1))
    ]
    return (max(lengths), min(lengths))


def _read_entities(
    dxf_bytes: bytes,
    expected_contract_hash: str,
) -> tuple[dict[str, RemeasuredEntity], list[Violation], list[Evidence]]:
    try:
        document = read(io.StringIO(dxf_bytes.decode("utf-8")))
    except (UnicodeDecodeError, DXFError, ValueError) as exc:
        raise DxfReadError("DXF parsing failed") from exc

    violations: list[Violation] = []
    evidence: list[Evidence] = []
    layer_names = {layer.dxf.name for layer in document.layers}
    missing_layers = sorted(set(DXF_LAYERS) - layer_names)
    if missing_layers:
        violations.append(
            Violation(
                code="DG_DXF_LAYER_MISSING",
                message="필수 DXF 레이어가 없습니다.",
                details={"missing_layers": missing_layers},
            )
        )
    if document.dxfversion != "AC1027":
        violations.append(
            Violation(
                code="DG_DXF_VERSION_INVALID",
                message="DXF 버전이 R2013이 아닙니다.",
                details={"actual": document.dxfversion, "expected": "AC1027"},
            )
        )
    if document.units != units.MM:
        violations.append(
            Violation(
                code="DG_DXF_UNIT_INVALID",
                message="DXF 모델 공간 단위가 millimeter가 아닙니다.",
                details={"actual": document.units, "expected": units.MM},
            )
        )

    result: dict[str, RemeasuredEntity] = {}
    for entity in document.modelspace():
        if entity.dxf.layer not in {"OUTLINE", "CUT"}:
            continue
        if not isinstance(entity, Circle | LWPolyline):
            violations.append(
                Violation(
                    code="DG_DXF_ENTITY_UNSUPPORTED",
                    message="검증 경로에서 지원하지 않는 DXF entity입니다.",
                    details={"entity_type": entity.dxftype(), "layer": entity.dxf.layer},
                )
            )
            continue
        metadata = _xdata(entity)
        feature_id = metadata.get("feature_id")
        feature_type = metadata.get("feature_type")
        if not feature_id or not feature_type:
            violations.append(
                Violation(
                    code="DG_DXF_XDATA_MISSING",
                    message="DXF entity에 DatumGuard 식별 XDATA가 없습니다.",
                    details={"handle": entity.dxf.handle},
                )
            )
            continue
        if metadata.get("contract_hash") != expected_contract_hash:
            violations.append(
                Violation(
                    code="DG_CONTRACT_HASH_MISMATCH",
                    message="DXF XDATA의 contract hash가 요청과 다릅니다.",
                    entity_ids=[feature_id],
                    details={
                        "actual": metadata.get("contract_hash"),
                        "expected": expected_contract_hash,
                    },
                )
            )
        if feature_id in result:
            violations.append(
                Violation(
                    code="DG_DXF_ID_DUPLICATE",
                    message="CUT/OUTLINE entity의 feature ID가 중복됩니다.",
                    entity_ids=[feature_id],
                )
            )
            continue

        if isinstance(entity, Circle):
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            geometry: BaseGeometry = Point(float(center.x), float(center.y)).buffer(
                radius,
                quad_segs=64,
            )
            values = {
                "center.0": float(center.x),
                "center.1": float(center.y),
                "diameter": radius * 2.0,
                "width": radius * 2.0,
                "height": radius * 2.0,
            }
        else:
            points = [(float(x), float(y)) for x, y in entity.get_points("xy")]
            if len(points) < 3 or not entity.closed:
                violations.append(
                    Violation(
                        code="DG_DXF_POLYLINE_OPEN",
                        message="외곽 또는 절단 polyline이 닫혀 있지 않습니다.",
                        entity_ids=[feature_id],
                    )
                )
                continue
            polygon = Polygon(points)
            if not polygon.is_valid or polygon.is_empty:
                violations.append(
                    Violation(
                        code="DG_DXF_GEOMETRY_INVALID",
                        message="DXF에서 재구성한 polygon이 유효하지 않습니다.",
                        entity_ids=[feature_id],
                    )
                )
                continue
            geometry = polygon
            min_x, min_y, max_x, max_y = polygon.bounds
            centroid = polygon.centroid
            oriented_length, oriented_width = _oriented_dimensions(polygon)
            values = {
                "origin.0": min_x,
                "origin.1": min_y,
                "center.0": centroid.x,
                "center.1": centroid.y,
                "width": max_x - min_x,
                "height": max_y - min_y,
                "length": oriented_length,
                "oriented_width": oriented_width,
            }
            if feature_type == "slot":
                values["width"] = oriented_width
                values["height"] = oriented_width

        result[feature_id] = RemeasuredEntity(
            feature_id=feature_id,
            feature_type=feature_type,
            geometry=geometry,
            values=values,
        )

    evidence.append(
        Evidence(
            type="dxf_round_trip",
            source="independent_ezdxf_reader",
            locator="drawing.dxf",
            details={
                "dxf_version": document.dxfversion,
                "units": "mm" if document.units == units.MM else document.units,
                "remeasured_entity_count": len(result),
            },
        )
    )
    return result, violations, evidence


def _entity_center(entity: RemeasuredEntity) -> tuple[float, float]:
    return (entity.values["center.0"], entity.values["center.1"])


def _actual_for_path(
    contract: DesignContract,
    entities: dict[str, RemeasuredEntity],
    path: str,
) -> tuple[float, list[str]]:
    parts = path.split(".")
    if parts[0] == "outline" and len(parts) >= 2:
        entity = entities[contract.outline.id]
        key = ".".join(parts[1:])
        return entity.values[key], [entity.feature_id]
    if len(parts) >= 3 and parts[0] == "features":
        feature_id = parts[1]
        key = ".".join(parts[2:])
        maybe_entity = entities.get(feature_id)
        if maybe_entity is not None and key in maybe_entity.values:
            return maybe_entity.values[key], [maybe_entity.feature_id]

        feature = next((item for item in contract.features if item.id == feature_id), None)
        if isinstance(feature, LinearPattern) and key == "spacing":
            source = entities[feature.source_feature_id]
            clone = entities[f"{feature.id}__2"]
            sx, sy = _entity_center(source)
            cx, cy = _entity_center(clone)
            projected = (cx - sx) * feature.direction[0] + (cy - sy) * feature.direction[1]
            return projected, [source.feature_id, clone.feature_id]
        if isinstance(feature, CircularPattern) and key == "angle_step_deg":
            source = entities[feature.source_feature_id]
            clone = entities[f"{feature.id}__2"]
            sx, sy = _entity_center(source)
            cx, cy = _entity_center(clone)
            start = math.degrees(math.atan2(sy - feature.center[1], sx - feature.center[0]))
            end = math.degrees(math.atan2(cy - feature.center[1], cx - feature.center[0]))
            return (end - start) % 360.0, [source.feature_id, clone.feature_id]
    raise KeyError(path)


def _dimension_measurements(
    contract: DesignContract,
    entities: dict[str, RemeasuredEntity],
) -> tuple[list[Measurement], list[Violation]]:
    measurements: list[Measurement] = []
    violations: list[Violation] = []
    free_paths = {parameter.path for parameter in contract.free_parameters}
    for dimension in contract.dimensions:
        try:
            actual, entity_ids = _actual_for_path(contract, entities, dimension.path)
        except (KeyError, IndexError):
            violations.append(
                Violation(
                    code="DG_DIMENSION_PATH_INVALID",
                    message="DXF 재측정에서 dimension path를 찾을 수 없습니다.",
                    entity_ids=[],
                    repairable=False,
                    details={"dimension_id": dimension.id, "path": dimension.path},
                )
            )
            continue
        deviation = actual - dimension.target
        passed = (
            deviation >= dimension.tolerance_lower - VERIFY_EPSILON_MM
            and deviation <= dimension.tolerance_upper + VERIFY_EPSILON_MM
        )
        measurement = Measurement(
            measurement_id=f"measurement-{dimension.id}",
            dimension_id=dimension.id,
            target=round(dimension.target, 6),
            actual=round(actual, 6),
            deviation=round(deviation, 6),
            tolerance_lower=dimension.tolerance_lower,
            tolerance_upper=dimension.tolerance_upper,
            passed=passed,
            evidence={
                "artifact": "drawing.dxf",
                "entities": entity_ids,
                "method": "dxf_geometry_remeasurement",
                "path": dimension.path,
            },
        )
        measurements.append(measurement)
        if not passed:
            repairable = not dimension.locked and dimension.path in free_paths
            violations.append(
                Violation(
                    code="DG_TOLERANCE_EXCEEDED",
                    message="DXF 재측정값이 지정 공차를 벗어났습니다.",
                    entity_ids=entity_ids,
                    repairable=repairable,
                    details={
                        "dimension_id": dimension.id,
                        "path": dimension.path,
                        "target": dimension.target,
                        "actual": actual,
                        "deviation": deviation,
                        "locked": dimension.locked,
                    },
                )
            )
    return measurements, violations


def _geometry_violations(
    contract: DesignContract,
    entities: dict[str, RemeasuredEntity],
) -> list[Violation]:
    violations: list[Violation] = []
    outline = entities.get(contract.outline.id)
    if outline is None:
        return [
            Violation(
                code="DG_OUTLINE_MISSING",
                message="DXF에서 계약의 outline을 찾을 수 없습니다.",
                entity_ids=[contract.outline.id],
            )
        ]
    features = [item for key, item in entities.items() if key != contract.outline.id]
    free_paths = {parameter.path for parameter in contract.free_parameters}

    edge_distance = 0.0
    for constraint in contract.constraints:
        if constraint.type in {"features_inside_outline", "minimum_edge_distance"}:
            edge_distance = max(
                edge_distance,
                float(constraint.parameters.get("minimum_edge_distance", 0.0)),
                float(constraint.parameters.get("target", 0.0)),
            )

    for feature in features:
        is_inside = outline.geometry.covers(feature.geometry)
        actual_edge = outline.geometry.boundary.distance(feature.geometry) if is_inside else -1.0
        if not is_inside or actual_edge + VERIFY_EPSILON_MM < edge_distance:
            repairable = any(
                path.startswith(f"features.{feature.feature_id}.") for path in free_paths
            )
            violations.append(
                Violation(
                    code="DG_FEATURE_OUTSIDE_OUTLINE" if not is_inside else "DG_EDGE_DISTANCE",
                    message=(
                        "절단 feature가 outline 밖에 있습니다."
                        if not is_inside
                        else "Feature의 edge distance가 요구값보다 작습니다."
                    ),
                    entity_ids=[feature.feature_id, outline.feature_id],
                    repairable=repairable,
                    details={
                        "actual_edge_distance": actual_edge,
                        "required_edge_distance": edge_distance,
                    },
                )
            )

    required_ligament = contract.manufacturing_profile.minimum_ligament
    for constraint in contract.constraints:
        if constraint.type in {"non_overlap", "minimum_ligament"}:
            required_ligament = max(
                required_ligament,
                float(constraint.parameters.get("minimum_ligament", 0.0)),
                float(constraint.parameters.get("target", 0.0)),
            )

    for first, second in combinations(features, 2):
        distance = first.geometry.distance(second.geometry)
        if (
            first.geometry.intersects(second.geometry)
            or distance + VERIFY_EPSILON_MM < required_ligament
        ):
            repairable = any(
                path.startswith(f"features.{feature_id}.")
                for feature_id in (first.feature_id, second.feature_id)
                for path in free_paths
            )
            violations.append(
                Violation(
                    code="DG_FEATURE_OVERLAP"
                    if first.geometry.intersects(second.geometry)
                    else "DG_LIGAMENT",
                    message=(
                        "절단 feature가 서로 겹칩니다."
                        if first.geometry.intersects(second.geometry)
                        else "Feature 사이 ligament가 요구값보다 작습니다."
                    ),
                    entity_ids=[first.feature_id, second.feature_id],
                    repairable=repairable,
                    details={
                        "actual_ligament": 0.0
                        if first.geometry.intersects(second.geometry)
                        else distance,
                        "required_ligament": required_ligament,
                    },
                )
            )

    minimum_feature = contract.manufacturing_profile.minimum_feature
    for feature in features:
        if feature.feature_type == "circular_hole":
            actual = feature.values["diameter"]
        elif feature.feature_type == "slot":
            actual = feature.values["width"]
        else:
            actual = min(feature.values["width"], feature.values["height"])
        if actual + VERIFY_EPSILON_MM < minimum_feature:
            violations.append(
                Violation(
                    code="DG_MINIMUM_FEATURE",
                    message="Feature 크기가 manufacturing profile의 minimum feature보다 작습니다.",
                    entity_ids=[feature.feature_id],
                    details={"actual": actual, "required": minimum_feature},
                )
            )
    return violations


def _declared_constraint_violations(
    contract: DesignContract,
    entities: dict[str, RemeasuredEntity],
) -> list[Violation]:
    violations: list[Violation] = []
    outline = entities.get(contract.outline.id)
    if outline is None:
        return violations
    free_paths = {parameter.path for parameter in contract.free_parameters}
    pattern_by_id = {
        feature.id: feature
        for feature in contract.features
        if isinstance(feature, LinearPattern | CircularPattern)
    }

    for constraint in contract.constraints:
        if not constraint.required or constraint.type not in {
            "alignment",
            "equal_spacing",
            "symmetry",
        }:
            continue
        selected_ids: set[str] = set()
        for requested_id in constraint.entity_ids:
            if requested_id in entities and requested_id != contract.outline.id:
                selected_ids.add(requested_id)
            pattern = pattern_by_id.get(requested_id)
            if pattern is not None:
                selected_ids.add(pattern.source_feature_id)
                selected_ids.update(
                    entity_id for entity_id in entities if entity_id.startswith(f"{pattern.id}__")
                )
        selected = [entities[feature_id] for feature_id in sorted(selected_ids)]
        centers = [
            (entity.feature_id, (entity.geometry.centroid.x, entity.geometry.centroid.y))
            for entity in selected
        ]
        repairable = any(
            path.startswith(f"features.{feature_id}.")
            for feature_id, _center in centers
            for path in free_paths
        )
        axis = str(constraint.parameters.get("axis", "x")).lower()
        axis_index = 0 if axis == "x" else 1
        tolerance = float(constraint.parameters.get("tolerance", VERIFY_EPSILON_MM))

        if constraint.type == "alignment" and len(centers) >= 2:
            coordinates = [center[axis_index] for _feature_id, center in centers]
            target = constraint.parameters.get("axis_value")
            deviation = (
                max(abs(value - float(target)) for value in coordinates)
                if isinstance(target, int | float)
                else max(coordinates) - min(coordinates)
            )
            if deviation > tolerance + VERIFY_EPSILON_MM:
                violations.append(
                    Violation(
                        code="DG_ALIGNMENT",
                        message="DXF 재측정 중심이 선언된 축 정렬 공차를 벗어났습니다.",
                        entity_ids=[feature_id for feature_id, _center in centers],
                        constraint_id=constraint.id,
                        repairable=repairable,
                        details={
                            "axis": axis,
                            "actual_spread": deviation,
                            "tolerance": tolerance,
                        },
                    )
                )
        elif constraint.type == "equal_spacing" and len(centers) >= 3:
            coordinates = sorted(center[axis_index] for _feature_id, center in centers)
            gaps = [
                second - first for first, second in zip(coordinates, coordinates[1:], strict=False)
            ]
            deviation = max(gaps) - min(gaps)
            if deviation > tolerance + VERIFY_EPSILON_MM:
                violations.append(
                    Violation(
                        code="DG_EQUAL_SPACING",
                        message="DXF 재측정 중심 간격이 동일 간격 공차를 벗어났습니다.",
                        entity_ids=[feature_id for feature_id, _center in centers],
                        constraint_id=constraint.id,
                        repairable=repairable,
                        details={"axis": axis, "gaps": gaps, "tolerance": tolerance},
                    )
                )
        elif constraint.type == "symmetry" and centers:
            outline_center = outline.geometry.centroid
            default_axis_value = outline_center.x if axis_index == 0 else outline_center.y
            axis_value = float(constraint.parameters.get("axis_value", default_axis_value))
            unmatched: list[str] = []
            for feature_id, center in centers:
                reflected = list(center)
                reflected[axis_index] = axis_value * 2 - reflected[axis_index]
                nearest = min(
                    math.dist(reflected, candidate) for _candidate_id, candidate in centers
                )
                if nearest > tolerance + VERIFY_EPSILON_MM:
                    unmatched.append(feature_id)
            if unmatched:
                violations.append(
                    Violation(
                        code="DG_SYMMETRY",
                        message="DXF 재측정 배치가 선언된 대칭축 공차를 벗어났습니다.",
                        entity_ids=unmatched,
                        constraint_id=constraint.id,
                        repairable=repairable,
                        details={
                            "axis": axis,
                            "axis_value": axis_value,
                            "tolerance": tolerance,
                        },
                    )
                )
    return violations


def _deduplicate_violations(violations: list[Violation]) -> list[Violation]:
    result: list[Violation] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for violation in violations:
        key = (violation.code, tuple(sorted(violation.entity_ids)))
        if key not in seen:
            seen.add(key)
            result.append(violation)
    return result


def verify_dxf(
    contract: DesignContract,
    dxf_bytes: bytes,
    contract_hash: str,
) -> VerificationResult:
    artifact_hash = compute_artifact_hash(dxf_bytes)
    entities, violations, evidence = _read_entities(dxf_bytes, contract_hash)
    measurements, dimension_violations = _dimension_measurements(contract, entities)
    violations.extend(dimension_violations)
    violations.extend(_geometry_violations(contract, entities))
    violations.extend(_declared_constraint_violations(contract, entities))
    violations = _deduplicate_violations(violations)
    if not violations:
        status = RunStatus.PASSED
    elif all(item.repairable for item in violations):
        status = RunStatus.REPAIRABLE
    else:
        status = RunStatus.FAILED
    evidence.append(
        Evidence(
            type="artifact_digest",
            source="sha256",
            locator="drawing.dxf",
            details={"artifact_hash": artifact_hash},
        )
    )
    return VerificationResult(
        status=status,
        contract_hash=contract_hash,
        artifact_hash=artifact_hash,
        measurements=measurements,
        violations=violations,
        evidence=evidence,
    )

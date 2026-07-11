from __future__ import annotations

import io
import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from ezdxf import units
from ezdxf.entities.circle import Circle
from ezdxf.entities.dxfentity import DXFEntity
from ezdxf.entities.line import Line
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.entities.point import Point as DXFPoint
from ezdxf.entities.text import Text
from ezdxf.filemanagement import read
from ezdxf.lldxf.const import DXFError, DXFValueError
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from .architecture_models import ArchitecturalPlanContract, RectangularColumn
from .core import compute_artifact_hash
from .models import Evidence, Measurement, RunStatus, Violation

VERIFY_EPSILON_MM = 0.001
_LAYERS = {
    "A-GRID",
    "A-WALL",
    "A-WALL-CENTER",
    "A-DOOR",
    "A-WIND",
    "A-COLS",
    "A-ROOM",
    "A-DIMS",
    "A-ANNO",
    "DG-META",
}
_PRIMARY_LAYERS = {"A-GRID", "A-WALL", "A-DOOR", "A-WIND", "A-COLS", "A-ROOM"}
_ANNOTATION_LAYERS = {"A-DIMS", "A-ANNO", "DG-META"}
_XDATA_APP_ID = "DATUMGUARD"


class ArchitecturalDxfReadError(ValueError):
    """Raised when the serialized architectural DXF cannot be independently parsed."""


@dataclass(frozen=True)
class ArchitecturalRemeasuredEntity:
    feature_id: str
    feature_type: str
    layer: str
    geometry: BaseGeometry
    values: dict[str, float]


@dataclass(frozen=True)
class ArchitecturalVerificationResult:
    status: RunStatus
    contract_hash: str
    artifact_hash: str
    measurements: list[Measurement]
    violations: list[Violation]
    evidence: list[Evidence]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "contract_hash": self.contract_hash,
            "artifact_hash": self.artifact_hash,
            "measurements": [item.model_dump(mode="json") for item in self.measurements],
            "violations": [item.model_dump(mode="json") for item in self.violations],
            "evidence": [item.model_dump(mode="json") for item in self.evidence],
            "summary": self.summary,
            "error": None,
        }


def _xdata(entity: DXFEntity) -> dict[str, str]:
    try:
        tags = entity.get_xdata(_XDATA_APP_ID)
    except DXFValueError:
        return {}
    result: dict[str, str] = {}
    for tag in tags:
        if tag.code == 1000 and isinstance(tag.value, str) and "=" in tag.value:
            key, value = tag.value.split("=", 1)
            result[key] = value
    return result


def _polygon_dimensions(polygon: Polygon) -> tuple[float, float]:
    points = list(polygon.minimum_rotated_rectangle.exterior.coords)
    lengths = [math.dist(points[index], points[index + 1]) for index in range(4)]
    return max(lengths), min(lengths)


def _read_serialized_entities(
    dxf_bytes: bytes,
    expected_contract_hash: str,
) -> tuple[dict[str, ArchitecturalRemeasuredEntity], list[Violation]]:
    try:
        document = read(io.StringIO(dxf_bytes.decode("utf-8")))
    except (UnicodeDecodeError, DXFError, ValueError) as exc:
        raise ArchitecturalDxfReadError("architectural DXF parsing failed") from exc

    violations: list[Violation] = []
    missing_layers = sorted(_LAYERS - {layer.dxf.name for layer in document.layers})
    if missing_layers:
        violations.append(
            Violation(
                code="DG_ARCH_DXF_LAYER_MISSING",
                message="필수 건축 DXF 레이어가 없습니다.",
                details={"missing_layers": missing_layers},
            )
        )
    if document.dxfversion != "AC1027":
        violations.append(
            Violation(
                code="DG_ARCH_DXF_VERSION_INVALID",
                message="건축 DXF 버전이 R2013이 아닙니다.",
                details={"actual": document.dxfversion, "expected": "AC1027"},
            )
        )
    if document.units != units.MM:
        violations.append(
            Violation(
                code="DG_ARCH_DXF_UNIT_INVALID",
                message="건축 DXF 모델 공간 단위가 millimeter가 아닙니다.",
                details={"actual": document.units, "expected": units.MM},
            )
        )

    entities: dict[str, ArchitecturalRemeasuredEntity] = {}
    for entity in document.modelspace():
        if entity.dxf.layer not in _LAYERS - _ANNOTATION_LAYERS:
            continue
        if not isinstance(entity, Circle | Line | LWPolyline | DXFPoint):
            violations.append(
                Violation(
                    code="DG_ARCH_DXF_ENTITY_UNSUPPORTED",
                    message="건축 검증 경로가 지원하지 않는 DXF entity입니다.",
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
                    code="DG_ARCH_DXF_XDATA_MISSING",
                    message="건축 DXF entity에 식별 XDATA가 없습니다.",
                    details={"handle": entity.dxf.handle},
                )
            )
            continue
        if metadata.get("design_kind") != "architectural_plan":
            violations.append(
                Violation(
                    code="DG_ARCH_DESIGN_KIND_MISMATCH",
                    message="DXF XDATA의 design_kind가 architectural_plan이 아닙니다.",
                    entity_ids=[feature_id],
                )
            )
        if metadata.get("contract_hash") != expected_contract_hash:
            violations.append(
                Violation(
                    code="DG_CONTRACT_HASH_MISMATCH",
                    message="건축 DXF XDATA hash가 contract와 다릅니다.",
                    entity_ids=[feature_id],
                    details={
                        "actual": metadata.get("contract_hash"),
                        "expected": expected_contract_hash,
                    },
                )
            )
        if feature_id in entities:
            violations.append(
                Violation(
                    code="DG_ARCH_ENTITY_ID_DUPLICATE",
                    message="건축 DXF entity ID가 중복됩니다.",
                    entity_ids=[feature_id],
                )
            )
            continue

        geometry: BaseGeometry
        values: dict[str, float]
        if isinstance(entity, Line):
            start = entity.dxf.start
            end = entity.dxf.end
            geometry = LineString([(float(start.x), float(start.y)), (float(end.x), float(end.y))])
            values = {
                "start.0": float(start.x),
                "start.1": float(start.y),
                "end.0": float(end.x),
                "end.1": float(end.y),
                "length": geometry.length,
            }
        elif isinstance(entity, DXFPoint):
            location = entity.dxf.location
            geometry = Point(float(location.x), float(location.y))
            values = {"point.0": float(location.x), "point.1": float(location.y)}
        elif isinstance(entity, Circle):
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            geometry = Point(float(center.x), float(center.y)).buffer(radius, quad_segs=64)
            values = {
                "center.0": float(center.x),
                "center.1": float(center.y),
                "diameter": radius * 2,
            }
        else:
            points = [(float(x), float(y)) for x, y in entity.get_points("xy")]
            if len(points) < 3 or not entity.closed:
                violations.append(
                    Violation(
                        code="DG_ARCH_DXF_POLYLINE_OPEN",
                        message="건축 형상 polyline이 닫혀 있지 않습니다.",
                        entity_ids=[feature_id],
                    )
                )
                continue
            polygon = Polygon(points)
            if polygon.is_empty or not polygon.is_valid:
                violations.append(
                    Violation(
                        code="DG_ARCH_DXF_GEOMETRY_INVALID",
                        message="직렬화된 건축 polygon이 유효하지 않습니다.",
                        entity_ids=[feature_id],
                    )
                )
                continue
            major, minor = _polygon_dimensions(polygon)
            geometry = polygon
            values = {
                "center.0": polygon.centroid.x,
                "center.1": polygon.centroid.y,
                "major": major,
                "minor": minor,
            }
        entities[feature_id] = ArchitecturalRemeasuredEntity(
            feature_id=feature_id,
            feature_type=feature_type,
            layer=entity.dxf.layer,
            geometry=geometry,
            values=values,
        )
    return entities, violations


def _expected_representations(
    contract: ArchitecturalPlanContract,
) -> set[tuple[str, str, str]]:
    expected = {(item.id, "grid", "A-GRID") for item in contract.grids}
    expected.update((item.id, "wall", "A-WALL") for item in contract.walls)
    expected.update((item.id, "wall_centerline", "A-WALL-CENTER") for item in contract.walls)
    expected.update(
        (
            item.id,
            item.type,
            "A-WIND" if item.type == "window" else "A-DOOR",
        )
        for item in contract.openings
    )
    expected.update((item.id, item.type, "A-COLS") for item in contract.columns)
    expected.update((item.id, "room_seed", "A-ROOM") for item in contract.room_seeds)
    if contract.drawing_profile.include_dimensions:
        expected.update((item.id, "dimension", "A-DIMS") for item in contract.dimensions)
    if contract.drawing_profile.include_room_labels:
        expected.update((item.id, "room_annotation", "A-ANNO") for item in contract.room_seeds)
    expected.add(("architectural-metadata", "metadata", "DG-META"))
    return expected


def _measure_serialized_entity(
    entity: DXFEntity,
    entity_id: str,
) -> tuple[BaseGeometry, dict[str, float]]:
    if isinstance(entity, Line):
        start = entity.dxf.start
        end = entity.dxf.end
        geometry = LineString([(float(start.x), float(start.y)), (float(end.x), float(end.y))])
        if geometry.length <= 0:
            raise ArchitecturalDxfReadError(f"zero-length serialized line: {entity_id}")
        return geometry, {
            "start.0": float(start.x),
            "start.1": float(start.y),
            "end.0": float(end.x),
            "end.1": float(end.y),
            "length": geometry.length,
        }
    if isinstance(entity, DXFPoint):
        location = entity.dxf.location
        geometry = Point(float(location.x), float(location.y))
        return geometry, {"point.0": geometry.x, "point.1": geometry.y}
    if isinstance(entity, Circle):
        center = entity.dxf.center
        radius = float(entity.dxf.radius)
        if radius <= 0:
            raise ArchitecturalDxfReadError(f"invalid serialized circle: {entity_id}")
        geometry = Point(float(center.x), float(center.y)).buffer(radius, quad_segs=64)
        return geometry, {
            "center.0": float(center.x),
            "center.1": float(center.y),
            "diameter": radius * 2,
        }
    if isinstance(entity, LWPolyline):
        points = [(float(x), float(y)) for x, y in entity.get_points("xy")]
        if len(points) < 3 or not entity.closed:
            raise ArchitecturalDxfReadError(f"open serialized polygon: {entity_id}")
        polygon = Polygon(points)
        if polygon.is_empty or not polygon.is_valid:
            raise ArchitecturalDxfReadError(f"invalid serialized polygon: {entity_id}")
        major, minor = _polygon_dimensions(polygon)
        return polygon, {
            "center.0": polygon.centroid.x,
            "center.1": polygon.centroid.y,
            "major": major,
            "minor": minor,
        }
    raise ArchitecturalDxfReadError(
        f"unsupported serialized entity {entity.dxftype()}: {entity_id}"
    )


def _read_serialized_entities_v2(
    contract: ArchitecturalPlanContract,
    dxf_bytes: bytes,
    expected_contract_hash: str,
) -> tuple[
    dict[str, ArchitecturalRemeasuredEntity],
    dict[str, ArchitecturalRemeasuredEntity],
    list[Violation],
]:
    try:
        document = read(io.StringIO(dxf_bytes.decode("utf-8")))
    except (UnicodeDecodeError, DXFError, ValueError) as exc:
        raise ArchitecturalDxfReadError("architectural DXF parsing failed") from exc

    violations: list[Violation] = []
    present_layers = {layer.dxf.name for layer in document.layers}
    missing_layers = sorted(_LAYERS - present_layers)
    if missing_layers:
        violations.append(
            Violation(
                code="DG_ARCH_DXF_LAYER_MISSING",
                message="Required architectural DXF layers are missing.",
                details={"missing_layers": missing_layers},
            )
        )
    if document.dxfversion != "AC1027":
        violations.append(
            Violation(
                code="DG_ARCH_DXF_VERSION_INVALID",
                message="Architectural DXF version must be R2013.",
                details={"actual": document.dxfversion, "expected": "AC1027"},
            )
        )
    if document.units != units.MM:
        violations.append(
            Violation(
                code="DG_ARCH_DXF_UNIT_INVALID",
                message="Architectural DXF modelspace units must be millimeters.",
                details={"actual": document.units, "expected": units.MM},
            )
        )

    expected = _expected_representations(contract)
    seen: set[tuple[str, str, str]] = set()
    entities: dict[str, ArchitecturalRemeasuredEntity] = {}
    centerlines: dict[str, ArchitecturalRemeasuredEntity] = {}
    for entity in document.modelspace():
        layer = entity.dxf.layer
        if layer not in _LAYERS:
            violations.append(
                Violation(
                    code="DG_ARCH_DXF_LAYER_INVALID",
                    message="An architectural DXF entity is on an unapproved layer.",
                    details={"layer": layer, "handle": entity.dxf.handle},
                )
            )
            continue
        metadata = _xdata(entity)
        entity_id = metadata.get("entity_id")
        entity_type = metadata.get("entity_type")
        if not entity_id or not entity_type:
            violations.append(
                Violation(
                    code="DG_ARCH_DXF_XDATA_MISSING",
                    message="An architectural DXF entity is missing identity XDATA.",
                    details={"layer": layer, "handle": entity.dxf.handle},
                )
            )
            continue
        if metadata.get("contract_hash") != expected_contract_hash:
            violations.append(
                Violation(
                    code="DG_CONTRACT_HASH_MISMATCH",
                    message=(
                        "Architectural DXF XDATA hash differs from the canonical contract hash."
                    ),
                    entity_ids=[entity_id],
                    details={
                        "actual": metadata.get("contract_hash"),
                        "expected": expected_contract_hash,
                    },
                )
            )
        if metadata.get("revision") != contract.metadata.revision:
            violations.append(
                Violation(
                    code="DG_ARCH_DXF_REVISION_MISMATCH",
                    message="Architectural DXF revision XDATA differs from the contract.",
                    entity_ids=[entity_id],
                )
            )
        if metadata.get("design_kind") != "architectural_plan":
            violations.append(
                Violation(
                    code="DG_ARCH_DESIGN_KIND_MISMATCH",
                    message="Architectural DXF design_kind XDATA is invalid.",
                    entity_ids=[entity_id],
                )
            )

        representation = (entity_id, entity_type, layer)
        if representation in seen:
            violations.append(
                Violation(
                    code="DG_ARCH_ENTITY_ID_DUPLICATE",
                    message="An architectural DXF representation is duplicated.",
                    entity_ids=[entity_id],
                    details={"entity_type": entity_type, "layer": layer},
                )
            )
            continue
        seen.add(representation)
        if representation not in expected:
            violations.append(
                Violation(
                    code="DG_ARCH_DXF_IDENTITY_MISMATCH",
                    message="Architectural DXF identity or layer differs from the contract.",
                    entity_ids=[entity_id],
                    details={"entity_type": entity_type, "layer": layer},
                )
            )

        if layer in _ANNOTATION_LAYERS:
            if not isinstance(entity, Text):
                violations.append(
                    Violation(
                        code="DG_ARCH_DXF_ENTITY_UNSUPPORTED",
                        message="Architectural annotations must be serialized as TEXT.",
                        entity_ids=[entity_id],
                    )
                )
            continue
        valid_type = (
            (layer in {"A-GRID", "A-WALL-CENTER"} and isinstance(entity, Line))
            or (layer == "A-ROOM" and isinstance(entity, DXFPoint))
            or (layer in {"A-WALL", "A-DOOR", "A-WIND"} and isinstance(entity, LWPolyline))
            or (layer == "A-COLS" and isinstance(entity, Circle | LWPolyline))
        )
        if not valid_type:
            violations.append(
                Violation(
                    code="DG_ARCH_DXF_ENTITY_UNSUPPORTED",
                    message="A serialized architectural entity has the wrong DXF type.",
                    entity_ids=[entity_id],
                    details={"entity_type": entity.dxftype(), "layer": layer},
                )
            )
            continue
        try:
            geometry, values = _measure_serialized_entity(entity, entity_id)
        except ArchitecturalDxfReadError as exc:
            violations.append(
                Violation(
                    code="DG_ARCH_DXF_GEOMETRY_INVALID",
                    message="Serialized architectural geometry is invalid.",
                    entity_ids=[entity_id],
                    details={"reason": str(exc)},
                )
            )
            continue
        measured = ArchitecturalRemeasuredEntity(
            feature_id=entity_id,
            feature_type=entity_type,
            layer=layer,
            geometry=geometry,
            values=values,
        )
        if layer == "A-WALL-CENTER":
            centerlines[entity_id] = measured
        elif layer in _PRIMARY_LAYERS:
            if entity_id in entities:
                violations.append(
                    Violation(
                        code="DG_ARCH_ENTITY_ID_DUPLICATE",
                        message="An architectural primary entity identifier is duplicated.",
                        entity_ids=[entity_id],
                    )
                )
            else:
                entities[entity_id] = measured

    missing_representations = sorted(expected - seen)
    if missing_representations:
        violations.append(
            Violation(
                code="DG_ARCH_ENTITY_MISSING",
                message="Serialized architectural DXF representations are missing.",
                entity_ids=sorted({item[0] for item in missing_representations}),
                details={"missing_representations": missing_representations},
            )
        )
    return entities, centerlines, violations


def _projected_values(
    entity: ArchitecturalRemeasuredEntity,
    start: tuple[float, float],
    end: tuple[float, float],
) -> dict[str, float]:
    if not isinstance(entity.geometry, Polygon):
        raise ArchitecturalDxfReadError("expected serialized polygon entity")
    expected_length = math.dist(start, end)
    ux = (end[0] - start[0]) / expected_length
    uy = (end[1] - start[1]) / expected_length
    nx, ny = -uy, ux
    points = list(entity.geometry.exterior.coords)[:-1]
    along = [point[0] * ux + point[1] * uy for point in points]
    across = [point[0] * nx + point[1] * ny for point in points]
    start_projection = min(along)
    end_projection = max(along)
    mid_across = (min(across) + max(across)) / 2.0
    return {
        "start_projection": start_projection,
        "end_projection": end_projection,
        "length": end_projection - start_projection,
        "thickness": max(across) - min(across),
        "start.0": ux * start_projection + nx * mid_across,
        "start.1": uy * start_projection + ny * mid_across,
        "end.0": ux * end_projection + nx * mid_across,
        "end.1": uy * end_projection + ny * mid_across,
    }


def _remeasured_value(
    contract: ArchitecturalPlanContract,
    entities: dict[str, ArchitecturalRemeasuredEntity],
    path: str,
) -> float:
    parts = path.split(".")
    if len(parts) < 3:
        raise KeyError(path)
    collection, entity_id = parts[0], parts[1]
    entity = entities.get(entity_id)
    if entity is None:
        raise KeyError(path)
    suffix = ".".join(parts[2:])
    if collection == "walls":
        wall = next(item for item in contract.walls if item.id == entity_id)
        return _projected_values(entity, wall.start, wall.end)[suffix]
    if collection == "openings":
        opening = next(item for item in contract.openings if item.id == entity_id)
        wall = next(item for item in contract.walls if item.id == opening.wall_id)
        wall_entity = entities[wall.id]
        wall_values = _projected_values(wall_entity, wall.start, wall.end)
        opening_values = _projected_values(entity, wall.start, wall.end)
        values = {
            "offset": opening_values["start_projection"] - wall_values["start_projection"],
            "width": opening_values["length"],
        }
        return values[suffix]
    if collection == "columns" and isinstance(
        next(item for item in contract.columns if item.id == entity_id), RectangularColumn
    ):
        column = next(item for item in contract.columns if item.id == entity_id)
        assert isinstance(column, RectangularColumn)
        angle = math.radians(column.rotation_deg)
        ux, uy = math.cos(angle), math.sin(angle)
        rectangle = entity.geometry.minimum_rotated_rectangle
        points = list(rectangle.exterior.coords)[:-1]
        along = [point[0] * ux + point[1] * uy for point in points]
        across = [-point[0] * uy + point[1] * ux for point in points]
        values = {
            "center.0": entity.geometry.centroid.x,
            "center.1": entity.geometry.centroid.y,
            "width": max(along) - min(along),
            "depth": max(across) - min(across),
        }
        return values[suffix]
    return entity.values[suffix]


def _constraint_violations(
    contract: ArchitecturalPlanContract,
    entities: dict[str, ArchitecturalRemeasuredEntity],
    centerlines: dict[str, ArchitecturalRemeasuredEntity],
) -> list[Violation]:
    violations: list[Violation] = []
    free_paths = {item.path for item in contract.free_parameters}
    walls = {wall.id: wall for wall in contract.walls}

    expected_ids = {
        *(item.id for item in contract.grids),
        *(item.id for item in contract.walls),
        *(item.id for item in contract.openings),
        *(item.id for item in contract.columns),
        *(item.id for item in contract.room_seeds),
    }
    missing = sorted(expected_ids - set(entities))
    if missing:
        violations.append(
            Violation(
                code="DG_ARCH_ENTITY_MISSING",
                message="직렬화된 DXF에 계약 entity가 없습니다.",
                entity_ids=missing,
            )
        )

    for first_entity, second_entity in combinations(entities.values(), 2):
        if first_entity.layer == second_entity.layer and first_entity.geometry.equals_exact(
            second_entity.geometry, VERIFY_EPSILON_MM
        ):
            violations.append(
                Violation(
                    code="DG_ARCH_DUPLICATE_GEOMETRY",
                    message="서로 다른 ID가 동일한 건축 geometry를 가집니다.",
                    entity_ids=[first_entity.feature_id, second_entity.feature_id],
                )
            )

    wall_intervals: dict[str, list[tuple[str, float, float]]] = {}
    for opening in contract.openings:
        wall = walls[opening.wall_id]
        wall_entity = entities.get(wall.id)
        opening_entity = entities.get(opening.id)
        if wall_entity is None or opening_entity is None:
            continue
        wall_values = _projected_values(wall_entity, wall.start, wall.end)
        opening_values = _projected_values(opening_entity, wall.start, wall.end)
        offset = opening_values["start_projection"] - wall_values["start_projection"]
        width = opening_values["length"]
        wall_intervals.setdefault(wall.id, []).append((opening.id, offset, offset + width))
        if (
            offset < -VERIFY_EPSILON_MM
            or offset + width > wall_values["length"] + VERIFY_EPSILON_MM
        ):
            repairable = f"openings.{opening.id}.offset" in free_paths
            violations.append(
                Violation(
                    code="DG_ARCH_OPENING_OUTSIDE_HOST",
                    message="개구부가 참조 wall 범위를 벗어났습니다.",
                    entity_ids=[opening.id, wall.id],
                    repairable=repairable,
                    details={
                        "offset": offset,
                        "width": width,
                        "wall_length": wall_values["length"],
                    },
                )
            )
    for wall_id, intervals in wall_intervals.items():
        for first_interval, second_interval in combinations(intervals, 2):
            overlap = min(first_interval[2], second_interval[2]) - max(
                first_interval[1], second_interval[1]
            )
            if overlap > VERIFY_EPSILON_MM:
                violations.append(
                    Violation(
                        code="DG_ARCH_OPENING_OVERLAP",
                        message="같은 wall의 개구부가 서로 겹칩니다.",
                        entity_ids=[first_interval[0], second_interval[0], wall_id],
                        repairable=any(
                            f"openings.{item_id}.offset" in free_paths
                            for item_id in (first_interval[0], second_interval[0])
                        ),
                        details={"overlap": overlap},
                    )
                )

    wall_lines: dict[str, LineString] = {}
    for wall in contract.walls:
        centerline = centerlines.get(wall.id)
        wall_entity = entities.get(wall.id)
        if centerline is None or wall_entity is None:
            continue
        if not isinstance(centerline.geometry, LineString):
            continue
        wall_lines[wall.id] = centerline.geometry
        values = _projected_values(wall_entity, wall.start, wall.end)
        outline_line = LineString(
            [(values["start.0"], values["start.1"]), (values["end.0"], values["end.1"])]
        )
        if not centerline.geometry.equals_exact(outline_line, VERIFY_EPSILON_MM):
            violations.append(
                Violation(
                    code="DG_ARCH_WALL_CENTERLINE_MISMATCH",
                    message="Wall centerline and serialized wall outline do not align.",
                    entity_ids=[wall.id],
                )
            )
    if wall_lines:
        remaining = set(wall_lines)
        components = 0
        while remaining:
            components += 1
            stack = [remaining.pop()]
            while stack:
                current = stack.pop()
                connected = {
                    other
                    for other in remaining
                    if wall_lines[current].distance(wall_lines[other]) <= VERIFY_EPSILON_MM
                }
                remaining -= connected
                stack.extend(connected)
        if components > 1:
            violations.append(
                Violation(
                    code="DG_ARCH_WALL_DISCONNECTED",
                    message="Wall centerline graph가 연결되어 있지 않습니다.",
                    entity_ids=sorted(wall_lines),
                    details={"components": components},
                )
            )

    exterior_lines = [
        wall_lines[wall.id]
        for wall in contract.walls
        if wall.wall_type == "exterior" and wall.id in wall_lines
    ]
    exterior_polygons = list(polygonize(unary_union(exterior_lines)))
    if exterior_lines and not exterior_polygons:
        violations.append(
            Violation(
                code="DG_ARCH_EXTERIOR_OPEN",
                message="Exterior wall centerline이 닫힌 loop를 만들지 못합니다.",
                entity_ids=[wall.id for wall in contract.walls if wall.wall_type == "exterior"],
            )
        )

    room_polygons = list(polygonize(unary_union(list(wall_lines.values()))))
    for room in contract.room_seeds:
        entity = entities.get(room.id)
        if entity is None:
            continue
        matches = [polygon for polygon in room_polygons if polygon.covers(entity.geometry)]
        if len(matches) != 1:
            violations.append(
                Violation(
                    code="DG_ARCH_ROOM_UNRESOLVED",
                    message="Room seed가 정확히 하나의 닫힌 공간으로 해석되지 않습니다.",
                    entity_ids=[room.id],
                    details={"matching_regions": len(matches)},
                )
            )

    for constraint in contract.constraints:
        selected_ids = constraint.entity_ids
        if constraint.type == "column_grid_alignment":
            column_ids = selected_ids or [item.id for item in contract.columns]
            grid_lines = [
                entities[item.id].geometry for item in contract.grids if item.id in entities
            ]
            tolerance = float(constraint.parameters.get("tolerance", VERIFY_EPSILON_MM))
            for column_id in column_ids:
                entity = entities.get(column_id)
                if entity is None or entity.layer != "A-COLS" or not grid_lines:
                    continue
                distance = min(entity.geometry.centroid.distance(line) for line in grid_lines)
                if distance > tolerance + VERIFY_EPSILON_MM:
                    violations.append(
                        Violation(
                            code="DG_ARCH_COLUMN_OFF_GRID",
                            message="Column center가 허용 공차 내 grid에 정렬되지 않았습니다.",
                            entity_ids=[column_id],
                            constraint_id=constraint.id,
                            repairable=any(
                                path in free_paths
                                for path in (
                                    f"columns.{column_id}.center.0",
                                    f"columns.{column_id}.center.1",
                                )
                            ),
                            details={"distance": distance, "tolerance": tolerance},
                        )
                    )
        elif constraint.type == "columns_clear_of_openings":
            column_entities = [item for item in entities.values() if item.layer == "A-COLS"]
            opening_entities = [
                item for item in entities.values() if item.layer in {"A-DOOR", "A-WIND"}
            ]
            clearance = float(constraint.parameters.get("minimum_clearance", 0.0))
            for first_candidate, second_candidate in combinations(
                column_entities + opening_entities, 2
            ):
                candidate_layers = {first_candidate.layer, second_candidate.layer}
                if "A-COLS" not in candidate_layers or not candidate_layers.intersection(
                    {"A-DOOR", "A-WIND"}
                ):
                    continue
                column_entity = (
                    first_candidate if first_candidate.layer == "A-COLS" else second_candidate
                )
                opening_entity = (
                    first_candidate if first_candidate.layer != "A-COLS" else second_candidate
                )
                if (
                    column_entity.geometry.distance(opening_entity.geometry) + VERIFY_EPSILON_MM
                    < clearance
                ):
                    violations.append(
                        Violation(
                            code="DG_ARCH_COLUMN_OPENING_CLEARANCE",
                            message="Column과 opening의 최소 이격거리를 충족하지 않습니다.",
                            entity_ids=[column_entity.feature_id, opening_entity.feature_id],
                            constraint_id=constraint.id,
                            details={
                                "actual": column_entity.geometry.distance(opening_entity.geometry),
                                "required": clearance,
                            },
                        )
                    )
        elif constraint.type in {"non_overlap", "openings_non_overlap"}:
            selected = [entities[item_id] for item_id in selected_ids if item_id in entities]
            for selected_first, selected_second in combinations(selected, 2):
                if (
                    selected_first.geometry.intersection(selected_second.geometry).area
                    > VERIFY_EPSILON_MM**2
                ):
                    violations.append(
                        Violation(
                            code="DG_ARCH_CONSTRAINT_OVERLAP",
                            message="Constraint 대상 geometry가 겹칩니다.",
                            entity_ids=[selected_first.feature_id, selected_second.feature_id],
                            constraint_id=constraint.id,
                        )
                    )
    return violations


def _remeasured_summary(
    contract: ArchitecturalPlanContract,
    entities: dict[str, ArchitecturalRemeasuredEntity],
    centerlines: dict[str, ArchitecturalRemeasuredEntity],
) -> dict[str, Any]:
    wall_lines: dict[str, LineString] = {}
    for wall in contract.walls:
        entity = centerlines.get(wall.id)
        if entity is None or not isinstance(entity.geometry, LineString):
            continue
        wall_lines[wall.id] = entity.geometry
    exterior_ids = {wall.id for wall in contract.walls if wall.wall_type == "exterior"}
    exterior_lines = [line for wall_id, line in wall_lines.items() if wall_id in exterior_ids]
    exterior_regions = list(polygonize(unary_union(exterior_lines))) if exterior_lines else []
    all_wall_lines = list(wall_lines.values())
    room_regions = list(polygonize(unary_union(all_wall_lines))) if all_wall_lines else []
    room_areas: list[dict[str, Any]] = []
    for room in contract.room_seeds:
        room_entity = entities.get(room.id)
        matches = (
            [region for region in room_regions if region.covers(room_entity.geometry)]
            if room_entity is not None and isinstance(room_entity.geometry, Point)
            else []
        )
        room_areas.append(
            {
                "id": room.id,
                "name": room.name,
                "area_m2": round(matches[0].area / 1_000_000, 3) if len(matches) == 1 else None,
                "closed": len(matches) == 1,
            }
        )
    return {
        "design_kind": "architectural_plan",
        "summary_source": "independent_serialized_dxf_remeasurement",
        "grids": len(contract.grids),
        "walls": len(wall_lines),
        "openings": len(contract.openings),
        "columns": len(contract.columns),
        "rooms": len(contract.room_seeds),
        "dimensions": len(contract.dimensions),
        "gross_area_m2": round(
            sum(region.area for region in exterior_regions) / 1_000_000,
            3,
        ),
        "room_areas": room_areas,
        "dxf_layers": sorted(_LAYERS),
    }


def verify_architecture_dxf(
    contract: ArchitecturalPlanContract,
    dxf_bytes: bytes,
    contract_hash: str,
) -> ArchitecturalVerificationResult:
    entities, centerlines, violations = _read_serialized_entities_v2(
        contract, dxf_bytes, contract_hash
    )
    measurements: list[Measurement] = []
    locked_failure = False
    free_paths = {item.path for item in contract.free_parameters}
    for dimension in contract.dimensions:
        try:
            actual = _remeasured_value(contract, entities, dimension.path)
        except (KeyError, StopIteration, ArchitecturalDxfReadError):
            violations.append(
                Violation(
                    code="DG_ARCH_DIMENSION_PATH_UNMEASURABLE",
                    message="DXF geometry에서 dimension path를 재측정할 수 없습니다.",
                    details={"dimension_id": dimension.id, "path": dimension.path},
                    repairable=False,
                )
            )
            if dimension.locked:
                locked_failure = True
            continue
        deviation = actual - dimension.target
        passed = (
            dimension.tolerance_lower - VERIFY_EPSILON_MM - 1e-9
            <= deviation
            <= dimension.tolerance_upper + VERIFY_EPSILON_MM + 1e-9
        )
        measurements.append(
            Measurement(
                measurement_id=f"measurement-{dimension.id}",
                dimension_id=dimension.id,
                target=dimension.target,
                actual=actual,
                deviation=deviation,
                tolerance_lower=dimension.tolerance_lower,
                tolerance_upper=dimension.tolerance_upper,
                passed=passed,
                evidence={
                    "artifact": "architectural-plan.dxf",
                    "entities": [dimension.path.split(".")[1]],
                    "method": "independent_serialized_dxf_remeasurement",
                    "path": dimension.path,
                },
            )
        )
        if not passed:
            repairable = not dimension.locked and dimension.path in free_paths
            violations.append(
                Violation(
                    code="DG_ARCH_DIMENSION_OUT_OF_TOLERANCE",
                    message="건축 dimension 재측정값이 공차를 벗어났습니다.",
                    entity_ids=[dimension.path.split(".")[1]],
                    repairable=repairable,
                    details={"dimension_id": dimension.id, "path": dimension.path},
                )
            )
            locked_failure = locked_failure or dimension.locked

    violations.extend(_constraint_violations(contract, entities, centerlines))
    if not violations and all(item.passed for item in measurements):
        status = RunStatus.PASSED
    elif not locked_failure and violations and all(item.repairable for item in violations):
        status = RunStatus.REPAIRABLE
    else:
        status = RunStatus.FAILED
    return ArchitecturalVerificationResult(
        status=status,
        contract_hash=contract_hash,
        artifact_hash=compute_artifact_hash(dxf_bytes),
        measurements=measurements,
        violations=violations,
        evidence=[
            Evidence(
                type="architectural_dxf_remeasurement",
                source="independent_architecture_verifier",
                details={
                    "serialized_bytes_read": len(dxf_bytes),
                    "entity_count": len(entities),
                    "writer_geometry_reused": False,
                    "design_kind": "architectural_plan",
                },
            )
        ],
        summary=_remeasured_summary(contract, entities, centerlines),
    )


__all__ = [
    "ArchitecturalDxfReadError",
    "ArchitecturalVerificationResult",
    "verify_architecture_dxf",
]

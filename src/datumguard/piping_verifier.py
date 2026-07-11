from __future__ import annotations

import io
import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from ezdxf import units
from ezdxf.entities.circle import Circle
from ezdxf.entities.dxfentity import DXFEntity
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.entities.point import Point as DXFPoint
from ezdxf.entities.text import Text
from ezdxf.filemanagement import read
from ezdxf.lldxf.const import DXFError, DXFValueError
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from .core import compute_artifact_hash
from .models import Evidence, Measurement, RunStatus, Violation
from .piping_models import PipingPlanContract

VERIFY_EPSILON_MM = 0.001
_LAYERS = {
    "P-PIPE",
    "P-NODE",
    "P-COMP",
    "P-SUPPORT",
    "P-EQUIP",
    "P-DIMS",
    "P-META",
}
_GEOMETRY_LAYERS = {"P-PIPE", "P-NODE", "P-COMP", "P-SUPPORT", "P-EQUIP"}
_XDATA_APP_ID = "DATUMGUARD"


class PipingDxfReadError(ValueError):
    """Raised when the serialized piping DXF cannot be independently parsed."""


@dataclass(frozen=True)
class PipingRemeasuredEntity:
    feature_id: str
    feature_type: str
    layer: str
    geometry: BaseGeometry
    values: dict[str, float]
    metadata: dict[str, str]


@dataclass(frozen=True)
class PipingVerificationResult:
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


def _expected_entities(contract: PipingPlanContract) -> dict[str, tuple[str, str]]:
    expected: dict[str, tuple[str, str]] = {}
    expected.update((item.id, ("P-PIPE", "pipe_segment")) for item in contract.segments)
    expected.update((item.id, ("P-NODE", "piping_node")) for item in contract.nodes)
    expected.update((item.id, ("P-COMP", item.type)) for item in contract.components)
    expected.update((item.id, ("P-SUPPORT", item.type)) for item in contract.supports)
    expected.update(
        (item.id, ("P-EQUIP", f"{item.zone_kind}_{item.type}")) for item in contract.equipment_zones
    )
    if contract.drawing_profile.include_dimensions:
        expected.update((item.id, ("P-DIMS", "dimension_note")) for item in contract.dimensions)
    expected["piping-metadata"] = ("P-META", "metadata")
    return expected


def _closed_polygon(entity: LWPolyline, feature_id: str) -> Polygon:
    points = [(float(x), float(y)) for x, y in entity.get_points("xy")]
    if len(points) < 3 or not entity.closed:
        raise PipingDxfReadError(f"expected closed polyline for {feature_id}")
    polygon = Polygon(points)
    if polygon.is_empty or not polygon.is_valid:
        raise PipingDxfReadError(f"invalid serialized polygon for {feature_id}")
    return polygon


def _read_geometry_entity(
    entity: DXFEntity,
    feature_id: str,
) -> tuple[BaseGeometry, dict[str, float]]:
    layer = entity.dxf.layer
    if layer == "P-PIPE":
        if not isinstance(entity, LWPolyline):
            raise PipingDxfReadError(f"pipe segment {feature_id} is not an LWPOLYLINE")
        points = [(float(x), float(y)) for x, y in entity.get_points("xy")]
        if len(points) != 2 or entity.closed:
            raise PipingDxfReadError(f"pipe segment {feature_id} must have exactly two vertices")
        geometry = LineString(points)
        diameter = float(entity.dxf.const_width)
        if geometry.length <= 0 or diameter <= 0:
            raise PipingDxfReadError(f"pipe segment {feature_id} has invalid length or width")
        return geometry, {
            "start.0": points[0][0],
            "start.1": points[0][1],
            "end.0": points[1][0],
            "end.1": points[1][1],
            "length": geometry.length,
            "nominal_diameter": diameter,
        }
    if layer == "P-NODE":
        if not isinstance(entity, DXFPoint):
            raise PipingDxfReadError(f"piping node {feature_id} is not a POINT")
        location = entity.dxf.location
        point = Point(float(location.x), float(location.y))
        return point, {"point.0": point.x, "point.1": point.y}
    if layer == "P-SUPPORT":
        if not isinstance(entity, Circle):
            raise PipingDxfReadError(f"support {feature_id} is not a CIRCLE")
        center = entity.dxf.center
        point = Point(float(center.x), float(center.y))
        return point, {"point.0": point.x, "point.1": point.y}
    if layer == "P-COMP":
        if isinstance(entity, Circle):
            center = entity.dxf.center
            geometry = Point(float(center.x), float(center.y)).buffer(
                float(entity.dxf.radius), quad_segs=64
            )
        elif isinstance(entity, LWPolyline):
            points = [(float(x), float(y)) for x, y in entity.get_points("xy")]
            if len(points) < 2:
                raise PipingDxfReadError(f"component {feature_id} has too few vertices")
            geometry = Polygon(points) if entity.closed else LineString(points)
            if geometry.is_empty or not geometry.is_valid:
                raise PipingDxfReadError(f"component {feature_id} has invalid geometry")
        else:
            raise PipingDxfReadError(f"component {feature_id} has unsupported geometry")
        min_x, min_y, max_x, max_y = geometry.bounds
        return geometry, {"point.0": (min_x + max_x) / 2, "point.1": (min_y + max_y) / 2}
    if layer == "P-EQUIP":
        if isinstance(entity, Circle):
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            geometry = Point(float(center.x), float(center.y)).buffer(radius, quad_segs=64)
            return geometry, {
                "center.0": float(center.x),
                "center.1": float(center.y),
                "diameter": radius * 2,
            }
        if isinstance(entity, LWPolyline):
            geometry = _closed_polygon(entity, feature_id)
            min_x, min_y, max_x, max_y = geometry.bounds
            return geometry, {
                "origin.0": min_x,
                "origin.1": min_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
            }
        raise PipingDxfReadError(f"equipment zone {feature_id} has unsupported geometry")
    raise PipingDxfReadError(f"unexpected geometry layer: {layer}")


def _read_serialized_entities(
    contract: PipingPlanContract,
    dxf_bytes: bytes,
    expected_contract_hash: str,
) -> tuple[dict[str, PipingRemeasuredEntity], list[Violation]]:
    try:
        document = read(io.StringIO(dxf_bytes.decode("utf-8")))
    except (UnicodeDecodeError, DXFError, ValueError) as exc:
        raise PipingDxfReadError("piping DXF parsing failed") from exc

    violations: list[Violation] = []
    present_layers = {layer.dxf.name for layer in document.layers}
    missing_layers = sorted(_LAYERS - present_layers)
    if missing_layers:
        violations.append(
            Violation(
                code="DG_PIPE_DXF_LAYER_MISSING",
                message="Required piping DXF layers are missing.",
                details={"missing_layers": missing_layers},
            )
        )
    if document.dxfversion != "AC1027":
        violations.append(
            Violation(
                code="DG_PIPE_DXF_VERSION_INVALID",
                message="Piping DXF version must be R2013.",
                details={"actual": document.dxfversion, "expected": "AC1027"},
            )
        )
    if document.units != units.MM:
        violations.append(
            Violation(
                code="DG_PIPE_DXF_UNIT_INVALID",
                message="Piping DXF modelspace units must be millimeters.",
                details={"actual": document.units, "expected": units.MM},
            )
        )

    expected = _expected_entities(contract)
    entities: dict[str, PipingRemeasuredEntity] = {}
    seen_ids: set[str] = set()
    for entity in document.modelspace():
        if entity.dxf.layer not in _LAYERS:
            violations.append(
                Violation(
                    code="DG_PIPE_DXF_LAYER_INVALID",
                    message="A piping drawing entity is on an unapproved layer.",
                    details={"layer": entity.dxf.layer, "handle": entity.dxf.handle},
                )
            )
            continue
        metadata = _xdata(entity)
        feature_id = metadata.get("feature_id")
        feature_type = metadata.get("feature_type")
        if not feature_id or not feature_type:
            violations.append(
                Violation(
                    code="DG_PIPE_DXF_XDATA_MISSING",
                    message="A piping DXF entity is missing identity XDATA.",
                    details={"handle": entity.dxf.handle, "layer": entity.dxf.layer},
                )
            )
            continue
        if metadata.get("design_kind") != "piping_plan":
            violations.append(
                Violation(
                    code="DG_PIPE_DESIGN_KIND_MISMATCH",
                    message="DXF XDATA design_kind must be piping_plan.",
                    entity_ids=[feature_id],
                )
            )
        if metadata.get("contract_hash") != expected_contract_hash:
            violations.append(
                Violation(
                    code="DG_CONTRACT_HASH_MISMATCH",
                    message="Piping DXF XDATA hash differs from the canonical contract hash.",
                    entity_ids=[feature_id],
                    details={
                        "actual": metadata.get("contract_hash"),
                        "expected": expected_contract_hash,
                    },
                )
            )
        if metadata.get("revision") != contract.metadata.revision:
            violations.append(
                Violation(
                    code="DG_PIPE_DXF_REVISION_MISMATCH",
                    message="Piping DXF XDATA revision differs from the contract.",
                    entity_ids=[feature_id],
                )
            )
        if feature_id in seen_ids:
            violations.append(
                Violation(
                    code="DG_PIPE_ENTITY_ID_DUPLICATE",
                    message="A piping DXF feature identifier is duplicated.",
                    entity_ids=[feature_id],
                )
            )
            continue
        seen_ids.add(feature_id)
        expected_identity = expected.get(feature_id)
        if expected_identity is None:
            violations.append(
                Violation(
                    code="DG_PIPE_ENTITY_UNEXPECTED",
                    message="The piping DXF contains an unexpected feature identifier.",
                    entity_ids=[feature_id],
                )
            )
        elif expected_identity != (entity.dxf.layer, feature_type):
            violations.append(
                Violation(
                    code="DG_PIPE_DXF_IDENTITY_MISMATCH",
                    message="Piping DXF layer or feature type differs from the contract.",
                    entity_ids=[feature_id],
                    details={
                        "actual_layer": entity.dxf.layer,
                        "actual_type": feature_type,
                        "expected_layer": expected_identity[0],
                        "expected_type": expected_identity[1],
                    },
                )
            )
        if entity.dxf.layer not in _GEOMETRY_LAYERS:
            if not isinstance(entity, Text):
                violations.append(
                    Violation(
                        code="DG_PIPE_DXF_ENTITY_UNSUPPORTED",
                        message="Piping annotation entity type is unsupported.",
                        entity_ids=[feature_id],
                        details={"entity_type": entity.dxftype()},
                    )
                )
            continue
        try:
            geometry, values = _read_geometry_entity(entity, feature_id)
        except PipingDxfReadError as exc:
            violations.append(
                Violation(
                    code="DG_PIPE_DXF_GEOMETRY_INVALID",
                    message="Serialized piping geometry is invalid.",
                    entity_ids=[feature_id],
                    details={"reason": str(exc)},
                )
            )
            continue
        entities[feature_id] = PipingRemeasuredEntity(
            feature_id=feature_id,
            feature_type=feature_type,
            layer=entity.dxf.layer,
            geometry=geometry,
            values=values,
            metadata=metadata,
        )

    missing = sorted(set(expected) - seen_ids)
    if missing:
        violations.append(
            Violation(
                code="DG_PIPE_ENTITY_MISSING",
                message="The serialized piping DXF is missing contract entities.",
                entity_ids=missing,
            )
        )
    return entities, violations


def _point_value(entity: PipingRemeasuredEntity) -> Point:
    return Point(entity.values["point.0"], entity.values["point.1"])


def _segment_value(entity: PipingRemeasuredEntity) -> LineString:
    if not isinstance(entity.geometry, LineString):
        raise PipingDxfReadError(f"{entity.feature_id} is not a serialized segment line")
    return entity.geometry


def _constraint(
    contract: PipingPlanContract,
    constraint_type: str,
) -> tuple[str | None, dict[str, Any]]:
    item = next((item for item in contract.constraints if item.type == constraint_type), None)
    return (item.id, item.parameters) if item is not None else (None, {})


def _projected_offset(line: LineString, point: Point) -> float:
    return float(line.project(point))


def _remeasured_value(
    contract: PipingPlanContract,
    entities: dict[str, PipingRemeasuredEntity],
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
    if collection in {"components", "supports"} and suffix == "offset":
        item = next(
            item for item in [*contract.components, *contract.supports] if item.id == entity_id
        )
        segment = entities.get(item.segment_id)
        if segment is None:
            raise KeyError(path)
        return _projected_offset(_segment_value(segment), _point_value(entity))
    if collection not in {
        "nodes",
        "segments",
        "components",
        "supports",
        "equipment_zones",
    }:
        raise KeyError(path)
    return entity.values[suffix]


def _duplicate_violations(
    entities: dict[str, PipingRemeasuredEntity],
) -> list[Violation]:
    violations: list[Violation] = []
    for first, second in combinations(entities.values(), 2):
        if first.layer != second.layer:
            continue
        if first.geometry.equals(second.geometry) or first.geometry.equals_exact(
            second.geometry, VERIFY_EPSILON_MM
        ):
            violations.append(
                Violation(
                    code="DG_PIPE_DUPLICATE_GEOMETRY",
                    message="Different piping IDs contain duplicate serialized geometry.",
                    entity_ids=[first.feature_id, second.feature_id],
                )
            )
    return violations


def _route_violations(
    contract: PipingPlanContract,
    entities: dict[str, PipingRemeasuredEntity],
) -> list[Violation]:
    violations: list[Violation] = []
    endpoint_constraint_id, endpoint_parameters = _constraint(contract, "endpoint_alignment")
    endpoint_tolerance = float(endpoint_parameters.get("tolerance", VERIFY_EPSILON_MM))
    orthogonal_constraint_id, orthogonal_parameters = _constraint(contract, "orthogonal")
    orthogonal_tolerance = float(orthogonal_parameters.get("tolerance", VERIFY_EPSILON_MM))
    connectivity_constraint_id, _ = _constraint(contract, "route_connected")

    segment_entities: dict[str, PipingRemeasuredEntity] = {}
    for segment in contract.segments:
        entity = entities.get(segment.id)
        if entity is None:
            continue
        try:
            line = _segment_value(entity)
        except PipingDxfReadError:
            continue
        segment_entities[segment.id] = entity
        start = Point(line.coords[0])
        end = Point(line.coords[-1])
        start_node = entities.get(segment.start_node_id)
        end_node = entities.get(segment.end_node_id)
        metadata_matches = (
            entity.metadata.get("start_node_id") == segment.start_node_id
            and entity.metadata.get("end_node_id") == segment.end_node_id
        )
        distances = {
            "start": (
                start.distance(_point_value(start_node)) if start_node is not None else math.inf
            ),
            "end": end.distance(_point_value(end_node)) if end_node is not None else math.inf,
        }
        if (
            not metadata_matches
            or distances["start"] > endpoint_tolerance + VERIFY_EPSILON_MM
            or distances["end"] > endpoint_tolerance + VERIFY_EPSILON_MM
        ):
            violations.append(
                Violation(
                    code="DG_PIPE_ENDPOINT_MISALIGNED",
                    message="A serialized pipe endpoint is not aligned with its declared node.",
                    entity_ids=[segment.id, segment.start_node_id, segment.end_node_id],
                    constraint_id=endpoint_constraint_id,
                    details={"distances": distances, "tolerance": endpoint_tolerance},
                )
            )
        dx = abs(line.coords[-1][0] - line.coords[0][0])
        dy = abs(line.coords[-1][1] - line.coords[0][1])
        if min(dx, dy) > orthogonal_tolerance + VERIFY_EPSILON_MM:
            violations.append(
                Violation(
                    code="DG_PIPE_NON_ORTHOGONAL",
                    message="A piping route segment is not orthogonal in plan.",
                    entity_ids=[segment.id],
                    constraint_id=orthogonal_constraint_id,
                    details={"delta_x": dx, "delta_y": dy, "tolerance": orthogonal_tolerance},
                )
            )

    remaining = set(segment_entities)
    components = 0
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            current_id = stack.pop()
            current = _segment_value(segment_entities[current_id])
            current_endpoints = [Point(current.coords[0]), Point(current.coords[-1])]
            connected: set[str] = set()
            for other_id in remaining:
                other = _segment_value(segment_entities[other_id])
                other_endpoints = [Point(other.coords[0]), Point(other.coords[-1])]
                if (
                    min(
                        first.distance(second)
                        for first in current_endpoints
                        for second in other_endpoints
                    )
                    <= endpoint_tolerance + VERIFY_EPSILON_MM
                ):
                    connected.add(other_id)
            remaining -= connected
            stack.extend(connected)
    isolated_nodes = [
        node.id
        for node in contract.nodes
        if node.id in entities
        and not any(
            _point_value(entities[node.id]).distance(Point(point))
            <= endpoint_tolerance + VERIFY_EPSILON_MM
            for segment_entity in segment_entities.values()
            for point in (
                _segment_value(segment_entity).coords[0],
                _segment_value(segment_entity).coords[-1],
            )
        )
    ]
    if components > 1 or isolated_nodes:
        violations.append(
            Violation(
                code="DG_PIPE_ROUTE_DISCONNECTED",
                message="Serialized piping route geometry is not a single connected network.",
                entity_ids=sorted([*segment_entities, *isolated_nodes]),
                constraint_id=connectivity_constraint_id,
                details={"components": components, "isolated_nodes": isolated_nodes},
            )
        )
    return violations


def _component_and_support_violations(
    contract: PipingPlanContract,
    entities: dict[str, PipingRemeasuredEntity],
) -> tuple[list[Violation], dict[str, list[float]]]:
    violations: list[Violation] = []
    offsets_by_segment: dict[str, list[float]] = {segment.id: [] for segment in contract.segments}
    component_constraint_id, component_parameters = _constraint(
        contract, "inline_component_position"
    )
    component_tolerance = float(component_parameters.get("tolerance", VERIFY_EPSILON_MM))
    _, endpoint_parameters = _constraint(contract, "endpoint_alignment")
    support_tolerance = float(endpoint_parameters.get("tolerance", VERIFY_EPSILON_MM))

    for item in [*contract.components, *contract.supports]:
        entity = entities.get(item.id)
        segment_entity = entities.get(item.segment_id)
        if entity is None or segment_entity is None:
            continue
        point = _point_value(entity)
        try:
            line = _segment_value(segment_entity)
        except PipingDxfReadError:
            continue
        actual_offset = _projected_offset(line, point)
        line_distance = point.distance(line)
        tolerance = component_tolerance if item in contract.components else support_tolerance
        metadata_matches = entity.metadata.get("segment_id") == item.segment_id
        position_valid = (
            metadata_matches
            and line_distance <= tolerance + VERIFY_EPSILON_MM
            and -VERIFY_EPSILON_MM <= actual_offset <= line.length + VERIFY_EPSILON_MM
            and abs(actual_offset - item.offset) <= tolerance + VERIFY_EPSILON_MM
        )
        if not position_valid:
            is_component = item in contract.components
            violations.append(
                Violation(
                    code=(
                        "DG_PIPE_COMPONENT_POSITION_INVALID"
                        if is_component
                        else "DG_PIPE_SUPPORT_POSITION_INVALID"
                    ),
                    message=(
                        "An inline component is not at its declared host-segment offset."
                        if is_component
                        else "A pipe support is not at its declared host-segment offset."
                    ),
                    entity_ids=[item.id, item.segment_id],
                    constraint_id=component_constraint_id if is_component else None,
                    details={
                        "declared_offset": item.offset,
                        "actual_offset": actual_offset,
                        "line_distance": line_distance,
                        "tolerance": tolerance,
                    },
                )
            )
        elif item in contract.supports:
            offsets_by_segment[item.segment_id].append(actual_offset)
    return violations, offsets_by_segment


def _spacing_violations(
    contract: PipingPlanContract,
    entities: dict[str, PipingRemeasuredEntity],
    offsets_by_segment: dict[str, list[float]],
) -> tuple[list[Violation], float]:
    constraint_id, parameters = _constraint(contract, "maximum_support_spacing")
    maximum_spacing_value = parameters.get("maximum_spacing", parameters.get("max_support_spacing"))
    if not isinstance(maximum_spacing_value, int | float):
        return [], 0.0
    maximum_spacing = float(maximum_spacing_value)
    violations: list[Violation] = []
    largest_gap = 0.0
    for segment in contract.segments:
        entity = entities.get(segment.id)
        if entity is None:
            continue
        try:
            length = _segment_value(entity).length
        except PipingDxfReadError:
            continue
        offsets = sorted([0.0, *offsets_by_segment.get(segment.id, []), length])
        gaps = [second - first for first, second in zip(offsets, offsets[1:], strict=False)]
        segment_largest = max(gaps, default=length)
        largest_gap = max(largest_gap, segment_largest)
        if segment_largest > maximum_spacing + VERIFY_EPSILON_MM:
            gap_index = gaps.index(segment_largest)
            violations.append(
                Violation(
                    code="DG_PIPE_SUPPORT_SPACING_EXCEEDED",
                    message="Pipe support spacing exceeds the permitted maximum.",
                    entity_ids=[segment.id],
                    constraint_id=constraint_id,
                    details={
                        "actual_gap": segment_largest,
                        "maximum_spacing": maximum_spacing,
                        "gap_start": offsets[gap_index],
                        "gap_end": offsets[gap_index + 1],
                        "endpoint_gaps_included": True,
                    },
                )
            )
    return violations, largest_gap


def _clearance_violations(
    contract: PipingPlanContract,
    entities: dict[str, PipingRemeasuredEntity],
) -> tuple[list[Violation], float | None]:
    constraint_id, parameters = _constraint(contract, "minimum_obstacle_clearance")
    global_clearance = float(parameters.get("minimum_clearance", 0.0))
    violations: list[Violation] = []
    minimum_actual: float | None = None
    for segment in contract.segments:
        segment_entity = entities.get(segment.id)
        if segment_entity is None:
            continue
        try:
            line = _segment_value(segment_entity)
        except PipingDxfReadError:
            continue
        radius = segment_entity.values["nominal_diameter"] / 2.0
        for zone in contract.equipment_zones:
            zone_entity = entities.get(zone.id)
            if zone_entity is None:
                continue
            required = max(global_clearance, zone.minimum_clearance)
            actual = line.distance(zone_entity.geometry) - radius
            minimum_actual = actual if minimum_actual is None else min(minimum_actual, actual)
            if actual + VERIFY_EPSILON_MM < required:
                violations.append(
                    Violation(
                        code="DG_PIPE_CLEARANCE_VIOLATION",
                        message="Pipe-to-obstacle clearance is below the required minimum.",
                        entity_ids=[segment.id, zone.id],
                        constraint_id=constraint_id,
                        details={
                            "actual_clearance": actual,
                            "required_clearance": required,
                            "pipe_radius": radius,
                        },
                    )
                )
    return violations, minimum_actual


def _remeasured_summary(
    contract: PipingPlanContract,
    entities: dict[str, PipingRemeasuredEntity],
    *,
    maximum_support_gap: float,
    minimum_clearance: float | None,
) -> dict[str, Any]:
    segment_entities = [
        entities[item.id]
        for item in contract.segments
        if item.id in entities and isinstance(entities[item.id].geometry, LineString)
    ]
    return {
        "design_kind": "piping_plan",
        "summary_source": "independent_serialized_dxf_remeasurement",
        "nodes": sum(item.id in entities for item in contract.nodes),
        "segments": len(segment_entities),
        "components": sum(item.id in entities for item in contract.components),
        "supports": sum(item.id in entities for item in contract.supports),
        "equipment_zones": sum(item.id in entities for item in contract.equipment_zones),
        "dimensions": len(contract.dimensions),
        "total_route_length_mm": round(
            sum(_segment_value(item).length for item in segment_entities), 3
        ),
        "maximum_support_gap_mm": round(maximum_support_gap, 3),
        "minimum_clearance_mm": (
            round(minimum_clearance, 3) if minimum_clearance is not None else None
        ),
        "service_codes": sorted(
            {
                item.metadata["service_code"]
                for item in segment_entities
                if "service_code" in item.metadata
            }
        ),
        "dxf_layers": sorted(_LAYERS),
    }


def verify_piping_dxf(
    contract: PipingPlanContract,
    dxf_bytes: bytes,
    contract_hash: str,
) -> PipingVerificationResult:
    entities, violations = _read_serialized_entities(contract, dxf_bytes, contract_hash)
    measurements: list[Measurement] = []
    locked_failure = False
    free_paths = {item.path for item in contract.free_parameters}
    for dimension in contract.dimensions:
        try:
            actual = _remeasured_value(contract, entities, dimension.path)
        except (KeyError, StopIteration, PipingDxfReadError):
            violations.append(
                Violation(
                    code="DG_PIPE_DIMENSION_PATH_UNMEASURABLE",
                    message="The dimension path cannot be remeasured from serialized DXF geometry.",
                    details={"dimension_id": dimension.id, "path": dimension.path},
                )
            )
            locked_failure = locked_failure or dimension.locked
            continue
        deviation = actual - dimension.target
        passed = (
            dimension.tolerance_lower - VERIFY_EPSILON_MM
            <= deviation
            <= dimension.tolerance_upper + VERIFY_EPSILON_MM
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
                    "artifact": "piping-plan.dxf",
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
                    code="DG_PIPE_DIMENSION_OUT_OF_TOLERANCE",
                    message="A remeasured piping dimension is outside tolerance.",
                    entity_ids=[dimension.path.split(".")[1]],
                    repairable=repairable,
                    details={"dimension_id": dimension.id, "path": dimension.path},
                )
            )
            locked_failure = locked_failure or dimension.locked

    violations.extend(_duplicate_violations(entities))
    violations.extend(_route_violations(contract, entities))
    item_violations, support_offsets = _component_and_support_violations(contract, entities)
    violations.extend(item_violations)
    spacing_violations, maximum_support_gap = _spacing_violations(
        contract, entities, support_offsets
    )
    violations.extend(spacing_violations)
    clearance_violations, minimum_clearance = _clearance_violations(contract, entities)
    violations.extend(clearance_violations)

    if not violations and all(item.passed for item in measurements):
        status = RunStatus.PASSED
    elif not locked_failure and violations and all(item.repairable for item in violations):
        status = RunStatus.REPAIRABLE
    else:
        status = RunStatus.FAILED
    return PipingVerificationResult(
        status=status,
        contract_hash=contract_hash,
        artifact_hash=compute_artifact_hash(dxf_bytes),
        measurements=measurements,
        violations=violations,
        evidence=[
            Evidence(
                type="piping_dxf_remeasurement",
                source="independent_piping_verifier",
                details={
                    "serialized_bytes_read": len(dxf_bytes),
                    "entity_count": len(entities),
                    "writer_geometry_reused": False,
                    "design_kind": "piping_plan",
                },
            )
        ],
        summary=_remeasured_summary(
            contract,
            entities,
            maximum_support_gap=maximum_support_gap,
            minimum_clearance=minimum_clearance,
        ),
    )


__all__ = [
    "PipingDxfReadError",
    "PipingVerificationResult",
    "verify_piping_dxf",
]

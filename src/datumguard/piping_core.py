from __future__ import annotations

import hashlib
import json
import math
from typing import Any, cast

from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from .piping_models import (
    CircularEquipmentZone,
    PipeSegment,
    PipingPlanContract,
    RectangularEquipmentZone,
    Reducer,
)

MM_PER_INCH = 25.4
HASH_GRID_MM = 0.001


class PipingGeometryError(ValueError):
    """Raised when a piping contract cannot create valid native geometry."""


def _pair(value: list[float] | tuple[float, float], factor: float) -> list[float]:
    return [float(value[0]) * factor, float(value[1]) * factor]


def normalize_piping_to_mm(contract: PipingPlanContract) -> PipingPlanContract:
    data = contract.model_dump(mode="python")
    factor = MM_PER_INCH if contract.units == "inch" else 1.0
    data["units"] = "mm"
    data["contract_hash"] = None
    data["datum"]["origin"] = _pair(data["datum"]["origin"], factor)

    for node in data["nodes"]:
        node["point"] = _pair(node["point"], factor)
    for segment in data["segments"]:
        segment["nominal_diameter"] *= factor
    for component in data["components"]:
        component["offset"] *= factor
        if component["type"] == "reducer":
            component["inlet_diameter"] *= factor
            component["outlet_diameter"] *= factor
    for support in data["supports"]:
        support["offset"] *= factor
    for zone in data["equipment_zones"]:
        zone["minimum_clearance"] *= factor
        if zone["type"] == "rectangle":
            zone["origin"] = _pair(zone["origin"], factor)
            zone["width"] *= factor
            zone["height"] *= factor
        else:
            zone["center"] = _pair(zone["center"], factor)
            zone["diameter"] *= factor
    for dimension in data["dimensions"]:
        dimension["target"] *= factor
        dimension["tolerance_lower"] *= factor
        dimension["tolerance_upper"] *= factor

    scalable_keys = {
        "tolerance",
        "endpoint_tolerance",
        "maximum_spacing",
        "max_support_spacing",
        "minimum_clearance",
        "clearance",
    }
    for constraint in data["constraints"]:
        for key in scalable_keys:
            value = constraint["parameters"].get(key)
            if isinstance(value, int | float):
                constraint["parameters"][key] = float(value) * factor
    for parameter in data["free_parameters"]:
        parameter_factor = MM_PER_INCH if parameter["unit"] == "inch" else 1.0
        parameter["minimum"] *= parameter_factor
        parameter["maximum"] *= parameter_factor
        parameter["step"] *= parameter_factor
        parameter["unit"] = "mm"
    return PipingPlanContract.model_validate(data)


def _quantize(value: Any) -> Any:
    if isinstance(value, float):
        result = round(value / HASH_GRID_MM) * HASH_GRID_MM
        return 0.0 if abs(result) < HASH_GRID_MM / 2 else round(result, 6)
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


def canonical_piping_data(contract: PipingPlanContract) -> dict[str, Any]:
    normalized = normalize_piping_to_mm(contract)
    data = normalized.model_dump(mode="json", exclude={"contract_hash", "intent_text"})
    return cast(dict[str, Any], _quantize(data))


def compute_piping_hash(contract: PipingPlanContract) -> str:
    payload = json.dumps(
        canonical_piping_data(contract),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _node_points(contract: PipingPlanContract) -> dict[str, tuple[float, float]]:
    return {node.id: node.point for node in contract.nodes}


def segment_line(contract: PipingPlanContract, segment: PipeSegment) -> LineString:
    points = _node_points(contract)
    line = LineString([points[segment.start_node_id], points[segment.end_node_id]])
    if line.is_empty or not line.is_valid or line.length <= 0:
        raise PipingGeometryError(f"invalid pipe segment geometry: {segment.id}")
    return line


def segment_length(contract: PipingPlanContract, segment: PipeSegment) -> float:
    points = _node_points(contract)
    return math.dist(points[segment.start_node_id], points[segment.end_node_id])


def point_at_offset(
    contract: PipingPlanContract,
    segment: PipeSegment,
    offset: float,
) -> tuple[float, float]:
    points = _node_points(contract)
    start = points[segment.start_node_id]
    end = points[segment.end_node_id]
    length = math.dist(start, end)
    if length <= 0:
        raise PipingGeometryError(f"zero-length pipe segment: {segment.id}")
    return (
        start[0] + (end[0] - start[0]) * offset / length,
        start[1] + (end[1] - start[1]) * offset / length,
    )


def equipment_zone_geometry(
    zone: RectangularEquipmentZone | CircularEquipmentZone,
) -> Polygon:
    if isinstance(zone, CircularEquipmentZone):
        return Point(zone.center).buffer(zone.diameter / 2.0, quad_segs=64)
    return box(
        zone.origin[0],
        zone.origin[1],
        zone.origin[0] + zone.width,
        zone.origin[1] + zone.height,
    )


def piping_geometry_map(contract: PipingPlanContract) -> dict[str, BaseGeometry]:
    result: dict[str, BaseGeometry] = {}
    segments = {segment.id: segment for segment in contract.segments}
    for node in contract.nodes:
        result[node.id] = Point(node.point)
    for segment in contract.segments:
        result[segment.id] = segment_line(contract, segment)
    for component in contract.components:
        result[component.id] = Point(
            point_at_offset(contract, segments[component.segment_id], component.offset)
        )
    for support in contract.supports:
        result[support.id] = Point(
            point_at_offset(contract, segments[support.segment_id], support.offset)
        )
    for zone in contract.equipment_zones:
        result[zone.id] = equipment_zone_geometry(zone)
    if any(item.is_empty or not item.is_valid for item in result.values()):
        raise PipingGeometryError("piping native geometry is invalid")
    return result


def get_piping_numeric_path(contract: PipingPlanContract, path: str) -> float:
    parts = path.split(".")
    collections: dict[str, list[Any]] = {
        "nodes": contract.nodes,
        "segments": contract.segments,
        "components": contract.components,
        "supports": contract.supports,
        "equipment_zones": contract.equipment_zones,
    }
    if len(parts) < 3 or parts[0] not in collections:
        raise KeyError(path)
    current: Any = next((item for item in collections[parts[0]] if item.id == parts[1]), None)
    if current is None:
        raise KeyError(path)
    remaining = parts[2:]
    for part in remaining:
        if part == "length" and isinstance(current, PipeSegment):
            current = segment_length(contract, current)
        elif isinstance(current, tuple | list):
            current = current[int(part)]
        else:
            current = getattr(current, part)
    if not isinstance(current, int | float):
        raise KeyError(path)
    return float(current)


def segment_effective_diameter(contract: PipingPlanContract, segment: PipeSegment) -> float:
    diameter = segment.nominal_diameter
    for component in contract.components:
        if isinstance(component, Reducer) and component.segment_id == segment.id:
            diameter = max(diameter, component.inlet_diameter, component.outlet_diameter)
    return diameter


__all__ = [
    "PipingGeometryError",
    "canonical_piping_data",
    "compute_piping_hash",
    "equipment_zone_geometry",
    "get_piping_numeric_path",
    "normalize_piping_to_mm",
    "piping_geometry_map",
    "point_at_offset",
    "segment_effective_diameter",
    "segment_length",
    "segment_line",
]

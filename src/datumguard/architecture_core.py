from __future__ import annotations

import hashlib
import json
import math
from typing import Any, cast

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from .architecture_models import (
    ArchitecturalOpening,
    ArchitecturalPlanContract,
    ArchitecturalWall,
    CircularColumn,
    RectangularColumn,
)

MM_PER_INCH = 25.4
HASH_GRID_MM = 0.001


class ArchitecturalGeometryError(ValueError):
    """Raised when an architectural contract cannot create valid native geometry."""


def _pair(value: list[float] | tuple[float, float], factor: float) -> list[float]:
    return [float(value[0]) * factor, float(value[1]) * factor]


def normalize_architecture_to_mm(
    contract: ArchitecturalPlanContract,
) -> ArchitecturalPlanContract:
    data = contract.model_dump(mode="python")
    factor = MM_PER_INCH if contract.units == "inch" else 1.0
    data["units"] = "mm"
    data["contract_hash"] = None
    data["datum"]["origin"] = _pair(data["datum"]["origin"], factor)

    for grid in data["grids"]:
        grid["start"] = _pair(grid["start"], factor)
        grid["end"] = _pair(grid["end"], factor)
        if grid["offset"] is not None:
            grid["offset"] *= factor
        elif grid["axis"] == "x":
            grid["offset"] = grid["start"][0]
        elif grid["axis"] == "y":
            grid["offset"] = grid["start"][1]
    for wall in data["walls"]:
        wall["start"] = _pair(wall["start"], factor)
        wall["end"] = _pair(wall["end"], factor)
        wall["thickness"] *= factor
    for opening in data["openings"]:
        opening["offset"] *= factor
        opening["width"] *= factor
        if opening["height"] is not None:
            opening["height"] *= factor
        if opening["sill_height"] is not None:
            opening["sill_height"] *= factor
    for column in data["columns"]:
        column["center"] = _pair(column["center"], factor)
        if column["type"] == "rectangular_column":
            column["width"] *= factor
            column["depth"] *= factor
        else:
            column["diameter"] *= factor
    for room in data["room_seeds"]:
        room["point"] = _pair(room["point"], factor)
        if room["expected_area"] is not None:
            room["expected_area"] *= factor * factor
    for dimension in data["dimensions"]:
        dimension["target"] *= factor
        dimension["tolerance_lower"] *= factor
        dimension["tolerance_upper"] *= factor
    scalable_keys = {
        "minimum_clearance",
        "tolerance",
        "axis_value",
        "maximum_gap",
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
    return ArchitecturalPlanContract.model_validate(data)


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


def canonical_architecture_data(contract: ArchitecturalPlanContract) -> dict[str, Any]:
    normalized = normalize_architecture_to_mm(contract)
    data = normalized.model_dump(mode="json", exclude={"contract_hash", "intent_text"})
    return cast(dict[str, Any], _quantize(data))


def compute_architecture_hash(contract: ArchitecturalPlanContract) -> str:
    payload = json.dumps(
        canonical_architecture_data(contract),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def wall_length(wall: ArchitecturalWall) -> float:
    return math.dist(wall.start, wall.end)


def wall_geometry(wall: ArchitecturalWall) -> Polygon:
    geometry = LineString([wall.start, wall.end]).buffer(
        wall.thickness / 2.0,
        cap_style="flat",
        join_style="mitre",
    )
    if not isinstance(geometry, Polygon) or geometry.is_empty or not geometry.is_valid:
        raise ArchitecturalGeometryError(f"invalid wall geometry: {wall.id}")
    return geometry


def opening_geometry(
    opening: ArchitecturalOpening,
    wall: ArchitecturalWall,
) -> Polygon:
    length = wall_length(wall)
    ux = (wall.end[0] - wall.start[0]) / length
    uy = (wall.end[1] - wall.start[1]) / length
    nx, ny = -uy, ux
    start_distance = opening.offset
    end_distance = opening.offset + opening.width
    half_depth = wall.thickness / 2.0 + 0.001
    p1 = (
        wall.start[0] + ux * start_distance + nx * half_depth,
        wall.start[1] + uy * start_distance + ny * half_depth,
    )
    p2 = (
        wall.start[0] + ux * end_distance + nx * half_depth,
        wall.start[1] + uy * end_distance + ny * half_depth,
    )
    p3 = (
        wall.start[0] + ux * end_distance - nx * half_depth,
        wall.start[1] + uy * end_distance - ny * half_depth,
    )
    p4 = (
        wall.start[0] + ux * start_distance - nx * half_depth,
        wall.start[1] + uy * start_distance - ny * half_depth,
    )
    return Polygon([p1, p2, p3, p4])


def column_geometry(column: RectangularColumn | CircularColumn) -> Polygon:
    if isinstance(column, CircularColumn):
        return Point(column.center).buffer(column.diameter / 2.0, quad_segs=64)
    geometry = box(
        column.center[0] - column.width / 2.0,
        column.center[1] - column.depth / 2.0,
        column.center[0] + column.width / 2.0,
        column.center[1] + column.depth / 2.0,
    )
    if column.rotation_deg:
        geometry = affinity.rotate(geometry, column.rotation_deg, origin=column.center)
    return cast(Polygon, geometry)


def architecture_geometry_map(
    contract: ArchitecturalPlanContract,
) -> dict[str, BaseGeometry]:
    result: dict[str, BaseGeometry] = {}
    walls = {wall.id: wall for wall in contract.walls}
    for grid in contract.grids:
        result[grid.id] = LineString([grid.start, grid.end])
    for wall in contract.walls:
        result[wall.id] = wall_geometry(wall)
    for opening in contract.openings:
        result[opening.id] = opening_geometry(opening, walls[opening.wall_id])
    for column in contract.columns:
        result[column.id] = column_geometry(column)
    for room in contract.room_seeds:
        result[room.id] = Point(room.point)
    if any(item.is_empty or not item.is_valid for item in result.values()):
        raise ArchitecturalGeometryError("architectural native geometry is invalid")
    return result


def get_architecture_numeric_path(contract: ArchitecturalPlanContract, path: str) -> float:
    parts = path.split(".")
    collections: dict[str, list[Any]] = {
        "grids": contract.grids,
        "walls": contract.walls,
        "openings": contract.openings,
        "columns": contract.columns,
        "room_seeds": contract.room_seeds,
    }
    if len(parts) < 3 or parts[0] not in collections:
        raise KeyError(path)
    current: Any = next((item for item in collections[parts[0]] if item.id == parts[1]), None)
    if current is None:
        raise KeyError(path)
    remaining = parts[2:]
    for part in remaining:
        if isinstance(current, tuple | list):
            current = current[int(part)]
        elif part == "length" and isinstance(current, ArchitecturalWall):
            current = wall_length(current)
        else:
            current = getattr(current, part)
    if not isinstance(current, int | float):
        raise KeyError(path)
    return float(current)


__all__ = [
    "ArchitecturalGeometryError",
    "architecture_geometry_map",
    "canonical_architecture_data",
    "column_geometry",
    "compute_architecture_hash",
    "get_architecture_numeric_path",
    "normalize_architecture_to_mm",
    "opening_geometry",
    "wall_geometry",
    "wall_length",
]

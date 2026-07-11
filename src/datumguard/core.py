from __future__ import annotations

import hashlib
import json
import math
from typing import Any, cast

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from .models import (
    CircularHole,
    CircularPattern,
    DesignContract,
    LinearPattern,
    PolygonOutline,
    RectangleOutline,
    RectangularCutout,
    Slot,
)

MM_PER_INCH = 25.4
HASH_GRID_MM = 0.001


class GeometryError(ValueError):
    """Raised when a contract cannot produce valid canonical geometry."""


def _scale_pair(value: list[float] | tuple[float, float], factor: float) -> list[float]:
    return [float(value[0]) * factor, float(value[1]) * factor]


def normalize_to_mm(contract: DesignContract) -> DesignContract:
    """Return a validated copy expressed entirely in millimetres."""

    data = contract.model_dump(mode="python")
    factor = MM_PER_INCH if contract.units == "inch" else 1.0
    data["units"] = "mm"
    data["contract_hash"] = None

    datum = data["datum"]
    datum["origin"] = _scale_pair(datum["origin"], factor)

    outline = data["outline"]
    if outline["type"] == "rectangle":
        outline["origin"] = _scale_pair(outline["origin"], factor)
        outline["width"] *= factor
        outline["height"] *= factor
    else:
        outline["points"] = [_scale_pair(point, factor) for point in outline["points"]]

    for feature in data["features"]:
        feature_type = feature["type"]
        if feature_type == "circular_hole":
            feature["center"] = _scale_pair(feature["center"], factor)
            feature["diameter"] *= factor
        elif feature_type == "slot":
            feature["center"] = _scale_pair(feature["center"], factor)
            feature["length"] *= factor
            feature["width"] *= factor
        elif feature_type == "rectangular_cutout":
            feature["origin"] = _scale_pair(feature["origin"], factor)
            feature["width"] *= factor
            feature["height"] *= factor
            feature["corner_radius"] *= factor
        elif feature_type == "linear_pattern":
            feature["spacing"] *= factor
        elif feature_type == "circular_pattern":
            feature["center"] = _scale_pair(feature["center"], factor)

    for dimension in data["dimensions"]:
        dimension["target"] *= factor
        dimension["tolerance_lower"] *= factor
        dimension["tolerance_upper"] *= factor

    scalable_constraint_keys = {
        "minimum_edge_distance",
        "minimum_ligament",
        "target",
        "tolerance",
        "axis_value",
    }
    for constraint in data["constraints"]:
        for key in scalable_constraint_keys:
            value = constraint["parameters"].get(key)
            if isinstance(value, int | float):
                constraint["parameters"][key] = float(value) * factor

    for parameter in data["free_parameters"]:
        parameter_factor = MM_PER_INCH if parameter["unit"] == "inch" else 1.0
        parameter["minimum"] *= parameter_factor
        parameter["maximum"] *= parameter_factor
        parameter["step"] *= parameter_factor
        parameter["unit"] = "mm"

    profile = data["manufacturing_profile"]
    profile["kerf"] *= factor
    if profile["tool_diameter"] is not None:
        profile["tool_diameter"] *= factor
    profile["minimum_feature"] *= factor
    profile["minimum_ligament"] *= factor

    return DesignContract.model_validate(data)


def _quantize(value: Any) -> Any:
    if isinstance(value, float):
        quantized = round(value / HASH_GRID_MM) * HASH_GRID_MM
        return 0.0 if abs(quantized) < HASH_GRID_MM / 2 else round(quantized, 6)
    if isinstance(value, list):
        return [_quantize(item) for item in value]
    if isinstance(value, tuple):
        return [_quantize(item) for item in value]
    if isinstance(value, dict):
        return {key: _quantize(value[key]) for key in sorted(value)}
    return value


def canonical_contract_data(contract: DesignContract) -> dict[str, Any]:
    normalized = normalize_to_mm(contract)
    data = normalized.model_dump(mode="json", exclude={"contract_hash", "intent_text"})
    return cast(dict[str, Any], _quantize(data))


def compute_contract_hash(contract: DesignContract) -> str:
    canonical = canonical_contract_data(contract)
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def compute_artifact_hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def outline_geometry(outline: RectangleOutline | PolygonOutline) -> Polygon:
    if isinstance(outline, RectangleOutline):
        x, y = outline.origin
        geometry = box(x, y, x + outline.width, y + outline.height)
    else:
        geometry = Polygon(outline.points)
    if not geometry.is_valid or geometry.is_empty or geometry.area <= 0:
        raise GeometryError("outline must be a valid, non-self-intersecting closed polygon")
    return geometry


def feature_geometry(feature: CircularHole | Slot | RectangularCutout) -> Polygon:
    if isinstance(feature, CircularHole):
        return Point(feature.center).buffer(feature.diameter / 2.0, quad_segs=64)
    if isinstance(feature, Slot):
        half_segment = max((feature.length - feature.width) / 2.0, 0.0)
        angle = math.radians(feature.angle_deg)
        dx = math.cos(angle) * half_segment
        dy = math.sin(angle) * half_segment
        start = (feature.center[0] - dx, feature.center[1] - dy)
        end = (feature.center[0] + dx, feature.center[1] + dy)
        return cast(
            Polygon,
            LineString([start, end]).buffer(feature.width / 2.0, quad_segs=64),
        )
    geometry = box(
        feature.origin[0],
        feature.origin[1],
        feature.origin[0] + feature.width,
        feature.origin[1] + feature.height,
    )
    if feature.corner_radius > 0:
        geometry = geometry.buffer(-feature.corner_radius, join_style="round").buffer(
            feature.corner_radius,
            join_style="round",
        )
    return cast(Polygon, geometry)


def _move_feature(
    source: CircularHole | Slot | RectangularCutout,
    dx: float,
    dy: float,
    new_id: str,
) -> CircularHole | Slot | RectangularCutout:
    data = source.model_dump(mode="python")
    data["id"] = new_id
    coordinate_key = "origin" if isinstance(source, RectangularCutout) else "center"
    data[coordinate_key] = [
        float(data[coordinate_key][0]) + dx,
        float(data[coordinate_key][1]) + dy,
    ]
    return type(source).model_validate(data)


def _rotate_feature(
    source: CircularHole | Slot,
    center: tuple[float, float],
    angle_deg: float,
    new_id: str,
) -> CircularHole | Slot:
    data = source.model_dump(mode="python")
    point = Point(source.center)
    rotated = affinity.rotate(point, angle_deg, origin=center)
    data["id"] = new_id
    data["center"] = [rotated.x, rotated.y]
    if isinstance(source, Slot):
        data["angle_deg"] = source.angle_deg + angle_deg
    return type(source).model_validate(data)


def expand_features(contract: DesignContract) -> list[CircularHole | Slot | RectangularCutout]:
    """Expand patterns deterministically; source geometry is count item one."""

    base = [
        feature
        for feature in contract.features
        if isinstance(feature, CircularHole | Slot | RectangularCutout)
    ]
    by_id = {feature.id: feature for feature in base}
    expanded = list(base)
    for pattern in contract.features:
        if isinstance(pattern, LinearPattern):
            source = by_id.get(pattern.source_feature_id)
            if source is None:
                raise GeometryError(f"pattern source is not a primitive feature: {pattern.id}")
            for index in range(1, pattern.count):
                distance = pattern.spacing * index
                expanded.append(
                    _move_feature(
                        source,
                        pattern.direction[0] * distance,
                        pattern.direction[1] * distance,
                        f"{pattern.id}__{index + 1}",
                    )
                )
        elif isinstance(pattern, CircularPattern):
            source = by_id.get(pattern.source_feature_id)
            if not isinstance(source, CircularHole | Slot):
                raise GeometryError(
                    f"circular pattern supports holes and slots only in schema 1.0.0: {pattern.id}"
                )
            for index in range(1, pattern.count):
                expanded.append(
                    _rotate_feature(
                        source,
                        pattern.center,
                        pattern.angle_step_deg * index,
                        f"{pattern.id}__{index + 1}",
                    )
                )
    if len(expanded) > 200:
        raise GeometryError("expanded feature count exceeds the MVP limit of 200")
    return expanded


def geometry_map(contract: DesignContract) -> dict[str, BaseGeometry]:
    result: dict[str, BaseGeometry] = {contract.outline.id: outline_geometry(contract.outline)}
    for feature in expand_features(contract):
        geometry = feature_geometry(feature)
        if not geometry.is_valid or geometry.is_empty:
            raise GeometryError(f"invalid feature geometry: {feature.id}")
        result[feature.id] = geometry
    return result


def get_numeric_path(contract: DesignContract, path: str) -> float:
    parts = path.split(".")
    if parts[0] == "outline":
        current: Any = contract.outline
        remaining = parts[1:]
    elif len(parts) >= 3 and parts[0] == "features":
        feature = next((item for item in contract.features if item.id == parts[1]), None)
        if feature is None:
            raise KeyError(path)
        current = feature
        remaining = parts[2:]
    elif parts[0] == "manufacturing_profile":
        current = contract.manufacturing_profile
        remaining = parts[1:]
    else:
        raise KeyError(path)

    for part in remaining:
        if isinstance(current, tuple | list):
            current = current[int(part)]
        else:
            current = getattr(current, part)
    if not isinstance(current, int | float):
        raise KeyError(path)
    return float(current)


def set_numeric_path(contract: DesignContract, path: str, value: float) -> DesignContract:
    # JSON mode intentionally converts immutable coordinate tuples into mutable lists.
    data = json.loads(contract.model_dump_json())
    parts = path.split(".")
    if parts[0] == "outline":
        current: Any = data["outline"]
        remaining = parts[1:]
    elif len(parts) >= 3 and parts[0] == "features":
        current = next((item for item in data["features"] if item["id"] == parts[1]), None)
        if current is None:
            raise KeyError(path)
        remaining = parts[2:]
    elif parts[0] == "manufacturing_profile":
        current = data["manufacturing_profile"]
        remaining = parts[1:]
    else:
        raise KeyError(path)

    for index, part in enumerate(remaining):
        is_last = index == len(remaining) - 1
        if isinstance(current, list):
            item_index = int(part)
            if is_last:
                current[item_index] = value
            else:
                current = current[item_index]
        else:
            if is_last:
                current[part] = value
            else:
                current = current[part]
    data["contract_hash"] = None
    return DesignContract.model_validate(data)

from __future__ import annotations

import hashlib
import importlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def stable_issue_key(*parts: Any) -> str:
    digest = hashlib.sha256(canonical_json_bytes(parts)).hexdigest()[:24]
    return f"dg:{digest}"


def open_ifc_bytes(data: bytes) -> Any:
    if not data or len(data) < 32:
        raise ValueError("IFC input is empty or truncated")
    try:
        text = data.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("IFC input must be UTF-8 STEP text") from exc
    if "ISO-10303-21" not in text[:512].upper() or "END-ISO-10303-21" not in text[-1024:].upper():
        raise ValueError("IFC input is not a complete ISO-10303-21 document")
    ifcopenshell: Any = importlib.import_module("ifcopenshell")
    try:
        return ifcopenshell.file.from_string(text)
    except Exception as exc:
        raise ValueError("IFC input could not be parsed") from exc


def project_unit_scale_to_m(model: Any) -> float | None:
    try:
        unit_module: Any = importlib.import_module("ifcopenshell.util.unit")
        unit = unit_module.get_project_unit(model, "LENGTHUNIT")
        scale = float(unit_module.calculate_unit_scale(model, "LENGTHUNIT"))
    except Exception:
        return None
    if unit is None or not math.isfinite(scale) or scale <= 0:
        return None
    return scale


def entity_psets(entity: Any) -> dict[str, dict[str, Any]]:
    try:
        element_module: Any = importlib.import_module("ifcopenshell.util.element")
        raw = element_module.get_psets(entity, psets_only=True)
    except Exception:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for pset_name, values in raw.items():
        if not isinstance(values, Mapping):
            continue
        result[str(pset_name)] = {
            str(key): value for key, value in values.items() if str(key) != "id"
        }
    return result


def property_value(entity: Any, path: str) -> Any | None:
    if "." not in path:
        return getattr(entity, path, None)
    pset_name, property_name = path.split(".", 1)
    return entity_psets(entity).get(pset_name, {}).get(property_name)


def normalized_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return round(value, 12)
    wrapped = getattr(value, "wrappedValue", None)
    if wrapped is not None:
        return normalized_scalar(wrapped)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalized_scalar(item) for item in value]
    return str(value)


def entity_global_id(entity: Any) -> str:
    return str(getattr(entity, "GlobalId", "") or "")


def entity_step_id(entity: Any) -> int:
    try:
        return int(entity.id())
    except Exception:
        return 0


def entity_stable_id(entity: Any) -> str:
    return entity_global_id(entity) or f"#{entity_step_id(entity)}"


def entity_container(entity: Any) -> Any | None:
    relationships = list(getattr(entity, "ContainedInStructure", ()) or ())
    if len(relationships) != 1:
        return None
    return getattr(relationships[0], "RelatingStructure", None)


def entity_container_id(entity: Any) -> str | None:
    container = entity_container(entity)
    return entity_global_id(container) or None if container is not None else None


def is_required_product(entity: Any, applicable_entities: Sequence[str]) -> bool:
    return any(bool(entity.is_a(ifc_class)) for ifc_class in applicable_entities)


def world_aabb(
    entity: Any,
) -> tuple[tuple[float, float, float], tuple[float, float, float], int] | None:
    """Return an SI-metre world AABB and vertex count for a represented product."""

    if getattr(entity, "Representation", None) is None:
        return None
    try:
        geom: Any = importlib.import_module("ifcopenshell.geom")
        settings = geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = geom.create_shape(settings, entity)
        vertices = tuple(float(value) for value in shape.geometry.verts)
    except Exception:
        return None
    if len(vertices) < 3 or len(vertices) % 3:
        return None
    xs = vertices[0::3]
    ys = vertices[1::3]
    zs = vertices[2::3]
    minimum = (min(xs), min(ys), min(zs))
    maximum = (max(xs), max(ys), max(zs))
    if not all(math.isfinite(value) for value in (*minimum, *maximum)):
        return None
    return minimum, maximum, len(vertices) // 3


_SIDE_VECTORS: dict[str, tuple[float, float, float]] = {
    "+X": (1.0, 0.0, 0.0),
    "-X": (-1.0, 0.0, 0.0),
    "+Y": (0.0, 1.0, 0.0),
    "-Y": (0.0, -1.0, 0.0),
}


def orthogonal_world_side(entity: Any, service_side: str) -> tuple[int, int] | None:
    """Map a local +/-X or +/-Y side onto an orthogonal world axis."""

    vector = _SIDE_VECTORS.get(service_side)
    if vector is None:
        return None
    placement = getattr(entity, "ObjectPlacement", None)
    if placement is None:
        matrix: Any = (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    else:
        try:
            placement_module: Any = importlib.import_module("ifcopenshell.util.placement")
            matrix = placement_module.get_local_placement(placement)
        except Exception:
            return None
    world = [
        sum(float(matrix[row][column]) * vector[column] for column in range(3)) for row in range(3)
    ]
    axis = max(range(3), key=lambda index: abs(world[index]))
    if axis == 2 or abs(abs(world[axis]) - 1.0) > 1e-6:
        return None
    if any(abs(world[index]) > 1e-6 for index in range(3) if index != axis):
        return None
    return axis, 1 if world[axis] > 0 else -1


def service_envelope(
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]],
    *,
    world_side: tuple[int, int],
    depth_m: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    minimum = list(bounds[0])
    maximum = list(bounds[1])
    axis, direction = world_side
    if direction > 0:
        minimum[axis] = maximum[axis]
        maximum[axis] += depth_m
    else:
        maximum[axis] = minimum[axis]
        minimum[axis] -= depth_m
    return tuple(minimum), tuple(maximum)  # type: ignore[return-value]


def aabb_positive_overlap(
    left: tuple[tuple[float, float, float], tuple[float, float, float]],
    right: tuple[tuple[float, float, float], tuple[float, float, float]],
    *,
    epsilon: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    lower = (
        max(left[0][0], right[0][0]),
        max(left[0][1], right[0][1]),
        max(left[0][2], right[0][2]),
    )
    upper = (
        min(left[1][0], right[1][0]),
        min(left[1][1], right[1][1]),
        min(left[1][2], right[1][2]),
    )
    depths = (upper[0] - lower[0], upper[1] - lower[1], upper[2] - lower[2])
    if any(depth <= epsilon for depth in depths):
        return None
    center = (
        (lower[0] + upper[0]) / 2.0,
        (lower[1] + upper[1]) / 2.0,
        (lower[2] + upper[2]) / 2.0,
    )
    return depths, center


__all__ = [
    "aabb_positive_overlap",
    "canonical_json_bytes",
    "entity_container",
    "entity_container_id",
    "entity_global_id",
    "entity_psets",
    "entity_stable_id",
    "entity_step_id",
    "is_required_product",
    "normalized_scalar",
    "open_ifc_bytes",
    "orthogonal_world_side",
    "project_unit_scale_to_m",
    "property_value",
    "service_envelope",
    "sha256_bytes",
    "stable_issue_key",
    "world_aabb",
]

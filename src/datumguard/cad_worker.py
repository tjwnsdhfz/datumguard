from __future__ import annotations

import base64
import json
import math
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import cadquery

from .solid_models import (
    AngleBracketSolid,
    FlangeSolid,
    MountingPlateSolid,
    SolidPartContract,
)

MAX_PREVIEW_TRIANGLES = 3500


def _group_holes(holes: list[Any]) -> dict[float, list[tuple[float, float]]]:
    grouped: dict[float, list[tuple[float, float]]] = defaultdict(list)
    for hole in holes:
        grouped[float(hole.diameter)].append((float(hole.center[0]), float(hole.center[1])))
    return dict(grouped)


def _build_shape(contract: SolidPartContract) -> Any:
    geometry = contract.geometry
    if isinstance(geometry, MountingPlateSolid):
        part = cadquery.Workplane("XY").box(
            geometry.width,
            geometry.depth,
            geometry.thickness,
            centered=(True, True, False),
        )
        if geometry.corner_radius > 0:
            part = part.edges("|Z").fillet(geometry.corner_radius)
        for diameter, centers in _group_holes(geometry.holes).items():
            part = part.faces(">Z").workplane().pushPoints(centers).hole(diameter)
        return part.val()
    if isinstance(geometry, AngleBracketSolid):
        base = cadquery.Workplane("XY").box(
            geometry.width,
            geometry.base_depth,
            geometry.base_thickness,
            centered=(True, True, False),
        )
        for diameter, centers in _group_holes(geometry.base_holes).items():
            base = base.faces(">Z").workplane().pushPoints(centers).hole(diameter)
        vertical = (
            cadquery.Workplane("XY")
            .box(
                geometry.width,
                geometry.vertical_thickness,
                geometry.vertical_height,
                centered=(True, True, False),
            )
            .translate((0, -(geometry.base_depth - geometry.vertical_thickness) / 2, 0))
        )
        return base.union(vertical).val()
    if isinstance(geometry, FlangeSolid):
        flange = (
            cadquery.Workplane("XY")
            .circle(geometry.outer_diameter / 2)
            .circle(geometry.inner_diameter / 2)
            .extrude(geometry.thickness)
        )
        radius = geometry.bolt_circle_diameter / 2
        points = [
            (
                radius * math.cos(2 * math.pi * index / geometry.bolt_hole_count),
                radius * math.sin(2 * math.pi * index / geometry.bolt_hole_count),
            )
            for index in range(geometry.bolt_hole_count)
        ]
        return (
            flange.faces(">Z")
            .workplane()
            .pushPoints(points)
            .hole(geometry.bolt_hole_diameter)
            .val()
        )
    raise ValueError("unsupported solid geometry")


def _mesh(shape: Any) -> dict[str, Any] | None:
    bounds = shape.BoundingBox()
    diagonal = math.sqrt(bounds.xlen**2 + bounds.ylen**2 + bounds.zlen**2)
    vertices, triangles = shape.tessellate(max(0.05, diagonal / 250))
    source_count = len(triangles)
    selected = list(triangles[:MAX_PREVIEW_TRIANGLES])
    used_indices = sorted({int(index) for triangle in selected for index in triangle})
    index_map = {source: target for target, source in enumerate(used_indices)}
    mesh_vertices: list[tuple[float, float, float]] = []
    for index in used_indices:
        coordinates = vertices[index].toTuple()
        mesh_vertices.append(
            (
                round(float(coordinates[0]), 6),
                round(float(coordinates[1]), 6),
                round(float(coordinates[2]), 6),
            )
        )
    mesh_triangles = [
        (
            index_map[int(triangle[0])],
            index_map[int(triangle[1])],
            index_map[int(triangle[2])],
        )
        for triangle in selected
    ]
    return {
        "vertices": mesh_vertices,
        "triangles": mesh_triangles,
        "truncated": source_count > len(selected),
        "source_triangle_count": source_count,
    }


def _cylinders(shape: Any) -> list[dict[str, Any]]:
    cylinders: list[dict[str, Any]] = []
    for index, face in enumerate(shape.Faces()):
        if face.geomType() != "CYLINDER":
            continue
        cylinder = face._geomAdaptor().Cylinder()
        axis = cylinder.Axis()
        location = axis.Location()
        direction = axis.Direction()
        cylinders.append(
            {
                "face_index": index,
                "diameter": round(float(cylinder.Radius()) * 2, 6),
                "axis_origin": [
                    round(float(location.X()), 6),
                    round(float(location.Y()), 6),
                    round(float(location.Z()), 6),
                ],
                "axis_direction": [
                    round(float(direction.X()), 6),
                    round(float(direction.Y()), 6),
                    round(float(direction.Z()), 6),
                ],
            }
        )
    return cylinders


def _generate_solid(payload: dict[str, Any]) -> dict[str, Any]:
    contract = SolidPartContract.model_validate(payload["contract"])
    shape = _build_shape(contract)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "solid.step"
        shape.exportStep(str(path), unit="MM", outputUnit="MM")
        step_bytes = path.read_bytes()
    return {"step_base64": base64.b64encode(step_bytes).decode("ascii")}


def _audit_step(payload: dict[str, Any]) -> dict[str, Any]:
    step_bytes = base64.b64decode(str(payload["content_base64"]), validate=True)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "artifact.step"
        path.write_bytes(step_bytes)
        shape: Any = cadquery.importers.importStep(str(path), unit="MM").val()
    bounds = shape.BoundingBox()
    center = shape.Center()
    summary = {
        "valid_shape": bool(shape.isValid()),
        "solid_count": len(shape.Solids()),
        "face_count": len(shape.Faces()),
        "edge_count": len(shape.Edges()),
        "vertex_count": len(shape.Vertices()),
        "bounding_box_mm": {
            "minimum": [round(bounds.xmin, 6), round(bounds.ymin, 6), round(bounds.zmin, 6)],
            "maximum": [round(bounds.xmax, 6), round(bounds.ymax, 6), round(bounds.zmax, 6)],
            "size": [round(bounds.xlen, 6), round(bounds.ylen, 6), round(bounds.zlen, 6)],
        },
        "center_of_mass_mm": [round(center.x, 6), round(center.y, 6), round(center.z, 6)],
        "volume_mm3": round(float(shape.Volume()), 6),
        "surface_area_mm2": round(float(shape.Area()), 6),
        "cylindrical_surfaces": _cylinders(shape),
    }
    return {"summary": summary, "preview_mesh": _mesh(shape)}


def main() -> None:
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    operation = payload.get("operation")
    if operation == "generate_solid":
        result = _generate_solid(payload)
    elif operation == "audit_step":
        result = _audit_step(payload)
    else:
        raise ValueError("unsupported CAD worker operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

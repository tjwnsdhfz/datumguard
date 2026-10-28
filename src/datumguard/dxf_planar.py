"""Reject DXF primitives that cannot be faithfully read as flat XY geometry."""

from __future__ import annotations

import math

from ezdxf.entities.circle import Circle
from ezdxf.entities.dxfentity import DXFEntity
from ezdxf.entities.line import Line
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.entities.point import Point


def supports_flat_xy(
    entity: DXFEntity,
    *,
    epsilon: float = 0.001,
    allow_constant_width: bool = False,
) -> bool:
    extrusion = tuple(float(value) for value in entity.dxf.get("extrusion", (0, 0, 1)))
    thickness = float(entity.dxf.get("thickness", 0))
    if (
        not all(math.isfinite(value) for value in (*extrusion, thickness))
        or math.dist(extrusion, (0, 0, 1)) > 1e-9
        or abs(thickness) > epsilon
    ):
        return False
    if isinstance(entity, LWPolyline):
        elevation = float(entity.dxf.elevation)
        width = float(entity.dxf.const_width)
        return (
            math.isfinite(elevation)
            and abs(elevation) <= epsilon
            and math.isfinite(width)
            and (allow_constant_width or width == 0)
            and all(
                all(math.isfinite(value) for value in point)
                and point[2] == 0
                and point[3] == 0
                and point[4] == 0
                for point in entity.get_points("xyseb")
            )
        )
    if isinstance(entity, Circle):
        positions = [entity.dxf.center]
        if not math.isfinite(float(entity.dxf.radius)) or entity.dxf.radius <= 0:
            return False
    elif isinstance(entity, Line):
        positions = [entity.dxf.start, entity.dxf.end]
    elif isinstance(entity, Point):
        positions = [entity.dxf.location]
    else:
        return False
    return all(
        all(math.isfinite(value) for value in point) and abs(point.z) <= epsilon
        for point in positions
    )

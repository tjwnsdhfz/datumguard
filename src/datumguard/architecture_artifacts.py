from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from html import escape
from typing import Any

from ezdxf import units
from ezdxf._options import options
from ezdxf.document import Drawing
from ezdxf.entities.dxfentity import DXFEntity
from ezdxf.filemanagement import new
from ezdxf.lldxf.const import DXFError
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .architecture_core import (
    architecture_geometry_map,
    column_geometry,
    opening_geometry,
    wall_geometry,
)
from .architecture_models import ArchitecturalPlanContract, CircularColumn
from .core import compute_artifact_hash

ARCHITECTURE_DXF_LAYERS = (
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
)
ARCHITECTURE_XDATA_APP_ID = "DATUMGUARD"

options.write_fixed_meta_data_for_testing = True


@dataclass(frozen=True)
class GeneratedArchitecturalDrawing:
    dxf_bytes: bytes
    preview_svg: str
    contract_hash: str
    artifact_hash: str


def _set_xdata(
    entity: DXFEntity,
    *,
    contract_hash: str,
    feature_id: str,
    feature_type: str,
    revision: str,
) -> None:
    entity.set_xdata(
        ARCHITECTURE_XDATA_APP_ID,
        [
            (1000, f"contract_hash={contract_hash}"),
            (1000, f"entity_id={feature_id}"),
            (1000, f"entity_type={feature_type}"),
            (1000, "design_kind=architectural_plan"),
            (1000, f"revision={revision}"),
        ],
    )


def _polygon_points(geometry: Polygon) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in list(geometry.exterior.coords)[:-1]]


def _stabilize_header(document: Drawing) -> None:
    values: dict[str, Any] = {
        "$TDCREATE": 0.0,
        "$TDUPDATE": 0.0,
        "$TDUCREATE": 0.0,
        "$TDUUPDATE": 0.0,
        "$FINGERPRINTGUID": "{00000000-0000-0000-0000-000000000000}",
        "$VERSIONGUID": "{00000000-0000-0000-0000-000000000000}",
    }
    for name, value in values.items():
        try:
            document.header[name] = value
        except (DXFError, ValueError):
            continue


def generate_architecture_dxf(
    contract: ArchitecturalPlanContract,
    contract_hash: str,
) -> bytes:
    document = new("R2013", setup=False)
    document.units = units.MM
    _stabilize_header(document)
    if ARCHITECTURE_XDATA_APP_ID not in document.appids:
        document.appids.add(ARCHITECTURE_XDATA_APP_ID)
    colors = {
        "A-GRID": 8,
        "A-WALL": 7,
        "A-WALL-CENTER": 9,
        "A-DOOR": 1,
        "A-WIND": 5,
        "A-COLS": 3,
        "A-ROOM": 4,
        "A-DIMS": 2,
        "A-ANNO": 6,
        "DG-META": 6,
    }
    for layer in ARCHITECTURE_DXF_LAYERS:
        if layer not in document.layers:
            document.layers.add(layer, color=colors[layer])

    modelspace = document.modelspace()
    revision = contract.metadata.revision
    walls = {wall.id: wall for wall in contract.walls}
    entity: DXFEntity
    for grid in contract.grids:
        entity = modelspace.add_line(grid.start, grid.end, dxfattribs={"layer": "A-GRID"})
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=grid.id,
            feature_type="grid",
            revision=revision,
        )
    for wall in contract.walls:
        entity = modelspace.add_lwpolyline(
            _polygon_points(wall_geometry(wall)),
            close=True,
            dxfattribs={"layer": "A-WALL"},
        )
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=wall.id,
            feature_type="wall",
            revision=revision,
        )
        entity = modelspace.add_line(
            wall.start,
            wall.end,
            dxfattribs={"layer": "A-WALL-CENTER"},
        )
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=wall.id,
            feature_type="wall_centerline",
            revision=revision,
        )
    for opening in contract.openings:
        layer = "A-WIND" if opening.type == "window" else "A-DOOR"
        entity = modelspace.add_lwpolyline(
            _polygon_points(opening_geometry(opening, walls[opening.wall_id])),
            close=True,
            dxfattribs={"layer": layer},
        )
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=opening.id,
            feature_type=opening.type,
            revision=revision,
        )
    for column in contract.columns:
        if isinstance(column, CircularColumn):
            entity = modelspace.add_circle(
                column.center,
                column.diameter / 2.0,
                dxfattribs={"layer": "A-COLS"},
            )
        else:
            entity = modelspace.add_lwpolyline(
                _polygon_points(column_geometry(column)),
                close=True,
                dxfattribs={"layer": "A-COLS"},
            )
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=column.id,
            feature_type=column.type,
            revision=revision,
        )
    for room in contract.room_seeds:
        entity = modelspace.add_point(room.point, dxfattribs={"layer": "A-ROOM"})
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=room.id,
            feature_type="room_seed",
            revision=revision,
        )

    geometries = architecture_geometry_map(contract)
    min_x, min_y, max_x, max_y = unary_union(list(geometries.values())).bounds
    text_height = max(max(max_x - min_x, max_y - min_y) * 0.018, 80.0)
    if contract.drawing_profile.include_dimensions:
        for index, dimension in enumerate(contract.dimensions):
            entity = modelspace.add_text(
                f"{dimension.id}: {dimension.target:.3f} mm",
                height=text_height,
                dxfattribs={"layer": "A-DIMS"},
            )
            entity.set_placement((min_x, max_y + text_height * (index + 1.5)))
            _set_xdata(
                entity,
                contract_hash=contract_hash,
                feature_id=dimension.id,
                feature_type="dimension",
                revision=revision,
            )
    if contract.drawing_profile.include_room_labels:
        for room in contract.room_seeds:
            entity = modelspace.add_text(
                room.name,
                height=text_height,
                dxfattribs={"layer": "A-ANNO"},
            )
            entity.set_placement(room.point)
            _set_xdata(
                entity,
                contract_hash=contract_hash,
                feature_id=room.id,
                feature_type="room_annotation",
                revision=revision,
            )
    entity = modelspace.add_text(
        f"{contract.metadata.project_name} | Rev {revision} | DO NOT SCALE",
        height=text_height,
        dxfattribs={"layer": "DG-META"},
    )
    entity.set_placement((min_x, min_y - text_height * 2))
    _set_xdata(
        entity,
        contract_hash=contract_hash,
        feature_id="architectural-metadata",
        feature_type="metadata",
        revision=revision,
    )

    stream = io.StringIO(newline="\n")
    document.write(stream, fmt="asc")
    return stream.getvalue().encode("utf-8")


def render_architecture_svg(
    contract: ArchitecturalPlanContract,
    contract_hash: str,
) -> str:
    geometries = architecture_geometry_map(contract)
    bounds = unary_union(list(geometries.values())).bounds
    min_x, min_y, max_x, max_y = bounds
    span = max(max_x - min_x, max_y - min_y, 1.0)
    padding = span * 0.05
    view_x, view_y = min_x - padding, min_y - padding
    view_width = max_x - min_x + padding * 2
    view_height = max_y - min_y + padding * 2
    flip_origin = min_y + max_y

    def polygon(geometry: Polygon, entity_id: str, css_class: str) -> str:
        points = " ".join(f"{x:.6f},{y:.6f}" for x, y in _polygon_points(geometry))
        return (
            f'<polygon id="{escape(entity_id)}" data-feature-id="{escape(entity_id)}" '
            f'class="{css_class}" points="{points}" />'
        )

    elements: list[str] = []
    walls = {wall.id: wall for wall in contract.walls}
    for grid in contract.grids:
        elements.append(
            f'<line class="grid" data-feature-id="{escape(grid.id)}" '
            f'x1="{grid.start[0]:.6f}" y1="{grid.start[1]:.6f}" '
            f'x2="{grid.end[0]:.6f}" y2="{grid.end[1]:.6f}" />'
        )
    for wall in contract.walls:
        elements.append(polygon(wall_geometry(wall), wall.id, "wall"))
    for opening in contract.openings:
        elements.append(
            polygon(opening_geometry(opening, walls[opening.wall_id]), opening.id, "opening")
        )
    for column in contract.columns:
        if isinstance(column, CircularColumn):
            elements.append(
                f'<circle class="column" data-feature-id="{escape(column.id)}" '
                f'cx="{column.center[0]:.6f}" cy="{column.center[1]:.6f}" '
                f'r="{column.diameter / 2.0:.6f}" />'
            )
        else:
            elements.append(polygon(column_geometry(column), column.id, "column"))
    for room in contract.room_seeds:
        elements.append(
            f'<circle class="room" data-feature-id="{escape(room.id)}" '
            f'cx="{room.point[0]:.6f}" cy="{room.point[1]:.6f}" r="75" />'
        )

    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" role="img" '
            f'viewBox="{view_x:.6f} {view_y:.6f} {view_width:.6f} {view_height:.6f}">',
            f"<title>{escape(contract.metadata.project_name)} architectural plan</title>",
            "<style>.grid{stroke:#91a09a;stroke-dasharray:14 8;fill:none}"
            ".wall{fill:#183c32;stroke:#102b24}"
            ".opening{fill:#fff;stroke:#dc6046}.column{fill:#dba94b;stroke:#755516}"
            ".room{fill:#288d78;stroke:none;vector-effect:non-scaling-stroke}</style>",
            f"<metadata>contract_hash={escape(contract_hash)}</metadata>",
            f'<g transform="translate(0 {flip_origin:.6f}) scale(1 -1)">',
            *elements,
            "</g>",
            "</svg>",
        ]
    )


def generate_architecture_drawing(
    contract: ArchitecturalPlanContract,
    contract_hash: str,
) -> GeneratedArchitecturalDrawing:
    dxf_bytes = generate_architecture_dxf(contract, contract_hash)
    return GeneratedArchitecturalDrawing(
        dxf_bytes=dxf_bytes,
        preview_svg=render_architecture_svg(contract, contract_hash),
        contract_hash=contract_hash,
        artifact_hash=compute_artifact_hash(dxf_bytes),
    )


def render_architecture_pdf(
    contract: ArchitecturalPlanContract,
    *,
    contract_hash: str,
    artifact_hash: str,
) -> bytes:
    output = io.BytesIO()
    page_width, page_height = landscape(A3)
    pdf = canvas.Canvas(output, pagesize=(page_width, page_height), invariant=1)
    pdf.setTitle(f"DatumGuard Architecture - {contract.metadata.project_name}")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(15 * mm, page_height - 15 * mm, contract.metadata.project_name[:70])
    pdf.setFont("Helvetica-Bold", 18)
    pdf.setFillColorRGB(0.75, 0.08, 0.06)
    pdf.drawRightString(page_width - 15 * mm, page_height - 15 * mm, "DO NOT SCALE")

    shapes = architecture_geometry_map(contract)
    min_x, min_y, max_x, max_y = unary_union(list(shapes.values())).bounds
    draw_left, draw_bottom = 15 * mm, 28 * mm
    draw_width, draw_height = page_width - 30 * mm, page_height - 55 * mm
    scale = min(draw_width / max(max_x - min_x, 1.0), draw_height / max(max_y - min_y, 1.0))

    def xy(point: tuple[float, float]) -> tuple[float, float]:
        return (
            draw_left + (point[0] - min_x) * scale,
            draw_bottom + (point[1] - min_y) * scale,
        )

    for wall in contract.walls:
        points = _polygon_points(wall_geometry(wall))
        path = pdf.beginPath()
        first = xy(points[0])
        path.moveTo(*first)
        for point in points[1:]:
            path.lineTo(*xy(point))
        path.close()
        pdf.setFillColorRGB(0.10, 0.24, 0.20)
        pdf.drawPath(path, fill=1, stroke=0)
    for opening in contract.openings:
        wall = next(wall for wall in contract.walls if wall.id == opening.wall_id)
        points = _polygon_points(opening_geometry(opening, wall))
        path = pdf.beginPath()
        path.moveTo(*xy(points[0]))
        for point in points[1:]:
            path.lineTo(*xy(point))
        path.close()
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setStrokeColorRGB(0.75, 0.18, 0.12)
        pdf.drawPath(path, fill=1, stroke=1)
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(
        15 * mm,
        17 * mm,
        f"Revision {contract.metadata.revision} | Units mm | DXF authority",
    )
    pdf.drawString(15 * mm, 12 * mm, f"Contract {contract_hash} | Artifact {artifact_hash}")
    pdf.save()
    return output.getvalue()


def build_verified_architecture_bundle(
    contract: ArchitecturalPlanContract,
    *,
    contract_hash: str,
    artifact_hash: str,
    dxf_bytes: bytes,
    preview_svg: str,
    verification: dict[str, Any],
) -> bytes:
    if verification.get("status") != "passed" or verification.get("violations"):
        raise PermissionError("DG_EXPORT_NOT_APPROVED")
    contract_data = contract.model_dump(mode="json")
    contract_data["contract_hash"] = contract_hash
    manifest = {
        "schema_version": contract.schema_version,
        "design_kind": "architectural_plan",
        "contract_hash": contract_hash,
        "artifact_hash": artifact_hash,
        "approval": "passed",
        "authority": "architectural-plan.dxf",
        "pdf_notice": "DO NOT SCALE",
        "files": [
            "architectural-plan.dxf",
            "preview.svg",
            "architectural-plan-do-not-scale.pdf",
            "architectural-plan-contract.json",
            "verification.json",
        ],
    }
    files = {
        "architectural-plan.dxf": dxf_bytes,
        "preview.svg": preview_svg.encode("utf-8"),
        "architectural-plan-do-not-scale.pdf": render_architecture_pdf(
            contract,
            contract_hash=contract_hash,
            artifact_hash=artifact_hash,
        ),
        "architectural-plan-contract.json": json.dumps(
            contract_data, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8"),
        "verification.json": json.dumps(
            verification, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8"),
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        ),
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for filename in sorted(files):
            info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, files[filename])
    return archive.getvalue()


__all__ = [
    "ARCHITECTURE_DXF_LAYERS",
    "ARCHITECTURE_XDATA_APP_ID",
    "GeneratedArchitecturalDrawing",
    "build_verified_architecture_bundle",
    "generate_architecture_drawing",
    "generate_architecture_dxf",
    "render_architecture_pdf",
    "render_architecture_svg",
]

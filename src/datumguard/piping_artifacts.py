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

from .core import compute_artifact_hash
from .piping_core import (
    equipment_zone_geometry,
    piping_geometry_map,
    point_at_offset,
    segment_line,
)
from .piping_models import (
    CircularEquipmentZone,
    Instrument,
    PipingPlanContract,
    Reducer,
    Valve,
)

PIPING_DXF_LAYERS = (
    "P-PIPE",
    "P-NODE",
    "P-COMP",
    "P-SUPPORT",
    "P-EQUIP",
    "P-DIMS",
    "P-META",
)
PIPING_XDATA_APP_ID = "DATUMGUARD"

options.write_fixed_meta_data_for_testing = True


@dataclass(frozen=True)
class GeneratedPipingDrawing:
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
    extra: dict[str, str] | None = None,
) -> None:
    values = [
        (1000, f"contract_hash={contract_hash}"),
        (1000, f"feature_id={feature_id}"),
        (1000, f"feature_type={feature_type}"),
        (1000, "design_kind=piping_plan"),
        (1000, f"revision={revision}"),
    ]
    values.extend((1000, f"{key}={value}") for key, value in sorted((extra or {}).items()))
    entity.set_xdata(PIPING_XDATA_APP_ID, values)


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


def _polygon_points(geometry: Polygon) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in list(geometry.exterior.coords)[:-1]]


def _segment_basis(
    contract: PipingPlanContract,
    segment_id: str,
) -> tuple[tuple[float, float], tuple[float, float]]:
    segment = next(item for item in contract.segments if item.id == segment_id)
    line = segment_line(contract, segment)
    start = line.coords[0]
    end = line.coords[-1]
    ux = (end[0] - start[0]) / line.length
    uy = (end[1] - start[1]) / line.length
    return (ux, uy), (-uy, ux)


def _local_point(
    center: tuple[float, float],
    along: tuple[float, float],
    normal: tuple[float, float],
    x: float,
    y: float,
) -> tuple[float, float]:
    return (
        center[0] + along[0] * x + normal[0] * y,
        center[1] + along[1] * x + normal[1] * y,
    )


def generate_piping_dxf(contract: PipingPlanContract, contract_hash: str) -> bytes:
    document = new("R2013", setup=False)
    document.units = units.MM
    _stabilize_header(document)
    if PIPING_XDATA_APP_ID not in document.appids:
        document.appids.add(PIPING_XDATA_APP_ID)
    colors = {
        "P-PIPE": 4,
        "P-NODE": 7,
        "P-COMP": 1,
        "P-SUPPORT": 3,
        "P-EQUIP": 8,
        "P-DIMS": 2,
        "P-META": 6,
    }
    for layer in PIPING_DXF_LAYERS:
        if layer not in document.layers:
            document.layers.add(layer, color=colors[layer])

    modelspace = document.modelspace()
    revision = contract.metadata.revision
    nodes = {node.id: node for node in contract.nodes}
    segments = {segment.id: segment for segment in contract.segments}
    entity: DXFEntity

    for segment in contract.segments:
        entity = modelspace.add_lwpolyline(
            [nodes[segment.start_node_id].point, nodes[segment.end_node_id].point],
            dxfattribs={"layer": "P-PIPE", "const_width": segment.nominal_diameter},
        )
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=segment.id,
            feature_type="pipe_segment",
            revision=revision,
            extra={
                "start_node_id": segment.start_node_id,
                "end_node_id": segment.end_node_id,
                "service_code": segment.service_code,
            },
        )

    for node in contract.nodes:
        entity = modelspace.add_point(node.point, dxfattribs={"layer": "P-NODE"})
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=node.id,
            feature_type="piping_node",
            revision=revision,
            extra={"node_type": node.node_type},
        )

    for component in contract.components:
        segment = segments[component.segment_id]
        center = point_at_offset(contract, segment, component.offset)
        along, normal = _segment_basis(contract, segment.id)
        symbol_size = max(segment.nominal_diameter * 2.0, 120.0)
        if isinstance(component, Instrument):
            entity = modelspace.add_circle(
                center,
                symbol_size / 2.0,
                dxfattribs={"layer": "P-COMP"},
            )
        elif isinstance(component, Valve):
            points = [
                _local_point(center, along, normal, -symbol_size / 2, -symbol_size / 2),
                _local_point(center, along, normal, 0, 0),
                _local_point(center, along, normal, -symbol_size / 2, symbol_size / 2),
                _local_point(center, along, normal, symbol_size / 2, -symbol_size / 2),
                _local_point(center, along, normal, 0, 0),
                _local_point(center, along, normal, symbol_size / 2, symbol_size / 2),
            ]
            entity = modelspace.add_lwpolyline(points, dxfattribs={"layer": "P-COMP"})
        else:
            assert isinstance(component, Reducer)
            half_length = symbol_size / 2.0
            inlet = max(component.inlet_diameter, segment.nominal_diameter) / 2.0
            outlet = max(component.outlet_diameter, segment.nominal_diameter) / 2.0
            points = [
                _local_point(center, along, normal, -half_length, -inlet),
                _local_point(center, along, normal, half_length, -outlet),
                _local_point(center, along, normal, half_length, outlet),
                _local_point(center, along, normal, -half_length, inlet),
            ]
            entity = modelspace.add_lwpolyline(
                points,
                close=True,
                dxfattribs={"layer": "P-COMP"},
            )
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=component.id,
            feature_type=component.type,
            revision=revision,
            extra={"segment_id": component.segment_id},
        )

    for support in contract.supports:
        segment = segments[support.segment_id]
        center = point_at_offset(contract, segment, support.offset)
        radius = max(segment.nominal_diameter, 50.0) * 0.35
        entity = modelspace.add_circle(center, radius, dxfattribs={"layer": "P-SUPPORT"})
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=support.id,
            feature_type=support.type,
            revision=revision,
            extra={"segment_id": support.segment_id},
        )

    for zone in contract.equipment_zones:
        if isinstance(zone, CircularEquipmentZone):
            entity = modelspace.add_circle(
                zone.center,
                zone.diameter / 2.0,
                dxfattribs={"layer": "P-EQUIP"},
            )
        else:
            entity = modelspace.add_lwpolyline(
                _polygon_points(equipment_zone_geometry(zone)),
                close=True,
                dxfattribs={"layer": "P-EQUIP"},
            )
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=zone.id,
            feature_type=f"{zone.zone_kind}_{zone.type}",
            revision=revision,
        )

    all_geometry = piping_geometry_map(contract)
    min_x, min_y, max_x, max_y = unary_union(list(all_geometry.values())).bounds
    text_height = max(max(max_x - min_x, max_y - min_y) * 0.018, 80.0)
    if contract.drawing_profile.include_dimensions:
        for index, dimension in enumerate(contract.dimensions):
            entity = modelspace.add_text(
                f"{dimension.id}: {dimension.target:.3f} mm",
                height=text_height,
                dxfattribs={"layer": "P-DIMS"},
            )
            entity.set_placement((min_x, max_y + text_height * (index + 1.5)))
            _set_xdata(
                entity,
                contract_hash=contract_hash,
                feature_id=dimension.id,
                feature_type="dimension_note",
                revision=revision,
            )
    entity = modelspace.add_text(
        f"{contract.metadata.project_name} | Rev {revision} | DO NOT SCALE",
        height=text_height,
        dxfattribs={"layer": "P-META"},
    )
    entity.set_placement((min_x, min_y - text_height * 2))
    _set_xdata(
        entity,
        contract_hash=contract_hash,
        feature_id="piping-metadata",
        feature_type="metadata",
        revision=revision,
    )

    stream = io.StringIO(newline="\n")
    document.write(stream, fmt="asc")
    return stream.getvalue().encode("utf-8")


def render_piping_svg(contract: PipingPlanContract, contract_hash: str) -> str:
    geometries = piping_geometry_map(contract)
    min_x, min_y, max_x, max_y = unary_union(list(geometries.values())).bounds
    span = max(max_x - min_x, max_y - min_y, 1.0)
    padding = span * 0.08
    view_x, view_y = min_x - padding, min_y - padding
    view_width = max_x - min_x + padding * 2
    view_height = max_y - min_y + padding * 2
    flip_origin = min_y + max_y
    segments = {segment.id: segment for segment in contract.segments}
    nodes = {node.id: node for node in contract.nodes}

    elements: list[str] = []
    for zone in contract.equipment_zones:
        css_class = f"zone {zone.zone_kind}"
        if isinstance(zone, CircularEquipmentZone):
            elements.append(
                f'<circle class="{css_class}" data-feature-id="{escape(zone.id)}" '
                f'cx="{zone.center[0]:.6f}" cy="{zone.center[1]:.6f}" '
                f'r="{zone.diameter / 2.0:.6f}" />'
            )
        else:
            elements.append(
                f'<rect class="{css_class}" data-feature-id="{escape(zone.id)}" '
                f'x="{zone.origin[0]:.6f}" y="{zone.origin[1]:.6f}" '
                f'width="{zone.width:.6f}" height="{zone.height:.6f}" />'
            )
    for segment in contract.segments:
        start = nodes[segment.start_node_id].point
        end = nodes[segment.end_node_id].point
        elements.append(
            f'<line class="pipe" data-feature-id="{escape(segment.id)}" '
            f'x1="{start[0]:.6f}" y1="{start[1]:.6f}" '
            f'x2="{end[0]:.6f}" y2="{end[1]:.6f}" '
            f'stroke-width="{segment.nominal_diameter:.6f}" />'
        )
    for node in contract.nodes:
        elements.append(
            f'<circle class="node" data-feature-id="{escape(node.id)}" '
            f'cx="{node.point[0]:.6f}" cy="{node.point[1]:.6f}" r="55" />'
        )
    for component in contract.components:
        center = point_at_offset(contract, segments[component.segment_id], component.offset)
        elements.append(
            f'<circle class="component {escape(component.type)}" '
            f'data-feature-id="{escape(component.id)}" cx="{center[0]:.6f}" '
            f'cy="{center[1]:.6f}" r="90" />'
        )
    for support in contract.supports:
        center = point_at_offset(contract, segments[support.segment_id], support.offset)
        elements.append(
            f'<rect class="support" data-feature-id="{escape(support.id)}" '
            f'x="{center[0] - 35:.6f}" y="{center[1] - 35:.6f}" width="70" height="70" />'
        )

    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" role="img" '
            f'viewBox="{view_x:.6f} {view_y:.6f} {view_width:.6f} {view_height:.6f}">',
            f"<title>{escape(contract.metadata.project_name)} piping plan</title>",
            "<style>.pipe{stroke:#247c73;fill:none;stroke-linecap:round}"
            ".node{fill:#fff;stroke:#123d39;stroke-width:16}.component{fill:#e45b3f;stroke:#7d2414;stroke-width:14}"
            ".support{fill:#e9ae3a;stroke:#72500e;stroke-width:12}.zone{stroke-width:14}"
            ".equipment{fill:#aab5b0;fill-opacity:.4;stroke:#59645f}"
            ".keepout{fill:#ef7055;fill-opacity:.18;stroke:#bd3f2b;stroke-dasharray:35 20}</style>",
            f"<metadata>contract_hash={escape(contract_hash)}</metadata>",
            f'<g transform="translate(0 {flip_origin:.6f}) scale(1 -1)">',
            *elements,
            "</g>",
            "</svg>",
        ]
    )


def generate_piping_drawing(
    contract: PipingPlanContract,
    contract_hash: str,
) -> GeneratedPipingDrawing:
    dxf_bytes = generate_piping_dxf(contract, contract_hash)
    return GeneratedPipingDrawing(
        dxf_bytes=dxf_bytes,
        preview_svg=render_piping_svg(contract, contract_hash),
        contract_hash=contract_hash,
        artifact_hash=compute_artifact_hash(dxf_bytes),
    )


def render_piping_pdf(
    contract: PipingPlanContract,
    *,
    contract_hash: str,
    artifact_hash: str,
) -> bytes:
    output = io.BytesIO()
    page_width, page_height = landscape(A3)
    pdf = canvas.Canvas(output, pagesize=(page_width, page_height), invariant=1)
    pdf.setTitle(f"DatumGuard Piping - {contract.metadata.project_name}")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(15 * mm, page_height - 15 * mm, contract.metadata.project_name[:70])
    pdf.setFont("Helvetica-Bold", 18)
    pdf.setFillColorRGB(0.75, 0.08, 0.06)
    pdf.drawRightString(page_width - 15 * mm, page_height - 15 * mm, "DO NOT SCALE")

    geometries = piping_geometry_map(contract)
    min_x, min_y, max_x, max_y = unary_union(list(geometries.values())).bounds
    draw_left, draw_bottom = 15 * mm, 28 * mm
    draw_width, draw_height = page_width - 30 * mm, page_height - 55 * mm
    scale = min(draw_width / max(max_x - min_x, 1.0), draw_height / max(max_y - min_y, 1.0))

    def xy(point: tuple[float, float]) -> tuple[float, float]:
        return (
            draw_left + (point[0] - min_x) * scale,
            draw_bottom + (point[1] - min_y) * scale,
        )

    pdf.setStrokeColorRGB(0.12, 0.43, 0.39)
    pdf.setLineCap(1)
    nodes = {node.id: node for node in contract.nodes}
    for segment in contract.segments:
        start = xy(nodes[segment.start_node_id].point)
        end = xy(nodes[segment.end_node_id].point)
        pdf.setLineWidth(max(segment.nominal_diameter * scale, 1.2))
        pdf.line(start[0], start[1], end[0], end[1])
    pdf.setFillColorRGB(0.88, 0.28, 0.17)
    for component in contract.components:
        segment = next(item for item in contract.segments if item.id == component.segment_id)
        point = xy(point_at_offset(contract, segment, component.offset))
        pdf.circle(point[0], point[1], 1.6 * mm, fill=1, stroke=0)
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


def build_verified_piping_bundle(
    contract: PipingPlanContract,
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
        "design_kind": "piping_plan",
        "contract_hash": contract_hash,
        "artifact_hash": artifact_hash,
        "approval": "passed",
        "authority": "piping-plan.dxf",
        "pdf_notice": "DO NOT SCALE",
        "files": [
            "piping-plan.dxf",
            "preview.svg",
            "piping-plan-do-not-scale.pdf",
            "piping-plan-contract.json",
            "verification.json",
        ],
    }
    files = {
        "piping-plan.dxf": dxf_bytes,
        "preview.svg": preview_svg.encode("utf-8"),
        "piping-plan-do-not-scale.pdf": render_piping_pdf(
            contract,
            contract_hash=contract_hash,
            artifact_hash=artifact_hash,
        ),
        "piping-plan-contract.json": json.dumps(
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
    "GeneratedPipingDrawing",
    "PIPING_DXF_LAYERS",
    "PIPING_XDATA_APP_ID",
    "build_verified_piping_bundle",
    "generate_piping_drawing",
    "generate_piping_dxf",
    "render_piping_pdf",
    "render_piping_svg",
]

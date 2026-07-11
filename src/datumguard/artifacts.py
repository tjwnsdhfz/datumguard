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
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from shapely.geometry import Polygon

from .core import compute_artifact_hash, expand_features, feature_geometry, outline_geometry
from .models import CircularHole, DesignContract, Slot

DXF_LAYERS = ("OUTLINE", "CUT", "CENTER", "DIM", "CONSTRUCTION", "META")
XDATA_APP_ID = "DATUMGUARD"

# Reproducible engineering artifacts must not embed wall-clock time or random GUIDs.
options.write_fixed_meta_data_for_testing = True


@dataclass(frozen=True)
class GeneratedDrawing:
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
        XDATA_APP_ID,
        [
            (1000, f"contract_hash={contract_hash}"),
            (1000, f"feature_id={feature_id}"),
            (1000, f"feature_type={feature_type}"),
            (1000, f"revision={revision}"),
        ],
    )


def _polygon_points(geometry: Polygon) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in list(geometry.exterior.coords)[:-1]]


def _stabilize_header(document: Drawing) -> None:
    # ezdxf otherwise emits creation timestamps and random GUIDs, which breaks reproducibility.
    fixed_values: dict[str, Any] = {
        "$TDCREATE": 0.0,
        "$TDUPDATE": 0.0,
        "$TDUCREATE": 0.0,
        "$TDUUPDATE": 0.0,
        "$FINGERPRINTGUID": "{00000000-0000-0000-0000-000000000000}",
        "$VERSIONGUID": "{00000000-0000-0000-0000-000000000000}",
    }
    for name, value in fixed_values.items():
        try:
            document.header[name] = value
        except (DXFError, ValueError):
            continue


def generate_dxf(contract: DesignContract, contract_hash: str) -> bytes:
    document = new("R2013", setup=False)
    document.units = units.MM
    _stabilize_header(document)
    if XDATA_APP_ID not in document.appids:
        document.appids.add(XDATA_APP_ID)

    layer_colors = {
        "OUTLINE": 7,
        "CUT": 1,
        "CENTER": 4,
        "DIM": 3,
        "CONSTRUCTION": 8,
        "META": 6,
    }
    for layer in DXF_LAYERS:
        if layer not in document.layers:
            document.layers.add(layer, color=layer_colors[layer])

    modelspace = document.modelspace()
    outline = outline_geometry(contract.outline)
    outline_entity = modelspace.add_lwpolyline(
        _polygon_points(outline),
        close=True,
        dxfattribs={"layer": "OUTLINE"},
    )
    _set_xdata(
        outline_entity,
        contract_hash=contract_hash,
        feature_id=contract.outline.id,
        feature_type=contract.outline.type,
        revision=contract.metadata.revision,
    )

    for feature in expand_features(contract):
        entity: DXFEntity
        if isinstance(feature, CircularHole):
            entity = modelspace.add_circle(
                feature.center,
                radius=feature.diameter / 2.0,
                dxfattribs={"layer": "CUT"},
            )
        else:
            entity = modelspace.add_lwpolyline(
                _polygon_points(feature_geometry(feature)),
                close=True,
                dxfattribs={"layer": "CUT"},
            )
        _set_xdata(
            entity,
            contract_hash=contract_hash,
            feature_id=feature.id,
            feature_type=feature.type,
            revision=contract.metadata.revision,
        )

        if isinstance(feature, CircularHole | Slot):
            cx, cy = feature.center
        else:
            cx = feature.origin[0] + feature.width / 2.0
            cy = feature.origin[1] + feature.height / 2.0
        size = max(
            getattr(feature, "diameter", 0.0),
            getattr(feature, "width", 0.0),
            1.0,
        )
        for start, end in (
            ((cx - size * 0.6, cy), (cx + size * 0.6, cy)),
            ((cx, cy - size * 0.6), (cx, cy + size * 0.6)),
        ):
            center_entity = modelspace.add_line(
                start,
                end,
                dxfattribs={"layer": "CENTER"},
            )
            _set_xdata(
                center_entity,
                contract_hash=contract_hash,
                feature_id=feature.id,
                feature_type="center_mark",
                revision=contract.metadata.revision,
            )

    stream = io.StringIO(newline="\n")
    document.write(stream, fmt="asc")
    return stream.getvalue().encode("utf-8")


def render_svg(contract: DesignContract, contract_hash: str) -> str:
    outline = outline_geometry(contract.outline)
    min_x, min_y, max_x, max_y = outline.bounds
    padding = max(max_x - min_x, max_y - min_y) * 0.05 + 2.0
    view_x = min_x - padding
    view_y = min_y - padding
    view_width = max_x - min_x + padding * 2
    view_height = max_y - min_y + padding * 2
    flip_origin = min_y + max_y

    def polygon_element(geometry: Polygon, feature_id: str, css_class: str) -> str:
        points = " ".join(f"{x:.6f},{y:.6f}" for x, y in _polygon_points(geometry))
        return (
            f'<polygon id="{escape(feature_id)}" data-feature-id="{escape(feature_id)}" '
            f'class="{css_class}" points="{points}" />'
        )

    elements = [polygon_element(outline, contract.outline.id, "outline")]
    for feature in expand_features(contract):
        if isinstance(feature, CircularHole):
            elements.append(
                f'<circle id="{escape(feature.id)}" data-feature-id="{escape(feature.id)}" '
                f'class="feature" cx="{feature.center[0]:.6f}" cy="{feature.center[1]:.6f}" '
                f'r="{feature.diameter / 2.0:.6f}" />'
            )
        else:
            elements.append(polygon_element(feature_geometry(feature), feature.id, "feature"))

    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-labelledby="drawing-title" viewBox="{view_x:.6f} {view_y:.6f} '
            f'{view_width:.6f} {view_height:.6f}">',
            '<title id="drawing-title">DatumGuard preview — '
            f"{escape(contract.metadata.project_name)}</title>",
            "<style>.outline{fill:#dcece5;stroke:#153f32;stroke-width:.6;vector-effect:non-scaling-stroke}"
            ".feature{fill:#fff;stroke:#d04a35;stroke-width:.55;vector-effect:non-scaling-stroke}"
            ".datum{stroke:#2c6eaa;stroke-width:.4;vector-effect:non-scaling-stroke}</style>",
            f"<metadata>contract_hash={escape(contract_hash)}</metadata>",
            f'<g transform="translate(0 {flip_origin:.6f}) scale(1 -1)">',
            *elements,
            f'<line class="datum" x1="{min_x:.6f}" y1="{min_y:.6f}" '
            f'x2="{min_x + min(view_width * 0.1, 10):.6f}" y2="{min_y:.6f}" />',
            "</g>",
            "</svg>",
        ]
    )


def generate_drawing(contract: DesignContract, contract_hash: str) -> GeneratedDrawing:
    dxf_bytes = generate_dxf(contract, contract_hash)
    return GeneratedDrawing(
        dxf_bytes=dxf_bytes,
        preview_svg=render_svg(contract, contract_hash),
        contract_hash=contract_hash,
        artifact_hash=compute_artifact_hash(dxf_bytes),
    )


def render_pdf(
    contract: DesignContract,
    *,
    contract_hash: str,
    artifact_hash: str,
) -> bytes:
    output = io.BytesIO()
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(
        output,
        pagesize=(page_width, page_height),
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle(f"DatumGuard - {contract.metadata.project_name}")
    pdf.setAuthor("DatumGuard")

    pdf.setFillColorRGB(0.05, 0.12, 0.10)
    pdf.rect(0, page_height - 30 * mm, page_width, 30 * mm, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(16 * mm, page_height - 18 * mm, "DATUMGUARD VERIFIED DRAWING")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(page_width - 16 * mm, page_height - 17 * mm, "STATUS: PASSED")

    pdf.setFillColorRGB(0.75, 0.08, 0.06)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(page_width / 2, page_height - 48 * mm, "DO NOT SCALE")
    pdf.setFillColorRGB(0.12, 0.16, 0.14)
    pdf.setFont("Helvetica", 10)
    rows = [
        ("Project", contract.metadata.project_name),
        ("Revision", contract.metadata.revision),
        ("Units", "mm"),
        ("Datum", f"WCS XY / origin {contract.datum.origin}"),
        ("Contract", contract_hash),
        ("Artifact", artifact_hash),
        ("Authority", "DXF in this verified bundle"),
    ]
    y = page_height - 67 * mm
    for label, value in rows:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(20 * mm, y, f"{label}:")
        pdf.setFont("Helvetica", 8.5)
        safe_value = str(value).encode("latin-1", "replace").decode("latin-1")
        pdf.drawString(48 * mm, y, safe_value[:110])
        y -= 8 * mm

    pdf.setStrokeColorRGB(0.08, 0.25, 0.20)
    pdf.line(16 * mm, 18 * mm, page_width - 16 * mm, 18 * mm)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(
        16 * mm,
        11 * mm,
        "DatumGuard MVP does not certify structural safety, regulations, or industrial standards.",
    )
    pdf.save()
    return output.getvalue()


def build_verified_bundle(
    contract: DesignContract,
    *,
    contract_hash: str,
    artifact_hash: str,
    dxf_bytes: bytes,
    preview_svg: str,
    verification: dict[str, Any],
    repair_history: list[dict[str, Any]] | None = None,
) -> bytes:
    if verification.get("status") != "passed" or verification.get("violations"):
        raise PermissionError("DG_EXPORT_NOT_APPROVED")

    contract_data = contract.model_dump(mode="json")
    contract_data["contract_hash"] = contract_hash
    manifest = {
        "schema_version": "1.0.0",
        "contract_hash": contract_hash,
        "artifact_hash": artifact_hash,
        "approval": "passed",
        "authority": "drawing.dxf",
        "pdf_notice": "DO NOT SCALE",
        "files": [
            "drawing.dxf",
            "preview.svg",
            "drawing-do-not-scale.pdf",
            "design-contract.json",
            "verification.json",
            "repair-history.json",
        ],
    }
    files: dict[str, bytes] = {
        "drawing.dxf": dxf_bytes,
        "preview.svg": preview_svg.encode("utf-8"),
        "drawing-do-not-scale.pdf": render_pdf(
            contract,
            contract_hash=contract_hash,
            artifact_hash=artifact_hash,
        ),
        "design-contract.json": json.dumps(
            contract_data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
        "verification.json": json.dumps(
            verification,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
        "repair-history.json": json.dumps(
            repair_history or [],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
        "manifest.json": json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for filename in sorted(files):
            info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, files[filename])
    return archive.getvalue()

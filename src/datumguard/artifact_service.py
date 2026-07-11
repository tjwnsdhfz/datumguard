from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import math
import os
import re
import sys
import tempfile
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, cast

import ezdxf
from ezdxf import bbox, recover
from ezdxf.addons.drawing import layout
from ezdxf.addons.drawing.frontend import Frontend
from ezdxf.addons.drawing.properties import RenderContext
from ezdxf.addons.drawing.svg import SVGBackend
from ezdxf.filemanagement import readfile
from ezdxf.lldxf.const import DXFError

from .artifact_models import (
    ArtifactAuditResponse,
    ArtifactComparisonResponse,
    ArtifactFormat,
    ArtifactMetric,
    AuditIssue,
    PreviewMesh,
)
from .cad_subprocess import CadWorkerFailure, run_cad_worker, run_parser_worker
from .models import ErrorInfo, Evidence, Violation
from .operations import ARTIFACT_SINGLE_FLIGHT


def _configured_artifact_limit() -> int:
    raw = os.getenv("DATUMGUARD_MAX_ARTIFACT_BYTES", "").strip()
    try:
        configured = int(raw) if raw else 20 * 1024 * 1024
    except ValueError:
        configured = 20 * 1024 * 1024
    return min(max(configured, 1024), 64 * 1024 * 1024)


MAX_ARTIFACT_BYTES = _configured_artifact_limit()
MAX_PREVIEW_TRIANGLES = 3500
MAX_ISSUES = 100

_FORMAT_MEDIA_TYPES: dict[ArtifactFormat, str] = {
    "dxf": "image/vnd.dxf",
    "step": "model/step",
    "ifc": "application/x-step",
}


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _safe_filename(filename: str) -> str:
    return (Path(filename).name or "artifact")[0:255]


def _detect_format(filename: str, data: bytes) -> ArtifactFormat | None:
    suffix = Path(filename).suffix.lower()
    if suffix == ".dxf" or data.startswith(b"AutoCAD Binary DXF"):
        return "dxf"
    if suffix == ".ifc":
        return "ifc"
    if suffix in {".step", ".stp", ".p21"} or data.lstrip().startswith(b"ISO-10303-21"):
        return "step"
    if b"FILE_SCHEMA" in data[:8192] and b"IFC" in data[:8192].upper():
        return "ifc"
    return None


def _error_info(code: str, message: str, details: dict[str, Any]) -> ErrorInfo:
    return ErrorInfo(
        code=code,
        message=message,
        details=details,
        correlation_id=str(uuid.uuid4()),
    )


def _failed_audit(
    filename: str,
    data: bytes,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    artifact_format: ArtifactFormat | None = None,
) -> ArtifactAuditResponse:
    safe_name = _safe_filename(filename)
    detail_payload = details or {}
    issue = AuditIssue(code=code, severity="error", message=message, details=detail_payload)
    return ArtifactAuditResponse(
        status="failed_verification",
        artifact_hash=_sha256(data) if data else None,
        format=artifact_format,
        filename=safe_name,
        media_type=(
            _FORMAT_MEDIA_TYPES[artifact_format]
            if artifact_format is not None
            else "application/octet-stream"
        ),
        byte_size=len(data),
        issues=[issue],
        violations=[Violation(code=code, message=message, details=detail_payload)],
        error=_error_info(code, message, detail_payload),
    )


def _issue_to_violation(issue: AuditIssue) -> Violation:
    return Violation(
        code=issue.code,
        message=issue.message,
        entity_ids=issue.entity_ids,
        repairable=False,
        details=issue.details,
    )


def _status_from_issues(issues: list[AuditIssue]) -> str:
    if any(issue.severity == "error" for issue in issues):
        return "failed_verification"
    if any(issue.severity == "warning" for issue in issues):
        return "needs_confirmation"
    return "audited"


def _auditor_issues(auditor: Any) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for item in list(getattr(auditor, "errors", []))[:MAX_ISSUES]:
        issues.append(
            AuditIssue(
                code=f"DG_DXF_AUDIT_{getattr(item, 'code', 'ERROR')}",
                severity="error",
                message=str(item),
                details={"audit_kind": "unrecoverable_error"},
            )
        )
    remaining = max(0, MAX_ISSUES - len(issues))
    for item in list(getattr(auditor, "fixes", []))[:remaining]:
        issues.append(
            AuditIssue(
                code=f"DG_DXF_RECOVERED_{getattr(item, 'code', 'FIX')}",
                severity="warning",
                message=str(item),
                details={"audit_kind": "automatic_recovery", "original_file_modified": False},
            )
        )
    return issues


def _read_dxf(data: bytes) -> tuple[Any, Any]:
    if data.startswith(b"AutoCAD Binary DXF"):
        with tempfile.NamedTemporaryFile(suffix=".dxf") as temporary:
            temporary.write(data)
            temporary.flush()
            document = readfile(temporary.name)
            return document, document.audit()
    return recover.read(io.BytesIO(data), errors="strict")


def _datumguard_xdata(document: Any) -> tuple[int, str | None]:
    count = 0
    design_kind: str | None = None
    for entity in document.modelspace():
        try:
            tags = entity.get_xdata("DATUMGUARD")
        except (DXFError, ValueError):
            continue
        count += 1
        for tag in tags:
            value = str(getattr(tag, "value", ""))
            if value.startswith("design_kind="):
                design_kind = value.split("=", 1)[1]
    return count, design_kind


def _render_dxf_svg(document: Any) -> str | None:
    try:
        backend = SVGBackend()
        Frontend(RenderContext(document), backend).draw_layout(document.modelspace(), finalize=True)
        svg = backend.get_string(layout.Page(0, 0), xml_declaration=False)
        svg = re.sub(r"<image\b[^>]*(?:/>|>.*?</image>)", "", svg, flags=re.DOTALL)
        return svg if len(svg.encode("utf-8")) <= 2_000_000 else None
    except (DXFError, ValueError, TypeError, AttributeError):
        return None


def _round_value(value: Any) -> Any:
    if isinstance(value, bool | int | str) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return round(value, 6)
    if hasattr(value, "x") and hasattr(value, "y"):
        coordinates = [float(value.x), float(value.y)]
        if hasattr(value, "z"):
            coordinates.append(float(value.z))
        return [_round_value(item) for item in coordinates]
    if isinstance(value, dict):
        return {str(key): _round_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_round_value(item) for item in value]
    return str(value)


def _entity_payload(entity: Any) -> dict[str, Any]:
    attributes = {
        key: _round_value(value)
        for key, value in entity.dxfattribs().items()
        if key not in {"handle", "owner", "paperspace"}
    }
    entity_type = entity.dxftype()
    if entity_type == "LWPOLYLINE":
        attributes["points"] = _round_value(list(entity.get_points("xyseb")))
    elif entity_type == "POLYLINE":
        attributes["points"] = _round_value([vertex.dxf.location for vertex in entity.vertices])
    elif entity_type == "SPLINE":
        attributes["control_points"] = _round_value(list(entity.control_points))
        attributes["fit_points"] = _round_value(list(entity.fit_points))
    elif entity_type in {"TEXT", "MTEXT"}:
        try:
            attributes["plain_text"] = entity.plain_text()
        except (AttributeError, TypeError):
            pass
    return {"type": entity_type, "attributes": attributes}


def _dxf_fingerprints(data: bytes) -> tuple[Counter[str], dict[str, str]]:
    document, _auditor = _read_dxf(data)
    fingerprints: Counter[str] = Counter()
    handles: dict[str, str] = {}
    for entity in document.modelspace():
        payload = _entity_payload(entity)
        serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        fingerprints[fingerprint] += 1
        handle = str(getattr(entity.dxf, "handle", "") or "")
        if handle:
            handles[handle] = fingerprint
    return fingerprints, handles


def _audit_dxf(filename: str, data: bytes, artifact_hash: str) -> ArtifactAuditResponse:
    try:
        document, auditor = _read_dxf(data)
    except (OSError, UnicodeError, DXFError, ValueError) as exc:
        return _failed_audit(
            filename,
            data,
            code="DG_ARTIFACT_DXF_READ_FAILED",
            message="DXF 파일을 구조적으로 읽을 수 없습니다.",
            details={"exception": type(exc).__name__},
            artifact_format="dxf",
        )

    entities = list(document.modelspace())
    entity_counts = Counter(entity.dxftype() for entity in entities)
    layer_counts = Counter(str(entity.dxf.layer) for entity in entities)
    issues = _auditor_issues(auditor)
    if not entities:
        issues.append(
            AuditIssue(
                code="DG_ARTIFACT_DXF_EMPTY",
                severity="error",
                message="DXF modelspace에 검토할 entity가 없습니다.",
            )
        )

    unit_code = int(document.units)
    unit_name = "unitless" if unit_code == 0 else ezdxf.units.unit_name(unit_code)
    if unit_code == 0:
        issues.append(
            AuditIssue(
                code="DG_ARTIFACT_UNIT_CONFIRMATION_REQUIRED",
                severity="warning",
                message="DXF의 $INSUNITS가 unitless입니다. 수치 판정 전에 단위를 확인해야 합니다.",
            )
        )

    extents_payload: dict[str, Any] | None = None
    try:
        box = bbox.extents(entities, fast=True)
        if box.has_data:
            extents_payload = {
                "minimum": [round(box.extmin.x, 6), round(box.extmin.y, 6), round(box.extmin.z, 6)],
                "maximum": [round(box.extmax.x, 6), round(box.extmax.y, 6), round(box.extmax.z, 6)],
                "size": [
                    round(box.size.x, 6),
                    round(box.size.y, 6),
                    round(box.size.z, 6),
                ],
            }
    except (DXFError, ValueError, TypeError):
        issues.append(
            AuditIssue(
                code="DG_ARTIFACT_EXTENTS_UNAVAILABLE",
                severity="warning",
                message="일부 entity에서 안전한 전체 extents를 계산하지 못했습니다.",
            )
        )

    xdata_count, design_kind = _datumguard_xdata(document)
    preview_svg = _render_dxf_svg(document)
    if preview_svg is None:
        issues.append(
            AuditIssue(
                code="DG_ARTIFACT_PREVIEW_PARTIAL",
                severity="info",
                message="SVG preview를 생성하지 못했지만 구조 감사 결과는 유지됩니다.",
            )
        )

    summary: dict[str, Any] = {
        "dxf_version": document.dxfversion,
        "units": unit_name,
        "unit_code": unit_code,
        "entity_count": len(entities),
        "entity_types": dict(sorted(entity_counts.items())),
        "layer_count": len(layer_counts),
        "layers": dict(sorted(layer_counts.items())),
        "extents": extents_payload,
        "datumguard_xdata_entities": xdata_count,
        "detected_design_kind": design_kind,
        "audit_error_count": len(getattr(auditor, "errors", [])),
        "audit_fix_count": len(getattr(auditor, "fixes", [])),
        "binary_dxf": data.startswith(b"AutoCAD Binary DXF"),
    }
    metrics = [
        ArtifactMetric(metric_id="entity-count", label="Modelspace entities", value=len(entities)),
        ArtifactMetric(metric_id="layer-count", label="Layers used", value=len(layer_counts)),
        ArtifactMetric(
            metric_id="xdata-count", label="Traceable XDATA entities", value=xdata_count
        ),
    ]
    if extents_payload:
        size = extents_payload["size"]
        metrics.extend(
            [
                ArtifactMetric(
                    metric_id="extent-x", label="Extent X", value=size[0], unit=unit_name
                ),
                ArtifactMetric(
                    metric_id="extent-y", label="Extent Y", value=size[1], unit=unit_name
                ),
                ArtifactMetric(
                    metric_id="extent-z", label="Extent Z", value=size[2], unit=unit_name
                ),
            ]
        )
    status = _status_from_issues(issues)
    return ArtifactAuditResponse(
        status=status,  # type: ignore[arg-type]
        artifact_hash=artifact_hash,
        measurements=metrics,
        violations=[_issue_to_violation(issue) for issue in issues if issue.severity == "error"],
        evidence=[
            Evidence(
                type="artifact_audit",
                source="ezdxf_recover_and_auditor",
                details={"original_preserved": True, "normalized_for_preview_only": True},
            )
        ],
        format="dxf",
        filename=filename,
        media_type=_FORMAT_MEDIA_TYPES["dxf"],
        byte_size=len(data),
        summary=summary,
        issues=issues,
        preview_svg=preview_svg,
    )


def _step_unit(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text.upper())
    if "SI_UNIT(.MILLI.,.METRE.)" in compact:
        return "mm"
    if "SI_UNIT(.CENTI.,.METRE.)" in compact:
        return "cm"
    if "SI_UNIT($,.METRE.)" in compact:
        return "m"
    if "CONVERSION_BASED_UNIT('INCH'" in compact or 'CONVERSION_BASED_UNIT("INCH"' in compact:
        return "inch"
    return None


def _audit_step(filename: str, data: bytes, artifact_hash: str) -> ArtifactAuditResponse:
    text = data.decode("ascii", errors="ignore")
    schema_match = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*['\"]([^'\"]+)", text, re.IGNORECASE)
    schema = schema_match.group(1) if schema_match else "unknown"
    original_unit = _step_unit(text)
    issues: list[AuditIssue] = []
    if original_unit is None:
        issues.append(
            AuditIssue(
                code="DG_ARTIFACT_UNIT_CONFIRMATION_REQUIRED",
                severity="warning",
                message="STEP header에서 길이 단위를 확정하지 못했습니다.",
            )
        )

    try:
        worker_result = run_cad_worker(
            {
                "operation": "audit_step",
                "content_base64": base64.b64encode(data).decode("ascii"),
            }
        )
        kernel_summary = dict(worker_result["summary"])
        valid = bool(kernel_summary["valid_shape"])
        solid_count = int(kernel_summary["solid_count"])
        face_count = int(kernel_summary["face_count"])
        edge_count = int(kernel_summary["edge_count"])
        vertex_count = int(kernel_summary["vertex_count"])
        bounds = dict(kernel_summary["bounding_box_mm"])
        volume = float(kernel_summary["volume_mm3"])
        area = float(kernel_summary["surface_area_mm2"])
        cylinders = list(kernel_summary["cylindrical_surfaces"])
        mesh_payload = worker_result.get("preview_mesh")
        mesh = PreviewMesh.model_validate(mesh_payload) if mesh_payload else None
    except (CadWorkerFailure, KeyError, ValueError, TypeError) as exc:
        return _failed_audit(
            filename,
            data,
            code="DG_ARTIFACT_STEP_READ_FAILED",
            message="OpenCascade가 STEP geometry를 읽지 못했습니다.",
            details={
                "exception": type(exc).__name__,
                "isolated_worker": True,
                "failure": (
                    str(exc.details.get("failure", "worker_failure"))
                    if isinstance(exc, CadWorkerFailure)
                    else "invalid_result"
                ),
            },
            artifact_format="step",
        )

    if not valid:
        issues.append(
            AuditIssue(
                code="DG_STEP_SOLID_INVALID",
                severity="error",
                message="OpenCascade BRepCheck에서 유효하지 않은 shape로 판정했습니다.",
            )
        )
    if solid_count == 0:
        issues.append(
            AuditIssue(
                code="DG_STEP_NO_SOLID",
                severity="warning",
                message="STEP에 닫힌 solid가 없습니다. Surface model 여부를 확인해야 합니다.",
            )
        )

    if mesh is None:
        issues.append(
            AuditIssue(
                code="DG_ARTIFACT_PREVIEW_PARTIAL",
                severity="info",
                message="STEP tessellation preview를 생성하지 못했습니다.",
            )
        )
    summary = {
        "step_schema": schema,
        "original_length_unit": original_unit,
        "normalized_kernel_unit": "mm",
        "valid_shape": valid,
        "solid_count": solid_count,
        "face_count": face_count,
        "edge_count": edge_count,
        "vertex_count": vertex_count,
        "bounding_box_mm": bounds,
        "center_of_mass_mm": kernel_summary["center_of_mass_mm"],
        "volume_mm3": round(volume, 6),
        "surface_area_mm2": round(area, 6),
        "cylindrical_surfaces": cylinders,
    }
    metrics = [
        ArtifactMetric(metric_id="solid-count", label="Solids", value=solid_count),
        ArtifactMetric(metric_id="face-count", label="Faces", value=face_count),
        ArtifactMetric(metric_id="volume", label="Volume", value=round(volume, 6), unit="mm³"),
        ArtifactMetric(
            metric_id="surface-area", label="Surface area", value=round(area, 6), unit="mm²"
        ),
        ArtifactMetric(
            metric_id="bbox-x", label="Bounding box X", value=bounds["size"][0], unit="mm"
        ),
        ArtifactMetric(
            metric_id="bbox-y", label="Bounding box Y", value=bounds["size"][1], unit="mm"
        ),
        ArtifactMetric(
            metric_id="bbox-z", label="Bounding box Z", value=bounds["size"][2], unit="mm"
        ),
        ArtifactMetric(
            metric_id="cylinder-count", label="Cylindrical surfaces", value=len(cylinders)
        ),
    ]
    status = _status_from_issues(issues)
    return ArtifactAuditResponse(
        status=status,  # type: ignore[arg-type]
        artifact_hash=artifact_hash,
        measurements=metrics,
        violations=[_issue_to_violation(issue) for issue in issues if issue.severity == "error"],
        evidence=[
            Evidence(
                type="artifact_audit",
                source="isolated_cadquery_opencascade_step_reimport",
                details={
                    "normalized_unit": "mm",
                    "original_preserved": True,
                    "isolated_process": True,
                },
            )
        ],
        format="step",
        filename=filename,
        media_type=_FORMAT_MEDIA_TYPES["step"],
        byte_size=len(data),
        summary=summary,
        issues=issues,
        preview_mesh=mesh,
    )


def _ifc_entity_signature(entity: Any) -> str:
    fields: dict[str, Any] = {"ifc_class": entity.is_a()}
    for key in ("Name", "Description", "ObjectType", "Tag", "PredefinedType"):
        if hasattr(entity, key):
            fields[key] = _round_value(getattr(entity, key, None))
    relationships = getattr(entity, "ContainedInStructure", None) or []
    if relationships:
        container = relationships[0].RelatingStructure
        fields["container"] = getattr(container, "GlobalId", None)
    serialized = json.dumps(fields, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _ifc_index(data: bytes) -> tuple[Any, dict[str, str]]:
    ifcopenshell: Any = importlib.import_module("ifcopenshell")
    model = ifcopenshell.file.from_string(data.decode("utf-8-sig", errors="strict"))
    index: dict[str, str] = {}
    for entity in model.by_type("IfcRoot"):
        guid = str(getattr(entity, "GlobalId", "") or "")
        if guid:
            index[guid] = _ifc_entity_signature(entity)
    return model, index


def _audit_ifc(filename: str, data: bytes, artifact_hash: str) -> ArtifactAuditResponse:
    try:
        model, root_index = _ifc_index(data)
        validate_module: Any = importlib.import_module("ifcopenshell.validate")
        unit_module: Any = importlib.import_module("ifcopenshell.util.unit")
        logger = validate_module.json_logger()
        validate_module.validate(model, logger, express_rules=False)
    except (ImportError, UnicodeError, RuntimeError, ValueError, TypeError, AttributeError) as exc:
        return _failed_audit(
            filename,
            data,
            code="DG_ARTIFACT_IFC_READ_FAILED",
            message="IfcOpenShell이 IFC 모델을 읽지 못했습니다.",
            details={"exception": type(exc).__name__},
            artifact_format="ifc",
        )

    issues: list[AuditIssue] = []
    validation_statements = list(getattr(logger, "statements", []))
    for statement in validation_statements[:MAX_ISSUES]:
        message = str(statement.get("message", "IFC schema validation error"))
        issues.append(
            AuditIssue(
                code="DG_IFC_SCHEMA_VALIDATION",
                severity="error",
                message=message,
                details={"instance": str(statement.get("instance", ""))},
            )
        )

    roots = list(model.by_type("IfcRoot"))
    guid_counts = Counter(str(getattr(entity, "GlobalId", "") or "") for entity in roots)
    duplicate_guids = sorted(guid for guid, count in guid_counts.items() if guid and count > 1)
    if duplicate_guids:
        issues.append(
            AuditIssue(
                code="DG_IFC_DUPLICATE_GLOBAL_ID",
                severity="error",
                message="IFC 모델에 중복 GlobalId가 있습니다.",
                entity_ids=duplicate_guids[:25],
                details={"duplicate_count": len(duplicate_guids)},
            )
        )

    projects = list(model.by_type("IfcProject"))
    if len(projects) != 1:
        issues.append(
            AuditIssue(
                code="DG_IFC_PROJECT_CARDINALITY",
                severity="error" if not projects else "warning",
                message="IFC 파일은 하나의 IfcProject를 가져야 합니다.",
                details={"project_count": len(projects)},
            )
        )

    try:
        project_unit = unit_module.get_project_unit(model, "LENGTHUNIT")
        unit_scale = float(unit_module.calculate_unit_scale(model, "LENGTHUNIT"))
        unit_name = str(getattr(project_unit, "Name", "") or "")
        unit_prefix = str(getattr(project_unit, "Prefix", "") or "")
        length_unit = f"{unit_prefix}{unit_name}".lower() if project_unit else None
    except (RuntimeError, ValueError, TypeError, AttributeError):
        length_unit = None
        unit_scale = 1.0
    if not length_unit:
        issues.append(
            AuditIssue(
                code="DG_ARTIFACT_UNIT_CONFIRMATION_REQUIRED",
                severity="warning",
                message="IFC project length unit를 확정하지 못했습니다.",
            )
        )

    products = list(model.by_type("IfcProduct"))
    type_counts = Counter(str(entity.is_a()) for entity in products)
    spatial = [
        {
            "ifc_class": entity.is_a(),
            "global_id": str(getattr(entity, "GlobalId", "") or ""),
            "name": str(getattr(entity, "Name", "") or ""),
        }
        for entity in model.by_type("IfcSpatialElement")
    ]
    elements = list(model.by_type("IfcElement"))
    orphan_elements = [
        str(getattr(entity, "GlobalId", "") or "")
        for entity in elements
        if entity.is_a() not in {"IfcOpeningElement", "IfcVoidingFeature"}
        and not (getattr(entity, "ContainedInStructure", None) or [])
    ]
    if orphan_elements:
        issues.append(
            AuditIssue(
                code="DG_IFC_ORPHAN_ELEMENT",
                severity="warning",
                message="공간 구조에 배치되지 않은 IfcElement가 있습니다.",
                entity_ids=orphan_elements[:25],
                details={"orphan_count": len(orphan_elements)},
            )
        )

    summary = {
        "ifc_schema": model.schema,
        "length_unit": length_unit,
        "length_scale_to_m": unit_scale,
        "root_count": len(roots),
        "global_id_count": len(root_index),
        "product_count": len(products),
        "element_count": len(elements),
        "type_counts": dict(sorted(type_counts.items())),
        "spatial_structure": spatial[:100],
        "property_set_count": len(model.by_type("IfcPropertySet")),
        "relationship_count": len(model.by_type("IfcRelationship")),
        "orphan_element_count": len(orphan_elements),
        "validation_statement_count": len(validation_statements),
        "has_map_conversion": bool(model.by_type("IfcCoordinateOperation")),
    }
    metrics = [
        ArtifactMetric(metric_id="ifc-products", label="IFC products", value=len(products)),
        ArtifactMetric(metric_id="ifc-elements", label="IFC elements", value=len(elements)),
        ArtifactMetric(metric_id="ifc-spatial", label="Spatial containers", value=len(spatial)),
        ArtifactMetric(
            metric_id="ifc-property-sets",
            label="Property sets",
            value=len(model.by_type("IfcPropertySet")),
        ),
        ArtifactMetric(
            metric_id="ifc-orphans", label="Orphan elements", value=len(orphan_elements)
        ),
    ]
    status = _status_from_issues(issues)
    return ArtifactAuditResponse(
        status=status,  # type: ignore[arg-type]
        artifact_hash=artifact_hash,
        measurements=metrics,
        violations=[_issue_to_violation(issue) for issue in issues if issue.severity == "error"],
        evidence=[
            Evidence(
                type="artifact_audit",
                source="ifcopenshell_schema_and_spatial_audit",
                details={"original_preserved": True, "geometry_code_compliance": False},
            )
        ],
        format="ifc",
        filename=filename,
        media_type=_FORMAT_MEDIA_TYPES["ifc"],
        byte_size=len(data),
        summary=summary,
        issues=issues,
    )


def _audit_in_parser_worker(
    filename: str,
    data: bytes,
    artifact_hash: str,
    artifact_format: ArtifactFormat,
) -> ArtifactAuditResponse:
    try:
        result = run_parser_worker(
            {
                "operation": f"audit_{artifact_format}",
                "filename": filename,
                "content_base64": base64.b64encode(data).decode("ascii"),
                "artifact_hash": artifact_hash,
            }
        )
        return ArtifactAuditResponse.model_validate(result)
    except (CadWorkerFailure, ValueError, TypeError, KeyError) as exc:
        return _failed_audit(
            filename,
            data,
            code=f"DG_ARTIFACT_{artifact_format.upper()}_READ_FAILED",
            message="격리된 CAD parser가 파일을 안전하게 처리하지 못했습니다.",
            details={
                "isolated_worker": True,
                "failure": (
                    str(exc.details.get("failure", "worker_failure"))
                    if isinstance(exc, CadWorkerFailure)
                    else "invalid_result"
                ),
            },
            artifact_format=artifact_format,
        )


def _audit_artifact_uncached(filename: str, data: bytes) -> ArtifactAuditResponse:
    safe_name = _safe_filename(filename)
    if not data:
        return _failed_audit(
            safe_name,
            data,
            code="DG_ARTIFACT_EMPTY",
            message="업로드한 CAD 파일이 비어 있습니다.",
        )
    if len(data) > MAX_ARTIFACT_BYTES:
        return _failed_audit(
            safe_name,
            data,
            code="DG_ARTIFACT_TOO_LARGE",
            message="CAD 파일이 20MB 제한을 초과했습니다.",
            details={"max_bytes": MAX_ARTIFACT_BYTES, "actual_bytes": len(data)},
        )
    artifact_format = _detect_format(safe_name, data)
    if artifact_format is None:
        return _failed_audit(
            safe_name,
            data,
            code="DG_ARTIFACT_FORMAT_UNSUPPORTED",
            message="지원 형식은 ASCII/Binary DXF, STEP/STP, IFC입니다.",
        )
    artifact_hash = _sha256(data)
    if artifact_format == "dxf":
        return _audit_in_parser_worker(safe_name, data, artifact_hash, artifact_format)
    if artifact_format == "step":
        return _audit_step(safe_name, data, artifact_hash)
    return _audit_in_parser_worker(safe_name, data, artifact_hash, artifact_format)


def audit_artifact(filename: str, data: bytes) -> ArtifactAuditResponse:
    suffix = Path(filename).suffix.lower()[0:16]
    flight_key = f"audit:{suffix}:{_sha256(data)}"
    return cast(
        ArtifactAuditResponse,
        ARTIFACT_SINGLE_FLIGHT.run(
            flight_key,
            lambda: _audit_artifact_uncached(filename, data),
        ),
    )


def _metric_deltas(
    baseline: ArtifactAuditResponse,
    candidate: ArtifactAuditResponse,
) -> dict[str, Any]:
    baseline_metrics = {item.metric_id: item for item in baseline.measurements}
    candidate_metrics = {item.metric_id: item for item in candidate.measurements}
    deltas: dict[str, Any] = {}
    for metric_id in sorted(set(baseline_metrics) | set(candidate_metrics)):
        before = baseline_metrics.get(metric_id)
        after = candidate_metrics.get(metric_id)
        before_value = before.value if before else None
        after_value = after.value if after else None
        delta: float | None = None
        if isinstance(before_value, int | float) and isinstance(after_value, int | float):
            delta = round(float(after_value) - float(before_value), 6)
        deltas[metric_id] = {
            "before": before_value,
            "after": after_value,
            "delta": delta,
            "unit": (after.unit if after else before.unit if before else None),
        }
    return deltas


def _isolated_dxf_fingerprints(data: bytes) -> tuple[Counter[str], dict[str, str]]:
    result = run_parser_worker(
        {
            "operation": "dxf_fingerprints",
            "content_base64": base64.b64encode(data).decode("ascii"),
        }
    )
    fingerprints = Counter(
        {str(key): int(value) for key, value in dict(result["fingerprints"]).items()}
    )
    handles = {str(key): str(value) for key, value in dict(result["handles"]).items()}
    return fingerprints, handles


def _isolated_ifc_index(data: bytes) -> dict[str, str]:
    result = run_parser_worker(
        {
            "operation": "ifc_index",
            "content_base64": base64.b64encode(data).decode("ascii"),
        }
    )
    return {str(key): str(value) for key, value in dict(result["index"]).items()}


def _compare_artifacts_uncached(
    baseline_filename: str,
    baseline_data: bytes,
    candidate_filename: str,
    candidate_data: bytes,
) -> ArtifactComparisonResponse:
    baseline = audit_artifact(baseline_filename, baseline_data)
    candidate = audit_artifact(candidate_filename, candidate_data)
    baseline_hash = baseline.artifact_hash or "sha256:unavailable"
    candidate_hash = candidate.artifact_hash or "sha256:unavailable"
    same_artifact = baseline_hash == candidate_hash and baseline_hash != "sha256:unavailable"
    issues: list[AuditIssue] = []
    comparison: dict[str, Any] = {"metric_deltas": _metric_deltas(baseline, candidate)}

    if baseline.format is None or candidate.format is None or baseline.format != candidate.format:
        issues.append(
            AuditIssue(
                code="DG_ARTIFACT_FORMAT_MISMATCH",
                severity="error",
                message="같은 CAD 형식끼리만 revision을 비교할 수 있습니다.",
                details={"baseline": baseline.format, "candidate": candidate.format},
            )
        )
    elif baseline.format == "dxf":
        try:
            baseline_fingerprints, baseline_handles = _isolated_dxf_fingerprints(baseline_data)
            candidate_fingerprints, candidate_handles = _isolated_dxf_fingerprints(candidate_data)
            added = candidate_fingerprints - baseline_fingerprints
            removed = baseline_fingerprints - candidate_fingerprints
            common_handles = set(baseline_handles) & set(candidate_handles)
            changed_handles = sorted(
                handle
                for handle in common_handles
                if baseline_handles[handle] != candidate_handles[handle]
            )
            comparison["geometry"] = {
                "added_entity_count": sum(added.values()),
                "removed_entity_count": sum(removed.values()),
                "changed_handle_count": len(changed_handles),
                "changed_handles": changed_handles[:50],
                "same_geometry_multiset": not added and not removed,
            }
        except (
            CadWorkerFailure,
            OSError,
            UnicodeError,
            DXFError,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
        ) as exc:
            issues.append(
                AuditIssue(
                    code="DG_ARTIFACT_COMPARE_FAILED",
                    severity="error",
                    message="DXF geometry fingerprint 비교를 완료하지 못했습니다.",
                    details={"exception": type(exc).__name__},
                )
            )
    elif baseline.format == "ifc":
        try:
            baseline_index = _isolated_ifc_index(baseline_data)
            candidate_index = _isolated_ifc_index(candidate_data)
            baseline_ids = set(baseline_index)
            candidate_ids = set(candidate_index)
            common_ids = baseline_ids & candidate_ids
            comparison["ifc_revision"] = {
                "added_global_ids": sorted(candidate_ids - baseline_ids)[:100],
                "deleted_global_ids": sorted(baseline_ids - candidate_ids)[:100],
                "changed_global_ids": sorted(
                    guid for guid in common_ids if baseline_index[guid] != candidate_index[guid]
                )[:100],
            }
        except (
            CadWorkerFailure,
            ImportError,
            UnicodeError,
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            issues.append(
                AuditIssue(
                    code="DG_ARTIFACT_COMPARE_FAILED",
                    severity="error",
                    message="IFC GlobalId revision 비교를 완료하지 못했습니다.",
                    details={"exception": type(exc).__name__},
                )
            )

    if (
        issues
        or baseline.status == "failed_verification"
        or candidate.status == "failed_verification"
    ):
        status = "failed_verification"
    elif baseline.status == "needs_confirmation" or candidate.status == "needs_confirmation":
        status = "needs_confirmation"
    else:
        status = "audited"
    violations = [
        *baseline.violations,
        *candidate.violations,
        *(_issue_to_violation(issue) for issue in issues if issue.severity == "error"),
    ]
    return ArtifactComparisonResponse(
        status=status,  # type: ignore[arg-type]
        artifact_hash=candidate.artifact_hash,
        measurements=candidate.measurements,
        violations=violations,
        evidence=[
            Evidence(
                type="artifact_revision_comparison",
                source="format_specific_deterministic_comparator",
                details={"originals_preserved": True},
            )
        ],
        format=candidate.format if baseline.format == candidate.format else None,
        baseline_hash=baseline_hash,
        candidate_hash=candidate_hash,
        same_artifact=same_artifact,
        comparison=comparison,
        baseline=baseline,
        candidate=candidate,
        error=(
            _error_info(
                issues[0].code,
                issues[0].message,
                issues[0].details,
            )
            if issues
            else None
        ),
    )


def compare_artifacts(
    baseline_filename: str,
    baseline_data: bytes,
    candidate_filename: str,
    candidate_data: bytes,
) -> ArtifactComparisonResponse:
    baseline_hash = _sha256(baseline_data)
    candidate_hash = _sha256(candidate_data)
    format_key = (
        f"{Path(baseline_filename).suffix.lower()}:{Path(candidate_filename).suffix.lower()}"
    )
    flight_key = f"compare:{format_key[0:32]}:{baseline_hash}:{candidate_hash}"
    return cast(
        ArtifactComparisonResponse,
        ARTIFACT_SINGLE_FLIGHT.run(
            flight_key,
            lambda: _compare_artifacts_uncached(
                baseline_filename,
                baseline_data,
                candidate_filename,
                candidate_data,
            ),
        ),
    )


def parser_worker_main() -> None:
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("parser worker payload must be an object")
    operation = str(payload.get("operation", ""))
    content = base64.b64decode(str(payload.get("content_base64", "")), validate=True)
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("parser worker content exceeds the artifact limit")
    if operation == "audit_dxf":
        filename = _safe_filename(str(payload.get("filename", "artifact.dxf")))
        artifact_hash = str(payload.get("artifact_hash") or _sha256(content))
        result: dict[str, Any] = _audit_dxf(
            filename,
            content,
            artifact_hash,
        ).model_dump(mode="json")
    elif operation == "audit_ifc":
        filename = _safe_filename(str(payload.get("filename", "artifact.ifc")))
        artifact_hash = str(payload.get("artifact_hash") or _sha256(content))
        result = _audit_ifc(filename, content, artifact_hash).model_dump(mode="json")
    elif operation == "dxf_fingerprints":
        fingerprints, handles = _dxf_fingerprints(content)
        result = {"fingerprints": dict(fingerprints), "handles": handles}
    elif operation == "ifc_index":
        _model, index = _ifc_index(content)
        result = {"index": index}
    else:
        raise ValueError("unsupported parser worker operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


__all__ = [
    "MAX_ARTIFACT_BYTES",
    "audit_artifact",
    "compare_artifacts",
    "parser_worker_main",
]

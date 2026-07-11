from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import zipfile
from typing import Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .artifact_service import audit_artifact
from .cad_subprocess import CadWorkerFailure, run_cad_worker
from .models import Evidence, Measurement, RunStatus, Violation
from .solid_models import (
    AngleBracketSolid,
    MountingPlateSolid,
    SolidPartContract,
    SolidRunResponse,
)

HASH_GRID_MM = 0.001


def _quantize(value: Any) -> Any:
    if isinstance(value, float):
        quantized = round(value / HASH_GRID_MM) * HASH_GRID_MM
        return 0.0 if abs(quantized) < HASH_GRID_MM / 2 else round(quantized, 6)
    if isinstance(value, list | tuple):
        return [_quantize(item) for item in value]
    if isinstance(value, dict):
        return {key: _quantize(value[key]) for key in sorted(value)}
    return value


def compute_solid_contract_hash(contract: SolidPartContract) -> str:
    data = contract.model_dump(mode="json", exclude={"contract_hash"})
    payload = json.dumps(
        _quantize(data),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _canonicalize_step_bytes(data: bytes) -> bytes:
    text = data.decode("ascii", errors="strict")
    text = re.sub(
        r"(FILE_NAME\('[^']*',)'[^']*'",
        r"\1'2000-01-01T00:00:00'",
        text,
        count=1,
    )
    text = re.sub(
        r"Open CASCADE STEP translator ([0-9.]+) [0-9]+",
        r"Open CASCADE STEP translator \1 1",
        text,
    )
    return text.encode("ascii")


def _measurement(dimension_id: str, target: float, actual: float, tolerance: float) -> Measurement:
    deviation = actual - target
    return Measurement(
        measurement_id=f"measure-{dimension_id}",
        dimension_id=dimension_id,
        target=round(target, 6),
        actual=round(actual, 6),
        deviation=round(deviation, 6),
        tolerance_lower=-tolerance,
        tolerance_upper=tolerance,
        passed=abs(deviation) <= tolerance + 1e-9,
        evidence={"source": "independent_step_reimport", "kernel": "OpenCascade"},
    )


def _expected_box(contract: SolidPartContract) -> tuple[float, float, float]:
    geometry = contract.geometry
    if isinstance(geometry, MountingPlateSolid):
        return geometry.width, geometry.depth, geometry.thickness
    if isinstance(geometry, AngleBracketSolid):
        return geometry.width, geometry.base_depth, geometry.vertical_height
    return geometry.outer_diameter, geometry.outer_diameter, geometry.thickness


def _expected_cylinders(contract: SolidPartContract) -> list[dict[str, Any]]:
    geometry = contract.geometry
    expected: list[dict[str, Any]] = []
    if isinstance(geometry, MountingPlateSolid):
        return [
            {"id": hole.id, "diameter": hole.diameter, "center": list(hole.center)}
            for hole in geometry.holes
        ]
    if isinstance(geometry, AngleBracketSolid):
        return [
            {"id": hole.id, "diameter": hole.diameter, "center": list(hole.center)}
            for hole in geometry.base_holes
        ]
    expected.extend(
        [
            {"id": "outer-cylinder", "diameter": geometry.outer_diameter, "center": [0.0, 0.0]},
            {"id": "inner-bore", "diameter": geometry.inner_diameter, "center": [0.0, 0.0]},
        ]
    )
    radius = geometry.bolt_circle_diameter / 2
    for index in range(geometry.bolt_hole_count):
        angle = 2 * math.pi * index / geometry.bolt_hole_count
        expected.append(
            {
                "id": f"bolt-hole-{index + 1}",
                "diameter": geometry.bolt_hole_diameter,
                "center": [radius * math.cos(angle), radius * math.sin(angle)],
            }
        )
    return expected


def _cylinder_measurements(
    contract: SolidPartContract,
    actual_cylinders: list[dict[str, Any]],
) -> list[Measurement]:
    tolerance = contract.tolerance_mm
    remaining = set(range(len(actual_cylinders)))
    measurements: list[Measurement] = []
    for expected in _expected_cylinders(contract):
        expected_center = expected["center"]
        if not remaining:
            measurements.append(
                _measurement(
                    f"{expected['id']}-diameter", float(expected["diameter"]), 0.0, tolerance
                )
            )
            continue
        best_index = min(
            remaining,
            key=lambda index: (
                abs(float(actual_cylinders[index]["diameter"]) - float(expected["diameter"]))
                + math.dist(
                    actual_cylinders[index]["axis_origin"][:2],
                    expected_center,
                )
            ),
        )
        remaining.remove(best_index)
        actual = actual_cylinders[best_index]
        measurements.extend(
            [
                _measurement(
                    f"{expected['id']}-diameter",
                    float(expected["diameter"]),
                    float(actual["diameter"]),
                    tolerance,
                ),
                _measurement(
                    f"{expected['id']}-center-x",
                    float(expected_center[0]),
                    float(actual["axis_origin"][0]),
                    tolerance,
                ),
                _measurement(
                    f"{expected['id']}-center-y",
                    float(expected_center[1]),
                    float(actual["axis_origin"][1]),
                    tolerance,
                ),
            ]
        )
    return measurements


def _render_pdf(
    contract: SolidPartContract,
    *,
    contract_hash: str,
    artifact_hash: str,
    measurements: list[Measurement],
) -> bytes:
    output = io.BytesIO()
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(
        output,
        pagesize=(page_width, page_height),
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle(f"DatumGuard STEP - {contract.metadata.project_name}")
    pdf.setAuthor("DatumGuard")
    pdf.setFillColorRGB(0.02, 0.02, 0.025)
    pdf.rect(0, page_height - 30 * mm, page_width, 30 * mm, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(16 * mm, page_height - 18 * mm, "DATUMGUARD VERIFIED STEP SOLID")
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(page_width - 16 * mm, page_height - 17 * mm, "STATUS: PASSED")
    pdf.setFillColorRGB(0.72, 0.08, 0.06)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(page_width / 2, page_height - 47 * mm, "DO NOT SCALE")
    rows = [
        ("Project", contract.metadata.project_name),
        ("Revision", contract.metadata.revision),
        ("Family", contract.geometry.type),
        ("Units", "mm"),
        ("Contract", contract_hash),
        ("STEP artifact", artifact_hash),
        ("Dimensions", f"{sum(item.passed for item in measurements)}/{len(measurements)} passed"),
        ("Authority", "solid.step in this verified bundle"),
    ]
    pdf.setFillColorRGB(0.08, 0.09, 0.1)
    y = page_height - 65 * mm
    for label, value in rows:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(20 * mm, y, f"{label}:")
        pdf.setFont("Helvetica", 8.5)
        safe_value = str(value).encode("latin-1", "replace").decode("latin-1")
        pdf.drawString(53 * mm, y, safe_value[:120])
        y -= 8 * mm
    pdf.setStrokeColorRGB(0.1, 0.1, 0.12)
    pdf.line(16 * mm, 18 * mm, page_width - 16 * mm, 18 * mm)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(
        16 * mm,
        11 * mm,
        "Geometry verification only. No structural, pressure, material, code, "
        "or manufacturing certification.",
    )
    pdf.save()
    return output.getvalue()


def _build_bundle(
    contract: SolidPartContract,
    *,
    contract_hash: str,
    artifact_hash: str,
    step_bytes: bytes,
    measurements: list[Measurement],
    summary: dict[str, Any],
) -> bytes:
    verification = {
        "status": "passed",
        "contract_hash": contract_hash,
        "artifact_hash": artifact_hash,
        "summary_source": "independent_step_reimport",
        "measurements": [item.model_dump(mode="json") for item in measurements],
        "summary": summary,
        "violations": [],
    }
    contract_data = contract.model_dump(mode="json")
    contract_data["contract_hash"] = contract_hash
    manifest = {
        "schema_version": "1.0.0",
        "design_kind": "solid_part",
        "contract_hash": contract_hash,
        "artifact_hash": artifact_hash,
        "approval": "passed",
        "authority": "solid.step",
        "pdf_notice": "DO NOT SCALE",
        "files": [
            "solid.step",
            "solid-do-not-scale.pdf",
            "solid-contract.json",
            "verification.json",
            "manifest.json",
        ],
    }
    files = {
        "solid.step": step_bytes,
        "solid-do-not-scale.pdf": _render_pdf(
            contract,
            contract_hash=contract_hash,
            artifact_hash=artifact_hash,
            measurements=measurements,
        ),
        "solid-contract.json": json.dumps(
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


def run_solid_design(contract: SolidPartContract) -> SolidRunResponse:
    contract_hash = compute_solid_contract_hash(contract)
    try:
        writer_result = run_cad_worker(
            {
                "operation": "generate_solid",
                "contract": contract.model_dump(mode="json"),
            }
        )
        step_bytes = _canonicalize_step_bytes(
            base64.b64decode(str(writer_result["step_base64"]), validate=True)
        )
    except (CadWorkerFailure, KeyError, ValueError, TypeError) as exc:
        violation = Violation(
            code="DG_STEP_GENERATION_FAILED",
            message="구조화 contract에서 STEP solid를 생성하지 못했습니다.",
            details={
                "exception": type(exc).__name__,
                "worker": exc.details if isinstance(exc, CadWorkerFailure) else {},
            },
        )
        return SolidRunResponse(
            status=RunStatus.FAILED,
            contract_hash=contract_hash,
            violations=[violation],
            evidence=[
                Evidence(
                    type="step_generation_failure",
                    source="cadquery_opencascade_writer",
                    details=violation.details,
                )
            ],
        )

    audit = audit_artifact("solid.step", step_bytes)
    actual_box = audit.summary.get("bounding_box_mm", {}).get("size", [0.0, 0.0, 0.0])
    expected_box = _expected_box(contract)
    measurements = [
        _measurement("solid-bbox-x", expected_box[0], float(actual_box[0]), contract.tolerance_mm),
        _measurement("solid-bbox-y", expected_box[1], float(actual_box[1]), contract.tolerance_mm),
        _measurement("solid-bbox-z", expected_box[2], float(actual_box[2]), contract.tolerance_mm),
    ]
    measurements.extend(
        _cylinder_measurements(
            contract,
            list(audit.summary.get("cylindrical_surfaces", [])),
        )
    )
    violations = list(audit.violations)
    for measurement in measurements:
        if not measurement.passed:
            violations.append(
                Violation(
                    code="DG_STEP_DIMENSION_OUT_OF_TOLERANCE",
                    message="독립 STEP 재수입 치수가 contract 공차를 벗어났습니다.",
                    entity_ids=[measurement.dimension_id],
                    details={
                        "target": measurement.target,
                        "actual": measurement.actual,
                        "deviation": measurement.deviation,
                        "tolerance_mm": contract.tolerance_mm,
                    },
                )
            )
    artifact_hash = audit.artifact_hash
    passed = (
        audit.status != "failed_verification"
        and bool(audit.summary.get("valid_shape"))
        and not violations
        and all(item.passed for item in measurements)
    )
    summary = {
        "part_family": contract.geometry.type,
        "authority": "STEP",
        "summary_source": "independent_step_reimport",
        "valid_shape": audit.summary.get("valid_shape", False),
        "solid_count": audit.summary.get("solid_count", 0),
        "face_count": audit.summary.get("face_count", 0),
        "edge_count": audit.summary.get("edge_count", 0),
        "volume_mm3": audit.summary.get("volume_mm3", 0),
        "surface_area_mm2": audit.summary.get("surface_area_mm2", 0),
        "bounding_box_mm": audit.summary.get("bounding_box_mm", {}),
        "cylindrical_surface_count": len(audit.summary.get("cylindrical_surfaces", [])),
        "dimension_pass_count": sum(item.passed for item in measurements),
        "dimension_count": len(measurements),
    }
    evidence = [
        Evidence(
            type="canonical_solid_generation",
            source="isolated_cadquery_opencascade_writer",
            details={"serialized_before_verification": True, "isolated_process": True},
        ),
        Evidence(
            type="independent_step_remeasurement",
            source="isolated_cadquery_opencascade_step_reimport",
            details={
                "writer_memory_reused": False,
                "comparison_epsilon_mm": contract.tolerance_mm,
                "isolated_process": True,
            },
        ),
    ]
    bundle_base64: str | None = None
    if passed and artifact_hash:
        bundle_base64 = base64.b64encode(
            _build_bundle(
                contract,
                contract_hash=contract_hash,
                artifact_hash=artifact_hash,
                step_bytes=step_bytes,
                measurements=measurements,
                summary=summary,
            )
        ).decode("ascii")
    return SolidRunResponse(
        status=RunStatus.PASSED if passed else RunStatus.FAILED,
        contract_hash=contract_hash,
        artifact_hash=artifact_hash,
        measurements=measurements,
        violations=violations,
        evidence=evidence,
        summary=summary,
        preview_mesh=audit.preview_mesh,
        step_base64=base64.b64encode(step_bytes).decode("ascii") if passed else None,
        bundle_base64=bundle_base64,
    )

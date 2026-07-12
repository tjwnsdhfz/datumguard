from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Any

from ezdxf import units
from ezdxf._options import options
from ezdxf.document import Drawing
from ezdxf.entities.dxfentity import DXFEntity
from ezdxf.entities.line import Line
from ezdxf.entities.point import Point as DXFPoint
from ezdxf.entities.text import Text
from ezdxf.filemanagement import new, read
from ezdxf.lldxf.const import DXFError, DXFValueError

from .core import compute_artifact_hash
from .frame_models import StructuralFrameContract
from .frame_service import validate_frame_contract
from .models import ContractStatus, Evidence, Measurement, RunStatus, Violation

FRAME_DXF_LAYERS = ("S-FRAME", "S-SUPP", "S-LOAD", "DG-META")
FRAME_XDATA_APP_ID = "DATUMGUARD"
FRAME_DXF_VERSION = "AC1027"
FRAME_DXF_DATUM = "origin:0,0,0;x:1,0,0;y:0,1,0;z:0,0,1"
FRAME_DXF_UNIT = "mm"
FRAME_DXF_TOLERANCE_MM = 0.001

options.write_fixed_meta_data_for_testing = True


class FrameDxfGenerationError(ValueError):
    """Raised when an unverified structural contract requests an official DXF."""


@dataclass(frozen=True)
class FrameDxfVerificationResult:
    status: RunStatus
    contract_hash: str
    artifact_hash: str
    measurements: list[Measurement]
    violations: list[Violation]
    evidence: list[Evidence]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "contract_hash": self.contract_hash,
            "artifact_hash": self.artifact_hash,
            "measurements": [item.model_dump(mode="json") for item in self.measurements],
            "violations": [item.model_dump(mode="json") for item in self.violations],
            "evidence": [item.model_dump(mode="json") for item in self.evidence],
            "summary": self.summary,
            "error": None,
        }


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


def _set_xdata(
    entity: DXFEntity,
    *,
    contract_hash: str,
    entity_id: str,
    entity_type: str,
    revision: str,
) -> None:
    entity.set_xdata(
        FRAME_XDATA_APP_ID,
        [
            (1000, f"contract_hash={contract_hash}"),
            (1000, f"entity_id={entity_id}"),
            (1000, f"entity_type={entity_type}"),
            (1000, f"revision={revision}"),
            (1000, f"datum={FRAME_DXF_DATUM}"),
            (1000, f"unit={FRAME_DXF_UNIT}"),
            (1000, "design_kind=structural_frame"),
        ],
    )


def _canonical_contract(contract: StructuralFrameContract) -> tuple[StructuralFrameContract, str]:
    validation = validate_frame_contract(contract)
    if validation.status is not ContractStatus.READY or validation.normalized_contract is None:
        codes = ", ".join(item.code for item in validation.violations) or "unknown"
        raise FrameDxfGenerationError(
            f"structural frame contract is not ready for DXF generation: {codes}"
        )
    return validation.normalized_contract, validation.contract_hash


def generate_frame_dxf(contract: StructuralFrameContract) -> bytes:
    """Write a deterministic R2013/mm structural-frame evidence DXF.

    The writer accepts only a solver-valid canonical contract. The returned bytes are
    generated-unverified; callers must re-open them with :func:`verify_frame_dxf` before
    presenting any official PASS or export bundle.
    """

    normalized, contract_hash = _canonical_contract(contract)
    document = new("R2013", setup=False)
    document.units = units.MM
    _stabilize_header(document)
    if FRAME_XDATA_APP_ID not in document.appids:
        document.appids.add(FRAME_XDATA_APP_ID)
    colors = {"S-FRAME": 7, "S-SUPP": 3, "S-LOAD": 1, "DG-META": 6}
    for layer in FRAME_DXF_LAYERS:
        if layer not in document.layers:
            document.layers.add(layer, color=colors[layer])

    modelspace = document.modelspace()
    revision = normalized.metadata.revision
    nodes = {node.id: node for node in normalized.nodes}
    for member in sorted(normalized.members, key=lambda item: item.id):
        start = nodes[member.start_node_id].point
        end = nodes[member.end_node_id].point
        member_entity = modelspace.add_line(
            (start[0], start[1], 0.0),
            (end[0], end[1], 0.0),
            dxfattribs={"layer": "S-FRAME"},
        )
        _set_xdata(
            member_entity,
            contract_hash=contract_hash,
            entity_id=member.id,
            entity_type="member",
            revision=revision,
        )
    for support in sorted(normalized.supports, key=lambda item: item.id):
        point = nodes[support.node_id].point
        support_entity = modelspace.add_point(
            (point[0], point[1], 0.0), dxfattribs={"layer": "S-SUPP"}
        )
        _set_xdata(
            support_entity,
            contract_hash=contract_hash,
            entity_id=support.id,
            entity_type="support",
            revision=revision,
        )
    for load in sorted(normalized.loads, key=lambda item: item.id):
        point = nodes[load.node_id].point
        load_entity = modelspace.add_point(
            (point[0], point[1], 0.0), dxfattribs={"layer": "S-LOAD"}
        )
        _set_xdata(
            load_entity,
            contract_hash=contract_hash,
            entity_id=load.id,
            entity_type="load",
            revision=revision,
        )
    metadata_entity = modelspace.add_text(
        f"{normalized.metadata.project_name} | Rev {revision} | FRAMEGUARD SCREENING ONLY",
        height=100.0,
        dxfattribs={"layer": "DG-META"},
    )
    min_x = min(node.point[0] for node in normalized.nodes)
    min_y = min(node.point[1] for node in normalized.nodes)
    metadata_entity.set_placement((min_x, min_y - 300.0))
    _set_xdata(
        metadata_entity,
        contract_hash=contract_hash,
        entity_id="frame-metadata",
        entity_type="metadata",
        revision=revision,
    )

    stream = io.StringIO(newline="\n")
    document.write(stream, fmt="asc")
    return stream.getvalue().encode("utf-8")


def _xdata(entity: DXFEntity) -> dict[str, str]:
    try:
        tags = entity.get_xdata(FRAME_XDATA_APP_ID)
    except DXFValueError:
        return {}
    result: dict[str, str] = {}
    for tag in tags:
        if tag.code == 1000 and isinstance(tag.value, str) and "=" in tag.value:
            key, value = tag.value.split("=", 1)
            result[key] = value
    return result


def _measurement(
    measurement_id: str,
    entity_id: str,
    actual: float,
    *,
    evidence: dict[str, Any],
) -> Measurement:
    return Measurement(
        measurement_id=measurement_id,
        dimension_id=entity_id,
        target=0.0,
        actual=actual,
        deviation=actual,
        tolerance_lower=0.0,
        tolerance_upper=FRAME_DXF_TOLERANCE_MM,
        passed=actual <= FRAME_DXF_TOLERANCE_MM,
        evidence=evidence,
    )


def _distance3(left: Any, right: tuple[float, float]) -> float:
    return math.sqrt(
        (float(left.x) - right[0]) ** 2 + (float(left.y) - right[1]) ** 2 + float(left.z) ** 2
    )


def _entity_metadata_violations(
    entity: DXFEntity,
    metadata: dict[str, str],
    *,
    expected_hash: str,
    expected_id: str | None,
    expected_type: str | None,
    revision: str,
) -> list[Violation]:
    violations: list[Violation] = []
    handle = str(entity.dxf.handle)
    required = {
        "contract_hash",
        "entity_id",
        "entity_type",
        "revision",
        "datum",
        "unit",
        "design_kind",
    }
    missing = sorted(required - set(metadata))
    if missing:
        violations.append(
            Violation(
                code="DG_FRAME_DXF_XDATA_MISSING",
                message="A structural frame DXF entity is missing required identity XDATA.",
                details={"handle": handle, "missing_keys": missing},
            )
        )
        return violations
    entity_id = metadata["entity_id"]
    checks = (
        (
            metadata["contract_hash"] == expected_hash,
            "DG_FRAME_DXF_HASH_MISMATCH",
            "DXF XDATA contract hash differs from the canonical frame contract.",
            {"actual": metadata["contract_hash"], "expected": expected_hash},
        ),
        (
            expected_id is None or entity_id == expected_id,
            "DG_FRAME_DXF_ENTITY_ID_MISMATCH",
            "DXF entity identity differs from the expected structural object.",
            {"actual": entity_id, "expected": expected_id},
        ),
        (
            expected_type is None or metadata["entity_type"] == expected_type,
            "DG_FRAME_DXF_ENTITY_TYPE_MISMATCH",
            "DXF entity type XDATA is invalid.",
            {"actual": metadata["entity_type"], "expected": expected_type},
        ),
        (
            metadata["revision"] == revision,
            "DG_FRAME_DXF_REVISION_MISMATCH",
            "DXF revision XDATA differs from the frame contract.",
            {"actual": metadata["revision"], "expected": revision},
        ),
        (
            metadata["datum"] == FRAME_DXF_DATUM,
            "DG_FRAME_DXF_DATUM_MISMATCH",
            "DXF datum XDATA is not the normalized FrameGuard XY datum.",
            {"actual": metadata["datum"], "expected": FRAME_DXF_DATUM},
        ),
        (
            metadata["unit"] == FRAME_DXF_UNIT,
            "DG_FRAME_DXF_UNIT_XDATA_MISMATCH",
            "DXF unit XDATA must be mm.",
            {"actual": metadata["unit"], "expected": FRAME_DXF_UNIT},
        ),
        (
            metadata["design_kind"] == "structural_frame",
            "DG_FRAME_DXF_DESIGN_KIND_MISMATCH",
            "DXF design_kind XDATA must be structural_frame.",
            {"actual": metadata["design_kind"], "expected": "structural_frame"},
        ),
    )
    for passed, code, message, details in checks:
        if not passed:
            violations.append(
                Violation(
                    code=code,
                    message=message,
                    entity_ids=[entity_id] if entity_id else [],
                    details={"handle": handle, **details},
                )
            )
    return violations


def verify_frame_dxf(
    contract: StructuralFrameContract,
    dxf_bytes: bytes,
    expected_contract_hash: str | None = None,
) -> FrameDxfVerificationResult:
    """Independently re-open and remeasure a serialized FrameGuard DXF."""

    artifact_hash = compute_artifact_hash(dxf_bytes)
    try:
        normalized, canonical_hash = _canonical_contract(contract)
    except FrameDxfGenerationError as exc:
        return FrameDxfVerificationResult(
            status=RunStatus.FAILED,
            contract_hash=expected_contract_hash or "sha256:unavailable",
            artifact_hash=artifact_hash,
            measurements=[],
            violations=[
                Violation(
                    code="DG_FRAME_DXF_CONTRACT_NOT_READY",
                    message=str(exc),
                )
            ],
            evidence=[
                Evidence(
                    type="independent_dxf_verification",
                    source="ezdxf_reopen",
                    details={"approved": False, "fail_closed": True},
                )
            ],
            summary={"approved": False},
        )
    expected_hash = expected_contract_hash or canonical_hash
    violations: list[Violation] = []
    measurements: list[Measurement] = []
    try:
        document = read(io.StringIO(dxf_bytes.decode("utf-8")))
    except (UnicodeDecodeError, DXFError, ValueError) as exc:
        return FrameDxfVerificationResult(
            status=RunStatus.FAILED,
            contract_hash=expected_hash,
            artifact_hash=artifact_hash,
            measurements=[],
            violations=[
                Violation(
                    code="DG_FRAME_DXF_PARSE_FAILED",
                    message="The serialized frame DXF could not be independently reopened.",
                    details={"reason": str(exc)},
                )
            ],
            evidence=[
                Evidence(
                    type="independent_dxf_verification",
                    source="ezdxf_reopen",
                    details={"approved": False, "fail_closed": True},
                )
            ],
            summary={"approved": False},
        )

    if document.dxfversion != FRAME_DXF_VERSION:
        violations.append(
            Violation(
                code="DG_FRAME_DXF_VERSION_INVALID",
                message="Structural frame DXF must be R2013.",
                details={"actual": document.dxfversion, "expected": FRAME_DXF_VERSION},
            )
        )
    if document.units != units.MM:
        violations.append(
            Violation(
                code="DG_FRAME_DXF_INSUNITS_INVALID",
                message="Structural frame DXF $INSUNITS must be millimetres.",
                details={"actual": document.units, "expected": units.MM},
            )
        )
    layer_names = {layer.dxf.name for layer in document.layers}
    missing_layers = sorted(set(FRAME_DXF_LAYERS) - layer_names)
    if missing_layers:
        violations.append(
            Violation(
                code="DG_FRAME_DXF_LAYER_MISSING",
                message="Structural frame DXF is missing required layers.",
                details={"missing_layers": missing_layers},
            )
        )

    nodes = {node.id: node for node in normalized.nodes}
    expected_members = {item.id: item for item in normalized.members}
    expected_supports = {item.id: item for item in normalized.supports}
    expected_loads = {item.id: item for item in normalized.loads}
    seen: dict[str, set[str]] = {"member": set(), "support": set(), "load": set()}
    member_geometries: dict[tuple[tuple[float, float], tuple[float, float]], str] = {}
    relevant_count = 0
    for entity in document.modelspace():
        if entity.dxf.layer not in FRAME_DXF_LAYERS:
            continue
        relevant_count += 1
        metadata = _xdata(entity)
        entity_id = metadata.get("entity_id")
        entity_type = metadata.get("entity_type")
        expected_layer = {
            "member": "S-FRAME",
            "support": "S-SUPP",
            "load": "S-LOAD",
            "metadata": "DG-META",
        }.get(entity_type or "")
        violations.extend(
            _entity_metadata_violations(
                entity,
                metadata,
                expected_hash=expected_hash,
                expected_id=None,
                expected_type=None,
                revision=normalized.metadata.revision,
            )
        )
        if not entity_id or not entity_type:
            continue
        if expected_layer is None or entity.dxf.layer != expected_layer:
            violations.append(
                Violation(
                    code="DG_FRAME_DXF_LAYER_ENTITY_MISMATCH",
                    message="Structural entity is stored on the wrong DXF layer.",
                    entity_ids=[entity_id],
                    details={"actual": entity.dxf.layer, "expected": expected_layer},
                )
            )
        if entity_type in seen:
            if entity_id in seen[entity_type]:
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_ENTITY_ID_DUPLICATE",
                        message="Structural DXF contains a duplicate entity identifier.",
                        entity_ids=[entity_id],
                    )
                )
            seen[entity_type].add(entity_id)

        if entity_type == "member":
            if isinstance(entity, Line):
                start_key = (
                    round(float(entity.dxf.start.x), 6),
                    round(float(entity.dxf.start.y), 6),
                )
                end_key = (
                    round(float(entity.dxf.end.x), 6),
                    round(float(entity.dxf.end.y), 6),
                )
                geometry_key = (
                    (start_key, end_key) if start_key <= end_key else (end_key, start_key)
                )
                duplicate_id = member_geometries.get(geometry_key)
                if duplicate_id is not None and duplicate_id != entity_id:
                    violations.append(
                        Violation(
                            code="DG_FRAME_DXF_DUPLICATE_GEOMETRY",
                            message=(
                                "Two structural member entities have duplicate centerline geometry."
                            ),
                            entity_ids=sorted([duplicate_id, entity_id]),
                        )
                    )
                member_geometries[geometry_key] = entity_id
            member = expected_members.get(entity_id)
            if member is None:
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_ENTITY_UNEXPECTED",
                        message="DXF contains a member not present in the contract.",
                        entity_ids=[entity_id],
                    )
                )
                continue
            if not isinstance(entity, Line):
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_ENTITY_TYPE_INVALID",
                        message="A structural member must be serialized as a LINE.",
                        entity_ids=[entity_id],
                        details={"actual": entity.dxftype()},
                    )
                )
                continue
            expected_start = nodes[member.start_node_id].point
            expected_end = nodes[member.end_node_id].point
            direct = max(
                _distance3(entity.dxf.start, expected_start),
                _distance3(entity.dxf.end, expected_end),
            )
            reversed_distance = max(
                _distance3(entity.dxf.start, expected_end),
                _distance3(entity.dxf.end, expected_start),
            )
            deviation = min(direct, reversed_distance)
            measurements.append(
                _measurement(
                    f"frame-dxf-{entity_id}-endpoints",
                    entity_id,
                    deviation,
                    evidence={"layer": entity.dxf.layer, "handle": entity.dxf.handle},
                )
            )
            if deviation > FRAME_DXF_TOLERANCE_MM:
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_ENDPOINT_DEVIATION",
                        message="Reopened member endpoints differ from the canonical contract.",
                        entity_ids=[entity_id],
                        details={
                            "deviation_mm": deviation,
                            "tolerance_mm": FRAME_DXF_TOLERANCE_MM,
                        },
                    )
                )
        elif entity_type in {"support", "load"}:
            expected_collection = expected_supports if entity_type == "support" else expected_loads
            expected = expected_collection.get(entity_id)
            if expected is None:
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_ENTITY_UNEXPECTED",
                        message=f"DXF contains a {entity_type} not present in the contract.",
                        entity_ids=[entity_id],
                    )
                )
                continue
            if not isinstance(entity, DXFPoint):
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_ENTITY_TYPE_INVALID",
                        message=f"A structural {entity_type} must be serialized as a POINT.",
                        entity_ids=[entity_id],
                        details={"actual": entity.dxftype()},
                    )
                )
                continue
            expected_point = nodes[expected.node_id].point
            deviation = _distance3(entity.dxf.location, expected_point)
            measurements.append(
                _measurement(
                    f"frame-dxf-{entity_id}-point",
                    entity_id,
                    deviation,
                    evidence={"layer": entity.dxf.layer, "handle": entity.dxf.handle},
                )
            )
            if deviation > FRAME_DXF_TOLERANCE_MM:
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_POINT_DEVIATION",
                        message=f"Reopened {entity_type} point differs from the canonical node.",
                        entity_ids=[entity_id],
                        details={
                            "deviation_mm": deviation,
                            "tolerance_mm": FRAME_DXF_TOLERANCE_MM,
                        },
                    )
                )
        elif entity_type == "metadata":
            if entity_id != "frame-metadata" or not isinstance(entity, Text):
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_METADATA_INVALID",
                        message="FrameGuard DXF metadata entity is invalid.",
                        entity_ids=[entity_id],
                    )
                )
        else:
            violations.append(
                Violation(
                    code="DG_FRAME_DXF_ENTITY_TYPE_INVALID",
                    message="DXF contains an unsupported structural entity type.",
                    entity_ids=[entity_id],
                    details={"entity_type": entity_type},
                )
            )

    for entity_type, expected_ids in (
        ("member", set(expected_members)),
        ("support", set(expected_supports)),
        ("load", set(expected_loads)),
    ):
        missing = sorted(expected_ids - seen[entity_type])
        if missing:
            violations.append(
                Violation(
                    code="DG_FRAME_DXF_ENTITY_MISSING",
                    message=f"DXF is missing expected structural {entity_type} entities.",
                    entity_ids=missing,
                )
            )
    expected_relevant_count = (
        len(expected_members) + len(expected_supports) + len(expected_loads) + 1
    )
    if relevant_count != expected_relevant_count:
        violations.append(
            Violation(
                code="DG_FRAME_DXF_ENTITY_COUNT_MISMATCH",
                message="Reopened DXF entity count differs from the canonical contract.",
                details={"actual": relevant_count, "expected": expected_relevant_count},
            )
        )

    approved = not violations and all(item.passed for item in measurements)
    status = RunStatus.PASSED if approved else RunStatus.FAILED
    max_deviation = max((item.actual for item in measurements), default=0.0)
    return FrameDxfVerificationResult(
        status=status,
        contract_hash=expected_hash,
        artifact_hash=artifact_hash,
        measurements=measurements,
        violations=violations,
        evidence=[
            Evidence(
                type="independent_dxf_verification",
                source="ezdxf_reopen",
                details={
                    "approved": approved,
                    "official_pass": approved,
                    "dxf_version": document.dxfversion,
                    "insunits": document.units,
                    "coordinate_tolerance_mm": FRAME_DXF_TOLERANCE_MM,
                    "max_deviation_mm": max_deviation,
                    "xdata_app_id": FRAME_XDATA_APP_ID,
                },
            )
        ],
        summary={
            "approved": approved,
            "member_count": len(seen["member"]),
            "support_count": len(seen["support"]),
            "load_count": len(seen["load"]),
            "max_deviation_mm": max_deviation,
            "layers": list(FRAME_DXF_LAYERS),
        },
    )


__all__ = [
    "FRAME_DXF_DATUM",
    "FRAME_DXF_LAYERS",
    "FRAME_DXF_TOLERANCE_MM",
    "FRAME_DXF_UNIT",
    "FRAME_DXF_VERSION",
    "FRAME_XDATA_APP_ID",
    "FrameDxfGenerationError",
    "FrameDxfVerificationResult",
    "generate_frame_dxf",
    "verify_frame_dxf",
]

from __future__ import annotations

import base64
import io
import json
import math
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
from .frame_models import FrameSourceProvenance, StructuralFrameContract
from .frame_provenance import provenance_index
from .frame_service import validate_frame_contract
from .models import ContractStatus, Evidence, Measurement, RunStatus, StrictModel, Violation

FRAME_DXF_LAYERS = ("S-FRAME", "S-SUPP", "S-LOAD", "DG-META")
FRAME_XDATA_APP_ID = "DATUMGUARD"
FRAME_DXF_VERSION = "AC1027"
FRAME_DXF_DATUM = "origin:0,0,0;x:1,0,0;y:0,1,0;z:0,0,1"
FRAME_DXF_UNIT = "mm"
FRAME_DXF_TOLERANCE_MM = 0.001
FRAME_CONTRACT_RECORD_KEY = "DATUMGUARD_FRAME_CONTRACT_V1"
FRAME_CONTRACT_RECORD_SIGNATURE = "DATUMGUARD_FRAME_CONTRACT_V1"
FRAME_CONTRACT_RECORD_CHUNK_SIZE = 1800

options.write_fixed_meta_data_for_testing = True


class FrameDxfGenerationError(ValueError):
    """Raised when an unverified structural contract requests an official DXF."""


class FrameDxfVerificationResult(StrictModel):
    status: RunStatus
    contract_hash: str
    artifact_hash: str
    measurements: list[Measurement]
    violations: list[Violation]
    evidence: list[Evidence]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["error"] = None
        return payload


def _canonical_semantic_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical_semantic_value(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple | list):
        items = [_canonical_semantic_value(item) for item in value]
        if all(isinstance(item, dict) and "id" in item for item in items):
            return sorted(items, key=lambda item: str(item["id"]))
        if all(
            isinstance(item, dict) and {"entity_type", "entity_id", "source_object_id"} <= set(item)
            for item in items
        ):
            return sorted(
                items,
                key=lambda item: (
                    str(item["entity_type"]),
                    str(item["entity_id"]),
                    str(item["source_object_id"]),
                ),
            )
        return items
    return value


def _contract_record_bytes(contract: StructuralFrameContract, contract_hash: str) -> bytes:
    payload = contract.model_dump(mode="json", exclude={"intent_text"})
    payload["contract_hash"] = contract_hash
    return json.dumps(
        _canonical_semantic_value(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _write_contract_record(document: Drawing, payload: bytes) -> None:
    encoded = base64.b64encode(payload).decode("ascii")
    chunks = [
        encoded[index : index + FRAME_CONTRACT_RECORD_CHUNK_SIZE]
        for index in range(0, len(encoded), FRAME_CONTRACT_RECORD_CHUNK_SIZE)
    ]
    record = document.rootdict.add_xrecord(FRAME_CONTRACT_RECORD_KEY)
    record.reset(
        [
            (1, FRAME_CONTRACT_RECORD_SIGNATURE),
            (90, len(chunks)),
            *((1, chunk) for chunk in chunks),
        ]
    )


def _read_contract_record(document: Drawing) -> bytes:
    record = document.rootdict.get(FRAME_CONTRACT_RECORD_KEY)
    if record is None or not hasattr(record, "tags"):
        raise ValueError("the sealed structural contract XRECORD is missing")
    tags = list(record.tags)
    strings = [str(tag.value) for tag in tags if tag.code == 1]
    counts = [int(tag.value) for tag in tags if tag.code == 90]
    if not strings or strings[0] != FRAME_CONTRACT_RECORD_SIGNATURE or len(counts) != 1:
        raise ValueError("the sealed structural contract XRECORD header is invalid")
    chunks = strings[1:]
    if counts[0] != len(chunks) or counts[0] < 1:
        raise ValueError("the sealed structural contract XRECORD chunk count is invalid")
    try:
        return base64.b64decode("".join(chunks), validate=True)
    except ValueError as exc:
        raise ValueError("the sealed structural contract XRECORD payload is invalid") from exc


def _semantic_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


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
    provenance: FrameSourceProvenance | None = None,
    source_object_id: str | None = None,
    semantics: dict[str, Any] | None = None,
) -> None:
    values = [
        (1000, f"contract_hash={contract_hash}"),
        (1000, f"entity_id={entity_id}"),
        (1000, f"entity_type={entity_type}"),
        (1000, f"revision={revision}"),
        (1000, f"datum={FRAME_DXF_DATUM}"),
        (1000, f"unit={FRAME_DXF_UNIT}"),
        (1000, "design_kind=structural_frame"),
    ]
    if provenance is not None:
        values.extend(
            [
                (1000, f"source_system={provenance.source_system}"),
                (1000, f"source_document_id={provenance.source_document_id}"),
                (1000, f"source_exchange_hash={provenance.exchange_hash}"),
            ]
        )
    if source_object_id is not None:
        values.append((1000, f"source_object_id={source_object_id}"))
    for key, value in sorted((semantics or {}).items()):
        values.append((1000, f"semantic.{key}={_semantic_string(value)}"))
    entity.set_xdata(
        FRAME_XDATA_APP_ID,
        values,
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

    contract_record = _contract_record_bytes(normalized, contract_hash)
    contract_record_hash = compute_artifact_hash(contract_record)
    _write_contract_record(document, contract_record)

    modelspace = document.modelspace()
    revision = normalized.metadata.revision
    nodes = {node.id: node for node in normalized.nodes}
    source_index = provenance_index(normalized)
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
            provenance=normalized.provenance,
            source_object_id=source_index.get(("member", member.id)),
            semantics={
                "start_node_id": member.start_node_id,
                "end_node_id": member.end_node_id,
                "area_mm2": member.area_mm2,
                "inertia_mm4": member.inertia_mm4,
                "elastic_modulus_mpa": member.elastic_modulus_mpa,
                "section_depth_mm": member.section_depth_mm,
                "allowable_stress_mpa": member.allowable_stress_mpa,
                "locked": member.locked,
                "start_node_locked": nodes[member.start_node_id].locked,
                "end_node_locked": nodes[member.end_node_id].locked,
            },
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
            provenance=normalized.provenance,
            source_object_id=source_index.get(("support", support.id)),
            semantics={
                "node_id": support.node_id,
                "ux": support.ux,
                "uy": support.uy,
                "rz": support.rz,
            },
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
            provenance=normalized.provenance,
            source_object_id=source_index.get(("load", load.id)),
            semantics={
                "node_id": load.node_id,
                "fx_n": load.fx_n,
                "fy_n": load.fy_n,
                "mz_nmm": load.mz_nmm,
            },
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
        provenance=normalized.provenance,
        semantics={
            "contract_record_hash": contract_record_hash,
            "max_displacement_mm": normalized.limits.max_displacement_mm,
            "allowable_stress_mpa": normalized.limits.allowable_stress_mpa,
        },
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
    provenance: FrameSourceProvenance | None,
    expected_source_object_id: str | None,
    expected_semantics: dict[str, Any] | None,
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
    if provenance is not None:
        required.update({"source_system", "source_document_id", "source_exchange_hash"})
    if expected_source_object_id is not None:
        required.add("source_object_id")
    required.update(f"semantic.{key}" for key in (expected_semantics or {}))
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
    if provenance is not None:
        provenance_checks: list[tuple[bool, str, str | None, str]] = [
            (
                metadata.get("source_system") == provenance.source_system,
                "source_system",
                metadata.get("source_system"),
                provenance.source_system,
            ),
            (
                metadata.get("source_document_id") == provenance.source_document_id,
                "source_document_id",
                metadata.get("source_document_id"),
                provenance.source_document_id,
            ),
            (
                metadata.get("source_exchange_hash") == provenance.exchange_hash,
                "source_exchange_hash",
                metadata.get("source_exchange_hash"),
                provenance.exchange_hash,
            ),
        ]
        if expected_source_object_id is not None:
            provenance_checks.append(
                (
                    metadata.get("source_object_id") == expected_source_object_id,
                    "source_object_id",
                    metadata.get("source_object_id"),
                    expected_source_object_id,
                )
            )
        for passed, field, actual, expected in provenance_checks:
            if not passed:
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_PROVENANCE_MISMATCH",
                        message="DXF source provenance differs from the normalized Rhino exchange.",
                        entity_ids=[entity_id] if entity_id else [],
                        details={
                            "handle": handle,
                            "field": field,
                            "actual": actual,
                            "expected": expected,
                        },
                    )
                )
    for key, expected in sorted((expected_semantics or {}).items()):
        field = f"semantic.{key}"
        actual = metadata.get(field)
        encoded_expected = _semantic_string(expected)
        if actual != encoded_expected:
            violations.append(
                Violation(
                    code="DG_FRAME_DXF_SEMANTIC_MISMATCH",
                    message="DXF structural semantics differ from the normalized contract.",
                    entity_ids=[entity_id] if entity_id else [],
                    details={
                        "handle": handle,
                        "field": key,
                        "actual": actual,
                        "expected": encoded_expected,
                    },
                )
            )
    return violations


def _expected_semantics(
    contract: StructuralFrameContract,
    entity_type: str | None,
    entity_id: str | None,
    contract_record_hash: str,
) -> dict[str, Any] | None:
    if entity_type == "member":
        member = next((item for item in contract.members if item.id == entity_id), None)
        if member is None:
            return None
        nodes = {item.id: item for item in contract.nodes}
        return {
            "start_node_id": member.start_node_id,
            "end_node_id": member.end_node_id,
            "area_mm2": member.area_mm2,
            "inertia_mm4": member.inertia_mm4,
            "elastic_modulus_mpa": member.elastic_modulus_mpa,
            "section_depth_mm": member.section_depth_mm,
            "allowable_stress_mpa": member.allowable_stress_mpa,
            "locked": member.locked,
            "start_node_locked": nodes[member.start_node_id].locked,
            "end_node_locked": nodes[member.end_node_id].locked,
        }
    if entity_type == "support":
        support = next((item for item in contract.supports if item.id == entity_id), None)
        if support is None:
            return None
        return {
            "node_id": support.node_id,
            "ux": support.ux,
            "uy": support.uy,
            "rz": support.rz,
        }
    if entity_type == "load":
        load = next((item for item in contract.loads if item.id == entity_id), None)
        if load is None:
            return None
        return {
            "node_id": load.node_id,
            "fx_n": load.fx_n,
            "fy_n": load.fy_n,
            "mz_nmm": load.mz_nmm,
        }
    if entity_type == "metadata" and entity_id == "frame-metadata":
        return {
            "contract_record_hash": contract_record_hash,
            "max_displacement_mm": contract.limits.max_displacement_mm,
            "allowable_stress_mpa": contract.limits.allowable_stress_mpa,
        }
    return None


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
    if expected_contract_hash is not None and expected_contract_hash != canonical_hash:
        violations.append(
            Violation(
                code="DG_FRAME_DXF_HASH_MISMATCH",
                message="The expected hash differs from the canonical structural contract hash.",
                details={"actual": expected_contract_hash, "expected": canonical_hash},
            )
        )
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

    expected_contract_record = _contract_record_bytes(normalized, expected_hash)
    contract_record_hash = compute_artifact_hash(expected_contract_record)
    contract_record_verified = False
    try:
        reopened_contract_record = _read_contract_record(document)
        record_payload = json.loads(reopened_contract_record.decode("utf-8"))
        record_contract = StructuralFrameContract.model_validate(record_payload)
        record_validation = validate_frame_contract(record_contract)
        if (
            record_validation.status is not ContractStatus.READY
            or record_validation.contract_hash != expected_hash
            or record_contract.contract_hash != expected_hash
        ):
            violations.append(
                Violation(
                    code="DG_FRAME_DXF_CONTRACT_RECORD_INVALID",
                    message="The reopened DXF contract record is not a valid canonical contract.",
                    details={
                        "record_contract_hash": record_contract.contract_hash,
                        "canonical_record_hash": record_validation.contract_hash,
                        "expected_contract_hash": expected_hash,
                        "violation_codes": [item.code for item in record_validation.violations],
                    },
                )
            )
        elif reopened_contract_record != expected_contract_record:
            violations.append(
                Violation(
                    code="DG_FRAME_DXF_CONTRACT_RECORD_MISMATCH",
                    message="The reopened DXF contract semantics differ from the input contract.",
                    details={
                        "actual_record_hash": compute_artifact_hash(reopened_contract_record),
                        "expected_record_hash": contract_record_hash,
                    },
                )
            )
        else:
            contract_record_verified = True
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        violations.append(
            Violation(
                code="DG_FRAME_DXF_CONTRACT_RECORD_INVALID",
                message="The DXF does not contain a readable sealed structural contract record.",
                details={"reason": str(exc)},
            )
        )

    for layout in document.layouts:
        if layout.name != "Model" and len(layout) > 0:
            violations.append(
                Violation(
                    code="DG_FRAME_DXF_PAPERSPACE_CONTENT_FORBIDDEN",
                    message="FrameGuard evidence DXF must not contain paper-space entities.",
                    details={"layout": layout.name, "entity_count": len(layout)},
                )
            )
    for block in document.blocks:
        if not block.name.startswith("*"):
            violations.append(
                Violation(
                    code="DG_FRAME_DXF_USER_BLOCK_FORBIDDEN",
                    message="FrameGuard evidence DXF must not contain user block definitions.",
                    details={"block": block.name, "entity_count": len(block)},
                )
            )

    nodes = {node.id: node for node in normalized.nodes}
    expected_members = {item.id: item for item in normalized.members}
    expected_supports = {item.id: item for item in normalized.supports}
    expected_loads = {item.id: item for item in normalized.loads}
    source_index = provenance_index(normalized)
    seen: dict[str, set[str]] = {"member": set(), "support": set(), "load": set()}
    member_geometries: dict[tuple[tuple[float, float], tuple[float, float]], str] = {}
    relevant_count = 0
    for entity in document.modelspace():
        if entity.dxf.layer not in FRAME_DXF_LAYERS:
            violations.append(
                Violation(
                    code="DG_FRAME_DXF_LAYER_UNEXPECTED",
                    message="FrameGuard DXF contains model-space geometry on an unexpected layer.",
                    details={
                        "handle": str(entity.dxf.handle),
                        "layer": entity.dxf.layer,
                        "entity_type": entity.dxftype(),
                    },
                )
            )
            continue
        relevant_count += 1
        metadata = _xdata(entity)
        entity_id = metadata.get("entity_id")
        entity_type = metadata.get("entity_type")
        expected_source_object_id = (
            source_index.get((entity_type, entity_id))
            if entity_type is not None and entity_id is not None
            else None
        )
        expected_semantics = _expected_semantics(
            normalized,
            entity_type,
            entity_id,
            contract_record_hash,
        )
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
                provenance=normalized.provenance,
                expected_source_object_id=expected_source_object_id,
                expected_semantics=expected_semantics,
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
            elif entity.dxf.text != (
                f"{normalized.metadata.project_name} | Rev "
                f"{normalized.metadata.revision} | FRAMEGUARD SCREENING ONLY"
            ):
                violations.append(
                    Violation(
                        code="DG_FRAME_DXF_METADATA_TEXT_MISMATCH",
                        message="FrameGuard screening annotation differs from the canonical text.",
                        entity_ids=[entity_id],
                        details={"actual": entity.dxf.text},
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
    provenance_verified = normalized.provenance is None or not any(
        item.code in {"DG_FRAME_DXF_PROVENANCE_MISMATCH", "DG_FRAME_DXF_XDATA_MISSING"}
        for item in violations
    )
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
                    "provenance_required": normalized.provenance is not None,
                    "provenance_verified": provenance_verified,
                    "contract_record_verified": contract_record_verified,
                    "contract_record_hash": contract_record_hash,
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
            "provenance_required": normalized.provenance is not None,
            "provenance_verified": provenance_verified,
            "contract_record_verified": contract_record_verified,
            "contract_record_hash": contract_record_hash,
        },
    )


__all__ = [
    "FRAME_DXF_DATUM",
    "FRAME_DXF_LAYERS",
    "FRAME_DXF_TOLERANCE_MM",
    "FRAME_DXF_UNIT",
    "FRAME_DXF_VERSION",
    "FRAME_XDATA_APP_ID",
    "FRAME_CONTRACT_RECORD_KEY",
    "FrameDxfGenerationError",
    "FrameDxfVerificationResult",
    "generate_frame_dxf",
    "verify_frame_dxf",
]

from __future__ import annotations

import base64
import math
import re
import uuid
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from ezdxf.lldxf.const import DXFError

from .artifacts import GeneratedDrawing, build_verified_bundle, generate_drawing, render_svg
from .core import (
    GeometryError,
    compute_contract_hash,
    expand_features,
    feature_geometry,
    get_numeric_path,
    normalize_to_mm,
    outline_geometry,
)
from .models import (
    ArtifactStatus,
    ContractStatus,
    ContractValidationResponse,
    DesignContract,
    ErrorInfo,
    Evidence,
    GenerationResponse,
    RunResponse,
    RunStatus,
    Violation,
)
from .repair import RepairRejected, apply_repair, compare_contracts, propose_repair
from .verifier import DxfReadError, VerificationResult, verify_dxf


@dataclass(frozen=True)
class ServiceFailure(Exception):
    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _correlation_id() -> str:
    return str(uuid.uuid4())


def _preview_or_empty(contract: DesignContract, contract_hash: str) -> str:
    try:
        return render_svg(contract, contract_hash)
    except (GeometryError, ValueError):
        return ""


def _geometry_preflight(contract: DesignContract) -> list[Violation]:
    violations: list[Violation] = []
    outline = outline_geometry(contract.outline)
    features = expand_features(contract)
    shapes = {feature.id: feature_geometry(feature) for feature in features}
    free_paths = {parameter.path for parameter in contract.free_parameters}

    edge_distance = 0.0
    for constraint in contract.constraints:
        if constraint.type in {"features_inside_outline", "minimum_edge_distance"}:
            edge_distance = max(
                edge_distance,
                float(constraint.parameters.get("minimum_edge_distance", 0.0)),
                float(constraint.parameters.get("target", 0.0)),
            )
    for feature_id, shape in shapes.items():
        inside = outline.covers(shape)
        distance = outline.boundary.distance(shape) if inside else -1.0
        if not inside or distance + 0.001 < edge_distance:
            repairable = any(path.startswith(f"features.{feature_id}.") for path in free_paths)
            violations.append(
                Violation(
                    code="DG_FEATURE_OUTSIDE_OUTLINE" if not inside else "DG_EDGE_DISTANCE",
                    message=(
                        "Feature가 outline 밖에 있습니다."
                        if not inside
                        else "Feature의 edge distance가 요구값보다 작습니다."
                    ),
                    entity_ids=[feature_id, contract.outline.id],
                    repairable=repairable,
                    details={
                        "actual_edge_distance": distance,
                        "required_edge_distance": edge_distance,
                    },
                )
            )

    ligament = contract.manufacturing_profile.minimum_ligament
    for constraint in contract.constraints:
        if constraint.type in {"non_overlap", "minimum_ligament"}:
            ligament = max(
                ligament,
                float(constraint.parameters.get("minimum_ligament", 0.0)),
                float(constraint.parameters.get("target", 0.0)),
            )
    for (first_id, first), (second_id, second) in combinations(shapes.items(), 2):
        actual = first.distance(second)
        if first.intersects(second) or actual + 0.001 < ligament:
            repairable = any(
                path.startswith(f"features.{feature_id}.")
                for feature_id in (first_id, second_id)
                for path in free_paths
            )
            violations.append(
                Violation(
                    code="DG_FEATURE_OVERLAP" if first.intersects(second) else "DG_LIGAMENT",
                    message=(
                        "Feature가 서로 겹칩니다."
                        if first.intersects(second)
                        else "Feature 사이 ligament가 요구값보다 작습니다."
                    ),
                    entity_ids=[first_id, second_id],
                    repairable=repairable,
                    details={
                        "actual_ligament": 0.0 if first.intersects(second) else actual,
                        "required_ligament": ligament,
                    },
                )
            )

    outline_center = outline.centroid
    for constraint in contract.constraints:
        if not constraint.required or constraint.type not in {
            "alignment",
            "equal_spacing",
            "symmetry",
        }:
            continue
        selected = [
            (feature_id, shapes[feature_id])
            for feature_id in constraint.entity_ids
            if feature_id in shapes
        ]
        repairable = any(
            path.startswith(f"features.{feature_id}.")
            for feature_id, _shape in selected
            for path in free_paths
        )
        axis = str(constraint.parameters.get("axis", "x")).lower()
        axis_index = 0 if axis == "x" else 1
        tolerance = float(constraint.parameters.get("tolerance", 0.001))
        centers = [
            (feature_id, (shape.centroid.x, shape.centroid.y)) for feature_id, shape in selected
        ]
        if constraint.type == "alignment" and len(centers) >= 2:
            values = [center[axis_index] for _feature_id, center in centers]
            target = constraint.parameters.get("axis_value")
            deviation = (
                max(abs(value - float(target)) for value in values)
                if isinstance(target, int | float)
                else max(values) - min(values)
            )
            if deviation > tolerance + 0.001:
                violations.append(
                    Violation(
                        code="DG_ALIGNMENT",
                        message="Feature 중심이 선언된 축 정렬 공차를 벗어났습니다.",
                        entity_ids=[feature_id for feature_id, _center in centers],
                        constraint_id=constraint.id,
                        repairable=repairable,
                        details={
                            "axis": axis,
                            "actual_spread": deviation,
                            "tolerance": tolerance,
                        },
                    )
                )
        elif constraint.type == "equal_spacing" and len(centers) >= 3:
            coordinates = sorted(center[axis_index] for _feature_id, center in centers)
            gaps = [
                second - first for first, second in zip(coordinates, coordinates[1:], strict=False)
            ]
            deviation = max(gaps) - min(gaps)
            if deviation > tolerance + 0.001:
                violations.append(
                    Violation(
                        code="DG_EQUAL_SPACING",
                        message="Feature 중심 간격이 동일 간격 공차를 벗어났습니다.",
                        entity_ids=[feature_id for feature_id, _center in centers],
                        constraint_id=constraint.id,
                        repairable=repairable,
                        details={"axis": axis, "gaps": gaps, "tolerance": tolerance},
                    )
                )
        elif constraint.type == "symmetry" and centers:
            default_axis_value = outline_center.x if axis_index == 0 else outline_center.y
            axis_value = float(constraint.parameters.get("axis_value", default_axis_value))
            unmatched: list[str] = []
            for feature_id, center in centers:
                reflected = list(center)
                reflected[axis_index] = axis_value * 2 - reflected[axis_index]
                nearest = min(
                    math.dist(reflected, candidate) for _candidate_id, candidate in centers
                )
                if nearest > tolerance + 0.001:
                    unmatched.append(feature_id)
            if unmatched:
                violations.append(
                    Violation(
                        code="DG_SYMMETRY",
                        message="Feature 배치가 선언된 대칭축 공차를 벗어났습니다.",
                        entity_ids=unmatched,
                        constraint_id=constraint.id,
                        repairable=repairable,
                        details={
                            "axis": axis,
                            "axis_value": axis_value,
                            "tolerance": tolerance,
                        },
                    )
                )
    return violations


def validate_contract(contract: DesignContract) -> ContractValidationResponse:
    normalized = normalize_to_mm(contract)
    contract_hash = compute_contract_hash(normalized)
    normalized = normalized.model_copy(update={"contract_hash": contract_hash})
    violations: list[Violation] = []
    status = ContractStatus.READY

    if contract.contract_hash and contract.contract_hash != contract_hash:
        violations.append(
            Violation(
                code="DG_CONTRACT_HASH_MISMATCH",
                message="제공된 contract_hash가 canonical contract와 일치하지 않습니다.",
                details={"provided": contract.contract_hash, "canonical": contract_hash},
            )
        )
        status = ContractStatus.INFEASIBLE

    if not normalized.manufacturing_profile.confirmed_by_user:
        violations.append(
            Violation(
                code="DG_NEEDS_CONFIRMATION",
                message="Manufacturing profile을 사용자가 확인해야 합니다.",
                details={"field": "manufacturing_profile.confirmed_by_user"},
            )
        )
        status = ContractStatus.NEEDS_CONFIRMATION

    entity_ids = {normalized.outline.id, *(feature.id for feature in normalized.features)}
    for constraint in normalized.constraints:
        missing = sorted(set(constraint.entity_ids) - entity_ids)
        if missing:
            violations.append(
                Violation(
                    code="DG_CONSTRAINT_ENTITY_MISSING",
                    message="Constraint가 존재하지 않는 entity ID를 참조합니다.",
                    constraint_id=constraint.id,
                    details={"missing_entity_ids": missing},
                )
            )
            status = ContractStatus.INFEASIBLE

    if not normalized.dimensions:
        violations.append(
            Violation(
                code="DG_CONTRACT_UNDER_CONSTRAINED",
                message="공식 생성에 필요한 dimension이 없습니다.",
                details={"required": "at least one explicit dimension"},
            )
        )
        if status == ContractStatus.READY:
            status = ContractStatus.UNDER_CONSTRAINED

    free_paths = {parameter.path for parameter in normalized.free_parameters}
    for dimension in normalized.dimensions:
        try:
            actual = get_numeric_path(normalized, dimension.path)
        except (KeyError, IndexError, AttributeError):
            violations.append(
                Violation(
                    code="DG_DIMENSION_PATH_INVALID",
                    message="Dimension path가 계약의 수치 필드를 가리키지 않습니다.",
                    details={"dimension_id": dimension.id, "path": dimension.path},
                )
            )
            status = ContractStatus.INFEASIBLE
            continue
        deviation = actual - dimension.target
        if dimension.locked and not (
            dimension.tolerance_lower - 0.001 <= deviation <= dimension.tolerance_upper + 0.001
        ):
            violations.append(
                Violation(
                    code="DG_CONTRACT_INFEASIBLE",
                    message="현재 형상과 locked dimension이 충돌합니다.",
                    details={
                        "dimension_id": dimension.id,
                        "path": dimension.path,
                        "target": dimension.target,
                        "actual": actual,
                    },
                )
            )
            status = ContractStatus.INFEASIBLE
        elif not dimension.locked and dimension.path not in free_paths:
            violations.append(
                Violation(
                    code="DG_CONTRACT_UNDER_CONSTRAINED",
                    message="Unlocked dimension에 대응하는 free parameter 범위가 없습니다.",
                    details={"dimension_id": dimension.id, "path": dimension.path},
                )
            )
            if status == ContractStatus.READY:
                status = ContractStatus.UNDER_CONSTRAINED

    for parameter in normalized.free_parameters:
        try:
            actual = get_numeric_path(normalized, parameter.path)
        except (KeyError, IndexError, AttributeError):
            violations.append(
                Violation(
                    code="DG_FREE_PARAMETER_PATH_INVALID",
                    message="Free parameter path가 계약의 수치 필드를 가리키지 않습니다.",
                    details={"parameter_id": parameter.id, "path": parameter.path},
                )
            )
            status = ContractStatus.INFEASIBLE
            continue
        if not parameter.minimum <= actual <= parameter.maximum:
            violations.append(
                Violation(
                    code="DG_FREE_PARAMETER_RANGE",
                    message="현재 값이 선언된 free parameter 범위 밖에 있습니다.",
                    repairable=True,
                    details={
                        "parameter_id": parameter.id,
                        "path": parameter.path,
                        "actual": actual,
                        "minimum": parameter.minimum,
                        "maximum": parameter.maximum,
                    },
                )
            )

    try:
        geometry_violations = _geometry_preflight(normalized)
        violations.extend(geometry_violations)
        if geometry_violations and any(not item.repairable for item in geometry_violations):
            status = ContractStatus.INFEASIBLE
    except GeometryError as exc:
        violations.append(
            Violation(
                code="DG_GEOMETRY_INVALID",
                message="Canonical geometry를 만들 수 없습니다.",
                details={"reason": str(exc)},
            )
        )
        status = ContractStatus.INFEASIBLE

    return ContractValidationResponse(
        status=status,
        contract_hash=contract_hash,
        violations=violations,
        evidence=[
            Evidence(
                type="contract_normalization",
                source="deterministic_core",
                details={"input_units": contract.units, "normalized_units": "mm"},
            )
        ],
        normalized_contract=normalized,
    )


def draft_contract(
    contract: DesignContract, intent_text: str | None = None
) -> ContractValidationResponse:
    result = validate_contract(contract)
    text = (intent_text or contract.intent_text or "").strip()
    ambiguous_tokens = [
        token
        for token in ("대략", "적당", "알아서", "정도", "about", "roughly", "approximately")
        if token.lower() in text.lower()
    ]
    numeric_mentions = re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?\s*(?:mm|cm|m|inch|in)?", text)
    if text and (ambiguous_tokens or numeric_mentions):
        result.status = ContractStatus.NEEDS_CONFIRMATION
        result.violations.append(
            Violation(
                code="DG_NEEDS_CONFIRMATION",
                message="자연어 조건은 수치·단위를 폼 필드에 확정한 뒤 적용할 수 있습니다.",
                details={
                    "ambiguous_tokens": ambiguous_tokens,
                    "numeric_mentions": numeric_mentions,
                    "action": "Confirm values in structured form; no values were inferred.",
                },
            )
        )
    result.evidence.append(
        Evidence(
            type="intent_boundary",
            source="requirements_compiler_guard",
            details={"geometry_modified": False, "text_present": bool(text)},
        )
    )
    return result


def generate_only(contract: DesignContract) -> GenerationResponse:
    validation = validate_contract(contract)
    if validation.status != ContractStatus.READY or validation.normalized_contract is None:
        raise ServiceFailure(
            "DG_CONTRACT_INFEASIBLE"
            if validation.status == ContractStatus.INFEASIBLE
            else "DG_CONTRACT_UNDER_CONSTRAINED",
            "Contract가 drawing generation 준비 상태가 아닙니다.",
            {
                "status": validation.status.value,
                "violations": [v.model_dump() for v in validation.violations],
            },
        )
    drawing = generate_drawing(validation.normalized_contract, validation.contract_hash)
    return GenerationResponse(
        status=ArtifactStatus.GENERATED_UNVERIFIED,
        contract_hash=drawing.contract_hash,
        artifact_hash=drawing.artifact_hash,
        preview_svg=drawing.preview_svg,
        dxf_base64=base64.b64encode(drawing.dxf_bytes).decode("ascii"),
        evidence=validation.evidence,
    )


def verify_only(
    contract: DesignContract,
    dxf_bytes: bytes,
) -> VerificationResult:
    validation = validate_contract(contract)
    if validation.normalized_contract is None:
        raise ServiceFailure("DG_INPUT_INVALID", "Contract normalization failed.", {})
    try:
        return verify_dxf(
            validation.normalized_contract,
            dxf_bytes,
            validation.contract_hash,
        )
    except DxfReadError as exc:
        raise ServiceFailure("DG_DXF_READ_FAILED", "DXF를 독립 재읽기할 수 없습니다.", {}) from exc


def _failure_response(
    contract: DesignContract,
    validation: ContractValidationResponse,
) -> RunResponse:
    status_to_code = {
        ContractStatus.NEEDS_CONFIRMATION: "DG_NEEDS_CONFIRMATION",
        ContractStatus.UNDER_CONSTRAINED: "DG_CONTRACT_UNDER_CONSTRAINED",
        ContractStatus.INFEASIBLE: "DG_CONTRACT_INFEASIBLE",
    }
    code = status_to_code.get(validation.status, "DG_VERIFICATION_FAILED")
    normalized = validation.normalized_contract or contract
    return RunResponse(
        status=RunStatus.FAILED,
        contract_hash=validation.contract_hash,
        preview_svg=_preview_or_empty(normalized, validation.contract_hash),
        violations=validation.violations,
        evidence=validation.evidence,
        error=ErrorInfo(
            code=code,
            message="공식 도면 생성 조건을 충족하지 못했습니다.",
            details={"contract_status": validation.status.value},
            correlation_id=_correlation_id(),
        ),
    )


def run_design(contract: DesignContract, *, auto_repair: bool = True) -> RunResponse:
    validation = validate_contract(contract)
    if validation.status != ContractStatus.READY or validation.normalized_contract is None:
        return _failure_response(contract, validation)

    current = validation.normalized_contract
    drawing: GeneratedDrawing
    verification: VerificationResult
    history: list[dict[str, Any]] = []
    try:
        drawing = generate_drawing(current, validation.contract_hash)
        verification = verify_dxf(current, drawing.dxf_bytes, validation.contract_hash)
    except GeometryError as exc:
        return RunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            preview_svg="",
            violations=[
                Violation(
                    code="DG_GEOMETRY_INVALID",
                    message="도면 형상을 생성할 수 없습니다.",
                    details={"reason": str(exc)},
                )
            ],
            error=ErrorInfo(
                code="DG_GEOMETRY_INVALID",
                message="도면 형상을 생성할 수 없습니다.",
                details={"reason": str(exc)},
                correlation_id=_correlation_id(),
            ),
        )
    except (DxfReadError, DXFError) as exc:
        return RunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            preview_svg="",
            violations=[Violation(code="DG_DXF_READ_FAILED", message=str(exc))],
            error=ErrorInfo(
                code="DG_DXF_READ_FAILED",
                message="생성된 DXF를 독립 재읽기할 수 없습니다.",
                details={},
                correlation_id=_correlation_id(),
            ),
        )

    if auto_repair and verification.status == RunStatus.REPAIRABLE:
        for iteration in range(1, 4):
            proposal = propose_repair(current, verification.violations, iteration=iteration)
            history.append(proposal.model_dump(mode="json"))
            if proposal.status != "proposed":
                break
            try:
                current = apply_repair(current, proposal)
            except RepairRejected:
                break
            current_hash = compute_contract_hash(current)
            current = current.model_copy(update={"contract_hash": current_hash})
            drawing = generate_drawing(current, current_hash)
            verification = verify_dxf(current, drawing.dxf_bytes, current_hash)
            if verification.status == RunStatus.PASSED:
                break
        if verification.status != RunStatus.PASSED and history:
            verification = VerificationResult(
                status=RunStatus.REPAIR_EXHAUSTED,
                contract_hash=verification.contract_hash,
                artifact_hash=verification.artifact_hash,
                measurements=verification.measurements,
                violations=verification.violations,
                evidence=verification.evidence,
            )

    bundle_base64: str | None = None
    if verification.status == RunStatus.PASSED:
        bundle = build_verified_bundle(
            current,
            contract_hash=verification.contract_hash,
            artifact_hash=verification.artifact_hash,
            dxf_bytes=drawing.dxf_bytes,
            preview_svg=drawing.preview_svg,
            verification=verification.as_dict(),
            repair_history=history,
        )
        bundle_base64 = base64.b64encode(bundle).decode("ascii")

    evidence = list(verification.evidence)
    if history:
        evidence.append(
            Evidence(
                type="repair_history",
                source="bounded_cp_sat",
                details={"iterations": len(history), "locked_changes": 0},
            )
        )
    error: ErrorInfo | None = None
    if verification.status != RunStatus.PASSED:
        error = ErrorInfo(
            code=(
                "DG_REPAIR_EXHAUSTED"
                if verification.status == RunStatus.REPAIR_EXHAUSTED
                else "DG_VERIFICATION_FAILED"
            ),
            message="DXF 독립 검증을 통과하지 못해 공식 bundle을 생성하지 않았습니다.",
            details={"official_export_created": False},
            correlation_id=_correlation_id(),
        )
    return RunResponse(
        status=verification.status,
        contract_hash=verification.contract_hash,
        artifact_hash=verification.artifact_hash,
        measurements=verification.measurements,
        violations=verification.violations,
        evidence=evidence,
        preview_svg=drawing.preview_svg,
        bundle_base64=bundle_base64,
        error=error,
    )


__all__ = [
    "ServiceFailure",
    "apply_repair",
    "compare_contracts",
    "draft_contract",
    "generate_only",
    "propose_repair",
    "run_design",
    "validate_contract",
    "verify_only",
]

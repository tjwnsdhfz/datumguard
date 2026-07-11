from __future__ import annotations

import base64
import uuid
from typing import Any

from .models import ContractStatus, ErrorInfo, Evidence, RunStatus, Violation
from .piping_artifacts import (
    build_verified_piping_bundle,
    generate_piping_drawing,
    render_piping_svg,
)
from .piping_core import (
    PipingGeometryError,
    compute_piping_hash,
    get_piping_numeric_path,
    normalize_piping_to_mm,
    piping_geometry_map,
)
from .piping_models import (
    PipingContractValidationResponse,
    PipingGenerationResponse,
    PipingPlanContract,
    PipingRunResponse,
)
from .piping_verifier import (
    PipingDxfReadError,
    PipingVerificationResult,
    verify_piping_dxf,
)
from .service import ServiceFailure


def _correlation_id() -> str:
    return str(uuid.uuid4())


def validate_piping_contract(
    contract: PipingPlanContract,
) -> PipingContractValidationResponse:
    normalized = normalize_piping_to_mm(contract)
    contract_hash = compute_piping_hash(normalized)
    normalized = normalized.model_copy(update={"contract_hash": contract_hash})
    violations: list[Violation] = []
    status = ContractStatus.READY

    if contract.contract_hash and contract.contract_hash != contract_hash:
        violations.append(
            Violation(
                code="DG_CONTRACT_HASH_MISMATCH",
                message="The supplied piping contract hash differs from its canonical hash.",
                details={"provided": contract.contract_hash, "canonical": contract_hash},
            )
        )
        status = ContractStatus.INFEASIBLE

    entity_ids = {
        *(item.id for item in normalized.nodes),
        *(item.id for item in normalized.segments),
        *(item.id for item in normalized.components),
        *(item.id for item in normalized.supports),
        *(item.id for item in normalized.equipment_zones),
    }
    for constraint in normalized.constraints:
        missing = sorted(set(constraint.entity_ids) - entity_ids)
        if missing:
            violations.append(
                Violation(
                    code="DG_PIPE_CONSTRAINT_ENTITY_MISSING",
                    message="A piping constraint references unknown entities.",
                    constraint_id=constraint.id,
                    details={"missing_entity_ids": missing},
                )
            )
            status = ContractStatus.INFEASIBLE
        if constraint.type in {
            "orthogonal",
            "endpoint_alignment",
            "inline_component_position",
        }:
            tolerance = constraint.parameters.get("tolerance", 0.001)
            if not isinstance(tolerance, int | float) or float(tolerance) < 0:
                violations.append(
                    Violation(
                        code="DG_PIPE_CONSTRAINT_PARAMETER_INVALID",
                        message="A piping geometry tolerance must be a non-negative number.",
                        constraint_id=constraint.id,
                        details={"parameter": "tolerance"},
                    )
                )
                status = ContractStatus.INFEASIBLE
        elif constraint.type == "maximum_support_spacing":
            maximum = constraint.parameters.get(
                "maximum_spacing", constraint.parameters.get("max_support_spacing")
            )
            if not isinstance(maximum, int | float) or float(maximum) <= 0:
                violations.append(
                    Violation(
                        code="DG_PIPE_CONSTRAINT_PARAMETER_INVALID",
                        message="Maximum support spacing must be a positive number.",
                        constraint_id=constraint.id,
                        details={"parameter": "maximum_spacing"},
                    )
                )
                status = ContractStatus.INFEASIBLE
        elif constraint.type == "minimum_obstacle_clearance":
            clearance = constraint.parameters.get("minimum_clearance")
            if not isinstance(clearance, int | float) or float(clearance) < 0:
                violations.append(
                    Violation(
                        code="DG_PIPE_CONSTRAINT_PARAMETER_INVALID",
                        message="Minimum obstacle clearance must be a non-negative number.",
                        constraint_id=constraint.id,
                        details={"parameter": "minimum_clearance"},
                    )
                )
                status = ContractStatus.INFEASIBLE

    constraint_types = {item.type for item in normalized.constraints if item.required}
    if "maximum_support_spacing" not in constraint_types:
        violations.append(
            Violation(
                code="DG_CONTRACT_UNDER_CONSTRAINED",
                message="A required maximum_support_spacing constraint is missing.",
            )
        )
        if status == ContractStatus.READY:
            status = ContractStatus.UNDER_CONSTRAINED
    if normalized.equipment_zones and "minimum_obstacle_clearance" not in constraint_types:
        violations.append(
            Violation(
                code="DG_CONTRACT_UNDER_CONSTRAINED",
                message="A required minimum_obstacle_clearance constraint is missing.",
            )
        )
        if status == ContractStatus.READY:
            status = ContractStatus.UNDER_CONSTRAINED

    free_paths = {parameter.path for parameter in normalized.free_parameters}
    for dimension in normalized.dimensions:
        try:
            actual = get_piping_numeric_path(normalized, dimension.path)
        except (KeyError, IndexError, AttributeError):
            violations.append(
                Violation(
                    code="DG_PIPE_DIMENSION_PATH_INVALID",
                    message="A piping dimension path does not identify a numeric field.",
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
                    code="DG_PIPE_LOCKED_DIMENSION_CONFLICT",
                    message="Current piping geometry conflicts with a locked dimension.",
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
                    message="An unlocked piping dimension has no matching free parameter.",
                    details={"dimension_id": dimension.id, "path": dimension.path},
                )
            )
            if status == ContractStatus.READY:
                status = ContractStatus.UNDER_CONSTRAINED

    for parameter in normalized.free_parameters:
        try:
            actual = get_piping_numeric_path(normalized, parameter.path)
        except (KeyError, IndexError, AttributeError):
            violations.append(
                Violation(
                    code="DG_PIPE_FREE_PARAMETER_PATH_INVALID",
                    message="A piping free-parameter path does not identify a numeric field.",
                    details={"parameter_id": parameter.id, "path": parameter.path},
                )
            )
            status = ContractStatus.INFEASIBLE
            continue
        if not parameter.minimum <= actual <= parameter.maximum:
            violations.append(
                Violation(
                    code="DG_PIPE_FREE_PARAMETER_RANGE",
                    message="The current piping free-parameter value is outside its range.",
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
        piping_geometry_map(normalized)
    except PipingGeometryError as exc:
        violations.append(
            Violation(
                code="DG_PIPE_GEOMETRY_INVALID",
                message="Native piping geometry cannot be constructed.",
                details={"reason": str(exc)},
            )
        )
        status = ContractStatus.INFEASIBLE

    return PipingContractValidationResponse(
        status=status,
        contract_hash=contract_hash,
        violations=violations,
        evidence=[
            Evidence(
                type="piping_contract_normalization",
                source="deterministic_piping_core",
                details={
                    "input_units": contract.units,
                    "normalized_units": "mm",
                    "design_kind": "piping_plan",
                },
            )
        ],
        normalized_contract=normalized,
    )


def generate_piping_only(contract: PipingPlanContract) -> PipingGenerationResponse:
    validation = validate_piping_contract(contract)
    if validation.status != ContractStatus.READY or validation.normalized_contract is None:
        raise ServiceFailure(
            "DG_PIPE_CONTRACT_INFEASIBLE",
            "PipingPlanContract is not ready for drawing generation.",
            {
                "status": validation.status.value,
                "violations": [item.model_dump(mode="json") for item in validation.violations],
            },
        )
    drawing = generate_piping_drawing(validation.normalized_contract, validation.contract_hash)
    return PipingGenerationResponse(
        contract_hash=drawing.contract_hash,
        artifact_hash=drawing.artifact_hash,
        preview_svg=drawing.preview_svg,
        dxf_base64=base64.b64encode(drawing.dxf_bytes).decode("ascii"),
        evidence=validation.evidence,
    )


def verify_piping_only(
    contract: PipingPlanContract,
    dxf_bytes: bytes,
) -> PipingVerificationResult:
    validation = validate_piping_contract(contract)
    if validation.normalized_contract is None:
        raise ServiceFailure("DG_INPUT_INVALID", "Piping normalization failed.", {})
    try:
        return verify_piping_dxf(
            validation.normalized_contract,
            dxf_bytes,
            validation.contract_hash,
        )
    except PipingDxfReadError as exc:
        raise ServiceFailure(
            "DG_PIPE_DXF_READ_FAILED",
            "The piping DXF cannot be independently parsed.",
            {},
        ) from exc


def _summary(contract: PipingPlanContract) -> dict[str, Any]:
    return {
        "design_kind": "piping_plan",
        "summary_source": "normalized_contract_preview",
        "nodes": len(contract.nodes),
        "segments": len(contract.segments),
        "components": len(contract.components),
        "supports": len(contract.supports),
        "equipment_zones": len(contract.equipment_zones),
        "dimensions": len(contract.dimensions),
    }


def run_piping_design(contract: PipingPlanContract) -> PipingRunResponse:
    validation = validate_piping_contract(contract)
    timeline: list[dict[str, Any]] = [
        {"stage": "contract_validation", "status": validation.status.value}
    ]
    if validation.status != ContractStatus.READY or validation.normalized_contract is None:
        normalized = validation.normalized_contract or contract
        preview = ""
        try:
            preview = render_piping_svg(normalized, validation.contract_hash)
        except PipingGeometryError:
            pass
        return PipingRunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            preview_svg=preview,
            violations=validation.violations,
            evidence=validation.evidence,
            summary=_summary(normalized),
            timeline=timeline,
            error=ErrorInfo(
                code="DG_PIPE_CONTRACT_INFEASIBLE",
                message="Official piping drawing generation requirements were not met.",
                details={"contract_status": validation.status.value},
                correlation_id=_correlation_id(),
            ),
        )

    normalized = validation.normalized_contract
    try:
        drawing = generate_piping_drawing(normalized, validation.contract_hash)
        timeline.append({"stage": "dxf_generation", "status": "generated_unverified"})
        verification = verify_piping_dxf(
            normalized,
            drawing.dxf_bytes,
            validation.contract_hash,
        )
        timeline.append(
            {"stage": "independent_dxf_verification", "status": verification.status.value}
        )
    except (PipingGeometryError, PipingDxfReadError) as exc:
        return PipingRunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            preview_svg="",
            violations=[
                Violation(
                    code="DG_PIPE_DXF_PIPELINE_FAILED",
                    message="Piping DXF generation or independent parsing failed.",
                    details={"reason": str(exc)},
                )
            ],
            evidence=validation.evidence,
            summary=_summary(normalized),
            timeline=timeline,
            error=ErrorInfo(
                code="DG_PIPE_DXF_PIPELINE_FAILED",
                message="The piping DXF pipeline did not complete.",
                details={"reason": str(exc)},
                correlation_id=_correlation_id(),
            ),
        )

    bundle_base64: str | None = None
    if verification.status == RunStatus.PASSED:
        bundle = build_verified_piping_bundle(
            normalized,
            contract_hash=verification.contract_hash,
            artifact_hash=verification.artifact_hash,
            dxf_bytes=drawing.dxf_bytes,
            preview_svg=drawing.preview_svg,
            verification=verification.as_dict(),
        )
        bundle_base64 = base64.b64encode(bundle).decode("ascii")
        timeline.append({"stage": "official_bundle", "status": "created"})
    else:
        timeline.append({"stage": "official_bundle", "status": "blocked"})

    error = None
    if verification.status != RunStatus.PASSED:
        error = ErrorInfo(
            code="DG_PIPE_VERIFICATION_FAILED",
            message="Independent DXF verification blocked the official piping bundle.",
            details={"official_export_created": False},
            correlation_id=_correlation_id(),
        )
    return PipingRunResponse(
        status=verification.status,
        contract_hash=verification.contract_hash,
        artifact_hash=verification.artifact_hash,
        measurements=verification.measurements,
        violations=verification.violations,
        evidence=[*validation.evidence, *verification.evidence],
        preview_svg=drawing.preview_svg,
        bundle_base64=bundle_base64,
        summary=verification.summary,
        timeline=timeline,
        error=error,
    )


__all__ = [
    "generate_piping_only",
    "run_piping_design",
    "validate_piping_contract",
    "verify_piping_only",
]

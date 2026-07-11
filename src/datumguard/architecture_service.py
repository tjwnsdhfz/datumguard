from __future__ import annotations

import base64
import hashlib
import json
import math
import uuid
from typing import Any, Literal

from ortools.sat.python import cp_model

from .architecture_artifacts import (
    build_verified_architecture_bundle,
    generate_architecture_drawing,
    render_architecture_svg,
)
from .architecture_core import (
    ArchitecturalGeometryError,
    architecture_geometry_map,
    compute_architecture_hash,
    get_architecture_numeric_path,
    normalize_architecture_to_mm,
)
from .architecture_models import (
    ArchitecturalContractValidationResponse,
    ArchitecturalGenerationResponse,
    ArchitecturalPlanContract,
    ArchitecturalRunResponse,
)
from .architecture_verifier import (
    ArchitecturalDxfReadError,
    ArchitecturalVerificationResult,
    verify_architecture_dxf,
)
from .models import (
    ContractStatus,
    ErrorInfo,
    Evidence,
    RepairChange,
    RepairProposal,
    RunStatus,
    Violation,
)
from .repair import RepairRejected
from .service import ServiceFailure


def _correlation_id() -> str:
    return str(uuid.uuid4())


def validate_architecture_contract(
    contract: ArchitecturalPlanContract,
) -> ArchitecturalContractValidationResponse:
    normalized = normalize_architecture_to_mm(contract)
    contract_hash = compute_architecture_hash(normalized)
    normalized = normalized.model_copy(update={"contract_hash": contract_hash})
    violations: list[Violation] = []
    status = ContractStatus.READY

    if contract.contract_hash and contract.contract_hash != contract_hash:
        violations.append(
            Violation(
                code="DG_CONTRACT_HASH_MISMATCH",
                message="제공된 architectural contract hash가 canonical hash와 다릅니다.",
                details={"provided": contract.contract_hash, "canonical": contract_hash},
            )
        )
        status = ContractStatus.INFEASIBLE

    entity_ids = {
        *(item.id for item in normalized.grids),
        *(item.id for item in normalized.walls),
        *(item.id for item in normalized.openings),
        *(item.id for item in normalized.columns),
        *(item.id for item in normalized.room_seeds),
    }
    for constraint in normalized.constraints:
        missing = sorted(set(constraint.entity_ids) - entity_ids)
        if missing:
            violations.append(
                Violation(
                    code="DG_ARCH_CONSTRAINT_ENTITY_MISSING",
                    message="Architecture constraint가 존재하지 않는 entity를 참조합니다.",
                    constraint_id=constraint.id,
                    details={"missing_entity_ids": missing},
                )
            )
            status = ContractStatus.INFEASIBLE

    free_paths = {parameter.path for parameter in normalized.free_parameters}
    for dimension in normalized.dimensions:
        try:
            actual = get_architecture_numeric_path(normalized, dimension.path)
        except (KeyError, IndexError, AttributeError):
            violations.append(
                Violation(
                    code="DG_ARCH_DIMENSION_PATH_INVALID",
                    message="Architecture dimension path가 수치 필드를 가리키지 않습니다.",
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
                    code="DG_ARCH_LOCKED_DIMENSION_CONFLICT",
                    message="현재 geometry와 locked architecture dimension이 충돌합니다.",
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
                    message="Unlocked architecture dimension에 free parameter가 없습니다.",
                    details={"dimension_id": dimension.id, "path": dimension.path},
                )
            )
            if status == ContractStatus.READY:
                status = ContractStatus.UNDER_CONSTRAINED

    for parameter in normalized.free_parameters:
        try:
            actual = get_architecture_numeric_path(normalized, parameter.path)
        except (KeyError, IndexError, AttributeError):
            violations.append(
                Violation(
                    code="DG_ARCH_FREE_PARAMETER_PATH_INVALID",
                    message="Architecture free parameter path가 수치 필드를 가리키지 않습니다.",
                    details={"parameter_id": parameter.id, "path": parameter.path},
                )
            )
            status = ContractStatus.INFEASIBLE
            continue
        if not parameter.minimum <= actual <= parameter.maximum:
            violations.append(
                Violation(
                    code="DG_ARCH_FREE_PARAMETER_RANGE",
                    message="Architecture free parameter 현재 값이 범위 밖입니다.",
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
        architecture_geometry_map(normalized)
    except ArchitecturalGeometryError as exc:
        violations.append(
            Violation(
                code="DG_ARCH_GEOMETRY_INVALID",
                message="Native architecture geometry를 만들 수 없습니다.",
                details={"reason": str(exc)},
            )
        )
        status = ContractStatus.INFEASIBLE

    return ArchitecturalContractValidationResponse(
        status=status,
        contract_hash=contract_hash,
        violations=violations,
        evidence=[
            Evidence(
                type="architectural_contract_normalization",
                source="deterministic_architecture_core",
                details={
                    "input_units": contract.units,
                    "normalized_units": "mm",
                    "design_kind": "architectural_plan",
                },
            )
        ],
        normalized_contract=normalized,
    )


def generate_architecture_only(
    contract: ArchitecturalPlanContract,
) -> ArchitecturalGenerationResponse:
    validation = validate_architecture_contract(contract)
    if validation.status != ContractStatus.READY or validation.normalized_contract is None:
        raise ServiceFailure(
            "DG_ARCH_CONTRACT_INFEASIBLE",
            "ArchitecturalPlanContract가 drawing generation 준비 상태가 아닙니다.",
            {
                "status": validation.status.value,
                "violations": [item.model_dump(mode="json") for item in validation.violations],
            },
        )
    drawing = generate_architecture_drawing(
        validation.normalized_contract,
        validation.contract_hash,
    )
    return ArchitecturalGenerationResponse(
        contract_hash=drawing.contract_hash,
        artifact_hash=drawing.artifact_hash,
        preview_svg=drawing.preview_svg,
        dxf_base64=base64.b64encode(drawing.dxf_bytes).decode("ascii"),
        evidence=validation.evidence,
    )


def verify_architecture_only(
    contract: ArchitecturalPlanContract,
    dxf_bytes: bytes,
) -> ArchitecturalVerificationResult:
    validation = validate_architecture_contract(contract)
    if validation.normalized_contract is None:
        raise ServiceFailure("DG_INPUT_INVALID", "Architecture normalization failed.", {})
    try:
        return verify_architecture_dxf(
            validation.normalized_contract,
            dxf_bytes,
            validation.contract_hash,
        )
    except ArchitecturalDxfReadError as exc:
        raise ServiceFailure(
            "DG_ARCH_DXF_READ_FAILED",
            "건축 DXF를 독립 재읽기할 수 없습니다.",
            {},
        ) from exc


def _summary(contract: ArchitecturalPlanContract) -> dict[str, Any]:
    return {
        "design_kind": "architectural_plan",
        "summary_source": "normalized_contract_preview",
        "grids": len(contract.grids),
        "walls": len(contract.walls),
        "openings": len(contract.openings),
        "columns": len(contract.columns),
        "rooms": len(contract.room_seeds),
        "dimensions": len(contract.dimensions),
    }


def _run_architecture_design_legacy(
    contract: ArchitecturalPlanContract,
) -> ArchitecturalRunResponse:
    validation = validate_architecture_contract(contract)
    timeline: list[dict[str, Any]] = [
        {"stage": "contract_validation", "status": validation.status.value}
    ]
    if validation.status != ContractStatus.READY or validation.normalized_contract is None:
        normalized = validation.normalized_contract or contract
        preview = ""
        try:
            preview = render_architecture_svg(normalized, validation.contract_hash)
        except ArchitecturalGeometryError:
            pass
        return ArchitecturalRunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            preview_svg=preview,
            violations=validation.violations,
            evidence=validation.evidence,
            summary=_summary(normalized),
            timeline=timeline,
            error=ErrorInfo(
                code="DG_ARCH_CONTRACT_INFEASIBLE",
                message="공식 건축 도면 생성 조건을 충족하지 못했습니다.",
                details={"contract_status": validation.status.value},
                correlation_id=_correlation_id(),
            ),
        )

    normalized = validation.normalized_contract
    try:
        drawing = generate_architecture_drawing(normalized, validation.contract_hash)
        timeline.append({"stage": "dxf_generation", "status": "generated_unverified"})
        verification = verify_architecture_dxf(
            normalized,
            drawing.dxf_bytes,
            validation.contract_hash,
        )
        timeline.append(
            {"stage": "independent_dxf_verification", "status": verification.status.value}
        )
    except (ArchitecturalGeometryError, ArchitecturalDxfReadError) as exc:
        return ArchitecturalRunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            preview_svg="",
            violations=[
                Violation(
                    code="DG_ARCH_DXF_PIPELINE_FAILED",
                    message="건축 DXF 생성 또는 독립 검증에 실패했습니다.",
                    details={"reason": str(exc)},
                )
            ],
            evidence=validation.evidence,
            summary=_summary(normalized),
            timeline=timeline,
            error=ErrorInfo(
                code="DG_ARCH_DXF_PIPELINE_FAILED",
                message="건축 DXF pipeline을 완료하지 못했습니다.",
                details={"reason": str(exc)},
                correlation_id=_correlation_id(),
            ),
        )

    bundle_base64: str | None = None
    if verification.status == RunStatus.PASSED:
        bundle = build_verified_architecture_bundle(
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
            code="DG_ARCH_VERIFICATION_FAILED",
            message="독립 DXF 검증을 통과하지 못해 공식 건축 bundle을 만들지 않았습니다.",
            details={"official_export_created": False},
            correlation_id=_correlation_id(),
        )
    return ArchitecturalRunResponse(
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


def _supported_repair_paths(
    contract: ArchitecturalPlanContract,
    violation: Violation,
) -> list[str]:
    if violation.code == "DG_ARCH_COLUMN_OFF_GRID":
        return [
            path
            for entity_id in violation.entity_ids
            for path in (
                f"columns.{entity_id}.center.0",
                f"columns.{entity_id}.center.1",
            )
            if any(column.id == entity_id for column in contract.columns)
        ]
    if violation.code in {"DG_ARCH_OPENING_OUTSIDE_HOST", "DG_ARCH_OPENING_OVERLAP"}:
        return [
            f"openings.{entity_id}.offset"
            for entity_id in violation.entity_ids
            if any(opening.id == entity_id for opening in contract.openings)
        ]
    if violation.code == "DG_ARCH_DIMENSION_OUT_OF_TOLERANCE":
        path = violation.details.get("path")
        if not isinstance(path, str):
            return []
        parts = path.split(".")
        supported = (
            len(parts) == 4
            and parts[0] == "columns"
            and parts[2] == "center"
            and parts[3] in {"0", "1"}
        ) or (len(parts) == 3 and parts[0] == "openings" and parts[2] == "offset")
        return [path] if supported else []
    return []


def _opening_target(contract: ArchitecturalPlanContract, opening_id: str) -> float | None:
    opening = next((item for item in contract.openings if item.id == opening_id), None)
    if opening is None:
        return None
    wall = next(item for item in contract.walls if item.id == opening.wall_id)
    wall_length = math.dist(wall.start, wall.end)
    maximum = max(wall_length - opening.width, 0.0)
    candidates = [0.0, maximum]
    others = [
        item
        for item in contract.openings
        if item.wall_id == opening.wall_id and item.id != opening.id
    ]
    for other in others:
        candidates.extend([other.offset + other.width, other.offset - opening.width])

    def valid(candidate: float) -> bool:
        if not 0.0 <= candidate <= maximum:
            return False
        return all(
            min(candidate + opening.width, other.offset + other.width)
            - max(candidate, other.offset)
            <= 0.001
            for other in others
        )

    valid_candidates = [candidate for candidate in candidates if valid(candidate)]
    if not valid_candidates:
        return min(max(opening.offset, 0.0), maximum)
    return min(valid_candidates, key=lambda candidate: abs(candidate - opening.offset))


def _desired_repair_value(
    contract: ArchitecturalPlanContract,
    path: str,
    violation: Violation,
) -> float | None:
    if path.startswith("columns."):
        coordinate_index = int(path.rsplit(".", 1)[1])
        axis = "x" if coordinate_index == 0 else "y"
        offsets = [
            grid.offset for grid in contract.grids if grid.axis == axis and grid.offset is not None
        ]
        if not offsets:
            offsets = [
                grid.start[coordinate_index]
                for grid in contract.grids
                if abs(grid.start[coordinate_index] - grid.end[coordinate_index]) <= 0.001
            ]
        if not offsets:
            return None
        current = get_architecture_numeric_path(contract, path)
        return min(offsets, key=lambda value: abs(value - current))
    if path.startswith("openings."):
        return _opening_target(contract, path.split(".")[1])
    if violation.code == "DG_ARCH_DIMENSION_OUT_OF_TOLERANCE":
        dimension_id = violation.details.get("dimension_id")
        dimension = next(
            (item for item in contract.dimensions if item.id == dimension_id),
            None,
        )
        return dimension.target if dimension is not None else None
    return None


def _bounded_free_value(
    minimum: float,
    maximum: float,
    step: float,
    desired: float,
) -> float | None:
    microns_per_mm = 1000
    minimum_um = int(round(minimum * microns_per_mm))
    maximum_um = int(round(maximum * microns_per_mm))
    desired_um = int(round(desired * microns_per_mm))
    step_um = max(int(round(step * microns_per_mm)), 1)
    count = max((maximum_um - minimum_um) // step_um, 0)
    model = cp_model.CpModel()
    index = model.new_int_var(0, count, "architecture_step_index")
    value = model.new_int_var(minimum_um, minimum_um + count * step_um, "architecture_value_um")
    model.add(value == minimum_um + index * step_um)
    distance_bound = max(abs(desired_um - minimum_um), abs(desired_um - maximum_um)) + step_um
    distance = model.new_int_var(0, max(distance_bound, 1), "architecture_distance_um")
    model.add_abs_equality(distance, value - desired_um)
    model.minimize(distance)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 0.25
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return None
    return solver.value(value) / microns_per_mm


def _set_architecture_numeric_path(
    contract: ArchitecturalPlanContract,
    path: str,
    value: float,
) -> ArchitecturalPlanContract:
    data = contract.model_dump(mode="python")
    collection, entity_id, attribute, *remainder = path.split(".")
    if collection not in {"columns", "openings"}:
        raise KeyError(path)
    item = next(candidate for candidate in data[collection] if candidate["id"] == entity_id)
    if attribute == "center" and len(remainder) == 1:
        center = list(item["center"])
        center[int(remainder[0])] = value
        item["center"] = center
    elif attribute == "offset" and not remainder:
        item["offset"] = value
    else:
        raise KeyError(path)
    data["contract_hash"] = None
    return ArchitecturalPlanContract.model_validate(data)


def _next_architecture_repair(
    contract: ArchitecturalPlanContract,
    violations: list[Violation],
    *,
    iteration: int,
) -> tuple[ArchitecturalPlanContract | None, dict[str, Any] | None, Violation | None]:
    free_parameters = {item.path: item for item in contract.free_parameters}
    locked_paths = {item.path for item in contract.dimensions if item.locked}
    supported_paths = [
        path for violation in violations for path in _supported_repair_paths(contract, violation)
    ]
    if not supported_paths:
        return None, None, None
    locked = sorted(set(supported_paths) & locked_paths)
    if locked:
        return (
            None,
            None,
            Violation(
                code="DG_ARCH_REPAIR_LOCKED",
                message="Architecture auto-repair cannot change a locked dimension path.",
                details={"paths": locked, "iteration": iteration},
            ),
        )
    declared = [path for path in supported_paths if path in free_parameters]
    if not declared:
        return (
            None,
            None,
            Violation(
                code="DG_ARCH_REPAIR_NO_FREE_PARAMETER",
                message="No declared architecture free parameter permits this repair.",
                details={"paths": sorted(set(supported_paths)), "iteration": iteration},
            ),
        )
    for violation in violations:
        for path in _supported_repair_paths(contract, violation):
            parameter = free_parameters.get(path)
            if parameter is None:
                continue
            desired = _desired_repair_value(contract, path, violation)
            if desired is None:
                continue
            before = get_architecture_numeric_path(contract, path)
            after = _bounded_free_value(
                parameter.minimum,
                parameter.maximum,
                parameter.step,
                desired,
            )
            if after is None:
                continue
            if abs(after - before) <= 0.001:
                continue
            repaired = _set_architecture_numeric_path(contract, path, after)
            return (
                repaired,
                {
                    "iteration": iteration,
                    "path": path,
                    "before": before,
                    "after": after,
                    "violation_code": violation.code,
                    "solver": "ortools_cp_sat",
                },
                None,
            )
    return (
        None,
        None,
        Violation(
            code="DG_ARCH_REPAIR_EXHAUSTED",
            message="Declared architecture repair bounds cannot resolve the violation.",
            details={"iteration": iteration},
        ),
    )


def _is_architecture_repair_path(path: str) -> bool:
    parts = path.split(".")
    return (
        len(parts) == 4
        and parts[0] == "columns"
        and parts[2] == "center"
        and parts[3] in {"0", "1"}
    ) or (len(parts) == 3 and parts[0] == "openings" and parts[2] == "offset")


def propose_architecture_repair(
    contract: ArchitecturalPlanContract,
    violations: list[Violation],
    *,
    iteration: int = 1,
) -> RepairProposal:
    """Create one bounded CP-SAT proposal for an explicitly declared free parameter."""
    if iteration < 1:
        raise ValueError("architecture repair iteration must be positive")
    validation = validate_architecture_contract(contract)
    if validation.normalized_contract is None or validation.status != ContractStatus.READY:
        return RepairProposal(
            proposal_id=f"architecture-{validation.contract_hash[7:19]}-invalid",
            contract_hash=validation.contract_hash,
            iteration=min(iteration, 3),
            status="not_repairable",
            violations=validation.violations,
        )
    if iteration > 3:
        exhausted = Violation(
            code="DG_ARCH_REPAIR_EXHAUSTED",
            message="Architecture repair is limited to three iterations.",
            details={"max_iterations": 3},
        )
        return RepairProposal(
            proposal_id=f"architecture-{validation.contract_hash[7:19]}-exhausted",
            contract_hash=validation.contract_hash,
            iteration=3,
            status="exhausted",
            violations=[*violations, exhausted],
        )

    normalized = validation.normalized_contract
    source_violations = list(violations)
    if not source_violations:
        drawing = generate_architecture_only(normalized)
        verification = verify_architecture_only(
            normalized,
            base64.b64decode(drawing.dxf_base64),
        )
        source_violations = verification.violations

    _repaired, change, policy_violation = _next_architecture_repair(
        normalized,
        source_violations,
        iteration=iteration,
    )
    result_violations = [*source_violations]
    if policy_violation is not None:
        result_violations.append(policy_violation)
    if change is None:
        status: Literal["exhausted", "not_repairable"] = (
            "exhausted"
            if policy_violation is not None and policy_violation.code == "DG_ARCH_REPAIR_EXHAUSTED"
            else "not_repairable"
        )
        digest_source = [item.code for item in result_violations]
        digest = hashlib.sha256(
            json.dumps(digest_source, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        return RepairProposal(
            proposal_id=f"architecture-{digest}-{iteration}",
            contract_hash=validation.contract_hash,
            iteration=iteration,
            status=status,
            violations=result_violations,
        )

    matching_violation = next(
        (item for item in source_violations if item.code == change["violation_code"]),
        None,
    )
    repair_change = RepairChange(
        path=str(change["path"]),
        before=float(change["before"]),
        after=float(change["after"]),
        reason=str(change["violation_code"]),
        constraint_id=(matching_violation.constraint_id if matching_violation else None),
    )
    digest = hashlib.sha256(
        json.dumps(repair_change.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return RepairProposal(
        proposal_id=f"architecture-{digest}-{iteration}",
        contract_hash=validation.contract_hash,
        iteration=iteration,
        status="proposed",
        changes=[repair_change],
        violations=source_violations,
    )


def apply_architecture_repair(
    contract: ArchitecturalPlanContract,
    proposal: RepairProposal,
) -> ArchitecturalPlanContract:
    """Apply a proposal without permitting wall topology or locked values to change."""
    validation = validate_architecture_contract(contract)
    if validation.normalized_contract is None or validation.status != ContractStatus.READY:
        raise RepairRejected("architecture contract is not repair-ready")
    if proposal.contract_hash != validation.contract_hash:
        raise RepairRejected("proposal contract hash does not match")
    if proposal.status != "proposed" or not proposal.changes:
        raise RepairRejected("proposal has no applicable changes")

    result = validation.normalized_contract
    free_by_path = {item.path: item for item in result.free_parameters}
    locked_paths = {item.path for item in result.dimensions if item.locked}
    for change in proposal.changes:
        if (
            not _is_architecture_repair_path(change.path)
            or change.path in locked_paths
            or change.path not in free_by_path
        ):
            raise RepairRejected(f"path is not repairable: {change.path}")
        actual_before = get_architecture_numeric_path(result, change.path)
        if not math.isclose(actual_before, change.before, abs_tol=1e-9):
            raise RepairRejected(f"stale before value: {change.path}")
        parameter = free_by_path[change.path]
        if not parameter.minimum <= change.after <= parameter.maximum:
            raise RepairRejected(f"repair value is outside the declared range: {change.path}")
        step_index = (change.after - parameter.minimum) / parameter.step
        if not math.isclose(step_index, round(step_index), abs_tol=1e-9):
            raise RepairRejected(f"repair value is off the declared step: {change.path}")
        result = _set_architecture_numeric_path(result, change.path, change.after)

    repaired_validation = validate_architecture_contract(result)
    if (
        repaired_validation.status != ContractStatus.READY
        or repaired_validation.normalized_contract is None
    ):
        raise RepairRejected("repaired architecture contract is infeasible")
    return repaired_validation.normalized_contract


def run_architecture_design(
    contract: ArchitecturalPlanContract,
    *,
    auto_repair: bool = True,
) -> ArchitecturalRunResponse:
    validation = validate_architecture_contract(contract)
    timeline: list[dict[str, Any]] = [
        {"stage": "contract_validation", "status": validation.status.value}
    ]
    if validation.status != ContractStatus.READY or validation.normalized_contract is None:
        normalized = validation.normalized_contract or contract
        preview = ""
        try:
            preview = render_architecture_svg(normalized, validation.contract_hash)
        except ArchitecturalGeometryError:
            pass
        return ArchitecturalRunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            preview_svg=preview,
            violations=validation.violations,
            evidence=validation.evidence,
            summary={**_summary(normalized), "auto_repair": auto_repair, "repair_history": []},
            timeline=timeline,
            error=ErrorInfo(
                code="DG_ARCH_CONTRACT_INFEASIBLE",
                message="Official architecture drawing generation requirements were not met.",
                details={"contract_status": validation.status.value},
                correlation_id=_correlation_id(),
            ),
        )

    current = validation.normalized_contract
    current_hash = validation.contract_hash
    evidence = list(validation.evidence)
    repair_history: list[dict[str, Any]] = []
    repair_violation: Violation | None = None
    drawing = None
    verification: ArchitecturalVerificationResult | None = None
    for iteration in range(1, 5):
        try:
            drawing = generate_architecture_drawing(current, current_hash)
            timeline.append(
                {
                    "stage": "dxf_generation",
                    "iteration": iteration,
                    "status": "generated_unverified",
                }
            )
            verification = verify_architecture_dxf(current, drawing.dxf_bytes, current_hash)
            timeline.append(
                {
                    "stage": "independent_dxf_verification",
                    "iteration": iteration,
                    "status": verification.status.value,
                }
            )
        except (ArchitecturalGeometryError, ArchitecturalDxfReadError) as exc:
            return ArchitecturalRunResponse(
                status=RunStatus.FAILED,
                contract_hash=current_hash,
                preview_svg="",
                violations=[
                    Violation(
                        code="DG_ARCH_DXF_PIPELINE_FAILED",
                        message="Architecture DXF generation or parsing failed.",
                        details={"reason": str(exc)},
                    )
                ],
                evidence=evidence,
                summary={**_summary(current), "repair_history": repair_history},
                timeline=timeline,
                error=ErrorInfo(
                    code="DG_ARCH_DXF_PIPELINE_FAILED",
                    message="The architecture DXF pipeline did not complete.",
                    details={"reason": str(exc)},
                    correlation_id=_correlation_id(),
                ),
            )
        if verification.status == RunStatus.PASSED or not auto_repair:
            break
        if iteration > 3:
            repair_violation = Violation(
                code="DG_ARCH_REPAIR_EXHAUSTED",
                message="Architecture auto-repair reached the maximum of three iterations.",
                details={"max_iterations": 3},
            )
            break
        repaired, change, repair_violation = _next_architecture_repair(
            current,
            verification.violations,
            iteration=iteration,
        )
        if repaired is None or change is None:
            break
        repaired_validation = validate_architecture_contract(repaired)
        if (
            repaired_validation.status != ContractStatus.READY
            or repaired_validation.normalized_contract is None
        ):
            repair_violation = Violation(
                code="DG_ARCH_REPAIR_EXHAUSTED",
                message="An architecture repair candidate failed contract validation.",
                details={"iteration": iteration},
            )
            break
        repair_history.append(change)
        timeline.append({"stage": "auto_repair", "status": "applied", **change})
        current = repaired_validation.normalized_contract
        current_hash = repaired_validation.contract_hash

    assert drawing is not None and verification is not None
    final_violations = list(verification.violations)
    final_status = verification.status
    if repair_violation is not None:
        final_violations.append(repair_violation)
        final_status = (
            RunStatus.REPAIR_EXHAUSTED
            if repair_violation.code == "DG_ARCH_REPAIR_EXHAUSTED"
            else RunStatus.FAILED
        )
    bundle_base64: str | None = None
    if final_status == RunStatus.PASSED:
        bundle = build_verified_architecture_bundle(
            current,
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
    summary = {
        **verification.summary,
        "auto_repair": auto_repair,
        "repair_history": repair_history,
        "repair_iterations": len(repair_history),
    }
    error = None
    if final_status != RunStatus.PASSED:
        error = ErrorInfo(
            code=(repair_violation.code if repair_violation else "DG_ARCH_VERIFICATION_FAILED"),
            message="Independent DXF verification blocked the official architecture bundle.",
            details={"official_export_created": False},
            correlation_id=_correlation_id(),
        )
    if repair_history:
        evidence.append(
            Evidence(
                type="architecture_repair_history",
                source="ortools_cp_sat_architecture_repair",
                details={
                    "max_iterations": 3,
                    "iterations_used": len(repair_history),
                    "changes": repair_history,
                },
            )
        )
    return ArchitecturalRunResponse(
        status=final_status,
        contract_hash=verification.contract_hash,
        artifact_hash=verification.artifact_hash,
        measurements=verification.measurements,
        violations=final_violations,
        evidence=[*evidence, *verification.evidence],
        preview_svg=drawing.preview_svg,
        bundle_base64=bundle_base64,
        summary=summary,
        timeline=timeline,
        error=error,
    )


__all__ = [
    "apply_architecture_repair",
    "generate_architecture_only",
    "propose_architecture_repair",
    "run_architecture_design",
    "validate_architecture_contract",
    "verify_architecture_only",
]

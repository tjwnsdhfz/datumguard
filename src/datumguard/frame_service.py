from __future__ import annotations

import hashlib
import html
import json
import math
import uuid
from typing import Any

from .frame_models import (
    FrameAnalysisResult,
    FrameContractValidationResponse,
    FrameFreeParameter,
    FrameMember,
    FrameRunResponse,
    StructuralFrameContract,
)
from .frame_solver import FrameSolverError, solve_frame
from .models import (
    ContractStatus,
    ErrorInfo,
    Evidence,
    Measurement,
    RepairChange,
    RepairProposal,
    RunStatus,
    Violation,
)

HASH_GRID = 0.001
LIMIT_RELATIVE_TOLERANCE = 1e-9
MAX_REPAIR_ITERATIONS = 3


def _correlation_id() -> str:
    return str(uuid.uuid4())


def _quantize(value: Any) -> Any:
    if isinstance(value, float):
        result = round(value / HASH_GRID) * HASH_GRID
        return 0.0 if abs(result) < HASH_GRID / 2 else round(result, 9)
    if isinstance(value, list):
        items = [_quantize(item) for item in value]
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
    if isinstance(value, tuple):
        return [_quantize(item) for item in value]
    if isinstance(value, dict):
        return {key: _quantize(value[key]) for key in sorted(value)}
    return value


def _compute_contract_hash(contract: StructuralFrameContract) -> str:
    data = contract.model_dump(mode="json", exclude={"contract_hash", "intent_text"})
    # ``provenance`` was added after the v0.3 contract. Omitting only its absent value
    # preserves every pre-existing frame hash while binding imported Rhino identities
    # into the hash whenever a source mapping is present.
    if data.get("provenance") is None:
        data.pop("provenance", None)
    payload = json.dumps(
        _quantize(data),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _compute_analysis_hash(analysis: FrameAnalysisResult) -> str:
    data = analysis.model_dump(mode="json")
    payload = json.dumps(
        _quantize(data),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _screening_evidence() -> Evidence:
    return Evidence(
        type="engineering_screening_notice",
        source="datumguard_frameguard_mvp",
        locator="FrameGuard/limitations",
        details={
            "screening_only": True,
            "safety_certification": False,
            "official_judgement_source": "deterministic_numpy_2d_frame_solver",
            "assumptions": [
                "two_dimensional",
                "linear_elastic",
                "small_displacement",
                "Euler-Bernoulli frame members",
                "rigid member joints",
                "nodal loads only",
            ],
            "not_checked": [
                "buckling",
                "connection capacity",
                "fatigue",
                "dynamic response",
                "nonlinear behaviour",
                "code compliance",
            ],
            "professional_review_required": True,
        },
    )


def _topology_violations(contract: StructuralFrameContract) -> list[Violation]:
    violations: list[Violation] = []
    nodes = {node.id: node for node in contract.nodes}
    unknown: dict[str, set[str]] = {}
    for member in contract.members:
        for node_id in (member.start_node_id, member.end_node_id):
            if node_id not in nodes:
                unknown.setdefault(node_id, set()).add(member.id)
    for load in contract.loads:
        if load.node_id not in nodes:
            unknown.setdefault(load.node_id, set()).add(load.id)
    for support in contract.supports:
        if support.node_id not in nodes:
            unknown.setdefault(support.node_id, set()).add(support.id)
    if unknown:
        violations.append(
            Violation(
                code="DG_FRAME_UNKNOWN_NODE",
                message="A frame member, load, or support references an unknown node.",
                entity_ids=sorted({item for refs in unknown.values() for item in refs}),
                details={
                    "unknown_node_ids": sorted(unknown),
                    "references": {key: sorted(value) for key, value in sorted(unknown.items())},
                },
            )
        )

    zero_length: list[str] = []
    for member in contract.members:
        start = nodes.get(member.start_node_id)
        end = nodes.get(member.end_node_id)
        if start is not None and end is not None and math.dist(start.point, end.point) <= 1e-9:
            zero_length.append(member.id)
    if zero_length:
        violations.append(
            Violation(
                code="DG_FRAME_ZERO_LENGTH",
                message="One or more frame members have zero model length.",
                entity_ids=sorted(zero_length),
                details={"minimum_length_mm": 1e-9},
            )
        )

    if not unknown:
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
        for member in contract.members:
            adjacency[member.start_node_id].add(member.end_node_id)
            adjacency[member.end_node_id].add(member.start_node_id)
        visited: set[str] = set()
        if adjacency:
            pending = [min(adjacency)]
            visited.add(pending[0])
            while pending:
                current = pending.pop()
                for neighbour in sorted(adjacency[current] - visited):
                    visited.add(neighbour)
                    pending.append(neighbour)
        disconnected = sorted(set(adjacency) - visited)
        if disconnected:
            violations.append(
                Violation(
                    code="DG_FRAME_DISCONNECTED",
                    message="The structural frame contains disconnected nodes or sub-frames.",
                    entity_ids=disconnected,
                    details={"disconnected_node_ids": disconnected},
                )
            )
    return violations


def _member_for_parameter(
    contract: StructuralFrameContract,
    parameter: FrameFreeParameter,
) -> FrameMember | None:
    member_id = parameter.path.split(".")[1]
    return next((member for member in contract.members if member.id == member_id), None)


def _free_parameter_violations(contract: StructuralFrameContract) -> list[Violation]:
    violations: list[Violation] = []
    for parameter in contract.free_parameters:
        member = _member_for_parameter(contract, parameter)
        if member is None:
            violations.append(
                Violation(
                    code="DG_FRAME_FREE_PARAMETER_PATH_INVALID",
                    message="A frame free parameter references an unknown member.",
                    entity_ids=[parameter.id],
                    details={"path": parameter.path},
                )
            )
            continue
        if member.locked:
            violations.append(
                Violation(
                    code="DG_FRAME_LOCKED_REPAIR_PATH",
                    message="A free parameter may not target a locked frame member.",
                    entity_ids=[member.id, parameter.id],
                    details={"path": parameter.path},
                )
            )
        field = parameter.path.split(".")[2]
        actual = float(getattr(member, field))
        if not parameter.minimum <= actual <= parameter.maximum:
            violations.append(
                Violation(
                    code="DG_FRAME_FREE_PARAMETER_RANGE",
                    message="A member property is outside its declared repair range.",
                    entity_ids=[member.id, parameter.id],
                    repairable=not member.locked,
                    details={
                        "path": parameter.path,
                        "actual": actual,
                        "minimum": parameter.minimum,
                        "maximum": parameter.maximum,
                    },
                )
            )
    return violations


def validate_frame_contract(
    contract: StructuralFrameContract,
) -> FrameContractValidationResponse:
    contract_hash = _compute_contract_hash(contract)
    normalized = contract.model_copy(update={"contract_hash": contract_hash})
    violations = [*_topology_violations(normalized), *_free_parameter_violations(normalized)]
    if contract.contract_hash and contract.contract_hash != contract_hash:
        violations.append(
            Violation(
                code="DG_CONTRACT_HASH_MISMATCH",
                message="The supplied structural frame hash differs from its canonical hash.",
                details={"provided": contract.contract_hash, "canonical": contract_hash},
            )
        )

    if not violations:
        try:
            solve_frame(normalized)
        except FrameSolverError as exc:
            violations.append(
                Violation(
                    code=exc.code,
                    message=exc.message,
                    entity_ids=exc.entity_ids,
                    details=exc.details,
                )
            )
    status = ContractStatus.READY if not violations else ContractStatus.INFEASIBLE
    return FrameContractValidationResponse(
        status=status,
        contract_hash=contract_hash,
        violations=violations,
        evidence=[
            Evidence(
                type="structural_frame_contract_normalization",
                source="deterministic_frame_contract_core",
                details={
                    "design_kind": "structural_frame",
                    "units": "mm-N-MPa",
                    "hash_grid": HASH_GRID,
                    "learned_model_used": False,
                },
            ),
            _screening_evidence(),
        ],
        normalized_contract=normalized,
    )


def _passes(actual: float, limit: float) -> bool:
    tolerance = max(1e-9, abs(limit) * LIMIT_RELATIVE_TOLERANCE)
    return actual <= limit + tolerance


def _measurements(
    contract: StructuralFrameContract,
    analysis: FrameAnalysisResult,
) -> list[Measurement]:
    displacement_passed = _passes(
        analysis.max_displacement_mm,
        contract.limits.max_displacement_mm,
    )
    return [
        Measurement(
            measurement_id="frame-max-displacement",
            dimension_id="limits.max_displacement_mm",
            target=contract.limits.max_displacement_mm,
            actual=analysis.max_displacement_mm,
            deviation=analysis.max_displacement_mm - contract.limits.max_displacement_mm,
            tolerance_lower=-contract.limits.max_displacement_mm,
            tolerance_upper=0.0,
            passed=displacement_passed,
            evidence={
                "node_id": analysis.max_displacement_node_id,
                "measure": "sqrt(ux^2 + uy^2)",
                "solver": analysis.solver,
            },
        )
    ]


def _analysis_violations(
    contract: StructuralFrameContract,
    analysis: FrameAnalysisResult,
) -> list[Violation]:
    violations: list[Violation] = []
    if not _passes(analysis.max_displacement_mm, contract.limits.max_displacement_mm):
        violations.append(
            Violation(
                code="DG_FRAME_DISPLACEMENT_EXCEEDED",
                message="The maximum translational displacement exceeds the screening limit.",
                entity_ids=[analysis.max_displacement_node_id],
                repairable=any(
                    parameter.path.endswith(".inertia_mm4")
                    for parameter in contract.free_parameters
                ),
                details={
                    "actual_mm": analysis.max_displacement_mm,
                    "limit_mm": contract.limits.max_displacement_mm,
                    "utilization": analysis.displacement_utilization,
                },
            )
        )
    for result in analysis.member_results:
        if not _passes(result.max_combined_stress_mpa, result.allowable_stress_mpa):
            member_prefix = f"members.{result.member_id}."
            violations.append(
                Violation(
                    code="DG_FRAME_MEMBER_OVERSTRESS",
                    message="A frame member exceeds its allowable combined stress.",
                    entity_ids=[result.member_id],
                    repairable=any(
                        parameter.path.startswith(member_prefix)
                        for parameter in contract.free_parameters
                    ),
                    details={
                        "actual_mpa": result.max_combined_stress_mpa,
                        "allowable_mpa": result.allowable_stress_mpa,
                        "utilization": result.utilization,
                    },
                )
            )
    return violations


def _next_value(parameter: FrameFreeParameter, current: float, factor: float) -> float | None:
    desired = min(parameter.maximum, current * max(1.10, min(factor * 1.05, 4.0)))
    steps = math.ceil(max(0.0, desired - parameter.minimum) / parameter.step - 1e-12)
    candidate = min(parameter.maximum, parameter.minimum + steps * parameter.step)
    candidate = max(candidate, min(parameter.maximum, current + parameter.step))
    if candidate <= current + 1e-12:
        return None
    return candidate


def _propose_frame_repair(
    contract: StructuralFrameContract,
    analysis: FrameAnalysisResult,
    *,
    iteration: int,
) -> RepairProposal:
    violations = _analysis_violations(contract, analysis)
    if not violations:
        return RepairProposal(
            proposal_id=f"frame-repair-{iteration}",
            contract_hash=_compute_contract_hash(contract),
            iteration=iteration,
            status="not_repairable",
        )
    member_results = {item.member_id: item for item in analysis.member_results}
    high_energy_members = {
        item.member_id
        for item in sorted(
            analysis.member_results,
            key=lambda result: (-result.strain_energy_nmm, result.member_id),
        )[: max(1, min(3, len(analysis.member_results)))]
    }
    changes: list[RepairChange] = []
    for parameter in sorted(contract.free_parameters, key=lambda item: item.id):
        member = _member_for_parameter(contract, parameter)
        if member is None or member.locked:
            continue
        result = member_results[member.id]
        field = parameter.path.split(".")[2]
        is_stress_candidate = result.utilization > 1.0 + LIMIT_RELATIVE_TOLERANCE
        is_displacement_candidate = (
            analysis.displacement_utilization > 1.0 + LIMIT_RELATIVE_TOLERANCE
            and field == "inertia_mm4"
            and member.id in high_energy_members
        )
        if not (is_stress_candidate or is_displacement_candidate):
            continue
        factor = max(
            result.utilization if is_stress_candidate else 1.0,
            analysis.displacement_utilization if is_displacement_candidate else 1.0,
        )
        before = float(getattr(member, field))
        after = _next_value(parameter, before, factor)
        if after is None:
            continue
        changes.append(
            RepairChange(
                path=parameter.path,
                before=before,
                after=after,
                reason=(
                    "Increase a declared free section property, then rerun the exact solver; "
                    "geometry and locked members remain unchanged."
                ),
            )
        )
        if len(changes) == 3:
            break
    return RepairProposal(
        proposal_id=f"frame-repair-{iteration}",
        contract_hash=_compute_contract_hash(contract),
        iteration=iteration,
        status="proposed" if changes else "not_repairable",
        changes=changes,
        violations=violations,
    )


def propose_frame_repair(
    contract: StructuralFrameContract,
    analysis: FrameAnalysisResult,
) -> RepairProposal:
    return _propose_frame_repair(contract, analysis, iteration=1)


def _apply_repair(
    contract: StructuralFrameContract,
    proposal: RepairProposal,
) -> StructuralFrameContract:
    data = contract.model_dump(mode="python")
    members = {item["id"]: item for item in data["members"]}
    original = {item.id: item for item in contract.members}
    for change in proposal.changes:
        _, member_id, field = change.path.split(".")
        member = original[member_id]
        if member.locked or field not in {"area_mm2", "inertia_mm4"}:
            raise ValueError("repair attempted to modify a locked or non-free property")
        members[member_id][field] = change.after
    data["contract_hash"] = None
    return StructuralFrameContract.model_validate(data)


def _render_frame_svg(
    contract: StructuralFrameContract,
    analysis: FrameAnalysisResult | None = None,
) -> str:
    width, height = 900.0, 600.0
    margin_left, margin_top, margin_right, margin_bottom = 70.0, 70.0, 70.0, 110.0
    xs = [node.point[0] for node in contract.nodes]
    ys = [node.point[1] for node in contract.nodes]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    scale = min(
        (width - margin_left - margin_right) / span_x,
        (height - margin_top - margin_bottom) / span_y,
    )

    def screen(point: tuple[float, float]) -> tuple[float, float]:
        return (
            margin_left + (point[0] - min_x) * scale,
            height - margin_bottom - (point[1] - min_y) * scale,
        )

    nodes = {node.id: node for node in contract.nodes}
    results = {item.member_id: item for item in analysis.member_results} if analysis else {}
    node_results = {item.node_id: item for item in analysis.node_results} if analysis else {}
    lines: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 600" role="img" '
        'aria-label="FrameGuard structural screening preview">',
        '<rect width="900" height="600" fill="#07111d"/>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" '
        'orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#f59e0b"/></marker></defs>',
        '<text x="32" y="36" fill="#e5eef7" font-family="system-ui,sans-serif" '
        'font-size="20" font-weight="700">FrameGuard · Exact 2D Frame Screening</text>',
    ]
    for member in sorted(contract.members, key=lambda item: item.id):
        start_node = nodes.get(member.start_node_id)
        end_node = nodes.get(member.end_node_id)
        if start_node is None or end_node is None:
            continue
        x1, y1 = screen(start_node.point)
        x2, y2 = screen(end_node.point)
        member_result = results.get(member.id)
        utilization = member_result.utilization if member_result is not None else 0.0
        colour = "#ef4444" if utilization > 1.0 else "#38bdf8"
        lines.append(
            f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
            f'stroke="{colour}" stroke-width="5" stroke-linecap="round" '
            f'data-entity-id="{html.escape(member.id)}"/>'
        )
    if analysis and analysis.max_displacement_mm > 0:
        model_span = max(span_x, span_y)
        deformation_scale = min(model_span * 0.08 / analysis.max_displacement_mm, 100.0)
        for member in sorted(contract.members, key=lambda item: item.id):
            start_node = nodes.get(member.start_node_id)
            end_node = nodes.get(member.end_node_id)
            start_result = node_results.get(member.start_node_id)
            end_result = node_results.get(member.end_node_id)
            if not all((start_node, end_node, start_result, end_result)):
                continue
            assert start_node is not None and end_node is not None
            assert start_result is not None and end_result is not None
            deformed_start = (
                start_node.point[0] + start_result.ux_mm * deformation_scale,
                start_node.point[1] + start_result.uy_mm * deformation_scale,
            )
            deformed_end = (
                end_node.point[0] + end_result.ux_mm * deformation_scale,
                end_node.point[1] + end_result.uy_mm * deformation_scale,
            )
            x1, y1 = screen(deformed_start)
            x2, y2 = screen(deformed_end)
            lines.append(
                f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
                'stroke="#fbbf24" stroke-width="2" stroke-dasharray="8 5" opacity="0.9"/>'
            )
    for support in sorted(contract.supports, key=lambda item: item.id):
        node = nodes.get(support.node_id)
        if node is None:
            continue
        x, y = screen(node.point)
        lines.append(
            f'<path d="M {x - 10:.3f} {y + 14:.3f} L {x + 10:.3f} {y + 14:.3f} '
            f'L {x:.3f} {y:.3f} Z" fill="#a78bfa" opacity="0.95"/>'
        )
    for load in sorted(contract.loads, key=lambda item: item.id):
        node = nodes.get(load.node_id)
        if node is None:
            continue
        x, y = screen(node.point)
        magnitude = math.hypot(load.fx_n, load.fy_n)
        if magnitude <= 0:
            continue
        dx = load.fx_n / magnitude * 34.0
        dy = -load.fy_n / magnitude * 34.0
        lines.append(
            f'<line x1="{x - dx:.3f}" y1="{y - dy:.3f}" x2="{x:.3f}" y2="{y:.3f}" '
            'stroke="#f59e0b" stroke-width="3" marker-end="url(#arrow)"/>'
        )
    for node in sorted(contract.nodes, key=lambda item: item.id):
        x, y = screen(node.point)
        lines.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="4" fill="#f8fafc"/>')
        lines.append(
            f'<text x="{x + 7:.3f}" y="{y - 7:.3f}" fill="#9fb3c8" '
            f'font-size="11" font-family="ui-monospace,monospace">{html.escape(node.id)}</text>'
        )
    status = "UNSOLVED"
    status_colour = "#94a3b8"
    if analysis:
        passed = analysis.displacement_utilization <= 1.0 and analysis.max_member_utilization <= 1.0
        status = "PASS" if passed else "FAIL"
        status_colour = "#34d399" if passed else "#fb7185"
        lines.append(
            '<text x="32" y="548" fill="#9fb3c8" font-family="system-ui,sans-serif" '
            f'font-size="13">max displacement {analysis.max_displacement_mm:.3f} mm · '
            f"max utilization {analysis.max_member_utilization:.3f}</text>"
        )
    lines.extend(
        [
            f'<text x="818" y="38" fill="{status_colour}" text-anchor="end" '
            f'font-family="system-ui,sans-serif" font-size="18" font-weight="800">{status}</text>',
            '<text x="32" y="578" fill="#64748b" font-family="system-ui,sans-serif" '
            'font-size="11">SCREENING ONLY · NOT A SAFETY CERTIFICATION · '
            "PROFESSIONAL REVIEW REQUIRED</text>",
            "</svg>",
        ]
    )
    return "".join(lines)


def _summary(
    contract: StructuralFrameContract,
    analysis: FrameAnalysisResult | None,
    *,
    original_contract_hash: str,
    repairs: list[RepairProposal],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "design_kind": "structural_frame",
        "analysis_source": "exact_numpy_2d_euler_bernoulli",
        "official_judgement_source": "deterministic_solver",
        "screening_only": True,
        "safety_certification": False,
        "nodes": len(contract.nodes),
        "members": len(contract.members),
        "loads": len(contract.loads),
        "supports": len(contract.supports),
        "original_contract_hash": original_contract_hash,
        "repair_iterations": sum(item.status == "proposed" for item in repairs),
        "final_member_properties": [
            {
                "member_id": member.id,
                "area_mm2": member.area_mm2,
                "inertia_mm4": member.inertia_mm4,
                "locked": member.locked,
            }
            for member in sorted(contract.members, key=lambda item: item.id)
        ],
    }
    if analysis:
        summary.update(
            {
                "solver": analysis.solver,
                "node_count": len(contract.nodes),
                "member_count": len(contract.members),
                "max_displacement_mm": analysis.max_displacement_mm,
                "max_displacement_node_id": analysis.max_displacement_node_id,
                "displacement_utilization": analysis.displacement_utilization,
                "max_member_utilization": analysis.max_member_utilization,
                "max_utilization": analysis.max_member_utilization,
                "critical_member_id": analysis.critical_member_id,
                "governing_member_id": analysis.critical_member_id,
                "condition_number": analysis.condition_number,
                "equilibrium_residual_n": analysis.equilibrium_residual_n,
                "node_results": [item.model_dump(mode="json") for item in analysis.node_results],
                "member_results": [
                    item.model_dump(mode="json") for item in analysis.member_results
                ],
            }
        )
    return summary


def run_frame_design(
    contract: StructuralFrameContract,
    auto_repair: bool = False,
) -> FrameRunResponse:
    validation = validate_frame_contract(contract)
    original_hash = validation.contract_hash
    timeline: list[dict[str, Any]] = [
        {"stage": "contract_validation", "status": validation.status.value},
    ]
    if validation.status != ContractStatus.READY or validation.normalized_contract is None:
        preview = _render_frame_svg(validation.normalized_contract or contract)
        return FrameRunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            violations=validation.violations,
            evidence=validation.evidence,
            summary=_summary(
                validation.normalized_contract or contract,
                None,
                original_contract_hash=original_hash,
                repairs=[],
            ),
            timeline=[*timeline, {"stage": "official_screening", "status": "blocked"}],
            preview_svg=preview,
            error=ErrorInfo(
                code=(
                    validation.violations[0].code if validation.violations else "DG_INPUT_INVALID"
                ),
                message="Structural frame contract validation blocked analysis.",
                details={"contract_status": validation.status.value},
                correlation_id=_correlation_id(),
            ),
        )

    current = validation.normalized_contract
    proposals: list[RepairProposal] = []
    analysis: FrameAnalysisResult | None = None
    violations: list[Violation] = []
    measurements: list[Measurement] = []
    for iteration in range(1, MAX_REPAIR_ITERATIONS + 2):
        timeline.append({"stage": "exact_solver_assembly", "status": "started"})
        try:
            analysis = solve_frame(current)
        except FrameSolverError as exc:
            timeline.append({"stage": "exact_solver", "status": "failed", "code": exc.code})
            return FrameRunResponse(
                status=RunStatus.FAILED,
                contract_hash=_compute_contract_hash(current),
                violations=[
                    Violation(
                        code=exc.code,
                        message=exc.message,
                        entity_ids=exc.entity_ids,
                        details=exc.details,
                    )
                ],
                evidence=[*validation.evidence, _screening_evidence()],
                summary=_summary(
                    current,
                    None,
                    original_contract_hash=original_hash,
                    repairs=proposals,
                ),
                timeline=[*timeline, {"stage": "official_screening", "status": "blocked"}],
                preview_svg=_render_frame_svg(current),
                repair_proposals=proposals,
                error=ErrorInfo(
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                    correlation_id=_correlation_id(),
                ),
            )
        timeline.append(
            {
                "stage": "exact_solver",
                "status": "solved",
                "solver": analysis.solver,
                "iteration": iteration,
            }
        )
        measurements = _measurements(current, analysis)
        violations = _analysis_violations(current, analysis)
        timeline.append(
            {
                "stage": "independent_limit_checks",
                "status": "passed" if not violations else "failed",
                "iteration": iteration,
            }
        )
        if not violations:
            break
        proposal = _propose_frame_repair(current, analysis, iteration=min(iteration, 3))
        proposals.append(proposal)
        if not auto_repair or proposal.status != "proposed" or iteration > MAX_REPAIR_ITERATIONS:
            break
        current = _apply_repair(current, proposal)
        current_validation = validate_frame_contract(current)
        if (
            current_validation.status != ContractStatus.READY
            or current_validation.normalized_contract is None
        ):
            violations = [*violations, *current_validation.violations]
            break
        current = current_validation.normalized_contract
        timeline.append(
            {
                "stage": "bounded_section_repair",
                "status": "applied",
                "iteration": iteration,
                "change_count": len(proposal.changes),
            }
        )

    assert analysis is not None
    final_hash = _compute_contract_hash(current)
    artifact_hash = _compute_analysis_hash(analysis)
    passed = not violations
    exhausted = (
        auto_repair and not passed and any(proposal.status == "proposed" for proposal in proposals)
    )
    status = (
        RunStatus.PASSED
        if passed
        else (RunStatus.REPAIR_EXHAUSTED if exhausted else RunStatus.FAILED)
    )
    if exhausted:
        violations.append(
            Violation(
                code="DG_FRAME_REPAIR_EXHAUSTED",
                message="The bounded frame repair reached its limit without passing screening.",
                details={"max_iterations": MAX_REPAIR_ITERATIONS},
            )
        )
    timeline.append({"stage": "official_screening", "status": "passed" if passed else "blocked"})
    error = None
    if not passed:
        error = ErrorInfo(
            code="DG_FRAME_SCREENING_FAILED",
            message="Exact frame analysis did not satisfy all configured screening limits.",
            details={"official_pass": False, "safety_certification": False},
            correlation_id=_correlation_id(),
        )
    evidence = [
        *validation.evidence,
        Evidence(
            type="structural_analysis",
            source="datumguard_numpy_2d_frame_v1",
            details={
                "artifact_hash": artifact_hash,
                "learned_model_used": False,
                "exact_solver_is_official_judge": True,
                "condition_number": analysis.condition_number,
                "equilibrium_residual_n": analysis.equilibrium_residual_n,
            },
        ),
        Evidence(
            type="limit_check",
            source="frame_service",
            details={
                "relative_boundary_tolerance": LIMIT_RELATIVE_TOLERANCE,
                "passed": passed,
                "false_pass_allowed": False,
            },
        ),
    ]
    if proposals:
        evidence.append(
            Evidence(
                type="bounded_repair_history",
                source="declared_frame_free_parameters",
                details={
                    "max_iterations": MAX_REPAIR_ITERATIONS,
                    "proposals": [item.model_dump(mode="json") for item in proposals],
                    "locked_member_changes": 0,
                },
            )
        )
    return FrameRunResponse(
        status=status,
        contract_hash=final_hash,
        artifact_hash=artifact_hash,
        measurements=measurements,
        violations=violations,
        evidence=evidence,
        summary=_summary(
            current,
            analysis,
            original_contract_hash=original_hash,
            repairs=proposals,
        ),
        timeline=timeline,
        preview_svg=_render_frame_svg(current, analysis),
        repair_proposals=proposals,
        error=error,
    )


__all__ = [
    "propose_frame_repair",
    "run_frame_design",
    "validate_frame_contract",
]

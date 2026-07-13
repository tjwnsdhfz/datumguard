from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, cast

from mcp.server.fastmcp import FastMCP

from .architecture_models import ArchitecturalPlanContract
from .architecture_service import (
    apply_architecture_repair,
    generate_architecture_only,
    propose_architecture_repair,
    run_architecture_design,
    validate_architecture_contract,
    verify_architecture_only,
)
from .artifact_service import audit_artifact as audit_artifact_core
from .artifact_service import compare_artifacts as compare_artifacts_core
from .frame_cad_service import run_frame_cad_assurance
from .frame_models import StructuralFrameContract
from .frame_research_evidence import (
    FrameResearchEvidenceError,
    load_opensees_parity_report,
)
from .frame_rhino_adapter import RhinoFrameExchange, adapt_rhino_frame_exchange
from .frame_roundtrip_service import FrameRhinoRoundTripResponse, run_frame_rhino_roundtrip
from .frame_service import propose_frame_repair, run_frame_design, validate_frame_contract
from .frame_solver import FrameSolverError, solve_frame
from .frame_surrogate import predict_frame_surrogate
from .models import DesignContract, RepairProposal, Violation
from .piping_models import PipingPlanContract
from .piping_service import (
    generate_piping_only,
    run_piping_design,
    validate_piping_contract,
    verify_piping_only,
)
from .repair import RepairRejected
from .service import (
    apply_repair,
    compare_contracts,
    draft_contract,
    generate_only,
    propose_repair,
    run_design,
    validate_contract,
    verify_only,
)
from .solid_models import SolidPartContract
from .solid_service import run_solid_design

mcp = FastMCP(
    "DatumGuard",
    instructions=(
        "Use structured DesignContract inputs. Never infer missing numbers, units, datum, or "
        "tolerances. Only a passed independent DXF verification may produce an export bundle. "
        "Structural-frame results are screening evidence, never a safety certification."
    ),
    log_level="WARNING",
)


PublicContract = (
    DesignContract | ArchitecturalPlanContract | PipingPlanContract | StructuralFrameContract
)


def _contract(value: dict[str, Any]) -> PublicContract:
    if value.get("design_kind") == "structural_frame":
        return StructuralFrameContract.model_validate(value)
    if value.get("design_kind") == "architectural_plan":
        return ArchitecturalPlanContract.model_validate(value)
    if value.get("design_kind") == "piping_plan":
        return PipingPlanContract.model_validate(value)
    return DesignContract.model_validate(value)


def _base_envelope(contract_hash: str, *, status: str = "ready") -> dict[str, Any]:
    return {
        "status": status,
        "contract_hash": contract_hash,
        "artifact_hash": None,
        "measurements": [],
        "violations": [],
        "evidence": [],
        "error": None,
    }


def _frame_tool_unsupported(
    contract: StructuralFrameContract,
    *,
    tool_name: str,
) -> dict[str, Any]:
    validation = validate_frame_contract(contract)
    result = _base_envelope(validation.contract_hash, status="infeasible")
    result["violations"] = [item.model_dump(mode="json") for item in validation.violations]
    result["error"] = {
        "code": "DG_FRAME_TOOL_UNSUPPORTED",
        "message": f"{tool_name} is not part of the structural-frame screening path.",
        "details": {
            "tool": tool_name,
            "use_instead": "frame_analyze",
            "safety_certification": False,
        },
        "correlation_id": validation.contract_hash.removeprefix("sha256:")[:12],
    }
    return result


@mcp.tool(description="Draft a contract without inferring ambiguous numbers or units.")
def design_contract_draft(
    contract: dict[str, Any],
    intent_text: str | None = None,
) -> dict[str, Any]:
    source = _contract(contract)
    if isinstance(source, StructuralFrameContract):
        if intent_text is not None:
            source = source.model_copy(update={"intent_text": intent_text})
        return validate_frame_contract(source).model_dump(mode="json")
    if isinstance(source, ArchitecturalPlanContract):
        if intent_text is not None:
            source = source.model_copy(update={"intent_text": intent_text})
        return validate_architecture_contract(source).model_dump(mode="json")
    if isinstance(source, PipingPlanContract):
        if intent_text is not None:
            source = source.model_copy(update={"intent_text": intent_text})
        return validate_piping_contract(source).model_dump(mode="json")
    return draft_contract(source, intent_text).model_dump(mode="json")


@mcp.tool(description="Normalize and validate a DesignContract for deterministic generation.")
def design_contract_validate(contract: dict[str, Any]) -> dict[str, Any]:
    source = _contract(contract)
    if isinstance(source, StructuralFrameContract):
        return validate_frame_contract(source).model_dump(mode="json")
    if isinstance(source, ArchitecturalPlanContract):
        return validate_architecture_contract(source).model_dump(mode="json")
    if isinstance(source, PipingPlanContract):
        return validate_piping_contract(source).model_dump(mode="json")
    return validate_contract(source).model_dump(mode="json")


@mcp.tool(description="Generate an unverified R2013 DXF and SVG preview.")
def drawing_generate(contract: dict[str, Any]) -> dict[str, Any]:
    source = _contract(contract)
    if isinstance(source, StructuralFrameContract):
        return _frame_tool_unsupported(source, tool_name="drawing_generate")
    if isinstance(source, ArchitecturalPlanContract):
        return generate_architecture_only(source).model_dump(mode="json")
    if isinstance(source, PipingPlanContract):
        return generate_piping_only(source).model_dump(mode="json")
    return generate_only(source).model_dump(mode="json")


@mcp.tool(description="Independently re-read and remeasure serialized DXF bytes.")
def drawing_verify(contract: dict[str, Any], dxf_base64: str) -> dict[str, Any]:
    dxf_bytes = base64.b64decode(dxf_base64, validate=True)
    source = _contract(contract)
    if isinstance(source, StructuralFrameContract):
        return _frame_tool_unsupported(source, tool_name="drawing_verify")
    if isinstance(source, ArchitecturalPlanContract):
        return verify_architecture_only(source, dxf_bytes).as_dict()
    if isinstance(source, PipingPlanContract):
        return verify_piping_only(source, dxf_bytes).as_dict()
    return verify_only(source, dxf_bytes).as_dict()


@mcp.tool(
    description=(
        "Audit an immutable DXF, STEP, or IFC artifact. This is informational and never "
        "grants fabrication approval without an explicit contract."
    )
)
def artifact_audit(filename: str, content_base64: str) -> dict[str, Any]:
    try:
        content = base64.b64decode(content_base64, validate=True)
    except ValueError as exc:
        return {
            **_base_envelope("sha256:not-applicable", status="failed_verification"),
            "error": {
                "code": "DG_INPUT_INVALID",
                "message": "content_base64 is invalid.",
                "details": {},
                "correlation_id": type(exc).__name__,
            },
        }
    return audit_artifact_core(filename, content).model_dump(mode="json")


@mcp.tool(
    description=(
        "Compare two immutable CAD artifact revisions by DXF geometry fingerprints, STEP "
        "kernel measurements, or IFC GlobalIds."
    )
)
def artifact_compare(
    baseline_filename: str,
    baseline_base64: str,
    candidate_filename: str,
    candidate_base64: str,
) -> dict[str, Any]:
    try:
        baseline = base64.b64decode(baseline_base64, validate=True)
        candidate = base64.b64decode(candidate_base64, validate=True)
    except ValueError as exc:
        return {
            **_base_envelope("sha256:not-applicable", status="failed_verification"),
            "error": {
                "code": "DG_INPUT_INVALID",
                "message": "One or more artifact payloads are not valid base64.",
                "details": {},
                "correlation_id": type(exc).__name__,
            },
        }
    return compare_artifacts_core(
        baseline_filename,
        baseline,
        candidate_filename,
        candidate,
    ).model_dump(mode="json")


@mcp.tool(
    description=(
        "Generate a constrained mounting plate, angle bracket, or flange STEP file, reopen "
        "the serialized STEP with OpenCascade, and return an approved bundle only on pass."
    )
)
def solid_generate_verify(contract: dict[str, Any]) -> dict[str, Any]:
    parsed = SolidPartContract.model_validate(contract)
    return run_solid_design(parsed).model_dump(mode="json")


@mcp.tool(description="Propose bounded changes to declared free parameters only.")
def repair_propose(
    contract: dict[str, Any],
    violations: list[dict[str, Any]],
    iteration: int = 1,
) -> dict[str, Any]:
    parsed = [Violation.model_validate(item) for item in violations]
    source = _contract(contract)
    if isinstance(source, StructuralFrameContract):
        return cast(dict[str, Any], frame_repair_propose(contract))
    if isinstance(source, ArchitecturalPlanContract):
        proposal = propose_architecture_repair(source, parsed, iteration=iteration)
        result = _base_envelope(proposal.contract_hash, status=proposal.status)
        result["violations"] = [item.model_dump(mode="json") for item in proposal.violations]
        result["proposal"] = proposal.model_dump(mode="json")
        return result
    if isinstance(source, PipingPlanContract):
        piping_proposal_validation = validate_piping_contract(source)
        unsupported = Violation(
            code="DG_PIPE_REPAIR_NOT_SUPPORTED",
            message="MVP piping mode는 exact numeric edit 후 재검증을 사용합니다.",
            repairable=False,
        )
        result = _base_envelope(
            piping_proposal_validation.contract_hash,
            status="not_repairable",
        )
        result["violations"] = [
            *(item.model_dump(mode="json") for item in parsed),
            unsupported.model_dump(mode="json"),
        ]
        result["proposal"] = {
            "proposal_id": f"piping-{piping_proposal_validation.contract_hash[7:19]}",
            "contract_hash": piping_proposal_validation.contract_hash,
            "iteration": iteration,
            "status": "not_repairable",
            "changes": [],
            "violations": result["violations"],
        }
        return result
    proposal = propose_repair(source, parsed, iteration=iteration)
    result = _base_envelope(proposal.contract_hash, status=proposal.status)
    result["violations"] = [item.model_dump(mode="json") for item in proposal.violations]
    result["proposal"] = proposal.model_dump(mode="json")
    return result


@mcp.tool(description="Apply an accepted repair after enforcing locked/free policy.")
def repair_apply(
    contract: dict[str, Any],
    proposal: dict[str, Any],
) -> dict[str, Any]:
    source = _contract(contract)
    parsed = RepairProposal.model_validate(proposal)
    if isinstance(source, StructuralFrameContract):
        result = _frame_tool_unsupported(source, tool_name="repair_apply")
        result["error"]["details"]["proposal_id"] = parsed.proposal_id
        result["error"]["details"]["manual_contract_revision_required"] = True
        return result
    if isinstance(source, ArchitecturalPlanContract):
        try:
            repaired_architecture = apply_architecture_repair(source, parsed)
        except RepairRejected as exc:
            result = _base_envelope(parsed.contract_hash, status="infeasible")
            result["error"] = {
                "code": "DG_ARCH_REPAIR_REJECTED",
                "message": str(exc),
                "details": {},
                "correlation_id": parsed.proposal_id,
            }
            return result
        architecture_validation = validate_architecture_contract(repaired_architecture)
        result = _base_envelope(
            architecture_validation.contract_hash,
            status=architecture_validation.status.value,
        )
        result["contract"] = repaired_architecture.model_dump(mode="json")
        result["violations"] = [
            item.model_dump(mode="json") for item in architecture_validation.violations
        ]
        return result
    if isinstance(source, PipingPlanContract):
        piping_validation = validate_piping_contract(source)
        result = _base_envelope(piping_validation.contract_hash, status="infeasible")
        result["error"] = {
            "code": "DG_PIPE_REPAIR_NOT_SUPPORTED",
            "message": "Piping MVP에서는 repair proposal을 적용할 수 없습니다.",
            "details": {"manual_numeric_edit_required": True},
            "correlation_id": parsed.proposal_id,
        }
        return result
    try:
        repaired = apply_repair(source, parsed)
    except RepairRejected as exc:
        result = _base_envelope(parsed.contract_hash, status="infeasible")
        result["error"] = {
            "code": "DG_CONTRACT_INFEASIBLE",
            "message": str(exc),
            "details": {},
            "correlation_id": parsed.proposal_id,
        }
        return result
    plate_validation = validate_contract(repaired)
    result = _base_envelope(
        plate_validation.contract_hash,
        status=plate_validation.status.value,
    )
    result["contract"] = repaired.model_dump(mode="json")
    result["violations"] = [item.model_dump(mode="json") for item in plate_validation.violations]
    return result


def _contract_kind(contract: PublicContract) -> str:
    if isinstance(contract, StructuralFrameContract):
        return "structural_frame"
    if isinstance(contract, ArchitecturalPlanContract):
        return "architectural_plan"
    if isinstance(contract, PipingPlanContract):
        return "piping_plan"
    return "plate_panel"


def _collection_diff(
    baseline: PublicContract,
    candidate: PublicContract,
    collection_names: tuple[str, ...],
) -> dict[str, Any]:
    collections: dict[str, Any] = {}
    for name in collection_names:
        baseline_items = {item.id: item.model_dump(mode="json") for item in getattr(baseline, name)}
        candidate_items = {
            item.id: item.model_dump(mode="json") for item in getattr(candidate, name)
        }
        collections[name] = {
            "added": sorted(candidate_items.keys() - baseline_items.keys()),
            "removed": sorted(baseline_items.keys() - candidate_items.keys()),
            "changed": sorted(
                item_id
                for item_id in baseline_items.keys() & candidate_items.keys()
                if baseline_items[item_id] != candidate_items[item_id]
            ),
        }
    return collections


@mcp.tool(description="Compare two contract revisions by public dimension and feature IDs.")
def drawing_compare(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_contract = _contract(baseline)
    candidate_contract = _contract(candidate)
    if _contract_kind(baseline_contract) != _contract_kind(candidate_contract):
        result = _base_envelope("sha256:unavailable", status="infeasible")
        result["error"] = {
            "code": "DG_DESIGN_KIND_MISMATCH",
            "message": "서로 다른 design_kind의 contract는 비교할 수 없습니다.",
            "details": {
                "baseline": _contract_kind(baseline_contract),
                "candidate": _contract_kind(candidate_contract),
            },
            "correlation_id": "design-kind-mismatch",
        }
        return result

    comparison: dict[str, Any]
    if isinstance(baseline_contract, StructuralFrameContract) and isinstance(
        candidate_contract, StructuralFrameContract
    ):
        frame_baseline_validation = validate_frame_contract(baseline_contract)
        frame_candidate_validation = validate_frame_contract(candidate_contract)
        comparison = {
            "design_kind": "structural_frame",
            "baseline_hash": frame_baseline_validation.contract_hash,
            "candidate_hash": frame_candidate_validation.contract_hash,
            "collections": _collection_diff(
                baseline_contract,
                candidate_contract,
                ("nodes", "members", "loads", "supports"),
            ),
        }
    elif isinstance(baseline_contract, ArchitecturalPlanContract) and isinstance(
        candidate_contract, ArchitecturalPlanContract
    ):
        architecture_baseline_validation = validate_architecture_contract(baseline_contract)
        architecture_candidate_validation = validate_architecture_contract(candidate_contract)
        comparison = {
            "design_kind": "architectural_plan",
            "baseline_hash": architecture_baseline_validation.contract_hash,
            "candidate_hash": architecture_candidate_validation.contract_hash,
            "collections": _collection_diff(
                baseline_contract,
                candidate_contract,
                ("grids", "walls", "openings", "columns", "room_seeds"),
            ),
        }
    elif isinstance(baseline_contract, PipingPlanContract) and isinstance(
        candidate_contract, PipingPlanContract
    ):
        piping_baseline_validation = validate_piping_contract(baseline_contract)
        piping_candidate_validation = validate_piping_contract(candidate_contract)
        comparison = {
            "design_kind": "piping_plan",
            "baseline_hash": piping_baseline_validation.contract_hash,
            "candidate_hash": piping_candidate_validation.contract_hash,
            "collections": _collection_diff(
                baseline_contract,
                candidate_contract,
                ("nodes", "segments", "components", "supports", "equipment_zones"),
            ),
        }
    elif isinstance(baseline_contract, DesignContract) and isinstance(
        candidate_contract, DesignContract
    ):
        comparison = compare_contracts(baseline_contract, candidate_contract)
    else:
        raise AssertionError("design kind guard failed")
    result = _base_envelope(comparison["candidate_hash"])
    result["comparison"] = comparison
    result["evidence"] = [
        {"type": "contract_diff", "source": "deterministic_core", "details": comparison}
    ]
    return result


@mcp.tool(
    description=(
        "Run deterministic 2D structural-frame screening and return solver evidence. "
        "The result is engineering triage, not a structural-safety certification."
    )
)
def frame_analyze(
    contract: dict[str, Any],
    auto_repair: bool = False,
) -> dict[str, Any]:
    source = StructuralFrameContract.model_validate(contract)
    return run_frame_design(source, auto_repair=auto_repair).model_dump(mode="json")


@mcp.tool(
    description=(
        "Normalize a strict Rhino/Grasshopper frame exchange into millimetres without "
        "inferring units, datum, or topology."
    )
)
def frame_rhino_adapt(exchange: dict[str, Any]) -> dict[str, Any]:
    return adapt_rhino_frame_exchange(exchange).model_dump(mode="json")


@mcp.tool(
    description=(
        "Normalize a Rhino/Grasshopper frame exchange, preserve source object IDs, run "
        "deterministic screening, serialize and independently reopen DXF, and return a "
        "bundle only when every identity and verification gate passes."
    )
)
def frame_rhino_roundtrip(exchange: RhinoFrameExchange) -> FrameRhinoRoundTripResponse:
    return run_frame_rhino_roundtrip(exchange)


@mcp.tool(
    description=(
        "Generate a structural-frame DXF, reopen it independently, remeasure all entities, "
        "and combine that evidence with deterministic frame screening."
    )
)
def frame_dxf_generate_verify(contract: dict[str, Any]) -> dict[str, Any]:
    source = StructuralFrameContract.model_validate(contract)
    return run_frame_cad_assurance(source).model_dump(mode="json")


@mcp.tool(
    description=(
        "Run the advisory GraphSAGE ensemble. OOD or uncertainty returns REVIEW_REQUIRED; "
        "this tool never grants engineering approval."
    )
)
def frame_surrogate_predict(contract: dict[str, Any]) -> dict[str, Any]:
    source = StructuralFrameContract.model_validate(contract)
    return predict_frame_surrogate(source).model_dump(mode="json")


@mcp.tool(
    description=(
        "Return immutable NumPy-versus-OpenSeesPy parity evidence packaged with DatumGuard."
    )
)
def frame_opensees_parity_evidence() -> dict[str, Any]:
    try:
        return load_opensees_parity_report()
    except FrameResearchEvidenceError as exc:
        return {
            "status": "UNAVAILABLE",
            "authoritative": False,
            "safety_certification": False,
            "error": {"code": exc.code, "message": exc.message},
        }


@mcp.tool(
    description=(
        "Recompute a structural frame and propose bounded changes to declared free section "
        "properties. The proposal is not applied and is not safety approval."
    )
)
def frame_repair_propose(contract: dict[str, Any]) -> dict[str, Any]:
    source = StructuralFrameContract.model_validate(contract)
    validation = validate_frame_contract(source)
    if validation.status.value != "ready":
        result = validation.model_dump(mode="json")
        result["proposal"] = None
        return result
    normalized_contract = validation.normalized_contract
    if normalized_contract is None:
        raise AssertionError("ready frame validation must include a normalized contract")

    try:
        analysis = solve_frame(normalized_contract)
    except FrameSolverError as exc:
        result = _base_envelope(validation.contract_hash, status="infeasible")
        result["violations"] = [
            {
                "code": exc.code,
                "message": exc.message,
                "entity_ids": exc.entity_ids,
                "constraint_id": None,
                "repairable": False,
                "details": exc.details,
            }
        ]
        result["error"] = {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "correlation_id": validation.contract_hash.removeprefix("sha256:")[:12],
        }
        result["proposal"] = None
        return result

    proposal = propose_frame_repair(normalized_contract, analysis)
    result = _base_envelope(proposal.contract_hash, status=proposal.status)
    result["violations"] = [item.model_dump(mode="json") for item in proposal.violations]
    result["evidence"] = [
        {
            "type": "frame_repair_screening",
            "source": analysis.solver,
            "details": {
                "critical_member_id": analysis.critical_member_id,
                "max_displacement_node_id": analysis.max_displacement_node_id,
                "proposal_applied": False,
                "safety_certification": False,
            },
        }
    ]
    result["proposal"] = proposal.model_dump(mode="json")
    return result


@mcp.tool(description="Regenerate, independently verify, and write an approved bundle locally.")
def export_bundle(
    contract: dict[str, Any],
    workspace: str,
    auto_repair: bool = True,
) -> dict[str, Any]:
    source = _contract(contract)
    if isinstance(source, StructuralFrameContract):
        frame_response = run_frame_design(source, auto_repair=False)
        result = _frame_tool_unsupported(source, tool_name="export_bundle")
        result["artifact_hash"] = frame_response.artifact_hash
        result["measurements"] = [
            item.model_dump(mode="json") for item in frame_response.measurements
        ]
        result["violations"] = [item.model_dump(mode="json") for item in frame_response.violations]
        result["evidence"] = [item.model_dump(mode="json") for item in frame_response.evidence]
        result["summary"] = frame_response.summary
        result["preview_svg"] = frame_response.preview_svg
        result["bundle_path"] = None
        return result
    if isinstance(source, ArchitecturalPlanContract):
        architecture_response = run_architecture_design(source, auto_repair=auto_repair)
        result = architecture_response.model_dump(mode="json")
    elif isinstance(source, PipingPlanContract):
        piping_response = run_piping_design(source)
        result = piping_response.model_dump(mode="json")
    else:
        plate_response = run_design(source, auto_repair=auto_repair)
        result = plate_response.model_dump(mode="json")
    if result["status"] != "passed" or result["bundle_base64"] is None:
        return result

    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_directory = root / ".datumguard" / "runs" / str(result["contract_hash"])[7:19]
    run_directory.mkdir(parents=True, exist_ok=True)
    resolved_run_directory = run_directory.resolve()
    if not resolved_run_directory.is_relative_to(root) or resolved_run_directory.is_symlink():
        raise ValueError("workspace path escapes the approved root")
    bundle_path = resolved_run_directory / "datumguard-verified.zip"
    bundle_path.write_bytes(base64.b64decode(str(result["bundle_base64"])))
    result["bundle_path"] = str(bundle_path)
    result["bundle_base64"] = None
    return result


@mcp.tool(description="Report Rhino preview availability as secondary evidence only.")
def rhino_preview(
    contract_hash: str,
    artifact_hash: str,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    design_kind = "plate_panel"
    resolved_contract_hash = contract_hash
    if contract is not None:
        source = _contract(contract)
        design_kind = _contract_kind(source)
        if isinstance(source, ArchitecturalPlanContract):
            resolved_contract_hash = validate_architecture_contract(source).contract_hash
        elif isinstance(source, PipingPlanContract):
            resolved_contract_hash = validate_piping_contract(source).contract_hash
        elif isinstance(source, StructuralFrameContract):
            resolved_contract_hash = validate_frame_contract(source).contract_hash
        else:
            resolved_contract_hash = validate_contract(source).contract_hash

        if contract_hash != resolved_contract_hash:
            result = _base_envelope(resolved_contract_hash, status="infeasible")
            result["artifact_hash"] = artifact_hash
            result["error"] = {
                "code": "DG_INPUT_INVALID",
                "message": "contract_hash가 전달된 contract의 canonical hash와 다릅니다.",
                "details": {
                    "design_kind": design_kind,
                    "provided_contract_hash": contract_hash,
                    "resolved_contract_hash": resolved_contract_hash,
                },
                "correlation_id": artifact_hash.removeprefix("sha256:")[:12],
            }
            return result

    result = _base_envelope(resolved_contract_hash, status="cross_kernel_mismatch")
    result["artifact_hash"] = artifact_hash
    result["evidence"] = [
        {
            "type": "rhino_availability",
            "source": "datumguard_mcp",
            "details": {
                "design_kind": design_kind,
                "secondary": True,
                "enabled": False,
                "official_verifier_affected": False,
                "reason": "Connect an allowlisted local RhinoMCP adapter to enable preview.",
            },
        }
    ]
    result["error"] = {
        "code": "DG_CROSS_KERNEL_MISMATCH",
        "message": "Rhino adapter is not connected; official DXF verification is unchanged.",
        "details": {
            "design_kind": design_kind,
            "official_verifier_affected": False,
        },
        "correlation_id": artifact_hash.removeprefix("sha256:")[:12],
    }
    return result


def main() -> None:
    transport = os.getenv("DATUMGUARD_MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("DATUMGUARD_MCP_TRANSPORT must be stdio, sse, or streamable-http")
    mcp.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()

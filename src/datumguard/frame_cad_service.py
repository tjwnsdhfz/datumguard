from __future__ import annotations

import base64
import uuid
from typing import Any

from pydantic import Field

from .frame_dxf import (
    FrameDxfGenerationError,
    FrameDxfVerificationResult,
    generate_frame_dxf,
    verify_frame_dxf,
)
from .frame_models import FrameRunResponse, StructuralFrameContract
from .frame_service import run_frame_design, validate_frame_contract
from .models import ContractStatus, ErrorInfo, Evidence, RunStatus, StrictModel, Violation


class FrameCadRunResponse(StrictModel):
    status: RunStatus
    contract_hash: str
    artifact_hash: str | None = None
    dxf_base64: str | None = None
    verification: FrameDxfVerificationResult | None = None
    analysis: FrameRunResponse | None = None
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    error: ErrorInfo | None = None


def _error(code: str, message: str, details: dict[str, Any] | None = None) -> ErrorInfo:
    return ErrorInfo(
        code=code,
        message=message,
        details=details or {},
        correlation_id=str(uuid.uuid4()),
    )


def run_frame_cad_assurance(contract: StructuralFrameContract) -> FrameCadRunResponse:
    """Run exact screening and an independent serialized-DXF round trip.

    A generated DXF is never sufficient for PASS. The exact frame analysis and the
    independent ezdxf re-open verifier must both pass. The response remains screening
    evidence and is never a structural-safety certification or construction approval.
    """

    validation = validate_frame_contract(contract)
    if validation.status is not ContractStatus.READY or validation.normalized_contract is None:
        return FrameCadRunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            violations=validation.violations,
            evidence=validation.evidence,
            summary={
                "dxf_written": False,
                "dxf_reopened": False,
                "screening_only": True,
                "safety_certification": False,
            },
            error=_error(
                "DG_FRAME_CAD_CONTRACT_NOT_READY",
                "The structural frame contract is not ready for serialized DXF assurance.",
                {"violation_codes": [item.code for item in validation.violations]},
            ),
        )

    normalized = validation.normalized_contract
    analysis = run_frame_design(normalized, auto_repair=False)
    try:
        dxf_bytes = generate_frame_dxf(normalized)
    except FrameDxfGenerationError as exc:
        return FrameCadRunResponse(
            status=RunStatus.FAILED,
            contract_hash=validation.contract_hash,
            analysis=analysis,
            violations=analysis.violations,
            evidence=analysis.evidence,
            summary={
                "dxf_written": False,
                "dxf_reopened": False,
                "screening_only": True,
                "safety_certification": False,
            },
            error=_error("DG_FRAME_DXF_GENERATION_FAILED", str(exc)),
        )

    verification = verify_frame_dxf(
        normalized,
        dxf_bytes,
        expected_contract_hash=validation.contract_hash,
    )
    exact_passed = analysis.status is RunStatus.PASSED
    dxf_passed = verification.status is RunStatus.PASSED
    passed = exact_passed and dxf_passed
    violations = [*analysis.violations, *verification.violations]
    evidence = [
        *analysis.evidence,
        *verification.evidence,
        Evidence(
            type="frame_cad_assurance_gate",
            source="datumguard_frame_cad_service",
            details={
                "exact_solver_passed": exact_passed,
                "independent_dxf_verifier_passed": dxf_passed,
                "screening_pass": passed,
                "safety_certification": False,
                "construction_approval": False,
                "fail_closed": True,
            },
        ),
    ]
    return FrameCadRunResponse(
        status=RunStatus.PASSED if passed else RunStatus.FAILED,
        contract_hash=validation.contract_hash,
        artifact_hash=verification.artifact_hash,
        dxf_base64=(base64.b64encode(dxf_bytes).decode("ascii") if passed else None),
        verification=verification,
        analysis=analysis,
        violations=violations,
        evidence=evidence,
        summary={
            "dxf_written": True,
            "dxf_reopened": True,
            "dxf_verified": dxf_passed,
            "exact_solver_passed": exact_passed,
            "screening_pass": passed,
            "download_eligible": passed,
            "coordinate_tolerance_mm": 0.001,
            "screening_only": True,
            "safety_certification": False,
            "construction_approval": False,
        },
    )


__all__ = ["FrameCadRunResponse", "run_frame_cad_assurance"]

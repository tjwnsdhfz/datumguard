from __future__ import annotations

import base64
import uuid
from typing import Any

from pydantic import Field, ValidationError

from .frame_artifacts import (
    FrameRoundTripArtifactError,
    FrameRoundTripManifest,
    build_frame_roundtrip_bundle,
)
from .frame_cad_service import run_frame_cad_assurance
from .frame_dxf import FrameDxfVerificationResult
from .frame_models import FrameRunResponse, StructuralFrameContract
from .frame_rhino_adapter import (
    RhinoAdapterResult,
    RhinoFrameExchange,
    adapt_rhino_frame_exchange,
)
from .models import (
    ContractStatus,
    ErrorInfo,
    Evidence,
    Measurement,
    RunStatus,
    StrictModel,
    Violation,
)


class FrameRhinoRoundTripResponse(StrictModel):
    status: ContractStatus | RunStatus
    exchange_hash: str
    contract_hash: str | None = None
    artifact_hash: str | None = None
    bundle_hash: str | None = None
    manifest_hash: str | None = None
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    normalized_exchange: RhinoFrameExchange | None = None
    normalized_contract: StructuralFrameContract | None = None
    analysis: FrameRunResponse | None = None
    verification: FrameDxfVerificationResult | None = None
    dxf_base64: str | None = None
    bundle_base64: str | None = None
    manifest: FrameRoundTripManifest | None = None
    error: ErrorInfo | None = None


def _error(code: str, message: str, details: dict[str, Any] | None = None) -> ErrorInfo:
    return ErrorInfo(
        code=code,
        message=message,
        details=details or {},
        correlation_id=str(uuid.uuid4()),
    )


def _policy_violations(exchange: RhinoFrameExchange) -> list[Violation]:
    violations: list[Violation] = []
    if not exchange.supports:
        violations.append(
            Violation(
                code="DG_FRAME_RHINO_SUPPORT_REQUIRED",
                message="A round trip requires explicit support objects and restraint values.",
            )
        )
    for support in exchange.supports:
        missing_fields = sorted({"ux", "uy", "rz"} - support.model_fields_set)
        if missing_fields or not (support.ux or support.uy or support.rz):
            violations.append(
                Violation(
                    code="DG_FRAME_RHINO_SUPPORT_INVALID",
                    message="Each support must explicitly define at least one active restraint.",
                    entity_ids=[support.id],
                    details={"missing_fields": missing_fields},
                )
            )

    if not exchange.loads:
        violations.append(
            Violation(
                code="DG_FRAME_RHINO_LOAD_REQUIRED",
                message="A round trip requires explicit load objects and load components.",
            )
        )
    for load in exchange.loads:
        missing_fields = sorted({"fx_n", "fy_n", "mz_n_document_unit"} - load.model_fields_set)
        if missing_fields or not any(
            value != 0.0 for value in (load.fx_n, load.fy_n, load.mz_n_document_unit)
        ):
            violations.append(
                Violation(
                    code="DG_FRAME_RHINO_LOAD_INVALID",
                    message="Each load must explicitly define a non-zero load component.",
                    entity_ids=[load.id],
                    details={"missing_fields": missing_fields},
                )
            )

    missing_source_ids = [item.id for item in exchange.members if item.source_object_id is None]
    missing_source_ids.extend(
        item.id for item in exchange.supports if item.source_object_id is None
    )
    missing_source_ids.extend(item.id for item in exchange.loads if item.source_object_id is None)
    missing_source_ids.sort()
    if missing_source_ids:
        violations.append(
            Violation(
                code="DG_FRAME_RHINO_PROVENANCE_REQUIRED",
                message=(
                    "Every member, support, and load requires an explicit Rhino source object ID."
                ),
                entity_ids=missing_source_ids,
            )
        )
    return violations


def _adapter_failure(adapter: RhinoAdapterResult) -> FrameRhinoRoundTripResponse:
    code = adapter.violations[0].code if adapter.violations else "DG_FRAME_RHINO_ADAPT_FAILED"
    message = (
        adapter.violations[0].message
        if adapter.violations
        else "The Rhino exchange could not be normalized."
    )
    return FrameRhinoRoundTripResponse(
        status=adapter.status,
        exchange_hash=adapter.exchange_hash,
        contract_hash=adapter.contract_hash,
        normalized_exchange=adapter.normalized_exchange,
        normalized_contract=adapter.structural_contract,
        violations=adapter.violations,
        evidence=adapter.evidence,
        summary={
            "exchange_normalized": adapter.normalized_exchange is not None,
            "contract_validated": adapter.status is ContractStatus.READY,
            "dxf_written": False,
            "dxf_reopened": False,
            "bundle_created": False,
            "screening_only": True,
            "safety_certification": False,
            "construction_approval": False,
        },
        error=_error(code, message),
    )


def run_frame_rhino_roundtrip(
    payload: RhinoFrameExchange | dict[str, Any],
) -> FrameRhinoRoundTripResponse:
    """Normalize Rhino input, screen it, serialize DXF, reopen it, and gate a bundle."""

    try:
        exchange_for_policy = (
            payload
            if isinstance(payload, RhinoFrameExchange)
            else RhinoFrameExchange.model_validate(payload)
        )
    except ValidationError:
        exchange_for_policy = None
    policy_violations = (
        _policy_violations(exchange_for_policy) if exchange_for_policy is not None else []
    )
    adapter = adapt_rhino_frame_exchange(payload, provenance_bound=True)
    if policy_violations:
        return FrameRhinoRoundTripResponse(
            status=RunStatus.FAILED,
            exchange_hash=adapter.exchange_hash,
            contract_hash=adapter.contract_hash,
            normalized_exchange=adapter.normalized_exchange or exchange_for_policy,
            normalized_contract=adapter.structural_contract,
            violations=[*policy_violations, *adapter.violations],
            evidence=[
                *adapter.evidence,
                Evidence(
                    type="frame_rhino_roundtrip_gate",
                    source="datumguard_frame_roundtrip_service",
                    details={"passed": False, "fail_closed": True},
                ),
            ],
            summary={
                "exchange_normalized": adapter.normalized_exchange is not None,
                "contract_validated": adapter.status is ContractStatus.READY,
                "provenance_complete": False,
                "dxf_written": False,
                "dxf_reopened": False,
                "bundle_created": False,
                "screening_only": True,
                "safety_certification": False,
                "construction_approval": False,
            },
            error=_error(
                policy_violations[0].code,
                "The Rhino exchange failed the explicit round-trip input gate.",
                {"violation_codes": [item.code for item in policy_violations]},
            ),
        )
    if (
        adapter.status is not ContractStatus.READY
        or adapter.normalized_exchange is None
        or adapter.structural_contract is None
        or adapter.contract_hash is None
    ):
        return _adapter_failure(adapter)

    exchange = adapter.normalized_exchange
    contract = adapter.structural_contract
    policy_violations = []
    provenance = contract.provenance
    if (
        provenance is None
        or not provenance.complete
        or provenance.exchange_hash != adapter.exchange_hash
        or provenance.source_document_id != exchange.document.document_id
    ):
        policy_violations.append(
            Violation(
                code="DG_FRAME_RHINO_PROVENANCE_MISMATCH",
                message="Normalized contract provenance does not match the source exchange.",
                details={
                    "exchange_hash": adapter.exchange_hash,
                    "contract_exchange_hash": (
                        provenance.exchange_hash if provenance is not None else None
                    ),
                    "source_document_id": exchange.document.document_id,
                    "contract_source_document_id": (
                        provenance.source_document_id if provenance is not None else None
                    ),
                },
            )
        )
    if policy_violations:
        return FrameRhinoRoundTripResponse(
            status=RunStatus.FAILED,
            exchange_hash=adapter.exchange_hash,
            contract_hash=adapter.contract_hash,
            normalized_exchange=exchange,
            normalized_contract=contract,
            violations=policy_violations,
            evidence=[
                *adapter.evidence,
                Evidence(
                    type="frame_rhino_roundtrip_gate",
                    source="datumguard_frame_roundtrip_service",
                    details={"passed": False, "fail_closed": True},
                ),
            ],
            summary={
                "exchange_normalized": True,
                "contract_validated": True,
                "provenance_complete": False,
                "dxf_written": False,
                "dxf_reopened": False,
                "bundle_created": False,
                "screening_only": True,
                "safety_certification": False,
                "construction_approval": False,
            },
            error=_error(
                policy_violations[0].code,
                "The Rhino exchange failed the explicit round-trip input gate.",
                {"violation_codes": [item.code for item in policy_violations]},
            ),
        )

    cad = run_frame_cad_assurance(contract)
    verification = cad.verification
    analysis = cad.analysis
    verification_measurements = verification.measurements if verification is not None else []
    measurements = [
        *(analysis.measurements if analysis is not None else []),
        *verification_measurements,
    ]
    if (
        cad.status is not RunStatus.PASSED
        or cad.dxf_base64 is None
        or cad.artifact_hash is None
        or verification is None
        or analysis is None
    ):
        return FrameRhinoRoundTripResponse(
            status=RunStatus.FAILED,
            exchange_hash=adapter.exchange_hash,
            contract_hash=adapter.contract_hash,
            artifact_hash=cad.artifact_hash,
            measurements=measurements,
            violations=cad.violations,
            evidence=[*adapter.evidence, *cad.evidence],
            summary={
                **cad.summary,
                "exchange_normalized": True,
                "contract_validated": True,
                "provenance_complete": True,
                "bundle_created": False,
                "screening_only": True,
                "safety_certification": False,
                "construction_approval": False,
            },
            normalized_exchange=exchange,
            normalized_contract=contract,
            analysis=analysis,
            verification=verification,
            error=cad.error
            or _error(
                "DG_FRAME_RHINO_ROUNDTRIP_BLOCKED",
                "The exact screening or independent DXF verification did not pass.",
            ),
        )

    dxf_bytes = base64.b64decode(cad.dxf_base64, validate=True)
    try:
        bundle = build_frame_roundtrip_bundle(
            exchange=exchange,
            exchange_hash=adapter.exchange_hash,
            contract=contract,
            contract_hash=adapter.contract_hash,
            dxf_bytes=dxf_bytes,
            verification=verification,
            analysis=analysis,
        )
    except (FrameRoundTripArtifactError, ValueError) as exc:
        violation = Violation(
            code="DG_FRAME_RHINO_BUNDLE_IDENTITY_MISMATCH",
            message="The round-trip evidence chain failed before bundle creation.",
            details={"reason": str(exc)},
        )
        return FrameRhinoRoundTripResponse(
            status=RunStatus.FAILED,
            exchange_hash=adapter.exchange_hash,
            contract_hash=adapter.contract_hash,
            artifact_hash=cad.artifact_hash,
            measurements=measurements,
            violations=[*cad.violations, violation],
            evidence=[*adapter.evidence, *cad.evidence],
            summary={**cad.summary, "bundle_created": False, "fail_closed": True},
            normalized_exchange=exchange,
            normalized_contract=contract,
            analysis=analysis,
            verification=verification,
            error=_error(violation.code, violation.message, violation.details),
        )

    return FrameRhinoRoundTripResponse(
        status=RunStatus.PASSED,
        exchange_hash=adapter.exchange_hash,
        contract_hash=adapter.contract_hash,
        artifact_hash=cad.artifact_hash,
        bundle_hash=bundle.bundle_hash,
        manifest_hash=bundle.manifest_hash,
        measurements=measurements,
        violations=[],
        evidence=[
            *adapter.evidence,
            *cad.evidence,
            Evidence(
                type="frame_rhino_roundtrip_chain",
                source="datumguard_frame_roundtrip_service",
                details={
                    "exchange_hash": adapter.exchange_hash,
                    "contract_hash": adapter.contract_hash,
                    "artifact_hash": cad.artifact_hash,
                    "manifest_hash": bundle.manifest_hash,
                    "bundle_hash": bundle.bundle_hash,
                    "provenance_verified": True,
                    "screening_only": True,
                    "safety_certification": False,
                },
            ),
        ],
        summary={
            **cad.summary,
            "exchange_normalized": True,
            "contract_validated": True,
            "provenance_complete": True,
            "provenance_verified": True,
            "bundle_created": True,
            "screening_only": True,
            "safety_certification": False,
            "construction_approval": False,
        },
        normalized_exchange=exchange,
        normalized_contract=contract,
        analysis=analysis,
        verification=verification,
        dxf_base64=cad.dxf_base64,
        bundle_base64=base64.b64encode(bundle.bundle_bytes).decode("ascii"),
        manifest=bundle.manifest,
    )


__all__ = ["FrameRhinoRoundTripResponse", "run_frame_rhino_roundtrip"]

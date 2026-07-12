from __future__ import annotations

import base64
import os
import re
from collections.abc import Callable
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from . import __version__
from .architecture_models import ArchitecturalPlanContract
from .architecture_service import run_architecture_design, validate_architecture_contract
from .artifact_service import MAX_ARTIFACT_BYTES, audit_artifact, compare_artifacts
from .frame_cad_service import run_frame_cad_assurance
from .frame_models import StructuralFrameContract
from .frame_research_evidence import (
    FrameResearchEvidenceError,
    load_gnn_benchmark,
    load_opensees_parity_report,
)
from .frame_rhino_adapter import RhinoFrameExchange, adapt_rhino_frame_exchange
from .frame_service import run_frame_design, validate_frame_contract
from .frame_surrogate import predict_frame_surrogate
from .models import DesignContract, RepairProposal, StrictModel, Violation
from .openbim_service import (
    MAX_IDS_BYTES,
    MAX_IFC_BYTES,
    MAX_OPENBIM_TOTAL_BYTES,
    OpenBimServiceFailure,
    run_openbim_evidence,
)
from .operations import (
    DEFAULT_MAX_BODY_BYTES,
    OPERATIONS,
    OperationalMiddleware,
    current_request_id,
    make_error_content,
)
from .piping_models import PipingPlanContract
from .piping_service import run_piping_design, validate_piping_contract
from .repair import RepairRejected
from .service import (
    ServiceFailure,
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

MAX_BODY_BYTES = DEFAULT_MAX_BODY_BYTES


def _release_sha() -> str:
    """Return a public deployment revision without trusting arbitrary values."""
    for name in ("DATUMGUARD_RELEASE_SHA", "RENDER_GIT_COMMIT"):
        value = os.getenv(name, "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{40}", value):
            return value
    return "unknown"


class DraftRequest(StrictModel):
    contract: DesignContract
    intent_text: str | None = Field(default=None, max_length=2000)


class VerifyRequest(StrictModel):
    contract: DesignContract
    dxf_base64: str = Field(min_length=1, max_length=8_000_000)


class RepairProposeRequest(StrictModel):
    contract: DesignContract
    violations: list[Violation] = Field(max_length=250)
    iteration: int = Field(default=1, ge=1, le=4)


class RepairApplyRequest(StrictModel):
    contract: DesignContract
    proposal: RepairProposal


class CompareRequest(StrictModel):
    baseline: DesignContract
    candidate: DesignContract


def _origins() -> list[str]:
    defaults = ["http://localhost:3000", "http://127.0.0.1:3000"]
    configured = [
        item.strip() for item in os.getenv("DATUMGUARD_CORS_ORIGINS", "").split(",") if item.strip()
    ]
    return sorted(set(defaults + configured))


def _origin_regex() -> str | None:
    configured = os.getenv("DATUMGUARD_CORS_ORIGIN_REGEX", "").strip()
    return configured or None


app = FastAPI(
    title="DatumGuard API",
    version=__version__,
    description=(
        "Contract-first architecture, plant piping, plate, 3D solid generation, and "
        "deterministic structural-frame screening with independent serialized-DXF/STEP "
        "remeasurement and DXF/STEP/IFC artifact audit. Frame results support engineering "
        "triage only; this MVP does not certify structural safety, codes, or industrial "
        "standards."
    ),
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(OperationalMiddleware, controls=OPERATIONS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_origin_regex=_origin_regex(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization", "X-API-Key", "X-Request-ID"],
    expose_headers=["Retry-After", "X-Request-ID"],
)
app.add_middleware(GZipMiddleware, minimum_size=1200)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or current_request_id())


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retry_after: int | None = None,
) -> JSONResponse:
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(
        status_code=status_code,
        content=make_error_content(
            _request_id(request),
            code=code,
            message=message,
            details=details,
        ),
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = [
        {
            "location": [str(item) for item in error["loc"]],
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        status_code=422,
        code="DG_INPUT_INVALID",
        message="요청이 DesignContract 스키마를 통과하지 못했습니다.",
        details={"errors": errors},
    )


@app.exception_handler(ServiceFailure)
async def service_exception_handler(request: Request, exc: ServiceFailure) -> JSONResponse:
    return _error_response(
        request,
        status_code=422,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    return _error_response(
        request,
        status_code=500,
        code="DG_INTERNAL_ERROR",
        message="요청을 안전하게 완료하지 못했습니다.",
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "DatumGuard API",
        "version": __version__,
        "release_sha": _release_sha(),
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "datumguard",
        "version": __version__,
        "release_sha": _release_sha(),
    }


@app.get("/api/v1/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok", "service": "datumguard", "check": "liveness"}


@app.get("/api/v1/ready")
async def readiness() -> JSONResponse:
    gate = OPERATIONS.gate.snapshot()
    ready = gate.ready
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "service": "datumguard",
            "version": __version__,
            "release_sha": _release_sha(),
            "queue": {
                "limit": gate.limit,
                "active": gate.active,
                "waiting": gate.waiting,
                "max_waiters": gate.max_waiters,
                "wait_timeout_seconds": gate.wait_timeout_seconds,
            },
        },
        headers={} if ready else {"Retry-After": "2"},
    )


@app.get("/api/v1/metrics")
async def metrics() -> dict[str, Any]:
    return OPERATIONS.metrics_snapshot()


@app.get("/api/v1/domains")
def engineering_domains() -> list[dict[str, str]]:
    domains = [
        {
            "id": "architecture",
            "design_kind": "architectural_plan",
            "web_route": "/",
            "run_endpoint": "/api/v1/architecture/designs/run",
        },
        {
            "id": "plant_piping",
            "design_kind": "piping_plan",
            "web_route": "/piping",
            "run_endpoint": "/api/v1/piping/designs/run",
        },
        {
            "id": "mechanical_ship_plate",
            "design_kind": "plate_panel",
            "web_route": "/plate",
            "run_endpoint": "/api/v1/designs/run",
        },
        {
            "id": "solid_part",
            "design_kind": "solid_part",
            "web_route": "/solid",
            "run_endpoint": "/api/v1/solid/designs/run",
        },
        {
            "id": "structural_frame",
            "design_kind": "structural_frame",
            "web_route": "/frame",
            "run_endpoint": "/api/v1/frame/designs/run",
        },
        {
            "id": "artifact_lab",
            "design_kind": "artifact_audit",
            "web_route": "/intake",
            "run_endpoint": "/api/v1/artifacts/audit",
        },
        {
            "id": "openbim_evidence",
            "design_kind": "openbim_evidence",
            "web_route": "/openbim",
            "run_endpoint": "/api/v1/openbim/evidence/run",
        },
    ]
    if not OPERATIONS.solid_enabled:
        domains = [item for item in domains if item["id"] != "solid_part"]
    if not OPERATIONS.artifact_lab_enabled:
        domains = [item for item in domains if item["id"] != "artifact_lab"]
    if not OPERATIONS.openbim_enabled:
        domains = [item for item in domains if item["id"] != "openbim_evidence"]
    return domains


@app.get("/api/v1/schema/design-contract")
def design_contract_schema() -> dict[str, Any]:
    return DesignContract.model_json_schema()


@app.get("/api/v1/schema/architectural-plan-contract")
def architectural_plan_contract_schema() -> dict[str, Any]:
    return ArchitecturalPlanContract.model_json_schema()


@app.get("/api/v1/architecture/schema")
def architecture_schema_alias() -> dict[str, Any]:
    return ArchitecturalPlanContract.model_json_schema()


@app.get("/api/v1/schema/piping-plan-contract")
def piping_plan_contract_schema() -> dict[str, Any]:
    return PipingPlanContract.model_json_schema()


@app.get("/api/v1/piping/schema")
def piping_schema_alias() -> dict[str, Any]:
    return PipingPlanContract.model_json_schema()


@app.get("/api/v1/schema/solid-part-contract")
def solid_part_contract_schema() -> dict[str, Any]:
    return SolidPartContract.model_json_schema()


@app.get("/api/v1/schema/frame-contract")
def frame_contract_schema() -> dict[str, Any]:
    """Return the public contract for deterministic structural-frame screening."""
    return StructuralFrameContract.model_json_schema()


@app.get("/api/v1/schema/rhino-frame-exchange")
def rhino_frame_exchange_schema() -> dict[str, Any]:
    """Return the neutral Rhino/Grasshopper exchange contract."""
    return RhinoFrameExchange.model_json_schema()


@app.post("/api/v1/contracts/draft")
def contract_draft(request: DraftRequest) -> dict[str, Any]:
    return draft_contract(request.contract, request.intent_text).model_dump(mode="json")


@app.post("/api/v1/contracts/validate")
def contract_validate(contract: DesignContract) -> dict[str, Any]:
    return validate_contract(contract).model_dump(mode="json")


@app.post("/api/v1/architecture/contracts/validate")
def architecture_contract_validate(contract: ArchitecturalPlanContract) -> dict[str, Any]:
    return validate_architecture_contract(contract).model_dump(mode="json")


@app.post("/api/v1/piping/contracts/validate")
def piping_contract_validate(contract: PipingPlanContract) -> dict[str, Any]:
    return validate_piping_contract(contract).model_dump(mode="json")


@app.post("/api/v1/frame/contracts/validate")
def frame_contract_validate(contract: StructuralFrameContract) -> dict[str, Any]:
    return validate_frame_contract(contract).model_dump(mode="json")


@app.post("/api/v1/frame/rhino/adapt")
def frame_rhino_adapt(exchange: RhinoFrameExchange) -> dict[str, Any]:
    """Normalize explicit Rhino units and datum into a structural frame contract."""
    return adapt_rhino_frame_exchange(exchange).model_dump(mode="json")


@app.post("/api/v1/drawings/generate")
def drawing_generate(contract: DesignContract) -> dict[str, Any]:
    return generate_only(contract).model_dump(mode="json")


@app.post("/api/v1/drawings/verify")
def drawing_verify(request: VerifyRequest) -> dict[str, Any]:
    try:
        dxf_bytes = base64.b64decode(request.dxf_base64, validate=True)
    except ValueError as exc:
        raise ServiceFailure("DG_INPUT_INVALID", "dxf_base64가 유효하지 않습니다.", {}) from exc
    return verify_only(request.contract, dxf_bytes).as_dict()


@app.post("/api/v1/repairs/propose")
def repair_proposal(request: RepairProposeRequest) -> dict[str, Any]:
    return propose_repair(
        request.contract,
        request.violations,
        iteration=request.iteration,
    ).model_dump(mode="json")


@app.post("/api/v1/repairs/apply")
def repair_application(request: RepairApplyRequest) -> dict[str, Any]:
    try:
        repaired = apply_repair(request.contract, request.proposal)
    except RepairRejected as exc:
        raise ServiceFailure("DG_CONTRACT_INFEASIBLE", str(exc), {}) from exc
    return {
        "status": "ready",
        "contract_hash": validate_contract(repaired).contract_hash,
        "artifact_hash": None,
        "measurements": [],
        "violations": [],
        "evidence": [],
        "contract": repaired.model_dump(mode="json"),
        "error": None,
    }


@app.post("/api/v1/drawings/compare")
def drawing_compare(request: CompareRequest) -> dict[str, Any]:
    comparison = compare_contracts(request.baseline, request.candidate)
    return {
        "status": "ready",
        "contract_hash": comparison["candidate_hash"],
        "artifact_hash": None,
        "measurements": [],
        "violations": [],
        "evidence": [
            {"type": "contract_diff", "source": "deterministic_core", "details": comparison}
        ],
        "comparison": comparison,
        "error": None,
    }


@app.post("/api/v1/designs/run")
def design_run(
    contract: DesignContract,
    auto_repair: bool = Query(default=True),
) -> dict[str, Any]:
    return run_design(contract, auto_repair=auto_repair).model_dump(mode="json")


@app.post("/api/v1/architecture/designs/run")
def architecture_design_run(
    contract: ArchitecturalPlanContract,
    auto_repair: bool = Query(default=True),
) -> dict[str, Any]:
    return run_architecture_design(contract, auto_repair=auto_repair).model_dump(mode="json")


@app.post("/api/v1/piping/designs/run")
def piping_design_run(contract: PipingPlanContract) -> dict[str, Any]:
    return run_piping_design(contract).model_dump(mode="json")


@app.post("/api/v1/frame/designs/run")
def frame_design_run(
    contract: StructuralFrameContract,
    auto_repair: bool = Query(default=False),
) -> dict[str, Any]:
    """Screen a frame; the response is not a structural-safety certification."""
    return run_frame_design(contract, auto_repair=auto_repair).model_dump(mode="json")


@app.post("/api/v1/frame/cad/run")
def frame_cad_run(contract: StructuralFrameContract) -> dict[str, Any]:
    """Write, reopen, and remeasure a screening DXF before allowing download."""
    return run_frame_cad_assurance(contract).model_dump(mode="json")


@app.post("/api/v1/frame/surrogate/predict")
def frame_surrogate_predict(contract: StructuralFrameContract) -> dict[str, Any]:
    """Return a non-authoritative GNN estimate with an uncertainty review gate."""
    return predict_frame_surrogate(contract).model_dump(mode="json")


def _packaged_frame_evidence(
    loader: Callable[[], dict[str, Any]],
    *,
    evidence_kind: str,
) -> dict[str, Any]:
    try:
        report = loader()
        if "status" not in report:
            report["status"] = "COMPLETED"
        return report
    except FrameResearchEvidenceError as exc:
        return {
            "status": "UNAVAILABLE",
            "evidence_kind": evidence_kind,
            "authoritative": False,
            "safety_certification": False,
            "error": {"code": exc.code, "message": exc.message},
        }


@app.get("/api/v1/frame/benchmarks/opensees")
def frame_opensees_benchmark() -> dict[str, Any]:
    """Serve immutable parity evidence without loading OpenSees in production."""
    return _packaged_frame_evidence(
        load_opensees_parity_report,
        evidence_kind="frame_opensees_parity_v1",
    )


@app.get("/api/v1/frame/benchmarks/gnn")
def frame_gnn_benchmark() -> dict[str, Any]:
    """Serve the topology-holdout GraphSAGE/GAT comparison artifact."""
    return _packaged_frame_evidence(
        load_gnn_benchmark,
        evidence_kind="frame_gnn_benchmark_v1",
    )


@app.post("/api/v1/solid/designs/run", response_model=None)
def solid_design_run(
    request: Request,
    contract: SolidPartContract,
) -> dict[str, Any] | JSONResponse:
    if not OPERATIONS.solid_enabled:
        return _error_response(
            request,
            status_code=503,
            code="DG_CAPABILITY_DISABLED",
            message="요청한 CAD 기능이 이 배포에서 비활성화되어 있습니다.",
            details={"capability": "solid"},
            retry_after=60,
        )
    return run_solid_design(contract).model_dump(mode="json")


async def _read_upload_limited(file: UploadFile, *, max_bytes: int) -> bytes:
    data = bytearray()
    while len(data) <= max_bytes:
        remaining = max_bytes + 1 - len(data)
        chunk = await file.read(min(64 * 1024, remaining))
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


@app.post("/api/v1/artifacts/audit", response_model=None)
async def artifact_audit(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any] | JSONResponse:
    if not OPERATIONS.artifact_lab_enabled:
        return _error_response(
            request,
            status_code=503,
            code="DG_CAPABILITY_DISABLED",
            message="요청한 CAD 기능이 이 배포에서 비활성화되어 있습니다.",
            details={"capability": "artifact_lab"},
            retry_after=60,
        )
    data = await _read_upload_limited(file, max_bytes=MAX_ARTIFACT_BYTES)
    if len(data) > MAX_ARTIFACT_BYTES:
        return _error_response(
            request,
            status_code=413,
            code="DG_ARTIFACT_TOO_LARGE",
            message="CAD 파일 크기가 서버 제한을 초과했습니다.",
            details={"max_bytes": MAX_ARTIFACT_BYTES},
        )
    result = await run_in_threadpool(audit_artifact, file.filename or "artifact", data)
    return result.model_dump(mode="json")


@app.post("/api/v1/artifacts/compare", response_model=None)
async def artifact_compare(
    request: Request,
    baseline: Annotated[UploadFile, File()],
    candidate: Annotated[UploadFile, File()],
) -> dict[str, Any] | JSONResponse:
    if not OPERATIONS.artifact_lab_enabled:
        return _error_response(
            request,
            status_code=503,
            code="DG_CAPABILITY_DISABLED",
            message="요청한 CAD 기능이 이 배포에서 비활성화되어 있습니다.",
            details={"capability": "artifact_lab"},
            retry_after=60,
        )
    baseline_data = await _read_upload_limited(baseline, max_bytes=MAX_ARTIFACT_BYTES)
    candidate_data = await _read_upload_limited(candidate, max_bytes=MAX_ARTIFACT_BYTES)
    if len(baseline_data) > MAX_ARTIFACT_BYTES or len(candidate_data) > MAX_ARTIFACT_BYTES:
        return _error_response(
            request,
            status_code=413,
            code="DG_ARTIFACT_TOO_LARGE",
            message="비교할 CAD 파일 중 서버 제한을 초과한 파일이 있습니다.",
            details={"max_bytes_per_file": MAX_ARTIFACT_BYTES},
        )
    total_bytes = len(baseline_data) + len(candidate_data)
    if total_bytes > OPERATIONS.max_upload_total_bytes:
        return _error_response(
            request,
            status_code=413,
            code="DG_ARTIFACT_TOO_LARGE",
            message="비교할 CAD 파일의 합계 크기가 서버 제한을 초과했습니다.",
            details={"max_total_bytes": OPERATIONS.max_upload_total_bytes},
        )
    result = await run_in_threadpool(
        compare_artifacts,
        baseline.filename or "baseline",
        baseline_data,
        candidate.filename or "candidate",
        candidate_data,
    )
    return result.model_dump(mode="json")


@app.post("/api/v1/openbim/evidence/run", response_model=None)
async def openbim_evidence_run(
    request: Request,
    baseline: Annotated[UploadFile, File()],
    candidate: Annotated[UploadFile, File()],
    requirements: Annotated[UploadFile, File()],
    profile_id: Annotated[str, Form()],
    include_html: Annotated[bool, Form()] = True,
    include_bcf: Annotated[bool, Form()] = False,
) -> dict[str, Any] | JSONResponse:
    if not OPERATIONS.openbim_enabled:
        return _error_response(
            request,
            status_code=503,
            code="DG_CAPABILITY_DISABLED",
            message="요청한 CAD 기능이 이 배포에서 비활성화되어 있습니다.",
            details={"capability": "openbim"},
            retry_after=60,
        )
    if include_bcf and not OPERATIONS.bcf_enabled:
        return _error_response(
            request,
            status_code=503,
            code="DG_CAPABILITY_DISABLED",
            message="BCF packaging is disabled in this deployment.",
            details={"capability": "openbim_bcf"},
            retry_after=60,
        )
    filenames = {
        "baseline": baseline.filename or "",
        "candidate": candidate.filename or "",
        "requirements": requirements.filename or "",
    }
    invalid_fields = [
        field
        for field, filename in filenames.items()
        if not filename.lower().endswith(".ifc" if field != "requirements" else ".ids")
    ]
    if invalid_fields:
        return _error_response(
            request,
            status_code=422,
            code="DG_OPENBIM_INPUT_INVALID",
            message="IFC baseline/candidate와 IDS requirements 파일이 필요합니다.",
            details={"invalid_fields": invalid_fields},
        )
    baseline_data = await _read_upload_limited(baseline, max_bytes=MAX_IFC_BYTES)
    candidate_data = await _read_upload_limited(candidate, max_bytes=MAX_IFC_BYTES)
    requirements_data = await _read_upload_limited(requirements, max_bytes=MAX_IDS_BYTES)
    sizes = {
        "baseline": len(baseline_data),
        "candidate": len(candidate_data),
        "requirements": len(requirements_data),
    }
    limit_by_field = {
        "baseline": MAX_IFC_BYTES,
        "candidate": MAX_IFC_BYTES,
        "requirements": MAX_IDS_BYTES,
    }
    oversized = [field for field, size in sizes.items() if size > limit_by_field[field]]
    total_bytes = sum(sizes.values())
    # OpenBIM has its own 20 + 20 + 1 MiB semantic input budget. The existing
    # artifact comparison aggregate remains unchanged and does not govern this endpoint.
    max_total_bytes = MAX_OPENBIM_TOTAL_BYTES
    if oversized or total_bytes > max_total_bytes:
        return _error_response(
            request,
            status_code=413,
            code="DG_OPENBIM_TOO_LARGE",
            message="OpenBIM 입력 파일 크기가 서버 제한을 초과했습니다.",
            details={
                "oversized_fields": oversized,
                "max_ifc_bytes": MAX_IFC_BYTES,
                "max_ids_bytes": MAX_IDS_BYTES,
                "max_total_bytes": max_total_bytes,
            },
        )
    try:
        result = await run_in_threadpool(
            run_openbim_evidence,
            baseline_bytes=baseline_data,
            candidate_bytes=candidate_data,
            requirements_bytes=requirements_data,
            profile=profile_id,
            include_html=include_html,
            include_bcf=include_bcf,
        )
    except OpenBimServiceFailure as exc:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            retry_after=60 if exc.status_code == 503 else None,
        )
    return result.model_dump(mode="json")


@app.post("/api/v1/exports")
def export_bundle(
    contract: DesignContract,
    auto_repair: bool = Query(default=True),
) -> dict[str, Any]:
    # Stateless export always regenerates and independently verifies the artifact.
    return run_design(contract, auto_repair=auto_repair).model_dump(mode="json")


@app.post("/api/v1/rhino/preview")
def rhino_preview(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "status": "cross_kernel_mismatch",
            "contract_hash": "sha256:unavailable",
            "artifact_hash": None,
            "measurements": [],
            "violations": [],
            "evidence": [
                {
                    "type": "rhino_availability",
                    "source": "public_api",
                    "details": {"secondary": True, "enabled": False},
                }
            ],
            "error": {
                "code": "DG_CROSS_KERNEL_MISMATCH",
                "message": (
                    "공개 서버에서는 Rhino adapter를 실행하지 않습니다. 로컬 MCP를 사용하세요."
                ),
                "details": {"official_verifier_affected": False},
                "correlation_id": _request_id(request),
            },
        },
    )


def main() -> None:
    uvicorn.run(
        "datumguard.api:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()

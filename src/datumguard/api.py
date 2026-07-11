from __future__ import annotations

import base64
import os
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from .architecture_models import ArchitecturalPlanContract
from .architecture_service import run_architecture_design, validate_architecture_contract
from .artifact_service import MAX_ARTIFACT_BYTES, audit_artifact, compare_artifacts
from .models import DesignContract, RepairProposal, StrictModel, Violation
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
    version="0.2.0",
    description=(
        "Contract-first architecture, plant piping, plate, and 3D solid generation with "
        "independent serialized-DXF/STEP remeasurement and DXF/STEP/IFC artifact audit. "
        "This MVP does not certify structural safety, codes, or industrial standards."
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
        "version": "0.2.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "datumguard", "version": "0.2.0"}


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
            "version": "0.2.0",
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
            "id": "artifact_lab",
            "design_kind": "artifact_audit",
            "web_route": "/intake",
            "run_endpoint": "/api/v1/artifacts/audit",
        },
    ]
    if not OPERATIONS.solid_enabled:
        domains = [item for item in domains if item["id"] != "solid_part"]
    if not OPERATIONS.artifact_lab_enabled:
        domains = [item for item in domains if item["id"] != "artifact_lab"]
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

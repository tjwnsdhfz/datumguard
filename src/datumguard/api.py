from __future__ import annotations

import base64
import os
import uuid
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

MAX_BODY_BYTES = 48 * 1024 * 1024


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_origin_regex=_origin_regex(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)
app.add_middleware(GZipMiddleware, minimum_size=1200)


@app.middleware("http")
async def reject_large_body(request: Request, call_next: Any) -> Any:
    content_length = request.headers.get("content-length")
    try:
        body_too_large = bool(content_length) and int(content_length or 0) > MAX_BODY_BYTES
    except ValueError:
        body_too_large = True
    if body_too_large:
        return JSONResponse(
            status_code=413,
            content={
                "status": "failed_verification",
                "contract_hash": "sha256:unavailable",
                "artifact_hash": None,
                "measurements": [],
                "violations": [],
                "evidence": [],
                "error": {
                    "code": "DG_INPUT_INVALID",
                    "message": "요청 본문이 48MB 제한을 초과했습니다.",
                    "details": {"max_bytes": MAX_BODY_BYTES},
                    "correlation_id": str(uuid.uuid4()),
                },
            },
        )
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request,
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
    return JSONResponse(
        status_code=422,
        content={
            "status": "failed_verification",
            "contract_hash": "sha256:unavailable",
            "artifact_hash": None,
            "measurements": [],
            "violations": [],
            "evidence": [],
            "error": {
                "code": "DG_INPUT_INVALID",
                "message": "요청이 DesignContract 스키마를 통과하지 못했습니다.",
                "details": {"errors": errors},
                "correlation_id": str(uuid.uuid4()),
            },
        },
    )


@app.exception_handler(ServiceFailure)
async def service_exception_handler(_request: Request, exc: ServiceFailure) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "status": "failed_verification",
            "contract_hash": "sha256:unavailable",
            "artifact_hash": None,
            "measurements": [],
            "violations": [],
            "evidence": [],
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "correlation_id": str(uuid.uuid4()),
            },
        },
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
def health() -> dict[str, str]:
    return {"status": "ok", "service": "datumguard", "version": "0.2.0"}


@app.get("/api/v1/domains")
def engineering_domains() -> list[dict[str, str]]:
    return [
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


@app.post("/api/v1/solid/designs/run")
def solid_design_run(contract: SolidPartContract) -> dict[str, Any]:
    return run_solid_design(contract).model_dump(mode="json")


@app.post("/api/v1/artifacts/audit")
async def artifact_audit(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    data = await file.read(MAX_ARTIFACT_BYTES + 1)
    result = await run_in_threadpool(audit_artifact, file.filename or "artifact", data)
    return result.model_dump(mode="json")


@app.post("/api/v1/artifacts/compare")
async def artifact_compare(
    baseline: Annotated[UploadFile, File()],
    candidate: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    baseline_data = await baseline.read(MAX_ARTIFACT_BYTES + 1)
    candidate_data = await candidate.read(MAX_ARTIFACT_BYTES + 1)
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
def rhino_preview() -> JSONResponse:
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
                "correlation_id": str(uuid.uuid4()),
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

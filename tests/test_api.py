from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from datumguard import api as api_module
from datumguard.api import _origin_regex, app
from datumguard.models import DesignContract
from datumguard.operations import OPERATIONS, reset_operational_state_for_tests
from datumguard.service import generate_only

client = TestClient(app)


@pytest.fixture
def configure_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[..., None]]:
    def configure(**values: str) -> None:
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        reset_operational_state_for_tests()

    yield configure
    monkeypatch.undo()
    reset_operational_state_for_tests()


def test_health(monkeypatch) -> None:
    expected_sha = "a" * 40
    monkeypatch.setenv("RENDER_GIT_COMMIT", expected_sha.upper())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.2.1"
    assert response.json()["release_sha"] == expected_sha

    monkeypatch.setenv("DATUMGUARD_RELEASE_SHA", "not-a-commit")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "also-invalid")
    assert client.get("/api/v1/health").json()["release_sha"] == "unknown"


def test_liveness_readiness_and_metrics_are_public() -> None:
    assert client.get("/api/v1/live").status_code == 200
    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200
    assert ready.json()["version"] == "0.2.1"
    assert ready.json()["release_sha"] == "unknown"
    assert ready.json()["queue"]["active"] == 0

    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert set(metrics.json()["heavy"]) == {"limit", "active", "waiting", "max_waiters"}


def test_configured_cors_regex_allows_only_datumguard_vercel_previews(monkeypatch) -> None:
    pattern = r"^https://datumguard-tjwnsdhfz-[a-z0-9-]+\.vercel\.app$"
    monkeypatch.setenv("DATUMGUARD_CORS_ORIGIN_REGEX", pattern)

    preview_app = FastAPI()
    preview_app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=_origin_regex(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @preview_app.get("/health")
    def preview_health() -> dict[str, str]:
        return {"status": "ok"}

    preview_client = TestClient(preview_app)
    preview_origin = "https://datumguard-tjwnsdhfz-git-feature-tjwnsdhfzs-projects.vercel.app"
    allowed = preview_client.options(
        "/health",
        headers={
            "Origin": preview_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    denied = preview_client.options(
        "/health",
        headers={
            "Origin": "https://unrelated-project.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == preview_origin
    assert "access-control-allow-origin" not in denied.headers


def test_engineering_domain_registry_lists_all_public_workspaces() -> None:
    response = client.get("/api/v1/domains")
    assert response.status_code == 200
    payload = response.json()
    assert {item["design_kind"] for item in payload} == {
        "architectural_plan",
        "artifact_audit",
        "openbim_evidence",
        "piping_plan",
        "plate_panel",
        "solid_part",
    }
    assert {item["web_route"] for item in payload} == {
        "/",
        "/intake",
        "/openbim",
        "/piping",
        "/plate",
        "/solid",
    }


def test_artifact_audit_endpoint_accepts_real_dxf_upload(
    sample_contract: DesignContract,
) -> None:
    generated = generate_only(sample_contract)
    dxf_bytes = base64.b64decode(generated.dxf_base64)

    response = client.post(
        "/api/v1/artifacts/audit",
        files={"file": ("drawing.dxf", dxf_bytes, "image/vnd.dxf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "audited"
    assert payload["format"] == "dxf"
    assert payload["artifact_hash"].startswith("sha256:")
    assert payload["approval_eligible"] is False


def test_solid_contract_schema_is_public() -> None:
    response = client.get("/api/v1/schema/solid-part-contract")
    assert response.status_code == 200
    assert response.json()["properties"]["design_kind"]["const"] == "solid_part"


def test_run_endpoint_returns_common_envelope(sample_contract: DesignContract) -> None:
    response = client.post(
        "/api/v1/designs/run",
        json=sample_contract.model_dump(mode="json"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "passed"
    assert payload["contract_hash"].startswith("sha256:")
    assert payload["artifact_hash"].startswith("sha256:")
    assert payload["bundle_base64"]


def test_invalid_request_uses_stable_error_code() -> None:
    response = client.post("/api/v1/designs/run", json={"units": "pixels"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["status"] == "failed_verification"
    assert payload["error"]["code"] == "DG_INPUT_INVALID"


def test_request_id_is_returned_and_used_as_error_correlation_id() -> None:
    request_id = "request-test-0001"
    response = client.post(
        "/api/v1/designs/run",
        json={"units": "pixels"},
        headers={"X-Request-ID": request_id},
    )
    assert response.status_code == 422
    assert response.headers["x-request-id"] == request_id
    assert response.json()["error"]["correlation_id"] == request_id


def test_rate_limit_returns_429_retry_after_and_uses_trusted_cf_ip(
    sample_contract: DesignContract,
    configure_operations: Callable[..., None],
) -> None:
    configure_operations(DATUMGUARD_ANON_RATE_LIMIT_PER_MINUTE="1")
    route = "/api/v1/contracts/validate"
    payload = sample_contract.model_dump(mode="json")
    first_ip = {
        "CF-Ray": "aaaaaaaaaaaaaaaa-NRT",
        "CF-Connecting-IP": "203.0.113.10",
        "Origin": "http://localhost:3000",
    }
    second_ip = {
        "CF-Ray": "bbbbbbbbbbbbbbbb-NRT",
        "CF-Connecting-IP": "203.0.113.11",
    }

    assert client.post(route, json=payload, headers=first_ip).status_code == 200
    assert client.post(route, json=payload, headers=second_ip).status_code == 200
    limited = client.post(route, json=payload, headers=first_ip)

    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["x-request-id"]
    assert "Retry-After" in limited.headers["access-control-expose-headers"]
    assert "X-Request-ID" in limited.headers["access-control-expose-headers"]
    assert limited.json()["error"]["code"] == "DG_RATE_LIMITED"


def test_optional_api_key_has_separate_quota_and_invalid_keys_are_rejected(
    sample_contract: DesignContract,
    configure_operations: Callable[..., None],
) -> None:
    configure_operations(
        DATUMGUARD_API_KEYS="test-key",
        DATUMGUARD_ANON_RATE_LIMIT_PER_MINUTE="1",
        DATUMGUARD_AUTH_RATE_LIMIT_PER_MINUTE="2",
    )
    route = "/api/v1/contracts/validate"
    payload = sample_contract.model_dump(mode="json")

    invalid = client.post(route, json=payload, headers={"X-API-Key": "not-the-key"})
    assert invalid.status_code == 401
    assert "not-the-key" not in invalid.text

    headers = {"X-API-Key": "test-key"}
    assert client.post(route, json=payload, headers=headers).status_code == 200
    assert client.post(route, json=payload, headers=headers).status_code == 200
    assert client.post(route, json=payload, headers=headers).status_code == 429


def test_chunked_body_is_limited_without_content_length(
    configure_operations: Callable[..., None],
) -> None:
    configure_operations(DATUMGUARD_MAX_BODY_BYTES="1024")

    def chunks() -> Iterator[bytes]:
        yield b'{"payload":"' + (b"a" * 700)
        yield b"b" * 700 + b'"}'

    response = client.post(
        "/api/v1/contracts/validate",
        content=chunks(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "DG_INPUT_INVALID"
    assert response.headers["x-request-id"]


def test_readiness_reports_saturated_heavy_gate(
    configure_operations: Callable[..., None],
) -> None:
    configure_operations(DATUMGUARD_HEAVY_CONCURRENCY="1")
    lease = asyncio.run(OPERATIONS.gate.acquire())
    assert lease is not None
    try:
        response = client.get("/api/v1/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"
        assert response.json()["queue"]["active"] == 1
    finally:
        lease.release()


def test_capability_kill_switches_hide_domains_and_return_stable_503(
    configure_operations: Callable[..., None],
) -> None:
    configure_operations(
        DATUMGUARD_ENABLE_SOLID="false",
        DATUMGUARD_ENABLE_ARTIFACT_LAB="false",
        DATUMGUARD_ENABLE_OPENBIM="false",
    )
    domain_ids = {item["id"] for item in client.get("/api/v1/domains").json()}
    assert "solid_part" not in domain_ids
    assert "artifact_lab" not in domain_ids
    assert "openbim_evidence" not in domain_ids

    solid = client.post("/api/v1/solid/designs/run", json={})
    artifact = client.post("/api/v1/artifacts/audit")
    openbim = client.post("/api/v1/openbim/evidence/run")
    assert solid.status_code == 503
    assert artifact.status_code == 503
    assert openbim.status_code == 503
    assert solid.json()["error"]["code"] == "DG_CAPABILITY_DISABLED"
    assert artifact.json()["error"]["code"] == "DG_CAPABILITY_DISABLED"
    assert openbim.json()["error"]["code"] == "DG_CAPABILITY_DISABLED"


def test_artifact_upload_part_limit_returns_413(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_module, "MAX_ARTIFACT_BYTES", 8)
    response = client.post(
        "/api/v1/artifacts/audit",
        files={"file": ("oversize.dxf", b"123456789", "image/vnd.dxf")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "DG_ARTIFACT_TOO_LARGE"
    assert "oversize.dxf" not in response.text


def test_unhandled_exception_uses_generic_500_without_exception_details(
    sample_contract: DesignContract,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_contract: DesignContract) -> None:
        raise RuntimeError("C:/private/path must not leak")

    monkeypatch.setattr(api_module, "validate_contract", fail)
    safe_client = TestClient(app, raise_server_exceptions=False)
    response = safe_client.post(
        "/api/v1/contracts/validate",
        json=sample_contract.model_dump(mode="json"),
        headers={"X-Request-ID": "request-error-0001"},
    )

    assert response.status_code == 500
    assert response.headers["x-request-id"] == "request-error-0001"
    assert response.json()["error"]["code"] == "DG_INTERNAL_ERROR"
    assert "private/path" not in response.text

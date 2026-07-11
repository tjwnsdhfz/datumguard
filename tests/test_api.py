from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from datumguard.api import _origin_regex, app
from datumguard.models import DesignContract

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
        "piping_plan",
        "plate_panel",
    }
    assert {item["web_route"] for item in payload} == {"/", "/piping", "/plate"}


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

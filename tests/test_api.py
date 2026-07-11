from __future__ import annotations

from fastapi.testclient import TestClient

from datumguard.api import app
from datumguard.models import DesignContract

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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

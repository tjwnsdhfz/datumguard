from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from datumguard.api import app
from datumguard.operations import reset_operational_state_for_tests

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_operations() -> None:
    reset_operational_state_for_tests()


def _fixture(name: str) -> dict[str, Any]:
    path = Path(__file__).parents[1] / "fixtures" / "examples" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_common_envelope(payload: dict[str, Any]) -> None:
    assert {
        "contract_hash",
        "artifact_hash",
        "status",
        "measurements",
        "violations",
        "evidence",
        "error",
    } <= payload.keys()
    assert payload["contract_hash"].startswith("sha256:")


def test_frame_schema_exposes_explicit_screening_contract() -> None:
    response = client.get("/api/v1/schema/frame-contract")

    assert response.status_code == 200
    schema = response.json()
    assert schema["properties"]["design_kind"]["const"] == "structural_frame"
    assert schema["properties"]["units"]["const"] == "mm"
    assert {"nodes", "members", "loads", "supports", "limits", "free_parameters"} <= set(
        schema["properties"]
    )


def test_domains_registry_points_frameguard_to_public_web_and_api_routes() -> None:
    response = client.get("/api/v1/domains")

    assert response.status_code == 200
    frame_domain = next(item for item in response.json() if item["id"] == "structural_frame")
    assert frame_domain == {
        "id": "structural_frame",
        "design_kind": "structural_frame",
        "web_route": "/frame",
        "run_endpoint": "/api/v1/frame/designs/run",
    }


def test_frame_validation_returns_canonical_hash_and_normalized_contract() -> None:
    contract = _fixture("frame_pipe_rack.json")

    response = client.post("/api/v1/frame/contracts/validate", json=contract)

    assert response.status_code == 200
    payload = response.json()
    _assert_common_envelope(payload)
    assert payload["status"] == "ready"
    assert payload["artifact_hash"] is None
    assert payload["normalized_contract"]["design_kind"] == "structural_frame"
    assert payload["normalized_contract"]["contract_hash"] == payload["contract_hash"]


def test_frame_schema_error_uses_existing_structured_api_boundary() -> None:
    contract = _fixture("frame_pipe_rack.json")
    contract["units"] = "inch"

    response = client.post("/api/v1/frame/contracts/validate", json=contract)

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "DG_INPUT_INVALID"
    assert payload["error"]["correlation_id"]


def test_frame_run_endpoint_returns_explainable_pass_evidence() -> None:
    response = client.post(
        "/api/v1/frame/designs/run?auto_repair=false",
        json=_fixture("frame_pipe_rack.json"),
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_common_envelope(payload)
    assert payload["status"] == "passed"
    assert payload["artifact_hash"].startswith("sha256:")
    assert payload["summary"]
    assert payload["timeline"]
    assert payload["preview_svg"].lstrip().startswith("<svg")
    assert payload["evidence"]
    assert payload["error"] is None


def test_frame_run_endpoint_blocks_failure_fixture() -> None:
    response = client.post(
        "/api/v1/frame/designs/run?auto_repair=false",
        json=_fixture("frame_pipe_rack_failure.json"),
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_common_envelope(payload)
    assert payload["status"] != "passed"
    assert payload["violations"]
    assert all(item["code"].startswith("DG_FRAME_") for item in payload["violations"])


def test_openapi_keeps_frameguard_outside_safety_certification() -> None:
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    document = response.json()
    description = document["info"]["description"].lower()
    assert "screening" in description
    assert "does not certify structural safety" in description
    assert "/api/v1/frame/designs/run" in document["paths"]

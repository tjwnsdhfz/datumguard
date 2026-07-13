from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from datumguard.api import app
from datumguard.operations import HEAVY_PATHS, _normalized_route

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "examples"
client = TestClient(app)


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_rhino_exchange_schema_and_adapter_are_public() -> None:
    schema_response = client.get("/api/v1/schema/rhino-frame-exchange")
    assert schema_response.status_code == 200
    schema = schema_response.json()
    assert schema["properties"]["design_kind"]["const"] == "structural_frame_exchange"

    response = client.post(
        "/api/v1/frame/rhino/adapt",
        json=_fixture("frame_rhino_exchange.json"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["exchange_hash"].startswith("sha256:")
    assert payload["contract_hash"].startswith("sha256:")
    assert payload["structural_contract"]["units"] == "mm"


def test_rhino_adapter_requires_explicit_supported_units() -> None:
    exchange = _fixture("frame_rhino_exchange.json")
    exchange["document"]["units"] = "unset"  # type: ignore[index]
    response = client.post("/api/v1/frame/rhino/adapt", json=exchange)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_confirmation"
    assert payload["structural_contract"] is None
    assert payload["violations"][0]["code"] == "DG_FRAME_RHINO_UNIT_CONFIRMATION_REQUIRED"


def test_nonfinite_frame_and_rhino_scalars_are_rejected_at_schema_boundary() -> None:
    exchange = _fixture("frame_rhino_exchange.json")
    exchange["sections"][0]["area"] = float("inf")  # type: ignore[index]
    exchange_response = client.post(
        "/api/v1/frame/rhino/adapt",
        content=json.dumps(exchange, allow_nan=True),
        headers={"content-type": "application/json"},
    )
    assert exchange_response.status_code == 422

    contract = _fixture("frame_pipe_rack.json")
    contract["members"][0]["area_mm2"] = float("inf")  # type: ignore[index]
    contract_response = client.post(
        "/api/v1/frame/designs/run",
        content=json.dumps(contract, allow_nan=True),
        headers={"content-type": "application/json"},
    )
    assert contract_response.status_code == 422


def test_rhino_adapter_has_bounded_heavy_operation_controls() -> None:
    path = "/api/v1/frame/rhino/adapt"
    assert path in HEAVY_PATHS
    assert _normalized_route(path) == path
    assert "/api/v1/frame/rhino/roundtrip" in HEAVY_PATHS
    assert _normalized_route("/api/v1/frame/rhino/roundtrip") == ("/api/v1/frame/rhino/roundtrip")
    assert _normalized_route("/api/v1/frame/benchmarks/opensees") != "/other"


def test_frame_cad_endpoint_returns_only_reopened_verified_download() -> None:
    response = client.post(
        "/api/v1/frame/cad/run",
        json=_fixture("frame_pipe_rack.json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "passed"
    assert payload["dxf_base64"]
    assert payload["verification"]["status"] == "passed"
    assert payload["summary"]["download_eligible"] is True
    assert payload["summary"]["construction_approval"] is False


def test_frame_cad_endpoint_blocks_failed_screening() -> None:
    response = client.post(
        "/api/v1/frame/cad/run",
        json=_fixture("frame_pipe_rack_failure.json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed_verification"
    assert payload["dxf_base64"] is None
    assert payload["verification"]["status"] == "passed"
    assert payload["summary"]["download_eligible"] is False


def test_surrogate_endpoint_never_returns_authoritative_approval() -> None:
    response = client.post(
        "/api/v1/frame/surrogate/predict",
        json=_fixture("frame_pipe_rack.json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"PREDICTED", "REVIEW_REQUIRED"}
    assert payload["authoritative"] is False
    assert payload["exact_solver_required"] is True
    assert payload["input_hash"].startswith("sha256:")


def test_packaged_opensees_evidence_is_available_without_live_runtime() -> None:
    response = client.get("/api/v1/frame/benchmarks/opensees")

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_kind"] == "frame_opensees_parity_v1"
    assert payload["status"] == "PASSED"
    assert payload["summary"]["failed_count"] == 0
    assert "not a structural safety certification" in " ".join(payload["claims"]).lower()


def test_packaged_gnn_benchmark_reports_topology_holdout_without_authority() -> None:
    response = client.get("/api/v1/frame/benchmarks/gnn")

    assert response.status_code == 200
    payload = response.json()
    assert payload["benchmark_kind"] == "frame_gnn_benchmark_v1"
    assert payload["status"] == "COMPLETED"
    assert payload["split"]["case_id_leakage"] == 0
    assert payload["split"]["contract_hash_leakage"] == 0
    assert {"graphsage", "gat"} <= set(payload["models"])
    assert payload["claims"]["is_authoritative_pass_source"] is False
    assert payload["claims"]["is_safety_certification"] is False


def test_openapi_includes_complete_frame_assurance_surface() -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert {
        "/api/v1/schema/rhino-frame-exchange",
        "/api/v1/frame/rhino/adapt",
        "/api/v1/frame/cad/run",
        "/api/v1/frame/surrogate/predict",
        "/api/v1/frame/benchmarks/opensees",
        "/api/v1/frame/benchmarks/gnn",
    } <= set(paths)

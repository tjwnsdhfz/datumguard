from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import read
from fastapi.testclient import TestClient

from datumguard.api import app
from datumguard.models import ContractStatus, RunStatus
from datumguard.piping_artifacts import PIPING_DXF_LAYERS, generate_piping_drawing
from datumguard.piping_core import compute_piping_hash, normalize_piping_to_mm
from datumguard.piping_models import PipingPlanContract
from datumguard.piping_service import run_piping_design, validate_piping_contract
from datumguard.piping_verifier import verify_piping_dxf


def fixture_payload(name: str = "piping_utility.json") -> dict[str, Any]:
    path = Path(__file__).parents[1] / "fixtures" / "examples" / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def piping_contract() -> PipingPlanContract:
    return PipingPlanContract.model_validate(fixture_payload())


@pytest.mark.parametrize(
    ("fixture_name", "expected_status", "expected_code"),
    [
        ("piping_utility.json", RunStatus.PASSED, None),
        (
            "piping_clearance_failure.json",
            RunStatus.FAILED,
            "DG_PIPE_CLEARANCE_VIOLATION",
        ),
    ],
)
def test_public_piping_fixtures(
    fixture_name: str,
    expected_status: RunStatus,
    expected_code: str | None,
) -> None:
    contract = PipingPlanContract.model_validate(fixture_payload(fixture_name))
    result = run_piping_design(contract)
    assert result.status == expected_status
    assert result.summary["summary_source"] == "independent_serialized_dxf_remeasurement"
    assert result.summary["total_route_length_mm"] == 12000.0
    if expected_code is None:
        assert result.bundle_base64 is not None
        assert result.summary["maximum_support_gap_mm"] == 2000.0
    else:
        assert result.bundle_base64 is None
        assert expected_code in {item.code for item in result.violations}


def test_piping_contract_normalizes_and_hashes_canonically(
    piping_contract: PipingPlanContract,
) -> None:
    normalized = normalize_piping_to_mm(piping_contract)
    assert normalized.units == "mm"
    validation = validate_piping_contract(piping_contract)
    assert validation.status == ContractStatus.READY
    assert validation.contract_hash.startswith("sha256:")
    assert validation.normalized_contract is not None


def test_piping_inch_contract_has_same_hash(piping_contract: PipingPlanContract) -> None:
    data = piping_contract.model_dump(mode="python")
    data["units"] = "inch"
    scale = 1 / 25.4
    data["datum"]["origin"] = [value * scale for value in data["datum"]["origin"]]
    for node in data["nodes"]:
        node["point"] = [value * scale for value in node["point"]]
    for segment in data["segments"]:
        segment["nominal_diameter"] *= scale
    for component in data["components"]:
        component["offset"] *= scale
        if component["type"] == "reducer":
            component["inlet_diameter"] *= scale
            component["outlet_diameter"] *= scale
    for support in data["supports"]:
        support["offset"] *= scale
    for zone in data["equipment_zones"]:
        zone["minimum_clearance"] *= scale
        if zone["type"] == "rectangle":
            zone["origin"] = [value * scale for value in zone["origin"]]
            zone["width"] *= scale
            zone["height"] *= scale
        else:
            zone["center"] = [value * scale for value in zone["center"]]
            zone["diameter"] *= scale
    for dimension in data["dimensions"]:
        dimension["target"] *= scale
        dimension["tolerance_lower"] *= scale
        dimension["tolerance_upper"] *= scale
    for constraint in data["constraints"]:
        for key in ("tolerance", "maximum_spacing", "minimum_clearance"):
            if key in constraint["parameters"]:
                constraint["parameters"][key] *= scale
    inch_contract = PipingPlanContract.model_validate(data)
    assert compute_piping_hash(inch_contract) == compute_piping_hash(piping_contract)


def test_verified_piping_run_contains_native_artifacts(
    piping_contract: PipingPlanContract,
) -> None:
    response = run_piping_design(piping_contract)
    assert response.status == RunStatus.PASSED
    assert response.bundle_base64 is not None
    assert response.artifact_hash is not None
    assert all(item.passed for item in response.measurements)
    assert response.evidence[-1].details["writer_geometry_reused"] is False

    with zipfile.ZipFile(io.BytesIO(base64.b64decode(response.bundle_base64))) as bundle:
        assert set(bundle.namelist()) == {
            "manifest.json",
            "piping-plan-contract.json",
            "piping-plan-do-not-scale.pdf",
            "piping-plan.dxf",
            "preview.svg",
            "verification.json",
        }
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["design_kind"] == "piping_plan"
        assert manifest["approval"] == "passed"
        assert bundle.read("piping-plan-do-not-scale.pdf").startswith(b"%PDF")
        document = read(io.StringIO(bundle.read("piping-plan.dxf").decode("utf-8")))
        assert document.dxfversion == "AC1027"
        assert set(PIPING_DXF_LAYERS) <= {layer.dxf.name for layer in document.layers}
        xdata_values = [
            tag.value
            for entity in document.modelspace()
            for tag in entity.get_xdata("DATUMGUARD")
            if tag.code == 1000
        ]
        assert "design_kind=piping_plan" in xdata_values


def test_serialized_piping_hash_tamper_is_independently_rejected(
    piping_contract: PipingPlanContract,
) -> None:
    normalized = normalize_piping_to_mm(piping_contract)
    contract_hash = compute_piping_hash(normalized)
    drawing = generate_piping_drawing(normalized, contract_hash)
    tampered = drawing.dxf_bytes.replace(contract_hash.encode(), b"sha256:" + b"0" * 64)
    verification = verify_piping_dxf(normalized, tampered, contract_hash)
    assert verification.status == RunStatus.FAILED
    assert "DG_CONTRACT_HASH_MISMATCH" in {item.code for item in verification.violations}


def test_piping_api_schema_validate_and_run(piping_contract: PipingPlanContract) -> None:
    client = TestClient(app)
    for path in ("/api/v1/schema/piping-plan-contract", "/api/v1/piping/schema"):
        schema = client.get(path)
        assert schema.status_code == 200
        assert "PipingPlanContract" in json.dumps(schema.json())

    payload = piping_contract.model_dump(mode="json")
    validation = client.post("/api/v1/piping/contracts/validate", json=payload)
    assert validation.status_code == 200
    assert validation.json()["status"] == "ready"
    run = client.post("/api/v1/piping/designs/run", json=payload)
    assert run.status_code == 200
    assert run.json()["status"] == "passed"
    assert run.json()["summary"]["segments"] == 3
    assert run.json()["bundle_base64"]


def test_support_spacing_includes_segment_endpoint_gaps() -> None:
    data = fixture_payload()
    data["supports"] = [item for item in data["supports"] if item["id"] != "support-6"]
    result = run_piping_design(PipingPlanContract.model_validate(data))
    assert result.status == RunStatus.FAILED
    violations = [
        item for item in result.violations if item.code == "DG_PIPE_SUPPORT_SPACING_EXCEEDED"
    ]
    assert violations
    assert violations[0].details["endpoint_gaps_included"] is True


def test_nonorthogonal_route_and_duplicate_geometry_are_rejected() -> None:
    nonorthogonal = fixture_payload()
    nonorthogonal["dimensions"] = []
    nonorthogonal["nodes"][1]["point"] = [4000, 100]
    result = run_piping_design(PipingPlanContract.model_validate(nonorthogonal))
    assert "DG_PIPE_NON_ORTHOGONAL" in {item.code for item in result.violations}

    duplicate = fixture_payload()
    duplicate["segments"].append(
        {
            "id": "seg-duplicate",
            "start_node_id": "n1",
            "end_node_id": "n2",
            "nominal_diameter": 50,
            "service_code": "CDA",
        }
    )
    result = run_piping_design(PipingPlanContract.model_validate(duplicate))
    assert "DG_PIPE_DUPLICATE_GEOMETRY" in {item.code for item in result.violations}


def test_design_kind_is_strict_piping_discriminator() -> None:
    data = fixture_payload()
    data["design_kind"] = "utility_route"
    with pytest.raises(ValueError):
        PipingPlanContract.model_validate(data)

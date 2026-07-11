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
from datumguard.architecture_artifacts import (
    ARCHITECTURE_DXF_LAYERS,
    generate_architecture_drawing,
)
from datumguard.architecture_core import (
    compute_architecture_hash,
    normalize_architecture_to_mm,
)
from datumguard.architecture_models import ArchitecturalPlanContract
from datumguard.architecture_service import (
    run_architecture_design,
    validate_architecture_contract,
)
from datumguard.architecture_verifier import verify_architecture_dxf
from datumguard.models import ContractStatus, RunStatus


def architecture_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "design_kind": "architectural_plan",
        "units": "mm",
        "datum": {
            "id": "datum-main",
            "origin": [0, 0],
            "x_axis": [1, 0],
            "y_axis": [0, 1],
            "plane": "XY",
            "locked": True,
        },
        "grids": [
            {
                "id": "grid-a",
                "label": "A",
                "start": [5000, -500],
                "end": [5000, 8500],
                "axis": "x",
                "locked": True,
            }
        ],
        "walls": [
            {
                "id": "wall-1",
                "start": [0, 0],
                "end": [10000, 0],
                "thickness": 200,
                "wall_type": "exterior",
            },
            {
                "id": "wall-2",
                "start": [10000, 0],
                "end": [10000, 8000],
                "thickness": 200,
                "wall_type": "exterior",
            },
            {
                "id": "wall-3",
                "start": [10000, 8000],
                "end": [0, 8000],
                "thickness": 200,
                "wall_type": "exterior",
            },
            {
                "id": "wall-4",
                "start": [0, 8000],
                "end": [0, 0],
                "thickness": 200,
                "wall_type": "exterior",
            },
        ],
        "openings": [
            {
                "id": "door-1",
                "type": "door",
                "wall_id": "wall-1",
                "offset": 4550,
                "width": 900,
                "height": 2100,
            }
        ],
        "columns": [
            {
                "id": "column-1",
                "type": "circular_column",
                "center": [5000, 4000],
                "diameter": 400,
            }
        ],
        "room_seeds": [{"id": "room-1", "name": "Main room", "point": [5000, 4000]}],
        "dimensions": [
            {
                "id": "dim-wall-length",
                "path": "walls.wall-1.length",
                "target": 10000,
                "tolerance_lower": -0.1,
                "tolerance_upper": 0.1,
                "locked": True,
            },
            {
                "id": "dim-door-width",
                "path": "openings.door-1.width",
                "target": 900,
                "tolerance_lower": -0.1,
                "tolerance_upper": 0.1,
                "locked": True,
            },
        ],
        "constraints": [
            {
                "id": "constraint-column-grid",
                "type": "column_grid_alignment",
                "entity_ids": ["column-1"],
                "parameters": {"tolerance": 1.0},
                "required": True,
            }
        ],
        "free_parameters": [],
        "drawing_profile": {
            "id": "architecture-profile-default",
            "sheet_size": "A3",
            "scale_denominator": 100,
            "include_dimensions": True,
            "include_room_labels": True,
            "title_block": True,
        },
        "metadata": {"project_name": "Architecture fixture", "revision": "A", "notes": ""},
    }


@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    [
        ("architecture_studio.json", RunStatus.PASSED),
        ("architecture_open_loop.json", RunStatus.FAILED),
    ],
)
def test_public_architecture_fixtures(
    fixture_name: str,
    expected_status: RunStatus,
) -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "examples" / fixture_name
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    contract = ArchitecturalPlanContract.model_validate(payload)
    result = run_architecture_design(contract)
    assert result.status == expected_status
    if expected_status == RunStatus.PASSED:
        assert result.summary["summary_source"] == ("independent_serialized_dxf_remeasurement")
        assert result.summary["gross_area_m2"] == 96.0
        assert [room["area_m2"] for room in result.summary["room_areas"]] == [
            32.0,
            32.0,
            32.0,
        ]


@pytest.fixture
def architecture_contract() -> ArchitecturalPlanContract:
    return ArchitecturalPlanContract.model_validate(architecture_payload())


def violation_codes(contract: ArchitecturalPlanContract) -> set[str]:
    return {item.code for item in run_architecture_design(contract).violations}


def test_architecture_contract_normalizes_and_hashes_canonically(
    architecture_contract: ArchitecturalPlanContract,
) -> None:
    normalized = normalize_architecture_to_mm(architecture_contract)
    assert normalized.units == "mm"
    assert compute_architecture_hash(architecture_contract) == compute_architecture_hash(
        architecture_contract
    )
    validation = validate_architecture_contract(architecture_contract)
    assert validation.status == ContractStatus.READY
    assert validation.contract_hash.startswith("sha256:")
    assert validation.normalized_contract is not None


def test_architecture_inch_contract_has_same_hash(
    architecture_contract: ArchitecturalPlanContract,
) -> None:
    data = architecture_contract.model_dump(mode="python")
    data["units"] = "inch"
    scale = 1 / 25.4
    data["datum"]["origin"] = [value * scale for value in data["datum"]["origin"]]
    for collection in ("grids", "walls"):
        for item in data[collection]:
            item["start"] = [value * scale for value in item["start"]]
            item["end"] = [value * scale for value in item["end"]]
    for wall in data["walls"]:
        wall["thickness"] *= scale
    for opening in data["openings"]:
        opening["offset"] *= scale
        opening["width"] *= scale
        opening["height"] *= scale
    for column in data["columns"]:
        column["center"] = [value * scale for value in column["center"]]
        column["diameter"] *= scale
    for room in data["room_seeds"]:
        room["point"] = [value * scale for value in room["point"]]
    for dimension in data["dimensions"]:
        dimension["target"] *= scale
        dimension["tolerance_lower"] *= scale
        dimension["tolerance_upper"] *= scale
    data["constraints"][0]["parameters"]["tolerance"] *= scale
    inch_contract = ArchitecturalPlanContract.model_validate(data)
    assert compute_architecture_hash(inch_contract) == compute_architecture_hash(
        architecture_contract
    )


def test_verified_architecture_run_contains_native_artifacts(
    architecture_contract: ArchitecturalPlanContract,
) -> None:
    response = run_architecture_design(architecture_contract)
    assert response.status == RunStatus.PASSED
    assert response.bundle_base64 is not None
    assert response.artifact_hash is not None
    assert all(item.passed for item in response.measurements)
    assert "writer_geometry_reused" in response.evidence[-1].details
    assert response.evidence[-1].details["writer_geometry_reused"] is False

    with zipfile.ZipFile(io.BytesIO(base64.b64decode(response.bundle_base64))) as bundle:
        assert set(bundle.namelist()) == {
            "architectural-plan-contract.json",
            "architectural-plan-do-not-scale.pdf",
            "architectural-plan.dxf",
            "manifest.json",
            "preview.svg",
            "verification.json",
        }
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["design_kind"] == "architectural_plan"
        assert manifest["approval"] == "passed"
        document = read(io.StringIO(bundle.read("architectural-plan.dxf").decode("utf-8")))
        assert document.dxfversion == "AC1027"
        assert set(ARCHITECTURE_DXF_LAYERS) <= {layer.dxf.name for layer in document.layers}
        xdata = [
            tag.value
            for entity in document.modelspace()
            for tag in entity.get_xdata("DATUMGUARD")
            if tag.code == 1000
        ]
        assert "design_kind=architectural_plan" in xdata


def test_serialized_dxf_hash_tamper_is_independently_rejected(
    architecture_contract: ArchitecturalPlanContract,
) -> None:
    normalized = normalize_architecture_to_mm(architecture_contract)
    contract_hash = compute_architecture_hash(normalized)
    drawing = generate_architecture_drawing(normalized, contract_hash)
    tampered = drawing.dxf_bytes.replace(contract_hash.encode(), b"sha256:" + b"0" * 64)
    verification = verify_architecture_dxf(normalized, tampered, contract_hash)
    assert verification.status == RunStatus.FAILED
    assert "DG_CONTRACT_HASH_MISMATCH" in {item.code for item in verification.violations}


def test_architecture_api_schema_validate_and_run(
    architecture_contract: ArchitecturalPlanContract,
) -> None:
    client = TestClient(app)
    schema = client.get("/api/v1/schema/architectural-plan-contract")
    assert schema.status_code == 200
    assert "ArchitecturalPlanContract" in json.dumps(schema.json())

    payload = architecture_contract.model_dump(mode="json")
    validation = client.post("/api/v1/architecture/contracts/validate", json=payload)
    assert validation.status_code == 200
    assert validation.json()["status"] == "ready"
    run = client.post("/api/v1/architecture/designs/run", json=payload)
    assert run.status_code == 200
    assert run.json()["status"] == "passed"
    assert run.json()["summary"]["walls"] == 4
    assert run.json()["bundle_base64"]


def test_opening_outside_and_overlap_block_official_bundle() -> None:
    data = architecture_payload()
    data["openings"][0]["offset"] = 9700
    data["openings"].append(
        {
            "id": "door-2",
            "type": "door",
            "wall_id": "wall-1",
            "offset": 9750,
            "width": 200,
        }
    )
    response = run_architecture_design(ArchitecturalPlanContract.model_validate(data))
    assert response.status == RunStatus.FAILED
    assert response.bundle_base64 is None
    codes = {item.code for item in response.violations}
    assert "DG_ARCH_OPENING_OUTSIDE_HOST" in codes
    assert "DG_ARCH_OPENING_OVERLAP" in codes


def test_exterior_loop_connectivity_room_and_duplicate_errors() -> None:
    data = architecture_payload()
    data["walls"] = data["walls"][:-1]
    data["walls"].append(
        {
            "id": "wall-isolated",
            "start": [20000, 20000],
            "end": [21000, 20000],
            "thickness": 200,
            "wall_type": "interior",
        }
    )
    data["columns"].append(
        {
            "id": "column-duplicate",
            "type": "circular_column",
            "center": [5000, 4000],
            "diameter": 400,
        }
    )
    codes = violation_codes(ArchitecturalPlanContract.model_validate(data))
    assert "DG_ARCH_EXTERIOR_OPEN" in codes
    assert "DG_ARCH_WALL_DISCONNECTED" in codes
    assert "DG_ARCH_ROOM_UNRESOLVED" in codes
    assert "DG_ARCH_DUPLICATE_GEOMETRY" in codes


def test_column_grid_misalignment_is_reported() -> None:
    data = architecture_payload()
    data["columns"][0]["center"] = [5200, 4000]
    codes = violation_codes(ArchitecturalPlanContract.model_validate(data))
    assert "DG_ARCH_COLUMN_OFF_GRID" in codes


def test_design_kind_is_strict_public_discriminator() -> None:
    data = architecture_payload()
    data["design_kind"] = "architecture"
    with pytest.raises(ValueError):
        ArchitecturalPlanContract.model_validate(data)

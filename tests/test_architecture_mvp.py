from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from ezdxf import units
from ezdxf.document import Drawing
from ezdxf.filemanagement import read
from fastapi.testclient import TestClient

from datumguard.api import app
from datumguard.architecture_artifacts import (
    ARCHITECTURE_DXF_LAYERS,
    generate_architecture_drawing,
)
from datumguard.architecture_core import compute_architecture_hash, normalize_architecture_to_mm
from datumguard.architecture_models import ArchitecturalPlanContract
from datumguard.architecture_service import run_architecture_design, validate_architecture_contract
from datumguard.architecture_verifier import verify_architecture_dxf
from datumguard.models import RunStatus


def payload(name: str = "architecture_four_room.json") -> dict[str, Any]:
    fixture = Path(__file__).parents[1] / "fixtures" / "examples" / name
    return json.loads(fixture.read_text(encoding="utf-8"))


def serialize(document: Drawing) -> bytes:
    stream = io.StringIO(newline="\n")
    document.write(stream, fmt="asc")
    return stream.getvalue().encode("utf-8")


def xdata(entity: Any) -> dict[str, str]:
    return {
        str(tag.value).split("=", 1)[0]: str(tag.value).split("=", 1)[1]
        for tag in entity.get_xdata("DATUMGUARD")
        if tag.code == 1000 and "=" in str(tag.value)
    }


@pytest.mark.parametrize("case_index", range(20))
def test_twenty_valid_architecture_golden_cases(case_index: int) -> None:
    data = payload()
    data["metadata"]["revision"] = f"V{case_index + 1:02d}"
    data["openings"][0]["offset"] = 800 + (case_index % 5) * 100
    result = run_architecture_design(
        ArchitecturalPlanContract.model_validate(data),
        auto_repair=False,
    )
    assert result.status == RunStatus.PASSED
    assert result.summary["gross_area_m2"] == 96.0
    assert [item["area_m2"] for item in result.summary["room_areas"]] == [
        24.0,
        24.0,
        24.0,
        24.0,
    ]
    assert all(item["closed"] for item in result.summary["room_areas"])


@pytest.mark.parametrize(
    ("case_index", "expected_code"),
    [
        (0, "DG_ARCH_EXTERIOR_OPEN"),
        (1, "DG_ARCH_WALL_DISCONNECTED"),
        (2, "DG_ARCH_OPENING_OUTSIDE_HOST"),
        (3, "DG_ARCH_OPENING_OVERLAP"),
        (4, "DG_ARCH_COLUMN_OFF_GRID"),
        (5, "DG_ARCH_ROOM_UNRESOLVED"),
        (6, "DG_ARCH_DUPLICATE_GEOMETRY"),
        (7, "DG_ARCH_EXTERIOR_OPEN"),
        (8, "DG_ARCH_OPENING_OUTSIDE_HOST"),
        (9, "DG_ARCH_COLUMN_OFF_GRID"),
    ],
)
def test_ten_invalid_architecture_golden_cases(case_index: int, expected_code: str) -> None:
    data = payload("architecture_open_300mm.json") if case_index in {0, 7} else payload()
    if case_index == 1:
        data["walls"].append(
            {
                "id": "wall-isolated",
                "start": [20000, 20000],
                "end": [21000, 20000],
                "thickness": 100,
                "wall_type": "interior",
                "locked": True,
            }
        )
    elif case_index == 2:
        data["openings"][0]["offset"] = 11900
    elif case_index == 3:
        data["openings"].append(
            {
                "id": "door-overlap",
                "type": "door",
                "wall_id": "wall-south",
                "offset": 1500,
                "width": 1000,
                "height": 2100,
                "swing": "left",
            }
        )
    elif case_index in {4, 9}:
        data["columns"][0]["center"] = [6200, 4200]
    elif case_index == 5:
        data["room_seeds"][0]["point"] = [15000, 15000]
    elif case_index == 6:
        duplicate = dict(data["columns"][0])
        duplicate["id"] = "column-duplicate"
        data["columns"].append(duplicate)
    elif case_index == 8:
        data["openings"][-1]["offset"] = 7900
    result = run_architecture_design(
        ArchitecturalPlanContract.model_validate(data),
        auto_repair=False,
    )
    assert result.bundle_base64 is None
    assert expected_code in {item.code for item in result.violations}


def test_exact_layers_xdata_and_wall_centerline_companions() -> None:
    contract = ArchitecturalPlanContract.model_validate(payload())
    validation = validate_architecture_contract(contract)
    assert validation.normalized_contract is not None
    drawing = generate_architecture_drawing(
        validation.normalized_contract,
        validation.contract_hash,
    )
    document = read(io.StringIO(drawing.dxf_bytes.decode("utf-8")))
    assert tuple(ARCHITECTURE_DXF_LAYERS) == (
        "A-GRID",
        "A-WALL",
        "A-WALL-CENTER",
        "A-DOOR",
        "A-WIND",
        "A-COLS",
        "A-ROOM",
        "A-DIMS",
        "A-ANNO",
        "DG-META",
    )
    assert set(ARCHITECTURE_DXF_LAYERS) <= {layer.dxf.name for layer in document.layers}
    required = {"contract_hash", "entity_id", "entity_type", "revision"}
    for entity in document.modelspace():
        assert required <= set(xdata(entity))
    wall_ids = {
        xdata(entity)["entity_id"]
        for entity in document.modelspace()
        if entity.dxf.layer == "A-WALL"
    }
    centerline_ids = {
        xdata(entity)["entity_id"]
        for entity in document.modelspace()
        if entity.dxf.layer == "A-WALL-CENTER"
    }
    assert wall_ids == centerline_ids
    assert (
        verify_architecture_dxf(
            validation.normalized_contract,
            drawing.dxf_bytes,
            validation.contract_hash,
        ).status
        == RunStatus.PASSED
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("unit", "DG_ARCH_DXF_UNIT_INVALID"),
        ("layer", "DG_ARCH_DXF_LAYER_INVALID"),
        ("xdata", "DG_ARCH_DXF_XDATA_MISSING"),
    ],
)
def test_serialized_dxf_mutations_are_rejected(mutation: str, expected_code: str) -> None:
    contract = normalize_architecture_to_mm(ArchitecturalPlanContract.model_validate(payload()))
    contract_hash = compute_architecture_hash(contract)
    drawing = generate_architecture_drawing(contract, contract_hash)
    document = read(io.StringIO(drawing.dxf_bytes.decode("utf-8")))
    if mutation == "unit":
        document.units = units.IN
    elif mutation == "layer":
        next(
            item for item in document.modelspace() if item.dxf.layer == "A-WALL"
        ).dxf.layer = "A-BAD"
    else:
        next(iter(document.modelspace())).discard_xdata("DATUMGUARD")
    verification = verify_architecture_dxf(contract, serialize(document), contract_hash)
    assert verification.status == RunStatus.FAILED
    assert expected_code in {item.code for item in verification.violations}


@pytest.mark.parametrize(
    ("entity_layer", "expected_code"),
    [
        ("A-WALL-CENTER", "DG_ARCH_WALL_CENTERLINE_MISMATCH"),
        ("A-DOOR", "DG_ARCH_OPENING_OUTSIDE_HOST"),
    ],
)
def test_serialized_wall_and_opening_geometry_mutations(
    entity_layer: str,
    expected_code: str,
) -> None:
    contract = normalize_architecture_to_mm(ArchitecturalPlanContract.model_validate(payload()))
    contract_hash = compute_architecture_hash(contract)
    drawing = generate_architecture_drawing(contract, contract_hash)
    document = read(io.StringIO(drawing.dxf_bytes.decode("utf-8")))
    entity = next(item for item in document.modelspace() if item.dxf.layer == entity_layer)
    entity.translate(20000, 0, 0)
    verification = verify_architecture_dxf(contract, serialize(document), contract_hash)
    assert expected_code in {item.code for item in verification.violations}


def test_architecture_hash_tamper_and_dimension_epsilon_boundary() -> None:
    data = payload()
    data["dimensions"].append(
        {
            "id": "dim-column-x",
            "path": "columns.column-center.center.0",
            "target": 6000,
            "tolerance_lower": 0,
            "tolerance_upper": 0,
            "locked": True,
        }
    )
    contract = normalize_architecture_to_mm(ArchitecturalPlanContract.model_validate(data))
    contract_hash = compute_architecture_hash(contract)
    drawing = generate_architecture_drawing(contract, contract_hash)
    tampered_hash = drawing.dxf_bytes.replace(contract_hash.encode(), b"sha256:" + b"0" * 64)
    hash_result = verify_architecture_dxf(contract, tampered_hash, contract_hash)
    assert "DG_CONTRACT_HASH_MISMATCH" in {item.code for item in hash_result.violations}

    boundary_results: list[bool] = []
    for delta in (0.001, 0.0021):
        document = read(io.StringIO(drawing.dxf_bytes.decode("utf-8")))
        column = next(item for item in document.modelspace() if item.dxf.layer == "A-COLS")
        column.translate(delta, 0, 0)
        result = verify_architecture_dxf(contract, serialize(document), contract_hash)
        measurement = next(
            item for item in result.measurements if item.dimension_id == "dim-column-x"
        )
        boundary_results.append(measurement.passed)
    assert boundary_results == [True, False]


def test_cp_sat_auto_repair_and_api_false_switch() -> None:
    data = payload()
    data["columns"][0]["center"] = [6200, 4200]
    data["free_parameters"] = [
        {
            "id": "free-column-x",
            "path": "columns.column-center.center.0",
            "minimum": 0,
            "maximum": 12000,
            "step": 100,
            "unit": "mm",
        }
    ]
    contract = ArchitecturalPlanContract.model_validate(data)
    blocked = run_architecture_design(contract, auto_repair=False)
    assert blocked.status == RunStatus.REPAIRABLE
    repaired = run_architecture_design(contract, auto_repair=True)
    assert repaired.status == RunStatus.PASSED
    assert repaired.summary["repair_iterations"] == 1
    assert repaired.summary["repair_history"][0]["solver"] == "ortools_cp_sat"
    assert any(item.type == "architecture_repair_history" for item in repaired.evidence)

    client = TestClient(app)
    response = client.post(
        "/api/v1/architecture/designs/run?auto_repair=false",
        json=contract.model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "repairable"


def test_auto_repair_is_bounded_to_three_declared_center_changes() -> None:
    data = payload()
    data["constraints"][-2]["entity_ids"] = []
    data["columns"][0]["center"] = [6200, 4200]
    for index, center in enumerate(([5800, 3800], [11800, 7800]), start=2):
        column = dict(data["columns"][0])
        column["id"] = f"column-{index}"
        column["center"] = center
        data["columns"].append(column)
    data["free_parameters"] = [
        {
            "id": f"free-column-{index}",
            "path": f"columns.{column['id']}.center.0",
            "minimum": 0,
            "maximum": 12000,
            "step": 100,
            "unit": "mm",
        }
        for index, column in enumerate(data["columns"], start=1)
    ]
    result = run_architecture_design(ArchitecturalPlanContract.model_validate(data))
    assert result.status == RunStatus.PASSED
    assert result.summary["repair_iterations"] == 3
    assert len(result.summary["repair_history"]) == 3


def test_repair_refuses_undeclared_locked_and_topology_changes() -> None:
    no_free = payload()
    no_free["columns"][0]["center"] = [6200, 4200]
    result = run_architecture_design(ArchitecturalPlanContract.model_validate(no_free))
    assert "DG_ARCH_REPAIR_NO_FREE_PARAMETER" in {item.code for item in result.violations}

    locked = payload()
    locked["columns"][0]["center"] = [6200, 4200]
    locked["dimensions"].append(
        {
            "id": "dim-locked-column-x",
            "path": "columns.column-center.center.0",
            "target": 6200,
            "tolerance_lower": 0,
            "tolerance_upper": 0,
            "locked": True,
        }
    )
    result = run_architecture_design(ArchitecturalPlanContract.model_validate(locked))
    assert "DG_ARCH_REPAIR_LOCKED" in {item.code for item in result.violations}

    exhausted = payload()
    exhausted["columns"][0]["center"] = [6200, 4200]
    exhausted["free_parameters"] = [
        {
            "id": "free-bounded-column-x",
            "path": "columns.column-center.center.0",
            "minimum": 6100,
            "maximum": 6200,
            "step": 100,
            "unit": "mm",
        }
    ]
    result = run_architecture_design(ArchitecturalPlanContract.model_validate(exhausted))
    assert result.status == RunStatus.REPAIR_EXHAUSTED
    assert "DG_ARCH_REPAIR_EXHAUSTED" in {item.code for item in result.violations}
    assert len(result.summary["repair_history"]) <= 3

    topology = run_architecture_design(
        ArchitecturalPlanContract.model_validate(payload("architecture_open_300mm.json"))
    )
    assert topology.summary["repair_history"] == []
    assert "DG_ARCH_EXTERIOR_OPEN" in {item.code for item in topology.violations}


def test_legacy_payload_normalizes_new_explicit_fields() -> None:
    legacy = ArchitecturalPlanContract.model_validate(payload("architecture_studio.json"))
    normalized = normalize_architecture_to_mm(legacy)
    assert all(item.offset is not None for item in normalized.grids if item.axis != "custom")
    assert all(item.locked for item in normalized.walls)
    assert all(item.swing in {"left", "right", "double", "none"} for item in normalized.openings)

from __future__ import annotations

import base64
import io
import json
import zipfile

import ezdxf
import pytest
from jsonschema import validate as validate_json_schema

from datumguard.artifacts import generate_dxf
from datumguard.core import compute_contract_hash, normalize_to_mm
from datumguard.models import ContractStatus, DesignContract, RunStatus
from datumguard.service import draft_contract, run_design, validate_contract, verify_only


def test_public_example_validates_against_generated_schema(sample_contract: DesignContract) -> None:
    validate_json_schema(
        sample_contract.model_dump(mode="json"),
        DesignContract.model_json_schema(),
    )


def test_contract_and_dxf_hashes_are_reproducible(sample_contract: DesignContract) -> None:
    normalized = normalize_to_mm(sample_contract)
    contract_hash = compute_contract_hash(sample_contract)
    assert contract_hash == compute_contract_hash(normalized)
    assert generate_dxf(normalized, contract_hash) == generate_dxf(normalized, contract_hash)


def test_full_run_produces_only_verified_bundle(sample_contract: DesignContract) -> None:
    response = run_design(sample_contract)
    assert response.status == RunStatus.PASSED
    assert response.bundle_base64 is not None
    assert all(measurement.passed for measurement in response.measurements)
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(response.bundle_base64)))
    assert set(archive.namelist()) == {
        "design-contract.json",
        "drawing-do-not-scale.pdf",
        "drawing.dxf",
        "manifest.json",
        "preview.svg",
        "repair-history.json",
        "verification.json",
    }
    manifest = json.loads(archive.read("manifest.json"))
    verification = json.loads(archive.read("verification.json"))
    assert manifest["approval"] == "passed"
    assert manifest["authority"] == "drawing.dxf"
    assert manifest["pdf_notice"] == "DO NOT SCALE"
    assert verification["status"] == "passed"
    assert verification["artifact_hash"] == response.artifact_hash


def test_independent_verifier_detects_serialized_dxf_tampering(
    sample_contract: DesignContract,
) -> None:
    normalized = normalize_to_mm(sample_contract)
    contract_hash = compute_contract_hash(normalized)
    original = generate_dxf(normalized, contract_hash)
    document = ezdxf.read(io.StringIO(original.decode("utf-8")))
    outline = next(
        entity
        for entity in document.modelspace()
        if entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer == "OUTLINE"
    )
    outline.set_points([(0, 0), (121, 0), (121, 80), (0, 80)], format="xy")
    stream = io.StringIO(newline="\n")
    document.write(stream)

    result = verify_only(normalized, stream.getvalue().encode("utf-8"))
    width = next(item for item in result.measurements if item.dimension_id == "dim-width")
    assert result.status == RunStatus.FAILED
    assert width.actual == 121.0
    assert not width.passed
    assert any(item.code == "DG_TOLERANCE_EXCEEDED" for item in result.violations)


def test_locked_conflict_is_infeasible_and_never_exports(sample_contract: DesignContract) -> None:
    data = sample_contract.model_dump(mode="python")
    data["dimensions"][0]["target"] = 130.0
    contract = DesignContract.model_validate(data)
    validation = validate_contract(contract)
    response = run_design(contract)
    assert validation.status == ContractStatus.INFEASIBLE
    assert response.status == RunStatus.FAILED
    assert response.bundle_base64 is None
    assert any(item.code == "DG_CONTRACT_INFEASIBLE" for item in response.violations)


def test_outside_feature_is_blocked(sample_contract: DesignContract) -> None:
    data = sample_contract.model_dump(mode="python")
    data["features"][0]["center"] = [-10.0, 10.0]
    data["dimensions"] = [data["dimensions"][0]]
    data["free_parameters"] = []
    contract = DesignContract.model_validate(data)
    response = run_design(contract)
    assert response.status == RunStatus.FAILED
    assert response.bundle_base64 is None
    assert any(item.code == "DG_FEATURE_OUTSIDE_OUTLINE" for item in response.violations)


def test_bounded_repair_changes_only_declared_free_path(
    sample_contract: DesignContract,
) -> None:
    data = sample_contract.model_dump(mode="python")
    data["dimensions"][1]["target"] = 55.0
    contract = DesignContract.model_validate(data)

    blocked = run_design(contract, auto_repair=False)
    repaired = run_design(contract, auto_repair=True)

    assert blocked.status == RunStatus.REPAIRABLE
    assert blocked.bundle_base64 is None
    assert repaired.status == RunStatus.PASSED
    assert repaired.bundle_base64 is not None
    slot_x = next(item for item in repaired.measurements if item.dimension_id == "dim-slot-x")
    width = next(item for item in repaired.measurements if item.dimension_id == "dim-width")
    assert slot_x.actual == 55.0
    assert width.actual == 120.0
    repair_evidence = next(item for item in repaired.evidence if item.type == "repair_history")
    assert repair_evidence.details["locked_changes"] == 0


def test_locked_alignment_conflict_is_infeasible(sample_contract: DesignContract) -> None:
    data = sample_contract.model_dump(mode="python")
    data["constraints"].append(
        {
            "id": "constraint-alignment",
            "type": "alignment",
            "entity_ids": ["hole-1", "slot-1"],
            "parameters": {"axis": "y", "tolerance": 0.001},
            "required": True,
        }
    )
    data["free_parameters"] = []
    data["dimensions"][1]["locked"] = True
    contract = DesignContract.model_validate(data)
    validation = validate_contract(contract)
    response = run_design(contract)
    assert validation.status == ContractStatus.INFEASIBLE
    assert response.bundle_base64 is None
    assert any(item.code == "DG_ALIGNMENT" for item in response.violations)


def test_pattern_equal_spacing_is_remeasured_from_dxf(sample_contract: DesignContract) -> None:
    data = sample_contract.model_dump(mode="python")
    data["constraints"].append(
        {
            "id": "constraint-pattern-spacing",
            "type": "equal_spacing",
            "entity_ids": ["pattern-1"],
            "parameters": {"axis": "x", "tolerance": 0.001},
            "required": True,
        }
    )
    response = run_design(DesignContract.model_validate(data))
    assert response.status == RunStatus.PASSED
    assert response.bundle_base64 is not None


def test_inch_and_mm_contracts_share_canonical_hash() -> None:
    def make(unit: str, factor: float) -> DesignContract:
        return DesignContract.model_validate(
            {
                "units": unit,
                "outline": {
                    "type": "rectangle",
                    "width": 100 / factor,
                    "height": 60 / factor,
                },
                "features": [
                    {
                        "id": "hole-1",
                        "type": "circular_hole",
                        "center": [20 / factor, 20 / factor],
                        "diameter": 8 / factor,
                    }
                ],
                "dimensions": [
                    {
                        "id": "dim-width",
                        "path": "outline.width",
                        "target": 100 / factor,
                        "tolerance_lower": -0.1 / factor,
                        "tolerance_upper": 0.1 / factor,
                        "locked": True,
                        "source": {"kind": "form", "ref": "width"},
                    }
                ],
                "constraints": [],
                "free_parameters": [],
                "manufacturing_profile": {
                    "process": "custom",
                    "kerf": 0,
                    "tool_diameter": None,
                    "minimum_feature": 1 / factor,
                    "minimum_ligament": 0,
                    "confirmed_by_user": True,
                },
                "metadata": {"project_name": "Unit equivalence"},
            }
        )

    millimetres = make("mm", 1.0)
    inches = make("inch", 25.4)
    assert compute_contract_hash(millimetres) == compute_contract_hash(inches)


@pytest.mark.parametrize("index", range(100))
def test_golden_contract_matrix(sample_contract: DesignContract, index: int) -> None:
    data = sample_contract.model_dump(mode="python")
    width = 120.0 + index * 0.125
    data["outline"]["width"] = width
    data["dimensions"][0]["target"] = width
    contract = DesignContract.model_validate(data)
    response = run_design(contract)
    assert response.status == RunStatus.PASSED
    assert response.bundle_base64 is not None


@pytest.mark.parametrize("index", range(50))
def test_natural_language_numeric_mentions_require_confirmation(
    sample_contract: DesignContract,
    index: int,
) -> None:
    result = draft_contract(sample_contract, f"홀 간격은 대략 {20 + index} mm 정도로 해줘")
    assert result.status == ContractStatus.NEEDS_CONFIRMATION
    guard = next(item for item in result.violations if item.code == "DG_NEEDS_CONFIRMATION")
    assert guard.details["action"].startswith("Confirm values")

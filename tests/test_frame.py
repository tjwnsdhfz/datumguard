from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from datumguard.frame_models import StructuralFrameContract
from datumguard.frame_service import run_frame_design, validate_frame_contract
from datumguard.frame_solver import solve_frame
from datumguard.models import ContractStatus, RunStatus


def fixture_payload(name: str = "frame_pipe_rack.json") -> dict[str, Any]:
    path = Path(__file__).parents[1] / "fixtures" / "examples" / name
    return json.loads(path.read_text(encoding="utf-8"))


def cantilever_contract() -> StructuralFrameContract:
    return StructuralFrameContract.model_validate(
        {
            "design_kind": "structural_frame",
            "nodes": [
                {"id": "fixed", "point": [0, 0]},
                {"id": "tip", "point": [3000, 0]},
            ],
            "members": [
                {
                    "id": "cantilever",
                    "start_node_id": "fixed",
                    "end_node_id": "tip",
                    "area_mm2": 2000,
                    "inertia_mm4": 8000000,
                    "elastic_modulus_mpa": 200000,
                    "section_depth_mm": 200,
                }
            ],
            "loads": [{"id": "tip-load", "node_id": "tip", "fy_n": -1000}],
            "supports": [
                {"id": "fixed-support", "node_id": "fixed", "ux": True, "uy": True, "rz": True}
            ],
            "limits": {"max_displacement_mm": 10, "allowable_stress_mpa": 250},
            "metadata": {"project_name": "Closed-form cantilever"},
        }
    )


def test_pipe_rack_fixture_passes_exact_screening() -> None:
    contract = StructuralFrameContract.model_validate(fixture_payload())
    result = run_frame_design(contract)
    assert result.status == RunStatus.PASSED
    assert result.artifact_hash and result.artifact_hash.startswith("sha256:")
    assert result.summary["analysis_source"] == "exact_numpy_2d_euler_bernoulli"
    assert result.summary["screening_only"] is True
    assert result.summary["safety_certification"] is False
    assert result.summary["max_utilization"] <= 1.0
    assert "NOT A SAFETY CERTIFICATION" in result.preview_svg


def test_failure_fixture_is_failed_and_repair_is_free_only() -> None:
    contract = StructuralFrameContract.model_validate(
        fixture_payload("frame_pipe_rack_failure.json")
    )
    failed = run_frame_design(contract)
    assert failed.status == RunStatus.FAILED
    assert {
        "DG_FRAME_MEMBER_OVERSTRESS",
        "DG_FRAME_DISPLACEMENT_EXCEEDED",
    } & {item.code for item in failed.violations}
    assert failed.repair_proposals

    repaired = run_frame_design(contract, auto_repair=True)
    original = {item.id: item for item in contract.members}
    final = {item["member_id"]: item for item in repaired.summary["final_member_properties"]}
    for member_id, member in original.items():
        if member.locked:
            assert final[member_id]["area_mm2"] == member.area_mm2
            assert final[member_id]["inertia_mm4"] == member.inertia_mm4
    assert all(
        change.path in {item.path for item in contract.free_parameters}
        for proposal in repaired.repair_proposals
        for change in proposal.changes
    )
    assert repaired.summary["repair_iterations"] <= 3


def test_cantilever_matches_closed_form_displacement_rotation_and_equilibrium() -> None:
    contract = cantilever_contract()
    analysis = solve_frame(contract)
    tip = next(item for item in analysis.node_results if item.node_id == "tip")
    member = analysis.member_results[0]
    length = 3000.0
    load = 1000.0
    modulus = 200000.0
    inertia = 8000000.0
    expected_uy = load * length**3 / (3 * modulus * inertia)
    expected_rz = load * length**2 / (2 * modulus * inertia)
    assert abs(tip.uy_mm) == pytest.approx(expected_uy, rel=1e-9)
    assert abs(tip.rz_rad) == pytest.approx(expected_rz, rel=1e-9)
    assert max(abs(member.start_shear_n), abs(member.end_shear_n)) == pytest.approx(load)
    assert max(abs(member.start_moment_nmm), abs(member.end_moment_nmm)) == pytest.approx(
        load * length
    )
    assert analysis.equilibrium_residual_n <= 1e-8


def test_singular_unknown_zero_length_and_disconnected_fail_closed() -> None:
    singular = cantilever_contract().model_copy(update={"supports": []})
    validation = validate_frame_contract(singular)
    assert validation.status == ContractStatus.INFEASIBLE
    assert "DG_FRAME_SINGULAR" in {item.code for item in validation.violations}

    unknown_data = cantilever_contract().model_dump(mode="python")
    unknown_data["loads"][0]["node_id"] = "missing"
    unknown = validate_frame_contract(StructuralFrameContract.model_validate(unknown_data))
    assert "DG_FRAME_UNKNOWN_NODE" in {item.code for item in unknown.violations}

    zero_data = cantilever_contract().model_dump(mode="python")
    zero_data["nodes"][1]["point"] = [0, 0]
    zero = validate_frame_contract(StructuralFrameContract.model_validate(zero_data))
    assert "DG_FRAME_ZERO_LENGTH" in {item.code for item in zero.violations}

    disconnected_data = cantilever_contract().model_dump(mode="python")
    disconnected_data["nodes"].append({"id": "orphan", "point": [5000, 5000]})
    disconnected = validate_frame_contract(
        StructuralFrameContract.model_validate(disconnected_data)
    )
    assert "DG_FRAME_DISCONNECTED" in {item.code for item in disconnected.violations}


def test_contract_and_analysis_hashes_are_deterministic() -> None:
    first = StructuralFrameContract.model_validate(fixture_payload())
    reordered_data = fixture_payload()
    for key in ("nodes", "members", "loads", "supports"):
        reordered_data[key] = list(reversed(reordered_data[key]))
    reordered = StructuralFrameContract.model_validate(reordered_data)
    first_result = run_frame_design(first)
    second_result = run_frame_design(reordered)
    assert first_result.contract_hash == second_result.contract_hash
    assert first_result.artifact_hash == second_result.artifact_hash


def test_exact_tolerance_boundary_passes() -> None:
    initial = cantilever_contract()
    analysis = solve_frame(initial)
    max_stress = max(item.max_combined_stress_mpa for item in analysis.member_results)
    data = initial.model_dump(mode="python")
    data["limits"] = {
        "max_displacement_mm": analysis.max_displacement_mm,
        "allowable_stress_mpa": max_stress,
    }
    boundary = run_frame_design(StructuralFrameContract.model_validate(data))
    assert boundary.status == RunStatus.PASSED
    assert all(item.passed for item in boundary.measurements)


def test_locked_member_cannot_be_declared_free() -> None:
    data = cantilever_contract().model_dump(mode="python")
    data["free_parameters"] = [
        {
            "id": "illegal",
            "path": "members.cantilever.inertia_mm4",
            "minimum": 1000000,
            "maximum": 10000000,
            "step": 1000000,
            "unit": "mm4",
        }
    ]
    validation = validate_frame_contract(StructuralFrameContract.model_validate(data))
    assert validation.status == ContractStatus.INFEASIBLE
    assert "DG_FRAME_LOCKED_REPAIR_PATH" in {item.code for item in validation.violations}


def test_frame_contract_rejects_non_finite_coordinates() -> None:
    data = cantilever_contract().model_dump(mode="python")
    data["nodes"][1]["point"] = [math.inf, 0]
    with pytest.raises(ValueError):
        StructuralFrameContract.model_validate(data)


def test_frame_contract_caps_dense_solver_input_size() -> None:
    data = cantilever_contract().model_dump(mode="python")
    data["nodes"] = [
        {"id": f"node-{index}", "point": [index * 1000.0, 0.0]} for index in range(121)
    ]
    data["members"][0]["start_node_id"] = "node-0"
    data["members"][0]["end_node_id"] = "node-1"
    data["loads"][0]["node_id"] = "node-1"
    data["supports"][0]["node_id"] = "node-0"
    with pytest.raises(ValueError):
        StructuralFrameContract.model_validate(data)

from __future__ import annotations

import base64
import json
from pathlib import Path

from datumguard.mcp_server import (
    design_contract_draft,
    design_contract_validate,
    drawing_compare,
    drawing_generate,
    drawing_verify,
    export_bundle,
    mcp,
    repair_apply,
    repair_propose,
    rhino_preview,
)


def architecture_fixture() -> dict[str, object]:
    path = Path(__file__).parents[1] / "fixtures" / "examples" / "architecture_studio.json"
    return json.loads(path.read_text(encoding="utf-8"))


def piping_fixture() -> dict[str, object]:
    path = Path(__file__).parents[1] / "fixtures" / "examples" / "piping_utility.json"
    return json.loads(path.read_text(encoding="utf-8"))


def plate_fixture() -> dict[str, object]:
    path = Path(__file__).parents[1] / "fixtures" / "examples" / "design_contract.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_mcp_exposes_exact_public_tool_set() -> None:
    assert set(mcp._tool_manager._tools) == {
        "design_contract_draft",
        "design_contract_validate",
        "drawing_generate",
        "drawing_verify",
        "repair_propose",
        "repair_apply",
        "drawing_compare",
        "export_bundle",
        "rhino_preview",
        "artifact_audit",
        "artifact_compare",
        "solid_generate_verify",
        "frame_analyze",
        "frame_repair_propose",
        "frame_rhino_adapt",
        "frame_rhino_roundtrip",
        "frame_dxf_generate_verify",
        "frame_surrogate_predict",
        "frame_opensees_parity_evidence",
    }


def test_mcp_dispatches_architecture_contract_through_independent_dxf() -> None:
    contract = architecture_fixture()
    drafted = design_contract_draft(contract, "수치는 contract 그대로 사용")
    assert drafted["status"] == "ready"
    assert drafted["normalized_contract"]["design_kind"] == "architectural_plan"

    validation = design_contract_validate(contract)
    assert validation["status"] == "ready"

    generation = drawing_generate(contract)
    assert generation["status"] == "generated_unverified"
    verification = drawing_verify(contract, generation["dxf_base64"])
    assert verification["status"] == "passed"
    assert verification["artifact_hash"] == generation["artifact_hash"]


def test_mcp_architecture_compare_repair_policy_and_export(tmp_path: Path) -> None:
    contract = architecture_fixture()
    candidate = json.loads(json.dumps(contract))
    candidate["metadata"]["revision"] = "B"
    comparison = drawing_compare(contract, candidate)
    assert comparison["comparison"]["design_kind"] == "architectural_plan"
    assert comparison["contract_hash"].startswith("sha256:")

    repair_contract = json.loads(json.dumps(contract))
    repair_contract["columns"][0]["center"] = [6200, 4200]
    repair_contract["dimensions"] = [
        item
        for item in repair_contract["dimensions"]
        if item["path"] != "columns.column-a.center.0"
    ]
    repair_contract["free_parameters"] = [
        {
            "id": "free-column-x",
            "path": "columns.column-a.center.0",
            "minimum": 0,
            "maximum": 12000,
            "step": 100,
            "unit": "mm",
        }
    ]
    repair = repair_propose(repair_contract, [])
    assert repair["status"] == "proposed"
    assert repair["proposal"]["changes"][0]["path"] == "columns.column-a.center.0"

    applied = repair_apply(repair_contract, repair["proposal"])
    assert applied["status"] == "ready"
    assert applied["contract"]["columns"][0]["center"][0] == 8000

    exported = export_bundle(contract, str(tmp_path))
    assert exported["status"] == "passed"
    assert exported["bundle_base64"] is None
    bundle_path = Path(exported["bundle_path"])
    assert bundle_path.is_file()
    assert base64.b64decode(drawing_generate(contract)["dxf_base64"])

    rhino = rhino_preview(
        exported["contract_hash"],
        exported["artifact_hash"],
        contract,
    )
    assert rhino["error"]["code"] == "DG_CROSS_KERNEL_MISMATCH"
    assert rhino["evidence"][0]["details"]["design_kind"] == "architectural_plan"
    assert rhino["evidence"][0]["details"]["official_verifier_affected"] is False


def test_mcp_contract_without_design_kind_remains_plate() -> None:
    contract = plate_fixture()
    assert "design_kind" not in contract
    drafted = design_contract_draft(contract)
    assert drafted["status"] == "ready"
    assert "design_kind" not in drafted["normalized_contract"]
    validation = design_contract_validate(contract)
    assert validation["status"] == "ready"
    generation = drawing_generate(contract)
    assert generation["status"] == "generated_unverified"


def test_mcp_dispatches_piping_contract_through_independent_dxf() -> None:
    contract = piping_fixture()
    validation = design_contract_validate(contract)
    assert validation["status"] == "ready"

    generation = drawing_generate(contract)
    assert generation["status"] == "generated_unverified"
    verification = drawing_verify(contract, generation["dxf_base64"])
    assert verification["status"] == "passed"
    assert verification["artifact_hash"] == generation["artifact_hash"]
    assert verification["summary"]["summary_source"] == ("independent_serialized_dxf_remeasurement")


def test_mcp_piping_compare_repair_policy_and_export(tmp_path: Path) -> None:
    contract = piping_fixture()
    candidate = json.loads(json.dumps(contract))
    candidate["metadata"]["revision"] = "B"
    comparison = drawing_compare(contract, candidate)
    assert comparison["comparison"]["design_kind"] == "piping_plan"

    repair = repair_propose(contract, [])
    assert repair["status"] == "not_repairable"
    assert repair["violations"][0]["code"] == "DG_PIPE_REPAIR_NOT_SUPPORTED"

    exported = export_bundle(contract, str(tmp_path))
    assert exported["status"] == "passed"
    assert exported["bundle_base64"] is None
    assert Path(exported["bundle_path"]).is_file()

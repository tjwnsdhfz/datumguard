from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from datumguard.frame_rhino_adapter import RhinoFrameExchange
from datumguard.mcp_server import (
    design_contract_validate,
    frame_analyze,
    frame_dxf_generate_verify,
    frame_opensees_parity_evidence,
    frame_repair_propose,
    frame_rhino_adapt,
    frame_rhino_roundtrip,
    frame_surrogate_predict,
    mcp,
)


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


def test_mcp_lists_frameguard_tools() -> None:
    assert {
        "frame_analyze",
        "frame_repair_propose",
        "frame_rhino_adapt",
        "frame_rhino_roundtrip",
        "frame_dxf_generate_verify",
        "frame_surrogate_predict",
        "frame_opensees_parity_evidence",
    } <= set(mcp._tool_manager._tools)


def test_mcp_generic_validation_dispatches_structural_frame() -> None:
    result = design_contract_validate(_fixture("frame_pipe_rack.json"))

    _assert_common_envelope(result)
    assert result["status"] == "ready"
    assert result["normalized_contract"]["design_kind"] == "structural_frame"


def test_mcp_frame_analyze_returns_pass_and_failure_evidence() -> None:
    passed = frame_analyze(_fixture("frame_pipe_rack.json"))
    failed = frame_analyze(_fixture("frame_pipe_rack_failure.json"))

    _assert_common_envelope(passed)
    _assert_common_envelope(failed)
    assert passed["status"] == "passed"
    assert passed["artifact_hash"].startswith("sha256:")
    assert passed["summary"]
    assert passed["preview_svg"].lstrip().startswith("<svg")
    assert failed["status"] != "passed"
    assert failed["violations"]


def test_mcp_rejects_nonfinite_frame_scalars_before_solver_dispatch() -> None:
    contract = _fixture("frame_pipe_rack.json")
    contract["limits"]["max_displacement_mm"] = float("nan")

    with pytest.raises(ValidationError):
        frame_analyze(contract)

    exchange = _fixture("frame_rhino_exchange.json")
    exchange["limits"]["max_displacement"] = float("inf")
    adapted = frame_rhino_adapt(exchange)
    assert adapted["status"] == "infeasible"
    assert adapted["structural_contract"] is None
    assert adapted["violations"][0]["code"] == "DG_FRAME_RHINO_SCHEMA_INVALID"


def test_mcp_frame_repair_recomputes_analysis_and_returns_structured_proposal() -> None:
    result = frame_repair_propose(_fixture("frame_pipe_rack_failure.json"))

    _assert_common_envelope(result)
    assert "proposal" in result
    if result["proposal"] is not None:
        assert result["proposal"]["contract_hash"] == result["contract_hash"]
        assert result["proposal"]["status"] in {"proposed", "not_repairable", "exhausted"}
        assert result["evidence"][0]["details"]["proposal_applied"] is False
    else:
        assert result["status"] == "infeasible"
        assert result["error"]["code"].startswith("DG_FRAME_")


def test_mcp_frame_rhino_dxf_and_research_tools_are_fail_closed() -> None:
    exchange = _fixture("frame_rhino_exchange.json")
    adapted = frame_rhino_adapt(exchange)
    assert adapted["status"] == "ready"
    assert adapted["structural_contract"]["units"] == "mm"

    roundtrip = frame_rhino_roundtrip(RhinoFrameExchange.model_validate(exchange)).model_dump(
        mode="json"
    )
    assert roundtrip["status"] == "passed"
    assert roundtrip["bundle_base64"]
    assert roundtrip["manifest"]["exchange_hash"] == roundtrip["exchange_hash"]
    assert roundtrip["summary"]["safety_certification"] is False

    cad = frame_dxf_generate_verify(_fixture("frame_pipe_rack.json"))
    assert cad["status"] == "passed"
    assert cad["verification"]["status"] == "passed"
    assert cad["summary"]["safety_certification"] is False

    blocked_cad = frame_dxf_generate_verify(_fixture("frame_pipe_rack_failure.json"))
    assert blocked_cad["status"] != "passed"
    assert blocked_cad["dxf_base64"] is None
    assert blocked_cad["summary"]["download_eligible"] is False

    surrogate = frame_surrogate_predict(_fixture("frame_pipe_rack.json"))
    assert surrogate["status"] in {"PREDICTED", "REVIEW_REQUIRED"}
    assert surrogate["authoritative"] is False
    assert surrogate["exact_solver_required"] is True

    parity = frame_opensees_parity_evidence()
    assert parity["report_kind"] == "frame_opensees_parity_v1"
    assert parity["status"] == "PASSED"

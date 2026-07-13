from __future__ import annotations

import base64
import json
from pathlib import Path

from datumguard.frame_cad_service import run_frame_cad_assurance
from datumguard.frame_models import StructuralFrameContract
from datumguard.models import RunStatus

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "examples"


def _contract(name: str) -> StructuralFrameContract:
    return StructuralFrameContract.model_validate_json(
        (FIXTURES / name).read_text(encoding="utf-8")
    )


def test_frame_cad_assurance_requires_exact_and_dxf_pass() -> None:
    response = run_frame_cad_assurance(_contract("frame_pipe_rack.json"))

    assert response.status is RunStatus.PASSED
    assert response.dxf_base64 is not None
    assert base64.b64decode(response.dxf_base64).startswith(b"  0\nSECTION")
    assert response.verification is not None
    assert response.verification.status is RunStatus.PASSED
    assert response.summary["dxf_reopened"] is True
    assert response.summary["download_eligible"] is True
    assert response.summary["safety_certification"] is False
    assert any(item.type == "frame_cad_assurance_gate" for item in response.evidence)


def test_frame_cad_assurance_blocks_download_when_exact_screening_fails() -> None:
    response = run_frame_cad_assurance(_contract("frame_pipe_rack_failure.json"))

    assert response.status is RunStatus.FAILED
    assert response.dxf_base64 is None
    assert response.verification is not None
    assert response.verification.status is RunStatus.PASSED
    assert response.summary["exact_solver_passed"] is False
    assert response.summary["download_eligible"] is False
    assert response.summary["construction_approval"] is False


def test_frame_cad_assurance_fails_before_writing_invalid_contract() -> None:
    payload = json.loads((FIXTURES / "frame_pipe_rack.json").read_text(encoding="utf-8"))
    payload["members"][0]["end_node_id"] = "UNKNOWN"
    response = run_frame_cad_assurance(StructuralFrameContract.model_validate(payload))

    assert response.status is RunStatus.FAILED
    assert response.dxf_base64 is None
    assert response.summary["dxf_written"] is False
    assert response.error is not None
    assert response.error.code == "DG_FRAME_CAD_CONTRACT_NOT_READY"

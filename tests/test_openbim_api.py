from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from datumguard import api as api_module
from datumguard import openbim_service
from datumguard.api import app
from datumguard.ifc_evidence import sha256_bytes
from datumguard.openbim_models import OpenBimEvidenceReport, OpenBimReportArtifact
from datumguard.openbim_service import OpenBimServiceFailure, resolve_openbim_profile
from datumguard.operations import reset_operational_state_for_tests

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_operations() -> None:
    reset_operational_state_for_tests()


def _files(ids: bytes = b"<ids/>") -> dict[str, tuple[str, bytes, str]]:
    return {
        "baseline": ("baseline.ifc", b"baseline", "application/x-step"),
        "candidate": ("candidate.ifc", b"candidate", "application/x-step"),
        "requirements": ("requirements.ids", ids, "application/xml"),
    }


def _mock_report() -> OpenBimEvidenceReport:
    content = b"{}"
    return OpenBimEvidenceReport(
        status="passed",
        profile_id="virtual-fab-v1",
        baseline_hash="sha256:" + ("1" * 64),
        candidate_hash="sha256:" + ("2" * 64),
        ids_hash="sha256:" + ("3" * 64),
        profile_hash="sha256:" + ("4" * 64),
        rule_results=[],
        issues=[],
        reports=[
            OpenBimReportArtifact(
                kind="evidence_json",
                filename="openbim-evidence.json",
                media_type="application/json",
                artifact_hash=sha256_bytes(content),
                byte_size=len(content),
                content_base64=base64.b64encode(content).decode("ascii"),
            )
        ],
    )


def test_openbim_endpoint_returns_deterministic_download_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATUMGUARD_ENABLE_BCF", "true")
    reset_operational_state_for_tests()
    monkeypatch.setattr(api_module, "run_openbim_evidence", lambda **_kwargs: _mock_report())

    response = client.post(
        "/api/v1/openbim/evidence/run",
        files=_files(),
        data={"profile_id": "virtual-fab-v1", "include_html": "true", "include_bcf": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["research_validation_only"] is True
    assert payload["approval_eligible"] is False
    assert payload["reports"][0] == {
        "kind": "evidence_json",
        "filename": "openbim-evidence.json",
        "media_type": "application/json",
        "artifact_hash": sha256_bytes(b"{}"),
        "byte_size": 2,
        "content_base64": "e30=",
    }


def test_openbim_bcf_export_is_server_gated_before_worker_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_worker(**_kwargs: object) -> OpenBimEvidenceReport:
        raise AssertionError("worker must not run when BCF packaging is disabled")

    monkeypatch.setattr(api_module, "run_openbim_evidence", forbidden_worker)
    response = client.post(
        "/api/v1/openbim/evidence/run",
        files=_files(),
        data={"profile_id": "virtual-fab-v1", "include_bcf": "true"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DG_CAPABILITY_DISABLED"
    assert response.json()["error"]["details"]["capability"] == "openbim_bcf"


@pytest.mark.parametrize(
    "profile_id", ["../../virtual-fab-v1", "C:/private/profile.json", "unknown"]
)
def test_profile_id_is_a_strict_allowlist(profile_id: str) -> None:
    with pytest.raises(OpenBimServiceFailure) as captured:
        resolve_openbim_profile(profile_id)

    assert captured.value.code == "DG_OPENBIM_PROFILE_INVALID"
    assert "private" not in str(captured.value.details)


@pytest.mark.parametrize("profile_id", ["../profile.json", "not-registered"])
def test_openbim_api_rejects_unregistered_profile_without_worker_execution(
    monkeypatch: pytest.MonkeyPatch,
    profile_id: str,
) -> None:
    def forbidden_worker(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("worker must not run for an invalid profile id")

    monkeypatch.setattr(openbim_service, "run_openbim_worker", forbidden_worker)
    response = client.post(
        "/api/v1/openbim/evidence/run",
        files=_files(),
        data={"profile_id": profile_id},
        headers={"X-Request-ID": "request-openbim-0001"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DG_OPENBIM_PROFILE_INVALID"
    assert response.json()["error"]["correlation_id"] == "request-openbim-0001"
    assert response.headers["X-Request-ID"] == "request-openbim-0001"
    assert profile_id not in response.text


@pytest.mark.parametrize(
    ("field", "filename"),
    [("requirements", "requirements.xml"), ("candidate", "candidate.step")],
)
def test_openbim_api_rejects_wrong_file_extensions(field: str, filename: str) -> None:
    files = _files()
    original = files[field]
    files[field] = (filename, original[1], original[2])

    response = client.post(
        "/api/v1/openbim/evidence/run",
        files=files,
        data={"profile_id": "virtual-fab-v1"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DG_OPENBIM_INPUT_INVALID"
    assert filename not in response.text


def test_openbim_ids_part_limit_returns_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_module, "MAX_IDS_BYTES", 8)
    response = client.post(
        "/api/v1/openbim/evidence/run",
        files=_files(ids=b"123456789"),
        data={"profile_id": "virtual-fab-v1"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "DG_OPENBIM_TOO_LARGE"
    assert "requirements.ids" not in response.text


def test_openbim_ifc_part_limit_returns_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_module, "MAX_IFC_BYTES", 8)
    files = _files()
    files["candidate"] = ("candidate.ifc", b"123456789", "application/x-step")

    response = client.post(
        "/api/v1/openbim/evidence/run",
        files=files,
        data={"profile_id": "virtual-fab-v1"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "DG_OPENBIM_TOO_LARGE"


def test_openbim_aggregate_limit_returns_413_without_large_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_module, "MAX_IFC_BYTES", 16)
    monkeypatch.setattr(api_module, "MAX_IDS_BYTES", 8)
    monkeypatch.setattr(api_module, "MAX_OPENBIM_TOTAL_BYTES", 12)
    files = {
        "baseline": ("baseline.ifc", b"12345", "application/x-step"),
        "candidate": ("candidate.ifc", b"12345", "application/x-step"),
        "requirements": ("requirements.ids", b"123", "application/xml"),
    }

    response = client.post(
        "/api/v1/openbim/evidence/run",
        files=files,
        data={"profile_id": "virtual-fab-v1"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "DG_OPENBIM_TOO_LARGE"
    assert response.json()["error"]["details"]["max_total_bytes"] == 12

from __future__ import annotations

import base64
import copy
import io
import json
import math
import zipfile
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import read
from fastapi.testclient import TestClient

from datumguard.api import app
from datumguard.core import compute_artifact_hash
from datumguard.frame_artifacts import FrameRoundTripArtifactError, build_frame_roundtrip_bundle
from datumguard.frame_cad_service import run_frame_cad_assurance
from datumguard.frame_dxf import (
    FRAME_XDATA_APP_ID,
    generate_frame_dxf,
    verify_frame_dxf,
)
from datumguard.frame_models import StructuralFrameContract
from datumguard.frame_provenance import provenance_index
from datumguard.frame_rhino_adapter import RhinoFrameExchange, adapt_rhino_frame_exchange
from datumguard.frame_roundtrip_service import run_frame_rhino_roundtrip
from datumguard.frame_service import validate_frame_contract
from datumguard.models import ContractStatus, RunStatus

FIXTURE = Path("fixtures/examples/frame_rhino_exchange.json")
client = TestClient(app)


@pytest.fixture
def exchange_payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _xdata(entity: Any) -> dict[str, str]:
    return {
        str(tag.value).split("=", 1)[0]: str(tag.value).split("=", 1)[1]
        for tag in entity.get_xdata(FRAME_XDATA_APP_ID)
        if tag.code == 1000 and "=" in str(tag.value)
    }


def _serialize(document: Any) -> bytes:
    stream = io.StringIO(newline="\n")
    document.write(stream, fmt="asc")
    return stream.getvalue().encode("utf-8")


@pytest.mark.parametrize("unit", ["mm", "cm", "m", "in", "ft"])
def test_source_ids_survive_every_supported_unit_normalization(
    exchange_payload: dict[str, Any], unit: str
) -> None:
    exchange_payload["document"]["units"] = unit

    result = adapt_rhino_frame_exchange(exchange_payload, provenance_bound=True)

    assert result.status is ContractStatus.READY
    assert result.structural_contract is not None
    provenance = result.structural_contract.provenance
    assert provenance is not None
    assert provenance.complete is True
    assert provenance.exchange_hash == result.exchange_hash
    assert provenance.source_document_id == exchange_payload["document"]["document_id"]
    assert provenance_index(result.structural_contract)[("member", "beam-top")] == (
        "22222222-2222-2222-2222-222222222222"
    )


def test_v03_contract_without_provenance_keeps_its_canonical_hash() -> None:
    payload = json.loads(Path("fixtures/examples/frame_pipe_rack.json").read_text())
    contract = StructuralFrameContract.model_validate(payload)

    validation = validate_frame_contract(contract)

    assert validation.contract_hash == (
        "sha256:092d551d83834cf0516867e1a62bbb453609ad29aca94c46fd3c19fdb175ce3e"
    )


def test_roundtrip_passes_with_rotated_xy_datum_and_preserves_provenance(
    exchange_payload: dict[str, Any],
) -> None:
    angle = math.radians(30.0)
    exchange_payload["document"]["datum"].update(
        {
            "x_axis": [math.cos(angle), math.sin(angle), 0.0],
            "y_axis": [-math.sin(angle), math.cos(angle), 0.0],
            "z_axis": [0.0, 0.0, 1.0],
        }
    )

    result = run_frame_rhino_roundtrip(exchange_payload)

    assert result.status is RunStatus.PASSED
    assert result.summary["provenance_verified"] is True
    assert result.normalized_contract is not None
    assert result.normalized_contract.provenance is not None
    assert result.normalized_contract.provenance.exchange_hash == result.exchange_hash
    assert result.analysis is not None
    assert result.analysis.contract_hash == result.contract_hash
    assert result.verification is not None
    assert result.verification.contract_hash == result.contract_hash
    assert result.verification.summary["contract_record_verified"] is True
    assert result.bundle_base64 is not None


def test_roundtrip_hashes_dxf_and_bundle_are_deterministic_across_input_order(
    exchange_payload: dict[str, Any],
) -> None:
    first = run_frame_rhino_roundtrip(exchange_payload)
    reordered = copy.deepcopy(exchange_payload)
    reordered["members"].reverse()
    reordered["supports"].reverse()
    second = run_frame_rhino_roundtrip(reordered)
    model_input = run_frame_rhino_roundtrip(RhinoFrameExchange.model_validate(exchange_payload))

    assert first.status is RunStatus.PASSED
    assert second.status is RunStatus.PASSED
    assert first.exchange_hash == second.exchange_hash
    assert first.contract_hash == second.contract_hash
    assert first.artifact_hash == second.artifact_hash
    assert first.manifest_hash == second.manifest_hash
    assert first.bundle_hash == second.bundle_hash
    assert first.bundle_base64 == second.bundle_base64
    assert first.exchange_hash == model_input.exchange_hash
    assert first.contract_hash == model_input.contract_hash
    assert first.bundle_hash == model_input.bundle_hash


def test_source_identity_is_bound_into_exchange_contract_and_artifact_hashes(
    exchange_payload: dict[str, Any],
) -> None:
    first = run_frame_rhino_roundtrip(exchange_payload)
    changed_source = copy.deepcopy(exchange_payload)
    changed_source["members"][0]["source_object_id"] = "77777777-7777-7777-7777-777777777777"
    second = run_frame_rhino_roundtrip(changed_source)

    assert first.status is RunStatus.PASSED
    assert second.status is RunStatus.PASSED
    assert first.exchange_hash != second.exchange_hash
    assert first.contract_hash != second.contract_hash
    assert first.artifact_hash != second.artifact_hash
    assert first.bundle_hash != second.bundle_hash


def test_bundle_manifest_binds_every_file_and_source_object(
    exchange_payload: dict[str, Any],
) -> None:
    result = run_frame_rhino_roundtrip(exchange_payload)
    assert result.status is RunStatus.PASSED
    assert result.bundle_base64 is not None
    assert result.manifest is not None
    archive_bytes = base64.b64decode(result.bundle_base64, validate=True)
    assert compute_artifact_hash(archive_bytes) == result.bundle_hash

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest == result.manifest.model_dump(mode="json")
        assert manifest["exchange_hash"] == result.exchange_hash
        assert manifest["contract_hash"] == result.contract_hash
        assert manifest["artifact_hash"] == result.artifact_hash
        assert manifest["screening_only"] is True
        assert manifest["safety_certification"] is False
        assert manifest["screening_gate_status"] == "passed"
        assert manifest["artifact_role"] == "geometry_evidence"
        assert "approval" not in manifest
        assert "authority" not in manifest
        assert manifest["provenance"]["complete"] is True
        assert len(manifest["provenance"]["objects"]) == 6
        for record in manifest["files"]:
            content = archive.read(record["name"])
            assert len(content) == record["size_bytes"]
            assert compute_artifact_hash(content) == record["sha256"]
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
        assert all(item.create_system == 3 for item in archive.infolist())
        assert all(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist())
        assert all((item.external_attr >> 16) == 0o100644 for item in archive.infolist())


def test_bundle_rechecks_analysis_verification_and_source_mapping_identity(
    exchange_payload: dict[str, Any],
) -> None:
    adapter = adapt_rhino_frame_exchange(exchange_payload, provenance_bound=True)
    assert adapter.normalized_exchange is not None
    assert adapter.structural_contract is not None
    assert adapter.contract_hash is not None
    contract = adapter.structural_contract
    cad = run_frame_cad_assurance(contract)
    assert cad.analysis is not None
    assert cad.verification is not None
    assert cad.dxf_base64 is not None
    dxf_bytes = base64.b64decode(cad.dxf_base64, validate=True)

    bad_analysis = cad.analysis.model_copy(update={"contract_hash": "sha256:" + "0" * 64})
    with pytest.raises(FrameRoundTripArtifactError, match="analysis contract hash mismatch"):
        build_frame_roundtrip_bundle(
            exchange=adapter.normalized_exchange,
            exchange_hash=adapter.exchange_hash,
            contract=contract,
            contract_hash=adapter.contract_hash,
            dxf_bytes=dxf_bytes,
            verification=cad.verification,
            analysis=bad_analysis,
        )

    bad_verification = cad.verification.model_copy(
        update={
            "summary": {
                **cad.verification.summary,
                "contract_record_verified": False,
            }
        }
    )
    with pytest.raises(FrameRoundTripArtifactError, match="contract semantics"):
        build_frame_roundtrip_bundle(
            exchange=adapter.normalized_exchange,
            exchange_hash=adapter.exchange_hash,
            contract=contract,
            contract_hash=adapter.contract_hash,
            dxf_bytes=dxf_bytes,
            verification=bad_verification,
            analysis=cad.analysis,
        )


def test_dxf_xdata_source_mapping_is_reopened_and_tampering_fails_closed(
    exchange_payload: dict[str, Any],
) -> None:
    adapted = adapt_rhino_frame_exchange(exchange_payload, provenance_bound=True)
    assert adapted.structural_contract is not None
    contract = adapted.structural_contract
    document = read(io.StringIO(generate_frame_dxf(contract).decode("utf-8")))
    member = next(
        entity for entity in document.modelspace() if _xdata(entity).get("entity_id") == "beam-top"
    )
    metadata = _xdata(member)
    assert metadata["source_object_id"] == "22222222-2222-2222-2222-222222222222"
    assert metadata["source_exchange_hash"] == adapted.exchange_hash

    tags = member.get_xdata(FRAME_XDATA_APP_ID)
    member.set_xdata(
        FRAME_XDATA_APP_ID,
        [
            (tag.code, "source_object_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
            if tag.code == 1000 and str(tag.value).startswith("source_object_id=")
            else (tag.code, tag.value)
            for tag in tags
        ],
    )
    verification = verify_frame_dxf(contract, _serialize(document))

    assert verification.status is RunStatus.FAILED
    assert verification.summary["provenance_verified"] is False
    assert "DG_FRAME_DXF_PROVENANCE_MISMATCH" in {item.code for item in verification.violations}


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda payload: payload.__setitem__("supports", []), "DG_FRAME_RHINO_SUPPORT_REQUIRED"),
        (lambda payload: payload.__setitem__("loads", []), "DG_FRAME_RHINO_LOAD_REQUIRED"),
        (
            lambda payload: payload["supports"][0].pop("rz"),
            "DG_FRAME_RHINO_SUPPORT_INVALID",
        ),
        (
            lambda payload: payload["loads"][0].update(
                {"fx_n": 0.0, "fy_n": 0.0, "mz_n_document_unit": 0.0}
            ),
            "DG_FRAME_RHINO_LOAD_INVALID",
        ),
        (
            lambda payload: payload["members"][0].pop("source_object_id"),
            "DG_FRAME_RHINO_PROVENANCE_REQUIRED",
        ),
    ],
)
def test_roundtrip_requires_explicit_support_load_and_source_data(
    exchange_payload: dict[str, Any], mutation: Any, expected_code: str
) -> None:
    mutation(exchange_payload)

    result = run_frame_rhino_roundtrip(exchange_payload)

    assert result.status is RunStatus.FAILED
    assert result.bundle_base64 is None
    assert expected_code in {item.code for item in result.violations}
    assert result.summary["bundle_created"] is False


def test_roundtrip_rejects_nonfinite_and_out_of_plane_payloads(
    exchange_payload: dict[str, Any],
) -> None:
    nonfinite = copy.deepcopy(exchange_payload)
    nonfinite["loads"][0]["fy_n"] = float("nan")
    nonfinite_result = run_frame_rhino_roundtrip(nonfinite)
    assert nonfinite_result.status is ContractStatus.INFEASIBLE
    assert nonfinite_result.bundle_base64 is None
    assert {item.code for item in nonfinite_result.violations} == {"DG_FRAME_RHINO_SCHEMA_INVALID"}

    out_of_plane = copy.deepcopy(exchange_payload)
    out_of_plane["members"][0]["end"][2] = 0.01
    out_of_plane_result = run_frame_rhino_roundtrip(out_of_plane)
    assert out_of_plane_result.status is ContractStatus.INFEASIBLE
    assert out_of_plane_result.bundle_base64 is None
    assert {item.code for item in out_of_plane_result.violations} == {"DG_FRAME_RHINO_OUT_OF_PLANE"}


def test_roundtrip_api_happy_path_and_fail_closed_paths(
    exchange_payload: dict[str, Any],
) -> None:
    passed = client.post("/api/v1/frame/rhino/roundtrip", json=exchange_payload)
    assert passed.status_code == 200
    payload = passed.json()
    assert payload["status"] == "passed"
    assert payload["bundle_base64"]
    assert payload["manifest"]["exchange_hash"] == payload["exchange_hash"]
    assert payload["normalized_contract"]["provenance"]["complete"] is True

    missing_source = copy.deepcopy(exchange_payload)
    missing_source["members"][0].pop("source_object_id")
    blocked = client.post("/api/v1/frame/rhino/roundtrip", json=missing_source)
    assert blocked.status_code == 200
    blocked_payload = blocked.json()
    assert blocked_payload["status"] == "failed_verification"
    assert blocked_payload["bundle_base64"] is None
    assert "DG_FRAME_RHINO_PROVENANCE_REQUIRED" in {
        item["code"] for item in blocked_payload["violations"]
    }

    nonfinite = copy.deepcopy(exchange_payload)
    nonfinite["sections"][0]["inertia"] = float("inf")
    invalid = client.post(
        "/api/v1/frame/rhino/roundtrip",
        content=json.dumps(nonfinite, allow_nan=True),
        headers={"content-type": "application/json"},
    )
    assert invalid.status_code == 422


def test_openapi_exposes_one_step_roundtrip_without_changing_existing_routes() -> None:
    openapi = client.get("/api/v1/openapi.json").json()
    paths = openapi["paths"]
    assert "/api/v1/frame/rhino/roundtrip" in paths
    assert "/api/v1/frame/rhino/adapt" in paths
    assert "/api/v1/frame/cad/run" in paths
    response_schema = paths["/api/v1/frame/rhino/roundtrip"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/FrameRhinoRoundTripResponse")
    response_component = openapi["components"]["schemas"]["FrameRhinoRoundTripResponse"]
    verification_refs = response_component["properties"]["verification"]["anyOf"]
    assert any(
        item.get("$ref", "").endswith("/FrameDxfVerificationResult")
        for item in verification_refs
    )

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path

import ezdxf
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from datumguard import mcp_server
from datumguard.api import app
from datumguard.architecture_models import ArchitecturalConstraint
from datumguard.models import Constraint, Datum, DesignContract, LinearPattern
from datumguard.operations import OperationalControls, reset_operational_state_for_tests
from datumguard.piping_models import PipingConstraint


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_contract_rejects_nonfinite_coordinates_and_tolerances(
    sample_contract: DesignContract,
    value: float,
) -> None:
    for field in ("origin", "x_axis", "y_axis"):
        with pytest.raises(ValidationError):
            Datum.model_validate({field: [value, 0]})
    payload = sample_contract.model_dump(mode="python")
    payload["dimensions"][0]["tolerance_upper"] = value
    with pytest.raises(ValidationError):
        DesignContract.model_validate(payload)


def test_extreme_datum_is_validation_error_not_overflow() -> None:
    with pytest.raises(ValidationError):
        Datum(x_axis=(1e308, 0))
    direction = LinearPattern(
        id="p",
        source_feature_id="h",
        count=2,
        direction=(1e308, 0),
        spacing=10,
    )
    assert direction.direction == (1.0, 0.0)


@pytest.mark.parametrize("value", ["NaN", "Infinity", float("nan"), float("inf"), [], True])
@pytest.mark.parametrize(
    "model,kind",
    [
        (Constraint, "alignment"),
        (ArchitecturalConstraint, "column_grid_alignment"),
        (PipingConstraint, "endpoint_alignment"),
    ],
)
def test_constraint_parameter_cannot_bypass_tolerance_check(model, kind, value) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(
            {
                "id": "c",
                "type": kind,
                "entity_ids": ["a", "b"],
                "parameters": {"tolerance": value},
            }
        )


def test_api_rejects_nonfinite_json_before_geometry(sample_contract: DesignContract) -> None:
    payload = sample_contract.model_dump(mode="json")
    payload["datum"]["origin"][0] = float("nan")
    reset_operational_state_for_tests()
    response = TestClient(app).post(
        "/api/v1/designs/run",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DG_INPUT_INVALID"
    assert "bundle_base64" not in response.json()


def test_direct_clients_cannot_rotate_spoofed_cloudflare_ips(monkeypatch) -> None:
    from starlette.datastructures import Headers

    monkeypatch.delenv("DATUMGUARD_TRUST_CF_CONNECTING_IP", raising=False)
    monkeypatch.setenv("DATUMGUARD_ANON_RATE_LIMIT_PER_MINUTE", "1")
    monkeypatch.setenv("DATUMGUARD_RATE_LIMIT_ENABLED", "true")
    controls = OperationalControls()
    scope = {"client": ("198.51.100.5", 1234)}
    for index, expected in ((1, True), (2, False)):
        headers = Headers(
            {
                "CF-Ray": "aaaaaaaaaaaaaaaa-NRT",
                "CF-Connecting-IP": f"203.0.113.{index}",
            }
        )
        client_ip = controls.resolve_client_ip(headers, scope)
        assert client_ip == "198.51.100.5"
        allowed, _ = controls.rate_limit(
            client_ip=client_ip,
            route="/api/v1/contracts/validate",
            authenticated=False,
            heavy=False,
        )
        assert allowed is expected


@pytest.mark.parametrize("tool", ["drawing_verify", "artifact_audit", "artifact_compare"])
def test_mcp_rejects_oversize_before_decode(monkeypatch, tool) -> None:
    monkeypatch.setattr(mcp_server, "MAX_ARTIFACT_BYTES", 3)
    monkeypatch.setattr(mcp_server, "MAX_DXF_VERIFY_BYTES", 3)

    def forbidden_decode(*args, **kwargs):
        raise AssertionError("oversized payload must not be decoded")

    monkeypatch.setattr(mcp_server.base64, "b64decode", forbidden_decode)
    if tool == "drawing_verify":
        result = mcp_server.drawing_verify({}, "a" * 8)
    elif tool == "artifact_audit":
        result = mcp_server.artifact_audit("test.dxf", "a" * 8)
    else:
        result = mcp_server.artifact_compare("a.dxf", "a" * 8, "b.dxf", "a" * 8)
    assert result["status"] == "failed_verification"
    assert result["error"]["code"] == "DG_ARTIFACT_TOO_LARGE"


def test_mcp_checks_decoded_size_within_last_base64_quantum(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "MAX_DXF_VERIFY_BYTES", 4)
    result = mcp_server.drawing_verify({}, base64.b64encode(b"12345").decode())
    assert result["error"]["code"] == "DG_ARTIFACT_TOO_LARGE"


def test_mcp_malformed_dxf_has_structured_error() -> None:
    result = mcp_server.drawing_verify({}, "not base64!")
    assert result["status"] == "failed_verification"
    assert result["error"]["code"] == "DG_INPUT_INVALID"


@pytest.mark.parametrize(
    "fixture,layer",
    [
        ("architecture_studio.json", "A-WALL"),
        ("piping_utility.json", "P-PIPE"),
    ],
)
@pytest.mark.parametrize("tamper", ["bulge", "elevation", "extrusion"])
def test_domain_verifiers_reject_geometry_lost_by_xy_projection(fixture, layer, tamper) -> None:
    path = Path(__file__).parents[1] / "fixtures" / "examples" / fixture
    contract = json.loads(path.read_text(encoding="utf-8"))
    generated = mcp_server.drawing_generate(contract)
    document = ezdxf.read(io.StringIO(base64.b64decode(generated["dxf_base64"]).decode()))
    entity = next(item for item in document.modelspace() if item.dxf.layer == layer)
    if tamper == "bulge":
        points = list(entity.get_points("xyb"))
        points[0] = (points[0][0], points[0][1], 1.0)
        entity.set_points(points, format="xyb")
    elif tamper == "elevation":
        entity.dxf.elevation = 1000
    else:
        entity.dxf.extrusion = (0, 1, 0)
    stream = io.StringIO(newline="\n")
    document.write(stream)
    result = mcp_server.drawing_verify(
        contract,
        base64.b64encode(stream.getvalue().encode()).decode(),
    )
    assert result["status"] == "failed_verification"
    assert result["violations"]


def _symlink_or_skip(path: Path, target: Path, *, directory: bool = False) -> None:
    try:
        path.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")


def test_bundle_directory_escape_is_rejected_before_creating_outside_paths(tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_or_skip(root / ".datumguard", outside, directory=True)
    with pytest.raises(ValueError, match="must not be a link"):
        mcp_server._write_workspace_bundle(root, "run-id", b"bundle")
    assert list(outside.iterdir()) == []


def test_bundle_file_symlink_cannot_overwrite_external_file(tmp_path) -> None:
    root = tmp_path / "workspace"
    run = root / ".datumguard" / "runs" / "run-id"
    run.mkdir(parents=True)
    external = tmp_path / "external.zip"
    external.write_bytes(b"untouched")
    _symlink_or_skip(run / "datumguard-verified.zip", external)
    with pytest.raises(ValueError, match="must not be a link"):
        mcp_server._write_workspace_bundle(root, "run-id", b"bundle")
    assert external.read_bytes() == b"untouched"


def test_atomic_bundle_publication_does_not_write_through_hardlinks(tmp_path) -> None:
    root = tmp_path / "workspace"
    run = root / ".datumguard" / "runs" / "run-id"
    run.mkdir(parents=True)
    external = tmp_path / "external.zip"
    external.write_bytes(b"untouched")
    os.link(external, run / "datumguard-verified.zip")
    result = mcp_server._write_workspace_bundle(root, "run-id", b"bundle")
    assert result.read_bytes() == b"bundle"
    assert external.read_bytes() == b"untouched"
    assert len(list(run.iterdir())) == 1

from __future__ import annotations

import base64
import io
import json
import subprocess
import zipfile
from pathlib import Path

import ezdxf
import ifcopenshell
import ifcopenshell.api
import pytest

from datumguard import artifact_service, cad_subprocess, solid_service
from datumguard.artifact_service import audit_artifact, compare_artifacts
from datumguard.cad_subprocess import CadWorkerFailure, run_parser_worker
from datumguard.mcp_server import artifact_audit as mcp_artifact_audit
from datumguard.mcp_server import solid_generate_verify
from datumguard.models import DesignContract
from datumguard.service import generate_only
from datumguard.solid_models import SolidPartContract
from datumguard.solid_service import run_solid_design

FIXTURES = Path(__file__).parents[1] / "fixtures" / "examples"


def _dxf_bytes(document: ezdxf.document.Drawing) -> bytes:
    stream = io.StringIO()
    document.write(stream)
    return stream.getvalue().encode(document.encoding)


def _ifc_bytes() -> bytes:
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcProject", name="DatumGuard IFC"
    )
    ifcopenshell.api.run("unit.assign_unit", model)
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcBuilding", name="Building"
    )
    storey = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcBuildingStorey", name="Level 01"
    )
    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run(
        "aggregate.assign_object", model, products=[building], relating_object=site
    )
    ifcopenshell.api.run(
        "aggregate.assign_object", model, products=[storey], relating_object=building
    )
    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall 01")
    ifcopenshell.api.run(
        "spatial.assign_container", model, products=[wall], relating_structure=storey
    )
    return model.to_string().encode("utf-8")


def test_audit_generated_dxf_preserves_original_and_renders_preview() -> None:
    contract = DesignContract.model_validate_json(
        (FIXTURES / "design_contract.json").read_text(encoding="utf-8")
    )
    dxf_bytes = base64.b64decode(generate_only(contract).dxf_base64)

    result = audit_artifact("mounting-plate.dxf", dxf_bytes)

    assert result.status == "audited"
    assert result.format == "dxf"
    assert result.original_preserved is True
    assert result.approval_eligible is False
    assert result.summary["dxf_version"] == "AC1027"
    assert result.summary["units"] == "Millimeters"
    assert result.summary["datumguard_xdata_entities"] > 0
    assert result.preview_svg and result.preview_svg.startswith("<svg")


def test_unitless_dxf_requires_confirmation() -> None:
    document = ezdxf.new("R2013")
    document.units = 0
    document.modelspace().add_line((0, 0), (100, 0))

    result = audit_artifact("unitless.dxf", _dxf_bytes(document))

    assert result.status == "needs_confirmation"
    assert "DG_ARTIFACT_UNIT_CONFIRMATION_REQUIRED" in {issue.code for issue in result.issues}


def test_dxf_revision_compare_detects_geometry_change() -> None:
    baseline = ezdxf.new("R2013")
    baseline.units = ezdxf.units.MM
    baseline.modelspace().add_line((0, 0), (100, 0))
    candidate = ezdxf.new("R2013")
    candidate.units = ezdxf.units.MM
    candidate.modelspace().add_line((0, 0), (125, 0))

    result = compare_artifacts(
        "baseline.dxf",
        _dxf_bytes(baseline),
        "candidate.dxf",
        _dxf_bytes(candidate),
    )

    assert result.status == "audited"
    assert result.same_artifact is False
    assert result.comparison["geometry"]["added_entity_count"] == 1
    assert result.comparison["geometry"]["removed_entity_count"] == 1


def test_ifc_audit_and_global_id_revision_compare() -> None:
    baseline_bytes = _ifc_bytes()
    candidate_model = ifcopenshell.file.from_string(baseline_bytes.decode("utf-8"))
    wall = candidate_model.by_type("IfcWall")[0]
    wall.Name = "Wall 01 revised"
    candidate_bytes = candidate_model.to_string().encode("utf-8")

    audit = audit_artifact("model.ifc", baseline_bytes)
    comparison = compare_artifacts("baseline.ifc", baseline_bytes, "candidate.ifc", candidate_bytes)

    assert audit.status == "audited"
    assert audit.summary["ifc_schema"] == "IFC4"
    assert audit.summary["type_counts"]["IfcWall"] == 1
    assert comparison.status == "audited"
    assert wall.GlobalId in comparison.comparison["ifc_revision"]["changed_global_ids"]


@pytest.mark.parametrize(
    "fixture_name,expected_family",
    [
        ("solid_mounting_plate.json", "mounting_plate"),
        ("solid_angle_bracket.json", "angle_bracket"),
        ("solid_flange.json", "flange"),
    ],
)
def test_solid_contract_generates_and_independently_verifies_step(
    fixture_name: str,
    expected_family: str,
) -> None:
    contract = SolidPartContract.model_validate_json(
        (FIXTURES / fixture_name).read_text(encoding="utf-8")
    )

    result = run_solid_design(contract)

    assert result.status.value == "passed"
    assert result.summary["part_family"] == expected_family
    assert result.summary["valid_shape"] is True
    assert result.summary["summary_source"] == "independent_step_reimport"
    assert result.artifact_hash and result.artifact_hash.startswith("sha256:")
    assert result.measurements and all(item.passed for item in result.measurements)
    assert result.preview_mesh and result.preview_mesh.triangles
    assert result.bundle_base64
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result.bundle_base64))) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["authority"] == "solid.step"
        assert bundle.read("solid.step").startswith(b"ISO-10303-21")


def test_step_generation_is_byte_deterministic() -> None:
    contract = SolidPartContract.model_validate_json(
        (FIXTURES / "solid_mounting_plate.json").read_text(encoding="utf-8")
    )

    first = run_solid_design(contract)
    second = run_solid_design(contract)

    assert first.artifact_hash == second.artifact_hash
    assert first.bundle_base64 == second.bundle_base64


def test_independent_step_reimport_blocks_a_tampered_writer_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = SolidPartContract.model_validate_json(
        (FIXTURES / "solid_mounting_plate.json").read_text(encoding="utf-8")
    )
    real_worker = solid_service.run_cad_worker

    def wrong_dimension_worker(payload: dict[str, object]) -> dict[str, object]:
        if payload.get("operation") != "generate_solid":
            return real_worker(payload)
        wrong_contract = json.loads(json.dumps(payload["contract"]))
        wrong_contract["geometry"]["width"] += 5
        return real_worker({**payload, "contract": wrong_contract})

    monkeypatch.setattr(solid_service, "run_cad_worker", wrong_dimension_worker)

    result = run_solid_design(contract)

    assert result.status.value == "failed_verification"
    assert "DG_STEP_DIMENSION_OUT_OF_TOLERANCE" in {
        violation.code for violation in result.violations
    }
    assert result.step_base64 is None
    assert result.bundle_base64 is None


def test_new_mcp_tools_return_structured_artifact_evidence() -> None:
    document = ezdxf.new("R2013")
    document.units = ezdxf.units.MM
    document.modelspace().add_circle((0, 0), 25)
    audited = mcp_artifact_audit(
        "circle.dxf", base64.b64encode(_dxf_bytes(document)).decode("ascii")
    )
    contract = json.loads((FIXTURES / "solid_flange.json").read_text(encoding="utf-8"))
    solid = solid_generate_verify(contract)

    assert audited["status"] == "audited"
    assert audited["format"] == "dxf"
    assert solid["status"] == "passed"
    assert solid["summary"]["part_family"] == "flange"


def test_dxf_parser_worker_failure_is_contained_and_scrubbed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = ezdxf.new("R2013")
    document.modelspace().add_line((0, 0), (10, 0))

    def failed_worker(_payload: dict[str, object]) -> dict[str, object]:
        raise CadWorkerFailure(
            "worker crashed",
            {"return_code": 137, "stderr": "C:/private/parser/path", "failure": "worker_exit"},
        )

    monkeypatch.setattr(artifact_service, "run_parser_worker", failed_worker)
    result = audit_artifact("isolated-failure.dxf", _dxf_bytes(document))

    assert result.status == "failed_verification"
    assert result.error is not None
    assert result.error.code == "DG_ARTIFACT_DXF_READ_FAILED"
    serialized = result.model_dump_json()
    assert "stderr" not in serialized
    assert "private/parser" not in serialized
    assert result.error.details == {"isolated_worker": True, "failure": "worker_exit"}


def test_subprocess_failure_does_not_expose_stderr_or_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args=["python"],
            returncode=137,
            stdout=b"",
            stderr=b"C:/private/native/path and secret details",
        )

    monkeypatch.setattr(cad_subprocess.subprocess, "run", failed_run)
    with pytest.raises(CadWorkerFailure) as captured:
        run_parser_worker({"operation": "test"})

    assert captured.value.details == {"return_code": 137, "failure": "worker_exit"}
    assert "private/native" not in str(captured.value.details)

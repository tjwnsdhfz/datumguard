from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element
import numpy as np
import pytest
from ifctester.ids import Entity, Ids, Property, Specification

from datumguard import openbim_rules
from datumguard import openbim_service as openbim_service_module
from datumguard.cad_subprocess import CadWorkerFailure
from datumguard.ifc_evidence import sha256_bytes
from datumguard.openbim_models import (
    DEFAULT_VIRTUAL_FAB_PROFILE,
    OpenBimRuleStatus,
    OpenBimSourceHashes,
)
from datumguard.openbim_reporting import (
    attach_reports,
    canonical_evidence_json,
    render_bcfzip,
    render_evidence_html,
)
from datumguard.openbim_service import OpenBimServiceFailure, run_openbim_evidence
from datumguard.openbim_worker import evaluate_openbim_payload


def _add_pset(model: Any, product: Any, name: str, properties: dict[str, Any]) -> None:
    pset = ifcopenshell.api.run("pset.add_pset", model, product=product, name=name)
    ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=properties)


def _model_bytes(*, asset_key: str = "L1-PS-001", length_unit: str = "MILLIMETERS") -> bytes:
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcProject", name="Virtual FAB"
    )
    ifcopenshell.api.run(
        "unit.assign_unit",
        model,
        length={"is_metric": True, "raw": length_unit},
    )
    model_context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_context = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_context,
    )
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

    tool = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcBuildingElementProxy", name="FAB Tool"
    )
    tool.ObjectType = "FAB_TOOL"
    pipe = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcPipeSegment", name="PCW Pipe"
    )
    for product in (tool, pipe):
        ifcopenshell.api.run(
            "spatial.assign_container", model, products=[product], relating_structure=storey
        )
    _add_pset(
        model,
        tool,
        "DG_Identity",
        {"AssetKey": "L1-TOOL-001", "AssetTag": "VF-TL-001"},
    )
    _add_pset(
        model,
        pipe,
        "DG_Identity",
        {"AssetKey": asset_key, "AssetTag": "VF-PS-001"},
    )
    for product in (tool, pipe):
        _add_pset(
            model,
            product,
            "DG_VFabUtility",
            {"UtilityType": "PCW", "SystemCode": "SYS-PCW-A", "Criticality": "LOW"},
        )
    _add_pset(
        model,
        tool,
        "DG_VFabClearance",
        {"ServiceSide": "+X", "ServiceDepth": 0.6 if length_unit == "METERS" else 600.0},
    )
    for product in (tool, pipe):
        representation = ifcopenshell.api.run(
            "geometry.add_wall_representation",
            model,
            context=body_context,
            length=1.0,
            height=1.0,
            thickness=1.0,
        )
        ifcopenshell.api.run(
            "geometry.assign_representation",
            model,
            product=product,
            representation=representation,
        )
    _move_product(model, pipe, x=2.0)
    return model.to_string().encode("utf-8")


def _move_product(model: Any, product: Any, *, x: float) -> None:
    matrix = np.eye(4)
    matrix[0, 3] = x
    ifcopenshell.api.run(
        "geometry.edit_object_placement", model, product=product, matrix=matrix, is_si=True
    )


def _candidate(
    baseline: bytes,
    *,
    obstacle_x: float | None = None,
    system_code: str | None = None,
    remove_asset_tag: bool = False,
) -> bytes:
    model = ifcopenshell.file.from_string(baseline.decode("utf-8"))
    pipe = model.by_type("IfcPipeSegment")[0]
    if obstacle_x is not None:
        _move_product(model, pipe, x=obstacle_x)
    if system_code is not None:
        pset_id = ifcopenshell.util.element.get_psets(pipe, psets_only=True)["DG_VFabUtility"]["id"]
        ifcopenshell.api.run(
            "pset.edit_pset",
            model,
            pset=model.by_id(pset_id),
            properties={"SystemCode": system_code},
        )
    if remove_asset_tag:
        pset_id = ifcopenshell.util.element.get_psets(pipe, psets_only=True)["DG_Identity"]["id"]
        ifcopenshell.api.run(
            "pset.edit_pset",
            model,
            pset=model.by_id(pset_id),
            properties={"AssetTag": None},
            should_purge=True,
        )
    return model.to_string().encode("utf-8")


def _ids_bytes() -> bytes:
    document = Ids(title="Virtual FAB information contract")
    specification = Specification(
        name="IDS-01 AssetTag",
        minOccurs=1,
        maxOccurs="unbounded",
        ifcVersion=["IFC4"],
    )
    specification.applicability.append(Entity(name="IFCPIPESEGMENT"))
    specification.requirements.append(
        Property(
            propertySet="DG_Identity",
            baseName="AssetTag",
            dataType="IFCLABEL",
        )
    )
    document.specifications.append(specification)
    return document.to_string().encode("utf-8")


def _evaluate(baseline: bytes, candidate: bytes):  # type: ignore[no-untyped-def]
    return evaluate_openbim_payload(
        {
            "operation": "openbim_evidence",
            "baseline_b64": base64.b64encode(baseline).decode("ascii"),
            "candidate_b64": base64.b64encode(candidate).decode("ascii"),
            "requirements_b64": base64.b64encode(_ids_bytes()).decode("ascii"),
            "profile": DEFAULT_VIRTUAL_FAB_PROFILE.model_dump(mode="json"),
        }
    )


def test_clean_model_passes_all_registered_rules() -> None:
    baseline = _model_bytes()
    report = _evaluate(baseline, baseline)

    assert report.status == "passed"
    assert report.issues == []
    assert all(result.status == OpenBimRuleStatus.PASSED for result in report.rule_results)
    assert report.baseline_hash == sha256_bytes(baseline)


def test_clearance_boundary_contact_passes_and_positive_overlap_fails() -> None:
    baseline = _model_bytes()

    boundary = _evaluate(baseline, _candidate(baseline, obstacle_x=1.6))
    outside = _evaluate(baseline, _candidate(baseline, obstacle_x=1.601))
    overlap = _evaluate(baseline, _candidate(baseline, obstacle_x=1.599))

    assert (
        next(result for result in boundary.rule_results if result.rule_id == "GEO-01").status
        == "passed"
    )
    assert (
        next(result for result in outside.rule_results if result.rule_id == "GEO-01").status
        == "passed"
    )
    geometry = next(result for result in overlap.rule_results if result.rule_id == "GEO-01")
    assert geometry.status == "failed"
    issue = next(issue for issue in overlap.issues if issue.rule_id == "GEO-01")
    assert issue.entity_pair == sorted(issue.entity_pair or [])
    assert issue.location is not None


def test_clearance_is_equivalent_for_metre_and_millimetre_projects() -> None:
    millimetre = _model_bytes(length_unit="MILLIMETERS")
    metre = _model_bytes(length_unit="METERS")

    millimetre_result = _evaluate(millimetre, _candidate(millimetre, obstacle_x=1.599))
    metre_result = _evaluate(metre, _candidate(metre, obstacle_x=1.599))

    assert (
        next(
            result for result in millimetre_result.rule_results if result.rule_id == "GEO-01"
        ).status
        == "failed"
    )
    assert (
        next(result for result in metre_result.rule_results if result.rule_id == "GEO-01").status
        == "failed"
    )
    mm_overlap = next(
        issue.actual for issue in millimetre_result.issues if issue.rule_id == "GEO-01"
    )
    m_overlap = next(issue.actual for issue in metre_result.issues if issue.rule_id == "GEO-01")
    assert mm_overlap == m_overlap


def test_missing_geometry_is_not_evaluable_instead_of_a_pass() -> None:
    baseline = _model_bytes()
    candidate = ifcopenshell.file.from_string(baseline.decode("utf-8"))
    tool = candidate.by_type("IfcBuildingElementProxy")[0]
    representation = tool.Representation.Representations[0]
    ifcopenshell.api.run(
        "geometry.unassign_representation",
        candidate,
        product=tool,
        representation=representation,
    )
    ifcopenshell.api.run("geometry.remove_representation", candidate, representation=representation)

    report = _evaluate(baseline, candidate.to_string().encode("utf-8"))

    geometry = next(result for result in report.rule_results if result.rule_id == "GEO-01")
    assert report.status == "needs_confirmation"
    assert geometry.status == "not_evaluable"
    assert any(issue.rule_id == "GEO-01" and issue.severity == "warning" for issue in report.issues)


def test_registered_authorization_allows_only_the_exact_locked_change() -> None:
    baseline = _model_bytes(asset_key="L1-PS-001")

    authorized = _evaluate(baseline, _candidate(baseline, system_code="SYS-PCW-B"))
    unauthorized = _evaluate(baseline, _candidate(baseline, system_code="SYS-PCW-C"))

    assert not [issue for issue in authorized.issues if issue.rule_id == "REV-03"]
    assert (
        next(result for result in authorized.rule_results if result.rule_id == "REV-03").status
        == "passed"
    )
    revision_issue = next(issue for issue in unauthorized.issues if issue.rule_id == "REV-03")
    assert revision_issue.raw == {"asset_key": "L1-PS-001", "authorization": None}


def test_ifctester_failure_is_normalized_and_deduplicated() -> None:
    baseline = _model_bytes()
    report = _evaluate(baseline, _candidate(baseline, remove_asset_tag=True))

    ids_issues = [issue for issue in report.issues if issue.rule_id == "IDS-01"]
    assert report.status == "failed_verification"
    assert len(ids_issues) == 1
    assert ids_issues[0].entity_ids
    assert ids_issues[0].field == "DG_Identity.AssetTag"
    assert not [issue for issue in report.issues if issue.rule_id == "REV-03"]


def test_duplicate_identity_keeps_overall_failure_while_revision_is_ambiguous() -> None:
    baseline = _model_bytes()
    candidate = ifcopenshell.file.from_string(baseline.decode("utf-8"))
    tool = candidate.by_type("IfcBuildingElementProxy")[0]
    pipe = candidate.by_type("IfcPipeSegment")[0]
    pipe.GlobalId = tool.GlobalId

    report = _evaluate(baseline, candidate.to_string().encode("utf-8"))

    assert report.status == "failed_verification"
    assert any(issue.rule_id == "IFC-02" for issue in report.issues)
    assert (
        next(result for result in report.rule_results if result.rule_id == "REV-02").status
        == "ambiguous"
    )


def test_representative_ids_qname_schema_regression() -> None:
    fixtures = Path(__file__).parents[1] / "fixtures" / "openbim"
    candidate_bytes = (fixtures / "representative" / "v0_clean.ifc").read_bytes()
    ids_bytes = (fixtures / "virtual_fab_v1.ids").read_bytes()
    candidate = ifcopenshell.file.from_string(candidate_bytes.decode("utf-8"))
    hashes = OpenBimSourceHashes(
        baseline=sha256_bytes(candidate_bytes),
        candidate=sha256_bytes(candidate_bytes),
        ids=sha256_bytes(ids_bytes),
        profile="sha256:" + ("0" * 64),
    )

    results, issues = openbim_rules.validate_ids_requirements(
        candidate, ids_bytes.decode("utf-8"), hashes
    )

    assert {result.rule_id for result in results} == {
        "IDS-01",
        "IDS-02",
        "IDS-03",
        "IDS-04",
        "IDS-05",
        "IDS-06",
    }
    assert sum(result.evaluated_count for result in results) > 18
    assert issues == []
    assert all(result.status == "passed" for result in results)


def test_ids_dtd_and_external_entity_declarations_are_rejected() -> None:
    baseline = _model_bytes()
    candidate = ifcopenshell.file.from_string(baseline.decode("utf-8"))
    hashes = OpenBimSourceHashes(
        baseline=sha256_bytes(baseline),
        candidate=sha256_bytes(baseline),
        ids="sha256:" + ("1" * 64),
        profile="sha256:" + ("2" * 64),
    )
    malicious = '<!DOCTYPE ids [<!ENTITY xxe SYSTEM "file:///private">]><ids>&xxe;</ids>'

    with pytest.raises(ValueError, match="not allowed"):
        openbim_rules.validate_ids_requirements(candidate, malicious, hashes)


def test_schema_checker_failure_is_not_reported_as_a_pass(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    baseline_bytes = _model_bytes()
    model = ifcopenshell.file.from_string(baseline_bytes.decode("utf-8"))
    real_import = openbim_rules.importlib.import_module

    def failing_import(name: str):  # type: ignore[no-untyped-def]
        if name == "ifcopenshell.validate":
            raise ImportError(name)
        return real_import(name)

    monkeypatch.setattr(openbim_rules.importlib, "import_module", failing_import)
    hashes = openbim_rules.OpenBimSourceHashes(
        baseline=sha256_bytes(baseline_bytes),
        candidate=sha256_bytes(baseline_bytes),
        ids=sha256_bytes(_ids_bytes()),
        profile="sha256:" + ("0" * 64),
    )

    results, issues, _ = openbim_rules.validate_ifc_integrity(
        model, DEFAULT_VIRTUAL_FAB_PROFILE, hashes
    )

    schema = next(result for result in results if result.rule_id == "IFC-00")
    assert schema.status == "not_evaluable"
    assert any(issue.rule_id == "IFC-00" and issue.severity == "warning" for issue in issues)


def test_canonical_json_excludes_timings_and_html_escapes_content() -> None:
    baseline = _model_bytes()
    report = _evaluate(baseline, _candidate(baseline, obstacle_x=1.5))
    first = report.model_copy(update={"timings_ms": {"engine_total": 1.0}})
    second = report.model_copy(update={"timings_ms": {"engine_total": 999.0}})
    injected_issue = report.issues[0].model_copy(update={"message": "<script>alert(1)</script>"})
    injected = report.model_copy(update={"issues": [injected_issue, *report.issues[1:]]})

    assert canonical_evidence_json(first) == canonical_evidence_json(second)
    rendered = render_evidence_html(injected).decode("utf-8")
    assert "<script>alert(1)</script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_bcf_export_semantically_round_trips_twice() -> None:
    from bcf.v3.bcfxml import BcfXml

    baseline = _model_bytes()
    report = _evaluate(baseline, _candidate(baseline, obstacle_x=1.5))

    for index in range(2):
        content = render_bcfzip(report, max_topics=100)
        path = Path.cwd() / f".test-openbim-{index}.bcfzip"
        try:
            path.write_bytes(content)
            loaded = BcfXml.load(path)
            try:
                assert loaded is not None
                assert len(loaded.topics) == len(report.issues)
                loaded_topics = list(loaded.topics.values())
                assert all(topic.topic.topic_status == "Open" for topic in loaded_topics)
                assert all(topic.topic.title.startswith("[") for topic in loaded_topics)
                expected_guids = {
                    entity_id
                    for issue in report.issues
                    for entity_id in (issue.entity_pair or issue.entity_ids)
                    if len(entity_id) == 22
                }
                loaded_guids = {
                    guid
                    for topic in loaded_topics
                    for viewpoint in topic.viewpoints.values()
                    for guid in (viewpoint.get_selected_guids() or [])
                }
                assert loaded_guids == expected_guids
            finally:
                if loaded is not None:
                    loaded.close()
        finally:
            path.unlink(missing_ok=True)


def test_public_service_uses_worker_and_returns_hashed_downloads() -> None:
    baseline = _model_bytes()

    report = run_openbim_evidence(
        baseline_bytes=baseline,
        candidate_bytes=baseline,
        requirements_bytes=_ids_bytes(),
        profile="virtual-fab-v1",
        include_html=True,
        include_bcf=True,
    )

    assert report.status == "passed"
    assert [artifact.kind for artifact in report.reports] == [
        "bcfzip",
        "evidence_json",
        "html",
        "manifest",
    ]
    for artifact in report.reports:
        content = base64.b64decode(artifact.content_base64, validate=True)
        assert len(content) == artifact.byte_size
        assert sha256_bytes(content) == artifact.artifact_hash
    manifest = json.loads(
        base64.b64decode(
            next(item for item in report.reports if item.kind == "manifest").content_base64
        )
    )
    assert manifest["input_hashes"]["candidate"] == report.candidate_hash


def test_attach_reports_keeps_bcf_randomness_out_of_canonical_evidence() -> None:
    baseline = _model_bytes()
    report = _evaluate(baseline, _candidate(baseline, obstacle_x=1.5))

    first = attach_reports(report, include_html=True, include_bcf=True, max_bcf_topics=100)
    second = attach_reports(report, include_html=True, include_bcf=True, max_bcf_topics=100)

    assert canonical_evidence_json(first) == canonical_evidence_json(second)
    assert (
        next(item for item in first.reports if item.kind == "evidence_json").artifact_hash
        == next(item for item in second.reports if item.kind == "evidence_json").artifact_hash
    )


def test_openbim_worker_failure_is_scrubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed_worker(_payload: dict[str, object]) -> dict[str, object]:
        raise CadWorkerFailure(
            "worker crashed",
            {
                "failure": "worker_exit",
                "return_code": 137,
                "stderr": "C:/private/native/path TOKEN=secret",
            },
        )

    monkeypatch.setattr(openbim_service_module, "run_openbim_worker", failed_worker)
    with pytest.raises(OpenBimServiceFailure) as captured:
        run_openbim_evidence(
            baseline_bytes=b"baseline",
            candidate_bytes=b"candidate",
            requirements_bytes=b"requirements",
        )

    assert captured.value.code == "DG_OPENBIM_WORKER_UNAVAILABLE"
    assert captured.value.details == {
        "isolated_worker": True,
        "failure": "worker_exit",
        "return_code": 137,
    }
    assert "private" not in str(captured.value.details)
    assert "secret" not in str(captured.value.details)

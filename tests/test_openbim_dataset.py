from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import ifcopenshell
import pytest
from ifctester import ids, reporter

from datumguard.ifc_evidence import property_value
from datumguard.openbim_models import OpenBimProfile

ROOT = Path(__file__).resolve().parents[1]


def load_tool_module(name: str) -> ModuleType:
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load tool module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = load_tool_module("generate_virtual_fab_fixtures")
experiment = load_tool_module("run_openbim_experiment")
representative_export = load_tool_module("export_openbim_representative")


def generated_representative(tmp_path: Path) -> Path:
    output = tmp_path / "openbim"
    generator.generate_dataset(output, split="representative", evaluation_per_layout=4)
    return output


def test_representative_bcf_structure_check_is_independent_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("bcf.version", '<Version VersionId="3.0"/>')
        archive.writestr("topic-guid/markup.bcf", "<Markup/>")

    result = representative_export.inspect_bcfzip(stream.getvalue(), expected_topics=1)

    assert result["generic_zip_xml_parse"] is True
    assert result["topic_markup_count"] == 1
    assert result["independent_viewer_import"] is False

    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("bcf.version", '<Version VersionId="3.0"/>')
        archive.writestr("../topic/markup.bcf", "<Markup/>")
    with pytest.raises(RuntimeError, match="unsafe path"):
        representative_export.inspect_bcfzip(unsafe.getvalue(), expected_topics=1)

    monkeypatch.setattr(representative_export, "ROOT", tmp_path)
    output = tmp_path / "representative"
    staging = tmp_path / ".representative.staging-test"
    output.mkdir()
    staging.mkdir()
    (output / "old.json").write_text("old", encoding="utf-8")
    (staging / "new.json").write_text("new", encoding="utf-8")
    calls = 0

    def fail_final_publish(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated publish failure")
        os.replace(source, destination)

    with pytest.raises(OSError, match="simulated publish failure"):
        representative_export.publish_staged_directory(staging, output, replace=fail_final_publish)
    assert (output / "old.json").read_text(encoding="utf-8") == "old"
    assert not any(tmp_path.glob(".representative.backup-*"))


def test_representative_generation_is_byte_deterministic(tmp_path: Path) -> None:
    first = generated_representative(tmp_path / "first")
    second = generated_representative(tmp_path / "second")

    assert generator.relative_hashes(first) == generator.relative_hashes(second)


def test_representative_ids_profile_truth_and_duplicate_oracle(tmp_path: Path) -> None:
    output = generated_representative(tmp_path)
    profile_data = json.loads((output / "virtual_fab_profile.json").read_text(encoding="utf-8"))
    profile = OpenBimProfile.model_validate(profile_data)
    assert profile.profile_id == "virtual-fab-v1"
    assert len(profile.authorized_changes) == 3

    ids_path = output / "virtual_fab_v1.ids"
    ids_xml = ids_path.read_text(encoding="utf-8")
    ids.get_schema().validate(ids_xml)
    case_dir = output / "representative"
    failed_by_variant: dict[str, int] = {}
    for variant in ("v0_clean", "v1_authorized", "v1_faulty", "v2_corrected"):
        document = ids.open(str(ids_path), validate=True)
        document.validate(ifcopenshell.open(str(case_dir / f"{variant}.ifc")))
        report = reporter.Json(document).report()
        failed_by_variant[variant] = sum(
            not specification["status"] for specification in report["specifications"]
        )
    assert failed_by_variant == {
        "v0_clean": 0,
        "v1_authorized": 0,
        "v1_faulty": 5,
        "v2_corrected": 0,
    }

    mutation_manifest = json.loads(
        (case_dir / "mutation_manifest.json").read_text(encoding="utf-8")
    )
    duplicate_groups = mutation_manifest["integrity_oracle"]["duplicate_groups_by_variant"]
    intended_guid = mutation_manifest["integrity_oracle"]["expected_faulty_duplicate_global_id"]
    assert duplicate_groups["v0_clean"] == {}
    assert duplicate_groups["v1_authorized"] == {}
    assert duplicate_groups["v2_corrected"] == {}
    assert list(duplicate_groups["v1_faulty"]) == [intended_guid]
    assert len(duplicate_groups["v1_faulty"][intended_guid]) == 2

    mutation_targets: list[str] = []
    for mutation in mutation_manifest["mutations"]:
        mutation_targets.extend(
            mutation["target"].get("asset_keys", [mutation["target"]["asset_key"]])
        )
    assert len(mutation_targets) == 12
    assert len(set(mutation_targets)) == 12

    truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))
    assert truth["expected_primary_alert_count"] == 11
    assert len(truth["candidates"]["v1_faulty"]["expected_issues"]) == 11
    assert truth["admissible_secondary_alert_count"] == 6
    assert len(truth["candidates"]["v1_faulty"]["admissible_secondary_issues"]) == 6


def test_authorized_variant_exercises_allowlisted_locked_change(tmp_path: Path) -> None:
    output = generated_representative(tmp_path)
    case_dir = output / "representative"

    def system_code(path: Path) -> Any:
        model = ifcopenshell.open(str(path))
        for entity in model.by_type("IfcPipeSegment"):
            if property_value(entity, "DG_Identity.AssetKey") == "L1-PS-001":
                return property_value(entity, "DG_VFabUtility.SystemCode")
        raise AssertionError("Authorized fixture target was not found")

    assert system_code(case_dir / "v0_clean.ifc") == "SYS-PCW-A"
    assert system_code(case_dir / "v1_authorized.ifc") == "SYS-PCW-B"


def test_matching_excludes_admissible_secondary_from_primary_counts() -> None:
    expected = [
        {
            "fault_id": "I01",
            "rule_id": "IDS-01",
            "family": "Information",
            "asset_keys": ["L1-PS-002"],
            "entity_pair": [],
            "step_ids": [],
            "field": "DG_Identity.AssetTag",
        }
    ]
    secondary = [
        {
            "fault_id": "I01",
            "rule_id": "REV-03",
            "family": "Information",
            "asset_keys": ["L1-PS-002"],
            "entity_pair": [],
            "step_ids": [],
            "field": "DG_Identity.AssetTag",
        }
    ]
    predicted = [
        {**expected[0], "issue_key": "primary"},
        {**secondary[0], "issue_key": "secondary"},
    ]
    match = experiment.match_alerts(expected, secondary, predicted)

    assert (match["tp"], match["fp"], match["fn"]) == (1, 0, 0)
    assert len(match["matched_admissible_secondary"]) == 1
    assert "IFC-00" not in experiment.PRIMARY_RULE_IDS


def test_geometry_matching_uses_preregistered_raw_global_id_pair() -> None:
    expected = {
        "fault_id": "G01",
        "rule_id": "GEO-01",
        "family": "Geometry",
        "asset_keys": ["L1-PS-001"],
        "entity_pair": ["L1-PS-001", "L1-TL-001"],
        "global_id_pair": ["duplicate-guid", "obstacle-guid"],
        "step_ids": [],
        "field": "placement",
    }
    predicted = {
        "rule_id": "GEO-01",
        "asset_keys": ["L1-PS-001", "L1-TL-001"],
        "entity_pair": ["duplicate-guid", "L1-PS-001"],
        "global_id_pair": ["duplicate-guid", "obstacle-guid"],
        "step_ids": [100, 200],
        "field": "",
        "issue_key": "geometry",
    }

    match = experiment.match_alerts([expected], [], [predicted])

    assert (match["tp"], match["fp"], match["fn"]) == (1, 0, 0)

    with pytest.raises(ValueError, match="two distinct non-empty GlobalIds"):
        experiment.alert_key({"rule_id": "GEO-01", "global_id_pair": []})
    with pytest.raises(ValueError, match="two distinct non-empty GlobalIds"):
        experiment.alert_key({"rule_id": "GEO-01", "global_id_pair": ["same-guid", "same-guid"]})


def test_ablation_recall_keeps_fixed_primary_fault_denominator() -> None:
    expected = [
        {
            "rule_id": rule_id,
            "asset_keys": [f"asset-{index}"],
            "field": experiment.canonical_field(rule_id, None),
        }
        for index, rule_id in enumerate(("IDS-01", "IFC-03", "GEO-01", "REV-02"), 1)
    ]
    for item in expected:
        item.setdefault(
            "global_id_pair",
            ["geometry-a", "geometry-b"] if item["rule_id"] == "GEO-01" else [],
        )
        item.setdefault("entity_pair", [])
        item.setdefault("step_ids", [])
    predictions = [{**expected[0], "issue_key": "ids-only"}]

    matches = experiment.ablation_matches(expected, [], predictions)

    assert matches["A"]["tp"] == 1
    assert matches["A"]["fn"] == 3
    assert matches["A"]["recall"] == 0.25


def test_postfreeze_macro_policy_does_not_claim_preregistered_pass() -> None:
    statuses = experiment.preregistered_target_status(
        {
            "families": {"Information": {"f1": 1.0}, "Geometry": {"f1": 0.96}},
            "family_macro_f1_by_family": {"Information": 0.94, "Revision": 0.95},
            "controls": {"clean_false_positives": 0, "authorized_false_positives": 0},
            "runtime": {"engine_p95_ms": 4999.0},
        }
    )

    assert statuses["Information macro-F1 >= 0.95"]["status"] == "NOT_CONCLUSIVE"
    assert statuses["Revision macro-F1 >= 0.95"]["status"] == "NOT_CONCLUSIVE"
    assert "not preregistered" in statuses["Information macro-F1 >= 0.95"]["basis"]
    assert statuses["Information macro-F1 >= 0.95"]["value"] is None
    assert statuses["Information macro-F1 >= 0.95"]["sensitivity_value"] == 0.94
    assert "post-freeze sensitivity" in experiment.target_assessment_line(
        "Information macro-F1 >= 0.95",
        statuses["Information macro-F1 >= 0.95"],
    )
    assert statuses["Geometry F1 >= 0.95"]["status"] == "PASS"

    source_hashes = {
        key: f"sha256:{character * 64}"
        for key, character in zip(("baseline", "candidate", "ids", "profile"), "1234", strict=True)
    }
    report = {
        "baseline_hash": source_hashes["baseline"],
        "candidate_hash": source_hashes["candidate"],
        "ids_hash": source_hashes["ids"],
        "profile_hash": source_hashes["profile"],
        "rule_results": [{"rule_id": "IDS-01"}, {"rule_id": "IFC-00"}],
    }
    record = {
        "candidate": "v1_faulty",
        "matches": {
            "A": _match(1, 0, 3),
            "B": _match(2, 0, 2),
            "C": _match(3, 0, 1),
            "D": _match(4, 0, 0),
        },
        "normalized_predictions": [
            *[
                {
                    "rule_id": "IDS-01",
                    "asset_keys": [f"asset-{index}"],
                    "entity_pair": [],
                    "step_ids": [],
                    "source_hashes": source_hashes,
                }
                for index in range(4)
            ],
            {
                "rule_id": "IFC-00",
                "asset_keys": [],
                "entity_pair": [],
                "step_ids": [],
                "source_hashes": source_hashes,
            },
        ],
        "runs": [{"wall_ms": 2.0, "engine_ms": 1.0, "report": report}],
        "determinism": {"identical_runs": True},
    }
    metrics, _ = experiment.aggregate_metrics([record])

    assert metrics["incremental_recall"] == {
        "A_to_B": 0.25,
        "B_to_C": 0.25,
        "C_to_D": 0.25,
    }
    assert metrics["paired_incremental_recall"]["A_to_B"]["case_count"] == 1
    assert metrics["traceability"]["all_issues"]["issue_count"] == 5
    assert metrics["traceability"]["all_issues"]["source_hash_coverage_count"] == 5
    assert metrics["traceability"]["all_issues"]["rule_id_coverage_count"] == 5
    assert metrics["traceability"]["all_issues"]["entity_reference_coverage_count"] == 4
    assert metrics["traceability"]["primary_issues"]["issue_count"] == 4
    assert metrics["traceability"]["primary_issues"]["source_hash_coverage_count"] == 4
    assert metrics["traceability"]["primary_issues"]["rule_id_coverage_count"] == 4
    assert metrics["traceability"]["primary_issues"]["entity_reference_coverage_count"] == 4

    normalized = experiment.normalized_prediction(
        {"rule_id": "IDS-01", "source_hashes": source_hashes},
        {"by_global_id": {}, "by_step_id": {}},
    )
    assert normalized["source_hashes"] == source_hashes

    mismatched_record = {
        **record,
        "normalized_predictions": [
            {
                **prediction,
                "source_hashes": {**source_hashes, "candidate": f"sha256:{'f' * 64}"},
            }
            for prediction in record["normalized_predictions"]
        ],
    }
    mismatched_metrics, _ = experiment.aggregate_metrics([mismatched_record])
    assert mismatched_metrics["traceability"]["all_issues"]["source_hash_coverage_count"] == 0

    fixed_330_record = {
        **record,
        "matches": {
            "A": _match(150, 0, 180),
            "B": _match(210, 0, 120),
            "C": _match(270, 0, 60),
            "D": _match(330, 0, 0),
        },
        "normalized_predictions": [],
    }
    fixed_metrics, _ = experiment.aggregate_metrics([fixed_330_record])
    assert set(fixed_metrics["incremental_recall"].values()) == {0.181818182}

    pre_fix_records = [
        {
            "case_id": "EVAL-1",
            "matches": {
                "A": _match(1, 0, 0),
                "B": _match(2, 0, 0),
                "C": _match(3, 0, 0),
                "D": {**_match(3, 1, 0), "false_positives": [{"rule_id": "GEO-01"}]},
            },
        },
        {
            "case_id": "EVAL-2",
            "matches": {
                "A": _match(1, 0, 0),
                "B": _match(2, 0, 0),
                "C": _match(2, 0, 0),
                "D": _match(2, 0, 0),
            },
        },
    ]
    affected = experiment.affected_case_ids_by_fix(pre_fix_records)
    assert affected["EVAL-GEO-PAIR-01"] == ["EVAL-1"]
    assert affected["EVAL-ABLATION-DENOM-01"] == ["EVAL-1", "EVAL-2"]


def test_engine_runtime_prefers_backend_engine_total() -> None:
    timings = {"ifc_open": 10.0, "rules": 20.0, "engine_total": 31.0}
    assert experiment.engine_runtime_ms(timings) == 31.0
    assert experiment.engine_runtime_ms({"a": 1.0, "b": 2.0}) == 3.0


def test_initial_evidence_captures_git_state_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    observed: list[bool] = []

    def capture(_args: Any, _manifest: dict[str, Any]) -> dict[str, Any]:
        observed.append(not (evidence_dir / "fixture_manifest.json").exists())
        return {"git": {"dirty": False}}

    monkeypatch.setattr(experiment, "capture_environment", capture)
    environment = experiment.write_initial_evidence(
        evidence_dir,
        args=object(),
        dataset_manifest={"dataset_id": "test"},
        fixture_manifest={"schema_version": "fixture-test"},
    )

    assert observed == [True]
    assert environment["git"]["dirty"] is False
    saved_environment = json.loads((evidence_dir / "environment.json").read_text(encoding="utf-8"))
    assert saved_environment == environment


def _match(tp: int, fp: int, fn: int, family: str = "Information") -> dict[str, Any]:
    return {
        **experiment.prf(tp, fp, fn),
        "matched": [{"family": family, "rule_id": "IDS-01"} for _ in range(tp)],
        "matched_admissible_secondary": [],
        "false_positives": [{"rule_id": "IDS-01"} for _ in range(fp)],
        "false_negatives": [{"family": family, "rule_id": "IDS-01"} for _ in range(fn)],
    }


def test_bootstrap_is_deterministic_and_includes_preregistered_intervals() -> None:
    records: list[dict[str, Any]] = []
    for layout in ("L1", "L2", "L3"):
        case_id = f"EVAL-{layout}-S1"
        records.append(
            {
                "case_id": case_id,
                "layout": layout,
                "candidate": "v1_faulty",
                "matches": {"A": _match(5, 0, 6), "D": _match(11, 0, 0)},
            }
        )
        records.append(
            {
                "case_id": case_id,
                "layout": layout,
                "candidate": "v2_corrected",
                "matches": {"D": _match(0, 0, 0)},
            }
        )

    first = experiment.bootstrap_summary(records, 200, seed=1234)
    second = experiment.bootstrap_summary(records, 200, seed=1234)

    assert first == second
    assert first["full_recall"]["ci95"] == [1.0, 1.0]
    assert first["full_minus_ids_recall"]["estimate"] > 0
    assert first["corrected_closure_rate"]["ci95"] == [1.0, 1.0]
    assert "Information" in first["family_f1"]


def test_reanalysis_requires_external_hash_and_current_fixture_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = generated_representative(tmp_path / "dataset")
    manifest = json.loads((output / "dataset_manifest.json").read_text(encoding="utf-8"))
    case = manifest["cases"][0]
    case_dir = output / case["path"]
    records: list[dict[str, Any]] = []
    for candidate in ("v0_clean", "v1_authorized", "v1_faulty", "v2_corrected"):
        empty_matches = {ablation: _match(0, 0, 0) for ablation in experiment.ABLATION_SCOPES}
        records.append(
            {
                "case_id": case["case_id"],
                "layout": case["layout"],
                "split": case["split"],
                "candidate": candidate,
                "baseline_hash": experiment.sha256_file(case_dir / "v0_clean.ifc"),
                "candidate_hash": experiment.sha256_file(case_dir / f"{candidate}.ifc"),
                "runs": [
                    {
                        "repeat": 1,
                        "wall_ms": 1.0,
                        "engine_ms": 0.5,
                        "canonical_hash": "sha256:" + ("0" * 64),
                        "report": {"status": "passed", "issues": []},
                    }
                ],
                "runtime": {"wall_median_ms": 1.0, "wall_p95_ms": 1.0},
                "determinism": {
                    "identical_runs": True,
                    "total_runs": 1,
                    "identical_count": 1,
                    "canonical_hashes": ["sha256:" + ("0" * 64)],
                },
                "normalized_predictions": [],
                "matches": empty_matches,
            }
        )
    source = tmp_path / "external-raw.jsonl"
    experiment.write_jsonl(source, records)
    source_hash = experiment.sha256_file(source)
    environment = {"git": {"commit": "analysis-commit", "dirty": False}}
    manifest_hash = experiment.sha256_file(output / "dataset_manifest.json")

    def fake_git_value(*args: str) -> str | None:
        if args == ("rev-list", "-n", "1", "analysis-test"):
            return "analysis-commit"
        if args == ("rev-parse", "protocol-v1^{commit}"):
            return experiment.FROZEN_ENGINE_COMMIT
        return None

    monkeypatch.setattr(experiment, "git_value", fake_git_value)

    analyzed, audit = experiment.reanalyze_engine_records(
        evidence_dir=tmp_path / "evidence",
        dataset_root=output,
        cases=[case],
        source_path=source,
        expected_source_hash=source_hash,
        analysis_environment=environment,
        expected_repeats=1,
        analysis_tag="analysis-test",
        expected_dataset_manifest_hash=manifest_hash,
    )

    assert len(analyzed) == 4
    assert audit["analysis_git"] == {
        "commit": "analysis-commit",
        "dirty": False,
        "tag": "analysis-test",
    }
    assert audit["detector_rerun"] is False
    assert audit["raw_engine_results"]["readback_verified"] is True
    assert (
        tmp_path / "evidence" / "raw_results_pre_analysis_fix.jsonl"
    ).read_bytes() == source.read_bytes()

    with pytest.raises(RuntimeError, match="source hash mismatch"):
        experiment.reanalyze_engine_records(
            evidence_dir=tmp_path / "bad-hash-evidence",
            dataset_root=output,
            cases=[case],
            source_path=source,
            expected_source_hash="sha256:" + ("f" * 64),
            analysis_environment=environment,
            expected_repeats=1,
            analysis_tag="analysis-test",
            expected_dataset_manifest_hash=manifest_hash,
        )

    tampered = [dict(record) for record in records]
    tampered[0]["candidate_hash"] = "sha256:" + ("f" * 64)
    tampered_source = tmp_path / "tampered-raw.jsonl"
    experiment.write_jsonl(tampered_source, tampered)
    with pytest.raises(RuntimeError, match="Candidate hash mismatch"):
        experiment.reanalyze_engine_records(
            evidence_dir=tmp_path / "tampered-evidence",
            dataset_root=output,
            cases=[case],
            source_path=tampered_source,
            expected_source_hash=experiment.sha256_file(tampered_source),
            analysis_environment=environment,
            expected_repeats=1,
            analysis_tag="analysis-test",
            expected_dataset_manifest_hash=manifest_hash,
        )

    nondeterministic = [dict(record) for record in records]
    nondeterministic[0]["determinism"] = {
        "identical_runs": False,
        "total_runs": 1,
        "identical_count": 0,
    }
    nondeterministic_source = tmp_path / "nondeterministic-raw.jsonl"
    experiment.write_jsonl(nondeterministic_source, nondeterministic)
    with pytest.raises(RuntimeError, match="not deterministic"):
        experiment.reanalyze_engine_records(
            evidence_dir=tmp_path / "nondeterministic-evidence",
            dataset_root=output,
            cases=[case],
            source_path=nondeterministic_source,
            expected_source_hash=experiment.sha256_file(nondeterministic_source),
            analysis_environment=environment,
            expected_repeats=1,
            analysis_tag="analysis-test",
            expected_dataset_manifest_hash=manifest_hash,
        )

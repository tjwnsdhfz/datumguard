from __future__ import annotations

import importlib.util
import json
import sys
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


def generated_representative(tmp_path: Path) -> Path:
    output = tmp_path / "openbim"
    generator.generate_dataset(output, split="representative", evaluation_per_layout=4)
    return output


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
                "matches": {"A": _match(5, 0, 0), "D": _match(11, 0, 0)},
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
    assert first["corrected_closure_rate"]["ci95"] == [1.0, 1.0]
    assert "Information" in first["family_f1"]

"""Run the preregistered OpenBIM experiment and emit machine-generated evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import ifcopenshell

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "fixtures" / "openbim"
DEFAULT_EVIDENCE = ROOT / "docs" / "awards-2026" / "evidence"
DEFAULT_RESULTS = ROOT / "docs" / "awards-2026" / "RESULTS.md"
PROTOCOL_PATH = ROOT / "docs" / "awards-2026" / "protocol.yaml"
SCOPE_BY_RULE_PREFIX = {
    "IDS": "IDS_REQUIREMENT",
    "IFC": "IFC_SCHEMA",
    "GEO": "PROJECT_GEOMETRY_RULE",
    "REV": "PROJECT_REVISION_RULE",
}
ABLATION_SCOPES = {
    "A": {"IDS_REQUIREMENT"},
    "B": {"IDS_REQUIREMENT", "IFC_SCHEMA"},
    "C": {"IDS_REQUIREMENT", "IFC_SCHEMA", "PROJECT_GEOMETRY_RULE"},
    "D": {
        "IDS_REQUIREMENT",
        "IFC_SCHEMA",
        "PROJECT_GEOMETRY_RULE",
        "PROJECT_REVISION_RULE",
    },
}
CANONICAL_FIELD_BY_RULE = {
    "IDS-01": "DG_Identity.AssetTag",
    "IDS-02": "DG_VFabUtility.UtilityType",
    "IDS-03": "DG_VFabUtility.SystemCode",
    "IDS-04": "classification",
    "IDS-05": "DG_VFabUtility.Criticality",
    "IDS-06": "DG_VFabClearance",
    "IFC-01": "model",
    "IFC-02": "GlobalId",
    "IFC-03": "container",
    "REV-01": "DG_Identity.AssetKey",
    "REV-02": "GlobalId",
}
FAMILY_BY_RULE = {
    "IDS-01": "Information",
    "IDS-02": "Information",
    "IDS-03": "Information",
    "IDS-04": "Information",
    "IDS-05": "Information",
    "IDS-06": "Information",
    "IFC-01": "Integrity",
    "IFC-02": "IFC Identity",
    "IFC-03": "Integrity",
    "REV-01": "Revision",
    "REV-02": "Revision",
    "REV-03": "Revision",
    "GEO-01": "Geometry",
}
PRIMARY_RULE_IDS = set(FAMILY_BY_RULE)


def canonical_json(data: Any) -> bytes:
    return (
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def compact_json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def pretty_json(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty_json(data))


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def engine_runtime_ms(timings: Mapping[str, Any]) -> float:
    for key in ("total", "total_ms", "engine_total"):
        value = timings.get(key)
        if value is not None:
            return float(value)
    return sum(float(value) for value in timings.values())


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def prf(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = safe_ratio(tp, tp + fp)
    recall = safe_ratio(tp, tp + fn)
    f1 = safe_ratio(2 * precision * recall, precision + recall)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 9),
        "recall": round(recall, 9),
        "f1": round(f1, 9),
    }


def git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def distribution_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def capture_environment(
    args: argparse.Namespace, dataset_manifest: dict[str, Any]
) -> dict[str, Any]:
    status = git_value("status", "--porcelain")
    return {
        "schema_version": "openbim-experiment-environment-v1",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "command": [sys.executable, *sys.argv],
        "cwd": str(ROOT),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "os": {"name": os.name, "release": platform.release(), "version": platform.version()},
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "packages": {
            name: distribution_version(name)
            for name in ("datumguard", "ifcopenshell", "ifctester", "bcf-client", "pydantic")
        },
        "git": {
            "commit": git_value("rev-parse", "HEAD"),
            "branch": git_value("branch", "--show-current"),
            "dirty": bool(status),
            "status_sha256": sha256_bytes((status or "").encode("utf-8")),
        },
        "protocol": {
            "path": str(PROTOCOL_PATH.relative_to(ROOT)),
            "sha256": sha256_file(PROTOCOL_PATH),
        },
        "dataset_manifest_sha256": sha256_bytes(pretty_json(dataset_manifest)),
        "arguments": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
    }


def write_initial_evidence(
    evidence_dir: Path,
    *,
    args: argparse.Namespace,
    dataset_manifest: dict[str, Any],
    fixture_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Record the pre-run Git state before this run writes its own evidence files."""

    environment = capture_environment(args, dataset_manifest)
    write_json(evidence_dir / "fixture_manifest.json", fixture_manifest)
    write_json(evidence_dir / "environment.json", environment)
    return environment


def load_dataset_manifest(dataset_root: Path) -> dict[str, Any]:
    path = dataset_root / "dataset_manifest.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Dataset manifest not found: {path}. Run generate_virtual_fab_fixtures.py first."
        )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "openbim-dataset-manifest-v1":
        raise ValueError("Unsupported dataset manifest schema")
    return manifest


def select_cases(manifest: dict[str, Any], split: str, limit: int | None) -> list[dict[str, Any]]:
    cases = [case for case in manifest["cases"] if split == "all" or case.get("split") == split]
    cases.sort(key=lambda case: case["case_id"])
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        raise ValueError(f"No {split!r} cases are present in the dataset manifest")
    return cases


def pset_asset_key(entity: Any) -> str | None:
    for relation in getattr(entity, "IsDefinedBy", ()):
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        pset = relation.RelatingPropertyDefinition
        if not pset.is_a("IfcPropertySet") or pset.Name != "DG_Identity":
            continue
        for prop in pset.HasProperties:
            if prop.Name == "AssetKey" and prop.NominalValue is not None:
                return str(prop.NominalValue.wrappedValue)
    return None


def candidate_indexes(path: Path) -> dict[str, dict[Any, str]]:
    model = ifcopenshell.open(str(path))
    by_global_id: dict[str, str] = {}
    ambiguous_global_ids: set[str] = set()
    by_step_id: dict[int, str] = {}
    for ifc_class in (
        "IfcBuildingElementProxy",
        "IfcPipeSegment",
        "IfcPipeFitting",
        "IfcValve",
    ):
        for entity in model.by_type(ifc_class, include_subtypes=False):
            asset_key = pset_asset_key(entity)
            if asset_key is None:
                continue
            by_step_id[entity.id()] = asset_key
            global_id = str(entity.GlobalId or "")
            if global_id in by_global_id and by_global_id[global_id] != asset_key:
                ambiguous_global_ids.add(global_id)
            else:
                by_global_id[global_id] = asset_key
    for global_id in ambiguous_global_ids:
        by_global_id.pop(global_id, None)
    return {"by_global_id": by_global_id, "by_step_id": by_step_id}


def report_dict(report: Any) -> dict[str, Any]:
    if hasattr(report, "model_dump"):
        value = report.model_dump(mode="json")
    elif isinstance(report, Mapping):
        value = dict(report)
    else:
        raise TypeError(f"Unsupported OpenBIM report type: {type(report).__name__}")
    if not isinstance(value, dict):
        raise TypeError("OpenBIM report did not serialize to an object")
    return value


def invoke_engine(
    baseline: bytes,
    candidate: bytes,
    requirements: bytes,
    profile: dict[str, Any] | str,
) -> dict[str, Any]:
    from datumguard.openbim_service import run_openbim_evidence

    report = run_openbim_evidence(
        baseline_bytes=baseline,
        candidate_bytes=candidate,
        requirements_bytes=requirements,
        profile=profile,
        include_html=False,
        include_bcf=False,
    )
    return report_dict(report)


def trimmed_report(report: dict[str, Any]) -> dict[str, Any]:
    result = dict(report)
    result["reports"] = [
        {key: value for key, value in artifact.items() if key != "content_base64"}
        for artifact in report.get("reports", [])
        if isinstance(artifact, dict)
    ]
    return result


def canonical_report_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in {"timings_ms", "reports", "run_id", "timestamp", "generated_at"}
    }


def scope_for_rule(rule_id: str) -> str:
    prefix = rule_id.split("-", 1)[0]
    return SCOPE_BY_RULE_PREFIX.get(prefix, "UNKNOWN")


def canonical_field(rule_id: str, field: Any) -> str:
    if rule_id == "REV-03" and field:
        return str(field)
    return CANONICAL_FIELD_BY_RULE.get(rule_id, str(field or ""))


def normalized_prediction(
    issue: Mapping[str, Any], indexes: dict[str, dict[Any, str]]
) -> dict[str, Any]:
    rule_id = str(issue.get("rule_id") or "")
    entity_ids = [str(value) for value in issue.get("entity_ids") or []]
    step_ids = [int(value) for value in issue.get("step_ids") or []]
    asset_keys = {
        indexes["by_global_id"][entity_id]
        for entity_id in entity_ids
        if entity_id in indexes["by_global_id"]
    }
    asset_keys.update(
        indexes["by_step_id"][step_id] for step_id in step_ids if step_id in indexes["by_step_id"]
    )
    raw = issue.get("raw")
    if isinstance(raw, Mapping) and raw.get("asset_key"):
        asset_keys.add(str(raw["asset_key"]))

    raw_pair = [str(value) for value in issue.get("entity_pair") or []]
    pair = sorted(indexes["by_global_id"].get(value, value) for value in raw_pair)
    return {
        "rule_id": rule_id,
        "scope": str(issue.get("scope") or scope_for_rule(rule_id)),
        "severity": str(issue.get("severity") or "error"),
        "asset_keys": sorted(asset_keys),
        "entity_pair": pair,
        "step_ids": sorted(step_ids),
        "field": canonical_field(rule_id, issue.get("field")),
        "issue_key": str(issue.get("issue_key") or ""),
    }


def normalized_truth(issue: Mapping[str, Any]) -> dict[str, Any]:
    asset_keys = set(str(value) for value in issue.get("asset_keys") or [])
    if issue.get("asset_key"):
        asset_keys.add(str(issue["asset_key"]))
    return {
        "fault_id": str(issue.get("fault_id") or ""),
        "rule_id": str(issue["rule_id"]),
        "family": str(issue.get("family") or FAMILY_BY_RULE.get(str(issue["rule_id"]), "Other")),
        "asset_keys": sorted(asset_keys),
        "entity_pair": sorted(str(value) for value in issue.get("entity_pair") or []),
        "step_ids": sorted(int(value) for value in issue.get("step_entity_ids") or []),
        "field": canonical_field(str(issue["rule_id"]), issue.get("field")),
    }


def alert_key(alert: Mapping[str, Any]) -> tuple[Any, ...]:
    rule_id = str(alert["rule_id"])
    if rule_id == "GEO-01":
        return (rule_id, tuple(alert.get("entity_pair") or []))
    if rule_id == "IFC-02" and alert.get("step_ids"):
        return (rule_id, tuple(alert["step_ids"]))
    asset_keys = list(alert.get("asset_keys") or [])
    asset_key = asset_keys[-1] if asset_keys else ""
    return (rule_id, asset_key, str(alert.get("field") or ""))


def deduplicate_predictions(predictions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    for prediction in predictions:
        key = alert_key(prediction)
        current = result.get(key)
        if current is None or prediction["issue_key"] < current["issue_key"]:
            result[key] = prediction
    return [result[key] for key in sorted(result, key=repr)]


def match_alerts(
    expected: list[dict[str, Any]],
    admissible_secondary: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    secondary_by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in expected:
        expected_by_key[alert_key(item)].append(item)
    for item in admissible_secondary:
        secondary_by_key[alert_key(item)].append(item)

    matched_expected: list[dict[str, Any]] = []
    matched_secondary: list[dict[str, Any]] = []
    false_positives: list[dict[str, Any]] = []
    for item in predicted:
        key = alert_key(item)
        if expected_by_key.get(key):
            matched_expected.append(expected_by_key[key].pop(0))
        elif secondary_by_key.get(key):
            matched_secondary.append(secondary_by_key[key].pop(0))
        else:
            false_positives.append(item)
    false_negatives = [item for items in expected_by_key.values() for item in items]
    return {
        **prf(len(matched_expected), len(false_positives), len(false_negatives)),
        "matched": matched_expected,
        "matched_admissible_secondary": matched_secondary,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }


def scoped(alerts: list[dict[str, Any]], ablation: str) -> list[dict[str, Any]]:
    scopes = ABLATION_SCOPES[ablation]
    return [alert for alert in alerts if scope_for_rule(alert["rule_id"]) in scopes]


def run_candidate(
    *,
    case: dict[str, Any],
    case_dir: Path,
    candidate_name: str,
    requirements: bytes,
    profile: dict[str, Any] | str,
    expected_profile_hash: str,
    warmup_runs: int,
    repeats: int,
) -> dict[str, Any]:
    baseline_path = case_dir / "v0_clean.ifc"
    candidate_path = case_dir / f"{candidate_name}.ifc"
    baseline = baseline_path.read_bytes()
    candidate = candidate_path.read_bytes()
    for _ in range(warmup_runs):
        invoke_engine(baseline, candidate, requirements, profile)

    reports: list[dict[str, Any]] = []
    wall_times: list[float] = []
    engine_times: list[float] = []
    canonical_hashes: list[str] = []
    for repeat in range(1, repeats + 1):
        started = time.perf_counter()
        report = invoke_engine(baseline, candidate, requirements, profile)
        expected_hashes = {
            "baseline_hash": sha256_bytes(baseline),
            "candidate_hash": sha256_bytes(candidate),
            "ids_hash": sha256_bytes(requirements),
            "profile_hash": expected_profile_hash,
        }
        mismatched_hashes = {
            key: {"expected": expected, "actual": report.get(key)}
            for key, expected in expected_hashes.items()
            if report.get(key) != expected
        }
        if mismatched_hashes:
            raise RuntimeError(f"Engine source hash mismatch: {mismatched_hashes}")
        wall_ms = (time.perf_counter() - started) * 1000.0
        timings = report.get("timings_ms") or {}
        engine_ms = engine_runtime_ms(timings)
        wall_times.append(wall_ms)
        engine_times.append(engine_ms)
        canonical_hash = sha256_bytes(canonical_json(canonical_report_payload(report)))
        canonical_hashes.append(canonical_hash)
        reports.append(
            {
                "repeat": repeat,
                "wall_ms": round(wall_ms, 6),
                "engine_ms": round(engine_ms, 6),
                "canonical_hash": canonical_hash,
                "report": trimmed_report(report),
            }
        )
    return {
        "case_id": case["case_id"],
        "layout": case["layout"],
        "split": case["split"],
        "candidate": candidate_name,
        "baseline_hash": sha256_bytes(baseline),
        "candidate_hash": sha256_bytes(candidate),
        "runs": reports,
        "runtime": {
            "wall_median_ms": round(statistics.median(wall_times), 6),
            "wall_iqr_ms": round(percentile(wall_times, 0.75) - percentile(wall_times, 0.25), 6),
            "wall_p95_ms": round(percentile(wall_times, 0.95), 6),
            "engine_median_ms": round(statistics.median(engine_times), 6),
            "engine_p95_ms": round(percentile(engine_times, 0.95), 6),
        },
        "determinism": {
            "identical_runs": len(set(canonical_hashes)) == 1,
            "identical_count": max(
                canonical_hashes.count(value) for value in set(canonical_hashes)
            ),
            "total_runs": repeats,
            "canonical_hashes": canonical_hashes,
        },
    }


def evaluate_candidate(
    raw: dict[str, Any], truth: dict[str, Any], candidate_path: Path
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    indexes = candidate_indexes(candidate_path)
    report = raw["runs"][0]["report"]
    predictions = deduplicate_predictions(
        normalized_prediction(issue, indexes)
        for issue in report.get("issues", [])
        if str(issue.get("severity") or "error") in {"error", "warning"}
    )
    primary_predictions = [
        prediction for prediction in predictions if prediction["rule_id"] in PRIMARY_RULE_IDS
    ]
    candidate_truth = truth["candidates"][raw["candidate"]]
    expected = [normalized_truth(item) for item in candidate_truth.get("expected_issues", [])]
    secondary = [
        normalized_truth(item) for item in candidate_truth.get("admissible_secondary_issues", [])
    ]
    matches = {
        ablation: match_alerts(
            scoped(expected, ablation),
            scoped(secondary, ablation),
            scoped(primary_predictions, ablation),
        )
        for ablation in ABLATION_SCOPES
    }
    return predictions, matches


def raw_error_record(case: dict[str, Any], candidate: str, exc: Exception) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "layout": case["layout"],
        "split": case["split"],
        "candidate": candidate,
        "error": {"type": type(exc).__name__, "message": str(exc)[:1000]},
        "runs": [],
    }


def per_case_rows(raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in raw_records:
        if record.get("error"):
            for ablation in ABLATION_SCOPES:
                rows.append(
                    {
                        "case_id": record["case_id"],
                        "layout": record["layout"],
                        "split": record["split"],
                        "candidate": record["candidate"],
                        "ablation": ablation,
                        "status": "engine_error",
                        "tp": 0,
                        "fp": 0,
                        "fn": "",
                        "precision": "",
                        "recall": "",
                        "f1": "",
                        "admissible_secondary": 0,
                        "wall_median_ms": "",
                        "wall_p95_ms": "",
                        "deterministic": False,
                    }
                )
            continue
        for ablation, match in record["matches"].items():
            rows.append(
                {
                    "case_id": record["case_id"],
                    "layout": record["layout"],
                    "split": record["split"],
                    "candidate": record["candidate"],
                    "ablation": ablation,
                    "status": record["runs"][0]["report"].get("status"),
                    "tp": match["tp"],
                    "fp": match["fp"],
                    "fn": match["fn"],
                    "precision": match["precision"],
                    "recall": match["recall"],
                    "f1": match["f1"],
                    "admissible_secondary": len(match["matched_admissible_secondary"]),
                    "wall_median_ms": record["runtime"]["wall_median_ms"],
                    "wall_p95_ms": record["runtime"]["wall_p95_ms"],
                    "deterministic": record["determinism"]["identical_runs"],
                }
            )
    return rows


def aggregate_metrics(
    raw_records: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    successful = [record for record in raw_records if not record.get("error")]
    aggregate: dict[str, Any] = {"ablations": {}, "controls": {}, "families": {}}
    metric_rows: list[dict[str, Any]] = []
    for ablation in ABLATION_SCOPES:
        matches = [record["matches"][ablation] for record in successful]
        scores = prf(
            sum(int(match["tp"]) for match in matches),
            sum(int(match["fp"]) for match in matches),
            sum(int(match["fn"]) for match in matches),
        )
        scores["admissible_secondary"] = sum(
            len(match["matched_admissible_secondary"]) for match in matches
        )
        aggregate["ablations"][ablation] = scores
        metric_rows.append({"metric_group": "ablation", "key": ablation, **scores})

    full_matches = [record["matches"]["D"] for record in successful]
    families = sorted(
        {
            item["family"]
            for match in full_matches
            for item in match["matched"] + match["false_negatives"]
        }
        | set(FAMILY_BY_RULE.values())
    )
    family_f1_values: list[float] = []
    for family in families:
        tp = sum(item["family"] == family for match in full_matches for item in match["matched"])
        fn = sum(
            item["family"] == family for match in full_matches for item in match["false_negatives"]
        )
        fp = sum(
            FAMILY_BY_RULE.get(item["rule_id"], "Other") == family
            for match in full_matches
            for item in match["false_positives"]
        )
        scores = prf(tp, fp, fn)
        if tp + fn:
            family_f1_values.append(float(scores["f1"]))
        aggregate["families"][family] = scores
        metric_rows.append({"metric_group": "family", "key": family, **scores})
    aggregate["family_macro_f1"] = (
        round(statistics.mean(family_f1_values), 9) if family_f1_values else 0.0
    )

    def false_positives_for(candidate: str) -> int:
        return sum(
            int(record["matches"]["D"]["fp"])
            for record in successful
            if record["candidate"] == candidate
        )

    faulty = [record for record in successful if record["candidate"] == "v1_faulty"]
    corrected = [record for record in successful if record["candidate"] == "v2_corrected"]
    faulty_detected = sum(int(record["matches"]["D"]["tp"]) for record in faulty)
    corrected_remaining = sum(int(record["matches"]["D"]["fp"]) for record in corrected)
    closure_rate = safe_ratio(max(0, faulty_detected - corrected_remaining), faulty_detected)
    controls = {
        "clean_false_positives": false_positives_for("v0_clean"),
        "authorized_false_positives": false_positives_for("v1_authorized"),
        "corrected_new_issues": corrected_remaining,
        "corrected_issue_closure_rate": round(closure_rate, 9),
        "deterministic_candidate_runs": sum(
            bool(record["determinism"]["identical_runs"]) for record in successful
        ),
        "candidate_runs": len(successful),
        "engine_errors": len(raw_records) - len(successful),
        "low_level_diagnostic_alerts": sum(
            prediction["rule_id"] not in PRIMARY_RULE_IDS
            for record in successful
            for prediction in record["normalized_predictions"]
        ),
    }
    aggregate["controls"] = controls
    for key, value in controls.items():
        metric_rows.append({"metric_group": "control", "key": key, "value": value})
    wall_times = [float(run["wall_ms"]) for record in successful for run in record["runs"]]
    engine_times = [float(run["engine_ms"]) for record in successful for run in record["runs"]]
    aggregate["runtime"] = {
        "wall_median_ms": round(statistics.median(wall_times), 6) if wall_times else 0.0,
        "wall_iqr_ms": round(percentile(wall_times, 0.75) - percentile(wall_times, 0.25), 6),
        "wall_p95_ms": round(percentile(wall_times, 0.95), 6),
        "engine_median_ms": round(statistics.median(engine_times), 6) if engine_times else 0.0,
        "engine_iqr_ms": round(percentile(engine_times, 0.75) - percentile(engine_times, 0.25), 6),
        "engine_p95_ms": round(percentile(engine_times, 0.95), 6),
        "measured_run_count": len(engine_times),
    }
    return aggregate, metric_rows


def bootstrap_summary(
    raw_records: list[dict[str, Any]], iterations: int, seed: int = 20260820
) -> dict[str, Any]:
    by_case: dict[str, dict[str, Any]] = {}
    for record in raw_records:
        if record.get("error") or record["candidate"] not in {"v1_faulty", "v2_corrected"}:
            continue
        entry = by_case.setdefault(
            record["case_id"], {"case_id": record["case_id"], "layout": record["layout"]}
        )
        entry[record["candidate"]] = record
    complete_cases = [
        entry for entry in by_case.values() if "v1_faulty" in entry and "v2_corrected" in entry
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in complete_cases:
        grouped[entry["layout"]].append(entry)
    if not complete_cases:
        return {"iterations": 0, "reason": "No complete faulty/corrected case pairs"}
    rng = random.Random(seed)
    deltas: list[float] = []
    full_recalls: list[float] = []
    closure_rates: list[float] = []
    families = sorted(set(FAMILY_BY_RULE.values()))
    family_f1: dict[str, list[float]] = {family: [] for family in families}
    for _ in range(iterations):
        sample: list[dict[str, Any]] = []
        for layout in sorted(grouped):
            values = grouped[layout]
            sample.extend(values[rng.randrange(len(values))] for _ in values)
        recalls: dict[str, float] = {}
        for ablation in ("A", "D"):
            tp = sum(int(entry["v1_faulty"]["matches"][ablation]["tp"]) for entry in sample)
            fn = sum(int(entry["v1_faulty"]["matches"][ablation]["fn"]) for entry in sample)
            recalls[ablation] = safe_ratio(tp, tp + fn)
        deltas.append(recalls["D"] - recalls["A"])
        full_recalls.append(recalls["D"])
        faulty_detected = sum(int(entry["v1_faulty"]["matches"]["D"]["tp"]) for entry in sample)
        corrected_remaining = sum(
            int(entry["v2_corrected"]["matches"]["D"]["fp"]) for entry in sample
        )
        closure_rates.append(
            safe_ratio(max(0, faulty_detected - corrected_remaining), faulty_detected)
        )
        for family in families:
            matches = [entry["v1_faulty"]["matches"]["D"] for entry in sample]
            tp = sum(item["family"] == family for match in matches for item in match["matched"])
            fn = sum(
                item["family"] == family for match in matches for item in match["false_negatives"]
            )
            fp = sum(
                FAMILY_BY_RULE.get(item["rule_id"], "Other") == family
                for match in matches
                for item in match["false_positives"]
            )
            family_f1[family].append(float(prf(tp, fp, fn)["f1"]))
    return {
        "schema_version": "openbim-bootstrap-v1",
        "iterations": iterations,
        "seed": seed,
        "stratification": "layout-preserving paired bootstrap",
        "case_count": len(complete_cases),
        "full_recall": {
            "estimate": round(statistics.mean(full_recalls), 9),
            "ci95": [
                round(percentile(full_recalls, 0.025), 9),
                round(percentile(full_recalls, 0.975), 9),
            ],
        },
        "full_minus_ids_recall": {
            "estimate": round(statistics.mean(deltas), 9),
            "ci95": [round(percentile(deltas, 0.025), 9), round(percentile(deltas, 0.975), 9)],
        },
        "family_f1": {
            family: {
                "estimate": round(statistics.mean(values), 9),
                "ci95": [
                    round(percentile(values, 0.025), 9),
                    round(percentile(values, 0.975), 9),
                ],
            }
            for family, values in family_f1.items()
        },
        "corrected_closure_rate": {
            "estimate": round(statistics.mean(closure_rates), 9),
            "ci95": [
                round(percentile(closure_rates, 0.025), 9),
                round(percentile(closure_rates, 0.975), 9),
            ],
        },
    }


def panel_facts(
    manifest: dict[str, Any], raw_records: list[dict[str, Any]], metrics: dict[str, Any]
) -> dict[str, Any]:
    successful = [record for record in raw_records if not record.get("error")]
    actual_cases = sorted({record["case_id"] for record in successful})
    return {
        "schema_version": "openbim-panel-facts-v1",
        "machine_generated": True,
        "claim_status": "actual experiment output" if successful else "no completed experiment",
        "dataset_id": manifest["dataset_id"],
        "completed_case_count": len(actual_cases),
        "completed_candidate_runs": len(successful),
        "injected_primary_faults_evaluated": sum(
            11
            for case_id in actual_cases
            if any(record["case_id"] == case_id for record in successful)
        ),
        "full_pipeline": metrics.get("ablations", {}).get("D", {}),
        "family_macro_f1": metrics.get("family_macro_f1"),
        "controls": metrics.get("controls", {}),
        "runtime": metrics.get("runtime", {}),
        "assurance_boundary": (
            "Synthetic research validation only; not structural, safety, code, fabrication, "
            "or construction approval."
        ),
    }


def write_results_markdown(
    path: Path,
    *,
    summary: dict[str, Any],
    metrics: dict[str, Any],
    bootstrap: dict[str, Any],
) -> None:
    full = metrics.get("ablations", {}).get("D", {})
    controls = metrics.get("controls", {})
    runtime = metrics.get("runtime", {})
    lines = [
        "# OpenBIM Evidence Guard 실험 결과",
        "",
        "> 이 문서는 실험 러너가 원자료에서 자동 생성했다. 수동 편집하지 않는다.",
        "",
        f"- 실행 상태: `{summary['status']}`",
        f"- protocol SHA-256: `{summary['protocol_hash']}`",
        f"- dataset manifest SHA-256: `{summary['dataset_manifest_hash']}`",
        f"- 완료 candidate run: {summary['completed_candidate_runs']}",
        f"- engine error: {summary['engine_errors']}",
        "",
        "## Full pipeline (Ablation D)",
        "",
        f"- TP/FP/FN: {full.get('tp', 0)}/{full.get('fp', 0)}/{full.get('fn', 0)}",
        f"- Precision: {full.get('precision', 0):.6f}",
        f"- Recall: {full.get('recall', 0):.6f}",
        f"- F1: {full.get('f1', 0):.6f}",
        f"- Family macro-F1: {metrics.get('family_macro_f1', 0):.6f}",
        "",
        "## Controls and reproducibility",
        "",
        f"- Clean false positives: {controls.get('clean_false_positives', 0)}",
        f"- Authorized false positives: {controls.get('authorized_false_positives', 0)}",
        f"- Corrected new issues: {controls.get('corrected_new_issues', 0)}",
        f"- Corrected closure rate: {controls.get('corrected_issue_closure_rate', 0):.6f}",
        (
            "- Deterministic candidate runs: "
            f"{controls.get('deterministic_candidate_runs', 0)}/{controls.get('candidate_runs', 0)}"
        ),
        f"- Median engine runtime: {runtime.get('engine_median_ms', 0):.3f} ms",
        f"- p95 engine runtime: {runtime.get('engine_p95_ms', 0):.3f} ms",
        f"- p95 wall runtime: {runtime.get('wall_p95_ms', 0):.3f} ms",
        "",
        "## Bootstrap",
        "",
        f"- Iterations: {bootstrap.get('iterations', 0)}",
        f"- Full recall 95% interval: {bootstrap.get('full_recall', {}).get('ci95', 'N/A')}",
        (
            "- Full minus IDS-only recall 95% interval: "
            f"{bootstrap.get('full_minus_ids_recall', {}).get('ci95', 'N/A')}"
        ),
        "",
        "상세 실패와 모든 반복 결과는 `evidence/raw_results.jsonl`을 기준으로 한다. "
        "합성 IFC 결과를",
        "실제 FAB 적합성·안전·법규·시공 승인으로 일반화하지 않는다.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument(
        "--split", choices=("representative", "pilot", "evaluation", "all"), default="evaluation"
    )
    parser.add_argument("--case-limit", type=int)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--bootstrap-iterations", type=int, default=10_000)
    parser.add_argument("--registered-profile", action="store_true")
    parser.add_argument(
        "--regenerate-dataset",
        action="store_true",
        help="Regenerate all 37 cases and verify byte determinism before the experiment.",
    )
    parser.add_argument("--allow-engine-errors", action="store_true")
    parser.add_argument("--results-path", type=Path, default=DEFAULT_RESULTS)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.repeats < 1:
        raise ValueError("--repeats must be at least 1")
    if args.warmup_runs < 0:
        raise ValueError("--warmup-runs cannot be negative")
    if args.bootstrap_iterations < 1:
        raise ValueError("--bootstrap-iterations must be at least 1")
    if args.case_limit is not None and args.case_limit < 1:
        raise ValueError("--case-limit must be at least 1")


def main() -> int:
    args = parse_args()
    validate_args(args)
    dataset_root = args.dataset_root.resolve()
    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if args.regenerate_dataset:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "generate_virtual_fab_fixtures.py"),
                "--output-root",
                str(dataset_root),
                "--split",
                "all",
                "--evaluation-per-layout",
                "10",
                "--verify-determinism",
            ],
            cwd=ROOT,
            check=True,
        )
    manifest = load_dataset_manifest(dataset_root)
    cases = select_cases(manifest, args.split, args.case_limit)
    requirements_path = dataset_root / manifest["ids"]["path"]
    profile_path = dataset_root / manifest["profile"]["path"]
    requirements = requirements_path.read_bytes()
    profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
    profile: dict[str, Any] | str
    profile = "virtual-fab-v1" if args.registered_profile else profile_data
    expected_profile_hash = sha256_bytes(compact_json(profile_data))

    fixture_manifest = {
        **manifest,
        "dataset_manifest_sha256": sha256_file(dataset_root / "dataset_manifest.json"),
        "verified_at_experiment_start": {
            "ids": sha256_file(requirements_path),
            "profile": sha256_file(profile_path),
            "profile_canonical_json": expected_profile_hash,
        },
    }
    if fixture_manifest["verified_at_experiment_start"]["ids"] != manifest["ids"]["sha256"]:
        raise RuntimeError("IDS hash does not match dataset manifest")
    if fixture_manifest["verified_at_experiment_start"]["profile"] != manifest["profile"]["sha256"]:
        raise RuntimeError("Profile hash does not match dataset manifest")
    if expected_profile_hash != manifest["profile"].get("canonical_json_sha256"):
        raise RuntimeError("Canonical profile hash does not match dataset manifest")
    write_initial_evidence(
        evidence_dir,
        args=args,
        dataset_manifest=manifest,
        fixture_manifest=fixture_manifest,
    )

    raw_records: list[dict[str, Any]] = []
    variants = ("v0_clean", "v1_authorized", "v1_faulty", "v2_corrected")
    for case in cases:
        case_dir = dataset_root / case["path"]
        truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))
        for candidate_name in variants:
            try:
                record = run_candidate(
                    case=case,
                    case_dir=case_dir,
                    candidate_name=candidate_name,
                    requirements=requirements,
                    profile=profile,
                    expected_profile_hash=expected_profile_hash,
                    warmup_runs=args.warmup_runs,
                    repeats=args.repeats,
                )
                predictions, matches = evaluate_candidate(
                    record, truth, case_dir / f"{candidate_name}.ifc"
                )
                record["normalized_predictions"] = predictions
                record["matches"] = matches
            except Exception as exc:
                record = raw_error_record(case, candidate_name, exc)
            raw_records.append(record)
            print(
                f"[{len(raw_records)}/{len(cases) * len(variants)}] "
                f"{case['case_id']} {candidate_name} "
                f"{'ERROR' if record.get('error') else 'ok'}",
                flush=True,
            )

    raw_path = evidence_dir / "raw_results.jsonl"
    with raw_path.open("wb") as stream:
        for record in raw_records:
            stream.write(canonical_json(record))

    rows = per_case_rows(raw_records)
    write_csv(
        evidence_dir / "per_case.csv",
        rows,
        (
            "case_id",
            "layout",
            "split",
            "candidate",
            "ablation",
            "status",
            "tp",
            "fp",
            "fn",
            "precision",
            "recall",
            "f1",
            "admissible_secondary",
            "wall_median_ms",
            "wall_p95_ms",
            "deterministic",
        ),
    )
    metrics, metric_rows = aggregate_metrics(raw_records)
    write_csv(
        evidence_dir / "metrics.csv",
        metric_rows,
        (
            "metric_group",
            "key",
            "tp",
            "fp",
            "fn",
            "precision",
            "recall",
            "f1",
            "value",
            "admissible_secondary",
        ),
    )
    bootstrap = bootstrap_summary(raw_records, args.bootstrap_iterations)
    write_json(evidence_dir / "bootstrap_summary.json", bootstrap)
    errors = sum(bool(record.get("error")) for record in raw_records)
    summary = {
        "schema_version": "openbim-experiment-summary-v1",
        "status": "completed" if errors == 0 else "completed_with_engine_errors",
        "research_validation_only": True,
        "split": args.split,
        "case_count": len(cases),
        "completed_candidate_runs": len(raw_records) - errors,
        "engine_errors": errors,
        "protocol_hash": sha256_file(PROTOCOL_PATH),
        "dataset_manifest_hash": sha256_file(dataset_root / "dataset_manifest.json"),
        "raw_results_hash": sha256_file(raw_path),
        "metrics": metrics,
    }
    write_json(evidence_dir / "experiment_summary.json", summary)
    write_json(evidence_dir / "panel_facts.json", panel_facts(manifest, raw_records, metrics))
    reproduction_lines = [
        f"command={subprocess.list2cmdline([sys.executable, *sys.argv])}",
        f"status={summary['status']}",
        f"protocol_hash={summary['protocol_hash']}",
        f"dataset_manifest_hash={summary['dataset_manifest_hash']}",
        f"raw_results_hash={summary['raw_results_hash']}",
        f"completed_candidate_runs={summary['completed_candidate_runs']}",
        f"engine_errors={errors}",
    ]
    (evidence_dir / "reproduction.log").write_text(
        "\n".join(reproduction_lines) + "\n", encoding="utf-8"
    )
    write_results_markdown(
        args.results_path.resolve(), summary=summary, metrics=metrics, bootstrap=bootstrap
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if errors == 0 or args.allow_engine_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

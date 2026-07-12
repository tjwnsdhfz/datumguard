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
import shutil
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
FROZEN_ENGINE_COMMIT = "40f1f7a991e592511033a480c6799516578a45f8"
FROZEN_PROTOCOL_HASH = "sha256:d18cf856bde7879d6887091fb4851502d3979ab998ef6f96d6eb22c86c275b36"
EXPECTED_PRE_FIX_RAW_SHA256 = (
    "sha256:58dcf7dc75246c9e884f4ad31be8709ff480e58c37a811d569f0fa779f7df1e9"
)
FROZEN_DATASET_MANIFEST_HASH = (
    "sha256:317a68807ddefd0ca3854261fed28b4e5fd166056a68e0925f255435f8e7c7c8"
)
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


def sha256_lf_normalized_file(path: Path) -> str:
    """Hash tracked text consistently across Git CRLF/LF checkout policies."""

    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def is_canonical_sha256(value: Any) -> bool:
    text = str(value)
    digest = text.removeprefix("sha256:")
    return (
        text.startswith("sha256:")
        and len(digest) == 64
        and digest == digest.lower()
        and all(character in "0123456789abcdef" for character in digest)
    )


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
            "sha256": sha256_lf_normalized_file(PROTOCOL_PATH),
            "line_ending_normalization": "CRLF_to_LF",
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
    raw_source_hashes = issue.get("source_hashes")
    source_hashes = (
        {str(key): str(value) for key, value in raw_source_hashes.items() if value is not None}
        if isinstance(raw_source_hashes, Mapping)
        else {}
    )
    return {
        "rule_id": rule_id,
        "scope": str(issue.get("scope") or scope_for_rule(rule_id)),
        "severity": str(issue.get("severity") or "error"),
        "asset_keys": sorted(asset_keys),
        "entity_pair": pair,
        "global_id_pair": sorted(raw_pair),
        "step_ids": sorted(step_ids),
        "field": canonical_field(rule_id, issue.get("field")),
        "issue_key": str(issue.get("issue_key") or ""),
        "source_hashes": source_hashes,
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
        "global_id_pair": sorted(str(value) for value in issue.get("global_id_pair") or []),
        "step_ids": sorted(int(value) for value in issue.get("step_entity_ids") or []),
        "field": canonical_field(str(issue["rule_id"]), issue.get("field")),
    }


def alert_key(alert: Mapping[str, Any]) -> tuple[Any, ...]:
    rule_id = str(alert["rule_id"])
    if rule_id == "GEO-01":
        global_id_pair = [str(value).strip() for value in alert.get("global_id_pair") or []]
        if len(global_id_pair) != 2 or not all(global_id_pair) or len(set(global_id_pair)) != 2:
            raise ValueError("GEO-01 matching requires two distinct non-empty GlobalIds")
        return (rule_id, tuple(sorted(global_id_pair)))
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


def ablation_matches(
    expected: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        ablation: match_alerts(
            expected,
            scoped(secondary, ablation),
            scoped(predictions, ablation),
        )
        for ablation in ABLATION_SCOPES
    }


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
    matches = ablation_matches(expected, secondary, primary_predictions)
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


ENGINE_RECORD_KEYS = {
    "case_id",
    "layout",
    "split",
    "candidate",
    "baseline_hash",
    "candidate_hash",
    "runs",
    "runtime",
    "determinism",
    "error",
}


def engine_only_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key in ENGINE_RECORD_KEYS}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    with path.open("wb") as stream:
        for record in records:
            stream.write(canonical_json(record))


def affected_case_ids_by_fix(records: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    geo_cases: set[str] = set()
    denominator_cases: set[str] = set()
    for record in records:
        matches = record.get("matches")
        if not isinstance(matches, Mapping):
            continue
        full = matches.get("D")
        if not isinstance(full, Mapping):
            continue
        if any(
            isinstance(issue, Mapping) and issue.get("rule_id") == "GEO-01"
            for issue in full.get("false_positives", [])
        ):
            geo_cases.add(str(record["case_id"]))
        full_denominator = int(full.get("tp", 0)) + int(full.get("fn", 0))
        if any(
            isinstance(matches.get(ablation), Mapping)
            and int(matches[ablation].get("tp", 0)) + int(matches[ablation].get("fn", 0))
            != full_denominator
            for ablation in ABLATION_SCOPES
        ):
            denominator_cases.add(str(record["case_id"]))
    return {
        "EVAL-GEO-PAIR-01": sorted(geo_cases),
        "EVAL-ABLATION-DENOM-01": sorted(denominator_cases),
    }


def reanalyze_engine_records(
    *,
    evidence_dir: Path,
    dataset_root: Path,
    cases: list[dict[str, Any]],
    source_path: Path,
    expected_source_hash: str,
    analysis_environment: dict[str, Any],
    expected_repeats: int = 10,
    analysis_tag: str | None = None,
    expected_dataset_manifest_hash: str = FROZEN_DATASET_MANIFEST_HASH,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    preserved_path = evidence_dir / "raw_results_pre_analysis_fix.jsonl"
    engine_path = evidence_dir / "raw_engine_results.jsonl"
    resolved_source = source_path.resolve()
    if not resolved_source.is_file():
        raise FileNotFoundError(f"Reanalysis source does not exist: {resolved_source}")
    actual_source_hash = sha256_file(resolved_source)
    if actual_source_hash != expected_source_hash:
        raise RuntimeError(
            f"Reanalysis source hash mismatch: expected {expected_source_hash}, "
            f"got {actual_source_hash}"
        )
    if analysis_environment.get("git", {}).get("dirty") is not False:
        raise RuntimeError("Reanalysis must start from a clean analysis commit")
    analysis_commit = analysis_environment.get("git", {}).get("commit")
    frozen_tag_commit = git_value("rev-parse", "protocol-v1^{commit}")
    if frozen_tag_commit != FROZEN_ENGINE_COMMIT:
        raise RuntimeError(
            f"protocol-v1 does not resolve to frozen engine commit {FROZEN_ENGINE_COMMIT}"
        )
    if analysis_commit == FROZEN_ENGINE_COMMIT:
        raise RuntimeError("Analysis commit must be distinct from the frozen engine commit")
    if analysis_tag is not None:
        tagged_commit = git_value("rev-list", "-n", "1", analysis_tag)
        if tagged_commit is None or tagged_commit != analysis_commit:
            raise RuntimeError(
                f"Analysis tag {analysis_tag!r} does not resolve to HEAD {analysis_commit}"
            )
    actual_protocol_hash = sha256_lf_normalized_file(PROTOCOL_PATH)
    if actual_protocol_hash != FROZEN_PROTOCOL_HASH:
        raise RuntimeError(
            f"Frozen protocol hash mismatch: expected {FROZEN_PROTOCOL_HASH}, "
            f"got {actual_protocol_hash}"
        )
    actual_dataset_manifest_hash = sha256_lf_normalized_file(dataset_root / "dataset_manifest.json")
    if actual_dataset_manifest_hash != expected_dataset_manifest_hash:
        raise RuntimeError(
            f"Frozen dataset manifest hash mismatch: expected {expected_dataset_manifest_hash}, "
            f"got {actual_dataset_manifest_hash}"
        )

    source_records = read_jsonl(resolved_source)
    if preserved_path.is_file() and sha256_file(preserved_path) != actual_source_hash:
        raise RuntimeError("Existing preserved raw result does not match the external source")
    if not preserved_path.is_file() and resolved_source != preserved_path.resolve():
        shutil.copyfile(resolved_source, preserved_path)
    elif resolved_source == preserved_path.resolve():
        preserved_path.parent.mkdir(parents=True, exist_ok=True)
    if sha256_file(preserved_path) != actual_source_hash:
        raise RuntimeError("Preserved pre-fix raw result changed during byte copy")
    engine_records = [engine_only_record(record) for record in source_records]
    write_jsonl(engine_path, engine_records)
    engine_records_readback = read_jsonl(engine_path)
    if engine_records_readback != engine_records:
        raise RuntimeError("Engine-only JSONL readback differs from in-memory engine records")
    engine_records_fingerprint = sha256_bytes(canonical_json(engine_records))
    readback_fingerprint = sha256_bytes(canonical_json(engine_records_readback))
    if readback_fingerprint != engine_records_fingerprint:
        raise RuntimeError("Engine-only canonical fingerprint changed after write/readback")

    case_by_id = {case["case_id"]: case for case in cases}
    selected_records = [record for record in engine_records if record["case_id"] in case_by_id]
    expected_count = len(cases) * 4
    if len(selected_records) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} engine records for reanalysis, got {len(selected_records)}"
        )
    variants = ("v0_clean", "v1_authorized", "v1_faulty", "v2_corrected")
    expected_keys = {(case["case_id"], variant) for case in cases for variant in variants}
    actual_keys = [(record["case_id"], record["candidate"]) for record in selected_records]
    if len(set(actual_keys)) != len(actual_keys):
        raise RuntimeError("Reanalysis source contains duplicate case/candidate records")
    if set(actual_keys) != expected_keys:
        missing = sorted(expected_keys - set(actual_keys))
        unexpected = sorted(set(actual_keys) - expected_keys)
        raise RuntimeError(
            f"Reanalysis source case/candidate mismatch; missing={missing}, unexpected={unexpected}"
        )

    for record in selected_records:
        case = case_by_id[record["case_id"]]
        case_dir = dataset_root / case["path"]
        baseline_hash = sha256_file(case_dir / "v0_clean.ifc")
        candidate_hash = sha256_file(case_dir / f"{record['candidate']}.ifc")
        truth_hash = sha256_file(case_dir / "truth.json")
        if baseline_hash != case["files"].get("v0_clean.ifc"):
            raise RuntimeError(f"Baseline manifest hash mismatch for {record['case_id']}")
        if candidate_hash != case["files"].get(f"{record['candidate']}.ifc"):
            raise RuntimeError(
                f"Candidate manifest hash mismatch for {record['case_id']}/{record['candidate']}"
            )
        if truth_hash != case["files"].get("truth.json"):
            raise RuntimeError(f"Truth manifest hash mismatch for {record['case_id']}")
        if record.get("baseline_hash") != baseline_hash:
            raise RuntimeError(f"Baseline hash mismatch for {record['case_id']}")
        if record.get("candidate_hash") != candidate_hash:
            raise RuntimeError(
                f"Candidate hash mismatch for {record['case_id']}/{record['candidate']}"
            )
        if record.get("error"):
            raise RuntimeError(
                f"Frozen engine record contains an error for "
                f"{record['case_id']}/{record['candidate']}"
            )
        runs = record.get("runs") or []
        if len(runs) != expected_repeats:
            raise RuntimeError(
                f"Expected {expected_repeats} measured repeats for "
                f"{record['case_id']}/{record['candidate']}, got {len(runs)}"
            )
        determinism = record.get("determinism") or {}
        run_hashes = [run.get("canonical_hash") for run in runs]
        if (
            determinism.get("identical_runs") is not True
            or determinism.get("total_runs") != expected_repeats
            or determinism.get("identical_count") != expected_repeats
            or [run.get("repeat") for run in runs] != list(range(1, expected_repeats + 1))
            or determinism.get("canonical_hashes") != run_hashes
            or len(set(run_hashes)) != 1
        ):
            raise RuntimeError(
                f"Frozen engine record is not deterministic for "
                f"{record['case_id']}/{record['candidate']}"
            )

    analyzed: list[dict[str, Any]] = []
    primary_fault_denominator = 0
    for index, engine_record in enumerate(selected_records, 1):
        record = dict(engine_record)
        case = case_by_id[record["case_id"]]
        case_dir = dataset_root / case["path"]
        if not record.get("error"):
            truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))
            predictions, matches = evaluate_candidate(
                record, truth, case_dir / f"{record['candidate']}.ifc"
            )
            record["normalized_predictions"] = predictions
            record["matches"] = matches
            if record["candidate"] == "v1_faulty":
                case_denominator = len(truth["candidates"]["v1_faulty"].get("expected_issues", []))
                primary_fault_denominator += case_denominator
                for ablation, match in matches.items():
                    if int(match["tp"]) + int(match["fn"]) != case_denominator:
                        raise RuntimeError(
                            f"Ablation {ablation} denominator changed for {record['case_id']}"
                        )
        analyzed.append(record)
        print(
            f"[reanalyze {index}/{expected_count}] {record['case_id']} {record['candidate']} ok",
            flush=True,
        )

    preliminary_metrics, _ = aggregate_metrics(source_records)
    affected_by_fix = affected_case_ids_by_fix(source_records)
    affected_cases = sorted(
        {case for cases_by_fix in affected_by_fix.values() for case in cases_by_fix}
    )
    audit = {
        "schema_version": "openbim-analysis-audit-v1",
        "analysis_revision": "post-freeze-evaluator-fix-2",
        "reanalyzed_at_utc": datetime.now(UTC).isoformat(),
        "detector_rerun": False,
        "detector_inputs_changed": False,
        "detector_outputs_changed": False,
        "thresholds_changed": False,
        "truth_changed": False,
        "engine_record_count": len(engine_records),
        "analyzed_record_count": len(analyzed),
        "measured_run_count": sum(len(record["runs"]) for record in engine_records),
        "run_fingerprint_groups_verified": len(engine_records),
        "primary_fault_denominator": primary_fault_denominator,
        "pre_fix_raw_results": {
            "path": preserved_path.name,
            "sha256": sha256_file(preserved_path),
        },
        "raw_engine_results": {
            "path": engine_path.name,
            "sha256": sha256_file(engine_path),
            "records_canonical_sha256": engine_records_fingerprint,
            "readback_verified": True,
        },
        "source_raw_results": {
            "external_path": str(resolved_source),
            "sha256": actual_source_hash,
        },
        "frozen_engine_run": {
            "commit": FROZEN_ENGINE_COMMIT,
            "protocol_hash": FROZEN_PROTOCOL_HASH,
            "tag": "protocol-v1",
            "tag_commit": frozen_tag_commit,
        },
        "affected_case_ids": affected_cases,
        "affected_case_ids_by_fix": affected_by_fix,
        "preliminary_metrics": {
            "ablations": preliminary_metrics.get("ablations", {}),
            "full_pipeline": preliminary_metrics.get("ablations", {}).get("D"),
            "geometry": preliminary_metrics.get("families", {}).get("Geometry"),
        },
        "analysis_git": {
            "commit": analysis_commit,
            "dirty": analysis_environment.get("git", {}).get("dirty"),
            "tag": analysis_tag,
        },
        "fixes": [
            {
                "id": "EVAL-GEO-PAIR-01",
                "description": (
                    "Use the preregistered sorted raw GlobalId pair for GEO-01 matching; "
                    "retain STEP IDs for audit when a GlobalId is duplicated by R01."
                ),
            },
            {
                "id": "EVAL-ABLATION-DENOM-01",
                "description": (
                    "Keep every primary fault in every ablation recall denominator while "
                    "filtering predictions by enabled scope."
                ),
            },
        ],
        "post_freeze_metric_interpretation": {
            "id": "METRIC-MACRO-SENSITIVITY-01",
            "description": (
                "Supported-rule family macro-F1 is reported only as a post-freeze sensitivity "
                "metric because the protocol did not freeze zero-support rule handling."
            ),
            "hypothesis_status": "NOT_CONCLUSIVE",
        },
    }
    return analyzed, audit


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
    aggregate: dict[str, Any] = {
        "ablations": {},
        "controls": {},
        "families": {},
        "rules": {},
        "family_macro_f1_by_family": {},
    }
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

    ablation_denominators = {
        ablation: int(values["tp"]) + int(values["fn"])
        for ablation, values in aggregate["ablations"].items()
    }
    denominator_consistent = len(set(ablation_denominators.values())) == 1
    fixed_denominator = next(iter(ablation_denominators.values()), 0)
    transitions = {"A_to_B": ("A", "B"), "B_to_C": ("B", "C"), "C_to_D": ("C", "D")}
    aggregate["incremental_true_positives"] = {
        name: int(aggregate["ablations"][after]["tp"]) - int(aggregate["ablations"][before]["tp"])
        for name, (before, after) in transitions.items()
    }
    aggregate["incremental_recall"] = {
        name: round(safe_ratio(delta, fixed_denominator), 9) if denominator_consistent else None
        for name, delta in aggregate["incremental_true_positives"].items()
    }
    aggregate["ablation_denominator_consistent"] = denominator_consistent
    for key, value in aggregate["incremental_recall"].items():
        metric_rows.append({"metric_group": "incremental_recall", "key": key, "value": value})

    faulty_records = [record for record in successful if record.get("candidate") == "v1_faulty"]
    aggregate["paired_incremental_recall"] = {}
    for name, (before, after) in transitions.items():
        paired_values: list[float] = []
        for record in faulty_records:
            record_denominators = {
                int(record["matches"][ablation]["tp"]) + int(record["matches"][ablation]["fn"])
                for ablation in ABLATION_SCOPES
            }
            if len(record_denominators) != 1:
                continue
            before_match = record["matches"][before]
            after_match = record["matches"][after]
            denominator = int(after_match["tp"]) + int(after_match["fn"])
            paired_values.append(
                safe_ratio(int(after_match["tp"]) - int(before_match["tp"]), denominator)
            )
        aggregate["paired_incremental_recall"][name] = {
            "case_count": len(paired_values),
            "mean": round(statistics.mean(paired_values), 9) if paired_values else 0.0,
            "median": round(statistics.median(paired_values), 9) if paired_values else 0.0,
            "minimum": round(min(paired_values), 9) if paired_values else 0.0,
            "maximum": round(max(paired_values), 9) if paired_values else 0.0,
        }
        metric_rows.append(
            {
                "metric_group": "paired_incremental_recall",
                "key": name,
                **aggregate["paired_incremental_recall"][name],
            }
        )

    full_matches = [record["matches"]["D"] for record in successful]
    supported_rule_scores: dict[str, dict[str, Any]] = {}
    for rule_id in sorted(PRIMARY_RULE_IDS):
        tp = sum(item["rule_id"] == rule_id for match in full_matches for item in match["matched"])
        fn = sum(
            item["rule_id"] == rule_id
            for match in full_matches
            for item in match["false_negatives"]
        )
        fp = sum(
            item["rule_id"] == rule_id
            for match in full_matches
            for item in match["false_positives"]
        )
        scores = prf(tp, fp, fn)
        aggregate["rules"][rule_id] = scores
        metric_rows.append({"metric_group": "rule", "key": rule_id, **scores})
        if tp + fn + fp:
            supported_rule_scores[rule_id] = scores
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
        supported_family_rules = [
            float(rule_scores["f1"])
            for rule_id, rule_scores in supported_rule_scores.items()
            if FAMILY_BY_RULE.get(rule_id) == family
        ]
        if supported_family_rules:
            aggregate["family_macro_f1_by_family"][family] = round(
                statistics.mean(supported_family_rules), 9
            )
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
    trace_entries: list[tuple[dict[str, Any], dict[str, str], set[str]]] = []
    for record in faulty_records:
        report = record["runs"][0]["report"]
        expected_hashes = {
            "baseline": str(report.get("baseline_hash") or record.get("baseline_hash") or ""),
            "candidate": str(report.get("candidate_hash") or record.get("candidate_hash") or ""),
            "ids": str(report.get("ids_hash") or ""),
            "profile": str(report.get("profile_hash") or ""),
        }
        valid_rule_ids = {
            str(result.get("rule_id"))
            for result in report.get("rule_results", [])
            if result.get("rule_id")
        }
        trace_entries.extend(
            (prediction, expected_hashes, valid_rule_ids)
            for prediction in record["normalized_predictions"]
        )

    def traceability_for(
        entries: Sequence[tuple[dict[str, Any], dict[str, str], set[str]]],
    ) -> dict[str, Any]:
        total = len(entries)
        source_count = sum(
            prediction.get("source_hashes") == expected_hashes
            and all(is_canonical_sha256(value) for value in expected_hashes.values())
            for prediction, expected_hashes, _valid_rule_ids in entries
        )
        rule_count = sum(
            prediction.get("rule_id") in valid_rule_ids
            for prediction, _expected_hashes, valid_rule_ids in entries
        )
        entity_count = sum(
            bool(
                prediction.get("asset_keys")
                or prediction.get("entity_pair")
                or prediction.get("step_ids")
            )
            for prediction, _expected_hashes, _valid_rule_ids in entries
        )
        return {
            "issue_count": total,
            "source_hash_coverage_count": source_count,
            "source_hash_coverage": round(safe_ratio(source_count, total), 9),
            "rule_id_coverage_count": rule_count,
            "rule_id_coverage": round(safe_ratio(rule_count, total), 9),
            "entity_reference_coverage_count": entity_count,
            "entity_reference_coverage": round(safe_ratio(entity_count, total), 9),
        }

    primary_trace_entries = [
        entry for entry in trace_entries if entry[0].get("rule_id") in PRIMARY_RULE_IDS
    ]
    aggregate["traceability"] = {
        "all_issues": traceability_for(trace_entries),
        "primary_issues": traceability_for(primary_trace_entries),
    }
    for scope, values in aggregate["traceability"].items():
        for key, value in values.items():
            metric_rows.append(
                {"metric_group": "traceability", "key": f"{scope}.{key}", "value": value}
            )
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
        "measured_engine_runs": metrics.get("runtime", {}).get("measured_run_count", 0),
        "injected_primary_faults_evaluated": (
            int(metrics.get("ablations", {}).get("D", {}).get("tp", 0))
            + int(metrics.get("ablations", {}).get("D", {}).get("fn", 0))
        ),
        "full_pipeline": metrics.get("ablations", {}).get("D", {}),
        "family_macro_f1": metrics.get("family_macro_f1"),
        "incremental_recall": metrics.get("incremental_recall", {}),
        "paired_incremental_recall": metrics.get("paired_incremental_recall", {}),
        "traceability": metrics.get("traceability", {}),
        "preregistered_targets": preregistered_target_status(metrics),
        "controls": metrics.get("controls", {}),
        "runtime": metrics.get("runtime", {}),
        "research_validation_only": True,
        "approval_eligible": False,
        "external_gates": {
            "bcf_viewer_import": "not_completed_no_qualified_bcf3_viewer",
            "buildingSMART_ifc_validation_service": "not_completed_login_unavailable",
            "distribution_license_review": "blocked_upstream_metadata_conflict",
            "docker_linux_ci": "completed_pr20_run_29192363975",
            "production_smoke": (
                "preview_web_api_contract_completed_run_29192389643_openbim_runtime_disabled"
            ),
        },
        "assurance_boundary": (
            "Synthetic research validation only; not structural, safety, code, fabrication, "
            "or construction approval."
        ),
    }


def preregistered_target_status(metrics: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    family_macros = metrics.get("family_macro_f1_by_family", {})
    families = metrics.get("families", {})
    controls = metrics.get("controls", {})
    runtime = metrics.get("runtime", {})
    values = {
        "Information macro-F1 >= 0.95": (
            float(family_macros.get("Information", 0.0)),
            0.95,
            ">=",
        ),
        "Geometry F1 >= 0.95": (
            float(families.get("Geometry", {}).get("f1", 0.0)),
            0.95,
            ">=",
        ),
        "Revision macro-F1 >= 0.95": (
            float(family_macros.get("Revision", 0.0)),
            0.95,
            ">=",
        ),
        "Clean false positives = 0": (
            int(controls.get("clean_false_positives", 0)),
            0,
            "=",
        ),
        "Authorized false positives = 0": (
            int(controls.get("authorized_false_positives", 0)),
            0,
            "=",
        ),
        "Engine p95 < 5000 ms": (
            float(runtime.get("engine_p95_ms", 0.0)),
            5000.0,
            "<",
        ),
    }
    results = {
        name: {
            "value": value,
            "threshold": threshold,
            "operator": operator,
            "status": (
                "PASS"
                if (operator == ">=" and value >= threshold)
                or (operator == "=" and value == threshold)
                or (operator == "<" and value < threshold)
                else "FAIL"
            ),
        }
        for name, (value, threshold, operator) in values.items()
    }
    for name in ("Information macro-F1 >= 0.95", "Revision macro-F1 >= 0.95"):
        sensitivity_value = results[name]["value"]
        results[name].update(
            {
                "value": None,
                "status": "NOT_CONCLUSIVE",
                "basis": "post-freeze supported-rule macro; zero-support policy not preregistered",
                "sensitivity_value": sensitivity_value,
                "sensitivity_definition": "mean F1 across supported rules only",
            }
        )
    return results


def target_assessment_line(name: str, result: Mapping[str, Any]) -> str:
    if result.get("status") == "NOT_CONCLUSIVE":
        return (
            f"- {name}: **NOT_CONCLUSIVE** "
            f"(post-freeze sensitivity {result.get('sensitivity_value')}; "
            f"{result.get('sensitivity_definition')}) — {result.get('basis')}"
        )
    return f"- {name}: **{result['status']}** (actual {result['value']})"


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
    targets = preregistered_target_status(metrics)
    traceability = metrics.get("traceability", {})
    all_trace = traceability.get("all_issues", {})
    primary_trace = traceability.get("primary_issues", {})
    lines = [
        "# OpenBIM Evidence Guard 실험 결과",
        "",
        "> 이 문서는 실험 러너가 원자료에서 자동 생성했다. 수동 편집하지 않는다.",
        "",
        f"- 실행 상태: `{summary['status']}`",
        f"- protocol SHA-256: `{summary['protocol_hash']}`",
        f"- dataset manifest SHA-256: `{summary['dataset_manifest_hash']}`",
        f"- 완료 candidate run: {summary['completed_candidate_runs']}",
        f"- 측정 engine run: {summary['measured_engine_runs']}",
        f"- engine error: {summary['engine_errors']}",
        "- 판정 용도: synthetic research validation only; approval eligible: `false`",
        "",
        "## Full pipeline (Ablation D)",
        "",
        f"- TP/FP/FN: {full.get('tp', 0)}/{full.get('fp', 0)}/{full.get('fn', 0)}",
        f"- Precision: {full.get('precision', 0):.6f}",
        f"- Recall: {full.get('recall', 0):.6f}",
        f"- F1: {full.get('f1', 0):.6f}",
        f"- Family macro-F1: {metrics.get('family_macro_f1', 0):.6f}",
        "",
        "## Ablation recall on the fixed primary-fault denominator",
        "",
        *[
            (
                f"- {ablation}: TP {values['tp']}, FP {values['fp']}, FN {values['fn']}, "
                f"Recall {values['recall']:.6f}, F1 {values['f1']:.6f}"
            )
            for ablation, values in metrics.get("ablations", {}).items()
        ],
        "",
        "## Incremental recall contribution",
        "",
        *[
            f"- {transition}: {value:+.6f}"
            for transition, value in metrics.get("incremental_recall", {}).items()
        ],
        "",
        "## Paired per-case incremental recall",
        "",
        *[
            (
                f"- {transition}: cases {values['case_count']}, mean {values['mean']:+.6f}, "
                f"median {values['median']:+.6f}, range "
                f"[{values['minimum']:+.6f}, {values['maximum']:+.6f}]"
            )
            for transition, values in metrics.get("paired_incremental_recall", {}).items()
        ],
        "",
        "## Fault-family F1",
        "",
        *[
            (
                f"- {family}: micro-F1 {values['f1']:.6f}; supported-rule macro-F1 "
                f"{metrics.get('family_macro_f1_by_family', {}).get(family, 'N/A')}"
            )
            for family, values in metrics.get("families", {}).items()
        ],
        "",
        "## Preregistered target assessment",
        "",
        *[target_assessment_line(name, result) for name, result in targets.items()],
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
        "- Canonical JSON determinism covers timestamp/run-ID-excluded engine payloads only.",
        "- BCFZIP byte determinism was not part of the repeated-run experiment.",
        "",
        "## Issue traceability",
        "",
        (
            "- All detected issues — source hash coverage: "
            f"{all_trace.get('source_hash_coverage_count', 0)}/"
            f"{all_trace.get('issue_count', 0)}"
        ),
        (
            "- All detected issues — registered rule ID coverage: "
            f"{all_trace.get('rule_id_coverage_count', 0)}/"
            f"{all_trace.get('issue_count', 0)}"
        ),
        (
            "- All detected issues — entity reference coverage: "
            f"{all_trace.get('entity_reference_coverage_count', 0)}/"
            f"{all_trace.get('issue_count', 0)}"
        ),
        (
            "- Primary issues — source/rule/entity coverage: "
            f"{primary_trace.get('source_hash_coverage_count', 0)}/"
            f"{primary_trace.get('issue_count', 0)}, "
            f"{primary_trace.get('rule_id_coverage_count', 0)}/"
            f"{primary_trace.get('issue_count', 0)}, "
            f"{primary_trace.get('entity_reference_coverage_count', 0)}/"
            f"{primary_trace.get('issue_count', 0)}"
        ),
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
        *(
            [
                "## Post-freeze analysis correction",
                "",
                f"- Revision: `{summary['analysis_revision']}`",
                "- Audit: `evidence/ANALYSIS_CORRECTION.md`",
                "- No engine rerun and no detector, input, truth, rule, or threshold changes.",
                "",
            ]
            if summary.get("analysis_revision")
            else []
        ),
        "## Open gates and negative findings",
        "",
        "- The first frozen aggregation exposed two evaluator defects; the preserved raw "
        "reports were reanalyzed without rerunning the detector.",
        "- Information/revision supported-rule macro-F1 is a post-freeze sensitivity metric; "
        "the preregistered hypotheses are not declared confirmed because zero-support handling "
        "was not frozen.",
        "- A qualified BCF 3.0 graphical viewer import is not completed. BIMcollab Zoom 9.8.14 "
        "was attempted but officially supports BCF only through 2.1, so it is not counted as a "
        "BCF 3.0 validation result.",
        "- Hosted buildingSMART validation was not completed because login was unavailable; "
        "no upload is claimed.",
        "- The distribution-license review found an unresolved `bcf-client==0.8.5` source/wheel "
        "metadata conflict, so BCF remains opt-in and public distribution remains blocked "
        "pending clarification.",
        "- Draft PR Docker/Linux CI, container/SBOM/security gates and preview deployment smoke "
        "passed; OpenBIM production runtime remains intentionally disabled and is not claimed as "
        "production validation.",
        "- No detector miss remained in this synthetic corpus after evaluator correction; this is "
        "not evidence of performance on real industrial IFC files.",
        "",
        "상세 실패와 모든 반복 결과는 `evidence/raw_results.jsonl`을 기준으로 한다. "
        "합성 IFC 결과를",
        "실제 FAB 적합성·안전·법규·시공 승인으로 일반화하지 않는다.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_analysis_correction(
    evidence_dir: Path,
    *,
    audit: dict[str, Any],
    summary: dict[str, Any],
    metrics: dict[str, Any],
) -> None:
    corrected_full = metrics["ablations"]["D"]
    corrected_geometry = metrics["families"]["Geometry"]
    audit["corrected_metrics"] = {
        "ablations": metrics["ablations"],
        "full_pipeline": corrected_full,
        "geometry": corrected_geometry,
    }
    audit["ablation_denominators"] = {
        ablation: int(values["tp"]) + int(values["fn"])
        for ablation, values in metrics["ablations"].items()
    }
    if any(
        denominator != audit["primary_fault_denominator"]
        for denominator in audit["ablation_denominators"].values()
    ):
        raise RuntimeError("Corrected ablations do not share the frozen primary-fault denominator")
    audit["corrected_raw_results_sha256"] = summary["raw_results_hash"]
    write_json(evidence_dir / "analysis_correction.json", audit)
    preliminary_full = audit["preliminary_metrics"]["full_pipeline"] or {}
    preliminary_geometry = audit["preliminary_metrics"]["geometry"] or {}
    preliminary_ablations = audit["preliminary_metrics"].get("ablations", {})
    ablation_effect_lines = [
        (
            "| Ablation | Preliminary TP/FP/FN | Corrected TP/FP/FN | "
            "Preliminary denominator | Corrected denominator |"
        ),
        "|---|---:|---:|---:|---:|",
    ]
    for ablation in ABLATION_SCOPES:
        before = preliminary_ablations.get(ablation, {})
        after = metrics["ablations"].get(ablation, {})
        ablation_effect_lines.append(
            f"| {ablation} | {before.get('tp')}/{before.get('fp')}/{before.get('fn')} | "
            f"{after.get('tp')}/{after.get('fp')}/{after.get('fn')} | "
            f"{int(before.get('tp', 0)) + int(before.get('fn', 0))} | "
            f"{int(after.get('tp', 0)) + int(after.get('fn', 0))} |"
        )
    lines = [
        "# Analysis correction audit",
        "",
        "The frozen detector run was not repeated. IFC/IDS inputs, detector outputs, truth, "
        "thresholds, and rules were unchanged.",
        "",
        f"- Frozen engine commit: `{audit['frozen_engine_run']['commit']}`",
        f"- Frozen tag: `{audit['frozen_engine_run']['tag']}`",
        f"- Analysis commit: `{audit['analysis_git']['commit']}`",
        f"- Analysis tag: `{audit['analysis_git']['tag']}`",
        (f"- Preserved pre-fix raw SHA-256: `{audit['pre_fix_raw_results']['sha256']}`"),
        f"- Raw engine-only SHA-256: `{audit['raw_engine_results']['sha256']}`",
        f"- Affected case union: {len(audit['affected_case_ids'])} cases",
        *[
            f"- {fix_id}: {len(case_ids)} cases ({', '.join(case_ids)})"
            for fix_id, case_ids in audit["affected_case_ids_by_fix"].items()
        ],
        f"- Fixed primary-fault denominator: {audit['primary_fault_denominator']}",
        "",
        "## Corrected evaluator defects",
        "",
        "1. `EVAL-GEO-PAIR-01`: GEO-01 now uses the preregistered sorted raw GlobalId pair. "
        "STEP IDs remain audit evidence for duplicate-GlobalId cases.",
        "2. `EVAL-ABLATION-DENOM-01`: all ablations retain the same primary-fault recall "
        "denominator; only predictions are scope-filtered.",
        "",
        "## Post-freeze metric interpretation",
        "",
        "`METRIC-MACRO-SENSITIVITY-01` reports supported-rule information/revision macro-F1, "
        "but does not declare the preregistered hypotheses confirmed because zero-support "
        "handling was not frozen.",
        "",
        "## Metric effect",
        "",
        *ablation_effect_lines,
        "",
        (
            "- Preliminary full TP/FP/FN: "
            f"{preliminary_full.get('tp')}/{preliminary_full.get('fp')}/"
            f"{preliminary_full.get('fn')}"
        ),
        f"- Preliminary Geometry F1: {preliminary_geometry.get('f1')}",
        (
            "- Corrected full TP/FP/FN: "
            f"{corrected_full['tp']}/{corrected_full['fp']}/{corrected_full['fn']}"
        ),
        f"- Corrected Geometry F1: {corrected_geometry['f1']}",
        "",
        "This is an automated reanalysis of preserved reports, not manual editing of raw data.",
        "",
    ]
    (evidence_dir / "ANALYSIS_CORRECTION.md").write_text("\n".join(lines), encoding="utf-8")
    limitations_path = ROOT / "docs" / "awards-2026" / "LIMITATIONS.md"
    limitations = limitations_path.read_text(encoding="utf-8")
    marker_start = "<!-- ANALYSIS_CORRECTION_START -->"
    marker_end = "<!-- ANALYSIS_CORRECTION_END -->"
    correction = "\n".join(
        [
            marker_start,
            "## Post-freeze 평가 구현 수정",
            "",
            (
                "동결된 engine report를 처음 집계할 때 GEO-01 pair key와 ablation recall "
                "denominator 구현 오류가 발견됐다."
            ),
            "",
            (f"- 영향 case union: {len(audit['affected_case_ids'])}개"),
            (
                "- GEO-01 pair 영향: "
                f"{len(audit['affected_case_ids_by_fix']['EVAL-GEO-PAIR-01'])}개 case"
            ),
            (
                "- ablation denominator 영향: "
                f"{len(audit['affected_case_ids_by_fix']['EVAL-ABLATION-DENOM-01'])}개 case"
            ),
            (
                "- 최초 full TP/FP/FN: "
                f"{preliminary_full.get('tp')}/{preliminary_full.get('fp')}/"
                f"{preliminary_full.get('fn')}"
            ),
            f"- 최초 Geometry F1: {preliminary_geometry.get('f1')}",
            (
                "- 수정 후 full TP/FP/FN: "
                f"{corrected_full['tp']}/{corrected_full['fp']}/{corrected_full['fn']}"
            ),
            f"- 수정 후 Geometry F1: {corrected_geometry['f1']}",
            "- engine 재실행 없음; detector, 입력, truth, 규칙, threshold 변경 없음",
            "- 원본 byte는 `evidence/raw_results_pre_analysis_fix.jsonl`로 보존",
            (
                "- information/revision supported-rule macro-F1은 zero-support 정책을 사전등록하지 "
                "않아 post-freeze sensitivity로만 보고"
            ),
            "",
            (
                "이는 모델 성능 수정이 아니라 사전등록한 matching/ablation 정의에 분석 코드를 "
                "일치시킨 post-freeze evaluator correction이다."
            ),
            marker_end,
            "",
        ]
    )
    if marker_start in limitations and marker_end in limitations:
        prefix = limitations.split(marker_start, 1)[0]
        suffix = limitations.split(marker_end, 1)[1].lstrip("\n")
        limitations = prefix + correction + suffix
    else:
        limitations = limitations.rstrip() + "\n\n" + correction
    limitations_path.write_text(limitations, encoding="utf-8")


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
    parser.add_argument(
        "--reanalyze-existing",
        action="store_true",
        help="Recompute metrics from preserved engine reports without rerunning the detector.",
    )
    parser.add_argument(
        "--reanalyze-source",
        type=Path,
        help="External preserved raw_results.jsonl used by --reanalyze-existing.",
    )
    parser.add_argument(
        "--expected-source-sha256",
        default=EXPECTED_PRE_FIX_RAW_SHA256,
        help="Required SHA-256 of the external pre-fix raw result.",
    )
    parser.add_argument(
        "--analysis-tag",
        help="Required clean Git tag resolving to HEAD for analysis-only replay.",
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
    if args.reanalyze_existing and args.regenerate_dataset:
        raise ValueError("--reanalyze-existing cannot regenerate the dataset")
    if args.reanalyze_existing and args.reanalyze_source is None:
        raise ValueError("--reanalyze-existing requires --reanalyze-source")
    if args.reanalyze_existing and not args.analysis_tag:
        raise ValueError("--reanalyze-existing requires --analysis-tag")
    if not args.reanalyze_existing and args.reanalyze_source is not None:
        raise ValueError("--reanalyze-source requires --reanalyze-existing")
    if not args.reanalyze_existing and args.analysis_tag is not None:
        raise ValueError("--analysis-tag requires --reanalyze-existing")
    source_hash = str(args.expected_source_sha256)
    if (
        len(source_hash) != 71
        or not source_hash.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in source_hash[7:])
    ):
        raise ValueError("--expected-source-sha256 must be sha256: plus 64 lowercase hex digits")


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
    analysis_audit: dict[str, Any] | None = None
    if args.reanalyze_existing:
        analysis_environment = capture_environment(args, manifest)
        if analysis_environment.get("git", {}).get("dirty") is not False:
            raise RuntimeError("Reanalysis must begin from a clean tagged analysis commit")
        raw_records, analysis_audit = reanalyze_engine_records(
            evidence_dir=evidence_dir,
            dataset_root=dataset_root,
            cases=cases,
            source_path=args.reanalyze_source,
            expected_source_hash=args.expected_source_sha256,
            analysis_environment=analysis_environment,
            expected_repeats=args.repeats,
            analysis_tag=args.analysis_tag,
        )
        analysis_environment["run_kind"] = "analysis-only replay"
        analysis_environment["detector_rerun"] = False
        analysis_environment["frozen_engine_commit"] = FROZEN_ENGINE_COMMIT
        write_json(evidence_dir / "fixture_manifest.json", fixture_manifest)
        write_json(evidence_dir / "environment.json", analysis_environment)
    else:
        write_initial_evidence(
            evidence_dir,
            args=args,
            dataset_manifest=manifest,
            fixture_manifest=fixture_manifest,
        )
        raw_records = []
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
    write_jsonl(raw_path, raw_records)

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
        "approval_eligible": False,
        "split": args.split,
        "case_count": len(cases),
        "completed_candidate_runs": len(raw_records) - errors,
        "measured_engine_runs": metrics.get("runtime", {}).get("measured_run_count", 0),
        "engine_errors": errors,
        "protocol_hash": sha256_lf_normalized_file(PROTOCOL_PATH),
        "dataset_manifest_hash": sha256_lf_normalized_file(dataset_root / "dataset_manifest.json"),
        "raw_results_hash": sha256_file(raw_path),
        "metrics": metrics,
        "preregistered_targets": preregistered_target_status(metrics),
    }
    if analysis_audit is not None:
        summary.update(
            {
                "analysis_revision": analysis_audit["analysis_revision"],
                "analysis_commit": analysis_audit["analysis_git"]["commit"],
                "detector_rerun": False,
                "pre_fix_raw_results_hash": analysis_audit["pre_fix_raw_results"]["sha256"],
                "raw_engine_results_hash": analysis_audit["raw_engine_results"]["sha256"],
                "analysis_audit": "analysis_correction.json",
            }
        )
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
    if analysis_audit is not None:
        reproduction_lines.extend(
            [
                "detector_rerun=false",
                f"analysis_revision={analysis_audit['analysis_revision']}",
                f"analysis_commit={analysis_audit['analysis_git']['commit']}",
                f"pre_fix_raw_results_hash={analysis_audit['pre_fix_raw_results']['sha256']}",
                f"raw_engine_results_hash={analysis_audit['raw_engine_results']['sha256']}",
            ]
        )
    (evidence_dir / "reproduction.log").write_text(
        "\n".join(reproduction_lines) + "\n", encoding="utf-8"
    )
    if analysis_audit is not None:
        write_analysis_correction(
            evidence_dir,
            audit=analysis_audit,
            summary=summary,
            metrics=metrics,
        )
    write_results_markdown(
        args.results_path.resolve(), summary=summary, metrics=metrics, bootstrap=bootstrap
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if errors == 0 or args.allow_engine_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

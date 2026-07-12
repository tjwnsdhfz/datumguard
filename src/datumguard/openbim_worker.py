from __future__ import annotations

import base64
import binascii
import json
import sys
import time
from typing import Any

from pydantic import ValidationError

from .ifc_evidence import canonical_json_bytes, open_ifc_bytes, sha256_bytes
from .openbim_models import (
    OpenBimEvidenceReport,
    OpenBimProfile,
    OpenBimRuleStatus,
    OpenBimSeverity,
    OpenBimSourceHashes,
)
from .openbim_rules import (
    sort_openbim_results,
    validate_clearance,
    validate_ids_requirements,
    validate_ifc_integrity,
    validate_revision,
)

MAX_IFC_BYTES = 20 * 1024 * 1024
MAX_IDS_BYTES = 1 * 1024 * 1024


def _decode_payload_bytes(payload: dict[str, Any], key: str, *, max_bytes: int) -> bytes:
    encoded = payload.get(key)
    if not isinstance(encoded, str) or not encoded:
        raise ValueError(f"{key} is required")
    if len(encoded) > ((max_bytes + 2) // 3) * 4 + 16:
        raise ValueError(f"{key} exceeds its size limit")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{key} is not valid base64") from exc
    if not data or len(data) > max_bytes:
        raise ValueError(f"{key} exceeds its size limit")
    return data


def evaluate_openbim_payload(payload: dict[str, Any]) -> OpenBimEvidenceReport:
    if payload.get("operation") != "openbim_evidence":
        raise ValueError("unsupported worker operation")
    baseline_bytes = _decode_payload_bytes(payload, "baseline_b64", max_bytes=MAX_IFC_BYTES)
    candidate_bytes = _decode_payload_bytes(payload, "candidate_b64", max_bytes=MAX_IFC_BYTES)
    ids_bytes = _decode_payload_bytes(payload, "requirements_b64", max_bytes=MAX_IDS_BYTES)
    profile_raw = payload.get("profile")
    if not isinstance(profile_raw, dict):
        raise ValueError("resolved profile object is required")
    try:
        profile = OpenBimProfile.model_validate(profile_raw)
    except ValidationError as exc:
        raise ValueError("resolved profile is invalid") from exc
    try:
        ids_xml = ids_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("IDS input must be UTF-8 XML") from exc

    profile_hash = sha256_bytes(canonical_json_bytes(profile.model_dump(mode="json")))
    hashes = OpenBimSourceHashes(
        baseline=sha256_bytes(baseline_bytes),
        candidate=sha256_bytes(candidate_bytes),
        ids=sha256_bytes(ids_bytes),
        profile=profile_hash,
    )
    timings: dict[str, float] = {}

    started = time.perf_counter()
    baseline = open_ifc_bytes(baseline_bytes)
    candidate = open_ifc_bytes(candidate_bytes)
    timings["parse_ifc"] = (time.perf_counter() - started) * 1000.0
    if str(baseline.schema).upper() != profile.ifc_schema:
        raise ValueError("baseline IFC schema is not supported by the registered profile")
    if len(baseline.by_type("IfcProduct")) > profile.max_products:
        raise ValueError("baseline IFC exceeds the registered product limit")

    results = []
    issues = []
    started = time.perf_counter()
    ids_results, ids_issues = validate_ids_requirements(candidate, ids_xml, hashes)
    timings["ids"] = (time.perf_counter() - started) * 1000.0
    results.extend(ids_results)
    issues.extend(ids_issues)

    started = time.perf_counter()
    integrity_results, integrity_issues, identity_ambiguous = validate_ifc_integrity(
        candidate, profile, hashes
    )
    timings["integrity"] = (time.perf_counter() - started) * 1000.0
    results.extend(integrity_results)
    issues.extend(integrity_issues)

    started = time.perf_counter()
    revision_results, revision_issues = validate_revision(
        baseline,
        candidate,
        profile,
        hashes,
        candidate_identity_ambiguous=identity_ambiguous,
    )
    timings["revision"] = (time.perf_counter() - started) * 1000.0
    results.extend(revision_results)
    issues.extend(revision_issues)

    started = time.perf_counter()
    clearance_results, clearance_issues = validate_clearance(candidate, profile, hashes)
    timings["clearance"] = (time.perf_counter() - started) * 1000.0
    results.extend(clearance_results)
    issues.extend(clearance_issues)

    results, issues = sort_openbim_results(results, issues)
    if any(result.status == OpenBimRuleStatus.FAILED for result in results) or any(
        issue.severity == OpenBimSeverity.ERROR for issue in issues
    ):
        status = "failed_verification"
    elif (
        any(
            result.status in {OpenBimRuleStatus.NOT_EVALUABLE, OpenBimRuleStatus.AMBIGUOUS}
            for result in results
        )
        or issues
    ):
        status = "needs_confirmation"
    else:
        status = "passed"
    timings["engine_total"] = sum(timings.values())
    return OpenBimEvidenceReport(
        status=status,  # type: ignore[arg-type]
        profile_id=profile.profile_id,
        baseline_hash=hashes.baseline,
        candidate_hash=hashes.candidate,
        ids_hash=hashes.ids,
        profile_hash=hashes.profile,
        rule_results=results,
        issues=issues,
        timings_ms={key: round(value, 3) for key, value in sorted(timings.items())},
    )


def main() -> None:
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("worker payload must be an object")
        report = evaluate_openbim_payload(payload)
        response: dict[str, Any] = {"ok": True, "report": report.model_dump(mode="json")}
    except (ValueError, ValidationError, UnicodeError, json.JSONDecodeError):
        response = {
            "ok": False,
            "error": {
                "code": "DG_OPENBIM_INPUT_INVALID",
                "message": "OpenBIM input or registered profile is invalid.",
            },
        }
    except Exception:
        response = {
            "ok": False,
            "error": {
                "code": "DG_OPENBIM_WORKER_FAILED",
                "message": "The isolated OpenBIM worker could not complete validation.",
            },
        }
    sys.stdout.buffer.write(canonical_json_bytes(response))


if __name__ == "__main__":
    main()


__all__ = ["MAX_IDS_BYTES", "MAX_IFC_BYTES", "evaluate_openbim_payload", "main"]

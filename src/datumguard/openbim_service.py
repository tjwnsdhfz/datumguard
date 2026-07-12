from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .cad_subprocess import CadWorkerFailure, run_openbim_worker
from .openbim_models import (
    REGISTERED_OPENBIM_PROFILES,
    OpenBimEvidenceReport,
    OpenBimProfile,
)
from .openbim_reporting import attach_reports
from .openbim_worker import MAX_IDS_BYTES, MAX_IFC_BYTES

MAX_OPENBIM_TOTAL_BYTES = (2 * MAX_IFC_BYTES) + MAX_IDS_BYTES
_PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


@dataclass(frozen=True)
class OpenBimServiceFailure(RuntimeError):
    code: str
    message: str
    status_code: int
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


def resolve_openbim_profile(profile_id: str) -> OpenBimProfile:
    if not _PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_PROFILE_INVALID",
            message="The selected OpenBIM profile is not registered.",
            status_code=422,
            details={"allowed_profile_ids": sorted(REGISTERED_OPENBIM_PROFILES)},
        )
    profile = REGISTERED_OPENBIM_PROFILES.get(profile_id)
    if profile is None:
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_PROFILE_INVALID",
            message="The selected OpenBIM profile is not registered.",
            status_code=422,
            details={"allowed_profile_ids": sorted(REGISTERED_OPENBIM_PROFILES)},
        )
    return profile


def _resolved_profile(profile: OpenBimProfile | dict[str, Any] | str) -> OpenBimProfile:
    if isinstance(profile, str):
        return resolve_openbim_profile(profile)
    if isinstance(profile, OpenBimProfile):
        return profile
    try:
        return OpenBimProfile.model_validate(profile)
    except ValidationError as exc:
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_PROFILE_INVALID",
            message="The OpenBIM profile is invalid.",
            status_code=422,
            details={"registered_profile_required_for_public_api": True},
        ) from exc


def _validate_inputs(
    baseline_bytes: bytes,
    candidate_bytes: bytes,
    requirements_bytes: bytes,
) -> None:
    inputs = {
        "baseline": (baseline_bytes, MAX_IFC_BYTES),
        "candidate": (candidate_bytes, MAX_IFC_BYTES),
        "requirements": (requirements_bytes, MAX_IDS_BYTES),
    }
    for name, (data, limit) in inputs.items():
        if not data:
            raise OpenBimServiceFailure(
                code="DG_OPENBIM_INPUT_INVALID",
                message="All OpenBIM evidence inputs are required.",
                status_code=422,
                details={"field": name},
            )
        if len(data) > limit:
            raise OpenBimServiceFailure(
                code="DG_OPENBIM_TOO_LARGE",
                message="An OpenBIM input exceeds its format-specific limit.",
                status_code=413,
                details={"field": name, "max_bytes": limit},
            )
    total_bytes = len(baseline_bytes) + len(candidate_bytes) + len(requirements_bytes)
    if total_bytes > MAX_OPENBIM_TOTAL_BYTES:
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_TOO_LARGE",
            message="The combined OpenBIM inputs exceed the request limit.",
            status_code=413,
            details={"max_total_bytes": MAX_OPENBIM_TOTAL_BYTES},
        )


def run_openbim_evidence(
    *,
    baseline_bytes: bytes,
    candidate_bytes: bytes,
    requirements_bytes: bytes,
    profile: OpenBimProfile | dict[str, Any] | str = "virtual-fab-v1",
    include_html: bool = True,
    include_bcf: bool = False,
) -> OpenBimEvidenceReport:
    """Reopen IFC bytes in an isolated worker and return normalized research evidence."""

    _validate_inputs(baseline_bytes, candidate_bytes, requirements_bytes)
    resolved_profile = _resolved_profile(profile)
    payload = {
        "operation": "openbim_evidence",
        "baseline_b64": base64.b64encode(baseline_bytes).decode("ascii"),
        "candidate_b64": base64.b64encode(candidate_bytes).decode("ascii"),
        "requirements_b64": base64.b64encode(requirements_bytes).decode("ascii"),
        "profile": resolved_profile.model_dump(mode="json"),
    }
    try:
        worker_result = run_openbim_worker(payload)
    except CadWorkerFailure as exc:
        safe_details = {
            key: value
            for key, value in exc.details.items()
            if key in {"failure", "timeout_seconds", "return_code", "output_limit_bytes"}
        }
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_WORKER_UNAVAILABLE",
            message="The isolated OpenBIM worker could not complete the request.",
            status_code=503,
            details={"isolated_worker": True, **safe_details},
        ) from exc

    if worker_result.get("ok") is not True:
        error = worker_result.get("error")
        error_code = error.get("code") if isinstance(error, dict) else None
        if error_code == "DG_OPENBIM_INPUT_INVALID":
            raise OpenBimServiceFailure(
                code="DG_OPENBIM_INPUT_INVALID",
                message="The IFC or IDS input is malformed or unsupported.",
                status_code=422,
                details={"isolated_worker": True},
            )
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_WORKER_UNAVAILABLE",
            message="The isolated OpenBIM worker could not complete the request.",
            status_code=503,
            details={"isolated_worker": True, "failure": "worker_reported_failure"},
        )
    raw_report = worker_result.get("report")
    if not isinstance(raw_report, dict):
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_WORKER_UNAVAILABLE",
            message="The isolated OpenBIM worker returned an invalid result.",
            status_code=503,
            details={"isolated_worker": True, "failure": "invalid_output"},
        )
    try:
        report = OpenBimEvidenceReport.model_validate(raw_report)
    except ValidationError as exc:
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_WORKER_UNAVAILABLE",
            message="The isolated OpenBIM worker returned an invalid result.",
            status_code=503,
            details={"isolated_worker": True, "failure": "invalid_output"},
        ) from exc
    if report.profile_id != resolved_profile.profile_id:
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_WORKER_UNAVAILABLE",
            message="The isolated OpenBIM worker returned mismatched evidence.",
            status_code=503,
            details={"isolated_worker": True, "failure": "profile_mismatch"},
        )
    try:
        return attach_reports(
            report,
            include_html=include_html,
            include_bcf=include_bcf,
            max_bcf_topics=resolved_profile.max_bcf_topics,
        )
    except (RuntimeError, ValueError) as exc:
        raise OpenBimServiceFailure(
            code="DG_OPENBIM_REPORT_FAILED",
            message="OpenBIM validation completed, but requested reports could not be packaged.",
            status_code=503,
            details={"reporting": True, "failure": type(exc).__name__},
        ) from exc


__all__ = [
    "MAX_IDS_BYTES",
    "MAX_IFC_BYTES",
    "MAX_OPENBIM_TOTAL_BYTES",
    "OpenBimServiceFailure",
    "resolve_openbim_profile",
    "run_openbim_evidence",
]

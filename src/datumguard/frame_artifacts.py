from __future__ import annotations

import io
import json
import math
import zipfile
from dataclasses import dataclass
from typing import Any, Literal

from .core import compute_artifact_hash
from .frame_dxf import FrameDxfVerificationResult
from .frame_models import FrameRunResponse, FrameSourceProvenance, StructuralFrameContract
from .frame_provenance import build_source_provenance
from .frame_rhino_adapter import RhinoFrameExchange
from .models import RunStatus, StrictModel


class FrameRoundTripArtifactError(ValueError):
    """Raised when a fail-closed round-trip bundle cannot be assembled."""


class FrameBundleFileRecord(StrictModel):
    name: str
    sha256: str
    size_bytes: int


class FrameRoundTripManifest(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    bundle_kind: Literal["frameguard_rhino_roundtrip"] = "frameguard_rhino_roundtrip"
    design_kind: Literal["structural_frame"] = "structural_frame"
    exchange_hash: str
    contract_hash: str
    artifact_hash: str
    screening_gate_status: Literal["passed"] = "passed"
    artifact_role: Literal["geometry_evidence"] = "geometry_evidence"
    screening_only: Literal[True] = True
    safety_certification: Literal[False] = False
    construction_approval: Literal[False] = False
    provenance: FrameSourceProvenance
    files: list[FrameBundleFileRecord]


@dataclass(frozen=True)
class FrameRoundTripBundle:
    bundle_bytes: bytes
    bundle_hash: str
    manifest: FrameRoundTripManifest
    manifest_hash: str


def _canonicalize(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FrameRoundTripArtifactError("non-finite values cannot enter evidence artifacts")
        return value
    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple | list):
        items = [_canonicalize(item) for item in value]
        if all(isinstance(item, dict) for item in items):
            return sorted(
                items,
                key=lambda item: json.dumps(
                    item,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        return items
    return value


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def build_frame_roundtrip_bundle(
    *,
    exchange: RhinoFrameExchange,
    exchange_hash: str,
    contract: StructuralFrameContract,
    contract_hash: str,
    dxf_bytes: bytes,
    verification: FrameDxfVerificationResult,
    analysis: FrameRunResponse,
) -> FrameRoundTripBundle:
    """Build a deterministic screening-evidence ZIP after every identity gate passes."""

    provenance = contract.provenance
    artifact_hash = compute_artifact_hash(dxf_bytes)
    if provenance is None or not provenance.complete:
        raise FrameRoundTripArtifactError("complete Rhino provenance is required")
    if provenance.exchange_hash != exchange_hash:
        raise FrameRoundTripArtifactError("exchange hash does not match contract provenance")
    if provenance.source_document_id != exchange.document.document_id:
        raise FrameRoundTripArtifactError("source document does not match contract provenance")
    expected_provenance = build_source_provenance(exchange, exchange_hash)
    if expected_provenance is None or expected_provenance.model_dump(mode="json") != (
        provenance.model_dump(mode="json")
    ):
        raise FrameRoundTripArtifactError(
            "contract provenance does not exactly match the source exchange mapping"
        )
    if contract.contract_hash != contract_hash:
        raise FrameRoundTripArtifactError("normalized contract hash does not match request chain")
    if analysis.status is not RunStatus.PASSED:
        raise FrameRoundTripArtifactError("structural screening did not pass")
    if analysis.contract_hash != contract_hash:
        raise FrameRoundTripArtifactError("analysis contract hash mismatch")
    if analysis.violations:
        raise FrameRoundTripArtifactError("structural screening contains violations")
    if verification.status is not RunStatus.PASSED or verification.violations:
        raise FrameRoundTripArtifactError("independent DXF verification did not pass")
    if verification.contract_hash != contract_hash:
        raise FrameRoundTripArtifactError("verification contract hash mismatch")
    if verification.artifact_hash != artifact_hash:
        raise FrameRoundTripArtifactError("verification artifact hash mismatch")
    if not verification.summary.get("provenance_verified"):
        raise FrameRoundTripArtifactError("DXF provenance was not independently verified")
    if not verification.summary.get("contract_record_verified"):
        raise FrameRoundTripArtifactError("DXF contract semantics were not independently verified")

    contract_payload = contract.model_dump(mode="json")
    contract_payload["contract_hash"] = contract_hash
    files: dict[str, bytes] = {
        "frameguard-screening.dxf": dxf_bytes,
        "frameguard-source-exchange.json": _json_bytes(exchange.model_dump(mode="json")),
        "frameguard-structural-contract.json": _json_bytes(contract_payload),
        "frameguard-screening.json": _json_bytes(analysis.model_dump(mode="json")),
        "frameguard-verification.json": _json_bytes(verification.model_dump(mode="json")),
        "preview.svg": analysis.preview_svg.encode("utf-8"),
    }
    file_records = [
        FrameBundleFileRecord(
            name=name,
            sha256=compute_artifact_hash(content),
            size_bytes=len(content),
        )
        for name, content in sorted(files.items())
    ]
    manifest = FrameRoundTripManifest(
        exchange_hash=exchange_hash,
        contract_hash=contract_hash,
        artifact_hash=artifact_hash,
        provenance=provenance,
        files=file_records,
    )
    canonical_manifest = _canonicalize(manifest.model_dump(mode="json"))
    if not isinstance(canonical_manifest, dict):
        raise AssertionError("round-trip manifest must remain a mapping")
    manifest = FrameRoundTripManifest.model_validate(canonical_manifest)
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
    files["manifest.json"] = manifest_bytes

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for filename, content in sorted(files.items()):
            info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.create_version = 20
            info.extract_version = 20
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, content)
    bundle_bytes = archive.getvalue()
    return FrameRoundTripBundle(
        bundle_bytes=bundle_bytes,
        bundle_hash=compute_artifact_hash(bundle_bytes),
        manifest=manifest,
        manifest_hash=compute_artifact_hash(manifest_bytes),
    )


__all__ = [
    "FrameRoundTripArtifactError",
    "FrameRoundTripBundle",
    "FrameRoundTripManifest",
    "build_frame_roundtrip_bundle",
]

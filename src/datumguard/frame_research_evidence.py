from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DATA_DIRECTORY = Path(__file__).with_name("data")
OPENSEES_REPORT_NAME = "frame_opensees_parity.json"
GNN_BENCHMARK_NAME = "frame_gnn_benchmark.json"


class FrameResearchEvidenceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _load_report(filename: str, *, expected_kind: str) -> dict[str, Any]:
    path = DATA_DIRECTORY / filename
    if not path.is_file():
        raise FrameResearchEvidenceError(
            "DG_FRAME_RESEARCH_EVIDENCE_UNAVAILABLE",
            f"Packaged FrameGuard evidence is unavailable: {filename}",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrameResearchEvidenceError(
            "DG_FRAME_RESEARCH_EVIDENCE_INVALID",
            f"Packaged FrameGuard evidence is invalid: {filename}",
        ) from exc
    if not isinstance(payload, dict):
        raise FrameResearchEvidenceError(
            "DG_FRAME_RESEARCH_EVIDENCE_INVALID",
            f"Packaged FrameGuard evidence must be a JSON object: {filename}",
        )
    actual_kind = payload.get("benchmark_kind") or payload.get("report_kind")
    if actual_kind != expected_kind:
        raise FrameResearchEvidenceError(
            "DG_FRAME_RESEARCH_EVIDENCE_INVALID",
            f"Packaged FrameGuard evidence has the wrong kind: {filename}",
        )
    return copy.deepcopy(payload)


def load_opensees_parity_report() -> dict[str, Any]:
    return _load_report(
        OPENSEES_REPORT_NAME,
        expected_kind="frame_opensees_parity_v1",
    )


def load_gnn_benchmark() -> dict[str, Any]:
    return _load_report(
        GNN_BENCHMARK_NAME,
        expected_kind="frame_gnn_benchmark_v1",
    )


__all__ = [
    "DATA_DIRECTORY",
    "FrameResearchEvidenceError",
    "load_gnn_benchmark",
    "load_opensees_parity_report",
]

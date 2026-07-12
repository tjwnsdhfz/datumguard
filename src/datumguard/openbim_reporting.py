from __future__ import annotations

import base64
import html
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from .ifc_evidence import canonical_json_bytes, sha256_bytes
from .openbim_models import OpenBimEvidenceReport, OpenBimReportArtifact

_IFC_GUID_PATTERN = re.compile(r"^[0-9A-Za-z_$]{22}$")


def canonical_evidence_payload(report: OpenBimEvidenceReport) -> dict[str, Any]:
    """Return the deterministic evidence body, excluding measured and packaged fields."""

    payload = report.model_dump(mode="json", exclude={"timings_ms", "reports"})
    payload["timings_ms"] = {}
    payload["reports"] = []
    return payload


def canonical_evidence_json(report: OpenBimEvidenceReport) -> bytes:
    return canonical_json_bytes(canonical_evidence_payload(report))


def render_evidence_html(report: OpenBimEvidenceReport) -> bytes:
    issue_rows: list[str] = []
    for issue in report.issues:
        entities = issue.entity_pair or issue.entity_ids
        expected = html.escape(json.dumps(issue.expected, ensure_ascii=False, sort_keys=True))
        actual = html.escape(json.dumps(issue.actual, ensure_ascii=False, sort_keys=True))
        issue_rows.append(
            "<tr>"
            f"<td>{html.escape(issue.rule_id)}</td>"
            f"<td>{html.escape(issue.scope.value)}</td>"
            f"<td>{html.escape(issue.severity.value)}</td>"
            f"<td>{html.escape(issue.message)}</td>"
            f"<td>{html.escape(', '.join(entities))}</td>"
            f"<td><code>{expected}</code></td>"
            f"<td><code>{actual}</code></td>"
            "</tr>"
        )
    if not issue_rows:
        issue_rows.append(
            '<tr><td colspan="7">No issues in the registered research rules.</td></tr>'
        )
    rule_rows = [
        "<tr>"
        f"<td>{html.escape(result.rule_id)}</td>"
        f"<td>{html.escape(result.scope.value)}</td>"
        f"<td>{html.escape(result.status.value)}</td>"
        f"<td>{result.evaluated_count}</td>"
        f"<td>{result.issue_count}</td>"
        f"<td>{html.escape(result.summary)}</td>"
        "</tr>"
        for result in report.rule_results
    ]
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpenBIM Evidence Guard</title>
<style>
body{{font:14px/1.5 system-ui,sans-serif;margin:2rem;color:#172033}}
table{{border-collapse:collapse;width:100%;margin:1rem 0 2rem}}
th,td{{border:1px solid #ccd3df;padding:.45rem;text-align:left;vertical-align:top}}
th{{background:#eef2f7}}
code{{white-space:pre-wrap;overflow-wrap:anywhere}}
.boundary{{padding:.8rem;background:#fff4d6;border-left:4px solid #d28a00}}
</style>
</head>
<body>
<h1>OpenBIM Evidence Guard</h1>
<p class="boundary"><strong>Research validation only.</strong>
This report is not structural, safety, code, fabrication, or construction approval.</p>
<dl>
<dt>Status</dt><dd>{html.escape(report.status)}</dd>
<dt>Profile</dt><dd>{html.escape(report.profile_id)} / {html.escape(report.profile_hash)}</dd>
<dt>Baseline</dt><dd>{html.escape(report.baseline_hash)}</dd>
<dt>Candidate</dt><dd>{html.escape(report.candidate_hash)}</dd>
<dt>IDS</dt><dd>{html.escape(report.ids_hash)}</dd>
</dl>
<h2>Rule results</h2>
<table><thead><tr><th>Rule</th><th>Scope</th><th>Status</th><th>Evaluated</th><th>Issues</th><th>Summary</th></tr></thead><tbody>{"".join(rule_rows)}</tbody></table>
<h2>Issues</h2>
<table><thead><tr><th>Rule</th><th>Scope</th><th>Severity</th><th>Message</th><th>Entities</th><th>Expected</th><th>Actual</th></tr></thead><tbody>{"".join(issue_rows)}</tbody></table>
</body>
</html>
"""
    return document.encode("utf-8")


def render_bcfzip(report: OpenBimEvidenceReport, *, max_topics: int) -> bytes:
    if len(report.issues) > max_topics:
        raise ValueError("issue count exceeds the registered BCF topic limit")
    try:
        import numpy as np
        from bcf.v3.bcfxml import BcfXml
    except ImportError as exc:
        raise RuntimeError("BCF export dependency is unavailable") from exc

    bcfxml = BcfXml.create_new("OpenBIM Evidence Guard")
    for issue in report.issues:
        description = json.dumps(
            {
                "issue_key": issue.issue_key,
                "scope": issue.scope.value,
                "severity": issue.severity.value,
                "message": issue.message,
                "expected": issue.expected,
                "actual": issue.actual,
                "source_hashes": issue.source_hashes.model_dump(mode="json"),
                "step_ids": issue.step_ids,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        topic = bcfxml.add_topic(
            f"[{issue.rule_id}] {issue.message}"[:250],
            description,
            "OpenBIM Evidence Guard",
            topic_type=issue.scope.value,
            topic_status="Open",
        )
        guids = sorted(
            {
                entity_id
                for entity_id in (issue.entity_pair or issue.entity_ids)
                if _IFC_GUID_PATTERN.fullmatch(entity_id)
            }
        )
        if guids:
            position = np.array(issue.location or (0.0, 0.0, 0.0), dtype=float)
            topic.add_viewpoint_from_point_and_guids(position, *guids)

    with tempfile.TemporaryDirectory(prefix="datumguard-bcf-") as directory:
        filepath = Path(directory) / "openbim-evidence.bcfzip"
        bcfxml.save(filepath)
        loaded = BcfXml.load(filepath)
        try:
            if loaded is None or len(loaded.topics) != len(report.issues):
                raise RuntimeError("BCF semantic round-trip failed")
        finally:
            if loaded is not None:
                loaded.close()
        bcfxml.close()
        return filepath.read_bytes()


def _artifact(
    kind: str,
    filename: str,
    media_type: str,
    content: bytes,
) -> OpenBimReportArtifact:
    return OpenBimReportArtifact(
        kind=kind,  # type: ignore[arg-type]
        filename=filename,
        media_type=media_type,
        artifact_hash=sha256_bytes(content),
        byte_size=len(content),
        content_base64=base64.b64encode(content).decode("ascii"),
    )


def attach_reports(
    report: OpenBimEvidenceReport,
    *,
    include_html: bool,
    include_bcf: bool,
    max_bcf_topics: int,
) -> OpenBimEvidenceReport:
    artifacts = [
        _artifact(
            "evidence_json",
            "openbim-evidence.json",
            "application/json",
            canonical_evidence_json(report),
        )
    ]
    if include_html:
        artifacts.append(
            _artifact(
                "html",
                "openbim-evidence.html",
                "text/html; charset=utf-8",
                render_evidence_html(report),
            )
        )
    if include_bcf:
        artifacts.append(
            _artifact(
                "bcfzip",
                "openbim-evidence.bcfzip",
                "application/vnd.bcf+zip",
                render_bcfzip(report, max_topics=max_bcf_topics),
            )
        )
    manifest_payload = {
        "schema_version": "openbim-evidence-manifest-1.0",
        "profile_id": report.profile_id,
        "input_hashes": {
            "baseline": report.baseline_hash,
            "candidate": report.candidate_hash,
            "ids": report.ids_hash,
            "profile": report.profile_hash,
        },
        "artifacts": [
            {
                "kind": artifact.kind,
                "filename": artifact.filename,
                "media_type": artifact.media_type,
                "artifact_hash": artifact.artifact_hash,
                "byte_size": artifact.byte_size,
            }
            for artifact in sorted(artifacts, key=lambda item: item.kind)
        ],
    }
    artifacts.append(
        _artifact(
            "manifest",
            "openbim-evidence-manifest.json",
            "application/json",
            canonical_json_bytes(manifest_payload),
        )
    )
    return report.model_copy(update={"reports": sorted(artifacts, key=lambda item: item.kind)})


__all__ = [
    "attach_reports",
    "canonical_evidence_json",
    "canonical_evidence_payload",
    "render_bcfzip",
    "render_evidence_html",
]

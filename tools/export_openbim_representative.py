"""Export the representative OpenBIM evidence bundle from a clean Git commit."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from importlib import metadata
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from datumguard.openbim_service import run_openbim_evidence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_ROOT = ROOT / "fixtures" / "openbim"
DEFAULT_OUTPUT = ROOT / "docs" / "awards-2026" / "evidence" / "representative"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def distribution_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def publish_staged_directory(
    staging_dir: Path,
    output_dir: Path,
    *,
    replace: Any = os.replace,
) -> None:
    """Publish a complete directory with rollback if the final rename fails."""

    output_parent = output_dir.parent.resolve()
    staging_resolved = staging_dir.resolve()
    output_resolved = output_dir.resolve()
    if not output_resolved.is_relative_to(ROOT) or output_resolved == ROOT:
        raise RuntimeError("Representative output must remain inside the repository")
    if staging_resolved.parent != output_parent or not staging_resolved.is_dir():
        raise RuntimeError("Representative staging directory is invalid")
    if output_dir.is_symlink():
        raise RuntimeError("Representative output cannot replace a symlink")

    backup_dir = output_parent / f".{output_dir.name}.backup-{uuid.uuid4().hex}"
    had_previous = output_dir.exists()
    if had_previous:
        replace(output_dir, backup_dir)
    try:
        replace(staging_dir, output_dir)
    except Exception:
        if had_previous and backup_dir.exists() and not output_dir.exists():
            replace(backup_dir, output_dir)
        raise
    if backup_dir.exists():
        shutil.rmtree(backup_dir)


def inspect_bcfzip(content: bytes, *, expected_topics: int) -> dict[str, Any]:
    """Independently parse ZIP/XML structure without using the BCF writer library."""

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("BCFZIP contains duplicate paths")
        if any(
            Path(name).is_absolute() or ".." in Path(name).parts or "\\" in name for name in names
        ):
            raise RuntimeError("BCFZIP contains an unsafe path")
        if "bcf.version" not in names:
            raise RuntimeError("BCFZIP is missing bcf.version")
        xml_names = sorted(
            name for name in names if name.endswith((".bcf", ".bcfv", ".bcfp", ".version", ".xml"))
        )
        for name in xml_names:
            ElementTree.fromstring(archive.read(name))
        topic_markup = sorted(name for name in names if name.endswith("markup.bcf"))
        if len(topic_markup) != expected_topics:
            raise RuntimeError(f"Expected {expected_topics} BCF topics, found {len(topic_markup)}")
        return {
            "generic_zip_xml_parse": True,
            "entry_count": len(names),
            "xml_entry_count": len(xml_names),
            "topic_markup_count": len(topic_markup),
            "independent_viewer_import": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status = git_value("status", "--porcelain")
    if status and not args.allow_dirty:
        raise RuntimeError("Representative export requires a clean Git commit")
    source_commit = git_value("rev-parse", "HEAD")
    fixture_root = args.fixture_root.resolve()
    output_dir = args.output_dir.resolve()
    representative = fixture_root / "representative"
    baseline_path = representative / "v0_clean.ifc"
    candidate_path = representative / "v1_faulty.ifc"
    ids_path = fixture_root / "virtual_fab_v1.ids"
    input_bytes = {
        "baseline": baseline_path.read_bytes(),
        "candidate": candidate_path.read_bytes(),
        "ids": ids_path.read_bytes(),
    }
    independently_computed_hashes = {
        name: sha256_bytes(content) for name, content in input_bytes.items()
    }

    report = run_openbim_evidence(
        baseline_bytes=input_bytes["baseline"],
        candidate_bytes=input_bytes["candidate"],
        requirements_bytes=input_bytes["ids"],
        profile="virtual-fab-v1",
        include_html=True,
        include_bcf=True,
    )
    if report.status != "failed_verification" or not report.issues:
        raise RuntimeError("Representative faulty fixture did not produce failure evidence")
    if report.research_validation_only is not True or report.approval_eligible is not False:
        raise RuntimeError("Representative report crossed the registered assurance boundary")
    report_input_hashes = {
        "baseline": report.baseline_hash,
        "candidate": report.candidate_hash,
        "ids": report.ids_hash,
    }
    if report_input_hashes != independently_computed_hashes:
        raise RuntimeError("Service input hashes differ from independently computed hashes")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}.staging-", dir=output_dir.parent
    ) as temporary_directory:
        staging_dir = Path(temporary_directory)
        readme_path = output_dir / "README.md"
        if readme_path.is_file():
            shutil.copyfile(readme_path, staging_dir / "README.md")

        artifact_index: list[dict[str, Any]] = []
        bcf_check: dict[str, Any] | None = None
        manifest_payload: dict[str, Any] | None = None
        for artifact in report.reports:
            filename = artifact.filename
            if Path(filename).name != filename:
                raise RuntimeError(f"Unsafe report filename: {filename}")
            content = base64.b64decode(artifact.content_base64, validate=True)
            actual_hash = sha256_bytes(content)
            if actual_hash != artifact.artifact_hash or len(content) != artifact.byte_size:
                raise RuntimeError(f"Artifact metadata mismatch: {filename}")
            (staging_dir / filename).write_bytes(content)
            artifact_index.append(
                {
                    "kind": artifact.kind,
                    "filename": filename,
                    "media_type": artifact.media_type,
                    "byte_size": len(content),
                    "sha256": actual_hash,
                }
            )
            if artifact.kind == "bcfzip":
                bcf_check = inspect_bcfzip(content, expected_topics=len(report.issues))
            if artifact.kind == "manifest":
                manifest_payload = json.loads(content)

        if bcf_check is None:
            raise RuntimeError("Representative export did not include BCFZIP")
        if manifest_payload is None:
            raise RuntimeError("Representative export did not include a manifest")
        expected_manifest_artifacts = [
            {
                "kind": item["kind"],
                "filename": item["filename"],
                "media_type": item["media_type"],
                "artifact_hash": item["sha256"],
                "byte_size": item["byte_size"],
            }
            for item in sorted(artifact_index, key=lambda value: value["kind"])
            if item["kind"] != "manifest"
        ]
        expected_manifest_hashes = {**report_input_hashes, "profile": report.profile_hash}
        if manifest_payload.get("input_hashes") != expected_manifest_hashes:
            raise RuntimeError("Evidence manifest input hashes do not match the report")
        if manifest_payload.get("artifacts") != expected_manifest_artifacts:
            raise RuntimeError("Evidence manifest artifact index does not match exported bytes")

        verification = {
            "schema_version": "openbim-representative-export-v2",
            "source_commit": source_commit,
            "source_tags": sorted(git_value("tag", "--points-at", "HEAD").splitlines()),
            "analysis_tag": git_value("describe", "--tags", "--match", "analysis-*", "--abbrev=0"),
            "protocol_tag_commit": git_value("rev-parse", "protocol-v1^{commit}"),
            "git_dirty_before_export": bool(status),
            "uv_lock_sha256": sha256_bytes((ROOT / "uv.lock").read_bytes()),
            "protocol_sha256": sha256_bytes(
                (ROOT / "docs" / "awards-2026" / "protocol.yaml").read_bytes()
            ),
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "packages": {
                    name: distribution_version(name)
                    for name in ("datumguard", "ifcopenshell", "ifctester", "bcf-client")
                },
            },
            "research_validation_only": report.research_validation_only,
            "approval_eligible": report.approval_eligible,
            "status": report.status,
            "profile_id": report.profile_id,
            "input_files": {
                "baseline": str(baseline_path.relative_to(ROOT)).replace("\\", "/"),
                "candidate": str(candidate_path.relative_to(ROOT)).replace("\\", "/"),
                "ids": str(ids_path.relative_to(ROOT)).replace("\\", "/"),
            },
            "independently_computed_input_hashes": independently_computed_hashes,
            "profile_hash": report.profile_hash,
            "manifest_cross_check": True,
            "rule_result_count": len(report.rule_results),
            "issue_count": len(report.issues),
            "artifacts": sorted(artifact_index, key=lambda item: item["kind"]),
            "bcf_generic_structure_check": bcf_check,
            "external_bcf_viewer_gate": "not_completed",
        }
        (staging_dir / "representative-verification.json").write_bytes(
            canonical_json_bytes(verification)
        )
        publish_staged_directory(staging_dir, output_dir)
    print(json.dumps(verification, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

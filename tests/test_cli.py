from __future__ import annotations

import json
import shutil
from pathlib import Path

import ezdxf
import pytest
from pytest import CaptureFixture, MonkeyPatch

from datumguard.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _simple_dxf(path: Path) -> None:
    document = ezdxf.new("R2013")
    document.units = 4
    document.modelspace().add_line((0.0, 0.0), (100.0, 0.0))
    document.saveas(path)


def test_verify_writes_fail_closed_result_and_approved_bundle(tmp_path: Path) -> None:
    output = tmp_path / "results"

    exit_code = main(
        [
            "verify",
            str(ROOT / "fixtures" / "examples" / "design_contract.json"),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    result = json.loads((output / "verification-result.json").read_text(encoding="utf-8"))
    assert result["status"] == "passed"
    assert result["contract_hash"].startswith("sha256:")
    assert "bundle_base64" not in result
    assert (output / "verified-bundle.zip").is_file()
    assert (output / "preview.svg").is_file()


def test_audit_and_compare_existing_dxf(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.dxf"
    candidate = tmp_path / "candidate.dxf"
    _simple_dxf(baseline)
    shutil.copyfile(baseline, candidate)

    audit_output = tmp_path / "audit"
    compare_output = tmp_path / "compare"
    assert main(["audit", str(baseline), "--output", str(audit_output)]) == 0
    assert (
        main(
            [
                "compare",
                str(baseline),
                str(candidate),
                "--output",
                str(compare_output),
            ]
        )
        == 0
    )

    audit_result = json.loads(
        (audit_output / "verification-result.json").read_text(encoding="utf-8")
    )
    comparison = json.loads(
        (compare_output / "verification-result.json").read_text(encoding="utf-8")
    )
    assert audit_result["status"] == "audited"
    assert audit_result["original_preserved"] is True
    assert comparison["status"] == "audited"
    assert comparison["same_artifact"] is True
    assert comparison["comparison_complete"] is True


def test_unknown_design_kind_fails_without_outputs(tmp_path: Path) -> None:
    contract = tmp_path / "unknown.json"
    contract.write_text(
        json.dumps({"schema_version": "1.0.0", "design_kind": "unknown"}),
        encoding="utf-8",
    )
    output = tmp_path / "results"
    output.mkdir()
    (output / "verified-bundle.zip").write_bytes(b"stale approved output")
    (output / "verified.step").write_bytes(b"stale STEP")

    assert main(["verify", str(contract), "--output", str(output)]) == 1
    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_failed_contract_writes_evidence_but_never_bundle(tmp_path: Path) -> None:
    output = tmp_path / "rejected"

    assert (
        main(
            [
                "verify",
                str(ROOT / "fixtures" / "examples" / "architecture_studio.json"),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert (output / "verified-bundle.zip").is_file()

    exit_code = main(
        [
            "verify",
            str(ROOT / "fixtures" / "examples" / "architecture_open_300mm.json"),
            "--output",
            str(output),
        ]
    )

    result = json.loads((output / "verification-result.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert result["status"] == "failed_verification"
    assert not (output / "verified-bundle.zip").exists()


def test_contract_validation_error_does_not_log_input_value(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    payload = json.loads(
        (ROOT / "fixtures" / "examples" / "design_contract.json").read_text(encoding="utf-8")
    )
    payload["outline"]["width"] = "CONFIDENTIAL-DIMENSION"
    contract = tmp_path / "invalid.json"
    contract.write_text(json.dumps(payload), encoding="utf-8")

    assert main(["verify", str(contract), "--output", str(tmp_path / "results")]) == 1

    captured = capsys.readouterr()
    assert "contract validation error" in captured.err
    assert "CONFIDENTIAL-DIMENSION" not in captured.err


def test_model_validation_error_does_not_log_confidential_identifier(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    payload = json.loads(
        (ROOT / "fixtures" / "examples" / "architecture_studio.json").read_text(encoding="utf-8")
    )
    payload["openings"][0]["wall_id"] = "CONFIDENTIAL-WALL-ID"
    contract = tmp_path / "invalid-architecture.json"
    contract.write_text(json.dumps(payload), encoding="utf-8")

    assert main(["verify", str(contract), "--output", str(tmp_path / "results")]) == 1

    captured = capsys.readouterr()
    assert "contract validation error" in captured.err
    assert "CONFIDENTIAL-WALL-ID" not in captured.err


def test_managed_output_symlink_is_replaced_without_following(
    tmp_path: Path,
) -> None:
    output = tmp_path / "results"
    output.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("DO NOT OVERWRITE", encoding="utf-8")
    result_link = output / "verification-result.json"
    try:
        result_link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    assert (
        main(
            [
                "verify",
                str(ROOT / "fixtures" / "examples" / "design_contract.json"),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert outside.read_text(encoding="utf-8") == "DO NOT OVERWRITE"
    assert not result_link.is_symlink()
    assert json.loads(result_link.read_text(encoding="utf-8"))["status"] == "passed"


def test_input_cannot_collide_with_managed_output(tmp_path: Path) -> None:
    contract = tmp_path / "verification-result.json"
    original = (ROOT / "fixtures" / "examples" / "design_contract.json").read_text(encoding="utf-8")
    contract.write_text(original, encoding="utf-8")

    assert main(["verify", str(contract), "--output", str(tmp_path)]) == 1
    assert contract.read_text(encoding="utf-8") == original


def test_symlinked_input_target_cannot_collide_with_managed_output(tmp_path: Path) -> None:
    output = tmp_path / "results"
    output.mkdir()
    contract = output / "verification-result.json"
    original = (ROOT / "fixtures" / "examples" / "design_contract.json").read_text(encoding="utf-8")
    contract.write_text(original, encoding="utf-8")
    link = tmp_path / "contract-link.json"
    try:
        link.symlink_to(contract)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    assert main(["verify", str(link), "--output", str(output)]) == 1
    assert contract.read_text(encoding="utf-8") == original


def test_github_metadata_contains_only_input_basename(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    github_output = tmp_path / "github-output.txt"
    github_summary = tmp_path / "github-summary.md"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(github_summary))
    artifact = tmp_path / "private-folder" / "drawing.dxf"
    artifact.parent.mkdir()
    _simple_dxf(artifact)

    assert main(["audit", str(artifact), "--output", str(tmp_path / "results")]) == 0

    output_text = github_output.read_text(encoding="utf-8")
    summary_text = github_summary.read_text(encoding="utf-8")
    assert "status=audited" in output_text
    assert "drawing.dxf" in summary_text
    assert "private-folder" not in summary_text

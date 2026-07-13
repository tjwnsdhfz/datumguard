from __future__ import annotations

from pathlib import Path

import pytest

from datumguard.action_paths import (
    ActionPathError,
    resolve_action_input,
    resolve_action_output,
)


def test_action_input_accepts_regular_repository_file(tmp_path: Path) -> None:
    contract = tmp_path / "contracts" / "plan.json"
    contract.parent.mkdir()
    contract.write_text("{}", encoding="utf-8")

    result = resolve_action_input(tmp_path, "contracts/plan.json", allowed_suffixes=[".json"])

    assert result == contract.resolve()


@pytest.mark.parametrize("raw", ["", "../secret.dxf", "folder/../../secret.dxf", "/tmp/x.dxf"])
def test_action_input_rejects_invalid_paths(tmp_path: Path, raw: str) -> None:
    with pytest.raises(ActionPathError):
        resolve_action_input(tmp_path, raw, allowed_suffixes=[".dxf"])


def test_action_input_rejects_unsupported_extension(tmp_path: Path) -> None:
    source = tmp_path / "drawing.exe"
    source.write_bytes(b"not CAD")

    with pytest.raises(ActionPathError, match="unsupported input extension"):
        resolve_action_input(tmp_path, source.name, allowed_suffixes=[".dxf", ".step"])


def test_action_input_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.dxf"
    outside.write_bytes(b"outside")
    link = tmp_path / "linked.dxf"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(ActionPathError, match="escapes"):
        resolve_action_input(tmp_path, link.name, allowed_suffixes=[".dxf"])


def test_action_output_creates_nested_directory(tmp_path: Path) -> None:
    result = resolve_action_output(tmp_path, "results/nested")

    assert result == (tmp_path / "results" / "nested").resolve()
    assert result.is_dir()
    assert (result / ".datumguard-output").is_file()


def test_action_output_clears_only_owned_managed_files(tmp_path: Path) -> None:
    output = resolve_action_output(tmp_path, "results")
    (output / "verified-bundle.zip").write_bytes(b"stale")
    (output / "verification-result.json").write_text("{}", encoding="utf-8")

    preserved = resolve_action_output(tmp_path, "results")

    assert preserved == output
    assert (output / "verified-bundle.zip").is_file()
    assert (output / "verification-result.json").is_file()

    resolved = resolve_action_output(tmp_path, "results", clean=True)

    assert resolved == output
    assert sorted(item.name for item in output.iterdir()) == [".datumguard-output"]


def test_action_output_rejects_unowned_nonempty_directory(tmp_path: Path) -> None:
    output = tmp_path / "results"
    output.mkdir()
    (output / "user-file.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ActionPathError, match="not owned"):
        resolve_action_output(tmp_path, "results")


def test_action_output_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-results"
    outside.mkdir()
    link = tmp_path / "results"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable on this platform")

    with pytest.raises(ActionPathError, match="escapes"):
        resolve_action_output(tmp_path, "results")


def test_action_output_rejects_repository_root(tmp_path: Path) -> None:
    with pytest.raises(ActionPathError, match="repository root"):
        resolve_action_output(tmp_path, ".")

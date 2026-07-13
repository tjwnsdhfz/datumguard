from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath


class ActionPathError(ValueError):
    """Raised when a GitHub Action input escapes its caller-owned workspace."""


_OUTPUT_MARKER = ".datumguard-output"
_MANAGED_OUTPUT_NAMES = frozenset(
    {
        _OUTPUT_MARKER,
        "preview.svg",
        "verification-result.json",
        "verified-bundle.zip",
        "verified.dxf",
        "verified.step",
    }
)


def _relative_path(raw: str) -> Path:
    if not raw or "\n" in raw or "\r" in raw:
        raise ActionPathError("path must be a non-empty single line")
    path = Path(raw)
    posix_path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    is_absolute = (
        path.is_absolute()
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
    )
    if is_absolute or ".." in {*posix_path.parts, *windows_path.parts}:
        raise ActionPathError("path must be repository-relative and cannot contain '..'")
    return path


def _inside_workspace(workspace: Path, candidate: Path) -> Path:
    root = workspace.resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ActionPathError("path escapes the checked-out repository") from exc
    return candidate


def resolve_action_input(workspace: Path, raw: str, *, allowed_suffixes: Sequence[str]) -> Path:
    relative = _relative_path(raw)
    candidate = _inside_workspace(
        workspace,
        (workspace / relative).resolve(strict=True),
    )
    if not candidate.is_file():
        raise ActionPathError("input path is not a regular file")
    normalized_suffixes = {suffix.lower() for suffix in allowed_suffixes}
    if normalized_suffixes and candidate.suffix.lower() not in normalized_suffixes:
        expected = ", ".join(sorted(normalized_suffixes))
        raise ActionPathError(f"unsupported input extension; expected one of: {expected}")
    return candidate


def resolve_action_output(workspace: Path, raw: str, *, clean: bool = False) -> Path:
    relative = _relative_path(raw)
    root = workspace.resolve(strict=True)
    candidate = _inside_workspace(root, (root / relative).resolve(strict=False))
    if candidate == root:
        raise ActionPathError("output directory cannot be the repository root")
    candidate.mkdir(parents=True, exist_ok=True)
    candidate = _inside_workspace(root, candidate.resolve(strict=True))
    if not candidate.is_dir():
        raise ActionPathError("output path is not a directory")

    entries = list(candidate.iterdir())
    marker = candidate / _OUTPUT_MARKER
    if entries and (not marker.is_file() or marker.is_symlink()):
        raise ActionPathError("existing output directory is not owned by DatumGuard")
    unexpected = sorted(entry.name for entry in entries if entry.name not in _MANAGED_OUTPUT_NAMES)
    if unexpected:
        raise ActionPathError(
            "DatumGuard output directory contains unexpected entries: " + ", ".join(unexpected[:5])
        )
    if clean:
        for entry in entries:
            if entry.name == _OUTPUT_MARKER:
                continue
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
            else:
                raise ActionPathError(f"managed output is not a regular file: {entry.name}")
    marker.touch(exist_ok=True)
    return candidate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve a caller-owned Action path safely.")
    parser.add_argument("kind", choices=["input", "output"])
    parser.add_argument("path")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--suffix", action="append", default=[])
    parser.add_argument("--clean", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.kind == "input":
            resolved = resolve_action_input(
                args.workspace,
                args.path,
                allowed_suffixes=args.suffix,
            )
        else:
            resolved = resolve_action_output(args.workspace, args.path, clean=args.clean)
    except (ActionPathError, OSError) as exc:
        print(f"DatumGuard Action path error: {exc}", file=sys.stderr)
        return 1
    print(resolved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import ValidationError

from . import __version__
from .architecture_models import ArchitecturalPlanContract
from .architecture_service import run_architecture_design
from .artifact_service import MAX_ARTIFACT_BYTES, audit_artifact, compare_artifacts
from .frame_cad_service import run_frame_cad_assurance
from .frame_models import StructuralFrameContract
from .models import DesignContract
from .piping_models import PipingPlanContract
from .piping_service import run_piping_design
from .service import run_design
from .solid_models import SolidPartContract
from .solid_service import run_solid_design

MAX_CONTRACT_BYTES = 2 * 1024 * 1024
RESULT_FILENAME = "verification-result.json"
_ENCODED_ARTIFACTS = {
    "bundle_base64": "verified-bundle.zip",
    "dxf_base64": "verified.dxf",
    "step_base64": "verified.step",
}
_MANAGED_OUTPUTS = frozenset({RESULT_FILENAME, "preview.svg", *_ENCODED_ARTIFACTS.values()})


class _ResponseModel(Protocol):
    status: Any
    artifact_hash: str | None

    def model_dump(self, *, mode: str) -> dict[str, Any]: ...


def _existing_file(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"file does not exist: {path}")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datumguard",
        description="Fail-closed CAD contract verification and serialized artifact audit.",
    )
    parser.add_argument("--version", action="version", version=f"DatumGuard {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser(
        "verify",
        help="Generate and independently verify CAD artifacts from a DesignContract JSON file.",
    )
    verify.add_argument("contract", type=_existing_file)
    verify.add_argument("--output", type=Path, default=Path("datumguard-results"))
    verify.add_argument(
        "--auto-repair",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Allow only contract-declared free parameters to be repaired (default: enabled).",
    )

    audit = commands.add_parser(
        "audit",
        help="Read and measure an existing DXF, STEP, or IFC artifact without modifying it.",
    )
    audit.add_argument("artifact", type=_existing_file)
    audit.add_argument("--output", type=Path, default=Path("datumguard-results"))
    audit.add_argument(
        "--allow-review",
        action="store_true",
        help="Return success for needs_confirmation; hard verification failures still fail.",
    )

    compare = commands.add_parser(
        "compare",
        help="Compare serialized DXF, STEP, or IFC artifacts and report measurable drift.",
    )
    compare.add_argument("baseline", type=_existing_file)
    compare.add_argument("candidate", type=_existing_file)
    compare.add_argument("--output", type=Path, default=Path("datumguard-results"))
    compare.add_argument(
        "--allow-review",
        action="store_true",
        help="Return success for needs_confirmation; hard verification failures still fail.",
    )
    return parser


def _read_contract(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) > MAX_CONTRACT_BYTES:
        raise ValueError(f"contract exceeds the {MAX_CONTRACT_BYTES // (1024 * 1024)} MiB limit")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("contract JSON root must be an object")
    return cast(dict[str, Any], value)


def _verify_contract(payload: dict[str, Any], *, auto_repair: bool) -> _ResponseModel:
    design_kind = payload.get("design_kind")
    if design_kind in {None, "plate_panel"}:
        plate_payload = dict(payload)
        plate_payload.pop("design_kind", None)
        return cast(
            _ResponseModel,
            run_design(DesignContract.model_validate(plate_payload), auto_repair=auto_repair),
        )
    if design_kind == "architectural_plan":
        return cast(
            _ResponseModel,
            run_architecture_design(
                ArchitecturalPlanContract.model_validate(payload), auto_repair=auto_repair
            ),
        )
    if design_kind == "piping_plan":
        return cast(_ResponseModel, run_piping_design(PipingPlanContract.model_validate(payload)))
    if design_kind == "structural_frame":
        return cast(
            _ResponseModel,
            run_frame_cad_assurance(StructuralFrameContract.model_validate(payload)),
        )
    if design_kind == "solid_part":
        return cast(_ResponseModel, run_solid_design(SolidPartContract.model_validate(payload)))
    raise ValueError(
        "unsupported design_kind; expected plate_panel, architectural_plan, piping_plan, "
        "structural_frame, or solid_part"
    )


def _read_artifact(path: Path) -> bytes:
    size = path.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise ValueError(f"artifact exceeds the {MAX_ARTIFACT_BYTES // (1024 * 1024)} MiB limit")
    return path.read_bytes()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _prepare_output(output: Path, sources: Sequence[Path]) -> Path:
    output = output.expanduser().resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve(strict=True)
    if not output.is_dir():
        raise ValueError("output path is not a directory")

    source_locations: set[Path] = set()
    for source in sources:
        source_locations.add(source.parent.resolve(strict=True) / source.name)
        source_locations.add(source.resolve(strict=True))
    for filename in _MANAGED_OUTPUTS:
        target = output / filename
        if target in source_locations:
            raise ValueError(f"input file collides with managed output: {filename}")
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.exists():
            raise ValueError(f"managed output path is not a regular file: {filename}")
    return output


def _write_result(response: _ResponseModel, output: Path) -> tuple[dict[str, Any], Path]:
    payload = response.model_dump(mode="json")
    passed = _status_value(response) == "passed"

    for field, filename in _ENCODED_ARTIFACTS.items():
        encoded = payload.pop(field, None)
        if passed and isinstance(encoded, str) and encoded:
            _atomic_write_bytes(output / filename, base64.b64decode(encoded, validate=True))

    preview = payload.pop("preview_svg", None)
    if isinstance(preview, str) and preview:
        _write_text(output / "preview.svg", preview)

    result_path = output / RESULT_FILENAME
    _write_text(result_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload, result_path


def _status_value(response: _ResponseModel) -> str:
    status = response.status
    value = getattr(status, "value", status)
    return str(value)


def _markdown_summary(
    *,
    command: str,
    source_names: Sequence[str],
    status: str,
    artifact_hash: str | None,
    result_path: Path,
    payload: dict[str, Any],
) -> str:
    violation_count = len(payload.get("violations", []))
    issue_count = len(payload.get("issues", []))
    measurements = payload.get("measurements", [])
    return "\n".join(
        [
            "## DatumGuard CAD assurance",
            "",
            "| Field | Result |",
            "| --- | --- |",
            f"| Command | `{command}` |",
            f"| Input | {', '.join(f'`{name}`' for name in source_names)} |",
            f"| Status | **{status}** |",
            f"| Artifact hash | `{artifact_hash or 'not-produced'}` |",
            f"| Measurements | {len(measurements) if isinstance(measurements, list) else 0} |",
            f"| Violations / issues | {violation_count + issue_count} |",
            f"| Result | `{result_path.as_posix()}` |",
            "",
            "> DatumGuard is engineering screening evidence, not safety certification or "
            "construction approval.",
            "",
        ]
    )


def _append_github_file(environment_name: str, content: str) -> None:
    target = os.getenv(environment_name)
    if not target:
        return
    with Path(target).open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _publish_github_metadata(
    *, status: str, response: _ResponseModel, output: Path, result_path: Path, summary: str
) -> None:
    _append_github_file(
        "GITHUB_OUTPUT",
        "\n".join(
            [
                f"status={status}",
                f"artifact_hash={response.artifact_hash or ''}",
                f"result_json={result_path.resolve()}",
                f"output_directory={output.resolve()}",
                "",
            ]
        ),
    )
    _append_github_file("GITHUB_STEP_SUMMARY", summary)


def _complete(
    *,
    command: str,
    source_names: Sequence[str],
    response: _ResponseModel,
    output: Path,
    allow_review: bool = False,
) -> int:
    payload, result_path = _write_result(response, output)
    status = _status_value(response)
    summary = _markdown_summary(
        command=command,
        source_names=source_names,
        status=status,
        artifact_hash=response.artifact_hash,
        result_path=result_path,
        payload=payload,
    )
    _publish_github_metadata(
        status=status,
        response=response,
        output=output,
        result_path=result_path,
        summary=summary,
    )
    print(f"DatumGuard {command}: {status}")
    print(f"Result: {result_path.resolve()}")
    if status in {"passed", "audited"}:
        return 0
    if status == "needs_confirmation" and allow_review:
        return 0
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            contract = cast(Path, args.contract)
            output = _prepare_output(cast(Path, args.output), [contract])
            response = _verify_contract(
                _read_contract(contract), auto_repair=bool(args.auto_repair)
            )
            return _complete(
                command="verify",
                source_names=[contract.name],
                response=response,
                output=output,
            )
        if args.command == "audit":
            artifact = cast(Path, args.artifact)
            output = _prepare_output(cast(Path, args.output), [artifact])
            audit_response = audit_artifact(artifact.name, _read_artifact(artifact))
            return _complete(
                command="audit",
                source_names=[artifact.name],
                response=audit_response,
                output=output,
                allow_review=bool(args.allow_review),
            )
        baseline = cast(Path, args.baseline)
        candidate = cast(Path, args.candidate)
        output = _prepare_output(cast(Path, args.output), [baseline, candidate])
        comparison = compare_artifacts(
            baseline.name,
            _read_artifact(baseline),
            candidate.name,
            _read_artifact(candidate),
        )
        return _complete(
            command="compare",
            source_names=[baseline.name, candidate.name],
            response=comparison,
            output=output,
            allow_review=bool(args.allow_review),
        )
    except ValidationError as exc:
        safe_errors = [
            {
                "type": str(error.get("type", "validation_error")),
                "loc": [str(item)[:80] for item in error.get("loc", ())],
            }
            for error in exc.errors(include_input=False, include_url=False)
        ]
        print(
            "DatumGuard contract validation error: "
            + json.dumps(safe_errors, ensure_ascii=False, separators=(",", ":")),
            file=sys.stderr,
        )
        return 1
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"DatumGuard input error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

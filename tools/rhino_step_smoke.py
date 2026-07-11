"""Generate a verified STEP and prove that Rhino 8 can import and save it as 3DM.

This is a local, allowlisted compatibility smoke test. It is intentionally not
exposed through the hosted API and never accepts arbitrary Rhino commands.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from datumguard.solid_models import SolidPartContract
from datumguard.solid_service import run_solid_design

DEFAULT_RHINO = Path(r"C:\Program Files\Rhino 8\System\Rhino.exe")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a verified STEP, import it in Rhino 8, and save a 3DM proof."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("fixtures/examples/solid_mounting_plate.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("cad_smoke_outputs"))
    parser.add_argument(
        "--rhino",
        type=Path,
        default=Path(os.getenv("DATUMGUARD_RHINO_EXE", str(DEFAULT_RHINO))),
    )
    parser.add_argument("--timeout", type=int, default=90)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--connect-existing",
        dest="connect_existing",
        action="store_true",
        default=True,
        help="Use a running Rhino instance after its StartScriptServer command has been run.",
    )
    mode.add_argument(
        "--launch",
        dest="connect_existing",
        action="store_false",
        help="Launch a clean Rhino process and request its script server (environment-dependent).",
    )
    return parser.parse_args()


def _hidden_startup() -> tuple[int, subprocess.STARTUPINFO | None]:
    if os.name != "nt":
        return 0, None
    # Rhino's scripting server is initialized by the normal desktop event loop;
    # suppressing the window can prevent the startup command from being serviced.
    return subprocess.CREATE_NEW_PROCESS_GROUP, None


def _rhino_code_instances(rhino_code: Path) -> list[dict[str, Any]]:
    completed = subprocess.run(  # noqa: S603 - fixed Rhino installation executable
        [str(rhino_code), "list", "--json"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        return []
    try:
        parsed = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _run_rhino(
    rhino: Path,
    step_path: Path,
    three_dm_path: Path,
    driver_evidence_path: Path,
    timeout: int,
    connect_existing: bool,
) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("The Rhino 8 compatibility smoke currently supports Windows only.")
    if not rhino.is_file():
        raise FileNotFoundError(f"Rhino executable was not found: {rhino}")

    driver = (Path(__file__).parent / "rhino_headless_import.py").resolve()
    rhino_code = rhino.with_name("RhinoCode.exe")
    if not rhino_code.is_file():
        raise FileNotFoundError(f"RhinoCode executable was not found: {rhino_code}")
    current_instances = _rhino_code_instances(rhino_code)
    existing_instances = {str(item.get("pipeId")) for item in current_instances}
    command = [
        str(rhino),
        "/nosplash",
        "/notemplate",
        "/language=1033",
        "/runscript=_StartScriptServer",
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "DATUMGUARD_RHINO_STEP_INPUT": str(step_path),
            "DATUMGUARD_RHINO_3DM_OUTPUT": str(three_dm_path),
            "DATUMGUARD_RHINO_EVIDENCE_OUTPUT": str(driver_evidence_path),
            "DATUMGUARD_RHINO_EXIT": "false" if connect_existing else "true",
        }
    )
    creationflags, startupinfo = _hidden_startup()
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    instance: dict[str, Any] | None = (
        current_instances[0] if connect_existing and current_instances else None
    )
    if connect_existing and instance is None:
        raise RuntimeError(
            "No Rhino script server is available. Open Rhino, run StartScriptServer, and retry."
        )
    if not connect_existing:
        process = subprocess.Popen(  # noqa: S603 - fixed executable and allowlisted arguments
            command,
            cwd=str(three_dm_path.parent),
            env=environment,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
    try:
        deadline = time.monotonic() + timeout
        if not connect_existing:
            while time.monotonic() < deadline:
                candidates = [
                    item
                    for item in _rhino_code_instances(rhino_code)
                    if str(item.get("pipeId")) not in existing_instances
                ]
                if candidates:
                    instance = candidates[0]
                    break
                time.sleep(0.5)
        if instance is None:
            raise RuntimeError(
                "Rhino started but its allowlisted script server did not become ready"
            )

        script_result = subprocess.run(  # noqa: S603 - fixed RhinoCode executable and script
            [
                str(rhino_code),
                "--rhino",
                str(instance["pipeId"]),
                "script",
                str(driver),
            ],
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=max(10, int(deadline - time.monotonic())),
        )
        if script_result.returncode != 0:
            raise RuntimeError(
                "RhinoCode script failed: "
                + (script_result.stderr or script_result.stdout or "unknown error").strip()
            )
        while time.monotonic() < deadline and not driver_evidence_path.is_file():
            time.sleep(0.2)
        return_code = 0
        if process is not None:
            try:
                return_code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                return_code = 0
    except (subprocess.TimeoutExpired, RuntimeError) as exc:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        raise RuntimeError(f"Rhino did not finish the fixed import flow within {timeout}s") from exc

    elapsed = round(time.monotonic() - started, 3)
    if return_code != 0:
        raise RuntimeError(f"Rhino exited with code {return_code}")
    if not driver_evidence_path.is_file():
        raise RuntimeError("Rhino did not create its headless import evidence file")
    driver_evidence = json.loads(driver_evidence_path.read_text(encoding="utf-8"))
    if driver_evidence.get("status") != "passed":
        raise RuntimeError(
            "Rhino headless import failed: "
            + json.dumps(driver_evidence, ensure_ascii=False, sort_keys=True)
        )
    if not three_dm_path.is_file() or three_dm_path.stat().st_size < 128:
        raise RuntimeError("Rhino exited but did not create a usable 3DM file")
    header = three_dm_path.read_bytes()[:64]
    if b"3D Geometry File Format" not in header:
        raise RuntimeError("Rhino output does not contain the expected openNURBS 3DM header")
    return {
        "rhino_executable": str(rhino),
        "rhino_exit_code": return_code,
        "rhino_code_version": subprocess.run(  # noqa: S603 - fixed executable
            [str(rhino_code), "-V"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        ).stdout.strip(),
        "rhino_instance": instance,
        "connected_to_existing_instance": connect_existing,
        "elapsed_seconds": elapsed,
        "three_dm_path": str(three_dm_path),
        "three_dm_bytes": three_dm_path.stat().st_size,
        "three_dm_header_verified": True,
        "headless_import": driver_evidence,
    }


def main() -> int:
    args = _arguments()
    fixture_path = args.fixture.expanduser().resolve()
    output_directory = args.output.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    contract = SolidPartContract.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    result = run_solid_design(contract)
    if result.status != "passed" or not result.step_base64 or not result.artifact_hash:
        raise RuntimeError(
            "DatumGuard STEP generation or independent re-import failed: "
            + json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        )

    suffix = result.artifact_hash.removeprefix("sha256:")[:12]
    step_path = output_directory / f"datumguard-{suffix}.step"
    three_dm_path = output_directory / f"datumguard-{suffix}.3dm"
    evidence_path = output_directory / f"datumguard-{suffix}-rhino-evidence.json"
    driver_evidence_path = output_directory / f"datumguard-{suffix}-rhino-driver.json"
    for generated_path in (three_dm_path, evidence_path, driver_evidence_path):
        if generated_path.is_file():
            generated_path.unlink()
    step_path.write_bytes(base64.b64decode(result.step_base64, validate=True))
    (output_directory / "rhino-smoke-request.json").write_text(
        json.dumps(
            {
                "step_path": str(step_path),
                "three_dm_path": str(three_dm_path),
                "evidence_path": str(driver_evidence_path),
                "exit_rhino": not args.connect_existing,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    rhino_evidence = _run_rhino(
        args.rhino.expanduser().resolve(),
        step_path,
        three_dm_path,
        driver_evidence_path,
        args.timeout,
        args.connect_existing,
    )
    evidence = {
        "status": "passed",
        "purpose": "secondary CAD interoperability smoke; not engineering approval",
        "contract_hash": result.contract_hash,
        "step_artifact_hash": result.artifact_hash,
        "step_independent_reimport": result.summary,
        "step_path": str(step_path),
        **rhino_evidence,
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

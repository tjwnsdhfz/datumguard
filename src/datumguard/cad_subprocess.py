from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CadWorkerFailure(RuntimeError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def apply_worker_limits() -> None:
    """Apply best-effort POSIX limits before importing native CAD parsers."""

    if os.name == "nt":
        return
    try:
        resource: Any = importlib.import_module("resource")
    except ImportError:
        return

    def lower_limit(kind: int, requested: int) -> None:
        try:
            current_soft, current_hard = resource.getrlimit(kind)
            if current_soft == resource.RLIM_INFINITY:
                soft = requested
            else:
                soft = min(current_soft, requested)
            if current_hard == resource.RLIM_INFINITY:
                hard = requested
            else:
                hard = min(current_hard, requested)
            soft = min(soft, hard)
            resource.setrlimit(kind, (soft, hard))
        except (OSError, ValueError):
            return

    # Native OpenCascade/VTK wheels map large shared-library address ranges on Linux.
    # A 1 GiB RLIMIT_AS (and especially a low RLIMIT_NPROC on shared CI hosts) can abort a
    # healthy parser before it reads input. The container/cgroup remains the primary RSS
    # boundary; this higher address-space ceiling is a second, best-effort runaway guard.
    memory_bytes = (
        _env_int("DATUMGUARD_WORKER_MEMORY_MB", 4096, minimum=512, maximum=16384) * 1024 * 1024
    )
    file_bytes = _env_int("DATUMGUARD_WORKER_FILE_MB", 64, minimum=8, maximum=1024) * 1024 * 1024
    cpu_seconds = _env_int("DATUMGUARD_WORKER_CPU_SECONDS", 45, minimum=5, maximum=300)
    lower_limit(resource.RLIMIT_AS, memory_bytes)
    lower_limit(resource.RLIMIT_FSIZE, file_bytes)
    lower_limit(resource.RLIMIT_CPU, cpu_seconds)
    lower_limit(resource.RLIMIT_NOFILE, 128)


def _worker_environment() -> dict[str, str]:
    sensitive_markers = ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "API_KEYS")
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in sensitive_markers)
    }


def _run_worker(
    payload: dict[str, Any],
    *,
    command: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    max_input_bytes = (
        _env_int("DATUMGUARD_WORKER_INPUT_MB", 64, minimum=8, maximum=256) * 1024 * 1024
    )
    if len(encoded) > max_input_bytes:
        raise CadWorkerFailure(
            "Isolated CAD worker input exceeded its limit.",
            {"input_limit_bytes": max_input_bytes},
        )
    creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        completed = subprocess.run(
            command,
            input=encoded,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            creationflags=creation_flags,
            start_new_session=os.name != "nt",
            env=_worker_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise CadWorkerFailure(
            "Isolated CAD worker timed out.",
            {"timeout_seconds": timeout_seconds, "failure": "timeout"},
        ) from exc
    if completed.returncode != 0:
        raise CadWorkerFailure(
            "Isolated CAD worker failed.",
            {"return_code": completed.returncode, "failure": "worker_exit"},
        )
    max_output_bytes = (
        _env_int("DATUMGUARD_WORKER_OUTPUT_MB", 8, minimum=1, maximum=64) * 1024 * 1024
    )
    if len(completed.stdout) > max_output_bytes:
        raise CadWorkerFailure(
            "Isolated CAD worker output exceeded its limit.",
            {"output_limit_bytes": max_output_bytes, "failure": "output_limit"},
        )
    try:
        result = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CadWorkerFailure(
            "Isolated CAD worker returned invalid JSON.",
            {"stdout_bytes": len(completed.stdout), "failure": "invalid_output"},
        ) from exc
    if not isinstance(result, dict):
        raise CadWorkerFailure(
            "Isolated CAD worker returned a non-object result.",
            {"failure": "invalid_output"},
        )
    return result


def run_cad_worker(
    payload: dict[str, Any],
    *,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    timeout = timeout_seconds or _env_int(
        "DATUMGUARD_CAD_WORKER_TIMEOUT_SECONDS", 90, minimum=5, maximum=300
    )
    command = [
        sys.executable,
        "-c",
        (
            "from datumguard.cad_subprocess import apply_worker_limits;"
            "apply_worker_limits();"
            "from datumguard.cad_worker import main;main()"
        ),
    ]
    return _run_worker(payload, command=command, timeout_seconds=timeout)


def run_parser_worker(
    payload: dict[str, Any],
    *,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    timeout = timeout_seconds or _env_int(
        "DATUMGUARD_PARSER_WORKER_TIMEOUT_SECONDS", 45, minimum=5, maximum=300
    )
    command = [
        sys.executable,
        "-c",
        (
            "from datumguard.cad_subprocess import apply_worker_limits;"
            "apply_worker_limits();"
            "from datumguard.artifact_service import parser_worker_main;parser_worker_main()"
        ),
    ]
    return _run_worker(payload, command=command, timeout_seconds=timeout)


__all__ = [
    "CadWorkerFailure",
    "apply_worker_limits",
    "run_cad_worker",
    "run_parser_worker",
]

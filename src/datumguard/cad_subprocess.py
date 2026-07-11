from __future__ import annotations

import json
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


def run_cad_worker(payload: dict[str, Any], *, timeout_seconds: int = 90) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "datumguard.cad_worker"],
            input=encoded,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            creationflags=creation_flags,
        )
    except subprocess.TimeoutExpired as exc:
        raise CadWorkerFailure(
            "OpenCascade worker timed out.",
            {"timeout_seconds": timeout_seconds},
        ) from exc
    if completed.returncode != 0:
        raise CadWorkerFailure(
            "OpenCascade worker failed.",
            {
                "return_code": completed.returncode,
                "stderr": completed.stderr.decode("utf-8", errors="replace")[-2000:],
            },
        )
    try:
        result = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CadWorkerFailure(
            "OpenCascade worker returned invalid JSON.",
            {"stdout_bytes": len(completed.stdout)},
        ) from exc
    if not isinstance(result, dict):
        raise CadWorkerFailure("OpenCascade worker returned a non-object result.", {})
    return result

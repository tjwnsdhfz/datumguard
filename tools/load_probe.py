"""Small, guarded DatumGuard load probe for localhost and explicit staging origins.

This is intentionally not a production load-testing tool. It never accepts the known
DatumGuard production hosts, and non-local targets require an exact host acknowledgement.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KNOWN_PRODUCTION_HOSTS = {
    "datumguard-api.onrender.com",
    "datumguard-tjwnsdhfz.vercel.app",
}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
CONCURRENCY_LEVELS = (1, 2, 5, 10)


@dataclass(frozen=True)
class Attempt:
    status: int
    elapsed_ms: float
    response_bytes: int
    ok: bool
    error_kind: str | None = None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--scenario",
        choices=("health", "architecture", "solid"),
        default="architecture",
    )
    parser.add_argument(
        "--concurrency",
        action="append",
        type=int,
        choices=CONCURRENCY_LEVELS,
        help="repeat to select levels; default runs 1, 2, 5, and 10",
    )
    parser.add_argument("--requests-per-level", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--staging-host",
        help="exact non-production hostname; required with --acknowledge-staging",
    )
    parser.add_argument(
        "--acknowledge-staging",
        action="store_true",
        help="confirm the non-local target is isolated staging and authorized for load",
    )
    return parser


def _validate_target(args: argparse.Namespace) -> str:
    value = args.base_url.rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("--base-url must be an http(s) origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("--base-url must not contain credentials, query, or fragment")
    if parsed.path:
        raise ValueError("--base-url must be an origin without a path")
    if host in KNOWN_PRODUCTION_HOSTS:
        raise ValueError(f"production target is permanently blocked: {host}")
    if host not in LOCAL_HOSTS:
        expected = (args.staging_host or "").lower()
        if not args.acknowledge_staging or expected != host:
            raise ValueError(
                "non-local probes require --staging-host <exact-host> and --acknowledge-staging"
            )
    return value


def _scenario(args: argparse.Namespace, base_url: str) -> tuple[str, str, bytes | None]:
    if args.scenario == "health":
        return "GET", f"{base_url}/api/v1/health", None
    if args.scenario == "architecture":
        fixture = ROOT / "fixtures" / "examples" / "architecture_four_room.json"
        return "POST", f"{base_url}/api/v1/architecture/designs/run", fixture.read_bytes()
    fixture = ROOT / "fixtures" / "examples" / "solid_mounting_plate.json"
    return "POST", f"{base_url}/api/v1/solid/designs/run", fixture.read_bytes()


def _is_valid_payload(scenario: str, body: bytes) -> bool:
    try:
        payload: Any = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if scenario == "health":
        return payload.get("status") == "ok" and bool(payload.get("version"))
    if payload.get("status") != "passed" or not payload.get("bundle_base64"):
        return False
    if scenario == "solid" and not payload.get("step_base64"):
        return False
    return True


def _attempt(
    scenario: str,
    method: str,
    url: str,
    body: bytes | None,
    timeout: float,
) -> Attempt:
    headers = {
        "Accept": "application/json",
        "User-Agent": "datumguard-load-probe/1.0 staging-only",
        "X-DatumGuard-Probe": "staging-only",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            status = int(response.status)
        valid = 200 <= status < 300 and _is_valid_payload(scenario, payload)
        return Attempt(
            status=status,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            response_bytes=len(payload),
            ok=valid,
            error_kind=None if valid else "sentinel",
        )
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return Attempt(
            status=int(exc.code),
            elapsed_ms=(time.perf_counter() - started) * 1000,
            response_bytes=len(payload),
            ok=False,
            error_kind="http",
        )
    except (OSError, TimeoutError, urllib.error.URLError):
        return Attempt(
            status=0,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            response_bytes=0,
            ok=False,
            error_kind="network",
        )


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil((percentile / 100) * len(ordered)) - 1)
    return ordered[index]


def _summarize(concurrency: int, attempts: list[Attempt]) -> dict[str, Any]:
    latencies = [item.elapsed_ms for item in attempts]
    failures = sum(not item.ok for item in attempts)
    return {
        "concurrency": concurrency,
        "requests": len(attempts),
        "successes": len(attempts) - failures,
        "errors": failures,
        "error_rate": failures / len(attempts),
        "http_429": sum(item.status == 429 for item in attempts),
        "p50_ms": round(_percentile(latencies, 50), 1),
        "p95_ms": round(_percentile(latencies, 95), 1),
        "p99_ms": round(_percentile(latencies, 99), 1),
        "mean_response_bytes": round(
            sum(item.response_bytes for item in attempts) / len(attempts),
            1,
        ),
        "status_counts": {
            str(status): sum(item.status == status for item in attempts)
            for status in sorted({item.status for item in attempts})
        },
        "error_kinds": {
            kind: sum(item.error_kind == kind for item in attempts)
            for kind in sorted({item.error_kind for item in attempts if item.error_kind})
        },
    }


def _print_table(rows: list[dict[str, Any]]) -> None:
    print("conc  req  ok  err  err%   429    p50ms    p95ms    p99ms   mean-bytes")
    for row in rows:
        print(
            f"{row['concurrency']:>4} {row['requests']:>4} {row['successes']:>3} "
            f"{row['errors']:>4} {row['error_rate'] * 100:>5.1f} "
            f"{row['http_429']:>5} {row['p50_ms']:>8.1f} {row['p95_ms']:>8.1f} "
            f"{row['p99_ms']:>8.1f} {row['mean_response_bytes']:>12.1f}"
        )


def main() -> int:
    args = _parser().parse_args()
    try:
        base_url = _validate_target(args)
    except ValueError as exc:
        print(f"safety guard: {exc}", file=sys.stderr)
        return 2
    if args.requests_per_level < 1:
        print("--requests-per-level must be positive", file=sys.stderr)
        return 2
    if not 0 <= args.max_error_rate <= 1:
        print("--max-error-rate must be between 0 and 1", file=sys.stderr)
        return 2

    levels = list(dict.fromkeys(args.concurrency or CONCURRENCY_LEVELS))
    method, url, body = _scenario(args, base_url)
    rows: list[dict[str, Any]] = []
    raw: dict[str, list[dict[str, Any]]] = {}
    for index, concurrency in enumerate(levels):
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(_attempt, args.scenario, method, url, body, args.timeout)
                for _ in range(args.requests_per_level)
            ]
            attempts = [future.result() for future in concurrent.futures.as_completed(futures)]
        rows.append(_summarize(concurrency, attempts))
        raw[str(concurrency)] = [asdict(item) for item in attempts]
        if index + 1 < len(levels) and args.pause_seconds:
            time.sleep(args.pause_seconds)

    report = {
        "target": base_url,
        "scenario": args.scenario,
        "production_guard": True,
        "summaries": rows,
        "attempts": raw,
    }
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"target={base_url} scenario={args.scenario} (staging/local only)")
        _print_table(rows)
    return int(any(row["error_rate"] > args.max_error_rate for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())

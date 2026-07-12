from __future__ import annotations

import asyncio
import contextvars
import hmac
import ipaddress
import json
import logging
import math
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar, cast

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_MAX_BODY_BYTES = 48 * 1024 * 1024
DEFAULT_MAX_UPLOAD_TOTAL_BYTES = 40 * 1024 * 1024
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_CF_RAY_PATTERN = re.compile(r"^[0-9a-fA-F]{16,32}-[A-Za-z0-9]{3,8}$")
_REQUEST_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "datumguard_request_id",
    default=None,
)

HEAVY_PATHS = frozenset(
    {
        "/api/v1/designs/run",
        "/api/v1/architecture/designs/run",
        "/api/v1/piping/designs/run",
        "/api/v1/solid/designs/run",
        "/api/v1/artifacts/audit",
        "/api/v1/artifacts/compare",
        "/api/v1/openbim/evidence/run",
        "/api/v1/drawings/generate",
        "/api/v1/drawings/verify",
        "/api/v1/exports",
    }
)
_KNOWN_PATHS = HEAVY_PATHS | {
    "/",
    "/docs",
    "/redoc",
    "/api/v1/openapi.json",
    "/api/v1/health",
    "/api/v1/live",
    "/api/v1/ready",
    "/api/v1/metrics",
    "/api/v1/domains",
    "/api/v1/contracts/draft",
    "/api/v1/contracts/validate",
    "/api/v1/architecture/contracts/validate",
    "/api/v1/piping/contracts/validate",
    "/api/v1/architecture/schema",
    "/api/v1/piping/schema",
    "/api/v1/repairs/propose",
    "/api/v1/repairs/apply",
    "/api/v1/drawings/compare",
    "/api/v1/rhino/preview",
}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def current_request_id() -> str:
    return _REQUEST_ID.get() or str(uuid.uuid4())


def _safe_request_id(value: str | None) -> str:
    if value and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid.uuid4())


def _normalize_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        return None


def _normalized_route(path: str) -> str:
    if path.startswith("/api/v1/schema/"):
        return "/api/v1/schema/*"
    if path in _KNOWN_PATHS:
        return path
    return "/other"


def make_error_content(
    request_id: str,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "failed_verification",
        "contract_hash": "sha256:unavailable",
        "artifact_hash": None,
        "measurements": [],
        "violations": [],
        "evidence": [],
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "correlation_id": request_id,
        },
    }


@dataclass
class _RateBucket:
    window_started: float
    count: int
    last_seen: float


class BoundedRateLimiter:
    def __init__(
        self,
        *,
        window_seconds: int,
        ttl_seconds: int,
        max_keys: int,
    ) -> None:
        self.window_seconds = window_seconds
        self.ttl_seconds = max(ttl_seconds, window_seconds)
        self.max_keys = max_keys
        self._buckets: OrderedDict[tuple[str, str, str], _RateBucket] = OrderedDict()
        self._lock = threading.Lock()
        self._last_cleanup = 0.0

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < min(30.0, self.ttl_seconds / 2):
            return
        expired = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.last_seen >= self.ttl_seconds
        ]
        for key in expired:
            self._buckets.pop(key, None)
        self._last_cleanup = now

    def check(self, key: tuple[str, str, str], *, limit: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                while len(self._buckets) >= self.max_keys:
                    self._buckets.popitem(last=False)
                self._buckets[key] = _RateBucket(now, 1, now)
                return True, 0
            self._buckets.move_to_end(key)
            bucket.last_seen = now
            elapsed = now - bucket.window_started
            if elapsed >= self.window_seconds:
                bucket.window_started = now
                bucket.count = 1
                return True, 0
            if bucket.count >= limit:
                retry_after = max(1, math.ceil(self.window_seconds - elapsed))
                return False, retry_after
            bucket.count += 1
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
            self._last_cleanup = 0.0


@dataclass(frozen=True)
class GateSnapshot:
    limit: int
    active: int
    waiting: int
    max_waiters: int
    wait_timeout_seconds: float

    @property
    def ready(self) -> bool:
        return self.active < self.limit and self.waiting < self.max_waiters


class GateLease:
    def __init__(self, gate: HeavyOperationGate, wait_ms: float) -> None:
        self._gate = gate
        self.wait_ms = wait_ms
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._gate.release()


class HeavyOperationGate:
    def __init__(self, *, limit: int, max_waiters: int, wait_timeout_seconds: float) -> None:
        self.limit = limit
        self.max_waiters = max_waiters
        self.wait_timeout_seconds = wait_timeout_seconds
        self._semaphore = asyncio.Semaphore(limit)
        self._active = 0
        self._waiting = 0
        self._state_lock = threading.Lock()

    async def acquire(self) -> GateLease | None:
        with self._state_lock:
            if self._active >= self.limit and self._waiting >= self.max_waiters:
                return None
            self._waiting += 1
        started = time.monotonic()
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.wait_timeout_seconds,
            )
        except TimeoutError:
            with self._state_lock:
                self._waiting -= 1
            return None
        with self._state_lock:
            self._waiting -= 1
            self._active += 1
        return GateLease(self, (time.monotonic() - started) * 1000)

    def release(self) -> None:
        with self._state_lock:
            self._active = max(0, self._active - 1)
        self._semaphore.release()

    def snapshot(self) -> GateSnapshot:
        with self._state_lock:
            return GateSnapshot(
                limit=self.limit,
                active=self._active,
                waiting=self._waiting,
                max_waiters=self.max_waiters,
                wait_timeout_seconds=self.wait_timeout_seconds,
            )


_DURATION_BUCKETS_MS = (50, 100, 250, 500, 1000, 2000, 5000, 10000, 30000, 90000)


@dataclass
class _RouteMetric:
    request_count: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    error_count: int = 0
    rate_limited: int = 0
    duration_total_ms: float = 0.0
    duration_max_ms: float = 0.0
    duration_buckets: dict[str, int] = field(default_factory=dict)


class BoundedMetrics:
    def __init__(self, *, max_routes: int = 64) -> None:
        self.max_routes = max_routes
        self._routes: OrderedDict[str, _RouteMetric] = OrderedDict()
        self._lock = threading.Lock()

    def record(
        self,
        route: str,
        *,
        status: int,
        duration_ms: float,
        rate_limited: bool = False,
    ) -> None:
        route = _normalized_route(route)
        with self._lock:
            metric = self._routes.get(route)
            if metric is None:
                while len(self._routes) >= self.max_routes:
                    self._routes.popitem(last=False)
                metric = _RouteMetric()
                self._routes[route] = metric
            self._routes.move_to_end(route)
            metric.request_count += 1
            status_key = str(status)
            metric.status_counts[status_key] = metric.status_counts.get(status_key, 0) + 1
            if status >= 400:
                metric.error_count += 1
            if rate_limited:
                metric.rate_limited += 1
            metric.duration_total_ms += duration_ms
            metric.duration_max_ms = max(metric.duration_max_ms, duration_ms)
            for bound in _DURATION_BUCKETS_MS:
                if duration_ms <= bound:
                    key = f"le_{bound}"
                    metric.duration_buckets[key] = metric.duration_buckets.get(key, 0) + 1
                    break
            else:
                metric.duration_buckets["gt_90000"] = metric.duration_buckets.get("gt_90000", 0) + 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            routes: dict[str, Any] = {}
            for route, metric in self._routes.items():
                average = (
                    metric.duration_total_ms / metric.request_count if metric.request_count else 0.0
                )
                routes[route] = {
                    "request_count": metric.request_count,
                    "status": dict(sorted(metric.status_counts.items())),
                    "errors": metric.error_count,
                    "rate_limited": metric.rate_limited,
                    "duration_ms": {
                        "average": round(average, 3),
                        "maximum": round(metric.duration_max_ms, 3),
                        "buckets": dict(sorted(metric.duration_buckets.items())),
                    },
                }
            return {"routes": routes}


T = TypeVar("T")


@dataclass
class _Flight[T]:
    event: threading.Event = field(default_factory=threading.Event)
    result: T | None = None
    error: Exception | None = None


class BoundedSingleFlight[T]:
    """Coalesce only concurrent duplicates; completed values are never cached."""

    def __init__(self, *, max_flights: int, wait_timeout_seconds: float) -> None:
        self.max_flights = max_flights
        self.wait_timeout_seconds = wait_timeout_seconds
        self._flights: dict[str, _Flight[T]] = {}
        self._lock = threading.Lock()

    def run(self, key: str, operation: Callable[[], T]) -> T:
        with self._lock:
            flight = self._flights.get(key)
            owner = flight is None and len(self._flights) < self.max_flights
            if owner:
                flight = _Flight()
                self._flights[key] = flight
        if flight is None:
            return operation()
        if owner:
            try:
                flight.result = operation()
            except Exception as exc:
                flight.error = exc
            finally:
                flight.event.set()
                with self._lock:
                    self._flights.pop(key, None)
        elif not flight.event.wait(self.wait_timeout_seconds):
            return operation()
        if flight.error is not None:
            raise flight.error
        return cast(T, flight.result)


def _configured_api_keys() -> tuple[str, ...]:
    return tuple(
        item.strip() for item in os.getenv("DATUMGUARD_API_KEYS", "").split(",") if item.strip()
    )


class OperationalControls:
    def __init__(self) -> None:
        self.metrics = BoundedMetrics()
        self.configure_from_env(reset_metrics=False)

    def configure_from_env(self, *, reset_metrics: bool = True) -> None:
        self.max_body_bytes = _env_int(
            "DATUMGUARD_MAX_BODY_BYTES",
            DEFAULT_MAX_BODY_BYTES,
            minimum=1024,
            maximum=128 * 1024 * 1024,
        )
        self.max_upload_total_bytes = _env_int(
            "DATUMGUARD_MAX_UPLOAD_TOTAL_BYTES",
            DEFAULT_MAX_UPLOAD_TOTAL_BYTES,
            minimum=1024,
            maximum=self.max_body_bytes,
        )
        self.rate_limit_enabled = env_flag("DATUMGUARD_RATE_LIMIT_ENABLED", True)
        self.rate_window_seconds = _env_int(
            "DATUMGUARD_RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1, maximum=3600
        )
        self.anon_limit = _env_int(
            "DATUMGUARD_ANON_RATE_LIMIT_PER_MINUTE", 30, minimum=1, maximum=10000
        )
        self.anon_heavy_limit = _env_int(
            "DATUMGUARD_ANON_HEAVY_RATE_LIMIT_PER_MINUTE", 6, minimum=1, maximum=10000
        )
        self.auth_limit = _env_int(
            "DATUMGUARD_AUTH_RATE_LIMIT_PER_MINUTE", 120, minimum=1, maximum=100000
        )
        self.auth_heavy_limit = _env_int(
            "DATUMGUARD_AUTH_HEAVY_RATE_LIMIT_PER_MINUTE", 30, minimum=1, maximum=100000
        )
        self.api_keys = _configured_api_keys()
        self.trust_cf_connecting_ip = env_flag(
            "DATUMGUARD_TRUST_CF_CONNECTING_IP",
            True,
        )
        self.rate_limiter = BoundedRateLimiter(
            window_seconds=self.rate_window_seconds,
            ttl_seconds=_env_int(
                "DATUMGUARD_RATE_LIMIT_TTL_SECONDS", 600, minimum=60, maximum=86400
            ),
            max_keys=_env_int(
                "DATUMGUARD_RATE_LIMIT_MAX_KEYS", 10000, minimum=100, maximum=1000000
            ),
        )
        self.gate = HeavyOperationGate(
            limit=_env_int("DATUMGUARD_HEAVY_CONCURRENCY", 2, minimum=1, maximum=64),
            max_waiters=_env_int("DATUMGUARD_HEAVY_MAX_WAITERS", 8, minimum=1, maximum=1000),
            wait_timeout_seconds=_env_float(
                "DATUMGUARD_HEAVY_WAIT_TIMEOUT_SECONDS",
                2.0,
                minimum=0.05,
                maximum=120.0,
            ),
        )
        self.solid_enabled = env_flag("DATUMGUARD_ENABLE_SOLID", True)
        self.artifact_lab_enabled = env_flag("DATUMGUARD_ENABLE_ARTIFACT_LAB", True)
        self.openbim_enabled = env_flag("DATUMGUARD_ENABLE_OPENBIM", True)
        if reset_metrics:
            self.metrics = BoundedMetrics()

    def resolve_client_ip(self, headers: Headers, scope: Scope) -> str:
        if self.trust_cf_connecting_ip:
            cf_ray = headers.get("cf-ray")
            edge_ip = _normalize_ip(headers.get("cf-connecting-ip"))
            if cf_ray and _CF_RAY_PATTERN.fullmatch(cf_ray) and edge_ip:
                return edge_ip
        client = scope.get("client")
        if client:
            client_ip = _normalize_ip(str(client[0]))
            if client_ip:
                return client_ip
        return "unknown"

    def authenticate(self, headers: Headers) -> tuple[bool, bool]:
        if not self.api_keys:
            return False, False
        provided = headers.get("x-api-key", "").strip()
        authorization = headers.get("authorization", "").strip()
        if not provided and authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()
        if not provided:
            return False, False
        valid = any(hmac.compare_digest(provided, configured) for configured in self.api_keys)
        return valid, not valid

    def rate_limit(
        self,
        *,
        client_ip: str,
        route: str,
        authenticated: bool,
        heavy: bool,
    ) -> tuple[bool, int]:
        if not self.rate_limit_enabled:
            return True, 0
        tier = "authenticated" if authenticated else "anonymous"
        if authenticated:
            limit = self.auth_heavy_limit if heavy else self.auth_limit
        else:
            limit = self.anon_heavy_limit if heavy else self.anon_limit
        return self.rate_limiter.check((client_ip, route, tier), limit=limit)

    def disabled_capability(self, path: str) -> str | None:
        if path == "/api/v1/solid/designs/run" and not self.solid_enabled:
            return "solid"
        if path in {"/api/v1/artifacts/audit", "/api/v1/artifacts/compare"}:
            return None if self.artifact_lab_enabled else "artifact_lab"
        if path == "/api/v1/openbim/evidence/run" and not self.openbim_enabled:
            return "openbim"
        return None

    def metrics_snapshot(self) -> dict[str, Any]:
        snapshot = self.metrics.snapshot()
        gate = self.gate.snapshot()
        snapshot["heavy"] = {
            "limit": gate.limit,
            "active": gate.active,
            "waiting": gate.waiting,
            "max_waiters": gate.max_waiters,
        }
        return snapshot


OPERATIONS = OperationalControls()
ARTIFACT_SINGLE_FLIGHT: BoundedSingleFlight[Any] = BoundedSingleFlight(
    max_flights=_env_int("DATUMGUARD_SINGLE_FLIGHT_MAX_KEYS", 32, minimum=1, maximum=1024),
    wait_timeout_seconds=_env_float(
        "DATUMGUARD_SINGLE_FLIGHT_WAIT_SECONDS",
        120.0,
        minimum=1.0,
        maximum=300.0,
    ),
)


def reset_operational_state_for_tests() -> None:
    OPERATIONS.configure_from_env(reset_metrics=True)


def _logger() -> logging.Logger:
    logger = logging.getLogger("datumguard.operations")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


class OperationalMiddleware:
    def __init__(self, app: ASGIApp, *, controls: OperationalControls) -> None:
        self.app = app
        self.controls = controls
        self.logger = _logger()

    async def _respond(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        request_id: str,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        headers = {"X-Request-ID": request_id}
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
        response = JSONResponse(
            status_code=status_code,
            content=make_error_content(
                request_id,
                code=code,
                message=message,
                details=details,
            ),
            headers=headers,
        )
        await response(scope, receive, send)

    def _record(
        self,
        *,
        route: str,
        request_id: str,
        cf_ray: str | None,
        status: int,
        started: float,
        heavy: bool,
        wait_ms: float,
        rate_limited: bool = False,
    ) -> None:
        duration_ms = (time.monotonic() - started) * 1000
        self.controls.metrics.record(
            route,
            status=status,
            duration_ms=duration_ms,
            rate_limited=rate_limited,
        )
        gate = self.controls.gate.snapshot()
        payload = {
            "event": "http_request",
            "request_id": request_id,
            "cf_ray": cf_ray,
            "route": _normalized_route(route),
            "status": status,
            "duration_ms": round(duration_ms, 3),
            "queue": {
                "heavy": heavy,
                "active": gate.active,
                "waiting": gate.waiting,
                "wait_ms": round(wait_ms, 3),
            },
        }
        self.logger.info(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        path = str(scope.get("path", "/"))
        route = _normalized_route(path)
        request_id = _safe_request_id(headers.get("x-request-id"))
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = _REQUEST_ID.set(request_id)
        started = time.monotonic()
        raw_cf_ray = headers.get("cf-ray")
        cf_ray = raw_cf_ray if raw_cf_ray and _CF_RAY_PATTERN.fullmatch(raw_cf_ray) else None
        heavy = path in HEAVY_PATHS
        wait_ms = 0.0
        lease: GateLease | None = None
        status_code = 500
        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                response_headers = [
                    header
                    for header in message.get("headers", [])
                    if header[0].lower() != b"x-request-id"
                ]
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        received_bytes = 0

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                body = cast(bytes, message.get("body", b""))
                received_bytes += len(body)
                if received_bytes > self.controls.max_body_bytes:
                    raise _RequestBodyTooLarge
            return message

        try:
            content_length = headers.get("content-length")
            if content_length:
                try:
                    declared_length = int(content_length)
                except ValueError:
                    declared_length = self.controls.max_body_bytes + 1
                if declared_length > self.controls.max_body_bytes:
                    status_code = 413
                    await self._respond(
                        scope,
                        receive,
                        tracked_send,
                        status_code=413,
                        request_id=request_id,
                        code="DG_INPUT_INVALID",
                        message="요청 본문이 서버 제한을 초과했습니다.",
                        details={"max_bytes": self.controls.max_body_bytes},
                    )
                    return

            authenticated, invalid_key = self.controls.authenticate(headers)
            method = str(scope.get("method", "GET")).upper()
            if method == "POST":
                client_ip = self.controls.resolve_client_ip(headers, scope)
                allowed, retry_after = self.controls.rate_limit(
                    client_ip=client_ip,
                    route=route,
                    authenticated=authenticated,
                    heavy=heavy,
                )
                if not allowed:
                    status_code = 429
                    await self._respond(
                        scope,
                        receive,
                        tracked_send,
                        status_code=429,
                        request_id=request_id,
                        code="DG_RATE_LIMITED",
                        message="요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
                        retry_after=retry_after,
                    )
                    self._record(
                        route=route,
                        request_id=request_id,
                        cf_ray=cf_ray,
                        status=status_code,
                        started=started,
                        heavy=heavy,
                        wait_ms=wait_ms,
                        rate_limited=True,
                    )
                    return

            if invalid_key:
                status_code = 401
                await self._respond(
                    scope,
                    receive,
                    tracked_send,
                    status_code=401,
                    request_id=request_id,
                    code="DG_AUTH_INVALID",
                    message="제공한 API key가 유효하지 않습니다.",
                )
                return

            capability = self.controls.disabled_capability(path)
            if capability:
                status_code = 503
                await self._respond(
                    scope,
                    receive,
                    tracked_send,
                    status_code=503,
                    request_id=request_id,
                    code="DG_CAPABILITY_DISABLED",
                    message="요청한 CAD 기능이 이 배포에서 비활성화되어 있습니다.",
                    details={"capability": capability},
                    retry_after=60,
                )
                return

            if heavy:
                lease = await self.controls.gate.acquire()
                if lease is None:
                    status_code = 503
                    await self._respond(
                        scope,
                        receive,
                        tracked_send,
                        status_code=503,
                        request_id=request_id,
                        code="DG_SERVER_BUSY",
                        message="CAD 처리 대기열이 가득 찼습니다. 잠시 후 다시 시도해 주세요.",
                        details={"retryable": True},
                        retry_after=max(1, math.ceil(self.controls.gate.wait_timeout_seconds)),
                    )
                    return
                wait_ms = lease.wait_ms

            downstream_receive = limited_receive
            if method in {"POST", "PUT", "PATCH"} and not content_length:
                buffered_messages: list[Message] = []
                while True:
                    message = await limited_receive()
                    buffered_messages.append(message)
                    if message["type"] != "http.request" or not message.get("more_body", False):
                        break
                buffered_index = 0

                async def replay_receive() -> Message:
                    nonlocal buffered_index
                    if buffered_index < len(buffered_messages):
                        message = buffered_messages[buffered_index]
                        buffered_index += 1
                        return message
                    return {"type": "http.request", "body": b"", "more_body": False}

                downstream_receive = replay_receive

            await self.app(scope, downstream_receive, tracked_send)
        except _RequestBodyTooLarge:
            status_code = 413
            if not response_started:
                await self._respond(
                    scope,
                    receive,
                    tracked_send,
                    status_code=413,
                    request_id=request_id,
                    code="DG_INPUT_INVALID",
                    message="요청 본문이 서버 제한을 초과했습니다.",
                    details={"max_bytes": self.controls.max_body_bytes},
                )
        except Exception as exc:
            status_code = 500
            self.logger.error(
                json.dumps(
                    {
                        "event": "unhandled_exception",
                        "request_id": request_id,
                        "route": route,
                        "error_code": "DG_INTERNAL_ERROR",
                        "exception_type": type(exc).__name__,
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
            )
            if not response_started:
                await self._respond(
                    scope,
                    receive,
                    tracked_send,
                    status_code=500,
                    request_id=request_id,
                    code="DG_INTERNAL_ERROR",
                    message="요청을 안전하게 완료하지 못했습니다.",
                )
            else:
                raise
        finally:
            if lease is not None:
                lease.release()
            if status_code != 429:
                self._record(
                    route=route,
                    request_id=request_id,
                    cf_ray=cf_ray,
                    status=status_code,
                    started=started,
                    heavy=heavy,
                    wait_ms=wait_ms,
                )
            _REQUEST_ID.reset(token)


class _RequestBodyTooLarge(Exception):
    pass


__all__ = [
    "ARTIFACT_SINGLE_FLIGHT",
    "DEFAULT_MAX_BODY_BYTES",
    "HEAVY_PATHS",
    "OPERATIONS",
    "OperationalMiddleware",
    "current_request_id",
    "env_flag",
    "make_error_content",
    "reset_operational_state_for_tests",
]

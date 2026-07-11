const DEFAULT_API_URL = "http://localhost:8000";

export const API_URL = (process.env.NEXT_PUBLIC_DATUMGUARD_API_URL || DEFAULT_API_URL).replace(
  /\/$/,
  "",
);

export type BackendDomainId =
  | "architecture"
  | "plant_piping"
  | "mechanical_ship_plate"
  | "solid_part"
  | "artifact_lab";

type ApiErrorKind = "aborted" | "http" | "invalid-response" | "network" | "timeout";

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    correlation_id?: string;
  } | null;
};

type RequestOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
};

export class ApiClientError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly retryAfterMs?: number;
  readonly correlationId?: string;
  readonly code?: string;

  constructor(
    message: string,
    options: {
      kind: ApiErrorKind;
      status?: number;
      retryAfterMs?: number;
      correlationId?: string;
      code?: string;
      cause?: unknown;
    },
  ) {
    super(message, { cause: options.cause });
    this.name = "ApiClientError";
    this.kind = options.kind;
    this.status = options.status;
    this.retryAfterMs = options.retryAfterMs;
    this.correlationId = options.correlationId;
    this.code = options.code;
  }
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000;
  const date = Date.parse(value);
  if (Number.isNaN(date)) return undefined;
  return Math.max(0, date - Date.now());
}

function errorEnvelope(value: unknown): ErrorEnvelope | null {
  if (!value || typeof value !== "object") return null;
  return value as ErrorEnvelope;
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
  { signal, timeoutMs = 60_000 }: RequestOptions = {},
): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal?.aborted) abortFromCaller();
  else signal?.addEventListener("abort", abortFromCaller, { once: true });

  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort("request-timeout");
  }, timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: { Accept: "application/json", ...init.headers },
      signal: controller.signal,
    });
  } catch (reason) {
    if (timedOut) {
      throw new ApiClientError(`요청이 ${Math.ceil(timeoutMs / 1000)}초 안에 완료되지 않았습니다.`, {
        kind: "timeout",
        cause: reason,
      });
    }
    if (signal?.aborted) {
      throw new ApiClientError("요청이 취소되었습니다.", { kind: "aborted", cause: reason });
    }
    throw new ApiClientError("DatumGuard API에 연결하지 못했습니다.", {
      kind: "network",
      cause: reason,
    });
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", abortFromCaller);
  }

  const raw = await response.text();
  let payload: unknown = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (reason) {
      if (response.ok) {
        throw new ApiClientError("서버가 올바른 JSON 응답을 반환하지 않았습니다.", {
          kind: "invalid-response",
          status: response.status,
          cause: reason,
        });
      }
    }
  }

  if (!response.ok) {
    const envelope = errorEnvelope(payload);
    const detail = envelope?.error;
    throw new ApiClientError(detail?.message || `API 요청이 실패했습니다. (${response.status})`, {
      kind: "http",
      status: response.status,
      retryAfterMs: parseRetryAfter(response.headers.get("retry-after")),
      correlationId: detail?.correlation_id,
      code: detail?.code,
    });
  }

  return payload as T;
}

export function apiGet<T>(path: string, options?: RequestOptions): Promise<T> {
  return requestJson<T>(path, { method: "GET" }, options);
}

export function apiPostJson<T>(
  path: string,
  body: unknown,
  options?: RequestOptions,
): Promise<T> {
  // Heavy POST requests are intentionally attempted once. The caller must expose a manual retry.
  return requestJson<T>(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    options,
  );
}

export function apiPostForm<T>(
  path: string,
  body: FormData,
  options?: RequestOptions,
): Promise<T> {
  // Do not retry uploads automatically: the first request may still be consuming CPU server-side.
  return requestJson<T>(path, { method: "POST", body }, options);
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiClientError)) {
    return error instanceof Error ? error.message : fallback;
  }
  if (error.kind === "timeout") {
    return `${error.message} 서버 작업이 계속 중일 수 있어 자동 재실행하지 않았습니다. 상태를 확인한 뒤 수동으로 다시 시도하세요.`;
  }
  const wait = error.retryAfterMs
    ? ` 약 ${Math.max(1, Math.ceil(error.retryAfterMs / 1000))}초 후`
    : " 잠시 후";
  if (error.status === 429) {
    return `요청이 많아 제한되었습니다.${wait} 수동으로 다시 시도하세요.`;
  }
  if (error.status === 503) {
    return `검증 엔진이 아직 준비되지 않았습니다.${wait} 수동으로 다시 시도하세요.`;
  }
  const reference = error.correlationId ? ` · 참조 ${error.correlationId}` : "";
  return `${error.message}${reference}`;
}

export type ReadinessProgress = {
  attempt: number;
  delayMs: number;
  phase: "checking" | "waiting";
};

type ReadinessResponse = { status?: string; version?: string };
type DomainResponse = Array<{ id?: string }>;

function abortableDelay(delayMs: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const finish = () => {
      signal?.removeEventListener("abort", abort);
      resolve();
    };
    const timer = window.setTimeout(finish, delayMs);
    const abort = () => {
      window.clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      reject(new ApiClientError("준비 상태 확인이 취소되었습니다.", { kind: "aborted" }));
    };
    if (signal?.aborted) abort();
    else signal?.addEventListener("abort", abort, { once: true });
  });
}

function readinessDelay(attempt: number, retryAfterMs?: number): number {
  const base = Math.min(8_000, 1_000 * 2 ** Math.max(0, attempt - 1));
  const jittered = Math.round(base * (0.82 + Math.random() * 0.36));
  return Math.max(jittered, retryAfterMs || 0);
}

export async function waitForBackendReadiness({
  domainId,
  deadlineMs = 70_000,
  signal,
  onProgress,
}: {
  domainId: BackendDomainId;
  deadlineMs?: number;
  signal?: AbortSignal;
  onProgress?: (progress: ReadinessProgress) => void;
}): Promise<{ version: string }> {
  const deadline = Date.now() + deadlineMs;
  let attempt = 0;
  let lastError: unknown = new ApiClientError("검증 엔진 준비 상태를 확인하지 못했습니다.", {
    kind: "network",
  });

  while (Date.now() < deadline) {
    attempt += 1;
    onProgress?.({ attempt, delayMs: 0, phase: "checking" });
    try {
      const remaining = Math.max(1_000, deadline - Date.now());
      const timeoutMs = Math.min(6_000, remaining);
      const readiness = await apiGet<ReadinessResponse>("/api/v1/ready", { signal, timeoutMs });
      if (readiness.status !== "ready") {
        throw new ApiClientError("검증 엔진이 시작 중입니다.", { kind: "http", status: 503 });
      }
      const domains = await apiGet<DomainResponse>("/api/v1/domains", { signal, timeoutMs });
      if (!domains.some((domain) => domain.id === domainId)) {
        throw new ApiClientError("이 배포에는 필요한 검증 기능이 아직 없습니다.", {
          kind: "http",
          status: 503,
          code: "DG_CAPABILITY_UNAVAILABLE",
        });
      }
      return { version: readiness.version || "unknown" };
    } catch (error) {
      if (error instanceof ApiClientError && error.kind === "aborted") throw error;
      lastError = error;
      const remaining = deadline - Date.now();
      if (remaining <= 0) break;
      const retryAfter = error instanceof ApiClientError ? error.retryAfterMs : undefined;
      const delayMs = Math.min(remaining, readinessDelay(attempt, retryAfter));
      onProgress?.({ attempt, delayMs, phase: "waiting" });
      await abortableDelay(delayMs, signal);
    }
  }

  if (lastError instanceof ApiClientError) throw lastError;
  throw new ApiClientError("70초 동안 검증 엔진에 연결하지 못했습니다.", {
    kind: "network",
    cause: lastError,
  });
}

"use client";

import type { BackendReadiness } from "@/lib/use-backend-readiness";

export default function BackendReadinessNotice({
  readiness,
  className = "",
}: {
  readiness: BackendReadiness;
  className?: string;
}) {
  return (
    <div
      className={`backend-readiness ${readiness.state} ${className}`.trim()}
      role="status"
      aria-live="polite"
      data-readiness-state={readiness.state}
    >
      <span aria-hidden="true" />
      <div>
        <strong>{readiness.state === "ready" ? "Backend ready" : "Backend readiness"}</strong>
        <small>{readiness.message}</small>
      </div>
      {readiness.state === "failed" && (
        <button type="button" onClick={readiness.retry}>수동 재시도</button>
      )}
    </div>
  );
}

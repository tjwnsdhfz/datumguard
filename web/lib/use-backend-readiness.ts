"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  apiErrorMessage,
  type BackendDomainId,
  waitForBackendReadiness,
} from "./api-client";

export type BackendReadinessState = "checking" | "failed" | "ready" | "waiting";

export type BackendReadiness = {
  attempts: number;
  message: string;
  retry: () => void;
  state: BackendReadinessState;
  version: string | null;
};

export function useBackendReadiness(domainId: BackendDomainId): BackendReadiness {
  const [state, setState] = useState<BackendReadinessState>("checking");
  const [attempts, setAttempts] = useState(0);
  const [message, setMessage] = useState("검증 엔진과 기능 버전을 확인하고 있습니다.");
  const [version, setVersion] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  const retry = useCallback(() => {
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setState("checking");
    setAttempts(0);
    setVersion(null);
    setMessage("검증 엔진과 기능 버전을 확인하고 있습니다.");

    void waitForBackendReadiness({
      domainId,
      signal: nextController.signal,
      onProgress: ({ attempt, delayMs, phase }) => {
        setAttempts(attempt);
        if (phase === "waiting") {
          setState("waiting");
          setMessage(`${attempt}회 확인 완료 · 약 ${Math.max(1, Math.ceil(delayMs / 1000))}초 후 다시 확인합니다.`);
        } else {
          setState("checking");
          setMessage(`${attempt}회째 검증 엔진 상태를 확인하고 있습니다.`);
        }
      },
    })
      .then((result) => {
        if (nextController.signal.aborted) return;
        setState("ready");
        setVersion(result.version);
        setMessage(`검증 엔진 준비 완료 · API ${result.version}`);
      })
      .catch((error) => {
        if (nextController.signal.aborted) return;
        setState("failed");
        setMessage(apiErrorMessage(error, "검증 엔진에 연결하지 못했습니다."));
      });
  }, [domainId]);

  useEffect(() => {
    const timer = window.setTimeout(retry, 0);
    return () => {
      window.clearTimeout(timer);
      controller.current?.abort();
    };
  }, [retry]);

  return { attempts, message, retry, state, version };
}

"use client";

import { useState } from "react";

import { clearLocalData } from "@/lib/draft-db";

export default function LocalDataControls() {
  const [armed, setArmed] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function clear() {
    if (!armed) {
      setArmed(true);
      setStatus("한 번 더 누르면 이 브라우저의 모든 DatumGuard draft를 삭제합니다.");
      return;
    }
    setBusy(true);
    try {
      await clearLocalData();
      setStatus("이 브라우저의 DatumGuard draft를 삭제했습니다.");
      setArmed(false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "로컬 데이터를 삭제하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="privacy-local-controls">
      <button type="button" className={armed ? "armed" : ""} disabled={busy} onClick={clear}>
        {busy ? "삭제 중…" : armed ? "모든 로컬 draft 삭제 확인" : "이 브라우저의 로컬 draft 삭제"}
      </button>
      {status && <p role="status" aria-live="polite">{status}</p>}
    </div>
  );
}

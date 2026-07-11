"use client";

import Link from "next/link";

export default function LocalDraftNotice({
  error,
  onDismiss,
}: {
  error: string | null;
  onDismiss: () => void;
}) {
  if (!error) return null;
  return (
    <div className="local-draft-notice" role="alert">
      <strong>로컬 draft 저장 문제</strong>
      <span>{error} 현재 편집은 계속할 수 있지만 새로고침하면 복원되지 않을 수 있습니다.</span>
      <Link href="/privacy">저장 정책·삭제</Link>
      <button type="button" onClick={onDismiss}>닫기</button>
    </div>
  );
}

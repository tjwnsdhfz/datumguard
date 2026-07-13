"use client";

import Link from "next/link";

import styles from "./launch-states.module.css";

const safeRoutes = [
  ["CASE STUDY", "/case-study"],
  ["FRAMEGUARD", "/frame"],
  ["HOME", "/"],
] as const;

export default function ErrorBoundary({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className={styles.statePage}>
      <a className={styles.skipLink} href="#error-actions">
        Go to recovery actions
      </a>

      <section className={styles.stateFrame} aria-labelledby="error-title">
        <header className={styles.frameHeader}>
          <Link className={styles.brand} href="/" aria-label="DatumGuard home">
            <span className={styles.brandMark} aria-hidden="true">DG</span>
            <span>DATUMGUARD</span>
          </Link>
          <span className={`${styles.headerStatus} ${styles.headerStatusError}`}>
            <i aria-hidden="true" /> SAFE FAILURE / CONTAINED
          </span>
        </header>

        <div className={styles.frameBody}>
          <aside className={`${styles.statusRail} ${styles.errorRail}`} aria-label="Application error status">
            <span className={styles.railLabel}>APPLICATION STATE</span>
            <strong className={styles.statusCode}>ERR</strong>
            <div className={styles.railDatum} aria-hidden="true">
              <span>RAW LOG / HIDDEN</span>
              <span>BOUNDARY / ACTIVE</span>
              <b>EXPORT / STOPPED</b>
            </div>
          </aside>

          <div className={styles.stateContent}>
            <p className={styles.eyebrow}>UI BOUNDARY / SAFE STOP</p>
            <h1 id="error-title">THE REQUEST<br />WAS STOPPED.</h1>
            <p className={styles.lead}>
              현재 화면을 처리하는 중 오류가 발생했습니다. 상세 진단 정보는 이 화면에 노출하지
              않으며, 재시도하거나 안전한 시작점으로 이동할 수 있습니다.
            </p>

            <div className={styles.errorEvidence} aria-label="Safe failure behavior">
              <div><span>01</span><strong>BOUNDARY</strong><small>화면 오류를 현재 경로 안에 격리</small></div>
              <div><span>02</span><strong>DIAGNOSTICS</strong><small>원문 오류·stack·식별자 비공개</small></div>
              <div><span>03</span><strong>NEXT ACTION</strong><small>사용자가 재시도 또는 이동 선택</small></div>
            </div>

            <div className={styles.errorActions} id="error-actions" tabIndex={-1}>
              <button className={styles.primaryButton} type="button" onClick={reset}>
                RETRY CURRENT VIEW
              </button>
              <nav className={styles.inlineRoutes} aria-label="Safe recovery routes">
                {safeRoutes.map(([label, href]) => (
                  <Link href={href} key={href}>{label}</Link>
                ))}
              </nav>
            </div>
          </div>
        </div>

        <footer className={styles.frameFooter}>
          <span>UNVERIFIED OUTPUT / NOT RELEASED</span>
          <span>USER-CONTROLLED RECOVERY / READY</span>
        </footer>
      </section>
    </main>
  );
}

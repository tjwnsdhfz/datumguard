import Link from "next/link";

import styles from "../launch-states.module.css";

const initializationSteps = [
  ["01", "CONTRACT INTERFACES"],
  ["02", "CAD VIEWPORT"],
  ["03", "EVIDENCE GATE"],
] as const;

export default function FrameLoading() {
  return (
    <main className={styles.statePage} role="status" aria-live="polite" aria-busy="true">
      <section className={styles.stateFrame} aria-labelledby="loading-title">
        <header className={styles.frameHeader}>
          <Link className={styles.brand} href="/" aria-label="DatumGuard home">
            <span className={styles.brandMark} aria-hidden="true">DG</span>
            <span>DATUMGUARD</span>
          </Link>
          <span className={`${styles.headerStatus} ${styles.loadingStatus}`}>
            <i aria-hidden="true" /> FRAME WORKSPACE / INITIALIZING
          </span>
        </header>

        <div className={styles.frameBody}>
          <aside className={styles.statusRail} aria-label="Loading status">
            <span className={styles.railLabel}>BOOT SEQUENCE</span>
            <strong className={`${styles.statusCode} ${styles.loadingCode}`} aria-hidden="true">•••</strong>
            <div className={styles.railDatum} aria-hidden="true">
              <span>UNITS / MM</span>
              <span>DATUM / ORIGIN</span>
              <b>GATE / WAITING</b>
            </div>
          </aside>

          <div className={`${styles.stateContent} ${styles.loadingContent}`}>
            <p className={styles.eyebrow}>SYSTEM / INITIALIZATION</p>
            <h1 id="loading-title">PREPARING THE<br />FRAME WORKSPACE.</h1>
            <p className={styles.lead}>
              구조 frame contract, CAD viewport, 독립 검증 gate를 순서대로 준비하고 있습니다.
            </p>

            <ol className={styles.loadingSteps} aria-label="Workspace initialization steps">
              {initializationSteps.map(([number, label], index) => (
                <li key={number} style={{ "--step-delay": `${index * 180}ms` } as React.CSSProperties}>
                  <span>{number}</span>
                  <strong>{label}</strong>
                  <i aria-hidden="true" />
                </li>
              ))}
            </ol>

            <div className={styles.loadingDrawing} aria-hidden="true">
              <span className={styles.drawingAxisX} />
              <span className={styles.drawingAxisY} />
              <i /><i /><i />
            </div>
          </div>
        </div>

        <footer className={styles.frameFooter}>
          <span>SERIALIZED ARTIFACT / PENDING</span>
          <span>PLEASE HOLD · DO NOT REFRESH</span>
        </footer>
      </section>
    </main>
  );
}

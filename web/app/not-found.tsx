import type { Metadata } from "next";
import Link from "next/link";

import styles from "./launch-states.module.css";

export const metadata: Metadata = {
  title: "404 — Route Not Found",
  alternates: null,
};

const recoveryRoutes = [
  ["01", "CASE STUDY", "/case-study", "검증 방식과 공개 evidence"],
  ["02", "FRAMEGUARD", "/frame", "구조 프레임 screening demo"],
  ["03", "CAD WORKSPACE", "/", "건축 CAD 검증 workspace"],
] as const;

export default function NotFound() {
  return (
    <main className={styles.statePage}>
      <a className={styles.skipLink} href="#recovery-actions">
        Go to recovery routes
      </a>

      <section className={styles.stateFrame} aria-labelledby="not-found-title">
        <header className={styles.frameHeader}>
          <Link className={styles.brand} href="/" aria-label="DatumGuard home">
            <span className={styles.brandMark} aria-hidden="true">DG</span>
            <span>DATUMGUARD</span>
          </Link>
          <span className={`${styles.headerStatus} ${styles.headerStatusError}`}>
            <i aria-hidden="true" /> ROUTE CHECK / FAILED
          </span>
        </header>

        <div className={styles.frameBody}>
          <aside className={styles.statusRail} aria-label="HTTP response status">
            <span className={styles.railLabel}>HTTP STATUS</span>
            <strong className={styles.statusCode}>404</strong>
            <div className={styles.railDatum} aria-hidden="true">
              <span>X / ROUTE</span>
              <span>Y / NULL</span>
              <b>DATUM / WEB</b>
            </div>
          </aside>

          <div className={styles.stateContent}>
            <p className={styles.eyebrow}>ROUTE / NOT FOUND</p>
            <h1 id="not-found-title">THE DRAWING PATH<br />DOES NOT EXIST.</h1>
            <p className={styles.lead}>
              요청한 경로를 현재 DatumGuard surface에서 찾을 수 없습니다. 아래 검증된 진입점에서
              다시 시작할 수 있습니다.
            </p>

            <nav
              className={styles.routeGrid}
              id="recovery-actions"
              aria-label="Recovery routes"
              tabIndex={-1}
            >
              {recoveryRoutes.map(([number, label, href, description]) => (
                <Link className={styles.routeCard} href={href} key={href}>
                  <span>{number}</span>
                  <strong>{label}</strong>
                  <small>{description}</small>
                  <b aria-hidden="true">→</b>
                </Link>
              ))}
            </nav>
          </div>
        </div>

        <footer className={styles.frameFooter}>
          <span>HTTP 404 · NO ARTIFACT CREATED</span>
          <span>RECOVERY ROUTES / ACTIVE</span>
        </footer>
      </section>
    </main>
  );
}

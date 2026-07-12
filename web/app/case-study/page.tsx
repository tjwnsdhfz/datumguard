import Image from "next/image";
import Link from "next/link";

import styles from "./case-study.module.css";

const repositoryUrl =
  process.env.NEXT_PUBLIC_GITHUB_URL || "https://github.com/tjwnsdhfz/datumguard";
const releaseUrl = `${repositoryUrl.replace(/\/$/, "")}/releases/tag/v0.2.1`;

const pipeline = [
  ["01", "LOCK", "datum·단위·치수·공차를 versioned contract로 고정"],
  ["02", "WRITE", "전용 writer가 DXF 또는 STEP을 직렬화"],
  ["03", "REOPEN", "writer와 분리된 process가 저장 artifact를 다시 로드"],
  ["04", "REMEASURE", "좌표·치수·topology·constraint를 파일에서 재측정"],
  ["05", "GATE", "모든 필수 검사가 통과할 때만 공식 bundle 활성화"],
] as const;

const domains = [
  ["Architecture", "/", "R2013 DXF", "wall loop · opening · grid · room", "HOSTED"],
  ["Plant Piping", "/piping", "R2013 DXF", "route · support · component · clearance", "HOSTED"],
  ["Engineering Plate", "/plate", "R2013 DXF", "hole · slot · cutout · ligament", "HOSTED"],
  ["Limited Solid", "/solid", "STEP", "B-rep · bbox · bore axis · topology", "LOCAL / CI"],
  ["Artifact Lab", "/intake", "DXF · STEP · IFC", "immutable audit · revision compare", "HOSTED"],
  ["OpenBIM Evidence", "/openbim", "IFC4 · IDS", "information · integrity · clearance · revision", "RESEARCH / LOCAL"],
] as const;

export default function CaseStudyPage() {
  return (
    <main className={styles.page} data-testid="case-study">
      <a className={styles.skipLink} href="#case-study-content">
        Skip to case study content
      </a>
      <header className={styles.header}>
        <Link className={styles.brand} href="/case-study" aria-label="DatumGuard case study home">
          <span aria-hidden="true">DG</span>
          <strong>DATUMGUARD</strong>
        </Link>
        <nav aria-label="Case study navigation">
          <a href="#method">Method</a>
          <a href="#evidence">Evidence</a>
          <a href="#scope">Scope</a>
          <Link className={styles.navCta} href="/">Open CAD</Link>
        </nav>
      </header>

      <section
        className={styles.hero}
        id="case-study-content"
        aria-labelledby="case-study-title"
        tabIndex={-1}
      >
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>PUBLIC ENGINEERING CASE STUDY · V0.2.1 BASELINE · UNRELEASED OPENBIM RESEARCH PREVIEW</p>
          <h1 id="case-study-title">
            CAD COMMAND SUCCESS
            <br />
            IS NOT <em>ACCURACY EVIDENCE.</em>
          </h1>
          <p className={styles.lead}>
            DatumGuard는 요구값을 contract로 잠근 뒤, 생성된 CAD 파일을 별도 reader가 다시 열어
            측정합니다. 검증에 실패한 artifact는 공식 export가 될 수 없습니다.
          </p>
          <div className={styles.actions}>
            <Link className={styles.primaryAction} href="/">
              OPEN LIVE ARCHITECTURE
            </Link>
            <a className={styles.secondaryAction} href={repositoryUrl} target="_blank" rel="noreferrer">
              INSPECT SOURCE
            </a>
          </div>
        </div>
        <div className={styles.orbit} aria-hidden="true">
          <span>CONTRACT</span>
          <span>SERIALIZE</span>
          <span>REMEASURE</span>
          <b>PASS</b>
        </div>
      </section>

      <section className={styles.proofStrip} aria-label="Verified project evidence">
        <div><strong>0.001 mm</strong><span>comparison grid</span></div>
        <div><strong>256</strong><span>pytest baseline</span></div>
        <div><strong>24</strong><span>Playwright baseline</span></div>
        <div><strong>5</strong><span>v0.2.1 production workspaces</span></div>
        <div><strong>0</strong><span>unverified official CAD bundles</span></div>
      </section>

      <section className={styles.problemBand}>
        <p className={styles.bandIndex}>01 / PROBLEM</p>
        <div>
          <h2>화면에 올바르게 보이는 형상과 제작 가능한 정확성은 같은 문제가 아닙니다.</h2>
          <p>
            CAD·MCP 자동화는 명령 실행, viewport 표시, 파일 저장까지는 성공할 수 있습니다. 그러나
            좌표계, 단위, locked dimension, 공차 또는 저장 과정이 달라지면 요구한 형상과 실제 파일이
            어긋납니다. 그래서 생성기의 메모리 형상이나 성공 메시지를 승인 근거로 사용하지 않습니다.
          </p>
        </div>
      </section>

      <section className={styles.method} id="method" aria-labelledby="method-title">
        <div className={styles.sectionIntro}>
          <p className={styles.bandIndex}>02 / ASSURANCE METHOD</p>
          <h2 id="method-title">WRITER와 VERIFIER 사이에 저장 파일 경계를 둡니다.</h2>
          <p>
            verifier는 writer의 in-memory geometry를 전달받지 않습니다. hash가 고정된 serialized
            artifact만 독립 입력으로 사용합니다.
          </p>
        </div>
        <ol className={styles.pipeline}>
          {pipeline.map(([number, title, body]) => (
            <li key={number}>
              <span>{number}</span>
              <strong>{title}</strong>
              <p>{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.evidence} id="evidence" aria-labelledby="evidence-title">
        <div className={styles.sectionIntro}>
          <p className={styles.bandIndex}>03 / SERIALIZED-DXF EVIDENCE</p>
          <h2 id="evidence-title">같은 계약은 같은 hash와 같은 측정 결과를 만듭니다.</h2>
          <p>
            공개 demo의 수치는 합성 fixture와 실제 API 응답에서 재현되며, PASS와 FAIL 모두 저장소에
            남아 있습니다.
          </p>
        </div>

        <article className={styles.evidenceFeature}>
          <div className={styles.imageFrame}>
            <Image
              src="/case-study/architecture-verified.png"
              alt="Architecture contract editor with a four-room DXF plan and passed verification timeline"
              width={1440}
              height={960}
              sizes="(max-width: 1000px) calc(100vw - 44px), 68vw"
            />
          </div>
          <div className={styles.evidenceCopy}>
            <p className={styles.resultPass}>PASS · ARCHITECTURE</p>
            <h3>12,000 × 8,000 mm studio plan</h3>
            <dl>
              <div><dt>Gross area</dt><dd>96.0 m²</dd></div>
              <div><dt>Resolved rooms</dt><dd>4 / 4</dd></div>
              <div><dt>DXF identity</dt><dd>hash-bound XDATA</dd></div>
              <div><dt>Export gate</dt><dd>bundle enabled</dd></div>
            </dl>
            <Link href="/">REPRODUCE IN LIVE WORKSPACE</Link>
          </div>
        </article>

        <div className={styles.passFailGrid}>
          <article className={styles.passCard}>
            <span>PASS PATH</span>
            <strong>Contract locked → DXF reopened → 0 violations</strong>
            <p>DXF·SVG·DO NOT SCALE PDF·verification JSON이 하나의 approval bundle로 생성됩니다.</p>
            <code>status: passed · bundle_base64: present</code>
          </article>
          <article className={styles.failCard}>
            <span>FAIL-CLOSED PATH</span>
            <strong>외벽 endpoint를 300 mm 이격</strong>
            <p>독립 verifier가 열린 외벽 loop를 찾고 공식 bundle 생성을 차단합니다.</p>
            <code>DG_ARCH_EXTERIOR_OPEN · bundle: null</code>
          </article>
        </div>

        <article className={`${styles.evidenceFeature} ${styles.reverse}`}>
          <div className={styles.imageFrame}>
            <Image
              src="/case-study/piping-verified.png"
              alt="Plant piping workspace with routed utility line, supports, clearance zones, and passed DXF verification"
              width={1440}
              height={960}
              sizes="(max-width: 1000px) calc(100vw - 44px), 68vw"
            />
          </div>
          <div className={styles.evidenceCopy}>
            <p className={styles.resultPass}>PASS · PLANT / SEMICONDUCTOR PIPING</p>
            <h3>CDA utility route geometry</h3>
            <dl>
              <div><dt>Route length</dt><dd>12.0 m</dd></div>
              <div><dt>Max support gap</dt><dd>2,000 mm</dd></div>
              <div><dt>Minimum clearance</dt><dd>1,975 mm</dd></div>
              <div><dt>Failure fixture</dt><dd>DG_PIPE_CLEARANCE_VIOLATION</dd></div>
            </dl>
            <Link href="/piping">OPEN PIPING WORKSPACE</Link>
          </div>
        </article>
      </section>

      <section className={styles.method} aria-labelledby="openbim-preview-title">
        <div className={styles.sectionIntro}>
          <p className={styles.bandIndex}>04 / OPENBIM RESEARCH PREVIEW</p>
          <h2 id="openbim-preview-title">IFC 변경을 보는 대신, 동결 protocol로 검증 evidence를 남깁니다.</h2>
          <p>
            baseline/candidate IFC4와 IDS 1.0을 별도 worker에서 다시 열어 정보요구조건, IFC integrity,
            project AABB clearance와 protected revision을 검사합니다. 이 결과는 합성 연구 검증이며
            제작·시공 승인 자격을 만들지 않습니다.
          </p>
        </div>
        <div className={styles.passFailGrid}>
          <article className={styles.passCard}>
            <span>CORRECTED HELD-OUT RESULT</span>
            <strong>30 cases · 330 TP · 0 FP · 0 FN</strong>
            <p>120 candidate records, 1,200 measured engine runs, clean/authorized false positive 0.</p>
            <code>research_validation_only: true · approval_eligible: false</code>
          </article>
          <article className={styles.failCard}>
            <span>OPEN GATES</span>
            <strong>Perfect synthetic score is not industrial approval</strong>
            <p>독립 BCF viewer, buildingSMART 외부 validation, license 검토, Docker/Linux CI와 production smoke는 미완료입니다.</p>
            <code>protocol-v1 → analysis-v1.0.2 · detector rerun: false</code>
          </article>
        </div>
        <Link className={styles.secondaryAction} href="/openbim">OPEN LOCAL RESEARCH WORKSPACE</Link>
      </section>

      <section className={styles.solidBand} aria-labelledby="solid-title">
        <div className={styles.solidCopy}>
          <p className={styles.bandIndex}>05 / STEP CROSS-CHECK</p>
          <h2 id="solid-title">3D는 공개 실행보다 검증 가능한 범위를 먼저 제한했습니다.</h2>
          <p>
            Mounting plate, angle bracket, flange만 지원합니다. OpenCascade writer subprocess가 만든 STEP을
            별도 OpenCascade process가 다시 읽어 B-rep, bbox, topology와 cylindrical feature를
            측정합니다.
          </p>
          <ul>
            <li><b>120 × 80 × 8 mm</b> verified mounting plate bbox</li>
            <li><b>15 / 15</b> contracted dimensions passed</li>
            <li><b>Rhino 8</b> re-import는 secondary evidence</li>
          </ul>
          <div className={styles.hostedNotice}>
            <strong>HOSTED RUN DISABLED</strong>
            <span>Render Free에서는 OpenCascade memory risk 때문에 `503 DG_CAPABILITY_DISABLED`로 fail closed합니다.</span>
          </div>
          <Link className={styles.secondaryAction} href="/solid">VIEW STATIC SOLID EVIDENCE</Link>
        </div>
        <div className={styles.solidImage}>
          <Image
            src="/case-study/solid-step-verified.png"
            alt="OpenCascade STEP mounting plate verification with mesh preview and all dimensions passing"
            width={1440}
            height={960}
            sizes="(max-width: 1000px) calc(100vw - 44px), 62vw"
          />
        </div>
      </section>

      <section className={styles.scope} id="scope" aria-labelledby="scope-title">
        <div className={styles.sectionIntro}>
          <p className={styles.bandIndex}>06 / IMPLEMENTED SURFACE</p>
          <h2 id="scope-title">다섯 production workflow와 하나의 연구 검증 workspace를 분리했습니다.</h2>
        </div>
        <div className={styles.domainTable} role="table" aria-label="Implemented engineering workspaces">
          <div className={styles.tableHeader} role="row">
            <span role="columnheader">WORKSPACE</span>
            <span role="columnheader">ARTIFACT</span>
            <span role="columnheader">INDEPENDENT EVIDENCE</span>
            <span role="columnheader">RUNTIME</span>
          </div>
          {domains.map(([name, href, artifact, checks, runtime]) => (
            <div className={styles.tableRow} role="row" key={name}>
              <div role="cell" data-label="Workspace"><Link href={href}>{name}</Link></div>
              <div role="cell" data-label="Artifact">{artifact}</div>
              <div role="cell" data-label="Evidence">{checks}</div>
              <div role="cell" data-label="Runtime"><b>{runtime}</b></div>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.boundaries} aria-labelledby="boundaries-title">
        <p className={styles.bandIndex}>07 / EXPLICIT LIMITS</p>
        <div>
          <h2 id="boundaries-title">이 도구가 증명하는 것과 증명하지 않는 것을 분리합니다.</h2>
          <div className={styles.boundaryColumns}>
            <article>
              <span>VERIFIES</span>
              <ul>
                <li>계약한 좌표·치수·공차와 저장 artifact의 일치</li>
                <li>지원 geometry의 topology·clearance·연결 constraint</li>
                <li>artifact/contract hash와 재현 가능한 PASS/FAIL evidence</li>
                <li>official CAD 경로의 미검증 bundle 차단</li>
              </ul>
            </article>
            <article>
              <span>DOES NOT CERTIFY</span>
              <ul>
                <li>구조 안전, 유체·열·피로·압력 해석</li>
                <li>건축법·산업표준·제작 규격 적합성</li>
                <li>범용 3D, assembly, 재료·용접·가공성</li>
                <li>계획 중인 100 golden + 50 language benchmark의 완료</li>
              </ul>
            </article>
          </div>
        </div>
      </section>

      <section className={styles.releaseEvidence} aria-labelledby="release-title">
        <div>
          <p className={styles.bandIndex}>08 / REPRODUCIBLE RELEASE</p>
          <h2 id="release-title">설명보다 재현 경로를 남깁니다.</h2>
        </div>
        <div className={styles.releaseGrid}>
          <a className={styles.releaseCard} href={releaseUrl} target="_blank" rel="noreferrer">
            <span>TEST</span><strong>256 pytest + 24 Playwright</strong><p>Open the v0.2.1 release evidence ↗</p>
          </a>
          <article><span>OPENBIM LOCAL</span><strong>295 pytest + 27 Playwright</strong><p>unreleased research branch gate</p></article>
          <article><span>CI</span><strong>Type · lint · build · containers</strong><p>SBOM, CodeQL, audit, Trivy 포함</p></article>
          <article><span>DEPLOY</span><strong>Vercel + Render</strong><p>DOM, API capability, canary, CORS smoke</p></article>
          <article><span>ROLLBACK</span><strong>Known-good SHA + deployment IDs</strong><p>Wrong PASS를 SEV1으로 처리</p></article>
        </div>
        <pre><code>{`git clone https://github.com/tjwnsdhfz/datumguard.git\ncd datumguard\ndocker compose up --build`}</code></pre>
      </section>

      <section className={styles.finalCta}>
        <p>CONTRACT → SERIALIZED ARTIFACT → INDEPENDENT REMEASUREMENT → GATE</p>
        <h2>검증 evidence가 없는 CAD 자동화는 공식 산출물이 아닙니다.</h2>
        <div className={styles.actions}>
          <Link className={styles.primaryAction} href="/">RUN THE LIVE DEMO</Link>
          <a className={styles.secondaryAction} href={repositoryUrl} target="_blank" rel="noreferrer">READ THE CODE</a>
        </div>
      </section>

      <footer className={styles.footer}>
        <span>DATUMGUARD · INDEPENDENT CAD ASSURANCE</span>
        <Link href="/privacy">PRIVACY / LOCAL DATA</Link>
      </footer>
    </main>
  );
}

"use client";

import Link from "next/link";
import { type KeyboardEvent, useRef, useState } from "react";

import { apiErrorMessage, apiPostForm } from "@/lib/api-client";
import { useBackendReadiness } from "@/lib/use-backend-readiness";
import BackendReadinessNotice from "./components/backend-readiness";
import MeshPreview from "./components/mesh-preview";

type Metric = {
  metric_id: string;
  label: string;
  value: number | string | boolean | null;
  unit: string | null;
};

type Issue = {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
  entity_ids: string[];
  details: Record<string, unknown>;
};

type Mesh = {
  vertices: [number, number, number][];
  triangles: [number, number, number][];
  truncated: boolean;
  source_triangle_count: number;
};

type AuditResult = {
  status: "audited" | "needs_confirmation" | "failed_verification";
  artifact_hash: string | null;
  format: "dxf" | "step" | "ifc" | null;
  filename: string;
  byte_size: number;
  approval_eligible: false;
  original_preserved: true;
  measurements: Metric[];
  summary: Record<string, unknown>;
  issues: Issue[];
  preview_svg: string | null;
  preview_mesh: Mesh | null;
  error?: { code: string; message: string } | null;
};

type ComparisonResult = {
  status: AuditResult["status"];
  format: AuditResult["format"];
  baseline_hash: string;
  candidate_hash: string;
  same_artifact: boolean;
  comparison: Record<string, unknown>;
  baseline: AuditResult;
  candidate: AuditResult;
  error?: { code: string; message: string } | null;
};

function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

function displayValue(value: Metric["value"]): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "YES" : "NO";
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
  return value;
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function FilePicker({
  id,
  label,
  file,
  onChange,
}: {
  id: string;
  label: string;
  file: File | null;
  onChange: (file: File | null) => void;
}) {
  return (
    <label className={`lab-dropzone ${file ? "has-file" : ""}`} htmlFor={id}>
      <input
        id={id}
        type="file"
        accept=".dxf,.step,.stp,.p21,.ifc"
        onChange={(event) => onChange(event.target.files?.[0] || null)}
      />
      <span className="lab-file-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M7 2h7l5 5v15H7zM14 2v6h6M9 14h6M12 11v6" /></svg>
      </span>
      <span>
        <strong>{file ? file.name : label}</strong>
        <small>{file ? `${bytes(file.size)} · ${file.type || "CAD artifact"}` : "DXF · STEP/STP · IFC · 최대 20MB"}</small>
      </span>
      <b>{file ? "CHANGE" : "SELECT FILE"}</b>
    </label>
  );
}

function DxfPreview({ svg, filename }: { svg: string; filename: string }) {
  const source = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  return (
    <figure className="lab-dxf-figure">
      {/* An image document cannot execute embedded SVG script in the application origin. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={source} alt={`${filename} DXF modelspace preview`} />
      <figcaption><span>ezdxf rendered modelspace</span><code>{filename}</code></figcaption>
    </figure>
  );
}

function AuditEvidence({ result }: { result: AuditResult }) {
  const typeCounts = (result.summary.type_counts || result.summary.entity_types || {}) as Record<
    string,
    number
  >;
  return (
    <section className="lab-evidence" aria-labelledby="artifact-evidence-title" data-testid="artifact-audit-results">
      <div className="lab-result-heading">
        <div>
          <span>INDEPENDENT ARTIFACT EVIDENCE</span>
          <h2 id="artifact-evidence-title">{result.filename}</h2>
          <p>원본 파일은 변경하지 않았으며, 이 결과는 contract 승인이나 제작 인증이 아닙니다.</p>
        </div>
        <div className={`lab-status ${result.status}`} role="status">
          <strong>{result.status.replace("_", " ")}</strong>
          <small>{result.format?.toUpperCase() || "UNKNOWN"} · {bytes(result.byte_size)}</small>
        </div>
      </div>

      <div className="lab-hash-row">
        <span>Artifact SHA-256</span>
        <code>{result.artifact_hash || "unavailable"}</code>
        <b>ORIGINAL PRESERVED</b>
      </div>

      <div className="lab-metric-grid" aria-label="Artifact measurements">
        {result.measurements.map((metric) => (
          <article key={metric.metric_id}>
            <span>{metric.label}</span>
            <strong>{displayValue(metric.value)}</strong>
            <small>{metric.unit || metric.metric_id}</small>
          </article>
        ))}
      </div>

      <div className="lab-preview-grid">
        <div className="lab-preview-panel">
          <div className="lab-panel-label"><span>GEOMETRY PREVIEW</span><b>SECONDARY VISUAL</b></div>
          {result.preview_svg && <DxfPreview svg={result.preview_svg} filename={result.filename} />}
          {result.preview_mesh && <MeshPreview mesh={result.preview_mesh} label={result.filename} />}
          {!result.preview_svg && !result.preview_mesh && (
            <div className="lab-no-preview">
              <strong>{result.format === "ifc" ? "IFC DATA MODEL" : "NO GEOMETRY PREVIEW"}</strong>
              <p>구조·속성 감사 결과를 우측 데이터에서 확인하세요.</p>
            </div>
          )}
        </div>
        <div className="lab-preview-panel">
          <div className="lab-panel-label"><span>ENTITY / TYPE MATRIX</span><b>{Object.keys(typeCounts).length} TYPES</b></div>
          <div className="lab-type-table" role="table" aria-label="CAD entity type counts">
            {Object.entries(typeCounts).length ? (
              Object.entries(typeCounts).map(([name, count]) => (
                <div role="row" key={name}><code role="cell">{name}</code><strong role="cell">{count.toLocaleString()}</strong></div>
              ))
            ) : (
              <p>분류 가능한 entity type이 없습니다.</p>
            )}
          </div>
        </div>
      </div>

      <div className="lab-issues">
        <div className="lab-panel-label"><span>AUDIT ISSUES</span><b>{result.issues.length}</b></div>
        {result.issues.length ? result.issues.map((issue, index) => (
          <article key={`${issue.code}-${index}`} className={issue.severity}>
            <span>{issue.severity}</span>
            <code>{issue.code}</code>
            <div><strong>{issue.message}</strong>{issue.entity_ids.length > 0 && <small>{issue.entity_ids.join(", ")}</small>}</div>
          </article>
        )) : <div className="lab-clear-state"><strong>NO STRUCTURAL AUDIT ISSUES</strong><span>파일 정확성 승인을 의미하지는 않습니다.</span></div>}
      </div>
    </section>
  );
}

function ComparisonEvidence({ result }: { result: ComparisonResult }) {
  const geometry = result.comparison.geometry as Record<string, unknown> | undefined;
  const ifcRevision = result.comparison.ifc_revision as Record<string, string[]> | undefined;
  const deltas = (result.comparison.metric_deltas || {}) as Record<
    string,
    { before: unknown; after: unknown; delta: number | null; unit: string | null }
  >;
  return (
    <section className="lab-compare-evidence" aria-labelledby="revision-title" data-testid="artifact-compare-results">
      <div className="lab-result-heading">
        <div><span>REVISION INTELLIGENCE</span><h2 id="revision-title">Baseline → Candidate</h2><p>두 원본 hash와 format별 deterministic diff를 함께 보존합니다.</p></div>
        <div className={`lab-status ${result.status}`} role="status"><strong>{result.same_artifact ? "IDENTICAL" : "CHANGED"}</strong><small>{result.format?.toUpperCase() || "MISMATCH"}</small></div>
      </div>
      <div className="lab-compare-hashes">
        <article><span>BASELINE</span><code>{result.baseline_hash}</code></article>
        <article><span>CANDIDATE</span><code>{result.candidate_hash}</code></article>
      </div>
      {geometry && (
        <div className="lab-revision-cards">
          <article><span>Added geometry</span><strong>{String(geometry.added_entity_count ?? 0)}</strong></article>
          <article><span>Removed geometry</span><strong>{String(geometry.removed_entity_count ?? 0)}</strong></article>
          <article><span>Changed handles</span><strong>{String(geometry.changed_handle_count ?? 0)}</strong></article>
          <article><span>Same multiset</span><strong>{geometry.same_geometry_multiset ? "YES" : "NO"}</strong></article>
        </div>
      )}
      {ifcRevision && (
        <div className="lab-revision-cards">
          <article><span>Added GlobalIds</span><strong>{ifcRevision.added_global_ids.length}</strong></article>
          <article><span>Deleted GlobalIds</span><strong>{ifcRevision.deleted_global_ids.length}</strong></article>
          <article><span>Changed GlobalIds</span><strong>{ifcRevision.changed_global_ids.length}</strong></article>
        </div>
      )}
      <div className="lab-delta-table">
        <div className="lab-panel-label"><span>MEASUREMENT DELTAS</span><b>{Object.keys(deltas).length}</b></div>
        <div className="table-scroll"><table><thead><tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Delta</th><th>Unit</th></tr></thead><tbody>
          {Object.entries(deltas).map(([id, item]) => <tr key={id}><td><code>{id}</code></td><td>{String(item.before ?? "—")}</td><td>{String(item.after ?? "—")}</td><td>{item.delta === null ? "—" : item.delta.toLocaleString()}</td><td>{item.unit || "—"}</td></tr>)}
        </tbody></table></div>
      </div>
      <AuditEvidence result={result.candidate} />
    </section>
  );
}

export default function ArtifactLab() {
  const [mode, setMode] = useState<"audit" | "compare">("audit");
  const [file, setFile] = useState<File | null>(null);
  const [baseline, setBaseline] = useState<File | null>(null);
  const [candidate, setCandidate] = useState<File | null>(null);
  const [auditResult, setAuditResult] = useState<AuditResult | null>(null);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<"audit" | "compare">("audit");
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const readiness = useBackendReadiness("artifact_lab");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  function selectMode(nextMode: "audit" | "compare", focusIndex?: number) {
    setMode(nextMode);
    setError(null);
    if (focusIndex != null) window.requestAnimationFrame(() => tabRefs.current[focusIndex]?.focus());
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + 2) % 2;
    selectMode(nextIndex === 0 ? "audit" : "compare", nextIndex);
  }

  function selectFile(nextFile: File | null, setter: (value: File | null) => void) {
    if (nextFile && nextFile.size > 20 * 1024 * 1024) {
      setter(null);
      setError("CAD 파일은 20MB 이하여야 합니다. 파일은 전송되지 않았습니다.");
      return;
    }
    setError(null);
    setter(nextFile);
  }

  async function runAudit() {
    if (!file) return;
    if (!privacyAccepted) {
      setError("비기밀 CAD 업로드 고지를 확인해야 합니다.");
      return;
    }
    if (readiness.state !== "ready") {
      setError("Backend readiness를 먼저 확인합니다. 준비 완료 후 수동으로 다시 시도하세요.");
      readiness.retry();
      return;
    }
    setLastAction("audit");
    setLoading(true); setError(null); setAuditResult(null);
    const body = new FormData(); body.append("file", file);
    try {
      const payload = await apiPostForm<AuditResult>(
        "/api/v1/artifacts/audit",
        body,
        { timeoutMs: 210_000 },
      );
      setAuditResult(payload);
    } catch (reason) {
      setError(apiErrorMessage(reason, "Artifact audit failed"));
    } finally { setLoading(false); }
  }

  async function runCompare() {
    if (!baseline || !candidate) return;
    if (!privacyAccepted) {
      setError("비기밀 CAD 업로드 고지를 확인해야 합니다.");
      return;
    }
    if (readiness.state !== "ready") {
      setError("Backend readiness를 먼저 확인합니다. 준비 완료 후 수동으로 다시 시도하세요.");
      readiness.retry();
      return;
    }
    setLastAction("compare");
    setLoading(true); setError(null); setComparison(null);
    const body = new FormData(); body.append("baseline", baseline); body.append("candidate", candidate);
    try {
      const payload = await apiPostForm<ComparisonResult>(
        "/api/v1/artifacts/compare",
        body,
        { timeoutMs: 210_000 },
      );
      setComparison(payload);
    } catch (reason) {
      setError(apiErrorMessage(reason, "Revision comparison failed"));
    } finally { setLoading(false); }
  }

  return (
    <main className="lab-shell" data-testid="artifact-lab">
      <header className="lab-topbar">
        <Link href="/" className="lab-brand"><span>DG</span><div><strong>DatumGuard</strong><small>Engineering artifact assurance</small></div></Link>
        <nav aria-label="Engineering workspaces"><Link href="/">Architecture</Link><Link href="/piping">Piping</Link><Link href="/plate">Plate</Link><Link href="/solid">3D Solid</Link><Link href="/intake" aria-current="page">Artifact Lab</Link><Link href="/openbim">OpenBIM</Link><Link href="/case-study">Case Study</Link></nav>
      </header>

      <section className="lab-hero">
        <div><span>CAD ARTIFACT LAB · IMMUTABLE INPUT</span><h1>생성기가 아니라<br /><em>실제 파일</em>을 검사합니다.</h1></div>
        <p>AutoCAD·Rhino·FreeCAD·Revit 등에서 내보낸 DXF, STEP, IFC를 원본 hash로 잠그고 구조·단위·geometry·revision을 독립 감사합니다.</p>
      </section>

      <section className="lab-workbench" aria-label="Artifact audit workbench">
        <BackendReadinessNotice readiness={readiness} />
        <div className="lab-mode-tabs" role="tablist" aria-label="Audit mode">
          <button ref={(node) => { tabRefs.current[0] = node; }} id="artifact-tab-audit" type="button" role="tab" aria-selected={mode === "audit"} aria-controls="artifact-panel-audit" tabIndex={mode === "audit" ? 0 : -1} onKeyDown={(event) => handleTabKeyDown(event, 0)} onClick={() => selectMode("audit")}>01 · SINGLE FILE AUDIT<span>구조·단위·형상·속성</span></button>
          <button ref={(node) => { tabRefs.current[1] = node; }} id="artifact-tab-compare" type="button" role="tab" aria-selected={mode === "compare"} aria-controls="artifact-panel-compare" tabIndex={mode === "compare" ? 0 : -1} onKeyDown={(event) => handleTabKeyDown(event, 1)} onClick={() => selectMode("compare")}>02 · REVISION COMPARE<span>Geometry · metrics · GlobalId</span></button>
        </div>

        <label className="lab-upload-consent">
          <input type="checkbox" checked={privacyAccepted} onChange={(event) => setPrivacyAccepted(event.target.checked)} />
          <span><strong>비기밀 CAD만 업로드합니다.</strong> 파일은 Oregon의 API에서 일시 처리되고 서버에 장기 보관되지 않습니다. 브라우저 draft 정책은 <Link href="/privacy">Privacy & local data</Link>에서 확인하세요.</span>
        </label>

        {mode === "audit" ? (
          <div id="artifact-panel-audit" className="lab-input-panel" role="tabpanel" aria-labelledby="artifact-tab-audit" tabIndex={0}>
            <div className="lab-panel-copy"><span>INPUT / 01</span><h2>CAD 파일 하나를 감사합니다</h2><p>복구 가능한 DXF 오류는 원본을 바꾸지 않고 evidence로만 기록합니다. STEP은 격리 OpenCascade worker에서 재수입합니다.</p></div>
            <FilePicker id="artifact-file" label="검사할 CAD 파일" file={file} onChange={(value) => selectFile(value, setFile)} />
            <button data-testid="artifact-audit-button" type="button" className="lab-primary" disabled={!file || !privacyAccepted || loading || readiness.state !== "ready"} onClick={runAudit}>{loading ? <><span className="lab-spinner" />AUDITING SERIALIZED ARTIFACT</> : error && lastAction === "audit" ? "RETRY AUDIT MANUALLY" : "LOCK HASH + RUN INDEPENDENT AUDIT"}</button>
          </div>
        ) : (
          <div id="artifact-panel-compare" className="lab-input-panel" role="tabpanel" aria-labelledby="artifact-tab-compare" tabIndex={0}>
            <div className="lab-panel-copy"><span>INPUT / 02</span><h2>두 revision을 비교합니다</h2><p>DXF는 geometry fingerprint, STEP은 kernel metrics, IFC는 GlobalId와 핵심 속성 변경을 비교합니다.</p></div>
            <div className="lab-file-pair"><FilePicker id="baseline-file" label="Baseline CAD 파일" file={baseline} onChange={(value) => selectFile(value, setBaseline)} /><FilePicker id="candidate-file" label="Candidate CAD 파일" file={candidate} onChange={(value) => selectFile(value, setCandidate)} /></div>
            <button data-testid="artifact-compare-button" type="button" className="lab-primary" disabled={!baseline || !candidate || !privacyAccepted || loading || readiness.state !== "ready"} onClick={runCompare}>{loading ? <><span className="lab-spinner" />COMPARING REVISIONS</> : error && lastAction === "compare" ? "RETRY COMPARE MANUALLY" : "LOCK BOTH HASHES + COMPARE"}</button>
          </div>
        )}
        {error && <div className="lab-error" role="alert"><strong>REQUEST FAILED</strong><span>{error}</span><button type="button" onClick={lastAction === "audit" ? runAudit : runCompare}>수동 재시도</button><button type="button" onClick={() => setError(null)}>Dismiss</button></div>}
      </section>

      {auditResult && <><div className="lab-export-row"><button type="button" onClick={() => downloadJson(`${auditResult.filename}-audit.json`, auditResult)}>DOWNLOAD AUDIT JSON</button></div><AuditEvidence result={auditResult} /></>}
      {comparison && <><div className="lab-export-row"><button type="button" onClick={() => downloadJson("datumguard-revision-comparison.json", comparison)}>DOWNLOAD COMPARISON JSON</button></div><ComparisonEvidence result={comparison} /></>}

      <section className="lab-boundary"><span>ASSURANCE BOUNDARY</span><h2>감사 완료는 설계 승인과 다릅니다.</h2><p>Artifact Lab은 파일 구조와 기하학 evidence를 제공합니다. 구조안전, 압력, 재료, 법규, 공정 적합성은 자격 있는 엔지니어와 제작자가 검토해야 합니다. <Link href="/privacy">Privacy & local data</Link></p></section>
    </main>
  );
}

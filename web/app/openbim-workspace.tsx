"use client";

import Link from "next/link";
import { FormEvent, useMemo, useRef, useState } from "react";

import { WorkspaceNavigation } from "@/app/components/workspace-navigation";
import { apiErrorMessage, apiPostForm } from "@/lib/api-client";

type UploadKey = "baseline" | "candidate" | "requirements";
type RuleStatus = "passed" | "failed" | "not_evaluable" | "ambiguous" | string;

type RuleResult = {
  rule_id?: string;
  scope?: string;
  status?: RuleStatus;
  severity?: string;
  evaluated_count?: number;
  issue_count?: number;
  summary?: string;
};

type EvidenceIssue = {
  issue_key?: string;
  rule_id?: string;
  scope?: string;
  severity?: string;
  message?: string;
  entity_ids?: string[];
  entity_pair?: string[] | null;
  step_ids?: number[];
  field?: string | null;
  expected?: unknown;
  actual?: unknown;
  location?: [number, number, number] | null;
  source_hashes?: {
    baseline?: string;
    candidate?: string;
    ids?: string;
    profile?: string;
  };
};

type ReportArtifact = {
  kind?: string;
  filename?: string;
  media_type?: string;
  artifact_hash?: string;
  byte_size?: number;
  content_base64?: string;
};

type OpenBimEvidenceReport = {
  schema_version?: string;
  status?: "passed" | "failed_verification" | "needs_confirmation" | string;
  profile_id?: string;
  research_validation_only?: boolean;
  approval_eligible?: boolean;
  baseline_hash?: string;
  candidate_hash?: string;
  ids_hash?: string;
  profile_hash?: string;
  rule_results?: RuleResult[];
  issues?: EvidenceIssue[];
  timings_ms?: Record<string, number>;
  reports?: ReportArtifact[];
  error?: { code?: string; message?: string } | null;
};

type UploadDefinition = {
  key: UploadKey;
  step: string;
  title: string;
  helper: string;
  accept: string;
  extensions: string[];
  maxBytes: number;
};

const MEBIBYTE = 1024 * 1024;
const MAX_TOTAL_BYTES = 41 * MEBIBYTE;
const UPLOADS: UploadDefinition[] = [
  {
    key: "baseline",
    step: "01",
    title: "기준 IFC",
    helper: "승인된 기준 모델 · IFC4 · 최대 20 MB",
    accept: ".ifc,application/x-step,application/octet-stream",
    extensions: [".ifc"],
    maxBytes: 20 * MEBIBYTE,
  },
  {
    key: "candidate",
    step: "02",
    title: "후보 IFC",
    helper: "검토할 변경 모델 · IFC4 · 최대 20 MB",
    accept: ".ifc,application/x-step,application/octet-stream",
    extensions: [".ifc"],
    maxBytes: 20 * MEBIBYTE,
  },
  {
    key: "requirements",
    step: "03",
    title: "IDS 요구사항",
    helper: "buildingSMART IDS 1.0 XML (.ids) · 최대 1 MB",
    accept: ".ids,application/xml,text/xml",
    extensions: [".ids"],
    maxBytes: MEBIBYTE,
  },
];

const STATUS_COPY: Record<string, { label: string; detail: string; tone: string }> = {
  passed: {
    label: "검증 통과",
    detail: "실행 가능한 모든 규칙이 통과했습니다.",
    tone: "pass",
  },
  failed_verification: {
    label: "검증 실패",
    detail: "오류 등급 이슈가 있어 증거 검토가 필요합니다.",
    tone: "fail",
  },
  needs_confirmation: {
    label: "확인 필요",
    detail: "판정 불가 또는 모호한 항목을 사람이 확인해야 합니다.",
    tone: "warn",
  },
};

const RULE_STATUS_COPY: Record<string, string> = {
  passed: "통과",
  failed: "실패",
  not_evaluable: "판정 불가",
  ambiguous: "모호함",
};

const ARTIFACT_COPY: Record<string, { label: string; extension: string }> = {
  evidence_json: { label: "Evidence JSON", extension: "JSON" },
  manifest: { label: "Manifest", extension: "JSON" },
  html: { label: "검토 보고서", extension: "HTML" },
  bcf: { label: "BCF 3.0 이슈", extension: "BCF" },
  bcfzip: { label: "BCFZIP 호환본", extension: "BCFZIP" },
};

function formatBytes(bytes: number | undefined): string {
  if (!Number.isFinite(bytes) || bytes === undefined || bytes < 0) return "크기 정보 없음";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < MEBIBYTE) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / MEBIBYTE).toFixed(1)} MB`;
}

function fileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

function scalarText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return "표시할 수 없음";
  }
}

function shortHash(value: string | undefined): string {
  if (!value) return "—";
  return value.length > 27 ? `${value.slice(0, 19)}…${value.slice(-8)}` : value;
}

function safeFilename(value: string | undefined, fallback: string): string {
  const cleaned = (value || fallback).replace(/[\\/:*?"<>|]/g, "-").replace(/^\.+/, "");
  return cleaned || fallback;
}

function Icon({ name }: { name: "arrow" | "check" | "copy" | "download" | "file" | "info" | "shield" | "x" }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (name === "arrow") return <svg {...common}><path d="M5 12h14M13 6l6 6-6 6" /></svg>;
  if (name === "check") return <svg {...common}><path d="m5 12 4 4L19 6" /></svg>;
  if (name === "copy") return <svg {...common}><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></svg>;
  if (name === "download") return <svg {...common}><path d="M12 3v12m0 0 5-5m-5 5-5-5M5 21h14" /></svg>;
  if (name === "file") return <svg {...common}><path d="M6 2h8l4 4v16H6zM14 2v5h5" /><path d="M9 13h6M9 17h6" /></svg>;
  if (name === "info") return <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7h.01" /></svg>;
  if (name === "shield") return <svg {...common}><path d="M12 3 4.5 6v5.5c0 4.7 3.1 7.8 7.5 9.5 4.4-1.7 7.5-4.8 7.5-9.5V6z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></svg>;
  return <svg {...common}><path d="m7 7 10 10M17 7 7 17" /></svg>;
}

function UploadField({
  definition,
  file,
  error,
  disabled,
  onChange,
}: {
  definition: UploadDefinition;
  file: File | null;
  error: string | null;
  disabled: boolean;
  onChange: (file: File | null) => void;
}) {
  const inputId = `openbim-${definition.key}`;
  return (
    <div className={`ob-upload ${file ? "selected" : ""} ${error ? "invalid" : ""}`}>
      <span className="ob-upload-step" aria-hidden="true">{definition.step}</span>
      <div className="ob-upload-copy">
        <label htmlFor={inputId}>{definition.title}</label>
        <p id={`${inputId}-help`}>{definition.helper}</p>
        {file && (
          <div className="ob-file-name" data-testid={`${definition.key}-filename`}>
            <Icon name="file" />
            <span><strong>{file.name}</strong><small>{formatBytes(file.size)}</small></span>
          </div>
        )}
        {error && <p className="ob-field-error" id={`${inputId}-error`}>{error}</p>}
      </div>
      <div className="ob-upload-actions">
        <input
          id={inputId}
          data-testid={`${definition.key}-input`}
          type="file"
          accept={definition.accept}
          disabled={disabled}
          aria-describedby={`${inputId}-help${error ? ` ${inputId}-error` : ""}`}
          aria-invalid={Boolean(error)}
          onChange={(event) => onChange(event.target.files?.[0] || null)}
        />
        <label className="ob-file-button" htmlFor={inputId} aria-hidden={disabled}>
          {file ? "교체" : "파일 선택"}
        </label>
        {file && (
          <button type="button" className="ob-icon-button" disabled={disabled} onClick={() => onChange(null)} aria-label={`${definition.title} 제거`}>
            <Icon name="x" />
          </button>
        )}
      </div>
    </div>
  );
}

function HashItem({ label, value, copied, onCopy }: { label: string; value?: string; copied: boolean; onCopy: () => void }) {
  return (
    <div className="ob-hash-item">
      <span>{label}</span>
      <code title={value}>{shortHash(value)}</code>
      <button type="button" onClick={onCopy} disabled={!value} aria-label={`${label} 해시 복사`}>
        <Icon name={copied ? "check" : "copy"} />
        {copied ? "복사됨" : "복사"}
      </button>
    </div>
  );
}

export default function OpenBimWorkspace() {
  const [files, setFiles] = useState<Record<UploadKey, File | null>>({ baseline: null, candidate: null, requirements: null });
  const [fileErrors, setFileErrors] = useState<Record<UploadKey, string | null>>({ baseline: null, candidate: null, requirements: null });
  const [profileId] = useState("virtual-fab-v1");
  const [consented, setConsented] = useState(false);
  const [includeBcf, setIncludeBcf] = useState(false);
  const [loading, setLoading] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [result, setResult] = useState<OpenBimEvidenceReport | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const totalBytes = useMemo(() => Object.values(files).reduce((sum, file) => sum + (file?.size || 0), 0), [files]);
  const readyFileCount = Object.values(files).filter(Boolean).length;
  const readyToRun = Object.values(files).every(Boolean) && Object.values(fileErrors).every((error) => !error) && totalBytes <= MAX_TOTAL_BYTES && consented && !loading;
  const rules = Array.isArray(result?.rule_results) ? result.rule_results : [];
  const issues = Array.isArray(result?.issues) ? result.issues : [];
  const reports = Array.isArray(result?.reports) ? result.reports : [];
  const status = STATUS_COPY[result?.status || ""] || { label: result?.status || "결과 확인 필요", detail: "서버가 반환한 상태를 검토하세요.", tone: "warn" };
  const counts = {
    passed: rules.filter((rule) => rule.status === "passed").length,
    failed: rules.filter((rule) => rule.status === "failed").length,
    needsReview: rules.filter((rule) => rule.status === "not_evaluable" || rule.status === "ambiguous").length,
  };
  const totalTiming = useMemo(() => {
    const timings = result?.timings_ms || {};
    const explicit = timings.total ?? timings.total_ms ?? timings.engine_total;
    if (Number.isFinite(explicit)) return explicit;
    return Object.values(timings).filter(Number.isFinite).reduce((sum, value) => sum + value, 0);
  }, [result]);

  function updateFile(key: UploadKey, file: File | null) {
    const definition = UPLOADS.find((item) => item.key === key);
    let error: string | null = null;
    if (file && definition) {
      const extension = fileExtension(file.name);
      if (!definition.extensions.includes(extension)) error = `${definition.extensions.join(" 또는 ")} 파일을 선택하세요.`;
      else if (file.size === 0) error = "빈 파일은 검증할 수 없습니다.";
      else if (file.size > definition.maxBytes) error = `파일이 ${formatBytes(definition.maxBytes)} 제한을 초과했습니다.`;
    }
    setFiles((current) => ({ ...current, [key]: file }));
    setFileErrors((current) => ({ ...current, [key]: error }));
    setResult(null);
    setRequestError(null);
  }

  function showRequestError(message: string) {
    setRequestError(message);
    window.requestAnimationFrame(() => errorRef.current?.focus());
  }

  async function runEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!readyToRun || !files.baseline || !files.candidate || !files.requirements) {
      showRequestError("세 파일과 연구 검증 경계 동의를 모두 확인하세요.");
      return;
    }
    const body = new FormData();
    body.append("baseline", files.baseline);
    body.append("candidate", files.candidate);
    body.append("requirements", files.requirements);
    body.append("profile_id", profileId);
    body.append("include_html", "true");
    body.append("include_bcf", String(includeBcf));
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setResult(null);
    setRequestError(null);
    try {
      const response = await apiPostForm<OpenBimEvidenceReport>("/api/v1/openbim/evidence/run", body, { signal: controller.signal, timeoutMs: 180_000 });
      if (!response || typeof response !== "object" || !response.status) throw new Error("검증 결과의 상태 필드가 없습니다.");
      setResult(response);
      window.requestAnimationFrame(() => document.getElementById("openbim-results")?.focus());
    } catch (error) {
      showRequestError(apiErrorMessage(error, "OpenBIM 증거 검증을 완료하지 못했습니다."));
    } finally {
      controllerRef.current = null;
      setLoading(false);
    }
  }

  function cancelRun() {
    controllerRef.current?.abort("cancelled-by-user");
  }

  function downloadBlob(bytes: Uint8Array<ArrayBuffer>, mediaType: string, filename: string) {
    const url = URL.createObjectURL(new Blob([bytes], { type: mediaType }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function downloadArtifact(artifact: ReportArtifact) {
    if (!artifact.content_base64) return;
    try {
      const binary = window.atob(artifact.content_base64);
      const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
      downloadBlob(bytes, artifact.media_type || "application/octet-stream", safeFilename(artifact.filename, `datumguard-${artifact.kind || "evidence"}`));
    } catch {
      showRequestError("산출물 데이터를 해석하지 못했습니다. Evidence JSON에서 artifact hash를 확인하세요.");
    }
  }

  function downloadCurrentResult() {
    if (!result) return;
    const encoded = new TextEncoder().encode(`${JSON.stringify(result, null, 2)}\n`);
    downloadBlob(encoded, "application/json", `datumguard-openbim-${(result.candidate_hash || "evidence").replace("sha256:", "").slice(0, 12)}.json`);
  }

  async function copyHash(label: string, value: string | undefined) {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopiedHash(label);
      window.setTimeout(() => setCopiedHash((current) => current === label ? null : current), 1800);
    } catch {
      showRequestError("클립보드에 해시를 복사하지 못했습니다.");
    }
  }

  return (
    <main className="openbim-app" data-testid="openbim-workspace" data-status={result?.status || "idle"}>
      <header className="ob-topbar">
        <Link className="ob-brand" href="/" aria-label="DatumGuard Architecture로 이동">
          <span aria-hidden="true">DG</span>
          <div><strong>DatumGuard</strong><small>Independent evidence</small></div>
        </Link>
        <WorkspaceNavigation active="openbim" />
      </header>

      <section className="ob-hero" aria-labelledby="openbim-title">
        <div className="ob-hero-copy">
          <p className="ob-kicker">OPENBIM / IFC4 / IDS 1.0 / DETERMINISTIC EVIDENCE</p>
          <h1 id="openbim-title">모델을 보는 대신,<br /><em>변경을 증명합니다.</em></h1>
          <p className="ob-lede">기준 IFC와 후보 IFC를 독립적으로 다시 읽어 요구사항, 모델 무결성, 보호된 변경을 검사합니다. 결과는 해시로 연결된 JSON·HTML과, 선택 시 BCF 증거로 남습니다.</p>
          <div className="ob-hero-actions" aria-label="OpenBIM 시연 바로가기">
            <a className="ob-hero-primary" href="#openbim-demo">90초 시연 보기</a>
            <a className="ob-hero-secondary" href="#openbim-run-heading">직접 검증 실행</a>
            <small>대표 합성 IFC 1건 · 입력부터 추적 증거까지</small>
          </div>
        </div>
        <div className="ob-hero-proof" aria-label="검증 범위 요약">
          <div><span>01</span><strong>IDS</strong><small>정보 요구사항</small></div>
          <div><span>02</span><strong>IFC</strong><small>구조·식별자 무결성</small></div>
          <div><span>03</span><strong>REV</strong><small>보호된 변경 추적</small></div>
        </div>
      </section>

      <section id="openbim-demo" className="ob-demo" aria-labelledby="openbim-demo-heading">
        <div className="ob-demo-heading">
          <div><span>COMPETITION DEMO / 90 SEC</span><h2 id="openbim-demo-heading">세 단계로 검증의 차이를<br />보여줍니다.</h2></div>
          <p><strong>PUBLIC PREVIEW</strong> 공개 주소에서는 시연 구조와 대표 결과를 확인하고, 실제 IFC 검증은 발표 장비의 로컬 환경에서 재현합니다.</p>
        </div>
        <ol className="ob-demo-steps">
          <li><span>01 / INPUT</span><strong>세 원본을 고정합니다.</strong><p>기준 IFC, 후보 IFC, IDS 요구사항을 하나의 입력 세트로 묶습니다.</p></li>
          <li><span>02 / VERIFY</span><strong>14개 규칙을 다시 계산합니다.</strong><p>IDS·IFC 무결성·리비전·여유공간을 결정론적으로 검사합니다.</p></li>
          <li><span>03 / TRACE</span><strong>수정 위치와 증거를 남깁니다.</strong><p>이슈의 entity·field·입력 해시와 JSON·HTML·Manifest를 연결합니다.</p></li>
        </ol>
        <div className="ob-demo-result" aria-label="대표 합성 오류 모델 실행 결과">
          <div><span>REPRESENTATIVE FAULTY IFC</span><strong>검증 실패</strong><small>의도적으로 오류를 주입한 합성 모델 1건</small></div>
          <dl>
            <div><dt>RULES</dt><dd>14</dd></div>
            <div><dt>PASSED</dt><dd>4</dd></div>
            <div><dt>FAILED</dt><dd>10</dd></div>
            <div><dt>ISSUES</dt><dd>12</dd></div>
          </dl>
          <a href="#openbim-run-heading">입력 화면으로 이동</a>
        </div>
      </section>

      <section className="ob-run-section" aria-labelledby="openbim-run-heading">
        <div className="ob-section-heading">
          <div><span>RUN EVIDENCE</span><h2 id="openbim-run-heading">검증 입력</h2></div>
          <p>파일은 실행 요청 동안만 backend로 전송됩니다. DatumGuard는 이 화면에서 모델을 렌더링하지 않습니다.</p>
        </div>

        <form className="ob-run-grid" onSubmit={runEvidence} noValidate>
          <div className="ob-input-panel">
            <div className="ob-panel-label"><span>INPUT SET</span><strong>3개의 원본 파일</strong></div>
            <div className="ob-upload-list">
              {UPLOADS.map((definition) => (
                <UploadField key={definition.key} definition={definition} file={files[definition.key]} error={fileErrors[definition.key]} disabled={loading} onChange={(file) => updateFile(definition.key, file)} />
              ))}
            </div>
            {totalBytes > MAX_TOTAL_BYTES && <p className="ob-total-error" role="alert">세 파일의 합계가 {formatBytes(MAX_TOTAL_BYTES)} 제한을 초과했습니다.</p>}
            <div className="ob-profile-row">
              <label htmlFor="openbim-profile">검증 프로파일</label>
              <select id="openbim-profile" value={profileId} disabled aria-describedby="openbim-profile-help">
                <option value="virtual-fab-v1">Virtual FAB v1</option>
              </select>
              <p id="openbim-profile-help">FAB_TOOL 서비스 여유 공간과 설비 자산 변경 규칙을 포함하는 고정 연구 프로파일입니다.</p>
            </div>
            <label className="ob-package-option">
              <input data-testid="openbim-include-bcf" type="checkbox" checked={includeBcf} disabled={loading} onChange={(event) => setIncludeBcf(event.target.checked)} />
              <span><strong>BCF 3.0 추가</strong>표준 `.bcf`와 동일 바이트의 기존 `.bcfzip` 호환본을 함께 제공합니다. 현재 배포 license와 독립 viewer gate가 완료되지 않아 기본값은 꺼져 있습니다.</span>
            </label>
          </div>

          <aside className="ob-boundary-panel" aria-labelledby="openbim-boundary-heading">
            <div className="ob-panel-label"><span>ASSURANCE BOUNDARY</span><strong id="openbim-boundary-heading">판정 전에 확인하세요</strong></div>
            <ul>
              <li><Icon name="shield" /><span><strong>연구용 검증</strong>설계 승인·법규 인증·제작 승인이 아닙니다.</span></li>
              <li><Icon name="file" /><span><strong>결정론적 규칙</strong>AI 추론이나 자동 수정 없이 같은 입력을 같은 방식으로 검사합니다.</span></li>
              <li><Icon name="info" /><span><strong>의도적인 제한</strong>3D viewer 없이 규칙 결과와 추적 가능한 증거에 집중합니다.</span></li>
            </ul>
            <label className="ob-consent">
              <input type="checkbox" checked={consented} disabled={loading} onChange={(event) => setConsented(event.target.checked)} />
              <span>이 결과가 <strong>research validation only</strong>이며, 자격 있는 검토자의 판단을 대체하지 않음을 이해했습니다.</span>
            </label>
            <div className="ob-readiness" data-testid="openbim-readiness" aria-live="polite">
              <span className={readyFileCount === 3 ? "ready" : ""}><strong>{readyFileCount}/3</strong>FILES READY</span>
              <span className={consented ? "ready" : ""}><strong>{consented ? "OK" : "—"}</strong>BOUNDARY</span>
            </div>
            <div className="ob-run-actions">
              <button className="ob-primary-button" data-testid="openbim-run" type="submit" disabled={!readyToRun} aria-describedby="openbim-run-help">
                {loading ? <><span className="ob-spinner" aria-hidden="true" />증거 생성 중</> : <>OpenBIM 증거 실행<Icon name="arrow" /></>}
              </button>
              {loading && <button className="ob-cancel-button" type="button" onClick={cancelRun}>요청 취소</button>}
            </div>
            <p id="openbim-run-help" className="ob-run-help">IFC 형상 해석 때문에 최대 3분이 걸릴 수 있습니다. 실행 요청은 자동으로 재시도하지 않습니다.</p>
            <div ref={errorRef} className="ob-request-error" role="alert" tabIndex={-1} hidden={!requestError} data-testid="openbim-error">
              <Icon name="info" /><span><strong>실행하지 못했습니다.</strong>{requestError}</span>
            </div>
          </aside>
        </form>
      </section>

      {result && (
        <section id="openbim-results" className="ob-results" aria-labelledby="openbim-result-heading" tabIndex={-1} data-testid="openbim-results">
          <div className="ob-result-heading">
            <div><span>EVIDENCE RESULT · {result.schema_version || "schema unknown"}</span><h2 id="openbim-result-heading">검증 증거</h2></div>
            <div className={`ob-status ob-status-${status.tone}`} data-testid="openbim-status">
              <span aria-hidden="true">{status.tone === "pass" ? "✓" : status.tone === "fail" ? "×" : "!"}</span>
              <div><strong>{status.label}</strong><small>{status.detail}</small></div>
            </div>
          </div>

          <div className="ob-metrics" aria-label="검증 결과 요약">
            <div><span>RULES PASSED</span><strong>{counts.passed}</strong><small>전체 {rules.length}개</small></div>
            <div><span>RULES FAILED</span><strong>{counts.failed}</strong><small>오류 규칙</small></div>
            <div><span>NEEDS REVIEW</span><strong>{counts.needsReview}</strong><small>판정 불가·모호함</small></div>
            <div><span>ISSUES</span><strong>{issues.length}</strong><small>추적 가능한 항목</small></div>
            <div><span>RUNTIME</span><strong>{totalTiming ? `${Math.round(totalTiming)} ms` : "—"}</strong><small>{Object.keys(result.timings_ms || {}).length}개 단계</small></div>
          </div>

          <div className={`ob-result-brief ob-result-brief-${status.tone}`} data-testid="openbim-next-action">
            <span>NEXT REVIEW</span>
            <div>
              <strong>{status.tone === "fail" ? `${counts.failed}개 실패 규칙부터 수정 위치를 확인하세요.` : status.tone === "warn" ? "판정 불가 항목을 검토자에게 배정하세요." : "같은 입력 세트로 결과를 보존할 수 있습니다."}</strong>
              <p>{status.tone === "fail" ? "규칙별 판정에서 원인을 찾고, 검토 항목의 entity·field를 모델에서 수정한 뒤 같은 입력 세트로 재실행합니다." : "입력 해시와 산출물을 함께 저장하면 다음 검토에서도 동일한 증거 체인을 확인할 수 있습니다."}</p>
            </div>
            <a href="#openbim-issues-heading">검토 항목 보기</a>
          </div>

          <div className="ob-result-grid">
            <section className="ob-rule-panel" aria-labelledby="openbim-rules-heading">
              <div className="ob-panel-heading"><div><span>RULE MATRIX</span><h3 id="openbim-rules-heading">규칙별 판정</h3></div><small>{rules.length} rules</small></div>
              {rules.length ? (
                <div className="ob-rule-list">
                  {rules.map((rule, index) => (
                    <article key={`${rule.rule_id || "rule"}-${index}`} className={`ob-rule ob-rule-${rule.status || "unknown"}`}>
                      <span className="ob-rule-marker" aria-hidden="true">{rule.status === "passed" ? "✓" : rule.status === "failed" ? "×" : "!"}</span>
                      <div><code>{rule.rule_id || "UNNAMED_RULE"}</code><strong>{rule.summary || "요약이 제공되지 않았습니다."}</strong><small>{rule.scope || "범위 미지정"} · {rule.severity || "등급 미지정"}</small></div>
                      <div className="ob-rule-count"><strong>{RULE_STATUS_COPY[rule.status || ""] || rule.status || "확인"}</strong><small>{rule.issue_count ?? 0} issues / {rule.evaluated_count ?? 0} checked</small></div>
                    </article>
                  ))}
                </div>
              ) : <p className="ob-empty">반환된 규칙 결과가 없습니다. 서버 오류 필드와 Evidence JSON을 확인하세요.</p>}
            </section>

            <aside className="ob-trace-panel" aria-labelledby="openbim-trace-heading">
              <div className="ob-panel-heading"><div><span>TRACEABILITY</span><h3 id="openbim-trace-heading">입력 해시</h3></div></div>
              <HashItem label="Baseline IFC" value={result.baseline_hash} copied={copiedHash === "baseline"} onCopy={() => copyHash("baseline", result.baseline_hash)} />
              <HashItem label="Candidate IFC" value={result.candidate_hash} copied={copiedHash === "candidate"} onCopy={() => copyHash("candidate", result.candidate_hash)} />
              <HashItem label="IDS requirement" value={result.ids_hash} copied={copiedHash === "ids"} onCopy={() => copyHash("ids", result.ids_hash)} />
              <HashItem label="Rule profile" value={result.profile_hash} copied={copiedHash === "profile"} onCopy={() => copyHash("profile", result.profile_hash)} />
              <div className="ob-trace-note"><Icon name="shield" /><p><strong>{result.profile_id || profileId}</strong><span>{result.research_validation_only === false ? "경계 필드 확인 필요" : "Research validation only"} · approval eligible: {String(result.approval_eligible ?? false)}</span><span>각 이슈는 이 네 입력 해시를 source_hashes로 함께 기록합니다.</span></p></div>
            </aside>
          </div>

          <section className="ob-issues" aria-labelledby="openbim-issues-heading">
            <div className="ob-panel-heading"><div><span>ISSUE REGISTER</span><h3 id="openbim-issues-heading">검토 항목</h3></div><small>{issues.length} issues</small></div>
            {issues.length ? (
              <div className="ob-table-wrap">
                <table>
                  <thead><tr><th scope="col">등급 / 규칙</th><th scope="col">설명</th><th scope="col">엔티티 / 필드</th><th scope="col">예상 ↔ 실제</th></tr></thead>
                  <tbody>
                    {issues.map((issue, index) => {
                      const entities = issue.entity_pair?.length ? issue.entity_pair : issue.entity_ids;
                      return (
                        <tr key={`${issue.issue_key || "issue"}-${index}`}>
                          <td data-label="등급 / 규칙"><span className={`ob-severity ob-severity-${issue.severity || "info"}`}>{issue.severity || "info"}</span><code>{issue.rule_id || "UNKNOWN_RULE"}</code><small>{issue.issue_key || "키 없음"}</small></td>
                          <td data-label="설명"><strong>{issue.message || "설명이 제공되지 않았습니다."}</strong><small>{issue.scope || "범위 미지정"}{issue.location ? ` · (${issue.location.join(", ")})` : ""}</small>{issue.source_hashes && <details className="ob-issue-hashes"><summary>이슈 원본 해시</summary><code title={issue.source_hashes.baseline}>B {shortHash(issue.source_hashes.baseline)}</code><code title={issue.source_hashes.candidate}>C {shortHash(issue.source_hashes.candidate)}</code><code title={issue.source_hashes.ids}>I {shortHash(issue.source_hashes.ids)}</code><code title={issue.source_hashes.profile}>P {shortHash(issue.source_hashes.profile)}</code></details>}</td>
                          <td data-label="엔티티 / 필드"><code>{entities?.length ? entities.join(", ") : "—"}</code><small>{issue.field || (issue.step_ids?.length ? `STEP #${issue.step_ids.join(", #")}` : "필드 없음")}</small></td>
                          <td data-label="예상 ↔ 실제"><span>{scalarText(issue.expected)}</span><i aria-hidden="true">→</i><strong>{scalarText(issue.actual)}</strong></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : <div className="ob-no-issues"><Icon name="check" /><span><strong>등록된 이슈 없음</strong>실행 가능한 규칙에서 추적 항목이 발견되지 않았습니다.</span></div>}
          </section>

          <section className="ob-exports" aria-labelledby="openbim-exports-heading">
            <div className="ob-panel-heading"><div><span>EVIDENCE EXPORT</span><h3 id="openbim-exports-heading">검증 산출물</h3></div><button type="button" className="ob-current-json" onClick={downloadCurrentResult}><Icon name="download" />현재 응답 JSON 저장</button></div>
            {reports.length ? (
              <div className="ob-export-grid">
                {reports.map((artifact, index) => {
                  const copy = ARTIFACT_COPY[artifact.kind || ""] || { label: artifact.kind || "Evidence artifact", extension: "FILE" };
                  return (
                    <article key={`${artifact.artifact_hash || artifact.filename || "artifact"}-${index}`}>
                      <span className="ob-export-type">{copy.extension}</span>
                      <div><strong>{copy.label}</strong><small>{safeFilename(artifact.filename, "datumguard-evidence")} · {formatBytes(artifact.byte_size)}</small><code title={artifact.artifact_hash}>{shortHash(artifact.artifact_hash)}</code></div>
                      <button type="button" disabled={!artifact.content_base64} onClick={() => downloadArtifact(artifact)} aria-label={`${copy.label} 다운로드`}><Icon name="download" />다운로드</button>
                    </article>
                  );
                })}
              </div>
            ) : <p className="ob-empty">서버 생성 산출물이 없습니다. 위 버튼으로 현재 응답 JSON을 보존할 수 있습니다. BCF는 추적 가능한 이슈가 있을 때만 제공될 수 있습니다.</p>}
          </section>

          {result.error && <div className="ob-result-error" role="alert"><Icon name="info" /><span><strong>{result.error.code || "RESULT_ERROR"}</strong>{result.error.message || "서버가 상세 오류를 제공하지 않았습니다."}</span></div>}
        </section>
      )}

      <section className="ob-method" aria-labelledby="openbim-method-heading">
        <span>METHOD / SCOPE</span>
        <h2 id="openbim-method-heading">증거가 답하는 것과<br />답하지 않는 것을 분리합니다.</h2>
        <div>
          <article><strong>검사합니다</strong><p>IDS 속성 요구사항, IFC 구조·식별자 무결성, 자산 키 기반 보호 필드 변경, 프로젝트 전용 서비스 여유 공간 규칙.</p></article>
          <article><strong>검사하지 않습니다</strong><p>구조 안전, 압력 설계, 공정 시뮬레이션, 법규 적합성, 모델의 시각적 품질 또는 제작 가능성 전체.</p></article>
          <article><strong>사람에게 남깁니다</strong><p>판정 불가·모호함의 해석, 변경 승인, BCF 이슈 조정, 최종 설계와 제작 승인.</p></article>
        </div>
      </section>

      <footer className="ob-footer">
        <div><span aria-hidden="true">DG</span><p><strong>DatumGuard OpenBIM Evidence Guard</strong><small>Student research prototype · independent evidence, not certification</small></p></div>
        <nav aria-label="OpenBIM footer links"><Link href="/privacy">Privacy</Link><Link href="/case-study">Case Study</Link><a href="#openbim-title">맨 위로</a></nav>
      </footer>
    </main>
  );
}

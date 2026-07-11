"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import BackendReadinessNotice from "./components/backend-readiness";
import LocalDraftNotice from "./components/local-draft-notice";
import MeshPreview from "./components/mesh-preview";
import { apiErrorMessage, apiPostJson } from "@/lib/api-client";
import { loadDraft, saveDraft } from "@/lib/draft-db";
import { useBackendReadiness } from "@/lib/use-backend-readiness";

type Family = "mounting_plate" | "angle_bracket" | "flange";

type Draft = {
  family: Family;
  projectName: string;
  revision: string;
  tolerance: number;
  width: number;
  depth: number;
  thickness: number;
  cornerRadius: number;
  holeDiameter: number;
  holeX: number;
  holeY: number;
  verticalHeight: number;
  verticalThickness: number;
  outerDiameter: number;
  innerDiameter: number;
  boltCircleDiameter: number;
  boltHoleDiameter: number;
  boltHoleCount: number;
};

type Measurement = {
  dimension_id: string;
  target: number;
  actual: number;
  deviation: number;
  tolerance_lower: number;
  tolerance_upper: number;
  passed: boolean;
};

type Violation = { code: string; message: string; entity_ids: string[] };

type Mesh = {
  vertices: [number, number, number][];
  triangles: [number, number, number][];
  truncated: boolean;
  source_triangle_count: number;
};

type SolidResult = {
  status: "passed" | "failed_verification";
  contract_hash: string;
  artifact_hash: string | null;
  measurements: Measurement[];
  violations: Violation[];
  summary: Record<string, unknown>;
  preview_mesh: Mesh | null;
  step_base64: string | null;
  bundle_base64: string | null;
  error?: { code: string; message: string } | null;
};

const DRAFT_KEY = "solid-contract-draft-v1";

const PLATE: Draft = {
  family: "mounting_plate", projectName: "Semiconductor tool mounting plate", revision: "A",
  tolerance: 0.001, width: 120, depth: 80, thickness: 8, cornerRadius: 6,
  holeDiameter: 10, holeX: 45, holeY: 25, verticalHeight: 90, verticalThickness: 8,
  outerDiameter: 160, innerDiameter: 70, boltCircleDiameter: 120, boltHoleDiameter: 14,
  boltHoleCount: 8,
};

const BRACKET: Draft = {
  ...PLATE, family: "angle_bracket", projectName: "Ship equipment angle bracket",
  width: 140, depth: 80, thickness: 8, holeDiameter: 12, holeX: 45, holeY: 15,
  verticalHeight: 90, verticalThickness: 8,
};

const FLANGE: Draft = {
  ...PLATE, family: "flange", projectName: "Utility flange geometry study",
  thickness: 18, outerDiameter: 160, innerDiameter: 70, boltCircleDiameter: 120,
  boltHoleDiameter: 14, boltHoleCount: 8,
};

const PRESETS: Record<Family, Draft> = { mounting_plate: PLATE, angle_bracket: BRACKET, flange: FLANGE };

function buildContract(draft: Draft) {
  let geometry: Record<string, unknown>;
  if (draft.family === "mounting_plate") {
    geometry = {
      type: draft.family, width: draft.width, depth: draft.depth, thickness: draft.thickness,
      corner_radius: draft.cornerRadius,
      holes: [
        { id: "mount-a", center: [-draft.holeX, -draft.holeY], diameter: draft.holeDiameter },
        { id: "mount-b", center: [draft.holeX, -draft.holeY], diameter: draft.holeDiameter },
        { id: "mount-c", center: [-draft.holeX, draft.holeY], diameter: draft.holeDiameter },
        { id: "mount-d", center: [draft.holeX, draft.holeY], diameter: draft.holeDiameter },
      ],
    };
  } else if (draft.family === "angle_bracket") {
    geometry = {
      type: draft.family, width: draft.width, base_depth: draft.depth,
      base_thickness: draft.thickness, vertical_height: draft.verticalHeight,
      vertical_thickness: draft.verticalThickness,
      base_holes: [
        { id: "base-a", center: [-draft.holeX, draft.holeY], diameter: draft.holeDiameter },
        { id: "base-b", center: [draft.holeX, draft.holeY], diameter: draft.holeDiameter },
      ],
    };
  } else {
    geometry = {
      type: draft.family, outer_diameter: draft.outerDiameter, inner_diameter: draft.innerDiameter,
      thickness: draft.thickness, bolt_circle_diameter: draft.boltCircleDiameter,
      bolt_hole_diameter: draft.boltHoleDiameter, bolt_hole_count: draft.boltHoleCount,
    };
  }
  return {
    schema_version: "1.0.0", design_kind: "solid_part", units: "mm", geometry,
    tolerance_mm: draft.tolerance,
    metadata: { project_name: draft.projectName, revision: draft.revision, notes: "Geometry verification only." },
    contract_hash: null,
  };
}

function saveBase64(filename: string, encoded: string, type: string) {
  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
  URL.revokeObjectURL(url);
}

function Field({ label, value, unit = "mm", onChange, min = 0.001, step = 1 }: { label: string; value: number; unit?: string; onChange: (value: number) => void; min?: number; step?: number }) {
  return <label className="solid-field"><span>{label}</span><div><input type="number" min={min} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} /><small>{unit}</small></div></label>;
}

export default function SolidWorkspace() {
  const [draft, setDraft] = useState<Draft>(PLATE);
  const [result, setResult] = useState<SolidResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [storageError, setStorageError] = useState<string | null>(null);
  const readiness = useBackendReadiness("solid_part");
  const contract = useMemo(() => buildContract(draft), [draft]);
  const setNumber = (key: keyof Draft, value: number) => setDraft((current) => ({ ...current, [key]: value }));

  useEffect(() => {
    loadDraft<Draft>(DRAFT_KEY)
      .then((saved) => {
        if (saved && saved.family in PRESETS) setDraft(saved);
      })
      .catch((reason) => setStorageError(reason instanceof Error ? reason.message : "로컬 draft를 읽지 못했습니다."))
      .finally(() => setHydrated(true));
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    const timer = window.setTimeout(() => {
      saveDraft(draft, DRAFT_KEY)
        .then(() => setStorageError(null))
        .catch((reason) => setStorageError(reason instanceof Error ? reason.message : "로컬 draft를 저장하지 못했습니다."));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [draft, hydrated]);

  async function run() {
    if (readiness.state !== "ready") {
      setError("Backend readiness를 먼저 확인합니다. 준비 완료 후 수동으로 다시 시도하세요.");
      readiness.retry();
      return;
    }
    setLoading(true); setError(null); setResult(null);
    try {
      const payload = await apiPostJson<SolidResult>(
        "/api/v1/solid/designs/run",
        contract,
        { timeoutMs: 210_000 },
      );
      setResult(payload);
    } catch (reason) {
      setError(apiErrorMessage(reason, "STEP generation failed"));
    } finally { setLoading(false); }
  }

  const pipeline = result?.status === "passed" ? ["locked", "written", "reopened", "measured", "approved"] : loading ? ["locked", "running", "waiting", "waiting", "blocked"] : ["waiting", "waiting", "waiting", "waiting", "blocked"];

  return (
    <main className="solid-shell" data-testid="solid-workspace" data-run-status={loading ? "running" : result?.status || "idle"}>
      <header className="lab-topbar">
        <Link href="/" className="lab-brand"><span>DG</span><div><strong>DatumGuard</strong><small>OpenCascade solid assurance</small></div></Link>
        <nav aria-label="Engineering workspaces"><Link href="/">Architecture</Link><Link href="/piping">Piping</Link><Link href="/plate">Plate</Link><Link href="/solid" aria-current="page">3D Solid</Link><Link href="/intake">Artifact Lab</Link></nav>
      </header>

      <LocalDraftNotice error={storageError} onDismiss={() => setStorageError(null)} />

      <section className="solid-header">
        <div><span>3D SOLID CONTRACT · STEP AUTHORITY</span><h1>정확한 3D 형상을 만들고<br /><em>다시 열어 측정합니다.</em></h1></div>
        <div className="solid-kernel"><span>WRITER</span><strong>OpenCascade 7.9</strong><span>VERIFIER</span><strong>Isolated STEP re-import</strong></div>
      </section>

      <section className="solid-workbench">
        <aside className="solid-sidebar">
          <div className="lab-panel-label"><span>PART FAMILY</span><b>03 PRESETS</b></div>
          {(Object.keys(PRESETS) as Family[]).map((family, index) => <button key={family} type="button" className={draft.family === family ? "active" : ""} onClick={() => { setDraft(PRESETS[family]); setResult(null); }}><span>0{index + 1}</span><strong>{family.replace("_", " ")}</strong><small>{family === "mounting_plate" ? "Equipment interface" : family === "angle_bracket" ? "Ship / plant support" : "Utility connection"}</small></button>)}
          <div className="solid-contract-meta"><label><span>Project</span><input value={draft.projectName} onChange={(event) => setDraft({ ...draft, projectName: event.target.value })} /></label><label><span>Revision</span><input value={draft.revision} onChange={(event) => setDraft({ ...draft, revision: event.target.value })} /></label></div>
        </aside>

        <section className="solid-properties" aria-labelledby="solid-properties-title">
          <div className="lab-panel-label"><span id="solid-properties-title">EXACT PROPERTIES</span><b>WCS · mm</b></div>
          <div className="solid-field-grid">
            {draft.family !== "flange" && <><Field label="Width X" value={draft.width} onChange={(value) => setNumber("width", value)} /><Field label="Depth Y" value={draft.depth} onChange={(value) => setNumber("depth", value)} /></>}
            <Field label="Thickness Z" value={draft.thickness} onChange={(value) => setNumber("thickness", value)} />
            {draft.family === "mounting_plate" && <><Field label="Corner radius" value={draft.cornerRadius} onChange={(value) => setNumber("cornerRadius", value)} min={0} /><Field label="Hole diameter" value={draft.holeDiameter} onChange={(value) => setNumber("holeDiameter", value)} /><Field label="Hole center ±X" value={draft.holeX} onChange={(value) => setNumber("holeX", value)} /><Field label="Hole center ±Y" value={draft.holeY} onChange={(value) => setNumber("holeY", value)} /></>}
            {draft.family === "angle_bracket" && <><Field label="Vertical height" value={draft.verticalHeight} onChange={(value) => setNumber("verticalHeight", value)} /><Field label="Vertical thickness" value={draft.verticalThickness} onChange={(value) => setNumber("verticalThickness", value)} /><Field label="Base hole diameter" value={draft.holeDiameter} onChange={(value) => setNumber("holeDiameter", value)} /><Field label="Hole center ±X" value={draft.holeX} onChange={(value) => setNumber("holeX", value)} /><Field label="Hole center Y" value={draft.holeY} onChange={(value) => setNumber("holeY", value)} /></>}
            {draft.family === "flange" && <><Field label="Outer diameter" value={draft.outerDiameter} onChange={(value) => setNumber("outerDiameter", value)} /><Field label="Inner diameter" value={draft.innerDiameter} onChange={(value) => setNumber("innerDiameter", value)} /><Field label="Bolt circle" value={draft.boltCircleDiameter} onChange={(value) => setNumber("boltCircleDiameter", value)} /><Field label="Bolt hole diameter" value={draft.boltHoleDiameter} onChange={(value) => setNumber("boltHoleDiameter", value)} /><Field label="Bolt hole count" value={draft.boltHoleCount} unit="ea" step={1} min={2} onChange={(value) => setNumber("boltHoleCount", Math.round(value))} /></>}
            <Field label="Verification tolerance" value={draft.tolerance} unit="mm" step={0.001} min={0.001} onChange={(value) => setNumber("tolerance", value)} />
          </div>
          <details className="solid-contract-json"><summary>Structured contract preview</summary><pre>{JSON.stringify(contract, null, 2)}</pre></details>
          <BackendReadinessNotice readiness={readiness} />
          <button data-testid="solid-run-button" type="button" className="lab-primary" disabled={loading || readiness.state !== "ready"} onClick={run}>{loading ? <><span className="lab-spinner" />OPEN CASCADE WORKERS RUNNING</> : readiness.state !== "ready" ? "BACKEND READINESS" : error ? "RETRY MANUALLY" : "GENERATE STEP + INDEPENDENTLY VERIFY"}</button>
          {error && <div className="lab-error" role="alert"><strong>CONTRACT / KERNEL ERROR</strong><span>{error}</span><button type="button" onClick={run}>수동 재시도</button></div>}
        </section>

        <section className="solid-preview-panel">
          <div className="lab-panel-label"><span>ACTUAL STEP TESSELLATION</span><b>{result ? result.status.toUpperCase() : "AWAITING RUN"}</b></div>
          {result?.preview_mesh ? <MeshPreview mesh={result.preview_mesh} label={draft.projectName} /> : <div className="solid-empty-preview"><svg viewBox="0 0 200 150" aria-hidden="true"><path d="m38 48 65-28 62 31-67 32zM38 48v58l60 28V83M165 51v58l-67 25" /></svg><strong>{draft.family.replace("_", " ")}</strong><span>Run the isolated STEP pipeline</span></div>}
          <div className="solid-pipeline">{["Contract locked", "STEP written", "STEP reopened", "Remeasured", "Approved"].map((label, index) => <article key={label} className={pipeline[index]}><span>0{index + 1}</span><div><strong>{label}</strong><code>{pipeline[index]}</code></div></article>)}</div>
        </section>
      </section>

      {result && <section className="solid-results" id="solid-evidence" data-testid="solid-results">
        <div className="lab-result-heading"><div><span>INDEPENDENT STEP EVIDENCE</span><h2>{result.status === "passed" ? "Serialized STEP remeasurement passed" : "Official solid bundle blocked"}</h2><p>Writer memory가 아니라 저장된 STEP을 별도 worker에서 다시 읽은 수치입니다.</p></div><div className={`lab-status ${result.status === "passed" ? "audited" : "failed_verification"}`} role="status"><strong>{result.status === "passed" ? "VERIFIED" : "FAILED"}</strong><small>{String(result.summary.dimension_pass_count || 0)}/{String(result.summary.dimension_count || 0)} DIMENSIONS</small></div></div>
        <div className="solid-summary-grid"><article><span>Volume</span><strong>{Number(result.summary.volume_mm3 || 0).toLocaleString()}</strong><small>mm³</small></article><article><span>Surface area</span><strong>{Number(result.summary.surface_area_mm2 || 0).toLocaleString()}</strong><small>mm²</small></article><article><span>Faces / edges</span><strong>{String(result.summary.face_count)} / {String(result.summary.edge_count)}</strong><small>OpenCascade topology</small></article><article><span>Cylindrical surfaces</span><strong>{String(result.summary.cylindrical_surface_count)}</strong><small>diameter + axis checked</small></article></div>
        <div className="lab-compare-hashes"><article><span>CONTRACT</span><code>{result.contract_hash}</code></article><article><span>STEP ARTIFACT</span><code>{result.artifact_hash || "not created"}</code></article></div>
        <div className="solid-downloads"><button data-testid="solid-download-step" type="button" disabled={!result.step_base64} onClick={() => result.step_base64 && saveBase64("datumguard-solid.step", result.step_base64, "model/step")}>DOWNLOAD STEP</button><button data-testid="solid-download-bundle" type="button" disabled={!result.bundle_base64} onClick={() => result.bundle_base64 && saveBase64("datumguard-solid-verified.zip", result.bundle_base64, "application/zip")}>STEP + PDF + JSON BUNDLE</button></div>
        <div className="table-scroll"><table><thead><tr><th>Dimension</th><th>Target</th><th>Actual</th><th>Deviation</th><th>Tolerance</th><th>Decision</th></tr></thead><tbody>{result.measurements.map((item) => <tr key={item.dimension_id}><td><code>{item.dimension_id}</code></td><td>{item.target.toFixed(3)}</td><td>{item.actual.toFixed(3)}</td><td>{item.deviation.toFixed(6)}</td><td>{item.tolerance_lower} / +{item.tolerance_upper}</td><td><span className={item.passed ? "solid-pass" : "solid-fail"}>{item.passed ? "PASS" : "FAIL"}</span></td></tr>)}</tbody></table></div>
        {result.violations.length > 0 && <div className="lab-issues">{result.violations.map((violation) => <article className="error" key={`${violation.code}-${violation.entity_ids.join("-")}`}><span>blocked</span><code>{violation.code}</code><div><strong>{violation.message}</strong><small>{violation.entity_ids.join(", ")}</small></div></article>)}</div>}
      </section>}

      <section className="lab-boundary"><span>ENGINEERING BOUNDARY</span><h2>정확한 STEP은 안전 인증이 아닙니다.</h2><p>형상, 치수, topology evidence만 검증합니다. 구조강도, 용접, 압력, 재료와 산업규격은 자격 있는 엔지니어가 별도로 승인해야 합니다. <Link href="/privacy">Privacy & local data</Link></p></section>
    </main>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import BackendReadinessNotice from "@/app/components/backend-readiness";
import LocalDraftNotice from "@/app/components/local-draft-notice";
import { apiErrorMessage, apiPostJson } from "@/lib/api-client";
import { loadDraft, saveDraft } from "@/lib/draft-db";
import { useBackendReadiness } from "@/lib/use-backend-readiness";
import ArchitectureWorkspace from "./architecture-workspace";

type Units = "mm" | "inch";
type Process = "laser" | "cnc" | "manual" | "custom";
type FeatureType = "circular_hole" | "slot" | "rectangular_cutout";

type FeatureDraft = {
  id: string;
  type: FeatureType;
  x: number;
  y: number;
  a: number;
  b: number;
  movable: boolean;
};

type Draft = {
  projectName: string;
  revision: string;
  units: Units;
  width: number;
  height: number;
  process: Process;
  kerf: number;
  minimumFeature: number;
  minimumLigament: number;
  edgeDistance: number;
  tolerance: number;
  intentText: string;
  features: FeatureDraft[];
};

type Measurement = {
  measurement_id: string;
  dimension_id: string;
  target: number;
  actual: number;
  deviation: number;
  tolerance_lower: number;
  tolerance_upper: number;
  passed: boolean;
};

type Violation = {
  code: string;
  message: string;
  entity_ids: string[];
  repairable: boolean;
  details: Record<string, unknown>;
};

type ApiResult = {
  status: string;
  contract_hash: string;
  artifact_hash: string | null;
  measurements: Measurement[];
  violations: Violation[];
  evidence: Array<Record<string, unknown>>;
  preview_svg?: string;
  bundle_base64?: string | null;
  error?: { code: string; message: string } | null;
};

const DEFAULT_DRAFT: Draft = {
  projectName: "Mounting plate 01",
  revision: "A",
  units: "mm",
  width: 160,
  height: 100,
  process: "laser",
  kerf: 0.2,
  minimumFeature: 1,
  minimumLigament: 2,
  edgeDistance: 3,
  tolerance: 0.1,
  intentText: "",
  features: [
    { id: "hole-a", type: "circular_hole", x: 20, y: 20, a: 8, b: 0, movable: false },
    { id: "hole-b", type: "circular_hole", x: 140, y: 80, a: 8, b: 0, movable: false },
    { id: "slot-a", type: "slot", x: 80, y: 50, a: 30, b: 10, movable: true },
    {
      id: "cutout-a",
      type: "rectangular_cutout",
      x: 112,
      y: 30,
      a: 18,
      b: 24,
      movable: false,
    },
  ],
};

const SHIP_BRACKET_DRAFT: Draft = {
  projectName: "Ship stiffener bracket plate",
  revision: "A",
  units: "mm",
  width: 240,
  height: 180,
  process: "laser",
  kerf: 0.3,
  minimumFeature: 4,
  minimumLigament: 8,
  edgeDistance: 12,
  tolerance: 0.5,
  intentText: "합성 조선 브래킷 예제. 구조강도와 용접 적합성은 판정하지 않습니다.",
  features: [
    { id: "bolt-a", type: "circular_hole", x: 30, y: 30, a: 14, b: 0, movable: false },
    { id: "bolt-b", type: "circular_hole", x: 210, y: 30, a: 14, b: 0, movable: false },
    { id: "lift-slot", type: "slot", x: 120, y: 145, a: 60, b: 18, movable: true },
    { id: "access-cutout", type: "rectangular_cutout", x: 90, y: 65, a: 60, b: 42, movable: false },
  ],
};

const SEMICON_PANEL_DRAFT: Draft = {
  projectName: "Semiconductor tool interface panel",
  revision: "A",
  units: "mm",
  width: 300,
  height: 200,
  process: "cnc",
  kerf: 0.1,
  minimumFeature: 2,
  minimumLigament: 6,
  edgeDistance: 10,
  tolerance: 0.1,
  intentText: "합성 장비 interface panel 예제. 실제 장비 vendor drawing을 대체하지 않습니다.",
  features: [
    { id: "mount-a", type: "circular_hole", x: 25, y: 25, a: 10, b: 0, movable: false },
    { id: "mount-b", type: "circular_hole", x: 275, y: 25, a: 10, b: 0, movable: false },
    { id: "mount-c", type: "circular_hole", x: 25, y: 175, a: 10, b: 0, movable: false },
    { id: "mount-d", type: "circular_hole", x: 275, y: 175, a: 10, b: 0, movable: false },
    { id: "cable-slot", type: "slot", x: 90, y: 100, a: 70, b: 20, movable: true },
    { id: "utility-window", type: "rectangular_cutout", x: 165, y: 65, a: 80, b: 70, movable: false },
  ],
};

const GITHUB_URL = process.env.NEXT_PUBLIC_GITHUB_URL || "https://github.com";

function numberValue(value: string, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildContract(draft: Draft) {
  const features = draft.features.map((feature) => {
    if (feature.type === "circular_hole") {
      return {
        id: feature.id,
        type: feature.type,
        center: [feature.x, feature.y],
        diameter: feature.a,
      };
    }
    if (feature.type === "slot") {
      return {
        id: feature.id,
        type: feature.type,
        center: [feature.x, feature.y],
        length: feature.a,
        width: feature.b,
        angle_deg: 0,
      };
    }
    return {
      id: feature.id,
      type: feature.type,
      origin: [feature.x, feature.y],
      width: feature.a,
      height: feature.b,
      corner_radius: 0,
    };
  });

  const dimensions: Array<Record<string, unknown>> = [
    {
      id: "dim-outline-width",
      path: "outline.width",
      target: draft.width,
      tolerance_lower: -draft.tolerance,
      tolerance_upper: draft.tolerance,
      locked: true,
      source: { kind: "form", ref: "outline-width" },
    },
    {
      id: "dim-outline-height",
      path: "outline.height",
      target: draft.height,
      tolerance_lower: -draft.tolerance,
      tolerance_upper: draft.tolerance,
      locked: true,
      source: { kind: "form", ref: "outline-height" },
    },
  ];
  const freeParameters: Array<Record<string, unknown>> = [];

  draft.features.forEach((feature) => {
    const coordinate = feature.type === "rectangular_cutout" ? "origin" : "center";
    (["0", "1"] as const).forEach((axis, axisIndex) => {
      const path = `features.${feature.id}.${coordinate}.${axis}`;
      dimensions.push({
        id: `dim-${feature.id}-${coordinate}-${axis}`,
        path,
        target: axisIndex === 0 ? feature.x : feature.y,
        tolerance_lower: -draft.tolerance,
        tolerance_upper: draft.tolerance,
        locked: !feature.movable,
        source: { kind: "form", ref: `${feature.id}-${axis}` },
      });
      if (feature.movable) {
        freeParameters.push({
          id: `free-${feature.id}-${axis}`,
          path,
          minimum: 0,
          maximum: axisIndex === 0 ? draft.width : draft.height,
          step: draft.units === "mm" ? 0.001 : 0.0001,
          unit: draft.units,
        });
      }
    });

    const sizeFields =
      feature.type === "circular_hole"
        ? [["diameter", feature.a]]
        : feature.type === "slot"
          ? [
              ["length", feature.a],
              ["width", feature.b],
            ]
          : [
              ["width", feature.a],
              ["height", feature.b],
            ];
    sizeFields.forEach(([field, target]) => {
      dimensions.push({
        id: `dim-${feature.id}-${field}`,
        path: `features.${feature.id}.${field}`,
        target,
        tolerance_lower: -draft.tolerance,
        tolerance_upper: draft.tolerance,
        locked: true,
        source: { kind: "form", ref: `${feature.id}-${field}` },
      });
    });
  });

  const allIds = ["outline-plate", ...draft.features.map((feature) => feature.id)];
  return {
    schema_version: "1.0.0",
    units: draft.units,
    datum: {
      id: "datum-main",
      origin: [0, 0],
      x_axis: [1, 0],
      y_axis: [0, 1],
      plane: "XY",
      locked: true,
    },
    outline: {
      id: "outline-plate",
      type: "rectangle",
      origin: [0, 0],
      width: draft.width,
      height: draft.height,
    },
    features,
    dimensions,
    constraints: [
      {
        id: "constraint-containment",
        type: "features_inside_outline",
        entity_ids: allIds,
        parameters: { minimum_edge_distance: draft.edgeDistance },
        required: true,
      },
      {
        id: "constraint-non-overlap",
        type: "non_overlap",
        entity_ids: draft.features.map((feature) => feature.id),
        parameters: { minimum_ligament: draft.minimumLigament },
        required: true,
      },
    ],
    free_parameters: freeParameters,
    manufacturing_profile: {
      id: `profile-${draft.process}`,
      process: draft.process,
      kerf: draft.kerf,
      tool_diameter: null,
      minimum_feature: draft.minimumFeature,
      minimum_ligament: draft.minimumLigament,
      confirmed_by_user: true,
    },
    metadata: {
      project_name: draft.projectName,
      revision: draft.revision,
      notes: "Created with the public DatumGuard form",
    },
    contract_hash: null,
    intent_text: draft.intentText || null,
  };
}

function LivePreview({ draft }: { draft: Draft }) {
  const padding = Math.max(draft.width, draft.height) * 0.08;
  const y = (value: number) => draft.height - value;
  return (
    <svg
      className="live-drawing"
      viewBox={`${-padding} ${-padding} ${draft.width + padding * 2} ${draft.height + padding * 2}`}
      role="img"
      aria-label={`${draft.projectName} 실시간 형상 미리보기`}
    >
      <rect className="plate" x="0" y="0" width={draft.width} height={draft.height} rx="1" />
      <g className="datum-axis">
        <line x1="0" y1={draft.height} x2={Math.min(18, draft.width / 5)} y2={draft.height} />
        <line x1="0" y1={draft.height} x2="0" y2={Math.max(0, draft.height - 18)} />
      </g>
      {draft.features.map((feature) => {
        if (feature.type === "circular_hole") {
          return (
            <circle
              className="cut"
              key={feature.id}
              cx={feature.x}
              cy={y(feature.y)}
              r={feature.a / 2}
            />
          );
        }
        if (feature.type === "slot") {
          return (
            <rect
              className="cut"
              key={feature.id}
              x={feature.x - feature.a / 2}
              y={y(feature.y) - feature.b / 2}
              width={feature.a}
              height={feature.b}
              rx={feature.b / 2}
            />
          );
        }
        return (
          <rect
            className="cut"
            key={feature.id}
            x={feature.x}
            y={y(feature.y + feature.b)}
            width={feature.a}
            height={feature.b}
          />
        );
      })}
      <text x={draft.width / 2} y={draft.height + padding * 0.62} textAnchor="middle">
        {draft.width} × {draft.height} {draft.units}
      </text>
    </svg>
  );
}

function Field({
  label,
  value,
  onChange,
  suffix,
  min = 0,
  step = "any",
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  suffix?: string;
  min?: number;
  step?: number | "any";
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <span className="input-with-suffix">
        <input
          type="number"
          value={value}
          min={min}
          step={step}
          onChange={(event) => onChange(numberValue(event.target.value, value))}
        />
        {suffix && <small>{suffix}</small>}
      </span>
    </label>
  );
}

function PlateWorkspace() {
  const [draft, setDraft] = useState<Draft>(DEFAULT_DRAFT);
  const [hydrated, setHydrated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ApiResult | null>(null);
  const [intentResult, setIntentResult] = useState<ApiResult | null>(null);
  const [networkError, setNetworkError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<"intent" | "verify" | null>(null);
  const [storageError, setStorageError] = useState<string | null>(null);
  const readiness = useBackendReadiness("mechanical_ship_plate");

  useEffect(() => {
    loadDraft<Draft>()
      .then((saved) => {
        if (saved) setDraft(saved);
      })
      .catch((error) => setStorageError(error instanceof Error ? error.message : "로컬 draft를 읽지 못했습니다."))
      .finally(() => setHydrated(true));
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    const timer = window.setTimeout(() => {
      saveDraft(draft)
        .then(() => setStorageError(null))
        .catch((error) => setStorageError(error instanceof Error ? error.message : "로컬 draft를 저장하지 못했습니다."));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [draft, hydrated]);

  const contract = useMemo(() => buildContract(draft), [draft]);

  function updateFeature(id: string, changes: Partial<FeatureDraft>) {
    setDraft((current) => ({
      ...current,
      features: current.features.map((feature) =>
        feature.id === id ? { ...feature, ...changes } : feature,
      ),
    }));
  }

  function addFeature(type: FeatureType) {
    const index = draft.features.length + 1;
    const isHole = type === "circular_hole";
    setDraft((current) => ({
      ...current,
      features: [
        ...current.features,
        {
          id: `${type === "circular_hole" ? "hole" : type === "slot" ? "slot" : "cutout"}-${Date.now()}`,
          type,
          x: current.width / 2,
          y: current.height / 2,
          a: isHole ? 8 : type === "slot" ? 24 : 18,
          b: isHole ? 0 : type === "slot" ? 8 : 18,
          movable: false,
        },
      ],
    }));
    window.setTimeout(() => document.getElementById(`feature-${index}`)?.scrollIntoView(), 0);
  }

  async function request(path: string, body: unknown, timeoutMs = 60_000): Promise<ApiResult> {
    return apiPostJson<ApiResult>(path, body, { timeoutMs });
  }

  async function checkIntent() {
    if (readiness.state !== "ready") {
      setNetworkError("Backend readiness를 먼저 확인합니다. 준비 완료 후 수동으로 다시 시도하세요.");
      readiness.retry();
      return;
    }
    setLastAction("intent");
    setLoading(true);
    setNetworkError(null);
    try {
      setIntentResult(await request("/api/v1/contracts/draft", { contract, intent_text: draft.intentText }, 30_000));
    } catch (error) {
      setNetworkError(apiErrorMessage(error, "조건 모호성 확인 요청에 실패했습니다."));
    } finally {
      setLoading(false);
    }
  }

  async function runVerification() {
    if (readiness.state !== "ready") {
      setNetworkError("Backend readiness를 먼저 확인합니다. 준비 완료 후 수동으로 다시 시도하세요.");
      readiness.retry();
      return;
    }
    setLastAction("verify");
    setLoading(true);
    setNetworkError(null);
    setResult(null);
    try {
      setResult(await request("/api/v1/designs/run?auto_repair=true", contract));
    } catch (error) {
      setNetworkError(apiErrorMessage(error, "Plate 검증 요청에 실패했습니다."));
    } finally {
      setLoading(false);
    }
  }

  function downloadBundle() {
    if (!result?.bundle_base64 || result.status !== "passed") return;
    const binary = window.atob(result.bundle_base64);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `datumguard-${result.contract_hash.slice(7, 19)}.zip`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main data-testid="plate-designer">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="DatumGuard 처음으로">
          <span className="brand-mark" aria-hidden="true">DG</span>
          <span>DatumGuard</span>
        </a>
        <nav aria-label="주요 링크">
          <Link href="/">Architecture</Link>
          <Link href="/piping">Plant Piping</Link>
          <Link href="/solid">3D Solid</Link>
          <Link href="/intake">Artifact Lab</Link>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
        </nav>
      </header>

      <LocalDraftNotice error={storageError} onDismiss={() => setStorageError(null)} />

      <section className="hero" id="top">
        <div className="eyebrow">MECHANICAL / SHIP PLATE · CONTRACT → DXF → REMEASURE → APPROVE</div>
        <h1>보이는 도면이 아니라,<br /><em>측정된 도면</em>을 만드세요.</h1>
        <p>
          치수를 폼에 입력하면 R2013 DXF를 만들고, 저장된 파일을 다시 읽어 공차와 간섭을 검사합니다.
          검증에 실패한 도면은 공식 파일로 내려받을 수 없습니다.
        </p>
        <div className="hero-proof" aria-label="핵심 보증">
          <span><b>0.001 mm</b> 재측정 epsilon</span>
          <span><b>0회</b> locked 치수 자동변경</span>
          <span><b>2 kernels</b> writer / verifier 분리</span>
        </div>
      </section>

      <section className="workspace" id="designer">
        <div className="form-column">
          <div className="section-heading">
            <div><span className="step">01</span><h2>설계 계약</h2></div>
            <button className="text-button" type="button" onClick={() => setDraft(DEFAULT_DRAFT)}>
              샘플 초기화
            </button>
          </div>

          <div className="plate-presets" aria-label="기계·조선 plate 예제">
            <button type="button" onClick={() => setDraft(DEFAULT_DRAFT)}>Mounting plate</button>
            <button data-testid="plate-preset-ship" type="button" onClick={() => setDraft(SHIP_BRACKET_DRAFT)}>Ship bracket</button>
            <button data-testid="plate-preset-semiconductor" type="button" onClick={() => setDraft(SEMICON_PANEL_DRAFT)}>Semiconductor panel</button>
          </div>

          <div className="card form-grid two">
            <label className="field wide">
              <span>프로젝트 이름</span>
              <input
                value={draft.projectName}
                maxLength={120}
                onChange={(event) => setDraft({ ...draft, projectName: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Revision</span>
              <input
                value={draft.revision}
                maxLength={16}
                onChange={(event) => setDraft({ ...draft, revision: event.target.value })}
              />
            </label>
            <label className="field">
              <span>단위</span>
              <select
                value={draft.units}
                onChange={(event) => setDraft({ ...draft, units: event.target.value as Units })}
              >
                <option value="mm">millimeter</option>
                <option value="inch">inch</option>
              </select>
            </label>
            <Field label="폭 X" value={draft.width} suffix={draft.units} min={0.001} onChange={(width) => setDraft({ ...draft, width })} />
            <Field label="높이 Y" value={draft.height} suffix={draft.units} min={0.001} onChange={(height) => setDraft({ ...draft, height })} />
          </div>

          <div className="section-heading compact">
            <div><span className="step">02</span><h2>절단 Feature</h2></div>
            <div className="add-menu">
              <button type="button" onClick={() => addFeature("circular_hole")}>+ 홀</button>
              <button type="button" onClick={() => addFeature("slot")}>+ 슬롯</button>
              <button type="button" onClick={() => addFeature("rectangular_cutout")}>+ Cutout</button>
            </div>
          </div>

          <div className="feature-list">
            {draft.features.map((feature, index) => (
              <article className="feature-card" id={`feature-${index + 1}`} key={feature.id}>
                <div className="feature-title">
                  <span className={`feature-icon ${feature.type}`} aria-hidden="true" />
                  <div>
                    <strong>{feature.type === "circular_hole" ? "원형 홀" : feature.type === "slot" ? "슬롯" : "사각 Cutout"}</strong>
                    <small>{feature.id}</small>
                  </div>
                  <button
                    className="remove"
                    type="button"
                    aria-label={`${feature.id} 삭제`}
                    onClick={() => setDraft({ ...draft, features: draft.features.filter((item) => item.id !== feature.id) })}
                  >×</button>
                </div>
                <div className="feature-fields">
                  <Field label={feature.type === "rectangular_cutout" ? "원점 X" : "중심 X"} value={feature.x} suffix={draft.units} onChange={(x) => updateFeature(feature.id, { x })} />
                  <Field label={feature.type === "rectangular_cutout" ? "원점 Y" : "중심 Y"} value={feature.y} suffix={draft.units} onChange={(yValue) => updateFeature(feature.id, { y: yValue })} />
                  <Field label={feature.type === "circular_hole" ? "직경" : feature.type === "slot" ? "전체 길이" : "폭"} value={feature.a} suffix={draft.units} min={0.001} onChange={(a) => updateFeature(feature.id, { a })} />
                  {feature.type !== "circular_hole" && (
                    <Field label={feature.type === "slot" ? "슬롯 폭" : "높이"} value={feature.b} suffix={draft.units} min={0.001} onChange={(b) => updateFeature(feature.id, { b })} />
                  )}
                </div>
                <label className="check-row">
                  <input type="checkbox" checked={feature.movable} onChange={(event) => updateFeature(feature.id, { movable: event.target.checked })} />
                  <span>검증 실패 시 위치만 선언 범위에서 자동수정 허용</span>
                </label>
              </article>
            ))}
          </div>

          <div className="section-heading compact">
            <div><span className="step">03</span><h2>제작·공차 조건</h2></div>
          </div>
          <div className="card form-grid three">
            <label className="field">
              <span>공정</span>
              <select value={draft.process} onChange={(event) => setDraft({ ...draft, process: event.target.value as Process })}>
                <option value="laser">Laser</option><option value="cnc">CNC</option><option value="manual">Manual</option><option value="custom">Custom</option>
              </select>
            </label>
            <Field label="Kerf" value={draft.kerf} suffix={draft.units} onChange={(kerf) => setDraft({ ...draft, kerf })} />
            <Field label="치수 공차 ±" value={draft.tolerance} suffix={draft.units} onChange={(tolerance) => setDraft({ ...draft, tolerance })} />
            <Field label="최소 Feature" value={draft.minimumFeature} suffix={draft.units} onChange={(minimumFeature) => setDraft({ ...draft, minimumFeature })} />
            <Field label="최소 Ligament" value={draft.minimumLigament} suffix={draft.units} onChange={(minimumLigament) => setDraft({ ...draft, minimumLigament })} />
            <Field label="최소 Edge 거리" value={draft.edgeDistance} suffix={draft.units} onChange={(edgeDistance) => setDraft({ ...draft, edgeDistance })} />
          </div>

          <div className="intent card">
            <label className="field">
              <span>자연어 추가 조건 <small>선택</small></span>
              <textarea
                value={draft.intentText}
                maxLength={2000}
                rows={3}
                placeholder="예: 네 모서리 홀은 대칭이어야 한다. 숫자와 단위는 위 폼에서 확정합니다."
                onChange={(event) => setDraft({ ...draft, intentText: event.target.value })}
              />
            </label>
            <div className="intent-footer">
              <p>AI가 원문에 없는 숫자·단위·좌표를 추정하지 않습니다.</p>
              <button type="button" className="secondary-button" disabled={loading || readiness.state !== "ready" || !draft.intentText.trim()} onClick={checkIntent}>조건 모호성 확인</button>
            </div>
            {intentResult && (
              <div className={`inline-status ${intentResult.status === "ready" ? "pass" : "warn"}`}>
                <strong>{intentResult.status}</strong>
                <span>{intentResult.violations[0]?.message || "폼 값과 충돌하는 조건을 찾지 못했습니다."}</span>
              </div>
            )}
          </div>
        </div>

        <aside className="preview-column">
          <div className="preview-sticky">
            <div className="preview-header"><div><span>WCS XY</span><strong>Canonical preview</strong></div><span className="draft-badge">PREVIEW ONLY</span></div>
            <div className="preview-canvas"><LivePreview draft={draft} /></div>
            <div className="preview-meta">
              <span>Origin <b>0, 0</b></span><span>Features <b>{draft.features.length}</b></span><span>Units <b>{draft.units}</b></span>
            </div>
            <BackendReadinessNotice readiness={readiness} />
            <button className="primary-button" type="button" disabled={loading || readiness.state !== "ready" || !draft.features.length} onClick={runVerification}>
              {loading ? <><span className="spinner" /> 생성·재측정 중</> : readiness.state !== "ready" ? <>Backend readiness</> : networkError && lastAction === "verify" ? <>수동 검증 재시도 <span>→</span></> : <>DXF 생성 및 독립 검증 <span>→</span></>}
            </button>
            <p className="approval-note"><span aria-hidden="true">⌁</span> 검증 통과 전에는 공식 ZIP을 만들지 않습니다.</p>
          </div>
        </aside>
      </section>

      <section className="results" id="verification">
        <div className="section-heading results-heading"><div><span className="step">04</span><h2>검증 결과</h2></div></div>
        {!result && !networkError && <div className="empty-result"><span>⌖</span><p>도면을 생성하면 DXF에서 다시 읽은 측정값이 여기에 표시됩니다.</p></div>}
        {networkError && <div className="result-banner failed"><strong>연결 실패</strong><p>{networkError}</p><button type="button" className="secondary-button" onClick={lastAction === "intent" ? checkIntent : runVerification}>수동 재시도</button></div>}
        {result && (
          <div className="result-shell">
            <div className={`result-banner ${result.status === "passed" ? "passed" : "failed"}`}>
              <div className="status-symbol" aria-hidden="true">{result.status === "passed" ? "✓" : "!"}</div>
              <div><span>INDEPENDENT DXF VERIFICATION</span><h3>{result.status === "passed" ? "모든 필수 검사를 통과했습니다" : "공식 산출물이 차단되었습니다"}</h3><p>{result.error?.message || "직렬화된 DXF를 별도 reader로 재측정했습니다."}</p></div>
              <button type="button" className="download-button" disabled={result.status !== "passed" || !result.bundle_base64} onClick={downloadBundle}>검증 ZIP 받기 ↓</button>
            </div>
            <div className="hash-grid"><div><span>Contract hash</span><code>{result.contract_hash}</code></div><div><span>Artifact hash</span><code>{result.artifact_hash || "not created"}</code></div></div>
            {result.measurements.length > 0 && (
              <div className="table-wrap"><table><thead><tr><th>Dimension ID</th><th>Target</th><th>Actual</th><th>Deviation</th><th>Tolerance</th><th>판정</th></tr></thead><tbody>{result.measurements.map((item) => <tr key={item.measurement_id}><td><code>{item.dimension_id}</code></td><td>{item.target.toFixed(3)}</td><td>{item.actual.toFixed(3)}</td><td>{item.deviation.toFixed(6)}</td><td>{item.tolerance_lower} / +{item.tolerance_upper}</td><td><span className={`pill ${item.passed ? "pass" : "fail"}`}>{item.passed ? "PASS" : "FAIL"}</span></td></tr>)}</tbody></table></div>
            )}
            {result.violations.length > 0 && <div className="violation-list"><h3>확인할 항목</h3>{result.violations.map((item, index) => <article key={`${item.code}-${index}`}><code>{item.code}</code><div><strong>{item.message}</strong><p>{item.entity_ids.join(", ") || "contract"}</p></div><span>{item.repairable ? "수정 가능" : "잠금/필수"}</span></article>)}</div>}
          </div>
        )}
      </section>

      <section className="boundary"><div><span>NOT A CERTIFICATION</span><h2>정확한 파일과 안전한 설계는 같은 말이 아닙니다.</h2></div><p>DatumGuard MVP는 파일의 치수·공차·간섭을 검사합니다. 구조 안전, 법규, 재료 성능, 공정 적합성은 자격 있는 엔지니어와 제작자가 별도로 검토해야 합니다. PDF는 <b>DO NOT SCALE</b>이며 검증 ZIP의 DXF만 제작 기준입니다.</p></section>
      <footer><span>DatumGuard / Open engineering accuracy harness</span><span>Stateless · No account · No server project storage · <Link href="/privacy">Privacy & local data</Link></span></footer>
    </main>
  );
}

export default function Home() {
  const pathname = usePathname();

  if (pathname.startsWith("/plate")) {
    return <PlateWorkspace />;
  }

  return <ArchitectureWorkspace />;
}

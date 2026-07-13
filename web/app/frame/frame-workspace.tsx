"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { API_URL } from "@/lib/api-client";

import FrameAssuranceLab from "./frame-assurance-lab";
import styles from "./frame.module.css";

const repositoryUrl =
  process.env.NEXT_PUBLIC_GITHUB_URL || "https://github.com/tjwnsdhfz/datumguard";
const releaseUrl = `${repositoryUrl.replace(/\/$/, "")}/releases/tag/v0.4.0`;

type PresetId = "verified" | "missing-brace";
type EngineState = "checking" | "offline" | "ready" | "warming";
type RunState = "idle" | "running" | "passed" | "failed";

type FrameNode = {
  id: string;
  point: [number, number];
  locked: boolean;
};

type FrameMember = {
  id: string;
  start_node_id: string;
  end_node_id: string;
  area_mm2: number;
  inertia_mm4: number;
  elastic_modulus_mpa: number;
  section_depth_mm: number;
  allowable_stress_mpa: number;
  locked: boolean;
};

type FrameLoad = {
  id: string;
  node_id: string;
  fx_n: number;
  fy_n: number;
  mz_nmm: number;
};

type FrameSupport = {
  id: string;
  node_id: string;
  ux: boolean;
  uy: boolean;
  rz: boolean;
};

export type FrameContract = {
  schema_version: "1.0.0";
  design_kind: "structural_frame";
  units: "mm";
  nodes: FrameNode[];
  members: FrameMember[];
  loads: FrameLoad[];
  supports: FrameSupport[];
  limits: {
    max_displacement_mm: number;
    allowable_stress_mpa: number;
  };
  free_parameters: Array<Record<string, unknown>>;
  metadata: {
    project_name: string;
    revision: string;
    notes: string;
  };
};

type Violation = {
  code?: string;
  message?: string;
  entity_ids?: string[];
  repairable?: boolean;
};

type TimelineItem = {
  stage?: string;
  status?: string;
};

type RepairProposal = {
  id?: string;
  member_id?: string;
  description?: string;
  action?: string;
  predicted_utilization?: number;
};

type FrameResult = {
  status: string;
  contract_hash?: string;
  artifact_hash?: string | null;
  preview_svg?: string;
  measurements?: Array<Record<string, unknown>>;
  violations?: Violation[];
  evidence?: Array<Record<string, unknown>>;
  summary?: {
    max_displacement_mm?: number;
    governing_member_id?: string;
    max_utilization?: number;
    node_count?: number;
    member_count?: number;
    solver?: string;
    [key: string]: unknown;
  };
  timeline?: TimelineItem[];
  repair_proposals?: RepairProposal[];
  error?: { code?: string; message?: string } | null;
};

type IconName =
  | "analysis"
  | "arrow"
  | "check"
  | "fit"
  | "layers"
  | "rack"
  | "risk"
  | "warning";

const BAY = 6000;
const LEVEL = 4000;
const VIEW_WIDTH = 760;
const VIEW_HEIGHT = 520;
const PLOT = { left: 62, right: 716, top: 72, bottom: 448 };

const NODE_POSITIONS = [
  [0, 0], [6000, 0], [12000, 0], [18000, 0], [24000, 0],
  [0, 4000], [6000, 4000], [12000, 4000], [18000, 4000], [24000, 4000],
  [0, 8000], [6000, 8000], [12000, 8000], [18000, 8000], [24000, 8000],
] as const;

function nodeId(index: number) {
  return `N${String(index + 1).padStart(2, "0")}`;
}

function member(
  id: string,
  start: number,
  end: number,
  family: "beam" | "brace" | "column",
): FrameMember {
  const profiles = {
    column: { area_mm2: 9210, inertia_mm4: 210_000_000, section_depth_mm: 350 },
    beam: { area_mm2: 7810, inertia_mm4: 166_000_000, section_depth_mm: 300 },
    brace: { area_mm2: 3480, inertia_mm4: 19_800_000, section_depth_mm: 175 },
  };
  return {
    id,
    start_node_id: nodeId(start),
    end_node_id: nodeId(end),
    ...profiles[family],
    elastic_modulus_mpa: 200_000,
    allowable_stress_mpa: 215,
    locked: true,
  };
}

function memberFamily(item: FrameMember): "beam" | "brace" | "column" {
  if (item.id.startsWith("BR")) return "brace";
  if (item.id.startsWith("B")) return "beam";
  return "column";
}

const ALL_MEMBERS: FrameMember[] = [
  ...[0, 1, 2, 3, 4].flatMap((column, index) => [
    member(`C${String(index * 2 + 1).padStart(2, "0")}`, column, column + 5, "column"),
    member(`C${String(index * 2 + 2).padStart(2, "0")}`, column + 5, column + 10, "column"),
  ]),
  ...[0, 1, 2, 3].flatMap((bay, index) => [
    member(`B${String(index * 2 + 1).padStart(2, "0")}`, bay + 5, bay + 6, "beam"),
    member(`B${String(index * 2 + 2).padStart(2, "0")}`, bay + 10, bay + 11, "beam"),
  ]),
  member("BR01", 0, 6, "brace"),
  member("BR02", 1, 5, "brace"),
  member("BR03", 6, 12, "brace"),
  member("BR04", 7, 11, "brace"),
  member("BR05", 2, 8, "brace"),
  member("BR06", 3, 7, "brace"),
  member("BR07", 8, 14, "brace"),
  member("BR08", 9, 13, "brace"),
];

function buildContract(preset: PresetId): FrameContract {
  const isFailure = preset === "missing-brace";
  return {
    schema_version: "1.0.0",
    design_kind: "structural_frame",
    units: "mm",
    nodes: NODE_POSITIONS.map(([x, y], index) => ({
      id: nodeId(index),
      point: [x, y],
      locked: true,
    })),
    members: ALL_MEMBERS.filter((item) => !(isFailure && item.id === "BR04")),
    loads: [10, 11, 12, 13, 14].map((index) => ({
      id: `LC1-${nodeId(index)}`,
      node_id: nodeId(index),
      fx_n: 12_000,
      fy_n: -42_000,
      mz_nmm: 0,
    })),
    supports: [0, 1, 2, 3, 4].map((index) => ({
      id: `SUP-${nodeId(index)}`,
      node_id: nodeId(index),
      ux: true,
      uy: true,
      rz: true,
    })),
    limits: {
      max_displacement_mm: 0.65,
      allowable_stress_mpa: 215,
    },
    free_parameters: [],
    metadata: {
      project_name: "Semiconductor Utility Pipe Rack PR-101",
      revision: isFailure ? "FAIL-01" : "A",
      notes: `${preset}; linear_static_2d; screening_only`,
    },
  };
}

const FALLBACK_TIMELINE: TimelineItem[] = [
  { stage: "Contract locked", status: "waiting" },
  { stage: "Graph assembled", status: "waiting" },
  { stage: "Solver executed", status: "waiting" },
  { stage: "Response checked", status: "waiting" },
  { stage: "Screening decision", status: "waiting" },
];

function Icon({ name }: { name: IconName }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.7,
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" {...common}>
      {name === "analysis" && <><path d="M4 19V9m6 10V5m6 14v-7m4 7H2" /><path d="m3 6 6-3 6 5 6-5" /></>}
      {name === "arrow" && <><path d="M12 3v15m-5-5 5 5 5-5" /><path d="M5 21h14" /></>}
      {name === "check" && <><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></>}
      {name === "fit" && <path d="M9 4H4v5m11-5h5v5M4 15v5h5m11-5v5h-5" />}
      {name === "layers" && <><path d="m12 3 9 5-9 5-9-5z" /><path d="m3 12 9 5 9-5m-18 5 9 5 9-5" /></>}
      {name === "rack" && <><path d="M4 20V5m16 15V5M4 9h16M4 15h16" /><path d="m4 15 8-6 8 6" /></>}
      {name === "risk" && <><path d="M4 19 9 9l4 5 3-8 4 13" /><path d="M3 19h18" /></>}
      {name === "warning" && <><path d="m12 3 10 18H2z" /><path d="M12 9v5m0 3h.01" /></>}
    </svg>
  );
}

function screenPoint(node: FrameNode, deformationScale: number, showDeformed: boolean, failed: boolean) {
  const [x, y] = node.point;
  const baseX = PLOT.left + (x / (BAY * 4)) * (PLOT.right - PLOT.left);
  const baseY = PLOT.bottom - (y / (LEVEL * 2)) * (PLOT.bottom - PLOT.top);
  if (!showDeformed || y === 0) return { x: baseX, y: baseY };
  const ratio = y / (LEVEL * 2);
  const drift = (failed ? 2.1 : 0.75) * deformationScale * ratio * ratio;
  const sag = y === LEVEL ? deformationScale * 0.08 : deformationScale * 0.14;
  return { x: baseX + drift, y: baseY + sag * Math.sin((x / (BAY * 4)) * Math.PI) };
}

function compactHash(value?: string | null) {
  if (!value) return "not created";
  return value.length > 26 ? `${value.slice(0, 15)}…${value.slice(-8)}` : value;
}

function stageLabel(stage?: string) {
  if (!stage) return "Unknown stage";
  const labels: Record<string, string> = {
    contract_validation: "Contract locked",
    graph_assembly: "Graph assembled",
    structural_analysis: "Solver executed",
    solver_analysis: "Solver executed",
    response_verification: "Response checked",
    verification: "Response checked",
    screening_decision: "Screening decision",
  };
  return labels[stage] ?? stage.replaceAll("_", " ");
}

function normalizedStatus(status?: string): RunState {
  const value = status?.toLowerCase() ?? "";
  if (["pass", "passed", "approved", "verified"].includes(value)) return "passed";
  if (value && !["idle", "running", "pending"].includes(value)) return "failed";
  return value === "running" ? "running" : "idle";
}

function metric(value: number | undefined, digits = 2) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function safeSvgDataUrl(svg?: string) {
  if (!svg || !svg.trim().startsWith("<svg")) return null;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export default function FrameWorkspace() {
  const [preset, setPreset] = useState<PresetId>("verified");
  const [selectedMemberId, setSelectedMemberId] = useState("BR04");
  const [showDeformed, setShowDeformed] = useState(true);
  const [deformationScale, setDeformationScale] = useState(12);
  const [engineState, setEngineState] = useState<EngineState>("checking");
  const [runState, setRunState] = useState<RunState>("idle");
  const [result, setResult] = useState<FrameResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const contract = useMemo(() => buildContract(preset), [preset]);
  const nodes = useMemo(
    () => new Map(contract.nodes.map((node) => [node.id, node])),
    [contract],
  );
  const failed = runState === "failed" || preset === "missing-brace";
  const summary = result?.summary ?? {};
  const governingMember =
    summary.governing_member_id ??
    (runState === "failed" ? "C08" : runState === "passed" ? "BR04" : "");
  const selectedMember = contract.members.find((item) => item.id === selectedMemberId);
  const timeline = result?.timeline?.length ? result.timeline : FALLBACK_TIMELINE;
  const serverPreview = safeSvgDataUrl(result?.preview_svg);

  const checkBackend = useCallback(async () => {
    setEngineState("checking");
    try {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 5_500);
      const response = await fetch(`${API_URL}/api/v1/ready`, {
        cache: "no-store",
        signal: controller.signal,
      });
      window.clearTimeout(timeout);
      setEngineState(response.ok ? "ready" : "warming");
    } catch {
      setEngineState("offline");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void checkBackend(), 0);
    return () => window.clearTimeout(timer);
  }, [checkBackend]);

  function changePreset(next: PresetId) {
    setPreset(next);
    setSelectedMemberId(next === "verified" ? "BR04" : "C08");
    setRunState("idle");
    setResult(null);
    setError(null);
  }

  async function runAnalysis() {
    setRunState("running");
    setError(null);
    setResult(null);
    if (engineState !== "ready") setEngineState("warming");

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort("frame-analysis-timeout"), 90_000);
    try {
      const response = await fetch(
        `${API_URL}/api/v1/frame/designs/run?auto_repair=false`,
        {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify(contract),
          cache: "no-store",
          signal: controller.signal,
        },
      );
      const payload = (await response.json().catch(() => null)) as FrameResult | null;
      if (!response.ok || !payload) {
        const detail = payload?.error?.message || `Analysis API returned HTTP ${response.status}.`;
        throw new Error(detail);
      }
      setResult(payload);
      const nextState = normalizedStatus(payload.status);
      setRunState(nextState === "idle" ? "failed" : nextState);
      setEngineState("ready");
      if (payload.summary?.governing_member_id) {
        setSelectedMemberId(payload.summary.governing_member_id);
      }
    } catch (reason) {
      const isAbort = reason instanceof DOMException && reason.name === "AbortError";
      setError(
        isAbort
          ? "The analysis timed out. The solver may still be warming up; retry manually after checking engine status."
          : reason instanceof Error
            ? reason.message
            : "The structural screening service could not be reached.",
      );
      setRunState("failed");
      setEngineState("offline");
    } finally {
      window.clearTimeout(timeout);
    }
  }

  const statusLabel =
    runState === "running"
      ? "ANALYZING"
      : runState === "passed"
        ? "SCREENED PASS"
        : runState === "failed"
          ? "REVIEW REQUIRED"
          : "READY TO RUN";

  return (
    <main
      className={styles.shell}
      data-testid="frame-workspace"
      data-run-status={runState}
      data-preset={preset}
      lang="en"
    >
      <header className={styles.topbar}>
        <Link href="/frame" className={styles.brand} aria-label="FrameGuard home">
          <span className={styles.brandMark}>FG</span>
          <span><strong>FrameGuard</strong><small>by DatumGuard</small></span>
        </Link>
        <nav className={styles.nav} aria-label="Engineering workspaces">
          <Link href="/">Architecture</Link>
          <Link href="/piping">Piping</Link>
          <Link href="/plate">Plate</Link>
          <Link href="/solid">3D Solid</Link>
          <Link href="/frame" aria-current="page">Frame</Link>
          <Link href="/case-study">Case Study</Link>
        </nav>
        <div className={`${styles.engine} ${styles[engineState]}`} data-testid="frame-engine-state">
          <span aria-hidden="true" />
          <div><strong>{engineState === "ready" ? "SOLVER READY" : engineState === "warming" ? "ENGINE WARMING" : engineState === "offline" ? "ENGINE OFFLINE" : "CHECKING ENGINE"}</strong><small>{engineState === "ready" ? "DatumGuard 2D frame · linear static" : "Hosted workers may need a cold start"}</small></div>
          {engineState === "offline" && <button type="button" onClick={checkBackend}>Retry</button>}
        </div>
      </header>

      <section className={styles.intro}>
        <div>
          <span className={styles.eyebrow}>STRUCTURAL FRAME SCREENING · 2D LINEAR STATIC</span>
          <h1>FrameGuard</h1>
          <p>Structural Frame Screening</p>
        </div>
        <div className={styles.introCopy}>
          <p>Turn an exact frame contract into explainable displacement and member-risk evidence, then independently retain the solver trail.</p>
          <div><span>MODEL</span><strong>Utility pipe rack PR-101</strong><span>UNITS</span><strong>mm · N · MPa</strong></div>
        </div>
      </section>

      <section className={styles.workbench}>
        <aside className={styles.leftPanel} aria-labelledby="frame-presets-title">
          <div className={styles.panelLabel}><span id="frame-presets-title">FRAME PRESETS</span><b>02 CASES</b></div>
          <button
            type="button"
            className={`${styles.preset} ${preset === "verified" ? styles.activePreset : ""}`}
            onClick={() => changePreset("verified")}
            data-testid="frame-preset-verified"
            aria-pressed={preset === "verified"}
          >
            <span className={styles.presetIcon}><Icon name="rack" /></span>
            <span><strong>Verified rack</strong><small>4 bays · 2 levels · full bracing</small></span>
            <b>01</b>
          </button>
          <button
            type="button"
            className={`${styles.preset} ${preset === "missing-brace" ? styles.activePreset : ""}`}
            onClick={() => changePreset("missing-brace")}
            data-testid="frame-preset-failure"
            aria-pressed={preset === "missing-brace"}
          >
            <span className={`${styles.presetIcon} ${styles.failureIcon}`}><Icon name="warning" /></span>
            <span><strong>Missing brace failure</strong><small>BR04 removed · drift amplified</small></span>
            <b>02</b>
          </button>

          <div className={styles.modelCard}>
            <div className={styles.panelLabel}><span>MODEL CONTRACT</span><b>LOCKED</b></div>
            <dl>
              <div><dt>Span</dt><dd>4 × 6,000</dd></div>
              <div><dt>Level</dt><dd>2 × 4,000</dd></div>
              <div><dt>Nodes</dt><dd>{contract.nodes.length}</dd></div>
              <div><dt>Members</dt><dd>{contract.members.length}</dd></div>
              <div><dt>Load case</dt><dd>LC-01</dd></div>
              <div><dt>Supports</dt><dd>5 fixed</dd></div>
            </dl>
          </div>

          <div className={styles.legend} aria-label="Structural plot legend">
            <span><i className={styles.legendNominal} />Nominal member</span>
            <span><i className={styles.legendRisk} />Governing risk</span>
            <span><i className={styles.legendDeformed} />Deformed shape</span>
            <span><i className={styles.legendLoad} />Applied load</span>
          </div>
        </aside>

        <section className={styles.canvasPanel} aria-labelledby="frame-plot-title">
          <div className={styles.canvasToolbar}>
            <div><span>FRAME ELEVATION · XY</span><strong id="frame-plot-title">PR-101 / Load case LC-01</strong></div>
            <div className={styles.toolbarActions}>
              <div className={styles.segmented} aria-label="Shape display">
                <button type="button" aria-pressed={!showDeformed} onClick={() => setShowDeformed(false)}>Undeformed</button>
                <button type="button" aria-pressed={showDeformed} onClick={() => setShowDeformed(true)}>Deformed</button>
              </div>
              <button type="button" className={styles.iconButton} aria-label="Fit frame view" title="Fit view"><Icon name="fit" /></button>
            </div>
          </div>

          <div className={styles.plotWrap} data-testid="frame-canvas">
            <svg
              className={styles.plot}
              viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
              role="img"
              aria-labelledby="frame-svg-title frame-svg-description"
            >
              <title id="frame-svg-title">Four-bay, two-level utility pipe rack elevation</title>
              <desc id="frame-svg-description">Structural nodes, beam, column, brace, fixed supports, downward loads, and a scaled deformed shape overlay.</desc>
              <defs>
                <pattern id="frame-minor-grid" width="18" height="18" patternUnits="userSpaceOnUse"><path d="M18 0H0V18" className={styles.minorGrid} /></pattern>
                <pattern id="frame-major-grid" width="90" height="90" patternUnits="userSpaceOnUse"><rect width="90" height="90" fill="url(#frame-minor-grid)" /><path d="M90 0H0V90" className={styles.majorGrid} /></pattern>
                <marker id="frame-load-arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto"><path d="M0 0 8 4 0 8z" className={styles.loadArrowHead} /></marker>
              </defs>
              <rect x="0" y="0" width={VIEW_WIDTH} height={VIEW_HEIGHT} className={styles.plotPaper} />
              <rect x="0" y="0" width={VIEW_WIDTH} height={VIEW_HEIGHT} fill="url(#frame-major-grid)" />

              <g className={styles.dimensions} aria-hidden="true">
                {[0, 1, 2, 3].map((bay) => {
                  const x1 = PLOT.left + (bay / 4) * (PLOT.right - PLOT.left);
                  const x2 = PLOT.left + ((bay + 1) / 4) * (PLOT.right - PLOT.left);
                  return <g key={bay}><path d={`M${x1} 490V474M${x2} 490V474M${x1} 483H${x2}`} /><text x={(x1 + x2) / 2} y="502">6 000</text></g>;
                })}
                <path d={`M38 ${PLOT.bottom}H22M38 ${(PLOT.top + PLOT.bottom) / 2}H22M38 ${PLOT.top}H22M30 ${PLOT.bottom}V${PLOT.top}`} />
                <text x="16" y="360" transform="rotate(-90 16 360)">4 000</text>
                <text x="16" y="170" transform="rotate(-90 16 170)">4 000</text>
              </g>

              <g className={styles.loads} aria-label="Five roof-level loads">
                {contract.loads.map((load) => {
                  const node = nodes.get(load.node_id);
                  if (!node) return null;
                  const point = screenPoint(node, 0, false, false);
                  return <g key={load.id}><path d={`M${point.x} ${point.y - 54}V${point.y - 12}`} markerEnd="url(#frame-load-arrow)" /><text x={point.x} y={point.y - 61}>42 kN</text></g>;
                })}
              </g>

              {showDeformed && (
                <g className={`${styles.deformed} ${failed ? styles.deformedFailed : ""}`} aria-label={`Deformed shape at ${deformationScale} times scale`}>
                  {contract.members.map((item) => {
                    const start = nodes.get(item.start_node_id);
                    const end = nodes.get(item.end_node_id);
                    if (!start || !end) return null;
                    const a = screenPoint(start, deformationScale, true, failed);
                    const b = screenPoint(end, deformationScale, true, failed);
                    return <line key={item.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />;
                  })}
                </g>
              )}

              <g className={styles.members} aria-label="Frame members">
                {contract.members.map((item) => {
                  const start = nodes.get(item.start_node_id);
                  const end = nodes.get(item.end_node_id);
                  if (!start || !end) return null;
                  const a = screenPoint(start, 0, false, false);
                  const b = screenPoint(end, 0, false, false);
                  const family = memberFamily(item);
                  const isSelected = item.id === selectedMemberId;
                  const isGoverning = item.id === governingMember;
                  return (
                    <g
                      key={item.id}
                      className={`${styles.member} ${styles[family]} ${isGoverning ? styles.governing : ""} ${isSelected ? styles.selected : ""}`}
                      role="button"
                      tabIndex={0}
                      aria-label={`${item.id}, ${family}${isGoverning ? ", governing member" : ""}`}
                      onClick={() => setSelectedMemberId(item.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedMemberId(item.id);
                        }
                      }}
                    >
                      <line className={styles.memberHit} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
                      <line className={styles.memberLine} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
                    </g>
                  );
                })}
                {preset === "missing-brace" && <g className={styles.missingMember} aria-label="Missing brace BR04"><path d="M225 260 389 72" /><circle cx="307" cy="166" r="12" /><text x="307" y="170">!</text></g>}
              </g>

              <g className={styles.supports} aria-label="Fixed supports">
                {contract.nodes.filter((node) => node.point[1] === 0).map((node) => {
                  const point = screenPoint(node, 0, false, false);
                  return <g key={node.id}><path d={`M${point.x - 12} ${point.y + 17}H${point.x + 12}L${point.x} ${point.y + 2}z`} /><path d={`M${point.x - 16} ${point.y + 19}H${point.x + 16}m-28 5 5-5m3 5 5-5m3 5 5-5m3 5 5-5m3 5 5-5m3 5 5-5`} /></g>;
                })}
              </g>

              <g className={styles.nodes} aria-label="Frame nodes">
                {contract.nodes.map((node) => {
                  const point = screenPoint(node, 0, false, false);
                  return <g key={node.id}><circle cx={point.x} cy={point.y} r="3.2" /><text x={point.x + 7} y={point.y - 7}>{node.id}</text></g>;
                })}
              </g>

              <g className={styles.axis} aria-hidden="true"><path d="M680 470h28m-28 0v-28" /><text x="711" y="474">X</text><text x="676" y="438">Y</text></g>
              <g className={styles.plotStamp} aria-hidden="true"><text x="62" y="30">DATUMGUARD / FRAME ANALYSIS VIEW</text><text x="716" y="30" textAnchor="end">NOT FOR CONSTRUCTION</text></g>
            </svg>

            <div className={styles.plotStatus}>
              <span className={`${styles.statusDot} ${styles[runState]}`} />
              <div><small>SCREENING STATUS</small><strong>{statusLabel}</strong></div>
            </div>
          </div>

          <div className={styles.canvasFooter}>
            <label>
              <span>DEFORMATION SCALE</span>
              <input
                type="range"
                min="1"
                max="24"
                value={deformationScale}
                onChange={(event) => setDeformationScale(Number(event.target.value))}
                aria-label="Deformation scale"
              />
              <output>×{deformationScale}</output>
            </label>
            <span className={styles.coordinate}>WCS · X 12 000.000 · Y 4 000.000 · mm</span>
          </div>
        </section>

        <aside className={styles.inspector} aria-labelledby="frame-inspector-title">
          <div className={styles.panelLabel}><span id="frame-inspector-title">ANALYSIS INSPECTOR</span><b>{statusLabel}</b></div>
          <section className={`${styles.verdict} ${styles[runState]}`} data-testid="frame-verdict">
            <span>{runState === "passed" ? <Icon name="check" /> : runState === "failed" ? <Icon name="warning" /> : <Icon name="analysis" />}</span>
            <div><small>STRUCTURAL SCREENING</small><strong>{statusLabel}</strong><p>{runState === "passed" ? "All configured screening limits passed." : runState === "failed" ? "One or more limits require an engineer's review." : "Run the solver to issue traceable evidence."}</p></div>
          </section>

          <div className={styles.metrics} data-testid="frame-metrics">
            <article><span>MAX DISPLACEMENT</span><strong>{metric(summary.max_displacement_mm)}</strong><small>mm · limit {contract.limits.max_displacement_mm.toFixed(2)}</small></article>
            <article><span>GOVERNING UTILIZATION</span><strong>{metric(summary.max_utilization, 3)}</strong><small>ratio · limit 1.000</small></article>
            <article><span>GOVERNING MEMBER</span><strong>{result ? governingMember : "—"}</strong><small>{selectedMember ? memberFamily(selectedMember) : "select a member"}</small></article>
            <article><span>SOLVER</span><strong>{summary.solver ?? "DatumGuard 2D frame"}</strong><small>linear static · deterministic</small></article>
          </div>

          <section className={styles.memberInspector}>
            <div className={styles.sectionTitle}><span>SELECTED MEMBER</span><b>{selectedMember?.id ?? selectedMemberId}</b></div>
            {selectedMember ? <dl><div><dt>Family</dt><dd>{memberFamily(selectedMember)}</dd></div><div><dt>Nodes</dt><dd>{selectedMember.start_node_id} → {selectedMember.end_node_id}</dd></div><div><dt>Area</dt><dd>{selectedMember.area_mm2.toLocaleString()} mm²</dd></div><div><dt>Depth</dt><dd>{selectedMember.section_depth_mm} mm</dd></div><div><dt>Allowable</dt><dd>{selectedMember.allowable_stress_mpa} MPa</dd></div><div><dt>Geometry</dt><dd>locked</dd></div></dl> : <p>BR04 is intentionally absent from this failure fixture.</p>}
          </section>

          <section className={styles.timeline} data-testid="frame-timeline">
            <div className={styles.sectionTitle}><span>EVIDENCE TIMELINE</span><b>{timeline.length} STAGES</b></div>
            <ol>
              {timeline.map((item, index) => {
                const itemStatus = runState === "running" && index === 0 ? "running" : item.status ?? "waiting";
                const passedStage = ["passed", "complete", "completed", "created", "approved"].includes(itemStatus.toLowerCase());
                const failedStage = ["failed", "blocked", "rejected"].includes(itemStatus.toLowerCase());
                return <li key={`${item.stage}-${index}`} className={passedStage ? styles.stagePass : failedStage ? styles.stageFail : itemStatus === "running" ? styles.stageRunning : ""}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{stageLabel(item.stage)}</strong><small>{itemStatus}</small></div></li>;
              })}
            </ol>
          </section>

          {result?.violations && result.violations.length > 0 && (
            <section className={styles.issues} data-testid="frame-violations">
              <div className={styles.sectionTitle}><span>VIOLATIONS</span><b>{result.violations.length}</b></div>
              {result.violations.map((violation, index) => <article key={`${violation.code}-${index}`}><code>{violation.code ?? "FRAME_REVIEW"}</code><p>{violation.message ?? "Screening limit exceeded."}</p><small>{violation.entity_ids?.join(", ") || "frame model"}</small></article>)}
            </section>
          )}

          {result?.repair_proposals && result.repair_proposals.length > 0 && (
            <section className={styles.repairs} data-testid="frame-repairs">
              <div className={styles.sectionTitle}><span>REPAIR PROPOSALS</span><b>NOT APPLIED</b></div>
              {result.repair_proposals.map((proposal, index) => <article key={proposal.id ?? index}><strong>{proposal.member_id ?? `Option ${index + 1}`}</strong><p>{proposal.description ?? proposal.action ?? "Engineering review required before applying this option."}</p></article>)}
            </section>
          )}

          {serverPreview && (
            <details className={styles.serverPreview}>
              <summary>Serialized solver preview</summary>
              {/* The SVG is isolated as an image URL instead of injected into the page DOM. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={serverPreview} alt="Preview returned by the structural analysis API" />
            </details>
          )}

          <div className={styles.hashes}>
            <span><b>CONTRACT</b><code title={result?.contract_hash}>{compactHash(result?.contract_hash)}</code></span>
            <span><b>ARTIFACT</b><code title={result?.artifact_hash ?? undefined}>{compactHash(result?.artifact_hash)}</code></span>
          </div>

          {error && <div className={styles.error} role="alert" data-testid="frame-error"><strong>ANALYSIS UNAVAILABLE</strong><p>{error}</p><button type="button" onClick={checkBackend}>Check engine</button></div>}

          <button
            type="button"
            className={styles.runButton}
            onClick={runAnalysis}
            disabled={runState === "running"}
            data-testid="frame-run-analysis"
          >
            <Icon name={runState === "running" ? "layers" : "analysis"} />
            <span><strong>{runState === "running" ? "SOLVER RUNNING" : "RUN STRUCTURAL ANALYSIS"}</strong><small>{runState === "running" ? "Assembling model and checking limits" : "Exact contract → solver → evidence"}</small></span>
            <Icon name="arrow" />
          </button>

          <aside className={styles.boundary}>
            <Icon name="warning" />
            <div><strong>SCREENING ONLY · NOT A SAFETY CERTIFICATION</strong><p>Results do not replace code checks, nonlinear analysis, connection design, load validation, or approval by a qualified structural engineer.</p></div>
          </aside>
        </aside>
      </section>

      <FrameAssuranceLab
        key={preset}
        contract={contract as unknown as Record<string, unknown>}
      />

      <footer className={styles.footer}>
        <span>DATUMGUARD · TRACEABLE ENGINEERING AUTOMATION</span>
        <span>
          <Link href="/case-study">CASE STUDY</Link>
          {" / "}
          <a href={releaseUrl} target="_blank" rel="noreferrer">RELEASE EVIDENCE</a>
          {" / "}
          <a href={repositoryUrl} target="_blank" rel="noreferrer">SOURCE</a>
        </span>
      </footer>
    </main>
  );
}

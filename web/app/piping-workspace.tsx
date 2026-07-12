"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import BackendReadinessNotice from "@/app/components/backend-readiness";
import LocalDraftNotice from "@/app/components/local-draft-notice";
import { apiErrorMessage, apiPostJson } from "@/lib/api-client";
import { loadDraft, saveDraft } from "@/lib/draft-db";
import { useBackendReadiness } from "@/lib/use-backend-readiness";

type Point = [number, number];
type PresetId = "semiconductor-cda-utility" | "clearance-collision";
type Tool = "select" | "pan";
type VerificationState = "idle" | "running" | "passed" | "failed";
type ViewBox = { x: number; y: number; width: number; height: number };

type PipingNode = {
  id: string;
  point: Point;
  node_type: "endpoint" | "junction" | "equipment_connection";
  locked: boolean;
};

type PipeSegment = {
  id: string;
  start_node_id: string;
  end_node_id: string;
  nominal_diameter: number;
  service_code: string;
};

type ValveComponent = {
  id: string;
  type: "valve";
  segment_id: string;
  offset: number;
  tag: string;
  valve_type: "isolation" | "check" | "control";
};

type ReducerComponent = {
  id: string;
  type: "reducer";
  segment_id: string;
  offset: number;
  tag: string;
  inlet_diameter: number;
  outlet_diameter: number;
};

type InstrumentComponent = {
  id: string;
  type: "instrument";
  segment_id: string;
  offset: number;
  tag: string;
  instrument_type: string;
};

type InlineComponent = ValveComponent | ReducerComponent | InstrumentComponent;

type PipeSupport = {
  id: string;
  type: "hanger" | "shoe" | "guide" | "anchor";
  segment_id: string;
  offset: number;
};

type RectangleZone = {
  id: string;
  type: "rectangle";
  zone_kind: "equipment" | "keepout";
  origin: Point;
  width: number;
  height: number;
  minimum_clearance: number;
};

type CircleZone = {
  id: string;
  type: "circle";
  zone_kind: "equipment" | "keepout";
  center: Point;
  diameter: number;
  minimum_clearance: number;
};

type EquipmentZone = RectangleZone | CircleZone;

type PipingDraft = {
  presetId: PresetId;
  projectName: string;
  revision: string;
  snap: number;
  nodes: PipingNode[];
  segments: PipeSegment[];
  inlineComponents: InlineComponent[];
  supports: PipeSupport[];
  zones: EquipmentZone[];
};

type Measurement = {
  measurement_id: string;
  dimension_id: string;
  target: number;
  actual: number;
  deviation: number;
  passed: boolean;
};

type Violation = {
  code: string;
  message: string;
  entity_ids: string[];
  repairable: boolean;
  details?: Record<string, unknown>;
};

type TimelineItem = { stage: string; status: string };

type PipingResult = {
  status: string;
  contract_hash: string;
  artifact_hash: string | null;
  measurements: Measurement[];
  violations: Violation[];
  evidence: Array<Record<string, unknown>>;
  preview_svg?: string;
  bundle_base64: string | null;
  summary: {
    nodes?: number;
    segments?: number;
    components?: number;
    supports?: number;
    equipment_zones?: number;
    total_route_length_mm?: number;
    maximum_support_gap_mm?: number;
    minimum_clearance_mm?: number | null;
    summary_source?: string;
    [key: string]: unknown;
  };
  timeline: TimelineItem[];
  error?: { code: string; message: string } | null;
};

type DragState = {
  kind: "valve" | "pan";
  id: string;
  origin: Point;
  draft: PipingDraft;
  viewBox: ViewBox;
};

const DRAFT_KEY = "piping-contract-draft-v1";
const PLAN_HEIGHT = 8000;
const FIT_VIEW: ViewBox = { x: -700, y: -500, width: 13700, height: 9300 };

function cloneDraft<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const UTILITY_PRESET: PipingDraft = {
  presetId: "semiconductor-cda-utility",
  projectName: "Semiconductor CDA Utility Route",
  revision: "A",
  snap: 100,
  nodes: [
    { id: "n1", point: [0, 0], node_type: "endpoint", locked: true },
    { id: "n2", point: [4000, 0], node_type: "junction", locked: true },
    { id: "n3", point: [4000, 3000], node_type: "junction", locked: true },
    { id: "n4", point: [9000, 3000], node_type: "endpoint", locked: true },
  ],
  segments: [
    { id: "seg-1", start_node_id: "n1", end_node_id: "n2", nominal_diameter: 50, service_code: "CDA" },
    { id: "seg-2", start_node_id: "n2", end_node_id: "n3", nominal_diameter: 50, service_code: "CDA" },
    { id: "seg-3", start_node_id: "n3", end_node_id: "n4", nominal_diameter: 40, service_code: "CDA" },
  ],
  inlineComponents: [
    { id: "valve-1", type: "valve", segment_id: "seg-1", offset: 2000, tag: "CDA-V-101", valve_type: "isolation" },
    { id: "instrument-1", type: "instrument", segment_id: "seg-2", offset: 1500, tag: "CDA-PI-101", instrument_type: "pressure_indicator" },
    { id: "reducer-1", type: "reducer", segment_id: "seg-3", offset: 1000, tag: "CDA-R-101", inlet_diameter: 50, outlet_diameter: 40 },
  ],
  supports: [
    { id: "support-1", type: "shoe", segment_id: "seg-1", offset: 1000 },
    { id: "support-2", type: "guide", segment_id: "seg-1", offset: 3000 },
    { id: "support-3", type: "shoe", segment_id: "seg-2", offset: 1000 },
    { id: "support-4", type: "guide", segment_id: "seg-2", offset: 2000 },
    { id: "support-5", type: "shoe", segment_id: "seg-3", offset: 1000 },
    { id: "support-6", type: "guide", segment_id: "seg-3", offset: 3000 },
    { id: "support-7", type: "shoe", segment_id: "seg-3", offset: 4500 },
  ],
  zones: [
    { id: "eq-dryer", type: "rectangle", zone_kind: "equipment", origin: [6000, 5000], width: 2000, height: 1500, minimum_clearance: 300 },
    { id: "ko-cabinet", type: "circle", zone_kind: "keepout", center: [1500, 2500], diameter: 1000, minimum_clearance: 300 },
  ],
};

function clearanceFailurePreset(): PipingDraft {
  const value = cloneDraft(UTILITY_PRESET);
  value.presetId = "clearance-collision";
  value.zones = value.zones.map((zone) =>
    zone.id === "ko-cabinet" && zone.type === "circle"
      ? { ...zone, center: [2500, 400] as Point }
      : zone,
  );
  return value;
}

function nodeById(draft: PipingDraft, id: string): PipingNode {
  const node = draft.nodes.find((item) => item.id === id);
  if (!node) throw new Error(`Unknown piping node: ${id}`);
  return node;
}

function segmentGeometry(draft: PipingDraft, segment: PipeSegment) {
  const start = nodeById(draft, segment.start_node_id).point;
  const end = nodeById(draft, segment.end_node_id).point;
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const length = Math.hypot(dx, dy);
  return {
    start,
    end,
    length,
    unit: [dx / length, dy / length] as Point,
    angle: (Math.atan2(dy, dx) * 180) / Math.PI,
  };
}

function pointAtOffset(draft: PipingDraft, segmentId: string, offset: number): Point {
  const segment = draft.segments.find((item) => item.id === segmentId);
  if (!segment) return [0, 0];
  const geometry = segmentGeometry(draft, segment);
  return [
    geometry.start[0] + geometry.unit[0] * offset,
    geometry.start[1] + geometry.unit[1] * offset,
  ];
}

function buildContract(draft: PipingDraft) {
  const seg1 = draft.segments.find((segment) => segment.id === "seg-1");
  const valve = draft.inlineComponents.find((component) => component.id === "valve-1");
  const dimensions: Array<Record<string, unknown>> = [
    {
      id: "dim-seg-1-length",
      path: "segments.seg-1.length",
      target: seg1 ? segmentGeometry(draft, seg1).length : 4000,
      tolerance_lower: -0.1,
      tolerance_upper: 0.1,
      locked: true,
    },
    {
      id: "dim-valve-offset",
      path: "components.valve-1.offset",
      target: valve?.offset ?? 2000,
      tolerance_lower: -0.1,
      tolerance_upper: 0.1,
      locked: true,
    },
  ];

  return {
    schema_version: "1.0.0",
    design_kind: "piping_plan",
    units: "mm",
    datum: {
      id: "datum-main",
      origin: [0, 0],
      x_axis: [1, 0],
      y_axis: [0, 1],
      plane: "XY",
      locked: true,
    },
    nodes: draft.nodes,
    segments: draft.segments,
    components: draft.inlineComponents,
    supports: draft.supports,
    equipment_zones: draft.zones,
    dimensions,
    constraints: [
      { id: "constraint-route-connected", type: "route_connected", entity_ids: [], parameters: {}, required: true },
      { id: "constraint-orthogonal", type: "orthogonal", entity_ids: [], parameters: { tolerance: 0.1 }, required: true },
      { id: "constraint-endpoints", type: "endpoint_alignment", entity_ids: [], parameters: { tolerance: 0.1 }, required: true },
      { id: "constraint-components", type: "inline_component_position", entity_ids: [], parameters: { tolerance: 0.1 }, required: true },
      { id: "constraint-support-spacing", type: "maximum_support_spacing", entity_ids: [], parameters: { maximum_spacing: 2000 }, required: true },
      { id: "constraint-clearance", type: "minimum_obstacle_clearance", entity_ids: [], parameters: { minimum_clearance: 300 }, required: true },
      { id: "constraint-duplicates", type: "duplicate_geometry", entity_ids: [], parameters: {}, required: true },
    ],
    free_parameters: [],
    drawing_profile: {
      id: "piping-profile-default",
      sheet_size: "A3",
      scale_denominator: 50,
      include_dimensions: true,
      include_node_labels: true,
      title_block: true,
    },
    metadata: {
      project_name: draft.projectName,
      revision: draft.revision,
      notes: "",
    },
  };
}

function snap(value: number, step: number): number {
  return Math.round(value / step) * step;
}

function stageLabel(stage: string): string {
  return {
    contract_validation: "Contract locked",
    dxf_generation: "DXF written",
    independent_dxf_verification: "Independent reader",
    official_bundle: "Approval gate",
  }[stage] ?? stage.replaceAll("_", " ");
}

function statusClass(status: string): string {
  if (["passed", "created", "ready", "generated_unverified"].includes(status)) return "pass";
  if (status === "blocked" || status.includes("fail")) return "fail";
  return "pending";
}

function Icon({ name }: { name: "cursor" | "hand" | "undo" | "redo" | "minus" | "plus" | "fit" | "check" | "alert" | "node" | "pipe" | "valve" | "support" | "zone" | "download" | "run" }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" {...common}>
      {name === "cursor" && <path d="M5 3l13 8-6 2-3 6z" />}
      {name === "hand" && <path d="M7.5 11V6a1.5 1.5 0 013 0v4-6a1.5 1.5 0 013 0v6-5a1.5 1.5 0 013 0v6-3a1.5 1.5 0 013 0v6c0 4-2.5 7-7 7h-1c-2 0-3.5-1-4.5-3L3 14a1.7 1.7 0 013-1l1.5 2" />}
      {name === "undo" && <><path d="M9 7H4v-5" /><path d="M4.5 7A8 8 0 112 13" /></>}
      {name === "redo" && <><path d="M15 7h5v-5" /><path d="M19.5 7A8 8 0 1022 13" /></>}
      {name === "minus" && <path d="M5 12h14" />}
      {name === "plus" && <path d="M5 12h14M12 5v14" />}
      {name === "fit" && <path d="M8 4H4v4M16 4h4v4M4 16v4h4M20 16v4h-4" />}
      {name === "check" && <path d="M5 12.5l4 4L19 7" />}
      {name === "alert" && <><path d="M12 3l10 18H2z" /><path d="M12 9v5M12 18h.01" /></>}
      {name === "node" && <><circle cx="12" cy="12" r="4" /><path d="M12 3v5M12 16v5M3 12h5M16 12h5" /></>}
      {name === "pipe" && <><path d="M3 8h18M3 16h18" /><path d="M7 6v12M17 6v12" /></>}
      {name === "valve" && <path d="M3 7l9 5-9 5zm18 0l-9 5 9 5zM12 4v16" />}
      {name === "support" && <path d="M5 19h14M8 19l4-10 4 10M7 7h10" />}
      {name === "zone" && <><rect x="4" y="4" width="16" height="16" rx="1" /><path d="M4 9h16M9 4v16" /></>}
      {name === "download" && <><path d="M12 3v12M7 10l5 5 5-5" /><path d="M4 19h16" /></>}
      {name === "run" && <><path d="M5 4l14 8-14 8z" /><path d="M9 8v8" /></>}
    </svg>
  );
}

export default function PipingWorkspace() {
  const [draft, setDraft] = useState<PipingDraft>(cloneDraft(UTILITY_PRESET));
  const [history, setHistory] = useState<PipingDraft[]>([]);
  const [future, setFuture] = useState<PipingDraft[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [selectedId, setSelectedId] = useState("valve-1");
  const [tool, setTool] = useState<Tool>("select");
  const [viewBox, setViewBox] = useState<ViewBox>(FIT_VIEW);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [spaceDown, setSpaceDown] = useState(false);
  const [snapState, setSnapState] = useState<"idle" | "snapped">("idle");
  const [verification, setVerification] = useState<VerificationState>("idle");
  const [result, setResult] = useState<PipingResult | null>(null);
  const [message, setMessage] = useState("Ready to lock the piping contract and remeasure its serialized DXF.");
  const [storageError, setStorageError] = useState<string | null>(null);
  const readiness = useBackendReadiness("plant_piping");
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    loadDraft<PipingDraft>(DRAFT_KEY)
      .then((saved) => {
        if (saved && Array.isArray(saved.segments) && Array.isArray(saved.nodes)) setDraft(saved);
      })
      .catch((error) => setStorageError(error instanceof Error ? error.message : "로컬 draft를 읽지 못했습니다."))
      .finally(() => setHydrated(true));
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    const timer = window.setTimeout(() => {
      saveDraft(draft, DRAFT_KEY)
        .then(() => setStorageError(null))
        .catch((error) => setStorageError(error instanceof Error ? error.message : "로컬 draft를 저장하지 못했습니다."));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [draft, hydrated]);

  function clearVerification() {
    setVerification("idle");
    setResult(null);
    setMessage("Draft changed. Run verification to refresh independent evidence.");
  }

  function commit(next: PipingDraft) {
    setHistory((items) => [...items, cloneDraft(draft)].slice(-50));
    setFuture([]);
    setDraft(next);
    clearVerification();
  }

  function undo() {
    setHistory((items) => {
      if (!items.length) return items;
      const previous = items[items.length - 1];
      setFuture((redoItems) => [cloneDraft(draft), ...redoItems].slice(0, 50));
      setDraft(cloneDraft(previous));
      clearVerification();
      return items.slice(0, -1);
    });
  }

  function redo() {
    setFuture((items) => {
      if (!items.length) return items;
      const next = items[0];
      setHistory((past) => [...past, cloneDraft(draft)].slice(-50));
      setDraft(cloneDraft(next));
      clearVerification();
      return items.slice(1);
    });
  }

  useEffect(() => {
    const keyDown = (event: KeyboardEvent) => {
      if (event.code === "Space" && !event.repeat) setSpaceDown(true);
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
      }
    };
    const keyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") setSpaceDown(false);
    };
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);
    return () => {
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
    };
  });

  const pointFromEvent = (event: React.PointerEvent<SVGSVGElement>): Point => {
    const bounds = svgRef.current?.getBoundingClientRect();
    if (!bounds) return [0, 0];
    const screenX = viewBox.x + ((event.clientX - bounds.left) / bounds.width) * viewBox.width;
    const screenY = viewBox.y + ((event.clientY - bounds.top) / bounds.height) * viewBox.height;
    return [screenX, PLAN_HEIGHT - screenY];
  };

  const beginValveDrag = (event: React.PointerEvent<SVGGElement>, component: ValveComponent) => {
    if (window.innerWidth < 900) return;
    event.preventDefault();
    event.stopPropagation();
    setSelectedId(component.id);
    setSnapState("idle");
    const svgEvent = event as unknown as React.PointerEvent<SVGSVGElement>;
    setDrag({ kind: "valve", id: component.id, origin: pointFromEvent(svgEvent), draft: cloneDraft(draft), viewBox });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const pointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (tool !== "pan" && !spaceDown) {
      setSelectedId("");
      return;
    }
    event.preventDefault();
    setDrag({ kind: "pan", id: "canvas", origin: pointFromEvent(event), draft: cloneDraft(draft), viewBox });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const pointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag) return;
    const current = pointFromEvent(event);
    if (drag.kind === "pan") {
      const dx = current[0] - drag.origin[0];
      const dy = current[1] - drag.origin[1];
      setViewBox({ ...drag.viewBox, x: drag.viewBox.x - dx, y: drag.viewBox.y + dy });
      return;
    }

    const component = drag.draft.inlineComponents.find((item) => item.id === drag.id);
    if (!component) return;
    const segment = drag.draft.segments.find((item) => item.id === component.segment_id);
    if (!segment) return;
    const geometry = segmentGeometry(drag.draft, segment);
    const dx = current[0] - drag.origin[0];
    const dy = current[1] - drag.origin[1];
    const alongSegment = dx * geometry.unit[0] + dy * geometry.unit[1];
    const step = event.shiftKey ? 10 : draft.snap;
    const nextOffset = Math.max(0, Math.min(geometry.length, snap(component.offset + alongSegment, step)));
    const next = cloneDraft(drag.draft);
    const nextComponent = next.inlineComponents.find((item) => item.id === drag.id);
    if (nextComponent) nextComponent.offset = nextOffset;
    setDraft(next);
  };

  const pointerUp = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag) return;
    if (drag.kind === "valve") {
      setHistory((items) => [...items, cloneDraft(drag.draft)].slice(-50));
      setFuture([]);
      setSnapState("snapped");
      clearVerification();
    }
    setDrag(null);
    if (svgRef.current?.hasPointerCapture(event.pointerId)) svgRef.current.releasePointerCapture(event.pointerId);
  };

  const zoom = (factor: number) => {
    setViewBox((box) => {
      const width = Math.max(3200, Math.min(28000, box.width * factor));
      const height = (width / box.width) * box.height;
      return {
        x: box.x + (box.width - width) / 2,
        y: box.y + (box.height - height) / 2,
        width,
        height,
      };
    });
  };

  const contract = useMemo(() => buildContract(draft), [draft]);

  const runVerification = async () => {
    if (readiness.state !== "ready") {
      setMessage("Backend readiness를 먼저 확인합니다. 준비 완료 후 수동으로 다시 실행해 주세요.");
      readiness.retry();
      return;
    }
    setVerification("running");
    setResult(null);
    setMessage("Contract locked. The DXF writer and independent reader are running.");
    try {
      const payload = await apiPostJson<PipingResult>(
        "/api/v1/piping/designs/run",
        contract,
        { timeoutMs: 60_000 },
      );
      setResult(payload);
      if (payload.status === "passed") {
        setVerification("passed");
        setMessage("Serialized DXF remeasurement passed the approval gate.");
      } else {
        setVerification("failed");
        setMessage(payload.error?.message || payload.violations?.[0]?.message || "Required piping checks failed. Official output is blocked.");
      }
    } catch (error) {
      setVerification("failed");
      setMessage(apiErrorMessage(error, "Piping verification request failed."));
    }
  };

  const downloadBundle = () => {
    if (verification !== "passed" || !result?.bundle_base64 || result.status !== "passed") return;
    const binary = window.atob(result.bundle_base64);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `datumguard-piping-${result.contract_hash.slice(7, 19)}.zip`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const selectPreset = (preset: PipingDraft, selected: string) => {
    commit(cloneDraft(preset));
    setSelectedId(selected);
    setSnapState("idle");
    setViewBox(FIT_VIEW);
  };

  const selectedNode = draft.nodes.find((item) => item.id === selectedId);
  const selectedSegment = draft.segments.find((item) => item.id === selectedId);
  const selectedComponent = draft.inlineComponents.find((item) => item.id === selectedId);
  const selectedSupport = draft.supports.find((item) => item.id === selectedId);
  const selectedZone = draft.zones.find((item) => item.id === selectedId);

  const updateSelectedNumber = (field: string, value: number) => {
    if (!Number.isFinite(value)) return;
    const next = cloneDraft(draft);
    const node = next.nodes.find((item) => item.id === selectedId);
    const segment = next.segments.find((item) => item.id === selectedId);
    const component = next.inlineComponents.find((item) => item.id === selectedId);
    const support = next.supports.find((item) => item.id === selectedId);
    const zone = next.zones.find((item) => item.id === selectedId);
    if (node) {
      if (field === "x") node.point[0] = value;
      if (field === "y") node.point[1] = value;
    } else if (segment && field === "nominal_diameter") {
      segment.nominal_diameter = Math.max(1, value);
    } else if (component) {
      if (field === "offset") {
        const host = next.segments.find((item) => item.id === component.segment_id);
        const maximum = host ? segmentGeometry(next, host).length : value;
        component.offset = Math.max(0, Math.min(maximum, value));
      }
      if (component.type === "reducer" && field === "inlet_diameter") component.inlet_diameter = Math.max(1, value);
      if (component.type === "reducer" && field === "outlet_diameter") component.outlet_diameter = Math.max(1, value);
    } else if (support && field === "offset") {
      const host = next.segments.find((item) => item.id === support.segment_id);
      const maximum = host ? segmentGeometry(next, host).length : value;
      support.offset = Math.max(0, Math.min(maximum, value));
    } else if (zone) {
      if (zone.type === "rectangle") {
        if (field === "x") zone.origin[0] = value;
        if (field === "y") zone.origin[1] = value;
        if (field === "width") zone.width = Math.max(1, value);
        if (field === "height") zone.height = Math.max(1, value);
      } else {
        if (field === "x") zone.center[0] = value;
        if (field === "y") zone.center[1] = value;
        if (field === "diameter") zone.diameter = Math.max(1, value);
      }
      if (field === "clearance") zone.minimum_clearance = Math.max(0, value);
    }
    commit(next);
  };

  const valveKeyboardMove = (event: React.KeyboardEvent<SVGGElement>, component: ValveComponent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const direction = event.key === "ArrowLeft" || event.key === "ArrowDown" ? -1 : 1;
    const step = event.shiftKey ? 10 : draft.snap;
    setSelectedId(component.id);
    const next = cloneDraft(draft);
    const nextComponent = next.inlineComponents.find((item) => item.id === component.id);
    const host = next.segments.find((item) => item.id === component.segment_id);
    if (!nextComponent || !host) return;
    nextComponent.offset = Math.max(0, Math.min(segmentGeometry(next, host).length, nextComponent.offset + direction * step));
    commit(next);
    setSnapState("snapped");
  };

  const y = (value: number) => PLAN_HEIGHT - value;
  const collisionPreset = draft.presetId === "clearance-collision";
  const valve = draft.inlineComponents.find((item): item is ValveComponent => item.type === "valve");
  const hostSegment = valve ? draft.segments.find((item) => item.id === valve.segment_id) : undefined;
  const hostGeometry = hostSegment ? segmentGeometry(draft, hostSegment) : null;
  const snapTargetOffset = 3000;
  const snapTargetPoint = hostSegment ? pointAtOffset(draft, hostSegment.id, snapTargetOffset) : ([0, 0] as Point);

  const fallbackTimeline: TimelineItem[] = [
    { stage: "contract_validation", status: verification === "idle" ? "waiting" : verification === "running" ? "running" : verification },
    { stage: "dxf_generation", status: verification === "passed" ? "created" : verification === "failed" ? "blocked" : "waiting" },
    { stage: "independent_dxf_verification", status: verification === "passed" ? "passed" : verification === "failed" ? "failed" : "waiting" },
    { stage: "official_bundle", status: verification === "passed" && result?.bundle_base64 ? "ready" : "blocked" },
  ];
  const timeline = result?.timeline?.length ? result.timeline : fallbackTimeline;
  const measurements = result?.measurements || [];
  const violations = result?.violations || [];

  return (
    <main
      className="piping-app"
      data-testid="piping-demo"
      data-verification-status={verification}
      data-preset-id={draft.presetId}
    >
      <h1 className="piping-page-title">Plant piping accuracy workspace</h1>
      <header className="piping-topbar">
        <div className="piping-brand">
          <span aria-hidden="true">DG</span>
          <div><strong>DatumGuard</strong><small>Plant utility accuracy workspace</small></div>
        </div>
        <div className="piping-title">
          <span className="piping-live-dot" aria-hidden="true" />
          <b>{draft.projectName}</b>
          <small>REV {draft.revision} · WCS XY · EXACT mm</small>
        </div>
        <nav aria-label="Engineering workspaces">
          <Link href="/">Architecture</Link>
          <Link href="/piping" aria-current="page">Piping</Link>
          <Link href="/plate">Plate</Link>
          <Link href="/solid">3D Solid</Link>
          <Link href="/intake">Artifact Lab</Link>
          <Link href="/openbim">OpenBIM</Link>
          <Link href="/case-study">Case Study</Link>
          <a href="#piping-verification">Evidence</a>
        </nav>
      </header>

      <section className="piping-commandbar" aria-label="Piping CAD controls">
        <div className="piping-tools" role="group" aria-label="Canvas tool">
          <button type="button" className={tool === "select" ? "active" : ""} aria-pressed={tool === "select"} onClick={() => setTool("select")}><Icon name="cursor" /><span>Select</span></button>
          <button type="button" className={tool === "pan" ? "active" : ""} aria-pressed={tool === "pan"} onClick={() => setTool("pan")}><Icon name="hand" /><span>Pan</span></button>
        </div>
        <div className="piping-history" role="group" aria-label="History and view">
          <button type="button" onClick={undo} disabled={!history.length} aria-label="Undo"><Icon name="undo" /><span>Undo</span></button>
          <button type="button" onClick={redo} disabled={!future.length} aria-label="Redo"><Icon name="redo" /><span>Redo</span></button>
          <span className="piping-tool-divider" aria-hidden="true" />
          <button type="button" onClick={() => zoom(1.2)} aria-label="Zoom out"><Icon name="minus" /><span>Zoom out</span></button>
          <button type="button" onClick={() => zoom(0.84)} aria-label="Zoom in"><Icon name="plus" /><span>Zoom in</span></button>
          <button type="button" onClick={() => setViewBox(FIT_VIEW)}><Icon name="fit" /><span>Fit</span></button>
        </div>
        <div className="piping-snap-setting"><b>SNAP</b><span>{draft.snap} mm</span><small>Shift = 10 mm</small></div>
      </section>

      <LocalDraftNotice error={storageError} onDismiss={() => setStorageError(null)} />

      <section className="piping-workspace">
        <aside className="piping-left-panel" aria-label="Piping model browser">
          <div className="piping-panel-title"><span>MODEL</span><strong>CDA utility plan</strong></div>
          <div className="piping-presets">
            <button data-testid="piping-preset-utility" type="button" className={draft.presetId === "semiconductor-cda-utility" ? "active" : ""} onClick={() => selectPreset(UTILITY_PRESET, "valve-1")}>
              <Icon name="check" /><span><strong>Semiconductor CDA</strong><small>Connected · clear · verifiable</small></span>
            </button>
            <button data-testid="piping-preset-clearance-fail" type="button" className={draft.presetId === "clearance-collision" ? "active invalid" : "invalid"} onClick={() => selectPreset(clearanceFailurePreset(), "ko-cabinet")}>
              <Icon name="alert" /><span><strong>Clearance collision</strong><small>Required keepout is crossed</small></span>
            </button>
          </div>

          <div className="piping-tree">
            <TreeGroup icon="node" label="Nodes" count={draft.nodes.length}>
              {draft.nodes.map((item) => <TreeItem key={item.id} icon="node" label={item.id.toUpperCase()} meta={`${item.node_type} · ${item.point[0]}, ${item.point[1]}`} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}
            </TreeGroup>
            <TreeGroup icon="pipe" label="Pipe segments" count={draft.segments.length}>
              {draft.segments.map((item) => <TreeItem key={item.id} icon="pipe" label={item.id} meta={`DN${item.nominal_diameter} · ${item.service_code}`} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}
            </TreeGroup>
            <TreeGroup icon="valve" label="Inline components" count={draft.inlineComponents.length}>
              {draft.inlineComponents.map((item) => <TreeItem key={item.id} icon="valve" label={item.tag} meta={`${item.offset} mm station`} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}
            </TreeGroup>
            <TreeGroup icon="support" label="Supports" count={draft.supports.length}>
              {draft.supports.map((item) => <TreeItem key={item.id} icon="support" label={item.id} meta={`${item.type} · ${item.offset} mm`} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}
            </TreeGroup>
            <TreeGroup icon="zone" label="Equipment / keepout" count={draft.zones.length}>
              {draft.zones.map((item) => <TreeItem key={item.id} icon="zone" label={item.id === "eq-dryer" ? "CDA dryer" : "Cabinet keepout"} meta={`${item.zone_kind} · ${item.type}`} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}
            </TreeGroup>
          </div>
        </aside>

        <div className="piping-canvas-shell">
          <div className="piping-canvas-status"><span><b>PLAN / L01</b> 1:50</span><span>{tool.toUpperCase()} · {draft.snap} mm snap</span></div>
          <svg
            ref={svgRef}
            data-testid="piping-canvas"
            className={`piping-canvas tool-${tool}`}
            viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
            onPointerDown={pointerDown}
            onPointerMove={pointerMove}
            onPointerUp={pointerUp}
            onPointerCancel={pointerUp}
            onWheel={(event) => { event.preventDefault(); zoom(event.deltaY > 0 ? 1.1 : 0.9); }}
            role="application"
            aria-label={`${draft.projectName} piping plan. Select the valve and use arrow keys or the exact offset property to reposition it.`}
          >
            <defs>
              <pattern id="piping-minor-grid" width="100" height="100" patternUnits="userSpaceOnUse"><path d="M100 0H0V100" fill="none" stroke="#e6ece9" strokeWidth="4" /></pattern>
              <pattern id="piping-major-grid" width="1000" height="1000" patternUnits="userSpaceOnUse"><rect width="1000" height="1000" fill="url(#piping-minor-grid)" /><path d="M1000 0H0V1000" fill="none" stroke="#cfdbd6" strokeWidth="8" /></pattern>
              <marker id="piping-dim-arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto-start-reverse"><path d="M8 1L1 4l7 3" fill="none" stroke="#426157" strokeWidth="1" /></marker>
            </defs>
            <rect x="-2000" y="-2000" width="17000" height="13000" fill="url(#piping-major-grid)" />

            {draft.zones.map((zone) => (
              <g key={zone.id} className={`piping-zone ${zone.zone_kind} ${zone.type} ${selectedId === zone.id ? "selected" : ""}`} onPointerDown={(event) => { event.stopPropagation(); setSelectedId(zone.id); }}>
                {zone.type === "rectangle" ? <>
                  <rect x={zone.origin[0]} y={y(zone.origin[1] + zone.height)} width={zone.width} height={zone.height} rx="50" />
                  <path d={`M${zone.origin[0] + 280} ${y(zone.origin[1] + zone.height - 280)}h${zone.width - 560}v${zone.height - 560}h-${zone.width - 560}z`} />
                  <text x={zone.origin[0] + 120} y={y(zone.origin[1] + zone.height) + 250}>CDA DRYER</text>
                  <text className="zone-meta" x={zone.origin[0] + 120} y={y(zone.origin[1] + zone.height) + 470}>{zone.width} × {zone.height} mm</text>
                </> : <>
                  <circle cx={zone.center[0]} cy={y(zone.center[1])} r={zone.diameter / 2} />
                  <text x={zone.center[0]} y={y(zone.center[1]) - zone.diameter / 2 - 170} textAnchor="middle">CABINET KEEPOUT</text>
                  <text className="zone-meta" x={zone.center[0]} y={y(zone.center[1]) + 20} textAnchor="middle">Ø {zone.diameter} mm</text>
                </>}
              </g>
            ))}

            {draft.segments.map((segment) => {
              const geometry = segmentGeometry(draft, segment);
              const colliding = collisionPreset && segment.id === "seg-1";
              return (
                <g key={segment.id} className={`piping-segment ${selectedId === segment.id ? "selected" : ""} ${colliding ? "collision" : ""}`} onPointerDown={(event) => { event.stopPropagation(); setSelectedId(segment.id); }}>
                  <line className="pipe-outline" x1={geometry.start[0]} y1={y(geometry.start[1])} x2={geometry.end[0]} y2={y(geometry.end[1])} />
                  <line className="pipe-center" x1={geometry.start[0]} y1={y(geometry.start[1])} x2={geometry.end[0]} y2={y(geometry.end[1])} />
                  <text x={(geometry.start[0] + geometry.end[0]) / 2} y={(y(geometry.start[1]) + y(geometry.end[1])) / 2 - 150} textAnchor="middle">{segment.id} · {segment.service_code} · DN{segment.nominal_diameter}</text>
                </g>
              );
            })}

            {draft.nodes.map((node) => (
              <g key={node.id} className={`piping-node ${node.node_type} ${selectedId === node.id ? "selected" : ""}`} onPointerDown={(event) => { event.stopPropagation(); setSelectedId(node.id); }}>
                {node.node_type === "junction" ? <rect x={node.point[0] - 95} y={y(node.point[1]) - 95} width="190" height="190" /> : <circle cx={node.point[0]} cy={y(node.point[1])} r="115" />}
                <text x={node.point[0]} y={y(node.point[1]) - 190} textAnchor="middle">{node.id.toUpperCase()}</text>
              </g>
            ))}

            {draft.supports.map((support) => {
              const point = pointAtOffset(draft, support.segment_id, support.offset);
              const segment = draft.segments.find((item) => item.id === support.segment_id);
              const angle = segment ? segmentGeometry(draft, segment).angle : 0;
              return (
                <g key={support.id} className={`piping-support ${selectedId === support.id ? "selected" : ""}`} transform={`translate(${point[0]} ${y(point[1])}) rotate(${-angle})`} onPointerDown={(event) => { event.stopPropagation(); setSelectedId(support.id); }}>
                  <path d="M-170 0H170M-120 0L0 220 120 0M-150 220H150" />
                  <text transform={`rotate(${angle})`} y="390" textAnchor="middle">{support.id}</text>
                </g>
              );
            })}

            {draft.inlineComponents.map((component) => {
              const point = pointAtOffset(draft, component.segment_id, component.offset);
              const segment = draft.segments.find((item) => item.id === component.segment_id);
              const angle = segment ? segmentGeometry(draft, segment).angle : 0;
              if (component.type === "instrument") {
                return <g key={component.id} className={`piping-inline-component instrument ${selectedId === component.id ? "selected" : ""}`} transform={`translate(${point[0]} ${y(point[1])}) rotate(${-angle})`} onPointerDown={(event) => { event.stopPropagation(); setSelectedId(component.id); }}><circle r="190" /><path d="M0-190V-390M-110-390H110" /><text transform={`rotate(${angle})`} y="-500" textAnchor="middle">{component.tag}</text><text className="component-letter" transform={`rotate(${angle})`} y="60" textAnchor="middle">PI</text></g>;
              }
              if (component.type === "reducer") {
                return <g key={component.id} className={`piping-inline-component reducer ${selectedId === component.id ? "selected" : ""}`} transform={`translate(${point[0]} ${y(point[1])}) rotate(${-angle})`} onPointerDown={(event) => { event.stopPropagation(); setSelectedId(component.id); }}><path d="M-240-165L180-105V105L-240 165Z" /><text transform={`rotate(${angle})`} y="-300" textAnchor="middle">{component.tag}</text></g>;
              }
              return (
                <g
                  key={component.id}
                  data-testid={component.id === "valve-1" ? "piping-draggable-valve" : undefined}
                  data-snap-state={component.id === "valve-1" ? snapState : undefined}
                  className={`piping-valve ${selectedId === component.id ? "selected" : ""}`}
                  transform={`translate(${point[0]} ${y(point[1])}) rotate(${-angle})`}
                  onPointerDown={(event) => beginValveDrag(event, component)}
                  onKeyDown={(event) => valveKeyboardMove(event, component)}
                  role="button"
                  tabIndex={0}
                  aria-label={`${component.tag}, offset ${component.offset} millimetres on ${component.segment_id}. Drag on desktop, use arrow keys, or edit the exact offset field.`}
                >
                  <circle className="valve-hit" r="310" />
                  <path className="valve-body" d="M-210-170L0 0l-210 170zM210-170L0 0l210 170z" />
                  <path className="valve-stem" d="M0-6V-320M-120-320H120" />
                  <text transform={`rotate(${angle})`} y="-440" textAnchor="middle">{component.tag}</text>
                </g>
              );
            })}

            <circle data-testid="piping-snap-target" className="piping-snap-target" cx={snapTargetPoint[0]} cy={y(snapTargetPoint[1])} r="190" />

            {valve && hostGeometry && (
              <g className="piping-dimension">
                <line x1={hostGeometry.start[0]} y1={y(hostGeometry.start[1]) + 650} x2={pointAtOffset(draft, valve.segment_id, valve.offset)[0]} y2={y(pointAtOffset(draft, valve.segment_id, valve.offset)[1]) + 650} markerStart="url(#piping-dim-arrow)" markerEnd="url(#piping-dim-arrow)" />
                <text x={(hostGeometry.start[0] + pointAtOffset(draft, valve.segment_id, valve.offset)[0]) / 2} y={y(hostGeometry.start[1]) + 570} textAnchor="middle">VALVE OFFSET {valve.offset} mm</text>
              </g>
            )}

            {collisionPreset && (
              <g className="piping-collision-callout" role="img" aria-label="Required equipment clearance collision">
                <circle cx="2500" cy={y(0)} r="330" />
                <path d={`M2260 ${y(240)}l480 480M2740 ${y(240)}l-480 480`} />
                <text x="2500" y={y(0) - 430} textAnchor="middle">CLEARANCE COLLISION</text>
              </g>
            )}

            <g className="piping-datum"><line x1="0" y1={y(0)} x2="900" y2={y(0)} /><line x1="0" y1={y(0)} x2="0" y2={y(900)} /><text x="980" y={y(0) + 45}>X</text><text x="-45" y={y(980)}>Y</text></g>
          </svg>
          <div className="piping-scale" aria-hidden="true"><span>0</span><i /><span>2 m</span><i /><span>4 m</span></div>
          <p className="piping-mobile-note">Precision drag is disabled below 900 px. Select the valve and use its exact offset field; verification remains available.</p>
        </div>

        <aside className="piping-right-panel" aria-label="Exact piping properties and verification">
          <div className="piping-panel-title"><span>EXACT PROPERTIES · mm</span><strong>{selectedId || "No selection"}</strong></div>
          <div className="piping-inspector">
            {selectedNode && <>
              <ReadOnlyRow label="Node type" value={selectedNode.node_type} />
              <ReadOnlyRow label="Lock state" value={selectedNode.locked ? "locked" : "editable"} />
              <InspectorNumber label="X coordinate" value={selectedNode.point[0]} onChange={(value) => updateSelectedNumber("x", value)} />
              <InspectorNumber label="Y coordinate" value={selectedNode.point[1]} onChange={(value) => updateSelectedNumber("y", value)} />
            </>}
            {selectedSegment && <>
              <ReadOnlyRow label="Start node" value={selectedSegment.start_node_id} />
              <ReadOnlyRow label="End node" value={selectedSegment.end_node_id} />
              <ReadOnlyRow label="Service code" value={selectedSegment.service_code} />
              <InspectorNumber label="Nominal diameter" value={selectedSegment.nominal_diameter} onChange={(value) => updateSelectedNumber("nominal_diameter", value)} />
              <ReadOnlyRow label="Measured length" value={`${segmentGeometry(draft, selectedSegment).length.toFixed(3)} mm`} />
            </>}
            {selectedComponent && <>
              <ReadOnlyRow label="Component" value={`${selectedComponent.type} / ${selectedComponent.tag}`} />
              <ReadOnlyRow label="Host segment" value={selectedComponent.segment_id} />
              <InspectorNumber inputId={selectedComponent.type === "valve" ? "piping-valve-offset" : undefined} label="Exact host offset" value={selectedComponent.offset} onChange={(value) => updateSelectedNumber("offset", value)} />
              {selectedComponent.type === "valve" && <ReadOnlyRow label="Valve type" value={selectedComponent.valve_type} />}
              {selectedComponent.type === "instrument" && <ReadOnlyRow label="Instrument type" value={selectedComponent.instrument_type} />}
              {selectedComponent.type === "reducer" && <><InspectorNumber label="Inlet diameter" value={selectedComponent.inlet_diameter} onChange={(value) => updateSelectedNumber("inlet_diameter", value)} /><InspectorNumber label="Outlet diameter" value={selectedComponent.outlet_diameter} onChange={(value) => updateSelectedNumber("outlet_diameter", value)} /></>}
              {selectedComponent.type === "valve" && <p className="piping-property-help">Desktop drag snaps to 100 mm. Hold Shift for 10 mm. Numeric entry preserves the exact entered station.</p>}
            </>}
            {selectedSupport && <>
              <ReadOnlyRow label="Support type" value={selectedSupport.type} />
              <ReadOnlyRow label="Host segment" value={selectedSupport.segment_id} />
              <InspectorNumber label="Exact host offset" value={selectedSupport.offset} onChange={(value) => updateSelectedNumber("offset", value)} />
            </>}
            {selectedZone && <>
              <ReadOnlyRow label="Zone kind / shape" value={`${selectedZone.zone_kind} / ${selectedZone.type}`} />
              {selectedZone.type === "rectangle" ? <>
                <InspectorNumber label="Origin X" value={selectedZone.origin[0]} onChange={(value) => updateSelectedNumber("x", value)} />
                <InspectorNumber label="Origin Y" value={selectedZone.origin[1]} onChange={(value) => updateSelectedNumber("y", value)} />
                <InspectorNumber label="Width" value={selectedZone.width} onChange={(value) => updateSelectedNumber("width", value)} />
                <InspectorNumber label="Height" value={selectedZone.height} onChange={(value) => updateSelectedNumber("height", value)} />
              </> : <>
                <InspectorNumber label="Center X" value={selectedZone.center[0]} onChange={(value) => updateSelectedNumber("x", value)} />
                <InspectorNumber label="Center Y" value={selectedZone.center[1]} onChange={(value) => updateSelectedNumber("y", value)} />
                <InspectorNumber label="Diameter" value={selectedZone.diameter} onChange={(value) => updateSelectedNumber("diameter", value)} />
              </>}
              <InspectorNumber label="Required clearance" value={selectedZone.minimum_clearance} onChange={(value) => updateSelectedNumber("clearance", value)} />
            </>}
            {!selectedNode && !selectedSegment && !selectedComponent && !selectedSupport && !selectedZone && <p className="piping-property-help">Select a node, segment, valve, support, or zone to inspect exact contract values.</p>}
          </div>

          <BackendReadinessNotice readiness={readiness} />

          <div className="piping-flow" aria-label="Assurance pipeline">
            <div><span>01</span><div><strong>Contract</strong><small>Datum + explicit mm values</small></div></div>
            <div><span>02</span><div><strong>DXF Writer</strong><small>R2013 entities + trace IDs</small></div></div>
            <div><span>03</span><div><strong>Independent Reader</strong><small>Serialized DXF remeasurement</small></div></div>
            <div><span>04</span><div><strong>Approval Gate</strong><small>No pass, no official bundle</small></div></div>
          </div>

          <button data-testid="piping-run-verification" className="piping-run" type="button" disabled={verification === "running" || readiness.state !== "ready"} onClick={runVerification}>
            {verification === "running" ? <><span className="piping-spinner" aria-hidden="true" />Reading DXF…</> : readiness.state !== "ready" ? <><span className="piping-spinner" aria-hidden="true" />Backend readiness</> : verification === "failed" ? <><Icon name="run" />Retry manually</> : <><Icon name="run" />Generate + verify DXF</>}
          </button>
          <p className="piping-boundary"><b>NOT A CERTIFICATION.</b> Geometry evidence only; no pressure, stress, code, or safety determination.</p>
        </aside>
      </section>

      <section className={`piping-verification ${verification}`} id="piping-verification" aria-labelledby="piping-result-title">
        <div className="piping-result-head">
          <div><span>INDEPENDENT SERIALIZED-DXF EVIDENCE</span><h2 id="piping-result-title">{verification === "passed" ? "Piping geometry verified" : verification === "failed" ? "Official output blocked" : verification === "running" ? "Remeasuring the DXF" : "Approval evidence"}</h2><p aria-live="polite">{message}</p></div>
          <div data-testid="piping-verified-badge" className={`piping-verified ${verification}`} role="status" aria-label={`Verification status: ${verification}`}>
            {verification === "passed" ? <Icon name="check" /> : verification === "failed" ? <Icon name="alert" /> : null}
            <span>{verification === "passed" ? "VERIFIED" : verification.toUpperCase()}</span>
          </div>
          <button data-testid="piping-download" type="button" className="piping-download" disabled={verification !== "passed" || result?.status !== "passed" || !result?.bundle_base64} onClick={downloadBundle}><Icon name="download" /><span>DXF + PDF + JSON</span></button>
        </div>

        <div className="piping-evidence-grid">
          <div data-testid="piping-timeline" className="piping-timeline">
            <span>PIPELINE TIMELINE</span>
            {timeline.map((item, index) => <div key={`${item.stage}-${index}`}><i className={statusClass(item.status)} aria-hidden="true" /><strong>{stageLabel(item.stage)}</strong><code>{item.status}</code></div>)}
          </div>
          <div data-testid="piping-summary" className="piping-summary">
            <span>REMEASUREMENT SUMMARY</span>
            <SummaryMetric value="0.001 mm" label="comparison epsilon" />
            <SummaryMetric value={`${measurements.filter((item) => item.passed).length}/${measurements.length}`} label="dimensions passed" />
            <SummaryMetric value={String(result?.summary?.segments ?? draft.segments.length)} label="segments reopened" />
            <SummaryMetric value={String(result?.summary?.components ?? draft.inlineComponents.length)} label="inline components" />
            <SummaryMetric value={String(result?.summary?.supports ?? draft.supports.length)} label="supports located" />
            <SummaryMetric value={result?.summary?.total_route_length_mm != null ? `${(result.summary.total_route_length_mm / 1000).toFixed(1)} m` : "—"} label="DXF route length" />
            <SummaryMetric value={result?.summary?.maximum_support_gap_mm != null ? `${result.summary.maximum_support_gap_mm} mm` : "—"} label="maximum support gap" />
            <SummaryMetric value={result?.summary?.minimum_clearance_mm != null ? `${result.summary.minimum_clearance_mm} mm` : "—"} label="minimum clearance" />
            <SummaryMetric value={String(violations.length)} label="required violations" />
          </div>
          <div className="piping-hashes">
            <span>TRACEABLE HASHES</span>
            <label>Contract<code data-testid="piping-contract-hash" title={result?.contract_hash || "sha256:pending"}>{result?.contract_hash || "sha256:pending"}</code></label>
            <label>DXF artifact<code data-testid="piping-artifact-hash" title={result?.artifact_hash || "sha256:pending"}>{result?.artifact_hash || "sha256:pending"}</code></label>
            <p>PDF is marked <b>DO NOT SCALE</b>. The DXF remains the fabrication reference inside a passed bundle.</p>
          </div>
        </div>

        {violations.length > 0 && <div className="piping-violations" aria-label="Piping violations">
          {violations.map((item, index) => <article key={`${item.code}-${index}`}><code>{item.code}</code><div><strong>{item.message}</strong><span>{item.entity_ids.join(", ") || "contract"}</span></div><b>{item.repairable ? "REVIEW" : "BLOCKED"}</b></article>)}
        </div>}
      </section>
    </main>
  );
}

type TreeIcon = "node" | "pipe" | "valve" | "support" | "zone";

function TreeGroup({ icon, label, count, children }: { icon: TreeIcon; label: string; count: number; children: ReactNode }) {
  return <section><h2><span><Icon name={icon} />{label}</span><b>{count}</b></h2>{children}</section>;
}

function TreeItem({ icon, label, meta, active, onClick }: { icon: TreeIcon; label: string; meta: string; active: boolean; onClick: () => void }) {
  return <button type="button" className={active ? "active" : ""} aria-pressed={active} onClick={onClick}><Icon name={icon} /><span><strong>{label}</strong><small>{meta}</small></span></button>;
}

function InspectorNumber({ inputId, label, value, onChange }: { inputId?: string; label: string; value: number; onChange: (value: number) => void }) {
  return <label className="piping-number-field" htmlFor={inputId}><span>{label}</span><div><input id={inputId} type="number" step="1" value={value} onChange={(event) => onChange(Number(event.target.value))} /><small>mm</small></div></label>;
}

function ReadOnlyRow({ label, value }: { label: string; value: string }) {
  return <div className="piping-readonly"><span>{label}</span><code>{value}</code></div>;
}

function SummaryMetric({ value, label }: { value: string; label: string }) {
  return <div><b>{value}</b><small>{label}</small></div>;
}

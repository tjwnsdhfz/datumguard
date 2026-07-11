"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import LocalDraftNotice from "@/app/components/local-draft-notice";
import { apiErrorMessage, apiPostJson } from "@/lib/api-client";
import { loadDraft, saveDraft } from "@/lib/draft-db";
import { useBackendReadiness } from "@/lib/use-backend-readiness";

type Point = [number, number];
type Tool = "select" | "pan" | "wall" | "column" | "door" | "window";
type VerificationState = "idle" | "running" | "passed" | "failed";

type GridLine = {
  id: string;
  label: string;
  start: Point;
  end: Point;
  axis: "x" | "y" | "custom";
  locked: boolean;
};

type Wall = {
  id: string;
  start: Point;
  end: Point;
  thickness: number;
  wall_type: "exterior" | "interior" | "partition" | "custom";
};

type Opening = {
  id: string;
  type: "door" | "window" | "opening";
  wall_id: string;
  offset: number;
  width: number;
  height?: number;
  sill_height?: number;
};

type Column = {
  id: string;
  type: "rectangular_column";
  center: Point;
  width: number;
  depth: number;
  rotation_deg: number;
};

type RoomSeed = {
  id: string;
  name: string;
  point: Point;
  expected_area?: number;
};

type ArchitectureDraft = {
  presetId: "architecture-studio" | "architecture-open-loop";
  projectName: string;
  revision: string;
  snap: number;
  grids: GridLine[];
  walls: Wall[];
  openings: Opening[];
  columns: Column[];
  roomSeeds: RoomSeed[];
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
};

type ArchitectureResult = {
  status: string;
  contract_hash: string;
  artifact_hash: string | null;
  measurements: Measurement[];
  violations: Violation[];
  evidence: Array<Record<string, unknown>>;
  preview_svg: string;
  bundle_base64: string | null;
  summary: {
    walls?: number;
    rooms?: number;
    gross_area_m2?: number;
    room_areas?: Array<{ id: string; name: string; area_m2: number | null }>;
    [key: string]: unknown;
  };
  timeline: Array<{ stage: string; status: string }>;
  error?: { code: string; message: string } | null;
};

type DragState = {
  kind: "column" | "wall" | "wall-start" | "wall-end" | "grid" | "opening" | "pan";
  id: string;
  origin: Point;
  draft: ArchitectureDraft;
  viewBox: ViewBox;
};

type ViewBox = { x: number; y: number; width: number; height: number };

const PLAN_HEIGHT = 8000;
const FIT_VIEW: ViewBox = { x: -1100, y: -1100, width: 14200, height: 10200 };
const DRAFT_KEY = "architecture-contract-draft-v1";

function cloneDraft<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const STUDIO_PRESET: ArchitectureDraft = {
  presetId: "architecture-studio",
  projectName: "DatumGuard Small Architecture Studio",
  revision: "A",
  snap: 100,
  grids: [
    { id: "grid-x-a", label: "A", start: [0, -700], end: [0, 8700], axis: "x", locked: true },
    { id: "grid-x-b", label: "B", start: [4000, -700], end: [4000, 8700], axis: "x", locked: true },
    { id: "grid-x-c", label: "C", start: [8000, -700], end: [8000, 8700], axis: "x", locked: true },
    { id: "grid-x-d", label: "D", start: [12000, -700], end: [12000, 8700], axis: "x", locked: true },
    { id: "grid-y-1", label: "1", start: [-700, 0], end: [12700, 0], axis: "y", locked: true },
    { id: "grid-y-2", label: "2", start: [-700, 4000], end: [12700, 4000], axis: "y", locked: true },
    { id: "grid-y-3", label: "3", start: [-700, 8000], end: [12700, 8000], axis: "y", locked: true },
  ],
  walls: [
    { id: "wall-south", start: [0, 0], end: [12000, 0], thickness: 200, wall_type: "exterior" },
    { id: "wall-east", start: [12000, 0], end: [12000, 8000], thickness: 200, wall_type: "exterior" },
    { id: "wall-north", start: [12000, 8000], end: [0, 8000], thickness: 200, wall_type: "exterior" },
    { id: "wall-west", start: [0, 8000], end: [0, 0], thickness: 200, wall_type: "exterior" },
    { id: "wall-core", start: [4000, 0], end: [4000, 8000], thickness: 100, wall_type: "interior" },
    { id: "wall-studio", start: [4000, 4000], end: [12000, 4000], thickness: 100, wall_type: "interior" },
    { id: "wall-service", start: [0, 4000], end: [4000, 4000], thickness: 100, wall_type: "interior" },
  ],
  openings: [
    { id: "door-entry", type: "door", wall_id: "wall-south", offset: 1200, width: 1000, height: 2100 },
    { id: "door-core", type: "door", wall_id: "wall-core", offset: 1400, width: 900, height: 2100 },
    { id: "door-meeting", type: "door", wall_id: "wall-studio", offset: 2300, width: 900, height: 2100 },
    { id: "window-north", type: "window", wall_id: "wall-north", offset: 2800, width: 1800, height: 1500, sill_height: 900 },
    { id: "window-east", type: "window", wall_id: "wall-east", offset: 4700, width: 1800, height: 1500, sill_height: 900 },
  ],
  columns: [
    { id: "column-a", type: "rectangular_column", center: [4000, 4000], width: 400, depth: 400, rotation_deg: 0 },
  ],
  roomSeeds: [
    { id: "room-entry", name: "Entry / Reception", point: [2000, 2000], expected_area: 16000000 },
    { id: "room-service", name: "Service / Utility", point: [2000, 6000], expected_area: 16000000 },
    { id: "room-studio", name: "Open Studio", point: [8000, 2000], expected_area: 32000000 },
    { id: "room-review", name: "Meeting / Review", point: [8000, 6000], expected_area: 32000000 },
  ],
};

function openLoopPreset(): ArchitectureDraft {
  const value = cloneDraft(STUDIO_PRESET);
  value.presetId = "architecture-open-loop";
  value.projectName = "300 mm open exterior loop — failure sample";
  value.walls = value.walls.map((wall) =>
    wall.id === "wall-north" ? { ...wall, end: [300, 8000] as Point } : wall,
  );
  return value;
}

function wallById(draft: ArchitectureDraft, wallId: string): Wall {
  const wall = draft.walls.find((item) => item.id === wallId);
  if (!wall) throw new Error(`Unknown wall: ${wallId}`);
  return wall;
}

function openingEndpoints(opening: Opening, wall: Wall): [Point, Point] {
  const length = Math.hypot(wall.end[0] - wall.start[0], wall.end[1] - wall.start[1]);
  const ux = (wall.end[0] - wall.start[0]) / length;
  const uy = (wall.end[1] - wall.start[1]) / length;
  return [
    [wall.start[0] + ux * opening.offset, wall.start[1] + uy * opening.offset],
    [
      wall.start[0] + ux * (opening.offset + opening.width),
      wall.start[1] + uy * (opening.offset + opening.width),
    ],
  ];
}

function architectureContract(draft: ArchitectureDraft) {
  const dimensions = [
    { id: "dim-south-length", path: "walls.wall-south.length", target: 12000, tolerance_lower: -0.001, tolerance_upper: 0.001, locked: true, source: { kind: "form", ref: "wall-south" } },
    { id: "dim-west-length", path: "walls.wall-west.length", target: 8000, tolerance_lower: -0.001, tolerance_upper: 0.001, locked: true, source: { kind: "form", ref: "wall-west" } },
    { id: "dim-entry-width", path: "openings.door-entry.width", target: 1000, tolerance_lower: -0.001, tolerance_upper: 0.001, locked: true, source: { kind: "form", ref: "door-entry" } },
    { id: "dim-column-x", path: "columns.column-a.center.0", target: draft.columns[0]?.center[0] ?? 4000, tolerance_lower: -0.001, tolerance_upper: 0.001, locked: true, source: { kind: "form", ref: "column-a-x" } },
  ];
  return {
    schema_version: "1.0.0",
    design_kind: "architectural_plan",
    units: "mm",
    datum: { id: "datum-main", origin: [0, 0], x_axis: [1, 0], y_axis: [0, 1], plane: "XY", locked: true },
    grids: draft.grids,
    walls: draft.walls,
    openings: draft.openings,
    columns: draft.columns,
    room_seeds: draft.roomSeeds,
    dimensions,
    constraints: [
      { id: "constraint-exterior", type: "exterior_closed_loop", entity_ids: ["wall-south", "wall-east", "wall-north", "wall-west"], parameters: { tolerance: 1 }, required: true },
      { id: "constraint-connected", type: "walls_connected", entity_ids: draft.walls.map((wall) => wall.id), parameters: { tolerance: 1 }, required: true },
      { id: "constraint-openings", type: "openings_inside_walls", entity_ids: draft.openings.map((opening) => opening.id), parameters: {}, required: true },
      { id: "constraint-rooms", type: "room_resolved", entity_ids: draft.roomSeeds.map((room) => room.id), parameters: {}, required: true },
      { id: "constraint-column-grid", type: "column_grid_alignment", entity_ids: draft.columns.map((column) => column.id), parameters: { tolerance: 1 }, required: true },
      { id: "constraint-duplicates", type: "duplicate_geometry", entity_ids: [], parameters: {}, required: true },
    ],
    free_parameters: [],
    drawing_profile: { id: "architecture-profile-default", sheet_size: "A3", scale_denominator: 100, include_dimensions: true, include_room_labels: true, title_block: true },
    metadata: { project_name: draft.projectName, revision: draft.revision, notes: "Synthetic public architecture fixture" },
    contract_hash: null,
    intent_text: null,
  };
}

function snap(value: number, step: number): number {
  return Math.round(value / step) * step;
}

type ArchitectureTimelineItem = {
  id: "contract" | "writer" | "reopen" | "remeasure" | "approved";
  label: "Contract locked" | "DXF written" | "DXF reopened" | "Remeasured" | "Approved";
  status: string;
};

function architectureTimeline(
  result: ArchitectureResult | null,
  verification: VerificationState,
): ArchitectureTimelineItem[] {
  const statuses = new Map((result?.timeline || []).map((item) => [item.stage, item.status]));
  const contractStatus = statuses.get("contract_validation");
  const writerStatus = statuses.get("dxf_generation");
  const readerStatus = statuses.get("independent_dxf_verification");
  const bundleStatus = statuses.get("official_bundle");

  return [
    {
      id: "contract",
      label: "Contract locked",
      status: contractStatus
        ? contractStatus === "ready" || contractStatus === "passed" ? "locked" : contractStatus
        : verification === "running" ? "locking" : "waiting",
    },
    {
      id: "writer",
      label: "DXF written",
      status: writerStatus
        ? writerStatus === "generated_unverified" ? "written" : writerStatus
        : "waiting",
    },
    {
      id: "reopen",
      label: "DXF reopened",
      status: readerStatus ? "reopened" : "waiting",
    },
    {
      id: "remeasure",
      label: "Remeasured",
      status: readerStatus || "waiting",
    },
    {
      id: "approved",
      label: "Approved",
      status: bundleStatus === "created" || bundleStatus === "ready" ? "approved" : bundleStatus || "waiting",
    },
  ];
}

function timelineStatusClass(status: string): "pass" | "fail" | "pending" {
  if (["locked", "written", "reopened", "passed", "approved", "ready", "created"].includes(status)) return "pass";
  if (status === "blocked" || status.includes("fail")) return "fail";
  return "pending";
}

type ArchitectureIconName =
  | "select"
  | "pan"
  | "wall"
  | "column"
  | "door"
  | "window"
  | "undo"
  | "redo"
  | "zoom-in"
  | "zoom-out"
  | "fit"
  | "check"
  | "alert"
  | "tree"
  | "run"
  | "download"
  | "health";

function ArchitectureIcon({ name }: { name: ArchitectureIconName }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" {...common}>
      {name === "select" && <path d="M5 3l13 8-6 2-3 6z" />}
      {name === "pan" && <path d="M7.5 11V6a1.5 1.5 0 013 0v4-6a1.5 1.5 0 013 0v6-5a1.5 1.5 0 013 0v6-3a1.5 1.5 0 013 0v6c0 4-2.5 7-7 7h-1c-2 0-3.5-1-4.5-3L3 14a1.7 1.7 0 013-1l1.5 2" />}
      {name === "wall" && <path d="M3 8h18v8H3zM8 8v8M16 8v8" />}
      {name === "column" && <><rect x="5" y="5" width="14" height="14" /><path d="M9 9h6v6H9z" /></>}
      {name === "door" && <><path d="M5 20V4h11v16M16 20h3" /><path d="M16 5a15 15 0 01-11 15" /></>}
      {name === "window" && <><rect x="4" y="6" width="16" height="12" /><path d="M12 6v12M4 12h16" /></>}
      {name === "undo" && <><path d="M9 7H4V2" /><path d="M4.5 7A8 8 0 112 13" /></>}
      {name === "redo" && <><path d="M15 7h5V2" /><path d="M19.5 7A8 8 0 1022 13" /></>}
      {name === "zoom-in" && <><circle cx="10" cy="10" r="6" /><path d="M14.5 14.5L21 21M10 7v6M7 10h6" /></>}
      {name === "zoom-out" && <><circle cx="10" cy="10" r="6" /><path d="M14.5 14.5L21 21M7 10h6" /></>}
      {name === "fit" && <path d="M8 4H4v4M16 4h4v4M4 16v4h4M20 16v4h-4" />}
      {name === "check" && <path d="M5 12.5l4 4L19 7" />}
      {name === "alert" && <><path d="M12 3l10 18H2z" /><path d="M12 9v5M12 18h.01" /></>}
      {name === "tree" && <><path d="M7 5h10M7 12h10M7 19h10" /><circle cx="4" cy="5" r="1" /><circle cx="4" cy="12" r="1" /><circle cx="4" cy="19" r="1" /></>}
      {name === "run" && <path d="M6 4l13 8-13 8z" />}
      {name === "download" && <><path d="M12 3v12M7 10l5 5 5-5" /><path d="M4 20h16" /></>}
      {name === "health" && <><path d="M3 12h4l2-5 4 10 2-5h6" /><circle cx="12" cy="12" r="9" /></>}
    </svg>
  );
}

export default function ArchitectureWorkspace() {
  const [draft, setDraft] = useState<ArchitectureDraft>(cloneDraft(STUDIO_PRESET));
  const [history, setHistory] = useState<ArchitectureDraft[]>([]);
  const [future, setFuture] = useState<ArchitectureDraft[]>([]);
  const [selectedId, setSelectedId] = useState("column-a");
  const [tool, setTool] = useState<Tool>("select");
  const [viewBox, setViewBox] = useState<ViewBox>(FIT_VIEW);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [spaceDown, setSpaceDown] = useState(false);
  const [snapState, setSnapState] = useState<"idle" | "snapped">("idle");
  const [verification, setVerification] = useState<VerificationState>("idle");
  const [result, setResult] = useState<ArchitectureResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [storageError, setStorageError] = useState<string | null>(null);
  const readiness = useBackendReadiness("architecture");
  const health = readiness.state;
  const healthAttempts = readiness.attempts;
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    loadDraft<ArchitectureDraft>(DRAFT_KEY)
      .then((saved) => {
        if (
          saved &&
          saved.walls.some((wall) => wall.id === "wall-service") &&
          saved.roomSeeds.length === 4
        ) {
          setDraft(saved);
        }
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

  function commit(next: ArchitectureDraft) {
    setHistory((items) => [...items, cloneDraft(draft)].slice(-50));
    setFuture([]);
    setDraft(next);
    setVerification("idle");
    setResult(null);
    setMessage(null);
  }

  function undo() {
    setHistory((items) => {
      if (!items.length) return items;
      const previous = items[items.length - 1];
      setFuture((redoItems) => [cloneDraft(draft), ...redoItems].slice(0, 50));
      setDraft(cloneDraft(previous));
      setVerification("idle");
      return items.slice(0, -1);
    });
  }

  function redo() {
    setFuture((items) => {
      if (!items.length) return items;
      const next = items[0];
      setHistory((past) => [...past, cloneDraft(draft)].slice(-50));
      setDraft(cloneDraft(next));
      setVerification("idle");
      return items.slice(1);
    });
  }

  const pointFromEvent = (event: React.PointerEvent<SVGSVGElement>): Point => {
    const bounds = svgRef.current?.getBoundingClientRect();
    if (!bounds) return [0, 0];
    const screenX = viewBox.x + ((event.clientX - bounds.left) / bounds.width) * viewBox.width;
    const screenY = viewBox.y + ((event.clientY - bounds.top) / bounds.height) * viewBox.height;
    return [screenX, PLAN_HEIGHT - screenY];
  };

  const beginDrag = (
    event: React.PointerEvent<SVGElement>,
    kind: DragState["kind"],
    id: string,
  ) => {
    if (window.innerWidth < 900) return;
    event.preventDefault();
    event.stopPropagation();
    setSelectedId(id);
    setSnapState("idle");
    const svgEvent = event as unknown as React.PointerEvent<SVGSVGElement>;
    setDrag({ kind, id, origin: pointFromEvent(svgEvent), draft: cloneDraft(draft), viewBox });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const pointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (tool !== "pan" && !spaceDown) {
      setSelectedId("");
      return;
    }
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
    const step = event.shiftKey ? 10 : draft.snap;
    const dx = current[0] - drag.origin[0];
    const dy = current[1] - drag.origin[1];
    const next = cloneDraft(drag.draft);
    if (drag.kind === "column") {
      const column = next.columns.find((item) => item.id === drag.id);
      if (column) column.center = [snap(column.center[0] + dx, step), snap(column.center[1] + dy, step)];
    } else if (drag.kind === "wall" || drag.kind === "wall-start" || drag.kind === "wall-end") {
      const wall = next.walls.find((item) => item.id === drag.id);
      if (wall && drag.kind === "wall") {
        wall.start = [snap(wall.start[0] + dx, step), snap(wall.start[1] + dy, step)];
        wall.end = [snap(wall.end[0] + dx, step), snap(wall.end[1] + dy, step)];
      } else if (wall && drag.kind === "wall-start") {
        const horizontal = Math.abs(wall.end[0] - wall.start[0]) >= Math.abs(wall.end[1] - wall.start[1]);
        wall.start = horizontal
          ? [snap(wall.start[0] + dx, step), wall.start[1]]
          : [wall.start[0], snap(wall.start[1] + dy, step)];
      } else if (wall) {
        const horizontal = Math.abs(wall.end[0] - wall.start[0]) >= Math.abs(wall.end[1] - wall.start[1]);
        wall.end = horizontal
          ? [snap(wall.end[0] + dx, step), wall.end[1]]
          : [wall.end[0], snap(wall.end[1] + dy, step)];
      }
    } else if (drag.kind === "grid") {
      const grid = next.grids.find((item) => item.id === drag.id);
      if (grid?.axis === "x") {
        const move = snap(dx, step);
        grid.start[0] += move;
        grid.end[0] += move;
      } else if (grid) {
        const move = snap(dy, step);
        grid.start[1] += move;
        grid.end[1] += move;
      }
    } else if (drag.kind === "opening") {
      const opening = next.openings.find((item) => item.id === drag.id);
      if (opening) {
        const wall = wallById(next, opening.wall_id);
        const length = Math.hypot(wall.end[0] - wall.start[0], wall.end[1] - wall.start[1]);
        const ux = (wall.end[0] - wall.start[0]) / length;
        const uy = (wall.end[1] - wall.start[1]) / length;
        opening.offset = Math.max(0, Math.min(length - opening.width, snap(opening.offset + dx * ux + dy * uy, step)));
      }
    }
    setDraft(next);
  };

  const pointerUp = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag) return;
    if (drag.kind !== "pan") {
      setHistory((items) => [...items, cloneDraft(drag.draft)].slice(-50));
      setFuture([]);
      setSnapState("snapped");
      setVerification("idle");
      setResult(null);
      setMessage(null);
    }
    setDrag(null);
    if (svgRef.current?.hasPointerCapture(event.pointerId)) svgRef.current.releasePointerCapture(event.pointerId);
  };

  const zoom = (factor: number) => {
    setViewBox((box) => {
      const width = Math.max(3000, Math.min(30000, box.width * factor));
      const height = (width / box.width) * box.height;
      return { x: box.x + (box.width - width) / 2, y: box.y + (box.height - height) / 2, width, height };
    });
  };

  const runVerification = async () => {
    if (health !== "ready") {
      setMessage("검증 엔진 준비 중입니다. 연결이 완료되면 다시 실행해 주세요.");
      readiness.retry();
      return;
    }
    setVerification("running");
    setMessage("건축 검증 엔진이 contract를 잠그고 있습니다.");
    setResult(null);
    try {
      const payload = await apiPostJson<ArchitectureResult>(
        "/api/v1/architecture/designs/run",
        architectureContract(draft),
        { timeoutMs: 60_000 },
      );
      setResult(payload);
      setVerification(payload.status === "passed" ? "passed" : "failed");
      setMessage(payload.status === "passed" ? "독립 재측정과 approval gate를 통과했습니다." : payload.error?.message || "검증에 실패했습니다.");
    } catch (error) {
      setVerification("failed");
      setMessage(apiErrorMessage(error, "건축 검증 요청에 실패했습니다."));
    }
  };

  const download = () => {
    if (!result?.bundle_base64 || result.status !== "passed") return;
    const binary = window.atob(result.bundle_base64);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `datumguard-architecture-${result.contract_hash.slice(7, 19)}.zip`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const selectedWall = draft.walls.find((item) => item.id === selectedId);
  const selectedColumn = draft.columns.find((item) => item.id === selectedId);
  const selectedOpening = draft.openings.find((item) => item.id === selectedId);
  const selectedGrid = draft.grids.find((item) => item.id === selectedId);

  const updateNumber = (field: string, value: number) => {
    const next = cloneDraft(draft);
    const column = next.columns.find((item) => item.id === selectedId);
    const wall = next.walls.find((item) => item.id === selectedId);
    const opening = next.openings.find((item) => item.id === selectedId);
    const grid = next.grids.find((item) => item.id === selectedId);
    if (column) {
      if (field === "x") column.center[0] = value;
      if (field === "y") column.center[1] = value;
      if (field === "width") column.width = value;
      if (field === "depth") column.depth = value;
    } else if (wall) {
      const map: Record<string, ["start" | "end", 0 | 1]> = { x1: ["start", 0], y1: ["start", 1], x2: ["end", 0], y2: ["end", 1] };
      if (field === "thickness") wall.thickness = value;
      else if (map[field]) wall[map[field][0]][map[field][1]] = value;
    } else if (opening) {
      if (field === "offset") opening.offset = value;
      if (field === "width") opening.width = value;
    } else if (grid) {
      if (grid.axis === "x") {
        grid.start[0] = value;
        grid.end[0] = value;
      } else {
        grid.start[1] = value;
        grid.end[1] = value;
      }
    }
    commit(next);
  };

  const canvas = (() => {
    const y = (value: number) => PLAN_HEIGHT - value;
    return (
      <svg
        ref={svgRef}
        data-testid="architecture-canvas"
        data-preset-id={draft.presetId}
        className={`arch-canvas tool-${tool}`}
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        onPointerCancel={pointerUp}
        onWheel={(event) => { event.preventDefault(); zoom(event.deltaY > 0 ? 1.12 : 0.88); }}
        role="application"
        aria-label={`${draft.projectName} 건축 평면 CAD 캔버스. 데스크톱에서는 객체를 드래그하고, 모든 화면에서 정확한 수치 입력을 사용할 수 있습니다.`}
      >
        <defs>
          <pattern id="arch-minor-grid" width="100" height="100" patternUnits="userSpaceOnUse"><path d="M100 0H0V100" fill="none" stroke="#e8eeeb" strokeWidth="4" /></pattern>
          <pattern id="arch-major-grid" width="1000" height="1000" patternUnits="userSpaceOnUse"><rect width="1000" height="1000" fill="url(#arch-minor-grid)" /><path d="M1000 0H0V1000" fill="none" stroke="#d3dfda" strokeWidth="8" /></pattern>
        </defs>
        <rect x={-2000} y={-2000} width={16000} height={12000} fill="url(#arch-major-grid)" />
        {draft.grids.map((grid) => (
          <g key={grid.id} data-testid={grid.id === "grid-x-c" ? "architecture-draggable-grid" : undefined} data-snap-state={grid.id === "grid-x-c" ? snapState : undefined} onPointerDown={(event) => beginDrag(event, "grid", grid.id)} className={selectedId === grid.id ? "selected" : ""}>
            <line className="arch-grid-line hit" x1={grid.start[0]} y1={y(grid.start[1])} x2={grid.end[0]} y2={y(grid.end[1])} />
            <line className="arch-grid-line" x1={grid.start[0]} y1={y(grid.start[1])} x2={grid.end[0]} y2={y(grid.end[1])} />
            <text className="arch-grid-label" x={grid.axis === "x" ? grid.start[0] : grid.end[0] + 180} y={grid.axis === "x" ? y(grid.end[1]) - 120 : y(grid.end[1]) + 40}>{grid.label}</text>
          </g>
        ))}
        {draft.walls.map((wall) => {
          const horizontal = Math.abs(wall.end[0] - wall.start[0]) >= Math.abs(wall.end[1] - wall.start[1]);
          const hitX = horizontal ? Math.min(wall.start[0], wall.end[0]) : wall.start[0] - 200;
          const hitY = horizontal ? y(wall.start[1]) - 200 : Math.min(y(wall.start[1]), y(wall.end[1]));
          const hitWidth = horizontal ? Math.abs(wall.end[0] - wall.start[0]) : 400;
          const hitHeight = horizontal ? 400 : Math.abs(wall.end[1] - wall.start[1]);
          return <g key={wall.id} className={selectedId === wall.id ? "selected" : ""}>
            <line className={`arch-wall ${wall.wall_type}`} x1={wall.start[0]} y1={y(wall.start[1])} x2={wall.end[0]} y2={y(wall.end[1])} strokeWidth={wall.thickness} onPointerDown={(event) => beginDrag(event, "wall", wall.id)} />
            <rect data-testid={wall.id === "wall-service" ? "architecture-draggable-wall" : undefined} data-snap-state={wall.id === "wall-service" ? snapState : undefined} className="arch-wall-body-hit" x={hitX} y={hitY} width={Math.max(hitWidth, 1)} height={Math.max(hitHeight, 1)} onPointerDown={(event) => beginDrag(event, "wall", wall.id)} />
            {selectedId === wall.id && <><circle data-testid={wall.id === "wall-service" ? "architecture-wall-start-handle" : undefined} className="arch-handle" cx={wall.start[0]} cy={y(wall.start[1])} r="120" onPointerDown={(event) => beginDrag(event, "wall-start", wall.id)} /><circle data-testid={wall.id === "wall-service" ? "architecture-wall-end-handle" : undefined} className="arch-handle" cx={wall.end[0]} cy={y(wall.end[1])} r="120" onPointerDown={(event) => beginDrag(event, "wall-end", wall.id)} /></>}
          </g>;
        })}
        {draft.openings.map((opening) => {
          const [start, end] = openingEndpoints(opening, wallById(draft, opening.wall_id));
          return <g key={opening.id} data-testid={opening.id === "door-entry" ? "architecture-draggable-opening" : undefined} data-snap-state={opening.id === "door-entry" ? snapState : undefined} className={selectedId === opening.id ? "selected" : ""} onPointerDown={(event) => beginDrag(event, "opening", opening.id)}><line className={`arch-opening ${opening.type}`} x1={start[0]} y1={y(start[1])} x2={end[0]} y2={y(end[1])} strokeWidth={wallById(draft, opening.wall_id).thickness + 45} /><line className="arch-opening-center" x1={start[0]} y1={y(start[1])} x2={end[0]} y2={y(end[1])} /></g>;
        })}
        {draft.columns.map((column) => (
          <rect
            key={column.id}
            data-testid={column.id === "column-a" ? "architecture-draggable-column" : undefined}
            data-snap-state={column.id === "column-a" ? snapState : undefined}
            className={`arch-column ${selectedId === column.id ? "selected" : ""}`}
            x={column.center[0] - column.width / 2}
            y={y(column.center[1]) - column.depth / 2}
            width={column.width}
            height={column.depth}
            onPointerDown={(event) => beginDrag(event, "column", column.id)}
          />
        ))}
        <circle data-testid="architecture-snap-target-center" className="arch-snap-target" cx="8000" cy={y(4000)} r="180" />
        {draft.roomSeeds.map((room) => <g key={room.id} className="arch-room"><circle cx={room.point[0]} cy={y(room.point[1])} r="40" /><text x={room.point[0]} y={y(room.point[1]) - 120} textAnchor="middle">{room.name}</text></g>)}
        <g className="arch-datum"><line x1="0" y1={y(0)} x2="900" y2={y(0)} /><line x1="0" y1={y(0)} x2="0" y2={y(900)} /><text x="950" y={y(0) + 40}>X</text><text x="-40" y={y(950)}>Y</text></g>
      </svg>
    );
  })();

  const presentationTimeline = architectureTimeline(result, verification);
  const healthText = health === "ready"
    ? "검증 엔진 준비 완료"
    : health === "failed"
      ? "검증 엔진에 연결하지 못했습니다"
      : "검증 엔진 준비 중";

  return (
    <main className="architecture-app" data-testid="architecture-demo" data-verification-status={verification} data-health-status={health} data-history-depth={history.length} data-future-depth={future.length}>
      <header className="arch-topbar">
        <div className="arch-brand"><span>DG</span><div><strong>DatumGuard</strong><small>Architecture accuracy workspace</small></div></div>
        <div className="arch-title"><span className="arch-live-dot" /> <b>{draft.projectName}</b><small>REV {draft.revision} · WCS XY · mm</small></div>
        <nav><Link href="/piping">Plant Piping</Link><Link href="/plate">Plate</Link><Link href="/solid">3D Solid</Link><Link href="/intake">Artifact Lab</Link><a href="#verification">검증</a></nav>
      </header>

      <section className="arch-commandbar" aria-label="Architecture CAD tools">
        <div className="arch-tools" role="group" aria-label="Canvas tool">{(["select", "pan", "wall", "column", "door", "window"] as Tool[]).map((item) => <button key={item} type="button" className={tool === item ? "active" : ""} aria-pressed={tool === item} onClick={() => setTool(item)}><ArchitectureIcon name={item} /><span>{item}</span></button>)}</div>
        <div className="arch-history" role="group" aria-label="History and view"><button data-testid="architecture-undo" type="button" onClick={undo} disabled={!history.length} aria-label="Undo"><ArchitectureIcon name="undo" /><span>Undo</span></button><button data-testid="architecture-redo" type="button" onClick={redo} disabled={!future.length} aria-label="Redo"><ArchitectureIcon name="redo" /><span>Redo</span></button><button data-testid="architecture-zoom-in" type="button" onClick={() => zoom(0.82)} aria-label="Zoom in"><ArchitectureIcon name="zoom-in" /></button><button data-testid="architecture-zoom-out" type="button" onClick={() => zoom(1.22)} aria-label="Zoom out"><ArchitectureIcon name="zoom-out" /></button><button data-testid="architecture-fit" type="button" onClick={() => setViewBox(FIT_VIEW)}><ArchitectureIcon name="fit" /><span>Fit</span></button></div>
        <label className="arch-snap">Snap <select value={draft.snap} onChange={(event) => commit({ ...draft, snap: Number(event.target.value) })}><option value={100}>100 mm</option><option value={50}>50 mm</option><option value={10}>10 mm</option></select><small>Shift = 10mm</small></label>
      </section>

      <LocalDraftNotice error={storageError} onDismiss={() => setStorageError(null)} />

      <section className="arch-workspace">
        <aside className="arch-left-panel">
          <div className="arch-panel-title"><span>MODEL</span><strong>Level 01</strong></div>
          <div className="arch-presets">
            <button data-testid="architecture-preset-studio" type="button" className={draft.presetId === "architecture-studio" ? "active" : ""} onClick={() => { commit(cloneDraft(STUDIO_PRESET)); setSelectedId("column-a"); setSnapState("idle"); setViewBox(FIT_VIEW); }}><ArchitectureIcon name="check" /><span><strong>12 × 8 m / 4-room studio</strong><small>Closed, resolved, verifiable</small></span></button>
            <button data-testid="architecture-preset-invalid" type="button" className={draft.presetId === "architecture-open-loop" ? "active invalid" : "invalid"} onClick={() => { commit(openLoopPreset()); setSelectedId("wall-north"); setSnapState("idle"); setViewBox(FIT_VIEW); }}><ArchitectureIcon name="alert" /><span><strong>300 mm open loop</strong><small>Required exterior closure fails</small></span></button>
          </div>
          <div className="arch-tree">
            <TreeGroup label="Grids" count={draft.grids.length}>{draft.grids.map((item) => <TreeItem key={item.id} label={`${item.label} · ${item.id}`} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}</TreeGroup>
            <TreeGroup label="Walls" count={draft.walls.length}>{draft.walls.map((item) => <TreeItem key={item.id} label={item.id} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}</TreeGroup>
            <TreeGroup label="Openings" count={draft.openings.length}>{draft.openings.map((item) => <TreeItem key={item.id} label={`${item.type} · ${item.id}`} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}</TreeGroup>
            <TreeGroup label="Columns" count={draft.columns.length}>{draft.columns.map((item) => <TreeItem key={item.id} label={item.id} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}</TreeGroup>
            <TreeGroup label="Rooms" count={draft.roomSeeds.length}>{draft.roomSeeds.map((item) => <TreeItem key={item.id} label={item.name} active={selectedId === item.id} onClick={() => setSelectedId(item.id)} />)}</TreeGroup>
          </div>
        </aside>

        <div className="arch-canvas-shell">
          <div className="arch-canvas-status"><span><b>PLAN</b> 1:100</span><span>{draft.snap}mm snap · {tool} tool</span></div>
          {canvas}
          <div className="arch-scale"><span>0</span><i /><span>4m</span><i /><span>8m</span></div>
          <p className="arch-mobile-note">정밀 drag 편집은 900px 이상 화면에서 제공됩니다. 수치 입력과 검증은 모바일에서도 가능합니다.</p>
        </div>

        <aside className="arch-right-panel">
          <div className="arch-panel-title"><span>PROPERTIES</span><strong>{selectedId || "No selection"}</strong></div>
          <div className="arch-inspector">
            {selectedColumn && <><InspectorRow label="Center X" value={selectedColumn.center[0]} onChange={(value) => updateNumber("x", value)} /><InspectorRow label="Center Y" value={selectedColumn.center[1]} onChange={(value) => updateNumber("y", value)} /><InspectorRow label="Width" value={selectedColumn.width} onChange={(value) => updateNumber("width", value)} /><InspectorRow label="Depth" value={selectedColumn.depth} onChange={(value) => updateNumber("depth", value)} /></>}
            {selectedWall && <><InspectorRow label="Start X" value={selectedWall.start[0]} onChange={(value) => updateNumber("x1", value)} /><InspectorRow label="Start Y" value={selectedWall.start[1]} onChange={(value) => updateNumber("y1", value)} /><InspectorRow label="End X" value={selectedWall.end[0]} onChange={(value) => updateNumber("x2", value)} /><InspectorRow label="End Y" value={selectedWall.end[1]} onChange={(value) => updateNumber("y2", value)} /><InspectorRow label="Thickness" value={selectedWall.thickness} onChange={(value) => updateNumber("thickness", value)} /></>}
            {selectedOpening && <><div className="arch-readonly"><span>Host wall</span><code>{selectedOpening.wall_id}</code></div><InspectorRow label="Offset" value={selectedOpening.offset} onChange={(value) => updateNumber("offset", value)} /><InspectorRow label="Width" value={selectedOpening.width} onChange={(value) => updateNumber("width", value)} /></>}
            {selectedGrid && <InspectorRow label={`${selectedGrid.axis.toUpperCase()} offset`} value={selectedGrid.axis === "x" ? selectedGrid.start[0] : selectedGrid.start[1]} onChange={(value) => updateNumber("offset", value)} />}
            {!selectedColumn && !selectedWall && !selectedOpening && !selectedGrid && <p className="arch-help">객체를 선택하면 pixel이 아닌 정확한 mm 좌표와 치수를 편집할 수 있습니다.</p>}
          </div>

          <div data-testid="architecture-health" className={`arch-health ${health}`} role="status" aria-live="polite">
            <ArchitectureIcon name="health" />
            <div><strong>{healthText}</strong><small>{health === "ready" ? readiness.message : health === "failed" ? readiness.message : `Cold-start check · attempt ${healthAttempts}`}</small></div>
            {health === "failed" && <button data-testid="architecture-health-retry" type="button" onClick={readiness.retry}>수동 재시도</button>}
          </div>

          <div className="arch-contract-card" data-testid="architecture-flow">
            <div data-testid="architecture-stage-contract"><span>01</span><div><strong>Contract locked</strong><small>Datum + exact mm values</small></div></div>
            <div data-testid="architecture-stage-writer"><span>02</span><div><strong>DXF written</strong><small>R2013 entities + trace IDs</small></div></div>
            <div data-testid="architecture-stage-reopen"><span>03</span><div><strong>DXF reopened</strong><small>Independent parser, saved bytes</small></div></div>
            <div data-testid="architecture-stage-remeasure"><span>04</span><div><strong>Remeasured</strong><small>Dimensions + room topology</small></div></div>
            <div data-testid="architecture-stage-gate"><span>05</span><div><strong>Approved</strong><small>No pass, no official bundle</small></div></div>
          </div>

          <button data-testid="architecture-run-verification" className="arch-run" type="button" disabled={verification === "running" || health !== "ready"} onClick={runVerification}>{verification === "running" ? <><span className="spinner" /> READING DXF…</> : health === "failed" ? <><ArchitectureIcon name="alert" /> 재연결 필요</> : health !== "ready" ? <><span className="spinner" /> 검증 엔진 준비 중</> : verification === "failed" ? <><ArchitectureIcon name="run" /> RETRY MANUALLY</> : <><ArchitectureIcon name="run" /> GENERATE + VERIFY DXF</>}</button>
          <p className="arch-boundary">NOT A CERTIFICATION · 구조·안전·법규 판정이 아닙니다.</p>
        </aside>
      </section>

      <section className={`arch-verification ${verification}`} id="verification">
        <div className="arch-result-head">
          <div><span>INDEPENDENT EVIDENCE</span><h2>{verification === "passed" ? "DXF 재측정 통과" : verification === "failed" ? "공식 export 차단" : verification === "running" ? "도면을 다시 읽는 중" : "검증 대기"}</h2><p>{message || "캔버스 값을 DesignContract로 잠근 뒤 저장된 DXF만 다시 측정합니다."}</p></div>
          <div data-testid="architecture-verified-badge" className={`arch-verified ${verification}`} role="status" aria-label={`Architecture verification status: ${verification}`}>{verification === "passed" ? <ArchitectureIcon name="check" /> : verification === "failed" ? <ArchitectureIcon name="alert" /> : null}<span>{verification === "passed" ? "VERIFIED / PASS" : verification.toUpperCase()}</span></div>
          <button data-testid="architecture-download" type="button" className="arch-download" disabled={verification !== "passed" || !result?.bundle_base64} onClick={download}><ArchitectureIcon name="download" /><span>DXF + PDF + JSON</span></button>
        </div>
        <div className="arch-evidence-grid">
          <div data-testid="verification-timeline" className="arch-timeline"><span>PIPELINE TIMELINE</span>{presentationTimeline.map((item) => <div data-testid={`architecture-timeline-${item.id}`} key={item.id}><i className={timelineStatusClass(item.status)} aria-hidden="true" /><strong>{item.label}</strong><code>{item.status}</code></div>)}</div>
          <div data-testid="verification-summary" className="arch-summary"><span>REMEASUREMENT SUMMARY</span><div><b>0.001 mm</b><small>comparison epsilon</small></div><div><b>{result?.measurements.filter((item) => item.passed).length || 0}/{result?.measurements.length || 0}</b><small>dimensions passed</small></div><div><b>{result?.violations.length || 0}</b><small>required violations</small></div><div><b>{String(result?.summary.walls ?? draft.walls.length)}</b><small>walls measured</small></div><div><b>{result?.summary.gross_area_m2 != null ? `${result.summary.gross_area_m2} m²` : "—"}</b><small>gross enclosed area</small></div><div><b>{String(result?.summary.rooms ?? draft.roomSeeds.length)}</b><small>room seeds resolved</small></div></div>
          <div className="arch-hashes"><span>TRACEABLE HASHES</span><label>Contract<code data-testid="architecture-contract-hash">{result?.contract_hash || "sha256:pending"}</code></label><label>DXF artifact<code data-testid="architecture-artifact-hash">{result?.artifact_hash || "sha256:pending"}</code></label><p>PDF: <b>DO NOT SCALE</b> · 제작 기준은 bundle의 DXF입니다.</p></div>
        </div>
        {result?.violations.length ? <div className="arch-violations">{result.violations.map((item, index) => <article key={`${item.code}-${index}`}><code>{item.code}</code><strong>{item.message}</strong><span>{item.entity_ids.join(", ")}</span></article>)}</div> : null}
      </section>
    </main>
  );
}

function TreeGroup({ label, count, children }: { label: string; count: number; children: React.ReactNode }) {
  return <section><h3><span><ArchitectureIcon name="tree" />{label}</span><b>{count}</b></h3>{children}</section>;
}

function TreeItem({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return <button type="button" className={active ? "active" : ""} aria-pressed={active} onClick={onClick}><ArchitectureIcon name="tree" /><span>{label}</span></button>;
}

function InspectorRow({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  const testId = `architecture-inspector-${label.toLowerCase().replaceAll(" ", "-")}`;
  return <label><span>{label}</span><div><input data-testid={testId} type="number" inputMode="decimal" value={value} step="1" onChange={(event) => onChange(Number(event.target.value))} /><small>mm</small></div></label>;
}

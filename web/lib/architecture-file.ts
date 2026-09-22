import type { ArchitectureDraft } from "../app/architecture-workspace.tsx";

export const MAX_PROJECT_BYTES = 1_048_576;
const fail = (field: string): never => { throw new Error(`${field}: 올바른 작업 파일인지 확인해 주세요.`); };
function object(value: unknown, field: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return fail(field);
  return value as Record<string, unknown>;
}
function text(value: unknown, field: string) {
  if (typeof value !== "string" || !value.trim() || value.length > 200) fail(field);
}
function number(value: unknown, field: string, positive = false) {
  if (typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > 1e12 || (positive && value <= 0)) fail(field);
}
function point(value: unknown, field: string) {
  if (!Array.isArray(value) || value.length !== 2) return fail(field);
  value.forEach(v => number(v, field));
}
function choice(value: unknown, allowed: unknown[], field: string) {
  if (!allowed.includes(value)) fail(field);
}

export function serializeArchitecture(draft: ArchitectureDraft): string {
  return JSON.stringify({ format: "datumguard-architecture", version: 1, draft }, null, 2);
}

export function parseArchitecture(source: string): ArchitectureDraft {
  if (new TextEncoder().encode(source).length > MAX_PROJECT_BYTES) fail("파일 크기(최대 1MB)");
  let parsed: unknown;
  try { parsed = JSON.parse(source); } catch { return fail("JSON 형식"); }
  const envelope = object(parsed, "작업 파일");
  if (envelope.format !== "datumguard-architecture" || envelope.version !== 1) fail("지원하지 않는 파일 버전");
  const draft = object(envelope.draft, "작업 내용");
  text(draft.projectName, "프로젝트 이름"); text(draft.revision, "리비전");
  choice(draft.presetId, ["architecture-studio", "architecture-open-loop"], "기본 유형");
  choice(draft.snap, [10, 50, 100], "스냅");
  const allIds = new Set<string>();
  const groups: Record<string, Record<string, unknown>[]> = {};
  for (const key of ["grids", "walls", "openings", "columns", "roomSeeds"]) {
    const items = draft[key];
    if (!Array.isArray(items) || items.length > 200) return fail(`${key}(최대 200개)`);
    groups[key] = items.map(item => {
      const row = object(item, key); text(row.id, `${key}.id`);
      if (allIds.has(row.id as string)) fail(`중복 ID ${row.id}`);
      allIds.add(row.id as string); return row;
    });
  }
  for (const row of groups.grids) {
    text(row.label, "그리드 이름"); point(row.start, "그리드 시작점"); point(row.end, "그리드 끝점");
    choice(row.axis, ["x", "y", "custom"], "그리드 축"); choice(row.locked, [true, false], "그리드 잠금");
  }
  for (const row of groups.walls) {
    point(row.start, "벽 시작점"); point(row.end, "벽 끝점"); number(row.thickness, "벽 두께", true);
    choice(row.wall_type, ["exterior", "interior", "partition", "custom"], "벽 유형");
  }
  const walls = new Set(groups.walls.map(row => row.id));
  for (const row of groups.openings) {
    if (!walls.has(row.wall_id)) fail(`연결된 벽이 없는 개구부 ${row.id}`);
    choice(row.type, ["door", "window", "opening"], "개구부 유형");
    number(row.offset, "개구부 위치"); number(row.width, "개구부 너비", true);
    if (row.height !== undefined) number(row.height, "개구부 높이", true);
    if (row.sill_height !== undefined) number(row.sill_height, "창턱 높이");
  }
  for (const row of groups.columns) {
    choice(row.type, ["rectangular_column"], "기둥 유형"); point(row.center, "기둥 중심");
    number(row.width, "기둥 너비", true); number(row.depth, "기둥 깊이", true); number(row.rotation_deg, "기둥 회전");
  }
  for (const row of groups.roomSeeds) {
    text(row.name, "실 이름"); point(row.point, "실 기준점");
    if (row.expected_area !== undefined) number(row.expected_area, "실 면적", true);
  }
  return draft as ArchitectureDraft;
}

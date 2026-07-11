# DatumGuard v0.2 CAD Artifact Assurance Handoff

## 현재 작업 상태

- Repository: `https://github.com/tjwnsdhfz/datumguard`
- Branch: `agent/cad-artifact-assurance`
- Base: `main` at `2d1f08e`
- Production web: `https://datumguard-tjwnsdhfz.vercel.app`
- Production API: `https://datumguard-api.onrender.com`

이 문서의 v0.2 기능은 feature branch에 구현·검증되었으며 아직 production merge 전이다.

## 공개 workspace

| Route | 분야 | 공식 artifact/evidence |
|---|---|---|
| `/` | Architecture | serialized R2013 DXF 재측정, 4-room/96m² demo |
| `/piping` | Plant·semiconductor utility | route/support/clearance DXF 재측정 |
| `/plate` | Mechanical·ship plate | hole/slot/cutout와 공차 DXF 재측정 |
| `/solid` | 3D solid part | OpenCascade STEP 생성, 별도 process 재입력, mesh·dimension evidence |
| `/intake` | Existing CAD artifact | 외부 DXF·STEP·IFC immutable audit와 revision compare |

`/solid`은 mounting plate, angle bracket, flange를 지원한다. `/intake`는 contract 없는 파일을
검사하므로 `approval_eligible=false`가 고정이며 제작 승인을 만들지 않는다.

## Backend·API·MCP

- Python 3.12, Pydantic, ezdxf, Shapely, OR-Tools, CadQuery/OpenCascade, IfcOpenShell
- CadQuery writer/auditor는 고정 JSON operation만 받는 `cad_worker` subprocess로 격리
- `POST /api/v1/solid/designs/run`
- `POST /api/v1/artifacts/audit`
- `POST /api/v1/artifacts/compare`
- `GET /api/v1/schema/solid-part-contract`
- `/api/v1/domains`는 5개 workspace를 반환
- 기존 MCP 9개 도구 하위 호환 + `artifact_audit`, `artifact_compare`, `solid_generate_verify` = 12개
- 파일당 20MB, request body 48MB, stateless·no persistence

## 실제 CAD 상호운용 증거

2026-07-12 Rhino 8.30에서 검증 mounting plate STEP을 실제 import했다.

- OpenCascade official evidence: valid solid 1, bbox `120×80×8mm`, dimensions 15/15 pass
- Rhino secondary evidence: `Brep` 1, `Millimeters`, bbox `120×80×8mm`
- Rhino output: 63,911-byte `.3dm`
- 고정 evidence: `docs/evidence/rhino-step-smoke.json`
- 재현: Rhino에서 `StartScriptServer` 실행 후
  `python tools/rhino_step_smoke.py --connect-existing`

Rhino evidence는 STEP 공식 verifier를 대체하지 않으며 hosted API는 arbitrary Rhino/script command를
노출하지 않는다.

## 검증 결과

2026-07-12 실행:

- `ruff format --check src tests tools`: pass
- `ruff check src tests tools`: pass
- `mypy src/datumguard`: pass, 25 source files
- `pytest`: pass, 245 tests; 기존 Starlette/httpx deprecation warning 1건
- `npm run typecheck`: pass
- `npm run lint`: pass
- `npm run build`: pass, static routes `/`, `/piping`, `/plate`, `/solid`, `/intake`
- Playwright real API E2E: pass, Chromium 15 tests
- Solid demo capture: `docs/assets/demo/solid-step-verified.png`, 1440×960
- `git diff --check`: pass
- Local Docker build: Docker CLI가 설치되지 않아 미실행; GitHub `containers` job이 두 image를 build한다.

## 배포·다음 행동

1. 모든 변경을 commit하고 feature branch를 push한다.
2. Draft PR을 열어 GitHub CI의 backend/web/container job을 확인한다.
3. CI가 통과하면 PR을 ready로 전환하고 merge한다.
4. Render가 v0.2 dependency image를 배포한 뒤 Vercel production이 새 API를 바라보는지 확인한다.
5. `deployment-smoke`로 5개 route, solid schema, health/domains와 CORS를 검증한다.
6. Production에서 `/solid` STEP pass와 `/intake` DXF upload를 최종 smoke한다.

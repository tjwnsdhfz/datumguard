# DatumGuard v0.2.1 Production Handoff

## Production 기준점

- Repository: `https://github.com/tjwnsdhfz/datumguard`
- Release source and immutable evidence: [DatumGuard v0.2.1](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.1)
- Production web: `https://datumguard-tjwnsdhfz.vercel.app`
- Production API: `https://datumguard-api.onrender.com`
- API runtime version: `0.2.1`
- Runtime provenance: `/api/v1/health.release_sha`; Render-success smoke가 release commit과 exact-match
- Previous rollback baseline: [`v0.2.0`](operations/rollback-baseline.md)

CAD Artifact Assurance, 제한형 STEP, Product Case Study와 social preview는 `main`에 병합·배포되었다.
v0.2.1은 공개 test 수치, route별 canonical/Open Graph metadata와 privacy title을 정정하고, Render
완료 뒤 runtime `release_sha`까지 대조하는 2단계 deployment smoke를 추가한다. 정확한 CI·Security·
deployment·smoke ID와 release SBOM은 GitHub release notes에 고정한다.

## 공개 route와 실제 가용 범위

| Route | 분야 | Production 상태 | artifact/evidence |
|---|---|---|---|
| `/case-study` | Product Case Study | 활성 | 문제, assurance method, evidence, limits 요약 |
| `/` | Architecture | 활성 | serialized R2013 DXF 재측정, 4-room/96m² demo |
| `/piping` | Plant·semiconductor utility | 활성 | route/support/clearance DXF 재측정 |
| `/plate` | Mechanical·ship plate | 활성 | hole/slot/cutout와 공차 DXF 재측정 |
| `/solid` | 제한형 3D solid part | UI·schema 공개, hosted run 비활성 | local/CI에서 STEP 생성, 별도 process 재입력, mesh·dimension evidence |
| `/intake` | Existing CAD artifact | 활성 | 외부 DXF·STEP·IFC immutable audit와 revision compare |

`/solid`은 mounting plate, angle bracket, flange만 지원한다. 저장 STEP의 B-rep, bbox, topology와
계약된 cylindrical feature를 검증할 뿐 범용 3D·assembly 또는 구조강도, 압력, 피로, 재료,
용접, 가공성과 산업표준 적합성을 판정하지 않는다. Render Free에서는
`DATUMGUARD_ENABLE_SOLID=false`이며 실행 endpoint가 `503 DG_CAPABILITY_DISABLED`를 반환한다.

`/intake`는 contract 없는 외부 파일을 검사하므로 `approval_eligible=false`가 고정이며 제작 승인을
만들지 않는다.

## Backend·API·MCP

- Python 3.12, Pydantic, ezdxf, Shapely, OR-Tools, CadQuery/OpenCascade, IfcOpenShell
- CadQuery writer/auditor는 고정 JSON operation만 받는 `cad_worker` subprocess로 격리
- Hosted active: Architecture, Piping, Plate, Artifact Lab
- Local/CI active, hosted disabled: `POST /api/v1/solid/designs/run`
- Hosted active: `POST /api/v1/artifacts/audit`, `POST /api/v1/artifacts/compare`
- Hosted schema: `GET /api/v1/schema/solid-part-contract`
- Hosted `/api/v1/domains`: base 3개 + Artifact Lab = 4개; Solid은 fail-closed 상태라 registry에서 제외
- 기존 MCP 9개 도구 하위 호환 + `artifact_audit`, `artifact_compare`, `solid_generate_verify` = 12개
- 파일당 20MB, upload 합계 40MB, request body 48MB, stateless·no persistence

## 실제 CAD 상호운용 증거

2026-07-12 Rhino 8.30에서 검증 mounting plate STEP을 실제 import했다.

- OpenCascade official geometry evidence: valid solid 1, bbox `120×80×8mm`, dimensions 15/15 pass
- Rhino secondary evidence: `Brep` 1, `Millimeters`, bbox `120×80×8mm`
- Rhino output: 63,911-byte `.3dm`
- 고정 evidence: `docs/evidence/rhino-step-smoke.json`
- 재현: Rhino에서 `StartScriptServer` 실행 후
  `python tools/rhino_step_smoke.py --connect-existing`

Rhino evidence는 STEP 공식 verifier를 대체하지 않으며 hosted API는 arbitrary Rhino/script command를
노출하지 않는다.

## 검증 결과

v0.2.1 release gate:

- Ruff format/check: pass
- mypy: pass
- pytest: **256 passed**
- web typecheck, lint, build: pass
- Playwright real API E2E: **Chromium 24 passed**
- backend/web container build, SBOM 생성, fixed-critical scan: pass

- PR dependency review: pass
- push security: pip audit, Python·JavaScript/TypeScript CodeQL pass

Production smoke:

- API version `0.2.1`, exact `release_sha`, `solid=false`, `artifact=true`: pass
- `/case-study`와 다섯 engineering workspace DOM sentinel: pass
- Architecture serialized-DXF approval canary: pass
- Artifact Lab DXF audit canary: pass
- Solid hosted endpoint `503` fail-closed: pass
- CORS contract: pass

이 목록의 immutable run·deployment ID는 [v0.2.1 release](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.1)에 기록한다.

## 다음 release로 넘기는 항목

1. 계획 상태인 100개 golden contract + 자연어 50개 benchmark를 실행하고 결과를 공개한다.
2. Render Free가 아닌 후보 환경에서 동시성·최대 upload 부하 검증과 rollback drill을 수행한다.
3. 외부 uptime/error tracking과 장기 metric retention은 비용 승인 뒤 연결한다.

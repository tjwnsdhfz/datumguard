# DatumGuard v0.2 Production Handoff

## Production 기준점

- Repository: `https://github.com/tjwnsdhfz/datumguard`
- v0.2.0 pre-case-study source: `main` at `b2dd6e5ebd7f21780295f2f37331dadce14eaf68`
- Production web: `https://datumguard-tjwnsdhfz.vercel.app`
- Production API: `https://datumguard-api.onrender.com`
- API runtime version: `0.2.0`
- Vercel deployment: GitHub deployment `5406289230`
- Render deployment: GitHub deployment `5406318427`
- Verified smoke: [run 29163908612](https://github.com/tjwnsdhfz/datumguard/actions/runs/29163908612)

CAD Artifact Assurance와 제한형 STEP 기능은 v0.2.0으로 `main`에 병합·배포되었다. `b2dd6e5`는
Case Study 변경 전 제품·CI·배포 evidence 기준점이며, Case Study merge 후에는 새 commit의 CI와
여섯-route deployment smoke를 최종 release evidence로 기록한다.

## 공개 route와 실제 가용 범위

| Route | 분야 | Production 상태 | artifact/evidence |
|---|---|---|---|
| `/case-study` | Product Case Study | 이 변경에서 추가; merge·deploy 후 공개 | 문제, assurance method, evidence, limits 요약 |
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

v0.2.0 pre-case-study 기준점 `b2dd6e5`의
[CI run 29163874605](https://github.com/tjwnsdhfz/datumguard/actions/runs/29163874605):

- Ruff format/check: pass
- mypy: pass
- pytest: **256 passed**, warning 3건
- web typecheck, lint, build: pass
- Playwright real API E2E: **Chromium 19 passed**
- backend/web container build, SBOM 생성, fixed-critical scan: pass

[Production smoke run 29163908612](https://github.com/tjwnsdhfz/datumguard/actions/runs/29163908612):

- API version `0.2.0`, `solid=false`, `artifact=true`: pass
- 다섯 pre-case-study engineering UI route DOM sentinel: pass
- Architecture serialized-DXF approval canary: pass
- Artifact Lab DXF audit canary: pass
- Solid hosted endpoint `503` fail-closed: pass
- CORS contract: pass

## 남은 release 확인

1. Case Study 변경 commit에서 CI를 다시 실행하고 새 pytest/Playwright 개수를 기록한다.
2. Vercel Preview에서 `/case-study`와 기존 다섯 engineering route의 실제 DOM sentinel을 확인한다.
3. merge 후 Production deployment가 새 commit을 가리키는지 확인한다.
4. 여섯 public route, API v0.2.0 capability, Architecture/Artifact canary, Solid `503`, CORS를
   `deployment-smoke`로 다시 검증한다.
5. [Rollback baseline](operations/rollback-baseline.md)의 deployment ID와 smoke link를 새 release
   evidence로 갱신한다.
6. 계획 상태인 100개 golden contract + 자연어 50개 benchmark를 완료 전 성과로 표기하지 않는다.

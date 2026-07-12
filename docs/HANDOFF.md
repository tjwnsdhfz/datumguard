# DatumGuard v0.3.0 Production Handoff

## Production 기준점

- Repository: `https://github.com/tjwnsdhfz/datumguard`
- Evidence release: [`v0.3.0`](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.3.0); final tag SHA와 release-note deployment ID가 불변 기준
- Validated FrameGuard feature snapshot: [`472df5fe431277244fc0fcda1ee9aa3b6284ddff`](https://github.com/tjwnsdhfz/datumguard/commit/472df5fe431277244fc0fcda1ee9aa3b6284ddff) on `main`
- Production web: `https://datumguard-tjwnsdhfz.vercel.app`
- Production API: `https://datumguard-api.onrender.com`
- API runtime version: `0.3.0`
- Runtime provenance: `/api/v1/health.release_sha`; strict production smoke가 위 `main` SHA와 exact-match
- Vercel production: GitHub deployment `5413026696`
- Render production: GitHub deployment `5413009032`; Render deploy `dep-d99pkfeq1p3s73d3gjj0`
- Rollback baseline: [`v0.2.1`](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.1), Vercel `5410294611`, Render `5410321107`

CAD Artifact Assurance, 제한형 STEP, Product Case Study, FrameGuard, OpenBIM 연구 소스와 웹 경로가
`main`에 병합·배포되었다. 공개 Render에서는 FrameGuard가 활성이고 OpenBIM·BCF와 Solid 실행은
fail-closed 상태다. 아래 run과 deployment record는 FrameGuard feature snapshot을 증명하고, 문서 승격
뒤의 최종 source/deployment ID는 v0.3.0 release notes에 고정한다.

## 공개 route와 실제 가용 범위

| Route | 분야 | Production 상태 | artifact/evidence |
|---|---|---|---|
| `/case-study` | Product Case Study | 활성 | 문제, assurance method, evidence, limits 요약 |
| `/` | Architecture | 활성 | serialized R2013 DXF 재측정, 4-room/96m² demo |
| `/piping` | Plant·semiconductor utility | 활성 | route/support/clearance DXF 재측정 |
| `/frame` | Structural frame screening | 활성 | exact 2D solver, serialized DXF 재개봉, screening evidence |
| `/plate` | Mechanical·ship plate | 활성 | hole/slot/cutout와 공차 DXF 재측정 |
| `/solid` | 제한형 3D solid part | UI·schema 공개, hosted run 비활성 | local/CI에서 STEP 생성, 별도 process 재입력, mesh·dimension evidence |
| `/intake` | Existing CAD artifact | 활성 | 외부 DXF·STEP·IFC immutable audit와 revision compare |
| `/openbim` | OpenBIM research | 웹 경로 공개, hosted run 비활성 | 합성 IFC4+IDS 연구 UI; production API evidence 생성은 차단 |

`/solid`은 mounting plate, angle bracket, flange만 지원한다. 저장 STEP의 B-rep, bbox, topology와
계약된 cylindrical feature를 검증할 뿐 범용 3D·assembly 또는 구조강도, 압력, 피로, 재료,
용접, 가공성과 산업표준 적합성을 판정하지 않는다. Render Free에서는
`DATUMGUARD_ENABLE_SOLID=false`이며 실행 endpoint가 `503 DG_CAPABILITY_DISABLED`를 반환한다.

`/intake`는 contract 없는 외부 파일을 검사하므로 `approval_eligible=false`가 고정이며 제작 승인을
만들지 않는다. `/openbim`도 `research_validation_only=true`, `approval_eligible=false`이며 공개
Render의 `DATUMGUARD_ENABLE_OPENBIM=false`, `DATUMGUARD_ENABLE_BCF=false` 설정으로 실행을 차단한다.

## Backend·API·MCP

- Python 3.12, Pydantic, NumPy, ezdxf, Shapely, OR-Tools, CadQuery/OpenCascade, IfcOpenShell
- CadQuery writer/auditor는 고정 JSON operation만 받는 `cad_worker` subprocess로 격리
- Hosted active: Architecture, Piping, Plate, FrameGuard, Artifact Lab
- Local/CI active, hosted disabled: `POST /api/v1/solid/designs/run`
- Source/CI active, hosted disabled: `POST /api/v1/openbim/evidence/run`
- Hosted active: `POST /api/v1/artifacts/audit`, `POST /api/v1/artifacts/compare`
- Hosted schema: `GET /api/v1/schema/solid-part-contract`
- Hosted `/api/v1/domains`: base 3개 + FrameGuard + Artifact Lab = 5개; Solid·OpenBIM은 fail-closed 상태라 registry에서 제외
- 기존 MCP 9개 도구 하위 호환 + Artifact/Solid 3개 + FrameGuard 6개 = 18개
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

v0.3.0 production gate:

- Ruff format/check: pass
- mypy: pass
- pytest: **376 passed**
- web typecheck, lint, build: pass
- Playwright real API E2E: **Chromium 35 passed**
- backend/web container build, SBOM 생성, fixed-critical scan: pass
- CI: [run `29194952632`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29194952632)

- Push security: pip audit, Python·JavaScript/TypeScript CodeQL pass — [run `29194952607`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29194952607)
- Optional research runtime: genuine OpenSeesPy parity와 PyTorch Geometric smoke pass — [run `29194964854`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29194964854)

Production smoke:

- Feature deployment API version `0.3.0`, exact `release_sha=472df5fe...`, `frame=true`, `solid=false`, `artifact=true`: pass
- `/case-study`, Architecture, Piping, FrameGuard, Plate, Solid UI와 Artifact Lab DOM sentinel: pass
- Architecture serialized-DXF approval canary: pass
- FrameGuard deterministic solver canary: pass
- Artifact Lab DXF audit canary: pass
- Solid hosted endpoint `503` fail-closed: pass
- CORS contract: pass
- Strict smoke: [run `29195107475`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29195107475)

Vercel `5413026696`과 Render `5413009032`는 모두 같은 production SHA를 가리키며 성공 상태다.

## Production FrameGuard assurance

FrameGuard full pipeline은 v0.3.0 production에 배포되었고 `/frame`, `structural_frame` registry와
deterministic canary가 같은 revision에서 검증됐다.

- Web: `/frame`
- Exact screening: `datumguard_numpy_2d_frame_v1`; 2D linear-elastic Euler–Bernoulli only
- CAD input: Rhino/GH straight centerline, support, load, section metadata와 explicit unit/datum
- CAD gate: serialized R2013/mm DXF를 별도 reader가 `0.001 mm` 기준으로 재개봉
- OpenSees evidence: genuine `openseespy==3.8.0.0`, engine 3.8, required 6 cases `6/6 PASSED`
- PyG evidence: 90 cases, train/validation/test `48/12/30`, 4-bay topology holdout, leakage 0
- GraphSAGE test: displacement MAE/R² `0.627426/0.804861`, utilization `0.0371842/0.732706`
- GAT test: displacement MAE/R² `0.651228/0.792357`, utilization `0.0294386/0.806528`
- Surrogate boundary: `PREDICTED` 또는 `REVIEW_REQUIRED`; 항상 `authoritative=false`,
  `exact_solver_required=true`
- Packaged evidence: `src/datumguard/data/frame_opensees_parity.json`,
  `src/datumguard/data/frame_gnn_benchmark.json`
- Research dependency: 선택형 `frame-research` workflow에만 PyG/OpenSeesPy 설치; base Docker 제외

이는 제한된 2D 선형 탄성 Euler–Bernoulli frame의 초기 screening이다. OpenSees/PyG는 선택형
`frame-research` 검증 환경에만 설치되며 production 판정 경로와 base Docker에는 포함되지 않는다.
구조 안전, 법규 적합성, 접합부·좌굴·동적·비선형 거동 또는 전문 구조 검토를 대체하지 않는다.

## OpenBIM research status in v0.3.0

OpenBIM source와 `/openbim` 웹 경로는 v0.3.0 `main`에 포함됐지만, 공개 Render에서는
`DATUMGUARD_ENABLE_OPENBIM=false`와 `DATUMGUARD_ENABLE_BCF=false`다. 따라서 hosted evidence API
실행이나 BCF export가 검증된 production capability라는 뜻은 아니다.

- Web: `/openbim`
- API: `POST /api/v1/openbim/evidence/run`
- Domain id: `openbim_evidence`
- 판정 경계: `research_validation_only=true`, `approval_eligible=false`
- 입력: baseline IFC 20MiB, candidate IFC 20MiB, IDS 1MiB, 의미 입력 합계 41MiB
- request middleware body limit: multipart overhead를 포함한 48MiB
- 격리: heavy-operation queue + native IFC/IDS subprocess + timeout + redacted error
- 산출물: canonical JSON, escaped HTML, optional BCFZIP, manifest와 source SHA-256
- kill switch: `DATUMGUARD_ENABLE_OPENBIM`
- BCF API gate: `DATUMGUARD_ENABLE_BCF=false`가 기본이며 offline 연구 환경에서만 명시적으로 활성화
- Render production: `DATUMGUARD_ENABLE_OPENBIM=false`, `DATUMGUARD_ENABLE_BCF=false`로 fail-closed

연구 provenance:

- `protocol-v1` → `40f1f7a991e592511033a480c6799516578a45f8`
- `analysis-v1.0.2` → `9d147e30aa33a7c3571a83174d6b18a557662880`
- 30 held-out cases, 120 candidate records, 1,200 measured runs, engine error 0
- corrected Full TP/FP/FN `330/0/0`; clean·authorized FP 0; corrected 신규 issue 0
- v0.3.0 통합 CI: pytest 376 passed, Chromium Playwright 35 passed, web typecheck·lint·build와 OpenBIM interoperability job pass
- 최초 raw hash `sha256:58dcf7dc75246c9e884f4ad31be8709ff480e58c37a811d569f0fa779f7df1e9`
- detector 재실행 없이 clean analysis tag에서 evaluator field만 재계산
- 전체 issue source/rule coverage `360/360`, entity coverage `330/360`; primary issue는 모두 `330/330`
- buildingSMART IFC Validation Service 외부 확인은 아직 미완료

공식 연구 진입점은 [`awards-2026/README.md`](awards-2026/README.md)다. BCF 독립 graphical viewer,
`bcf-client` license 검토, buildingSMART hosted IFC 결과와 OpenBIM-enabled production
cold-start·CORS·부하 smoke는 아직 완료되지 않았다. 이 gate 전에는 OpenBIM 실행을 production 완료
기능으로 표시하지 않는다.

## 다음 release로 넘기는 항목

1. 계획 상태인 100개 golden contract + 자연어 50개 benchmark를 실행하고 결과를 공개한다.
2. Render Free가 아닌 후보 환경에서 동시성·최대 upload 부하 검증과 rollback drill을 수행한다.
3. 외부 uptime/error tracking과 장기 metric retention은 비용 승인 뒤 연결한다.
4. OpenBIM 외부 BCF viewer·buildingSMART hosted validation·license·OpenBIM-enabled production
   smoke gate를 별도 evidence로 완료한다.

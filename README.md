# DatumGuard

[![CI](https://github.com/tjwnsdhfz/datumguard/actions/workflows/ci.yml/badge.svg)](https://github.com/tjwnsdhfz/datumguard/actions/workflows/ci.yml)
[![Deployment Smoke](https://github.com/tjwnsdhfz/datumguard/actions/workflows/deployment-smoke.yml/badge.svg)](https://github.com/tjwnsdhfz/datumguard/actions/workflows/deployment-smoke.yml)
[![Live Demo](https://img.shields.io/badge/Live_Demo-Vercel-000000?logo=vercel)](https://datumguard-tjwnsdhfz.vercel.app)
[![API Endpoint](https://img.shields.io/badge/API_Endpoint-Render-46e3b7?logo=render&logoColor=000000)](https://datumguard-api.onrender.com/api/v1/health)

DatumGuard는 생성기가 “성공”했다고 보고한 CAD가 아니라, 저장된 artifact를 다시 열어 측정한 evidence로 export를 승인하는 오픈소스 Engineering Design Assurance 도구입니다.

**[60초 Case Study 열기 →](https://datumguard-tjwnsdhfz.vercel.app/case-study)** · [Live workspaces](https://datumguard-tjwnsdhfz.vercel.app) · [로컬 재현](docs/demo.md)

## 60초 요약

| | 핵심 |
|---|---|
| **문제** | 자연어·폼에서 CAD가 생성되어도 저장 파일의 실제 치수, datum, 공차가 요구조건과 같다는 보장은 없습니다. |
| **방법** | 요구를 versioned contract로 고정하고, writer와 분리된 reader가 serialized DXF 또는 STEP을 다시 열어 측정합니다. 모든 필수 검사가 통과할 때만 bundle을 활성화합니다. |
| **증거** | [v0.2.1 release](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.1)는 256 pytest, 24 Playwright, web/container/SBOM gate를 통과합니다. Render 완료 후 smoke는 공개 route와 canary뿐 아니라 API health의 `release_sha`가 배포 commit과 같은지도 확인하며, 정확한 run·deployment ID는 release notes에 고정합니다. |
| **한계** | 구조·안전·법규·산업표준 적합성이나 범용 3D를 판정하지 않습니다. 3D는 세 가지 제한형 solid family의 STEP 기하 검증만 local/CI에서 지원하며, 공개 Render Free API에서는 비활성입니다. 100개 golden contract + 자연어 50개 benchmark도 계획 단계로 아직 완료되지 않았습니다. |

| 결과 | 재현 fixture | 승인 게이트 |
|---|---|---|
| **PASS** | [4-room Architecture](fixtures/examples/architecture_four_room.json), [CDA piping](fixtures/examples/piping_utility.json) | 독립 재측정이 통과해 공식 bundle 생성 |
| **FAIL** | [300mm open loop](fixtures/examples/architecture_open_300mm.json), [clearance violation](fixtures/examples/piping_clearance_failure.json) | violation을 반환하고 공식 bundle 차단 |

> **중요:** PDF 미리보기는 `DO NOT SCALE`입니다. 2D 설계의 검증된 bundle에 포함된 DXF만 제작 기준 파일이며, `/intake`의 외부 파일 감사 결과는 informational evidence로서 제작 승인이 아닙니다.

[![DatumGuard의 architecture contract, CAD canvas, 독립 DXF verifier와 approval gate](docs/assets/demo/architecture-verified.png)](https://datumguard-tjwnsdhfz.vercel.app)

[공개 Architecture 데모 열기 →](https://datumguard-tjwnsdhfz.vercel.app) · [실행·재현 가이드 보기 →](docs/demo.md)

이미지의 재현 절차와 화면 계약은 [Architecture Demo Guide](docs/demo.md)에 고정되어 있습니다. Architecture, Piping, Plate는 저장된 DXF evidence가 통과해야만 bundle을 활성화합니다. 제한형 Solid은 같은 원칙을 STEP에 적용하지만 local/CI 전용이고, `/intake`는 외부 CAD 산출물을 변경하지 않고 감사합니다.

## Engineering domains

| 분야 | Route | 검증 예시 |
|---|---|---|
| Architecture | `/` | wall 폐합·연결, opening, grid/column, room area |
| Plant / Semiconductor Piping | `/piping` | route 연결·직교성, valve/support 위치, equipment clearance |
| Mechanical / Ship Plate | `/plate` | hole/slot/cutout, edge distance, ligament, overlap |
| 3D Solid Part — local/CI, hosted run disabled | `/solid` | 세 family의 OpenCascade B-rep, bbox, topology, hole/bore diameter와 axis |
| Existing CAD Artifact | `/intake` | DXF·STEP·IFC 구조 감사와 revision compare |

세부 범위와 분야별 비목표는 [Engineering Domains](docs/engineering-domains.md)에 정리되어 있습니다.

### Plant / Semiconductor Piping demo

![DatumGuard의 CDA utility piping route, support와 clearance 독립 DXF 검증 결과](docs/assets/demo/piping-verified.png)

재현 절차와 브라우저 계약은 [Piping Demo Guide](docs/piping-demo.md)에 고정되어 있습니다.

### 3D STEP solid demo

[![OpenCascade STEP 생성, 격리 재입력, 실제 mesh와 치수 검증](docs/assets/demo/solid-step-verified.png)](https://datumguard-tjwnsdhfz.vercel.app/solid)

Mounting plate, angle bracket, flange만 생성합니다. STEP writer와 격리된 OpenCascade process의 재입력·측정은 local/CI에서 통과하지만 공개 Render Free API의 실행 endpoint는 메모리 안전을 위해 `503 DG_CAPABILITY_DISABLED`로 닫혀 있습니다. 상세 contract·측정·Rhino 8 왕복 검증은 [3D Solid STEP Assurance](docs/solid-step.md)에 기록되어 있습니다. 외부 CAD 파일은 [Artifact Lab Guide](docs/artifact-lab.md)의 `/intake`에서 검사합니다.

## Assurance pipeline

```mermaid
flowchart LR
    UI["DesignContract<br/>form + confirmed intent"] --> CORE["Canonical geometry<br/>DXF writer"]
    CORE --> DXF["Serialized R2013 DXF<br/>layers + XDATA"]
    DXF --> VERIFY["Independent reader<br/>remeasure + constraints"]
    VERIFY -->|passed| GATE["Approval gate"]
    VERIFY -->|repairable| REPAIR["Bounded repair<br/>free parameters only, max 3"]
    REPAIR --> CORE
    GATE --> BUNDLE["DXF · SVG · DO NOT SCALE PDF<br/>verification JSON"]
```

Writer의 메모리 형상은 verifier로 전달되지 않습니다. Verifier는 직렬화된 DXF를 별도로 다시 읽고, 실제 측정값이 계약의 target·tolerance·constraint를 통과했을 때만 공식 bundle을 승인합니다.

제한형 3D 경로도 `SolidPartContract → OpenCascade STEP writer subprocess → 별도 OpenCascade re-import process → approval gate`로 writer와 verifier의 데이터 경로를 분리합니다. 이는 mounting plate, angle bracket, flange의 저장 STEP 기하 일치만 검증하며 범용 3D, assembly, 구조·압력·피로·재료·가공성 해석은 범위 밖입니다.

## 핵심 원칙

- 폼 입력을 `DesignContract`의 source of truth로 사용합니다.
- DXF writer와 verifier는 분리되어 있으며 verifier는 직렬화된 DXF를 재측정합니다.
- `locked` 치수와 datum은 자동수정하지 않습니다.
- 공차·필수 제약을 모두 통과한 경우에만 공식 ZIP bundle을 만듭니다.
- Rhino 결과는 선택적 secondary evidence일 뿐 공식 판정을 대체하지 않습니다.

## 빠른 시작

요구 사항은 Python 3.12+와 Node.js 20+입니다.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
datumguard-api
```

다른 터미널에서 웹을 실행합니다.

```bash
cd web
npm ci
npm run dev
```

브라우저에서 다음 경로를 엽니다.

- `http://localhost:3000/case-study`: 60초 product case study
- `http://localhost:3000/`: Interactive Architecture demo
- `http://localhost:3000/piping`: Plant/Semiconductor Utility Piping demo
- `http://localhost:3000/plate`: 샘플 플레이트 설계·검증
- `http://localhost:3000/solid`: 3D solid STEP 생성·독립 재입력
- `http://localhost:3000/intake`: 외부 DXF·STEP·IFC 감사·revision 비교
- `http://localhost:8000/docs`: FastAPI 문서

## Docker 실행

```bash
docker compose up --build
```

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- Health: `http://localhost:8000/api/v1/health`
- Readiness: `http://localhost:8000/api/v1/ready`

## 공개 배포

현재 공개 배포는 아래 주소에서 바로 사용할 수 있습니다.

- Web: [datumguard-tjwnsdhfz.vercel.app](https://datumguard-tjwnsdhfz.vercel.app)
- Product Case Study: [/case-study](https://datumguard-tjwnsdhfz.vercel.app/case-study)
- Architecture: [web root](https://datumguard-tjwnsdhfz.vercel.app)
- Plant / Semiconductor Piping: [/piping](https://datumguard-tjwnsdhfz.vercel.app/piping)
- Mechanical / Ship Plate: [/plate](https://datumguard-tjwnsdhfz.vercel.app/plate)
- 3D Solid STEP UI: [/solid](https://datumguard-tjwnsdhfz.vercel.app/solid) — UI·schema는 공개되지만 실행은 local/CI 기능이며 현재 Render Free API에서는 메모리 안전을 위해 비활성
- CAD Artifact Lab: [/intake](https://datumguard-tjwnsdhfz.vercel.app/intake)
- API: [health](https://datumguard-api.onrender.com/api/v1/health) · [domains](https://datumguard-api.onrender.com/api/v1/domains) · [OpenAPI](https://datumguard-api.onrender.com/docs)

현재 공개 기준은 [v0.2.1 release](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.1)입니다. Vercel 선행 smoke는 새 web과 기존 API의 하위 호환성을 확인하고, Render 완료 이벤트가 실행하는 최종 smoke는 API `version`, `release_sha`, capability, Architecture approval canary, Artifact Lab audit, Solid `503` fail-closed와 CORS를 같은 배포 revision에서 검사합니다. 도메인 evidence에서 Architecture는 96m²와 4개 room seed, Piping은 12.0m route와 1,975mm minimum clearance, Plate는 전체 치수 편차 0.000000mm를 보고합니다. 이전 `v0.2.0`의 고정 fallback은 [rollback baseline](docs/operations/rollback-baseline.md)에 보존합니다.

직접 복제해 배포하려면 공개 저장소 [tjwnsdhfz/datumguard](https://github.com/tjwnsdhfz/datumguard)를 사용합니다. 먼저 Render 버튼으로 backend를 만들고 발급된 API origin을 Vercel 배포 화면의 `NEXT_PUBLIC_DATUMGUARD_API_URL`에 입력합니다.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Ftjwnsdhfz%2Fdatumguard)
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Ftjwnsdhfz%2Fdatumguard&root-directory=web&env=NEXT_PUBLIC_DATUMGUARD_API_URL,NEXT_PUBLIC_GITHUB_URL)

- Backend는 루트 `Dockerfile`을 Render, Fly.io, Railway 같은 컨테이너 서비스에 배포합니다.
- Frontend는 Vercel 프로젝트의 Root Directory를 `web/`으로 지정하고, build 전에 `NEXT_PUBLIC_DATUMGUARD_API_URL`을 backend URL로 설정합니다.
- Backend의 `DATUMGUARD_CORS_ORIGINS`에는 frontend origin을 쉼표로 구분해 설정합니다.

`render.yaml`은 GitHub CI check가 통과한 commit만 backend에 자동 배포하도록 구성되어 있습니다. Vercel for GitHub는 Root Directory `web/`에서 PR Preview와 `main` Production을 만들며, `deployment-smoke`가 `/case-study`를 포함한 여섯 public route의 실제 DOM, API version/capability, Architecture와 활성화된 optional canary, 비활성 capability의 fail-closed 응답, CORS를 확인합니다. 정확한 연결 계약은 [GitHub Deployment Guide](docs/github-deployment.md), 환경변수·cold start 순서는 [Deployment Guide](docs/deployment.md)를 따릅니다.

배포가 끝나면 `$WEB_ORIGIN/case-study`, `/`, `/piping`, `/plate`, `/solid`, `/intake`를 모두 확인합니다. Frontend를 build한 뒤 `NEXT_PUBLIC_DATUMGUARD_API_URL`을 바꾸었다면 반드시 rebuild해야 합니다.

공개 데모는 stateless입니다. 계정·DB·서버 프로젝트 저장을 사용하지 않으며, 요청 파일과 자연어 원문을 영구 저장하지 않습니다. Hosted demo에는 Rhino 연결을 요구하지 않으며, Rhino evidence는 로컬 adapter가 있을 때만 secondary cross-check로 사용합니다.

운영 경계도 코드로 고정했습니다. 실제 수신 byte 제한, 파일별·합계 upload 제한, optional API key, anonymous/authenticated quota, heavy CAD queue, parser subprocess, request ID·redacted JSON log, `/live`·`/ready`·bounded `/metrics`, Solid/Artifact Lab kill switch를 제공합니다. 브라우저 draft는 30일 TTL의 IndexedDB에만 저장되며 [/privacy](https://datumguard-tjwnsdhfz.vercel.app/privacy)에서 전체 삭제할 수 있습니다. 10k DAU는 현재 Free 배포의 용량 주장이 아니며, 출시 체크리스트·장애/rollback·SLO·비용 후보는 [Operations Guide](docs/operations/README.md)와 [Cost Guard](docs/operations/cost-guard.md)에 분리했습니다.

OpenCascade Solid은 코드·Linux CI·Docker image에서 실제 STEP 생성과 재입력을 통과하지만, Render Free 512MB Production canary에서 HTTP 502가 발생해 `DATUMGUARD_ENABLE_SOLID=false`로 fail-closed했습니다. OOM 또는 worker restart는 의심되지만 직접 확인되지 않았습니다. 유료 변경 없이 기능을 과장하지 않기 위한 운영 결정이며, [Cost Guard](docs/operations/cost-guard.md)의 Render Standard 이상 staging에서 canary와 부하 검증을 통과한 뒤에만 다시 활성화합니다.

## API와 MCP

- 한 번에 생성·검증: `POST /api/v1/designs/run`
- 계약 검증: `POST /api/v1/contracts/validate`
- 건축 평면 생성·검증: `POST /api/v1/architecture/designs/run`
- 건축 계약 검증: `POST /api/v1/architecture/contracts/validate`
- 배관 route 생성·검증: `POST /api/v1/piping/designs/run`
- 배관 계약 검증: `POST /api/v1/piping/contracts/validate`
- 3D solid 생성·STEP 독립 검증: `POST /api/v1/solid/designs/run`
- CAD 파일 감사: `POST /api/v1/artifacts/audit`
- CAD revision 비교: `POST /api/v1/artifacts/compare`
- Liveness/readiness/metrics: `GET /api/v1/live`, `GET /api/v1/ready`, `GET /api/v1/metrics`
- 단계별 endpoint는 [TRD](docs/TRD.md)에 정리되어 있습니다.
- 로컬 MCP: `datumguard-mcp`

MCP는 기존 9개 설계 도구에 `artifact_audit`, `artifact_compare`, `solid_generate_verify`를 더한 12개 도구를 제공합니다.

MCP contract 분기는 입력의 `design_kind`로 결정합니다.

| `design_kind` | MCP application service | Web route |
|---|---|---|
| `architectural_plan` | Architecture | `/` |
| `piping_plan` | Piping | `/piping` |
| `solid_part` | OpenCascade STEP | `/solid` |
| 필드 없음 | Plate/panel 호환 경로 | `/plate` |

기존 9개 도구 이름은 plate·architecture·piping에서 하위 호환됩니다. `artifact_audit`과 `artifact_compare`는 contract 없는 실제 파일에 informational evidence만 만들고, `solid_generate_verify`는 `solid_part` contract를 실제 STEP으로 직렬화한 뒤 별도 OpenCascade worker에서 재측정합니다. `rhino_preview`는 secondary evidence이며 공식 판정을 변경하지 않습니다.

## 검증

```powershell
$env:UV_LINK_MODE = "copy" # Windows OneDrive only
uv sync --frozen --extra dev
uv run --frozen ruff check src tests tools
uv run --frozen mypy src/datumguard
uv run --frozen pytest
Set-Location web
npm run typecheck
npm run lint
npm run build
```

Case Study, Architecture, Piping, Plate, Solid, Artifact Lab route의 브라우저 계약은 실제 FastAPI를 함께 시작하는 Playwright E2E로 검사합니다.

```powershell
Set-Location web
npm run test:e2e
```

[v0.2.1 release evidence](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.1)는 backend **256 passed**, Chromium Playwright **24 passed**, web build, 두 container build, CycloneDX SBOM, fixed-critical scan, dependency review, pip audit와 두 CodeQL language 결과를 각각의 실제 run에 연결합니다. Render 배포 완료 뒤의 Production smoke는 health `release_sha`까지 대조합니다.

합성 예제 계약은 Architecture의 [통과 4-room studio](fixtures/examples/architecture_four_room.json)·[300mm open-loop 실패](fixtures/examples/architecture_open_300mm.json), Piping의 [통과 CDA route](fixtures/examples/piping_utility.json)·[clearance 실패](fixtures/examples/piping_clearance_failure.json)로 제공합니다. 기존 Architecture fixture도 하위 호환 회귀용으로 유지합니다. 모든 예제는 실사업장 도면이 아닌 공개 합성 데이터입니다.

## 문서

- [PRD](docs/PRD.md)
- [TRD](docs/TRD.md)
- [Prompt Design](docs/prompt-design.md)
- [Architecture Demo Guide](docs/demo.md)
- [Piping Demo Guide](docs/piping-demo.md)
- [3D Solid STEP Assurance](docs/solid-step.md)
- [Artifact Lab Guide](docs/artifact-lab.md)
- [Engineering Domains](docs/engineering-domains.md)
- [Mission Control Design System](docs/design-system.md)
- [Deployment Guide](docs/deployment.md)
- [GitHub Deployment Guide](docs/github-deployment.md)
- [현재 구현·배포 Handoff](docs/HANDOFF.md)
- [개발 프롬프트 실행 순서](prompts/INDEX.md)

## License

MIT

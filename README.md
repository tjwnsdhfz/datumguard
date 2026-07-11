# DatumGuard

[![CI](https://github.com/tjwnsdhfz/datumguard/actions/workflows/ci.yml/badge.svg)](https://github.com/tjwnsdhfz/datumguard/actions/workflows/ci.yml)
[![Deployment Smoke](https://github.com/tjwnsdhfz/datumguard/actions/workflows/deployment-smoke.yml/badge.svg)](https://github.com/tjwnsdhfz/datumguard/actions/workflows/deployment-smoke.yml)
[![Live Demo](https://img.shields.io/badge/Live_Demo-Vercel-000000?logo=vercel)](https://datumguard-tjwnsdhfz.vercel.app)
[![API Health](https://img.shields.io/badge/API_Health-Render-46e3b7?logo=render&logoColor=000000)](https://datumguard-api.onrender.com/api/v1/health)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Ftjwnsdhfz%2Fdatumguard)
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Ftjwnsdhfz%2Fdatumguard&root-directory=web&env=NEXT_PUBLIC_DATUMGUARD_API_URL,NEXT_PUBLIC_GITHUB_URL)

DatumGuard는 건축 평면, 플랜트·반도체 utility piping, 기계·조선 plate를 분야별 구조화 contract로 정의하고, 생성된 DXF를 다시 읽어 치수와 제약을 독립 검증한 뒤 통과한 파일만 내려받게 하는 오픈소스 Engineering Design Assurance 도구입니다.

> **중요:** DatumGuard MVP는 구조·안전·법규·산업표준 적합성을 판정하지 않습니다. PDF 미리보기는 `DO NOT SCALE`이며, 검증된 bundle의 DXF가 제작 기준 파일입니다.

[![DatumGuard의 architecture contract, CAD canvas, 독립 DXF verifier와 approval gate](docs/assets/demo/architecture-verified.png)](https://datumguard-tjwnsdhfz.vercel.app)

[공개 Architecture 데모 열기 →](https://datumguard-tjwnsdhfz.vercel.app) · [실행·재현 가이드 보기 →](docs/demo.md)

이미지의 재현 절차와 화면 계약은 [Architecture Demo Guide](docs/demo.md)에 고정되어 있습니다. `/`는 Architecture, `/piping`은 Plant/Semiconductor Piping, `/plate`는 Mechanical/Ship Plate workbench다. 세 모드 모두 실제 serialized DXF evidence가 통과해야만 bundle을 활성화합니다.

## Engineering domains

| 분야 | Route | 검증 예시 |
|---|---|---|
| Architecture | `/` | wall 폐합·연결, opening, grid/column, room area |
| Plant / Semiconductor Piping | `/piping` | route 연결·직교성, valve/support 위치, equipment clearance |
| Mechanical / Ship Plate | `/plate` | hole/slot/cutout, edge distance, ligament, overlap |

세부 범위와 분야별 비목표는 [Engineering Domains](docs/engineering-domains.md)에 정리되어 있습니다.

### Plant / Semiconductor Piping demo

![DatumGuard의 CDA utility piping route, support와 clearance 독립 DXF 검증 결과](docs/assets/demo/piping-verified.png)

재현 절차와 브라우저 계약은 [Piping Demo Guide](docs/piping-demo.md)에 고정되어 있습니다.

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

- `http://localhost:3000/`: Interactive Architecture demo
- `http://localhost:3000/piping`: Plant/Semiconductor Utility Piping demo
- `http://localhost:3000/plate`: 샘플 플레이트 설계·검증
- `http://localhost:8000/docs`: FastAPI 문서

## Docker 실행

```bash
docker compose up --build
```

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- Health: `http://localhost:8000/api/v1/health`

## 공개 배포

현재 공개 배포는 아래 주소에서 바로 사용할 수 있습니다.

- Web: [datumguard-tjwnsdhfz.vercel.app](https://datumguard-tjwnsdhfz.vercel.app)
- Architecture: [web root](https://datumguard-tjwnsdhfz.vercel.app)
- Plant / Semiconductor Piping: [/piping](https://datumguard-tjwnsdhfz.vercel.app/piping)
- Mechanical / Ship Plate: [/plate](https://datumguard-tjwnsdhfz.vercel.app/plate)
- API: [health](https://datumguard-api.onrender.com/api/v1/health) · [domains](https://datumguard-api.onrender.com/api/v1/domains) · [OpenAPI](https://datumguard-api.onrender.com/docs)

2026-07-11 실환경 smoke test에서 세 mode의 생성→serialized DXF 재측정→approval bundle이 모두 통과했습니다. Architecture는 96m²와 4개 room seed, Piping은 12.0m route와 1,975mm minimum clearance, Plate는 전체 치수 편차 0.000000mm를 보고했습니다.

직접 복제해 배포하려면 공개 저장소 [tjwnsdhfz/datumguard](https://github.com/tjwnsdhfz/datumguard)를 사용합니다. 먼저 Render 버튼으로 backend를 만들고 발급된 API origin을 Vercel 배포 화면의 `NEXT_PUBLIC_DATUMGUARD_API_URL`에 입력합니다.

- Backend는 루트 `Dockerfile`을 Render, Fly.io, Railway 같은 컨테이너 서비스에 배포합니다.
- Frontend는 Vercel 프로젝트의 Root Directory를 `web/`으로 지정하고, build 전에 `NEXT_PUBLIC_DATUMGUARD_API_URL`을 backend URL로 설정합니다.
- Backend의 `DATUMGUARD_CORS_ORIGINS`에는 frontend origin을 쉼표로 구분해 설정합니다.

`render.yaml`은 GitHub CI check가 통과한 commit만 backend에 자동 배포하도록 구성되어 있습니다. Vercel for GitHub는 Root Directory `web/`에서 PR Preview와 `main` Production을 만들며, `deployment-smoke`가 세 route와 API CORS를 확인합니다. 정확한 연결 계약은 [GitHub Deployment Guide](docs/github-deployment.md), 환경변수·cold start 순서는 [Deployment Guide](docs/deployment.md)를 따릅니다.

배포가 끝나면 `$WEB_ORIGIN/`, `$WEB_ORIGIN/piping`, `$WEB_ORIGIN/plate`를 모두 확인합니다. 각 모드는 Architecture, Piping, Plate 전용 run endpoint를 호출하므로 frontend를 build한 뒤 `NEXT_PUBLIC_DATUMGUARD_API_URL`을 바꾸었다면 반드시 rebuild해야 합니다.

공개 데모는 stateless입니다. 계정·DB·서버 프로젝트 저장을 사용하지 않으며, 요청 파일과 자연어 원문을 영구 저장하지 않습니다. Hosted demo에는 Rhino 연결을 요구하지 않으며, Rhino evidence는 로컬 adapter가 있을 때만 secondary cross-check로 사용합니다.

## API와 MCP

- 한 번에 생성·검증: `POST /api/v1/designs/run`
- 계약 검증: `POST /api/v1/contracts/validate`
- 건축 평면 생성·검증: `POST /api/v1/architecture/designs/run`
- 건축 계약 검증: `POST /api/v1/architecture/contracts/validate`
- 배관 route 생성·검증: `POST /api/v1/piping/designs/run`
- 배관 계약 검증: `POST /api/v1/piping/contracts/validate`
- 단계별 endpoint는 [TRD](docs/TRD.md)에 정리되어 있습니다.
- 로컬 MCP: `datumguard-mcp`

MCP는 `design_contract_draft`, `design_contract_validate`, `drawing_generate`, `drawing_verify`, `repair_propose`, `repair_apply`, `drawing_compare`, `export_bundle`, `rhino_preview`를 제공합니다.

MCP contract 분기는 입력의 `design_kind`로 결정합니다.

| `design_kind` | MCP application service | Web route |
|---|---|---|
| `architectural_plan` | Architecture | `/` |
| `piping_plan` | Piping | `/piping` |
| 필드 없음 | Plate/panel 호환 경로 | `/plate` |

9개 도구 이름은 모든 분야에서 동일합니다. Architecture의 `repair_propose`와 `repair_apply`는 선언된 `columns.<id>.center.0|1` 또는 `openings.<id>.offset` 자유값만 CP-SAT으로 제안·적용하며 locked 값과 wall topology를 거부합니다. `drawing_compare`는 같은 `design_kind`끼리만 비교하고, `export_bundle`은 분야별 독립 verifier가 `passed`를 반환한 경우에만 파일을 씁니다. `rhino_preview`에 선택적 `contract`를 함께 넘기면 canonical hash와 분야를 확인하지만, allowlisted adapter가 없을 때는 secondary evidence의 unavailable 상태만 반환합니다.

## 검증

```bash
ruff check .
mypy src/datumguard
pytest
cd web && npm run typecheck && npm run lint && npm run build
```

Architecture, Piping, Plate route의 브라우저 계약은 실제 FastAPI를 함께 시작하는 Playwright E2E로 검사합니다.

```bash
cd web
npm run test:e2e
```

합성 예제 계약은 Architecture의 [통과 4-room studio](fixtures/examples/architecture_four_room.json)·[300mm open-loop 실패](fixtures/examples/architecture_open_300mm.json), Piping의 [통과 CDA route](fixtures/examples/piping_utility.json)·[clearance 실패](fixtures/examples/piping_clearance_failure.json)로 제공합니다. 기존 Architecture fixture도 하위 호환 회귀용으로 유지합니다. 모든 예제는 실사업장 도면이 아닌 공개 합성 데이터입니다.

## 문서

- [PRD](docs/PRD.md)
- [TRD](docs/TRD.md)
- [Prompt Design](docs/prompt-design.md)
- [Architecture Demo Guide](docs/demo.md)
- [Piping Demo Guide](docs/piping-demo.md)
- [Engineering Domains](docs/engineering-domains.md)
- [Mission Control Design System](docs/design-system.md)
- [Deployment Guide](docs/deployment.md)
- [GitHub Deployment Guide](docs/github-deployment.md)
- [현재 구현·배포 Handoff](docs/HANDOFF.md)
- [개발 프롬프트 실행 순서](prompts/INDEX.md)

## License

MIT

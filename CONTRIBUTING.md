# Contributing to DatumGuard

DatumGuard는 AI-assisted CAD workflow에서 생성 성공과 치수 정확성을 분리해 검증하는
engineering assurance harness입니다. 기여는 새로운 기능 수보다 재현 가능한 contract,
독립 재측정 evidence, fail-closed 동작을 우선합니다.

## 먼저 확인할 범위

- DatumGuard의 구조 결과는 **preliminary structural screening**이며 구조 안전 인증,
  법규 검토, 제작 승인 또는 전문 엔지니어의 판단을 대체하지 않습니다.
- writer의 in-memory geometry를 verifier의 정답으로 사용하지 않습니다. 저장된 DXF, STEP,
  IFC artifact를 독립적으로 다시 읽고 측정해야 합니다.
- verifier가 실패하거나 지원 범위를 확정할 수 없으면 official export도 실패해야 합니다.
- `locked` dimension, datum, tolerance는 자동수정하지 않습니다.
- Rhino/Grasshopper 분석은 secondary evidence이며 official gate는 독립 verifier가 담당합니다.

제품 범위와 다음 우선순위는 [ROADMAP.md](ROADMAP.md), 보안과 데이터 처리 기준은
[SECURITY.md](SECURITY.md)를 먼저 읽어 주세요.

## 질문, 제안, 결함 보고

코드를 작성하기 전에 다음 경로로 문제를 먼저 정리합니다.

1. 사용법, 설계 방향, 아이디어 탐색은
   [GitHub Discussions](https://github.com/tjwnsdhfz/datumguard/discussions)에 올립니다.
2. 재현 가능한 결함은 `Bug report`, 새로운 fixture나 비교 corpus는 `Benchmark request`,
   제품 변경 제안은 `Feature request` issue form을 사용합니다.
3. 작은 오탈자 외에는 관련 issue 또는 Discussion 링크를 PR에 포함합니다.
4. public API, schema, error code, verification semantics를 바꾸는 작업은 구현 전에
   compatibility와 failure behavior를 issue에서 합의합니다.

보안 취약점은 공개 issue로 제출하지 말고
[private security advisory](https://github.com/tjwnsdhfz/datumguard/security/advisories/new)를
사용합니다.

## 기밀 CAD와 개인정보

공개 issue, Discussion, PR, CI log에 다음 정보를 올리지 마세요.

- 회사, 고객 또는 학교가 소유한 비공개 CAD/BIM 파일과 screenshot
- contract 원문, 자연어 intent/notes, filename, 로컬 경로, base64 bundle
- 도면 번호, 프로젝트 위치, 시설 배치, 장비 tag 등 식별 가능한 engineering metadata
- token, cookie, API key 또는 개인 식별 정보

fixture는 직접 만든 최소 재현 예제이거나 재배포가 명시적으로 허용된 자료만 사용합니다.
외부 자료에는 source URL, license, tool/version, 원본 hash와 변환 과정을 기록합니다.
기밀 파일로만 재현되는 문제는 파일을 업로드하지 말고 비식별화한 치수·entity 종류·error code와
최소 contract를 새로 작성해 주세요.

## 개발 환경

CI와 같은 기준은 Python 3.12, `uv==0.8.22`, Node.js 22입니다.

```bash
git clone https://github.com/tjwnsdhfz/datumguard.git
cd datumguard
python -m pip install uv==0.8.22
uv sync --frozen --extra dev

cd web
npm ci
cd ..
```

로컬 API와 web app은 각각 실행합니다.

```bash
uv run --frozen datumguard-api
```

```bash
cd web
npm run dev
```

Docker로 두 서비스를 함께 실행할 수도 있습니다.

```bash
docker compose up --build
```

## 변경 원칙

1. 하나의 branch와 PR은 하나의 명확한 문제를 해결합니다.
2. public type, API, schema, error code를 변경하면 문서와 test를 같은 PR에서 갱신합니다.
3. 새로운 engineering domain은 최소 정상 fixture와 의도된 failure fixture를 함께 추가합니다.
4. geometry writer와 independent verifier를 같은 측정 함수로 우회 연결하지 않습니다.
5. hash와 artifact는 deterministic해야 하며, 재실행 결과 차이가 있으면 근거를 남깁니다.
6. unsupported 또는 ambiguous input을 임의 추정하지 않고 `needs_confirmation`, `infeasible`
   또는 해당 fail-closed status로 반환합니다.
7. shell, RhinoScript, C# 등의 임의 실행 경로를 official design path에 추가하지 않습니다.

## 필수 검사

Backend 변경은 repository root에서 CI와 동일하게 검사합니다.

```bash
uv run --frozen ruff format --check src tests tools
uv run --frozen ruff check src tests tools
uv run --frozen mypy src/datumguard
uv run --frozen pytest
```

Web 변경은 `web/`에서 검사합니다.

```bash
cd web
npm run typecheck
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e -- --project=chromium
```

Playwright 설정은 API와 Next.js 개발 서버를 함께 시작합니다. 전체 browser test는 실제 parser와
CAD worker를 사용하므로 일반 unit test보다 오래 걸릴 수 있습니다. 문서만 변경한 경우에도
`git diff --check`와 수정한 Markdown link를 확인하고, 원격 CI의 결과를 기다립니다.

## Pull request 체크리스트

PR template의 모든 항목을 실제 변경 범위에 맞게 작성해 주세요.

- 문제와 사용자 영향을 한 문단으로 설명합니다.
- 관련 issue/Discussion, 변경된 requirement/constraint/error ID를 연결합니다.
- 실행한 명령과 결과를 그대로 기록합니다.
- PASS/FAIL preset 또는 변조 artifact를 사용한 failure test를 포함합니다.
- deployment, environment, CORS, capability flag 영향과 rollback 방법을 적습니다.
- 새 dependency, telemetry, 외부 API 또는 유료 서비스가 있으면 데이터·비용·장애 경계를
  명시하고 사전 승인을 받습니다.
- CAD payload, secret, 내부 경로가 diff, screenshot, log에 포함되지 않았는지 확인합니다.

검사를 실행하지 못했다면 이유와 남은 위험을 숨기지 말고 PR에 적습니다. test 수만 늘리는 것보다
어떤 engineering failure를 방지하는지 설명하는 evidence를 선호합니다.

## 문서와 언어

사용자 설명은 한국어를 기본으로 하되 API, type, error code, filename과 code identifier는 영어로
유지합니다. 번역에서 `verification`, `screening`, `certification`을 같은 의미로 섞지 않습니다.
특히 구조 관련 화면과 문서에는 `preliminary screening`과 `not structural certification` 경계를
항상 표시합니다.

기여를 제출하면 해당 변경을 repository의 [MIT License](LICENSE) 아래 배포하는 데 동의하는
것으로 간주합니다.

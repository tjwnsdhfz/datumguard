# DatumGuard Architecture Demo Guide

이 문서는 공개 demo의 route, DOM selector, deterministic capture와 CI 계약을 고정한다. Architecture 화면은 preset을 직접 조작하고 실제 backend 검증을 실행하는 기본 진입점이고, 상세 2D plate 설계기는 별도 route로 유지한다.

## Route 계약

| Route | 역할 | Backend 필요 여부 |
|---|---|---:|
| `/` | Architecture default. Preset load, drag/snap, 실제 독립 검증, timeline/summary/download | 예 |
| `/plate` | 기존 form, canonical SVG preview, generate/re-measure, verification table, bundle download | 검증 실행 시 필요 |
| `/api/v1/health` | Backend health | 예 |
| `/api/v1/architecture/designs/run` | Architecture workbench의 실제 검증 | 예 |
| `/api/v1/designs/run?auto_repair=true` | Plate의 generate/verify 흐름 | 예 |

`/`은 합성 preset을 실제 API에 보내고 응답의 측정 evidence로만 `VERIFIED`를 표시한다. Client가 pass 상태나 hash를 만들지 않는다. Backend가 없으면 검증 버튼은 구조화된 연결 오류를 보여주며 timeline, summary와 download를 성공 상태로 가장하지 않는다.

## Architecture 화면의 필수 구조

Architecture 구현은 다음 selector를 안정된 공개 E2E 계약으로 제공한다.

| Selector | 의미 |
|---|---|
| `[data-testid="architecture-demo"]` | 기본 route의 최상위 `<main>` |
| `[data-testid="architecture-flow"]` | 전체 flow 시각화 |
| `[data-testid="architecture-preset-studio"]` | 실제 12×8m studio preset을 불러오는 control |
| `[data-testid="architecture-canvas"]` | drag/snap workbench |
| `[data-testid="architecture-draggable-column"]` | E2E에서 이동하는 400mm column |
| `[data-testid="architecture-snap-target-center"]` | column의 deterministic grid snap target |
| `[data-testid="architecture-run-verification"]` | 실제 backend 검증 실행 |
| `[data-testid="architecture-stage-contract"]` | 계약·datum·locked/free 단계 |
| `[data-testid="architecture-stage-writer"]` | canonical geometry와 DXF writer 단계 |
| `[data-testid="architecture-stage-reopen"]` | serialized DXF 독립 재열기 단계 |
| `[data-testid="architecture-stage-remeasure"]` | 저장된 geometry 재측정 단계 |
| `[data-testid="architecture-stage-gate"]` | 승인·export gate |
| `[data-testid="architecture-health"]` | 최대 45초 backend 준비 polling과 retry 상태 |
| `[data-testid="verification-timeline"]` | 요청 진행과 완료 stage |
| `[data-testid="verification-summary"]` | 실제 target/actual/deviation/violation 요약 |
| `[data-testid="architecture-verified-badge"]` | 합성 sample의 `VERIFIED` 상태 |
| `[data-testid="architecture-contract-hash"]` | sample contract hash |
| `[data-testid="architecture-artifact-hash"]` | sample DXF artifact hash |
| `[data-testid="architecture-download"]` | 승인 bundle download |
| `a[href="/plate"]` | `플레이트 데모 열기` CTA |
| `[data-testid="plate-designer"]` | `/plate`의 기존 설계기 최상위 `<main>` |

검증 전 최상위 architecture node는 `data-verification-status="idle"`, 실행 중에는 `running`, 실제 응답이 통과한 뒤에만 `passed`를 가진다. Snap 완료 후 draggable에는 `data-snap-state="snapped"`가 설정된다. 각 stage는 색상만으로 구분하지 않고 heading과 설명 텍스트를 제공한다. `/plate`에는 Architecture로 돌아가는 링크가 있어야 한다.

## 검증된 demo fixture 표시 규칙

- Contract와 artifact hash는 backend 응답의 서로 다른 64자리 lowercase SHA-256 값을 사용한다.
- `writer`와 `verifier`가 서로 다른 경로임을 텍스트로 명시한다.
- `0.001 mm`, `locked changes: 0`, `required violations: 0`을 표시한다.
- PDF를 `DO NOT SCALE`로 표시하고 DXF만 제작 기준임을 명시한다.
- `VERIFIED`는 실제 API가 검증한 합성 demo fixture의 결과이며 구조·안전·법규 인증이 아님을 바로 옆에서 설명한다.
- Architecture page shell은 account, DB 또는 Rhino 없이 렌더링되지만 검증에는 DatumGuard backend가 필요하다.

## Playwright 실행

CI는 lockfile에 고정된 `@playwright/test@1.61.1`과 Chromium으로 test를 실행한다.

```bash
python -m pip install -e .
cd web
npm ci
npx playwright install chromium
npm run test:e2e
```

Playwright config는 `datumguard.api:app`을 `127.0.0.1:8000`에서, Next.js를 `127.0.0.1:3000`에서 함께 시작한다. 이미 실행 중인 두 서버는 로컬에서 재사용한다. 실패 시 `web/playwright-report/`와 `web/test-results/`가 GitHub Actions artifact로 올라간다. Trace, failure screenshot과 video는 실패한 test에만 보존한다.

## Deterministic capture

최종 README image의 고정 target은 다음과 같다.

```text
docs/assets/demo/architecture-verified.png
```

Architecture 구현이 selector 계약을 만족하고 로컬 production build가 실행 중일 때만 capture한다.

```bash
python -m uvicorn datumguard.api:app --host 127.0.0.1 --port 8000
# 다른 터미널
cd web
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
# 다른 터미널
node scripts/capture-architecture-demo.mjs
```

Capture script는 Chromium, `1440×960`, light color scheme, `ko-KR`, reduced motion을 사용하고 저장소에 묶인 local font loading을 기다린다. Script는 실제 backend 검증을 실행해 `passed`가 된 뒤 editor·평면·5단계 timeline·download CTA를 한 viewport에 capture한다. Animation과 caret은 제거한다.

## Web package 계약

웹 package 소유자가 충돌 없이 반영할 항목은 아래와 같다.

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "demo:capture": "node scripts/capture-architecture-demo.mjs"
  },
  "devDependencies": {
    "@playwright/test": "1.61.1"
  }
}
```

위 항목과 lockfile은 저장소에 포함한다. CI와 로컬 capture가 같은 version을 사용한다.

## 구현 연결점

Plate UI는 `/plate`, architecture page는 `/`에 연결한다. 구현은 다음을 지킨다.

1. 기존 plate form/API 동작과 IndexedDB draft key를 유지한다.
2. `/plate` 최상위 `<main>`에 `data-testid="plate-designer"`를 추가한다.
3. Architecture page에 위 selector와 실제 `POST /api/v1/architecture/designs/run` adapter를 추가한다.
4. Drag 종료 시 column을 deterministic grid target에 snap하고 계약 좌표를 갱신한다.
5. API 진행 상태를 timeline에, 측정값·hash·violation을 summary에 표시한다.
6. `passed`와 bundle이 함께 있을 때만 download를 활성화한다.
7. `/`과 `/plate` 사이의 keyboard-accessible link를 제공한다.
8. Architecture capture를 실행하기 전에 backend 포함 `npx playwright test`가 통과해야 한다.

## Hosted demo 확인

1. `$WEB_ORIGIN/`이 Architecture shell을 반환하고 preset load/drag/snap이 동작하는지 확인한다.
2. `$WEB_ORIGIN/plate`에서 canonical preview가 표시되는지 확인한다.
3. Backend `$API_ORIGIN/api/v1/health`가 `status: ok`인지 확인한다.
4. Frontend build의 `NEXT_PUBLIC_DATUMGUARD_API_URL=$API_ORIGIN`이 맞는지 확인한다.
5. `/`의 실제 architecture 검증에서 request가 `/api/v1/architecture/designs/run`으로 전송되는지 확인한다.
6. Timeline 완료 뒤 target, actual, deviation, tolerance와 hashes가 표시되는지 확인한다.
7. 승인되지 않은 결과에서 bundle download가 비활성인지 확인한다.

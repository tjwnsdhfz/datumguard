# DatumGuard Deployment Guide

이 문서는 Vercel web과 Render backend를 연결하는 설정 계약이다. 기준 공개 배포의 `$WEB_ORIGIN`은 `https://datumguard-tjwnsdhfz.vercel.app`, `$API_ORIGIN`은 `https://datumguard-api.onrender.com`이다. 새 환경을 만들 때는 아래 변수를 새 HTTPS origin으로 치환한다.

## 현재 공개 배포

| 구성요소 | 공개 URL | 2026-07-11 상태 |
|---|---|---|
| Next.js web | `https://datumguard-tjwnsdhfz.vercel.app` | Vercel Production `Ready` |
| FastAPI backend | `https://datumguard-api.onrender.com` | Render Free health `200 ok` |
| OpenAPI | `https://datumguard-api.onrender.com/docs` | 공개 접근 가능 |

Vercel에는 `NEXT_PUBLIC_DATUMGUARD_API_URL=https://datumguard-api.onrender.com`과 `NEXT_PUBLIC_GITHUB_URL=https://github.com/tjwnsdhfz/datumguard`를 Production/Preview에 설정했다. Vercel for GitHub는 `tjwnsdhfz/datumguard`, production branch `main`, Root Directory `web`, Node.js `22.x`로 연결되어 있다. Render는 production exact origin과 프로젝트 전용 Preview regex만 허용한다.

## 1. 배포 토폴로지

| 구성요소 | 기준 manifest | 책임 |
|---|---|---|
| Next.js web | `web/vercel.json`, `web/Dockerfile` | `/`, `/piping`, `/plate`, `/solid`, `/intake` UI와 API 호출 |
| FastAPI backend | `render.yaml`, 루트 `Dockerfile` | contract 기반 DXF/STEP 검증과 외부 DXF·STEP·IFC 감사 |
| CI | `.github/workflows/ci.yml` | backend, web, Playwright, backend/web Docker image build gate |
| Deployment smoke | `.github/workflows/deployment-smoke.yml` | Vercel deployment status 이후 web routes, API와 CORS 검사 |

Web과 API는 별도 origin이다. API는 stateless이며 계정, DB, 장기 artifact 저장을 요구하지 않는다.

## 2. Render backend

1. 저장소 루트의 `render.yaml`을 Blueprint로 사용한다.
2. 서비스는 `plan: free`로 생성하고 루트 `Dockerfile`을 build하며 queue capacity를 포함한 `/api/v1/ready`를 health check로 사용한다.
3. Render가 제공하는 `PORT`를 애플리케이션이 읽으므로 고정 public port를 manifest에 넣지 않는다.
4. `DATUMGUARD_CORS_ORIGINS`를 실제 production web origin으로 설정한다.
5. Preview가 필요하면 `DATUMGUARD_CORS_ORIGIN_REGEX`를 해당 Vercel project prefix로 제한한다.

현재 Blueprint는 Docker 서비스에 `runtime: docker`, `plan: free`, `dockerfilePath`, `dockerContext`, `healthCheckPath`, `autoDeployTrigger: checksPass`를 명시한다. 무료 instance는 유휴 상태에서 중지될 수 있으므로 공개 포트폴리오 시현용으로만 사용한다. 마지막 설정은 연결된 CI check가 통과한 commit만 자동 배포 대상으로 삼는다.

Blueprint는 optional Solid/Artifact Lab 기능, 48MB request·20MB artifact·40MB compare 합계 제한과 anonymous quota를 명시한다. Free instance에서는 OOM 위험을 줄이기 위해 heavy concurrency를 `1`, bounded waiter를 `4`로 제한한다. API key가 필요하면 dashboard secret `DATUMGUARD_API_KEYS`를 추가하며 Git이나 `NEXT_PUBLIC_*`에 값을 기록하지 않는다.

### CORS 값

`DATUMGUARD_CORS_ORIGINS`는 쉼표로 구분한 exact origin 목록이다. scheme과 host, non-default port만 포함하고 path와 마지막 slash는 넣지 않는다.

```text
https://datumguard-tjwnsdhfz.vercel.app,https://example-preview.invalid
```

첫 값은 현재 production origin이고 두 번째 값은 preview 형식 예시다. 기준 Render Blueprint는 아래 project-scoped regex도 설정한다.

```text
^https://datumguard-tjwnsdhfz-[a-z0-9-]+\.vercel\.app$
```

API는 localhost 두 origin을 개발 기본값으로 추가하지만 hosted origin은 자동 추정하지 않는다. regex는 DatumGuard project prefix로 시작하는 Vercel Preview만 허용하며 unrelated `vercel.app` origin이나 wildcard credential CORS로 완화하지 않는다.

### Cold start

Scale-to-zero 또는 유휴 sleep을 사용하는 Render plan에서는 첫 health/run 요청이 평상시보다 늦을 수 있다. 이는 검증 실패와 구분해야 한다.

- Web은 모든 workspace 요청 중 loading 상태를 유지하고 timeout/네트워크 오류를 명시적으로 보여준다.
- 운영 smoke check는 먼저 `$API_ORIGIN/api/v1/health`를 확인한 뒤 분야별 run을 호출한다.
- 일정한 first-request latency가 제품 요구사항이면 keep-alive 우회 대신 sleep하지 않는 서비스 plan을 선택한다.
- cold-start 시간은 plan과 시점에 따라 달라지므로 이 저장소는 고정 SLA를 주장하지 않는다.

## 3. Vercel web

1. Vercel Project의 Root Directory를 `web/`으로 설정한다.
2. `web/vercel.json`의 Next.js preset, `npm ci`, `npm run build`를 사용한다.
3. Production과 필요한 Preview environment에 아래 변수를 설정한다.

| 변수 | 필수 | 값 |
|---|---:|---|
| `NEXT_PUBLIC_DATUMGUARD_API_URL` | 예 | `$API_ORIGIN`; 마지막 slash 없이 설정 |
| `NEXT_PUBLIC_GITHUB_URL` | 공개 CTA 사용 시 | 실제 공개 저장소 URL |

`NEXT_PUBLIC_*` 값은 client build에 포함된다. API origin을 변경하면 environment variable만 바꾸고 끝내지 말고 web을 다시 build/deploy한다. Backend secret은 `NEXT_PUBLIC_*` 변수에 넣지 않는다.

공개 repository는 `https://github.com/tjwnsdhfz/datumguard`로 확정되었으며 Vercel project에 직접 연결되어 있다. PR push는 Preview, `main` push는 Production deployment를 만든다. Vercel button은 새 복제용으로 `root-directory=web`과 required env `NEXT_PUBLIC_DATUMGUARD_API_URL`, `NEXT_PUBLIC_GITHUB_URL`을 전달한다. Render는 repository root의 기존 Blueprint를 연결한다. 자세한 GitHub event 흐름은 [GitHub Deployment Guide](github-deployment.md)를 따른다.

## 4. 배포 순서

1. GitHub Actions의 `backend`와 `web` job을 통과시킨다.
2. `containers` job에서 backend와 web 두 Dockerfile이 모두 build되는지 확인한다.
3. Render backend를 배포하고 health endpoint를 확인한다.
4. Render의 `DATUMGUARD_CORS_ORIGINS=$WEB_ORIGIN`을 설정한다.
5. Vercel의 `NEXT_PUBLIC_DATUMGUARD_API_URL=$API_ORIGIN`을 설정하고 Git repository의 Root Directory를 `web`으로 연결한다.
6. PR Preview 또는 Production `deployment_status` 이후 `deployment-smoke`로 실제 DOM sentinel, API version/capability, CORS와 synthetic canary를 검사한다.

Production에서 Vercel과 Render는 독립적으로 완료될 수 있다. 새 web이 먼저 Ready가 되어도 smoke는 strict API version/capability가 수렴할 때까지 제한된 시간 동안 재시도한다. Backend 변경은 기존 web의 base architecture/piping/plate contract를 깨지 않는 backward-compatible release로 배포한다. Preview는 shared production API가 v0.1이면 base canary를 실행하고 solid canary를 명시적으로 보류하지만, 이 상태는 Production 승인으로 사용하지 않는다.

| Mode | Web | Run endpoint |
|---|---|---|
| Architecture | `$WEB_ORIGIN/` | `$API_ORIGIN/api/v1/architecture/designs/run` |
| Piping | `$WEB_ORIGIN/piping` | `$API_ORIGIN/api/v1/piping/designs/run` |
| Plate | `$WEB_ORIGIN/plate` | `$API_ORIGIN/api/v1/designs/run` |
| 3D Solid | `$WEB_ORIGIN/solid` | `$API_ORIGIN/api/v1/solid/designs/run` |
| Artifact Lab | `$WEB_ORIGIN/intake` | `$API_ORIGIN/api/v1/artifacts/audit` |

## 5. Smoke check

```bash
curl --fail --silent "$API_ORIGIN/api/v1/health"
curl --fail --silent "$API_ORIGIN/api/v1/domains"
```

Vercel generated deployment URL은 Vercel Authentication으로 보호될 수 있다. GitHub repository secret `VERCEL_AUTOMATION_BYPASS_SECRET`에 project의 automation bypass 값을 등록한다. workflow는 이 값을 header로만 보내고, login page title을 거부하며 route별 `data-testid` sentinel을 요구한다. secret이 없거나 잘못되면 status `200`인 login page도 smoke 실패다. [Vercel automation bypass 문서](https://vercel.com/docs/deployment-protection/methods-to-bypass-deployment-protection/protection-bypass-automation)를 따른다.

Smoke checkout은 deployment SHA를 사용한다. Production은 해당 `pyproject.toml` version과 web route가 요구하는 API capability를 strict하게 확인하고, Preview는 base capability를 backward-compatible하게 확인한다. Architecture canary는 `architecture_four_room.json`, solid capability가 광고되면 solid canary는 `solid_mounting_plate.json`을 사용한다. 두 canary 모두 `passed`, hash, official bundle과 핵심 geometry sentinel을 검사하며 response payload를 log에 출력하지 않는다.

브라우저에서는 `/`, `/piping`, `/plate`, `/solid`, `/intake`가 각각 유지되는지, 실패 preset에서 ZIP이 비활성인지, `passed` 응답과 `bundle_base64`가 함께 있을 때만 ZIP이 활성인지 확인한다. CORS 오류가 나면 browser console의 요청 origin과 `DATUMGUARD_CORS_ORIGINS`를 exact string으로 비교한다.

### 기준 배포 smoke 결과

| Mode | Web 결과 | API evidence |
|---|---|---|
| Architecture | `VERIFIED / PASS`, bundle 활성 | 96m², dimensions 4/4, room seeds 4, violations 0 |
| Piping | `VERIFIED`, bundle 활성 | route 12.0m, max support gap 2,000mm, min clearance 1,975mm |
| Plate | 모든 필수 검사 통과, bundle 활성 | 전체 표기 치수 deviation 0.000000mm |

추가로 `/api/v1/health`와 `/api/v1/domains`가 `200`, production origin의 CORS preflight가 `Access-Control-Allow-Origin: https://datumguard-tjwnsdhfz.vercel.app`을 반환하는지 확인했다.

## 6. CI가 보장하는 범위

- Backend: `uv==0.8.22`, frozen `uv.lock`, Ruff format/lint, mypy, pytest, pip-audit
- Web: npm lockfile install/audit, typecheck, ESLint, production build
- Browser: 실제 FastAPI와 Next.js를 함께 실행하는 5-workspace Playwright suite
- Containers: 루트 backend image와 `web/` image의 독립 build, CycloneDX SBOM과 fixed CRITICAL Trivy gate
- Security: PR dependency review, Python/JavaScript CodeQL, weekly Dependabot

CI 성공은 원격 Vercel/Render 배포 성공이나 구조·안전·법규 적합성을 의미하지 않는다. 원격 인증, DNS, plan 선택과 실제 공개 URL 확인은 운영 단계다.

## 7. 운영·비용 경계

운영 기준점과 장애 절차는 [`docs/operations/`](operations/README.md)를 따른다. 특히 Production 이전에 rollback baseline, SEV1 kill switch, SLO/SLI, payload redaction, local/staging load probe와 비용 guard를 검토한다.

현재 repository 변경은 Vercel/Render/Sentry/uptime 유료 업그레이드, 결제수단 등록, autoscaling 설정을 실행하지 않는다. Render service는 계속 `plan: free`이며 포트폴리오 시현용이다. 10k DAU 후보 비용은 [Cost Guard](operations/cost-guard.md)의 사전 제안일 뿐, owner 승인과 staging 부하 결과 없이 적용하지 않는다.

### Windows OneDrive local sync

이 workspace처럼 OneDrive 아래에서 uv hardlink가 `os error 396`으로 실패할 수 있다. local PowerShell에서는 copy mode를 명시한다. CI/Linux와 Docker의 frozen lock 계약은 그대로 유지한다.

```powershell
$env:UV_LINK_MODE = "copy"
uv sync --frozen --extra dev
```

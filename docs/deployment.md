# DatumGuard Deployment Guide

이 문서는 Vercel web과 Render backend를 연결하는 설정 계약이다. 저장소에는 배포 가능한 manifest만 포함하며, 실제 배포나 공개 URL 생성을 전제로 하지 않는다. 아래의 `$WEB_ORIGIN`과 `$API_ORIGIN`은 배포 후 운영자가 실제 HTTPS origin으로 치환한다.

## 1. 배포 토폴로지

| 구성요소 | 기준 manifest | 책임 |
|---|---|---|
| Next.js web | `web/vercel.json`, `web/Dockerfile` | `/`, `/piping`, `/plate` UI와 API 호출 |
| FastAPI backend | `render.yaml`, 루트 `Dockerfile` | 분야별 contract 검증, DXF 생성·독립 재측정, 승인 bundle |
| CI | `.github/workflows/ci.yml` | backend, web, Playwright, backend/web Docker image build gate |

Web과 API는 별도 origin이다. API는 stateless이며 계정, DB, 장기 artifact 저장을 요구하지 않는다.

## 2. Render backend

1. 저장소 루트의 `render.yaml`을 Blueprint로 사용한다.
2. 서비스는 루트 `Dockerfile`을 build하고 `/api/v1/health`를 health check로 사용한다.
3. Render가 제공하는 `PORT`를 애플리케이션이 읽으므로 고정 public port를 manifest에 넣지 않는다.
4. `DATUMGUARD_CORS_ORIGINS`를 실제 web origin으로 설정한다.

현재 Blueprint는 Docker 서비스에 `runtime: docker`, `dockerfilePath`, `dockerContext`, `healthCheckPath`, `autoDeployTrigger: checksPass`를 명시한다. 마지막 설정은 연결된 CI check가 통과한 commit만 자동 배포 대상으로 삼는다.

### CORS 값

`DATUMGUARD_CORS_ORIGINS`는 쉼표로 구분한 exact origin 목록이다. scheme과 host, non-default port만 포함하고 path와 마지막 slash는 넣지 않는다.

```text
https://example-web.invalid,https://example-preview.invalid
```

위 값은 형식 예시일 뿐 배포 URL이 아니다. API는 localhost 두 origin을 개발 기본값으로 추가하지만 hosted origin은 자동 추정하지 않는다. Vercel preview URL을 사용하려면 검증할 preview origin을 명시적으로 추가한다. wildcard credential CORS로 완화하지 않는다.

### Cold start

Scale-to-zero 또는 유휴 sleep을 사용하는 Render plan에서는 첫 health/run 요청이 평상시보다 늦을 수 있다. 이는 검증 실패와 구분해야 한다.

- Web은 architecture, piping, plate 요청 중 loading 상태를 유지하고 timeout/네트워크 오류를 명시적으로 보여준다.
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

공개 repository URL이 확정되기 전에는 README에 동작하지 않는 Deploy button을 넣지 않는다. URL이 생긴 뒤 Vercel Deploy button은 repository URL과 함께 `root-directory=web`, required env `NEXT_PUBLIC_DATUMGUARD_API_URL`을 전달해야 한다. Render는 repository root의 기존 Blueprint를 연결한다. 두 경우 모두 실제 배포 URL을 smoke-test하기 전에는 공개 demo가 배포되었다고 표시하지 않는다.

## 4. 배포 순서

1. GitHub Actions의 `backend`와 `web` job을 통과시킨다.
2. `containers` job에서 backend와 web 두 Dockerfile이 모두 build되는지 확인한다.
3. Render backend를 배포하고 health endpoint를 확인한다.
4. Render의 `DATUMGUARD_CORS_ORIGINS=$WEB_ORIGIN`을 설정한다.
5. Vercel의 `NEXT_PUBLIC_DATUMGUARD_API_URL=$API_ORIGIN`을 설정하고 web을 배포한다.
6. 세 route와 세 run endpoint를 smoke-test한다.

| Mode | Web | Run endpoint |
|---|---|---|
| Architecture | `$WEB_ORIGIN/` | `$API_ORIGIN/api/v1/architecture/designs/run` |
| Piping | `$WEB_ORIGIN/piping` | `$API_ORIGIN/api/v1/piping/designs/run` |
| Plate | `$WEB_ORIGIN/plate` | `$API_ORIGIN/api/v1/designs/run` |

## 5. Smoke check

```bash
curl --fail --silent "$API_ORIGIN/api/v1/health"
curl --fail --silent "$API_ORIGIN/api/v1/domains"
```

브라우저에서는 `/`, `/piping`, `/plate`가 각각 유지되는지, 실패 preset에서 ZIP이 비활성인지, `passed` 응답과 `bundle_base64`가 함께 있을 때만 ZIP이 활성인지 확인한다. CORS 오류가 나면 browser console의 요청 origin과 `DATUMGUARD_CORS_ORIGINS`를 exact string으로 비교한다.

## 6. CI가 보장하는 범위

- Backend: Ruff format/lint, mypy, pytest
- Web: npm lockfile install, typecheck, ESLint, production build
- Browser: 실제 FastAPI와 Next.js를 함께 실행하는 Architecture/Piping/Plate Playwright suite
- Containers: 루트 backend image와 `web/` image의 독립 build

CI 성공은 원격 Vercel/Render 배포 성공이나 구조·안전·법규 적합성을 의미하지 않는다. 원격 인증, DNS, plan 선택과 실제 공개 URL 확인은 운영 단계다.

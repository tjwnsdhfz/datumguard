# GitHub Deployment

DatumGuard의 기준 배포는 Vercel for GitHub와 Render Blueprint를 사용한다. 별도 `VERCEL_TOKEN`을 GitHub Actions에 저장하지 않고, 저장소 범위를 `tjwnsdhfz/datumguard`로 제한한 Vercel Git integration이 Preview와 Production deployment를 만든다.

## 연결 계약

| 항목 | 값 |
|---|---|
| GitHub repository | `tjwnsdhfz/datumguard` |
| Production branch | `main` |
| Vercel project | `tjwnsdhfzs-projects/datumguard-tjwnsdhfz` |
| Vercel Root Directory | `web` |
| Vercel Node.js | `22.x` |
| Web production origin | `https://datumguard-tjwnsdhfz.vercel.app` |
| Render service | `datumguard-api` |
| API production origin | `https://datumguard-api.onrender.com` |

`web/.vercel/`과 `web/.env.local`은 로컬 project link와 OIDC 정보를 포함할 수 있으므로 Git에 넣지 않는다. 공개 client 설정 예시는 `web/.env.example`만 추적한다.

## 배포 흐름

1. feature branch를 GitHub에 push한다.
2. GitHub `ci`가 backend, web, Playwright, container build를 검사한다.
3. Vercel Git integration이 `web/`만 읽어 Preview deployment를 만든다.
4. Vercel이 성공한 `deployment_status`를 GitHub에 기록한다.
5. 기본 브랜치의 `deployment-smoke.yml`이 Vercel URL의 `/`, `/piping`, `/plate`, `/solid`, `/intake`, Render version/domain registry, architecture와 활성화된 optional canary, CORS를 검사한다.
6. PR을 `main`에 merge하면 Vercel Production과 Render `checksPass` backend deployment가 실행된다.

Vercel preview origin은 매번 달라진다. Backend는 production origin을 `DATUMGUARD_CORS_ORIGINS` exact list로 허용하고, DatumGuard Vercel preview만 `DATUMGUARD_CORS_ORIGIN_REGEX`로 허용한다. unrelated `*.vercel.app` origin은 허용하지 않는다.

## Vercel 환경변수

Production과 Preview에 모두 설정한다.

```text
NEXT_PUBLIC_DATUMGUARD_API_URL=https://datumguard-api.onrender.com
NEXT_PUBLIC_GITHUB_URL=https://github.com/tjwnsdhfz/datumguard
```

두 값은 browser bundle에 포함되는 공개 설정이다. credential, API token 또는 OIDC token을 `NEXT_PUBLIC_*`에 넣지 않는다.

## 수동 smoke 실행

GitHub Actions에서 `deployment-smoke`를 선택하고 `Run workflow`를 실행한다. 기본 URL은 production이며 특정 Vercel Preview origin도 입력할 수 있다. 허용 대상은 HTTPS `vercel.app` origin으로 제한된다.

로컬에서는 다음 최소 검사를 실행한다.

```bash
curl --fail https://datumguard-api.onrender.com/api/v1/health
curl --fail https://datumguard-tjwnsdhfz.vercel.app/
curl --fail https://datumguard-tjwnsdhfz.vercel.app/piping
curl --fail https://datumguard-tjwnsdhfz.vercel.app/plate
curl --fail https://datumguard-tjwnsdhfz.vercel.app/solid
curl --fail https://datumguard-tjwnsdhfz.vercel.app/intake
```

## 새 Vercel 프로젝트로 복제

README의 `Deploy with Vercel` 버튼을 사용한다. Import 화면에서 Root Directory가 `web`인지 확인하고 위 두 공개 환경변수를 입력한다. Backend는 Render button으로 별도 생성하고 새 web origin을 exact CORS list 또는 프로젝트 전용 regex로 제한한다.

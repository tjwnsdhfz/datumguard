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
5. 기본 브랜치의 `deployment-smoke.yml`이 Vercel URL의 `/`, `/piping`, `/frame`, `/plate`,
   `/solid`, `/intake`, Render version/domain registry, architecture/FrameGuard와 활성화된 optional
   canary, CORS를 검사한다.
6. PR을 `main`에 merge하면 Vercel Production과 Render `commit` backend deployment가 실행된다.

Vercel preview origin은 매번 달라진다. Backend는 production origin을 `DATUMGUARD_CORS_ORIGINS` exact list로 허용하고, DatumGuard Vercel preview만 `DATUMGUARD_CORS_ORIGIN_REGEX`로 허용한다. unrelated `*.vercel.app` origin은 허용하지 않는다.

## 승격 전략

DatumGuard는 `main` 기반 continuous deployment와 milestone evidence release를 함께 사용한다.

| 용어 | 기준 | 용도 |
|---|---|---|
| PR Preview | feature branch SHA의 Vercel deployment | UI·DOM·기존 Production API와의 하위 호환성 확인 |
| Production revision | `main` SHA와 `/api/v1/health.release_sha`가 일치하는 Vercel·Render 배포 | 현재 실제 서비스 상태 |
| Evidence release | version tag와 GitHub Release에 CI·Security·SBOM·deployment ID·strict smoke를 고정 | 포트폴리오와 감사 가능한 불변 증거 |
| Rollback baseline | 이전 known-good tag/SHA와 두 platform deployment ID | 장애 복구 |

Evidence release tag와 현재 Production revision은 항상 같다고 가정하지 않는다. 문서·UI처럼 API 계약을
바꾸지 않는 변경은 같은 version에서 continuous deployment할 수 있다. 다음 변경은 version bump와 새
evidence release가 필요하다.

- `DesignContract`, 공개 API/MCP schema, error code 또는 capability 의미 변경
- PASS/FAIL, locked value, 공차, 독립 재측정 또는 official bundle gate 의미 변경
- 환경변수·CORS·kill switch 때문에 기존 web/API 조합의 호환 범위가 바뀌는 변경
- 공개 test 수치나 지원 분야 범위를 release evidence로 다시 주장하는 변경

PR Preview는 shared Production API를 사용하므로 Production 승격 증거가 아니다. Web은 직전 API와,
새 API는 직전 web과 base Architecture/Piping/Plate contract에서 하위 호환되어야 한다. Render 완료
후 strict smoke가 `release_sha`, version, capability, CORS와 synthetic canary를 같은 revision으로
확인한 뒤에만 배포를 완료로 기록한다. Strict smoke가 실패하면 배포 미완료로 기록하고 실제
`release_sha`를 비교한 뒤 이전 live revision 유지 또는 component rollback을 선택한다.

Render의 `autoDeployTrigger: commit`은 branch protection을 우회하지 않는다. 모든 변경은 merge 전에
required check를 통과하고, 관리자도 보호 규칙을 우회할 수 없다. Render의 `checksPass`는 사용하지
않는다. Render 배포 성공 후 실행되는 exact-revision `web-and-api` smoke가 다시 pre-deploy CI 입력이
되면 backend 배포와 검증 사이에 순환 의존이 생기기 때문이다.

## PR merge gate

모든 변경은 feature branch에서 시작해 squash merge한다. 기본 PR 본문은
[`pull_request_template.md`](../.github/pull_request_template.md)를 사용하며 다음 내용을 비워 두지 않는다.

- 변경 위험도와 web/API/contract/infra 영향
- 실행한 검증의 명령과 결과
- Vercel Preview URL과 `web-and-api` smoke
- 환경변수·CORS·capability 변경 여부
- component별 rollback 대상과 known-good tag/SHA/deployment ID
- merge 후 Production smoke를 확인할 owner

목표 required status checks는 다음과 같다.

```text
backend
web
containers
python-audit
dependency-review
codeql (python)
codeql (javascript-typescript)
Vercel
web-and-api
```

`strict` status check와 conversation resolution을 유지하고 force push와 branch deletion을 금지한다.
두 번째 독립 reviewer가 생기기 전에는 approval count와 CODEOWNERS를 강제하지 않는다. Solo owner가
자기 PR을 승인할 수 없어 release가 교착되기 때문이다. 대신 admin을 포함해 위 자동 gate를 우회하지
않고, merge commit과 rebase merge는 끄며 squash merge만 사용한다. 병합된 feature branch는 자동
삭제한다.

### GitHub 설정 변경과 원복

2026-07-12 적용 전 기준은 required check `backend`, `web`, `containers`, `strict: true`,
`enforce_admins: false`, approval `0`, conversation resolution 활성, merge 방식 3종 허용, 병합 branch
자동 삭제 비활성, update branch 비활성이다. 외부 GitHub 설정은 PR check 이름을 실제 확인한 뒤 다음 순서로
한 항목씩 적용하고, 각 단계 직후 API로 다시 읽어 검증한다.

1. required check에 Security, Vercel, compatibility smoke를 추가한다.
2. admin에도 branch protection을 적용한다.
3. squash merge만 허용하고 merged branch 자동 삭제와 update branch를 활성화한다.

잘못된 check 이름 때문에 병합이 막히면 해당 이름만 required check에서 제거한다. 전체 원복이 필요하면
required check를 위 세 개로 되돌리고 `enforce_admins`를 끈 뒤 merge commit·rebase merge를 다시 허용한다.
approval, conversation resolution, force push·branch deletion 정책은 이번 변경 대상이 아니므로 원복 중에도
변경하지 않는다. 설정 변경 전후 JSON은 PR evidence에 남긴다.

## 변경 유형별 승격·롤백

| 변경 유형 | 승격 조건 | 기본 rollback |
|---|---|---|
| 문서만 | 문서 링크·Markdown 검증, 일반 PR gate | squash commit revert; platform rollback 없음 |
| Web only | Preview DOM/접근성/E2E와 기존 API 호환 | Vercel만 직전 compatible deployment로 rollback |
| Backward-compatible API | 전체 CI, canary, 이전 web 호환, Render strict smoke | unsafe API면 Render를 먼저 rollback; web은 호환이 깨질 때만 rollback |
| Contract/capability | version bump, 새 evidence release, 양방향 호환 또는 명시적 변경 창 | matching tag의 Render → Vercel 순서로 full-stack rollback |
| Secret/CORS/infra | 값이 아닌 변수명·owner·검증 방법 기록, change window | dashboard 설정과 build를 함께 복구하고 새 smoke 실행 |

Wrong PASS 또는 unverified export 위험은 항상 SEV1이다. 이때 UI 가용성보다 API export 차단을 먼저
수행하고 [rollback baseline](operations/rollback-baseline.md)과
[incident runbook](operations/incident-runbook.md)을 따른다.

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
curl --fail https://datumguard-tjwnsdhfz.vercel.app/frame
curl --fail https://datumguard-tjwnsdhfz.vercel.app/plate
curl --fail https://datumguard-tjwnsdhfz.vercel.app/solid
curl --fail https://datumguard-tjwnsdhfz.vercel.app/intake
```

`/frame` 명령은 v0.3.0 Vercel/Render production에서 실행된다. 완료 evidence는 `/frame` DOM
sentinel, API `structural_frame` domain, deterministic solver canary, health `release_sha`와 CORS를
함께 검사한 [run 29195107475](https://github.com/tjwnsdhfz/datumguard/actions/runs/29195107475)에
고정한다. 해당 run의 checkout과 API release SHA는
`472df5fe431277244fc0fcda1ee9aa3b6284ddff`로 일치한다.

OpenSeesPy/PyG는 production dependency가 아니다. 필요할 때 GitHub Actions의 선택형
`frame-research` workflow를 수동 실행하며 base Docker image에는 Torch/OpenSeesPy를 넣지 않는다.

## 새 Vercel 프로젝트로 복제

README의 `Deploy with Vercel` 버튼을 사용한다. Import 화면에서 Root Directory가 `web`인지 확인하고 위 두 공개 환경변수를 입력한다. Backend는 Render button으로 별도 생성하고 새 web origin을 exact CORS list 또는 프로젝트 전용 regex로 제한한다.

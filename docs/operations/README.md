# DatumGuard Operations

이 디렉터리는 DatumGuard의 배포 검증, 장애 대응, 관측성, 데이터 수명과 비용 통제를 위한 운영 계약이다. 공개 환경은 제품 demo이며 10k DAU 용량 검증이나 운영 승인을 뜻하지 않는다.

## Evidence release, live revision, rollback snapshot

`evidence release`는 불변 검증 자료이고 `live production revision`은 현재 배포된 `main`이다.
두 SHA는 UI·문서의 continuous deployment 때문에 다를 수 있다. 아래 표는 2026-07-12에 검증한
v0.3.0 snapshot을 고정하고, 후속 배포의 현재 상태는 `/api/v1/health.release_sha`, GitHub Deployment
record와 최신 성공 `deployment-smoke`에서 다시 조회한다.

| 항목 | 고정 기준 |
|---|---|
| Validated v0.3.0 feature snapshot | [`472df5fe431277244fc0fcda1ee9aa3b6284ddff`](https://github.com/tjwnsdhfz/datumguard/commit/472df5fe431277244fc0fcda1ee9aa3b6284ddff) |
| Production deployments | Vercel `5413026696`; Render `5413009032` / `dep-d99pkfeq1p3s73d3gjj0` |
| Strict production smoke | [run `29195107475`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29195107475) |
| Rollback baseline | [`v0.2.1`](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.1); Vercel `5410294611`; Render `5410321107` |

현재 revision은 다음 경로로 확인한다. liveness와 admission readiness는 목적이 다르므로 둘 다 확인한다.

```bash
curl --fail https://datumguard-api.onrender.com/api/v1/health
curl --fail https://datumguard-api.onrender.com/api/v1/live
curl --fail https://datumguard-api.onrender.com/api/v1/ready
gh api 'repos/tjwnsdhfz/datumguard/deployments?sha=<release_sha>'
gh run list --repo tjwnsdhfz/datumguard --workflow deployment-smoke.yml --limit 5
```

Web-only 장애이고 API contract가 유지되면 Vercel만 v0.2.1 deployment로 복구할 수 있다.
Wrong PASS, unverified export 또는 API contract 불일치이면 Render를 먼저 복구하고 필요하면 web을 같은
v0.2.1 tag로 맞춘다. 아래 표는 현재 v0.3.0과 독립적으로 복구 가능한 v0.2.1 기준점이다.

| 항목 | 검증된 상태 |
|---|---|
| Release source | `v0.2.1` / `0e871c4a93872415f7151a99050b102f273986dd` |
| API | `0.2.1`; Architecture, Piping, Plate, Artifact Lab 활성 |
| Solid | local/CI 활성; Render Free hosted run 비활성, `503 DG_CAPABILITY_DISABLED` |
| FrameGuard/OpenBIM | v0.2.1 rollback에는 없음 |
| CI | 256 pytest, 24 Playwright, web/container/SBOM pass |
| Production smoke | exact release SHA, Architecture/Artifact canary, Solid fail-closed, CORS pass |
| Deployments | Vercel `5410294611`; Render `5410321107` |
| 100+50 benchmark | 계획됨, 미완료; 256 pytest/24 Playwright와 별도 평가 |

## 문서 지도

- [Historical v0.2.0 rollback record](rollback-baseline.md): 이전 고정 commit과 복구 절차; 현재 rollback 대상은 위 v0.2.1 deployment
- [GitHub deployment and promotion](../github-deployment.md): Preview, merge gate, Production revision, evidence release와 component rollback
- [Incident runbook](incident-runbook.md): SEV 분류, kill switch, 연락·상태 공지, 복구와 postmortem
- [SLO/SLI](slo-sli.md): 안전성과 가용성 목표, 측정 방법, error budget
- [Logging and redaction](logging-redaction.md): 구조화 로그 필드, 금지 데이터, 보존·알림 기준
- [Privacy and data lifecycle](privacy-data-lifecycle.md): contract/CAD/draft/bundle의 저장 위치와 삭제 책임
- [Cost guard](cost-guard.md): 10k DAU 가정, 플랫폼 한도, 예산 경보와 승인 경계
- [Load testing](load-testing.md): local/staging 전용 probe와 악성·최대 크기 단발 검사
- [Incidents](incidents/): 실제 배포 장애의 timeline, 영향, 완화와 재활성화 조건

## Release gate

- [x] v0.3.0 `backend`, `web`, `containers`가 [CI run `29194952632`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29194952632)에서 통과했다: 376 pytest, 35 Playwright, 두 container build·SBOM·fixed-critical scan.
- [x] [Security run `29194952607`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29194952607)에서 pip audit와 Python·JavaScript/TypeScript CodeQL이 통과했다.
- [x] [Frame research run `29194964854`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29194964854)에서 genuine OpenSeesPy parity와 PyG training/portable-inference smoke가 통과했다.
- [x] Vercel automation bypass를 GitHub Actions secret으로 등록하고 protected Preview DOM sentinel을 검증했다.
- [x] [Strict smoke `29195107475`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29195107475)가 API v0.3.0, exact `release_sha`, FrameGuard/Architecture/Artifact canary, Solid fail-closed와 CORS를 통과했다.
- [x] Production Vercel `5413026696`과 Render `5413009032`가 같은 `472df5fe...` revision에서 성공했다.
- [x] v0.2.1을 component rollback baseline으로 유지한다. FrameGuard는 rollback 시 제거되는 기능임을 incident 공지에 명시한다.
- [ ] Render Free가 아닌 용량 후보에서 1/2/5/10 동시성 probe와 STEP·20MB upload 단발 시험을 수행한다.
- [x] optional API key, bounded per-IP/route rate limit, CAD worker concurrency/queue와 timeout/429 계약을 구현했다.
- [x] payload를 제외한 request ID·route·status·duration·queue JSON 로그와 bounded in-process metrics를 구현했다.
- [ ] 외부 error tracker, uptime monitor, 담당자 알림과 장기 metric retention을 연결한다.
- [ ] [SEV1 rollback drill](incident-runbook.md)을 수행하고 시각·소요 시간·검증 결과를 incident log에 남긴다.
- [ ] 실제 월 예산과 50/75/90/100% 알림을 소유자가 승인한다.
- [ ] 100개 golden contract + 자연어 50개 benchmark를 실행하고 pass/fail report를 공개한다.

## 출시 후 개선

- [ ] p95/p99, worker RSS, queue depth, 429와 bundle byte 분포로 instance/worker 수를 재산정한다.
- [ ] API 결과 캐시는 contract hash 기반·private scope·짧은 TTL로만 검토한다.
- [ ] 사용자 계정이나 cloud history가 생길 때 DB PITR, object storage lifecycle, restore drill을 추가한다.
- [ ] 공개 status page, on-call escalation, 장기 log/metric retention은 실제 지원 인원에 맞춰 확장한다.

## 현재 불필요

- DB index, connection pool, DB backup: 현재 API는 DB가 없는 stateless 서비스다.
- 이메일 delivery retry/DLQ: 제품 이메일 발송 기능이 없다.
- 외부 업무 API circuit breaker: runtime에서 호출하는 업무 API가 없다. Vercel·Render 장애는 uptime/runbook으로 다룬다.

기능이 추가되면 “현재 불필요” 항목을 자동으로 유지하지 말고 같은 PR에서 운영 계약을 다시 분류한다.

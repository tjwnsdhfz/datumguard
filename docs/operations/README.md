# DatumGuard Operations

이 디렉터리는 DatumGuard의 배포 검증, 장애 대응, 관측성, 데이터 수명과 비용 통제를 위한 운영 계약이다. 공개 환경은 제품 demo이며 10k DAU 용량 검증이나 운영 승인을 뜻하지 않는다.

## 현재 release와 v0.2.0 rollback snapshot

현재 공개 release의 source SHA, 두 deployment, CI·Security와 Render-success exact-revision smoke는
[v0.2.1 release](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.1)에 고정한다. 아래 표는
독립적으로 복구 가능한 이전 v0.2.0 기준점이다.

| 항목 | 검증된 상태 |
|---|---|
| Release source | `v0.2.0` / `40dd132ae8ca3267a79283f65058d6c8bbcee44b` |
| API | `0.2.0`; Architecture, Piping, Plate, Artifact Lab 활성 |
| Solid | local/CI 활성; Render Free hosted run 비활성, `503 DG_CAPABILITY_DISABLED` |
| CI | [256 pytest, 24 Playwright, web/container/SBOM pass](https://github.com/tjwnsdhfz/datumguard/actions/runs/29181254550) |
| Production smoke | [6 public route, Architecture/Artifact canary, Solid fail-closed, CORS pass](https://github.com/tjwnsdhfz/datumguard/actions/runs/29181279413) |
| Deployments | Vercel `5410073153`; Render `5410097749` |
| 100+50 benchmark | 계획됨, 미완료; 256 pytest/24 Playwright와 별도 평가 |

## 문서 지도

- [Rollback baseline](rollback-baseline.md): 고정 commit, backup tag, GitHub deployment ID와 복구 순서
- [Incident runbook](incident-runbook.md): SEV 분류, kill switch, 연락·상태 공지, 복구와 postmortem
- [SLO/SLI](slo-sli.md): 안전성과 가용성 목표, 측정 방법, error budget
- [Logging and redaction](logging-redaction.md): 구조화 로그 필드, 금지 데이터, 보존·알림 기준
- [Privacy and data lifecycle](privacy-data-lifecycle.md): contract/CAD/draft/bundle의 저장 위치와 삭제 책임
- [Cost guard](cost-guard.md): 10k DAU 가정, 플랫폼 한도, 예산 경보와 승인 경계
- [Load testing](load-testing.md): local/staging 전용 probe와 악성·최대 크기 단발 검사
- [Incidents](incidents/): 실제 배포 장애의 timeline, 영향, 완화와 재활성화 조건

## Release gate

- [x] v0.2.1 release의 `backend`, `web`, `containers`와 security workflow가 통과했다.
- [x] Vercel automation bypass를 GitHub Actions secret으로 등록하고 protected Preview DOM sentinel을 검증했다.
- [x] Vercel compatibility smoke와 Render-success exact `release_sha` smoke가 version·capability, Architecture/Artifact canary, Solid fail-closed와 CORS를 통과했다.
- [x] CI와 Preview에서 `/case-study` 포함 6 public route를 확인했다.
- [x] v0.2.1 Production SHA·Vercel/Render deployment는 release notes에, 이전 v0.2.0은 [rollback baseline](rollback-baseline.md)에 고정했다.
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

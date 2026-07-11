# SLO and SLI

이 목표는 DatumGuard의 내부 운영 목표이며 Vercel/Render의 계약 SLA가 아니다. 측정이 연결되기 전에는 달성했다고 주장하지 않는다.

| SLI | Good event | 30일 SLO | Alert |
|---|---|---:|---|
| Safety correctness | independently reopened artifact가 모든 required check를 통과한 경우에만 `PASS`와 official bundle 발급 | wrong PASS `0` | 한 건 즉시 SEV1 |
| Web availability | production alias가 `2xx`이고 route별 `data-testid` sentinel 존재 | 99.9% | 2개 location에서 2회 연속 실패 |
| Base API availability | health `ok`, base 3 domain, architecture canary `passed` | 99.9% | 5분 창 성공률 <99% |
| v0.2 capability | health version과 domain registry가 같은 SHA의 kill-switch 계약과 일치, 활성화된 optional canary `passed` | 99.5% | Production 불일치 즉시 deploy 실패 |
| Architecture latency | warmed canary end-to-end duration | p95 ≤3s, p99 ≤5s | 15분간 p95 >3s |
| Solid latency | capability가 활성화된 환경의 small mounting plate end-to-end duration | provisional p95 ≤30s | 활성 환경에서 p95 >30s 또는 timeout; 비활성 환경은 domain 미광고·503 |
| Overload behavior | 허용량 초과 시 bounded queue/429, 5xx·OOM 없음 | overload 5xx <1% | 5xx 또는 restart 발생 |

## 측정 규칙

- uptime probe는 status code만 보지 않고 web DOM sentinel과 API JSON sentinel을 확인한다.
- Vercel protected deployment는 automation bypass를 사용한다. `Login – Vercel`은 good event가 아니다.
- Preview는 shared v0.1 API와 backward-compatible base canary를 허용하지만, Production은 checked-out `pyproject.toml` version과 capability를 strict하게 요구한다.
- planned maintenance는 사전 공지된 구간만 별도 표기하고 원시 수치에서 삭제하지 않는다.
- client abort, 429, 4xx validation, 5xx, timeout을 서로 다른 counter로 보존한다.

## Error budget

99.9% 월간 availability budget은 30일 기준 약 43분이다. budget 50% 소진 시 비운영 기능 release를 늦추고, 100% 소진 또는 wrong PASS 발생 시 reliability/safety 수정 외 release를 중지한다.

필수 dashboard: request rate, 2xx/4xx/429/5xx, p50/p95/p99, request/response bytes, worker duration, active CAD workers, queue depth, RSS/CPU, cold start, deployment SHA/version.

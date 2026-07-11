# Render Free Solid workspace incident

## 요약

- Incident: `DG-INC-2026-07-12-01`
- Severity: `SEV2`
- Owner: `@tjwnsdhfz`
- Affected route: `POST /api/v1/solid/designs/run`
- Affected release: `6a31fc1b2099a02bcd722dd128c2de82c2c5ce34`
- Detection: GitHub Actions Production smoke run `29163059124`
- Safety result: wrong `PASS`와 official export는 없었으며, 요청은 HTTP 502로 실패했다.

## Timeline

| 단계 | UTC | KST | 증거 |
|---|---|---|---|
| Production smoke 시작 | 2026-07-11 18:18:26 | 2026-07-12 03:18:26 | Actions run `29163059124` |
| Solid canary 502 감지 | 2026-07-11 18:19:06 | 2026-07-12 03:19:06 | curl이 `/api/v1/solid/designs/run`에서 HTTP 502 반환 |
| Kill switch 배포 완료 | 2026-07-11 18:23:56 | 2026-07-12 03:23:56 | Render deployment `5406155624` success |
| 복구 검증 | 2026-07-11 18:27 | 2026-07-12 03:27 | health 200/version `0.2.0`, domain registry에서 Solid 제거, Solid endpoint 503 |

## 영향

- 공개 Architecture, Plant Piping, Plate, Artifact Lab 경로에는 관찰된 기능 장애가 없었다.
- Solid workspace의 canary fixture 한 건이 502로 실패했다.
- 사용자 CAD나 개인정보는 전송하지 않았고, 저장된 서버 데이터도 없다.
- 검증 결과가 잘못 승인되거나 공식 bundle이 생성되지 않았다. 서비스는 가용성보다 정확성을 우선해 fail closed로 동작했다.

## 원인과 기여 조건

확인된 사실은 Render Free 인스턴스의 `512 MB RAM / 0.1 CPU` 용량에서 Solid canary가 502로 끝났고, 동일 release의 가벼운 Architecture canary는 통과했다는 점이다. STEP 파싱과 형상 검증은 이 인스턴스 등급에 비해 무거운 선택 기능이다.

직접적인 OOM 메시지는 보존된 로그에서 확인하지 못했으므로 OOM을 확정 원인으로 기록하지 않는다. 현재 root-cause 분류는 **Render Free 용량 경계 초과**이며, 메모리 고갈 또는 worker 재시작은 강한 의심 사항이다. 재활성화 전 격리된 staging에서 RSS, CPU, queue depth와 exit reason을 계측해 확정해야 한다.

기여 조건은 다음과 같다.

- 초기 Production smoke가 배포 manifest의 선택 기능 kill switch를 엄격히 비교하지 않았다.
- 웹은 capability 미지원 응답을 재시도 대기 구간이 끝날 때까지 표시할 수 있었다.
- 무료 인스턴스에서 Solid의 실제 최소 용량을 검증하기 전에 기능이 공개 capability로 광고됐다.

## 완화와 검증

1. Render 환경의 `DATUMGUARD_ENABLE_SOLID=false`를 적용하고 재배포했다.
2. `render.yaml`에도 같은 값을 고정해 dashboard와 저장소 설정의 drift를 제거했다.
3. domain registry에서 `solid_part`가 사라지고, endpoint가 명시적인 `503 DG_CAPABILITY_DISABLED`로 fail closed하는 것을 확인했다.
4. 웹 readiness는 capability unavailable을 재시도하지 않고 즉시 안내하도록 변경했다.
5. Production smoke는 `render.yaml`의 선택 기능 값을 읽어 API capability의 존재와 부재를 모두 검증하도록 변경했다.

## 재활성화 조건

다음 조건을 모두 충족하기 전에는 공개 Render 환경에서 Solid를 활성화하지 않는다.

- 유료 변경에 대한 저장소 소유자의 명시적 승인
- Render Standard 이상 또는 별도 worker 환경의 격리 staging
- 정상·최대 크기 STEP fixture의 1/2/5/10 동시성 시험
- worker RSS/CPU/queue/timeout/exit reason 관측
- 15분 soak 동안 5xx 0건, wrong `PASS` 0건, queue/timeout SLO 충족
- kill switch rollback과 Production smoke drill 성공

## Corrective actions

| 조치 | 상태 | 검증 |
|---|---|---|
| Render Free에서 Solid 기본 비활성화 | 완료 | deployment `5406155624`, domains/503 smoke |
| manifest와 capability strict comparison | 구현 | workflow syntax와 PR/Production smoke |
| capability unavailable UI fast-fail | 구현 | Playwright regression test |
| Solid 전용 최소 용량/RSS load test | 보류 | 유료 staging 승인 후 수행 |
| 외부 error tracker와 장기 metric retention | 보류 | 상용 출시 전 비용 승인 필요 |

## SLO와 데이터 검토

- 선택 workspace 1건의 가용성 실패로 SEV2를 선언했다.
- wrong `PASS`, 미검증 export, 데이터 유출은 0건이다.
- fixture 외 payload는 로그·문서에 포함하지 않았다.
- 계정·DB·서버 artifact 보관이 없으므로 데이터 복구 작업은 필요하지 않았다.

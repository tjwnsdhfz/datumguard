# Incident Runbook

## 심각도

| 등급 | 선언 조건 | 첫 행동 목표 |
|---|---|---|
| SEV1 | wrong `PASS`, 검증되지 않은 official export, CAD/contract 노출, 전체 export/API outage 15분 초과 | 5분 안에 export/API kill, 15분 안에 known-good rollback 결정 |
| SEV2 | 한 workspace 장애, p95 목표 3배 초과, 5xx/timeout 5% 초과, 지속적인 429 | 15분 안에 완화·rollback 판단 |
| SEV3 | 비핵심 UI/Preview/문서 문제, 우회 가능 | 다음 근무 주기 내 issue와 owner 지정 |

wrong PASS는 가용성 수치와 무관하게 항상 SEV1이다. 결과가 맞는지 불명확하면 fail closed로 간주하고 export를 중단한다.

## 역할과 연락

- Incident commander/primary responder: repository owner `@tjwnsdhfz`.
- 보안·사용자 CAD 관련 내용: GitHub private security advisory. 공개 issue나 채팅에 payload를 붙이지 않는다.
- 플랫폼 확인: [Vercel Status](https://www.vercel-status.com/), [Render Status](https://status.render.com/), 각 dashboard deploy/event log.
- 임시 공개 상태 채널: 민감 정보가 없는 GitHub issue에 `[status]` prefix로 시작·완화·복구 시각을 갱신한다. 상용 출시 전 독립 status page와 실제 연락 수단을 지정한다.

## SEV1 절차

1. **선언:** UTC/KST 시각, 최초 신고, 영향 route/version, incident commander를 기록한다.
2. **증거 보존:** request/correlation ID, deployment ID, SHA, status code, redacted log만 보존한다. contract, CAD bytes, base64 bundle은 복사하지 않는다.
3. **Kill switch:**
   - wrong PASS/export 위험: Render service suspend 또는 즉시 known-good backend rollback.
   - web이 위험한 export를 유도: Vercel production rollback.
   - CORS 변경만으로 direct API가 차단됐다고 판단하지 않는다.
4. **완화:** [rollback baseline](rollback-baseline.md)의 Render → Vercel 순서와 버전 계약을 따른다.
5. **검증:** health/domain, 실제 DOM sentinel, architecture canary, capability가 있으면 solid canary를 실행한다.
6. **공지:** 영향 범위, export 차단, 다음 업데이트 시각을 게시한다. 원인 추측은 확정 사실처럼 쓰지 않는다.
7. **복구 선언:** safety canary와 15분 관찰 구간이 정상이고 새 5xx/wrong PASS가 없을 때 종료한다.

## 목표

- 내부 RTO: SEV1 unsafe export 15분, 일반 API outage 30분.
- 현재 server RPO: 0(계정·DB·장기 artifact 저장 없음). 브라우저 IndexedDB draft와 사용자가 내려받은 bundle은 서버 복구 범위가 아니다.
- 플랫폼 계약 SLA가 아니라 내부 목표다.

## Postmortem template

```text
Incident / SEV / owner:
Start, detect, mitigate, recover (UTC and KST):
User and safety impact:
Affected releases, deployment IDs, routes:
Detection source and why earlier controls did/did not fire:
Root cause and contributing conditions:
Kill switch / rollback actions and evidence:
What went well / poorly / was lucky:
Corrective actions (owner, deadline, verification):
SLO/error-budget impact:
Payload/redaction review completed by:
```

Postmortem은 3영업일 안에 작성하고, safety invariant 회귀 test와 운영 gate가 추가되기 전 같은 release를 재배포하지 않는다.

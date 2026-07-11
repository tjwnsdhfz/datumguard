# Rollback Baseline — 2026-07-12

## 고정 기준점

| 항목 | 식별자 | 의미 |
|---|---|---|
| Production source | `main` / `2d1f08e6cfabe0a653500302cac1045ccb3b7a2f` | 현재 v0.1 production 기준 |
| v0.2 source | `agent/cad-artifact-assurance` / `eefad164c952d6c859327592eaedc1e2508d5e64` | CAD artifact/STEP feature 기준 |
| Backup tag | `ops-backup-20260712` | annotated tag, `eefad164c952d6c859327592eaedc1e2508d5e64`를 가리킴; origin 존재 확인 |
| Vercel Production deployment | GitHub deployment `5404705357` | SHA `2d1f08e`, environment `Production` |
| Render production deployment | GitHub deployment `5404701175` | SHA `2d1f08e`, environment `main - datumguard-api` |
| Vercel Preview deployment | GitHub deployment `5405362126` | SHA `eefad16`, environment `Preview` |

Preview `5405362126`은 rollback 대상으로 승격된 production이 아니다. v0.2 web이 v0.1 API를 공유하는 동안 solid/artifact capability가 없을 수 있으므로 Preview 성공만으로 production 승인을 만들지 않는다.

## 복구 우선순위

1. **Wrong PASS 또는 부적격 export가 의심되면 API를 먼저 차단한다.** 현재 코드에는 독립적인 export kill-switch flag가 없으므로 Render에서 서비스를 suspend하거나 마지막 known-good deploy로 즉시 rollback한다. CORS 제거는 direct API 호출을 막지 못하므로 kill switch가 아니다.
2. Render를 GitHub deployment `5404701175`가 가리키는 `2d1f08e` build로 rollback한다.
3. Vercel을 Production deployment `5404705357`로 Instant Rollback한다.
4. `/api/v1/health`가 `version: 0.1.0`, `/api/v1/domains`가 base 3개 domain을 반환하는지 확인한다.
5. production alias의 `/`, `/piping`, `/plate` DOM sentinel과 architecture canary를 확인한다.
6. 상태 공지에 영향 시간, export 중단 여부, 복구된 version/SHA를 기록한다.

## Roll forward

1. 원인을 수정한 새 PR에서 모든 CI/security check를 통과시킨다.
2. Preview는 automation bypass를 사용해 로그인 페이지가 아닌 실제 sentinel을 검사한다.
3. Backend가 새 version/capability를 먼저 광고하거나, 기존 API와 backward compatible한 상태로 준비한다.
4. Production smoke가 strict version/capability와 canary를 통과한 뒤에만 incident를 종료한다.

## 설정 복구 주의

- Render rollback은 대상 build의 설정 일부를 재사용하지만 dashboard의 현재 서비스 설정 전체를 되돌리는 것은 아니다.
- Vercel rollback은 이전 build에 포함된 `NEXT_PUBLIC_*` 값을 사용하므로 환경변수 변경 후에는 새 build가 필요하다.
- `DATUMGUARD_CORS_ORIGINS`는 `sync: false`이므로 값 자체는 Git에 없다. secret 값은 기록하지 말고 변수명, owner, 최종 검증 시각만 별도 비밀 관리대장에 보관한다.
- rollback 전후 GitHub deployment URL, health body, canary 결과와 담당자를 incident timeline에 남긴다.

참고: [Vercel Instant Rollback](https://vercel.com/docs/instant-rollback), [Render Rollbacks](https://render.com/docs/rollbacks).

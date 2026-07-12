# Rollback Baseline — v0.2.0 release

## 고정 기준점

| 항목 | 식별자 | 의미 |
|---|---|---|
| Known-good source | `v0.2.0` → `40dd132ae8ca3267a79283f65058d6c8bbcee44b` | annotated public release tag |
| Vercel deployment | GitHub deployment `5410073153` | 위 SHA의 Production web |
| Render deployment | GitHub deployment `5410097749` | 위 SHA의 Production API |
| Deployment smoke | [run `29181279413`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29181279413) | API v0.2.0, 6 public route, Architecture/Artifact canary, Solid fail-closed, CORS pass |
| CI | [run `29181254550`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29181254550) | 256 pytest, 24 Playwright, web/container/SBOM pass |
| Security | [run `29181254569`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29181254569) | dependency review, pip audit와 두 CodeQL language pass |
| Previous v0.2 fallback | `b2dd6e5ebd7f21780295f2f37331dadce14eaf68` | Case Study 이전 fallback; Vercel `5406289230`, Render `5406318427` |
| Historical backup tag | `ops-backup-20260712` → `eefad164c952d6c859327592eaedc1e2508d5e64` | pre-operations-hardening snapshot; 현재 rollback 대상으로 직접 사용하지 않음 |
| Legacy v0.1 fallback | `2d1f08e6cfabe0a653500302cac1045ccb3b7a2f` | v0.2 자체 결함 시에만 web/API를 함께 내리는 비상 호환 기준 |

Release tag, 두 deployment와 검증 run은 같은 `40dd132` 기준이다. `main`의 후속 문서·dependency
commit과 무관하게 이 tag를 known-good rollback target으로 유지한다.

## v0.2.0 fallback 절차

1. **Wrong PASS 또는 부적격 export가 의심되면 API를 먼저 차단한다.** 독립적인 export kill-switch
   flag가 없으므로 Render에서 서비스를 suspend하거나 known-good deploy로 즉시 rollback한다. CORS
   제거는 direct API 호출을 막지 못하므로 kill switch가 아니다.
2. Render를 GitHub deployment `5410097749`가 가리키는 `40dd132` build로 rollback한다.
3. Vercel을 deployment `5410073153`으로 Instant Rollback한다.
4. `/api/v1/health`가 `status: ok`, `version: 0.2.0`을 반환하는지 확인한다.
5. `/api/v1/domains`가 Architecture, Piping, Plate, Artifact Lab 4개만 반환하는지 확인한다. Solid은
   registry에 없어야 하며 `/api/v1/solid/designs/run`은 `503 DG_CAPABILITY_DISABLED`여야 한다.
6. Production alias의 `/case-study`, `/`, `/piping`, `/plate`, `/solid`, `/intake` DOM sentinel을 확인한다.
7. Architecture approval canary, Artifact Lab audit canary와 CORS를 확인한다.
8. 상태 공지에 영향 시간, export 중단 여부, 사라진 route, 복구한 version/SHA를 기록한다.

## Legacy v0.1 비상 fallback

v0.2.0 release 자체가 사고 원인이고 `40dd132`로 복구할 수 없을 때만 사용한다.

- Render deployment `5404701175`, Vercel deployment `5404705357`을 한 변경 창에서 함께 복구한다.
- `/api/v1/health`의 예상 version은 `0.1.0`, `/api/v1/domains`는 base 3개 domain이다.
- Artifact Lab과 Solid capability는 없고, `/case-study`도 없다. 이 기능 감소를 상태 공지에 명시한다.
- v0.2 web과 v0.1 API를 혼합한 채 incident를 종료하지 않는다.

## Roll forward

1. 원인을 수정한 새 PR에서 CI와 security workflow 전체를 통과시킨다.
2. Preview는 automation bypass를 사용해 로그인 페이지가 아닌 실제 sentinel을 검사한다.
3. Backend가 새 version/capability를 먼저 광고하거나 기존 API와 backward compatible한 상태로 준비한다.
4. `/case-study`를 포함한 여섯 public route, strict API version/capability, Architecture/Artifact canary,
   Solid fail-closed와 CORS가 Production smoke에서 통과한 뒤에만 incident를 종료한다.
5. 새 known-good SHA, deployment ID, smoke run과 확인 시각을 이 문서에 기록한다.

## 설정 복구 주의

- Render rollback은 대상 build의 설정 일부를 재사용하지만 dashboard의 현재 서비스 설정 전체를
  되돌리는 것은 아니다.
- Vercel rollback은 이전 build에 포함된 `NEXT_PUBLIC_*` 값을 사용하므로 환경변수 변경 후에는 새
  build가 필요하다.
- `DATUMGUARD_CORS_ORIGINS`는 `sync: false`이므로 값 자체는 Git에 없다. secret 값은 기록하지 말고
  변수명, owner, 최종 검증 시각만 별도 비밀 관리대장에 보관한다.
- rollback 전후 GitHub deployment URL, health body, domain registry, canary 결과와 담당자를 incident
  timeline에 남긴다.

참고: [Vercel Instant Rollback](https://vercel.com/docs/instant-rollback), [Render Rollbacks](https://render.com/docs/rollbacks).

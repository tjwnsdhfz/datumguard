# DatumGuard v0.4.0 Production Handoff

## 불변 기준점

| 항목 | 검증된 기준 |
|---|---|
| Repository | <https://github.com/tjwnsdhfz/datumguard> |
| Evidence release | [`v0.4.0`](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.4.0) |
| Evidence release source | [`0f9e0b08210aa6bc4fc8cc6bb1d398292b12e832`](https://github.com/tjwnsdhfz/datumguard/commit/0f9e0b08210aa6bc4fc8cc6bb1d398292b12e832) |
| Production web | <https://datumguard-tjwnsdhfz.vercel.app> |
| Production API | <https://datumguard-api.onrender.com> |
| Evidence API provenance | `version=0.4.0`, `release_sha=0f9e0b08210aa6bc4fc8cc6bb1d398292b12e832` |
| Evidence Vercel deployment | GitHub deployment `5420282596` |
| Evidence Render deployment | GitHub deployment `5420269040`; Render `dep-d9a8ffe47okc73eilf7g` |
| Main CI | [run `29229557683`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29229557683) |
| Security | [run `29229557731`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29229557731) |
| Strict production smoke | [run `29229800855`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29229800855) |

`v0.4.0` tag는 위 evidence source revision을 가리킨다. Release에는 Rhino round-trip evidence ZIP,
1280×640 social preview, API/Web CycloneDX SBOM을 첨부했다. Release asset digest와 production
deployment ID가 공개 검증 기준이며, 이후 `main` 문서-only 변경과 분리해 해석한다. 현재 live revision은
항상 `/api/v1/health.release_sha`와 최신 성공 `deployment-smoke`에서 다시 확인한다.

## 공개 capability

| Route | 분야 | Production 상태 | 공식 경계 |
|---|---|---|---|
| `/` | Architecture | 활성 | serialized R2013/mm DXF 독립 재측정 뒤에만 bundle 허용 |
| `/piping` | Plant·semiconductor utility | 활성 | route/support/clearance를 저장 DXF에서 재측정 |
| `/frame` | Structural frame screening | 활성 | exact 2D solver + DXF gate; 구조 인증 아님 |
| `/plate` | Mechanical·ship plate | 활성 | hole/slot/cutout와 공차 gate |
| `/intake` | Existing CAD artifact | 활성 | DXF completeness gate; 항상 `approval_eligible=false` |
| `/case-study` | Portfolio evidence | 활성 | 문제·방법·수치·한계·재현 경로 |
| `/solid` | 제한형 3D solid | UI/schema 활성, hosted run 비활성 | local/CI 전용 STEP 재입력; hosted `503` fail-closed |
| `/openbim` | OpenBIM research | UI 활성, hosted run 비활성 | research only; 제작 승인 아님 |

Hosted active domain은 Architecture, Piping, Plate, FrameGuard, Artifact Lab이다. Solid와 OpenBIM은
공개 Render에서 capability flag가 꺼져 있으며 endpoint가 fail-closed한다. API는 stateless·no DB이며,
외부 artifact 원문을 서버에 장기 보관하지 않는다.

## v0.4 핵심 증거

### Rhino/Grasshopper round trip

`frame_rhino_roundtrip`은 contract를 잠근 뒤 Rhino/Grasshopper 교환 artifact를 비교하고 provenance를
기록한다. 공개 evidence는 Rhino 8.30, Grasshopper, Cordyceps에서 생성한 실제 객체 6개의 GUID를
포함한다.

- Contract: `sha256:30b10a354b388e877acd0e42c6dd5e3b8e667c76f0b9b249d28293fb78950188`
- Exchange: `sha256:f82b99229d326f35298b0b06ee6eab010fe32403ab636e3cd479e009d49e4970`
- Returned artifact: `sha256:a9ce6ad6556a2d59c09945deaefef1965b430110a9d55d5d67e2775b6a3d718c`
- Evidence ZIP: `sha256:55c414f1e5775ab49d275c5c1ffd0aa4a5705529020c3482c9b165ed5985b65c`
- Source: [`docs/evidence/frameguard-rhino-roundtrip-result.json`](evidence/frameguard-rhino-roundtrip-result.json)
- Reproduction: [`docs/frameguard-rhino.md`](frameguard-rhino.md)

Rhino evidence의 `artifact_role`은 `geometry_evidence`다. 공식 DXF verifier나 전문 구조 검토를
대체하지 않으며 arbitrary RhinoScript, C#, shell 실행을 API/MCP에 노출하지 않는다.

### External DXF completeness gate

Artifact Lab은 외부 DXF를 modelspace와 nested block까지 순회해 entity family를 다음처럼 분류한다.

- `MEASURED`: geometry equivalence 계산에 포함
- `RENDER_ONLY`: 미리보기에는 표시하지만 동일성 판정은 불완전
- `UNSUPPORTED`: 공식 비교를 즉시 차단

`comparison_complete=false`이면 `same_geometry_multiset=null`이다. XREF, proxy, underlay, raster,
OLE, wipeout, 순환 block 또는 complexity budget 초과 입력은 PASS로 축약되지 않는다. 원본 bytes와
SHA-256은 보존하지만 contract 없는 외부 audit은 항상 `approval_eligible=false`다.

## 검증 결과

- Ruff format/check: pass
- mypy: pass
- pytest: **413 passed, 6 skipped**
- web typecheck, lint, 15-page production build: pass
- Playwright real API E2E: **41 passed**
- OpenBIM interoperability: pass
- backend/web container build: pass
- CycloneDX SBOM + fixed-critical Trivy scan: pass
- pip audit + Python/JavaScript/TypeScript CodeQL: pass
- Production strict smoke: web sentinels, API version/exact SHA, Architecture/Frame/Artifact canary,
  Solid fail-closed, CORS pass

SBOM release asset digest:

- API: `sha256:3f590c439f1165c22383d7bbe1a5e6a82e8aa6a8cb9b162faf4945a6c0fb4358`
- Web: `sha256:98959b1ed591ec7c5b476b616e3085266b1bad47aae47fdd9aa5eba122962d96`

## 운영 확인과 복구

```bash
curl --fail https://datumguard-api.onrender.com/api/v1/health
curl --fail https://datumguard-api.onrender.com/api/v1/live
curl --fail https://datumguard-api.onrender.com/api/v1/ready
gh api 'repos/tjwnsdhfz/datumguard/deployments?sha=0f9e0b08210aa6bc4fc8cc6bb1d398292b12e832'
gh run view 29229800855 --repo tjwnsdhfz/datumguard
```

Wrong PASS, unverified export, hash 불일치 또는 API contract mismatch는 SEV1이다. 우선 Render를 직전
검증 release로 복구하고, web/API compatibility가 깨졌다면 Vercel도 같은 release로 맞춘다. 상세
순서는 [`docs/operations/incident-runbook.md`](operations/incident-runbook.md)와
[`docs/github-deployment.md`](github-deployment.md)를 따른다. 비용 승인 없는 외부 monitor나 유료
capacity 증설은 적용하지 않았다.

## 미완료 launch gate

아래 항목은 v0.4.0 코드·배포 완료와 별개이며, 완료 전에는 대규모 Show HN/Product Hunt 홍보를 하지 않는다.

1. 단위 불명, tilted datum, out-of-plane failure를 포함한 추가 Rhino evidence pack
2. 60~75초 무음 자막 영상과 15초 README GIF
3. Search Console/sitemap 소유권 확인과 pageview baseline
4. 외부 uptime/error tracker, 장기 metric retention, 실제 SEV1 rollback drill
5. 유료 용량 후보에서 동시성·최대 upload 부하 검증
6. 100개 golden contract + 자연어 50개 benchmark 공개 보고서

소프트 런치에 사용할 검증된 문구와 CTA는
[`docs/launch/v0.4.0-launch-kit.md`](launch/v0.4.0-launch-kit.md)에 고정한다.

# DatumGuard Growth and Launch Roadmap

- 작성 기준일: 2026-07-13
- 현재 공개 release: `v0.3.0`
- 기준 source: `71b4aeb2e56bb910a4848b21345343602c5099a3`
- 목적: DatumGuard를 기술 데모에서 채용 담당자, Rhino/Grasshopper 실무자, 오픈소스 개발자가 직접 재현하고 피드백할 수 있는 공개 공학 포트폴리오 제품으로 승격한다.

## 1. 결정

다음 최우선 개발은 새 공학 분야 추가가 아니다.

> **FrameGuard v0.4 — Rhino Verified Round Trip**

완성해야 할 공개 증거 흐름은 다음과 같다.

```text
Rhino/GH 실제 모델
  -> centerline/support/load/section metadata 추출
  -> explicit unit/datum neutral exchange
  -> deterministic exact screening
  -> R2013/mm DXF serialization
  -> independent DXF reopen and remeasurement
  -> fail-closed export
  -> source/object/artifact hash manifest
```

홍보 문구는 `AI structural safety prediction`이 아니라 아래 범위로 통일한다.

- `Engineering verification harness`
- `Fail-closed CAD assurance`
- `Preliminary structural screening`
- `Not structural certification`

## 2. 대상과 전환 목표

우선 대상은 다음 순서로 고정한다.

1. 국내 플랜트·반도체 FAB·조선·CAD 자동화 직무의 채용 담당자와 현업 엔지니어
2. Rhino/Grasshopper 및 computational design 사용자
3. CAD·OpenBIM·구조해석 오픈소스 개발자
4. 일반 AI 개발자와 글로벌 launch 커뮤니티

방문자의 목표 행동도 하나씩 분리한다.

| 방문자 | 첫 CTA | 성공 행동 |
|---|---|---|
| 채용 담당자 | `60초 Case Study 보기` | 문제·방법·증거·한계를 3분 안에 이해 |
| 엔지니어 | `검증된 Frame 실행` | 정상과 실패 preset을 모두 실행 |
| Rhino/GH 사용자 | `Rhino demo kit 재현` | `.3dm/.gh`부터 verification JSON까지 재현 |
| 개발자 | `Benchmark 재현` | 명령 실행 또는 구체적인 issue/discussion 제출 |

GitHub README에는 장문의 지원자 서사를 넣지 않는다. 문제, 실제 workflow, 수치 증거, 재현 명령, 한계와 기여 경로를 우선한다.

## 3. 2026-07-13 기준 상태

### 3.1 이미 준비된 것

- `v0.3.0` public release, Vercel web, Render API, exact-SHA deployment smoke
- 376 pytest, 35 Playwright, container/SBOM/security gate
- OpenSeesPy 6/6 parity와 PyG GraphSAGE/GAT 비교
- 정상/실패 FrameGuard demo와 `REVIEW_REQUIRED` gate
- robots.txt, XML sitemap, canonical, route별 title/description/OG/Twitter metadata
- HTTPS, privacy page, release notes, rollback 문서
- public API/OpenAPI와 no-signup sample 실행

### 3.2 발견 가능성의 현재 격차

| 항목 | 현재 상태 | 판단 |
|---|---|---|
| Web search | `site:` 및 제품명 검색 결과 0건 | 새 사이트로 아직 발견되지 않음 |
| Custom domain | `datumguard-tjwnsdhfz.vercel.app` | 지금이 domain 결정과 migration의 최저비용 시점 |
| Search Console | 저장소에서 연결 여부 확인 불가 | property 확인과 sitemap 제출 필요 |
| Web analytics | client analytics package/event taxonomy 없음 | 홍보 전 baseline 필요 |
| Structured data | JSON-LD 없음 | `WebApplication`/`SoftwareApplication` 의미 정보 추가 후보 |
| GitHub repository | star/fork/watcher 0, release asset download 0 | 출시 직후라 정상이며 baseline으로만 기록 |
| GitHub community | community health 71% | `CONTRIBUTING`, `CODE_OF_CONDUCT`, issue form 부재 |
| GitHub Discussions | 비활성 | 사용자 질문과 전문가 피드백 수집 경로 부재 |
| GitHub social preview | GitHub 기본 이미지 사용 | custom 1280x640 proof image 필요 |
| GitHub profile | name, bio, blog, location, hireable, pinned repo, profile README 없음 | 채용 전환을 막는 가장 큰 외부 프로필 격차 |
| Rhino evidence | 실제 Rhino 8 + Grasshopper + Cordyceps `.gh` round-trip과 GUID/XDATA evidence 완료 | standalone `.3dm`, failure variant, 영상은 PR 5 범위로 유지 |

GitHub clone 수치는 CI가 집중된 날에 발생했으므로 외부 수요로 해석하지 않는다. referrer와 popular path가 생기기 전에는 automation이 섞인 지표로 취급한다.

## 4. 홍보 전 Launch Gate

아래 조건이 모두 닫히기 전에는 Show HN, Product Hunt, 대규모 cross-post를 하지 않는다.

- [x] 실제 Rhino 8 + Grasshopper + Cordyceps 왕복 시연
- [ ] 정상, 단위 불명, tilted datum, out-of-plane failure evidence
- [ ] `.3dm`, `.gh`, exchange JSON, contract JSON, DXF, verification JSON, manifest bundle
- [x] Rhino object GUID에서 DXF XDATA까지 provenance 추적
- [ ] 60~75초 무음 자막 영상과 15초 README GIF
- [ ] 첫 PASS까지 가입 없이 60초 이내
- [ ] 정상 preset 이후 failure preset을 한 CTA로 실행 가능
- [ ] GitHub custom social preview, profile, contribution path
- [ ] Search Console 또는 선택한 search property와 sitemap 확인
- [ ] 최소 pageview baseline과 privacy 문서 일치
- [ ] external uptime check와 launch-day cold-start 정책
- [ ] `screening only` 경계가 landing, video, release, community post에 동일하게 표시

## 5. v0.4 개발 계획 — 30일

예상량은 solo 기준 20~24 person-days다.

### PR 1 — `chore/growth-foundation`

예상: 1~2일

#### 범위

- README first fold를 bilingual technical summary로 축약
- hero proof image/GIF, `Try live`, `Case study`, `Release`, `Reproduce` CTA
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, `ROADMAP.md`
- issue forms: bug, benchmark request, feature request
- Discussions category와 Welcome/Benchmark Requests 안내
- repository description과 topics를 niche engineering 기준으로 조정
- 1280x640, 1MB 이하 GitHub social preview 제작
- GitHub 개인 profile README, name/bio/website/hireable, DatumGuard pin은 계정 작업으로 별도 체크

#### 권장 topics

`cad`, `dxf`, `ifc`, `step`, `rhino3d`, `grasshopper3d`, `structural-engineering`,
`finite-element-analysis`, `opensees`, `graph-neural-network`, `engineering-ai`,
`verification`, `openbim`, `computational-design`, `piping`, `semiconductor`,
`shipbuilding`, `fastapi`, `nextjs`, `mcp`

#### 완료 기준

- GitHub community health 87% 이상, 목표 100%
- custom social preview 활성
- 질문은 Discussions, 재현 가능한 결함은 Issues로 연결
- README 첫 화면에서 30초 안에 live demo와 safety boundary를 찾을 수 있음
- Markdown link check 통과

GitHub의 community checklist와 social preview 규격은 공식 문서를 따른다.

- [GitHub community profile](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories)
- [GitHub social preview](https://docs.github.com/en/enterprise-server%403.19/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview)

### PR 2 — `feat/web-launch-readiness`

예상: 2~3일

#### 범위

- landing hero와 CTA hierarchy 수정
- 한국어 핵심 설명 + 영문 technical summary
- `WebSite`, `WebApplication` 또는 `SoftwareApplication`, author `Person` JSON-LD
- sitemap `lastModified`, canonical origin을 환경 기반 단일 값으로 관리
- custom 404와 engineering route recovery
- Vercel Web Analytics pageview baseline 후보
- privacy page에 analytics 종류, 수집 항목, retention, opt-out 경계 반영
- `/case-study -> /frame -> GitHub/release` 내부 링크 강화
- metadata/JSON-LD/CTA/404 Playwright 테스트

#### 구조화 데이터 원칙

- 실제 rating/review가 없으므로 값을 만들지 않는다.
- Google rich result를 보장한다고 표현하지 않는다.
- 배포 후 Rich Results Test와 URL Inspection으로 critical error만 검증한다.

#### domain 결정

검색 등록 전에 custom domain 구매 여부를 결정한다.

- 구매: 새 domain을 canonical로 만들고 기존 Vercel URL을 301 redirect
- 미구매: 현재 Vercel URL을 최소 6개월 이상 안정적으로 유지하고 그대로 Search Console에 제출

domain을 바꾼다면 sitemap, OG, GitHub homepage, Vercel/Render CORS, Search Console property를 같은 release에서 교체한다. Google의 site move 지침에 따라 이전 URL redirect는 장기간 유지한다.

- [Vercel custom domain](https://vercel.com/docs/domains/working-with-domains/add-a-domain)
- [Google sitemap submission](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Google Search Console](https://support.google.com/webmasters/answer/9128668)
- [Software application structured data](https://developers.google.com/search/docs/appearance/structured-data/software-app)

#### 완료 기준

- robots, sitemap, canonical, OG image, JSON-LD 자동 검사 통과
- Search Console live inspection에서 index blocking 없음
- pageview test가 analytics dashboard에 나타남
- CAD bytes, filename, contract, memo가 analytics로 전송되지 않음
- privacy page와 실제 수집 코드 일치
- mobile/desktop horizontal overflow 0

### PR 3 — `feat/rhino-verified-roundtrip`

예상: 5~7일

2026-07-13 구현 상태: one-step API/MCP, full contract XRECORD, semantic XDATA,
실제 Rhino GUID 6개 provenance, independent DXF reopen, fail-closed evidence ZIP과 `.gh` 재현
파일을 완료했다. standalone `.3dm`, mm/inch live pair, failure variant, 영상/GIF는 PR 5의
portfolio evidence pack에서 닫는다.

#### 산출물

- 실제 Rhino 8 pipe-rack `.3dm`
- 재사용 가능한 Grasshopper `.gh`
- UserString tagging helper
- mm/inch equivalent model
- rotated XY construction plane model
- unknown unit, tilted datum, out-of-plane failure variants
- exchange JSON, normalized contract, exact result, DXF, verification JSON
- source/object/artifact SHA-256 manifest
- 60~90초 demo video와 15초 GIF

#### 완료 기준

- mm와 inch 문서가 같은 normalized geometry/hash를 생성
- 회전된 XY datum은 정확히 변환
- unknown unit, tilted datum, out-of-plane geometry는 fail-closed
- Rhino GUID, contract entity ID, DXF XDATA가 연결됨
- DXF 변조 시 official PASS와 download가 모두 차단됨
- fresh Rhino 8 환경에서 문서만 보고 5분 안에 재현
- Rhino evidence는 `SECONDARY EVIDENCE`, 독립 DXF verifier가 official gate

#### 수동 의존성

- Rhino 실행
- Grasshopper 실행
- active canvas에 Cordyceps component 연결

Cordyceps가 연결되지 않으면 먼저 `127.0.0.1:47820` adapter 상태, Rhino, Grasshopper, active canvas component를 확인한다.

### PR 4 — `feat/dxf-completeness-gate`

예상: 3~4일

2026-07-13 구현 상태: `support_matrix_version=2026-07-13.1`, entity별
`MEASURED/RENDER_ONLY/UNSUPPORTED`, `comparison_complete`, XREF·proxy·underlay·image·OLE·wipeout
차단, block nesting/cycle과 entity/render budget을 구현했다. 원본 SHA-256은 유지하고 불완전 비교는
`needs_confirmation`과 `same_geometry_multiset=null`로 제한한다.

`/intake`는 이미 외부 DXF/STEP/IFC upload를 지원하므로 새 업로더를 만들지 않는다. 대신 외부 DXF를 얼마나 완전하게 비교했는지를 명시한다.

#### support level

- `MEASURED`: 정밀 fingerprint, bbox, revision comparison 가능
- `RENDER_ONLY`: 시각화 가능하지만 완전 비교 대상은 아님
- `UNSUPPORTED`: 결과를 `needs_confirmation`으로 제한

#### 우선 entity

`INSERT`, nested block, XREF, proxy entity, underlay, image, OLE, wipeout

#### 완료 기준

- `support_matrix_version`, entity별 support level, `comparison_complete` 반환
- unsupported entity가 있으면 geometry equality를 완전 동일로 표시하지 않음
- entity count, nesting depth, render complexity budget 적용
- malformed, timeout, oversized, deep nesting fixture가 worker를 중단시키지 않음
- original bytes와 source hash 불변
- external upload는 계속 `approval_eligible=false`

### PR 5 — `chore/v0.4-portfolio-ready`

예상: 5~7일

#### 범위

- 실제 CAD sample evidence pack 4종과 각 failure counterpart
  - Rhino structural frame
  - LibreCAD/FreeCAD DXF plate
  - FreeCAD STEP bracket
  - 재배포 허용 IFC building
- source/license/tool version/hash/expected measurement 문서
- `Try verified -> Break one constraint -> Download evidence` tour
- 5분 Rhino tutorial, 3분 Artifact Lab tutorial
- curl/Python/TypeScript sample
- axe와 Lighthouse CI gate
- research artifact drift workflow
- v0.4 release notes, SBOM, demo bundle

#### 완료 기준

- first PASS median 60초 이하
- warm sample verification 5초 이하
- keyboard-only sample, verify, download 가능
- axe serious/critical 0
- Lighthouse performance/accessibility 목표 90 이상
- 실제 CAD sample 4개 + failure 4개
- packaged benchmark와 live research result drift 자동 비교
- drift가 model을 자동 교체하지 않고 release를 `REVIEW_REQUIRED`로만 차단

## 6. 배포 계획

### 6.1 PR gate

모든 PR은 다음을 통과한다.

- Python format/lint/type/test
- web type/lint/build
- real-API Playwright
- metadata, JSON-LD, robots, sitemap, 404 test
- backend/web container build와 SBOM
- security workflow
- Vercel Preview DOM smoke

### 6.2 capability 배포 순서

새 backend capability가 필요한 web은 capability detection으로 감싼다.

1. 기존 production API와 호환되는 web preview
2. backend merge 및 Render 배포
3. health의 exact `release_sha`와 capability 확인
4. web CTA 활성
5. deterministic canary와 CORS strict smoke

web과 API가 다른 revision일 때 official capability로 표시하지 않는다.

### 6.3 launch-day 운영

- launch 24시간 전 final release tag와 rollback tag 확인
- launch 직전 `/live`, `/ready`, FrameGuard canary, CORS 확인
- 48시간 동안 기능 개발을 동결하고 P0/P1만 hotfix
- GitHub/LinkedIn/McNeel 댓글을 24시간 내 답변
- 전문 피드백은 issue로 전환하고 source link를 남김
- Wrong PASS, stale download, unverified export는 SEV1

### 6.4 hosting 비용 선택

| 단계 | 권장 비용 | 판단 |
|---|---:|---|
| 현재 quiet beta | $0/month | Vercel Hobby + Render Free, cold start 허용 |
| domain | 대략 $10~25/year | 실제 registrar 가격 확인 후 별도 승인 |
| soft launch | Render Starter $7/month 상당 | 512MB RSS canary 통과 시 cold start 제거, 초 단위 prorating 가능 |
| 2GB worker staging | Render Standard $25/month | Solid/OpenBIM RSS·동시성 검증 전용 |
| Vercel Pro | $20/month | 상용 사용 또는 Hobby 한도 관측 후에만 |
| 광고 | $0 | niche portfolio는 전문가 피드백이 paid reach보다 우선 |

Render Free는 15분 idle 뒤 spin-down하며 공식 문서도 production workload에 권장하지 않는다. Show HN/Product Hunt 당일에는 Free cold start를 그대로 두지 않는다.

- [Render Free limits](https://render.com/docs/free)
- [Render pricing](https://render.com/pricing)
- [Vercel Web Analytics pricing](https://vercel.com/docs/analytics/limits-and-pricing)

Vercel Hobby Analytics는 현재 50,000 events/month와 1개월 reporting window 안에서 무료다. custom event와 UTM 분석은 포함되지 않으므로 첫 release에서는 pageview와 GitHub Traffic을 기준으로 사용한다. 유료 analytics나 별도 tracker는 privacy/cost 승인 후에만 추가한다.

## 7. GitHub와 개인 프로필 계획

### repository

- concise English description
- custom social preview
- niche topics
- bilingual first fold
- 15초 proof GIF
- 5분 quickstart
- current vs future capability 표
- contribution, security, citation, roadmap
- Discussions: `Announcements`, `Q&A`, `Benchmark Requests`, `Show and Tell`
- Issues: reproducible defect와 accepted roadmap only
- `good first issue`는 실제로 작은 문서·fixture·test 작업에만 부여

### 개인 profile

- name과 직무 방향을 명시
- bio 예시: `Architecture-trained engineering automation developer | CAD assurance, Rhino/GH, DXF/IFC, structural screening`
- website는 Case Study 또는 custom domain
- location과 `Available for opportunities`는 공개 범위를 확인 후 설정
- profile README에 DatumGuard evidence 3개와 target role만 표시
- DatumGuard를 첫 pinned repository로 지정

GitHub profile은 공식적으로 profile README와 pinned work를 통해 공개 작업을 보여줄 수 있다.

- [GitHub profile guide](https://docs.github.com/en/account-and-profile/concepts/personal-profile)
- [GitHub Traffic](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-traffic-to-a-repository)

## 8. 메시지와 페이지 copy

### Korean hero

**Headline**

> CAD가 생성됐다는 사실은, 치수가 맞다는 증거가 아닙니다.

**Subheadline**

> DatumGuard는 요구사항을 contract로 잠그고 저장된 DXF·STEP을 다시 읽어 재측정한 뒤, 검증된 파일만 내보냅니다.

**CTA**

- Primary: `검증된 Frame 실행`
- Secondary: `60초 Case Study`
- Technical: `Benchmark 재현`

### English hero

**Headline**

> CAD command success is not accuracy evidence.

**Subheadline**

> Lock the requirements, reopen the serialized artifact, remeasure independently, and export only verified results.

**Tagline**

> Fail-closed verification for AI-assisted CAD workflows.

## 9. 홍보 자산

### 60~75초 영상 storyboard

1. Rhino/GH metadata 추출
2. explicit unit/datum contract
3. 정상 preset: `0.5656mm < 0.65mm` -> PASS
4. DXF write -> reopen -> `0.001mm VERIFIED`
5. missing brace: `0.7633mm` -> BLOCKED
6. OOD input -> `REVIEW_REQUIRED`
7. `Screening only — not structural certification`

### LinkedIn 6장 carousel

1. 그럴듯하지만 틀린 CAD가 왜 위험한가
2. unit, datum, metadata contract
3. serialized DXF 독립 재측정
4. OpenSeesPy parity 6/6
5. GraphSAGE/GAT와 uncertainty gate
6. 한계와 직접 체험 CTA

### benchmark pack

- input contract
- exact/OpenSees result JSON·CSV
- absolute/relative tolerance
- environment lock와 실행 명령
- intentional failure fixture
- engine/library version과 source
- expected and actual hash

## 10. 채널 우선순위

| 순위 | 채널 | 목적 | 형식 |
|---:|---|---|---|
| 1 | GitHub + public web | canonical evidence | 항상 최신 |
| 2 | LinkedIn | 국내 채용 전환 | 주 1회, 한국어 + 영문 3줄, video/carousel |
| 3 | McNeel Forum | Rhino/GH 전문가 검토 | live round-trip 이후 영문 글 1회 |
| 4 | GeekNews Show GN | 국내 개발자 유입 | 한국어 launch 1회 |
| 5 | YouTube | 재사용 가능한 시연 | 75초 + 4~6분 walkthrough |
| 6 | DEV 또는 Hashnode 한 곳 | 검색 가능한 기술 설명 | 월 1~2개 |
| 7 | Reddit StructuralEngineering | benchmark 피드백 | 특정 benchmark 한 건, 질문 중심 |
| 8 | Threads | build-in-public 보조 | 주 2~3회, 한 글 한 인사이트 |
| 9 | Show HN | 글로벌 기술 피드백 | v0.4 안정 후 1회 |
| 10 | Product Hunt | product launch | v1.0 수준에서 1회 |

McNeel Gallery는 첫 이미지가 thumbnail이므로 video만 올리지 않고 proof image와 `.gh/.3dm` sample을 함께 제공한다.

- [McNeel Grasshopper Gallery](https://discourse.mcneel.com/t/about-the-grasshopper-gallery/101575)
- [GeekNews Show](https://news.hada.io/show)
- [Show HN guidelines](https://news.ycombinator.com/showhn.html)
- [Product Hunt featuring guidelines](https://help.producthunt.com/en/articles/9883485-product-hunt-featuring-guidelines)

Threads는 topic, original content, reply 중심으로 운영한다. Meta는 성장 목적 게시 빈도로 주 2~5회와 text context가 있는 image/video를 안내한다.

- [Threads creator guidance](https://about.fb.com/news/2024/10/find-your-community-with-new-threads-educational-insights/)
- [Threads profile links and insights](https://about.fb.com/news/2025/03/new-threads-features-more-personalized-experience-you-control/)

## 11. 4주 콘텐츠 일정

### Week 0 — 준비

- Rhino round-trip, video, demo kit
- GitHub profile, custom preview, Discussions
- analytics baseline, domain/Search Console 결정
- channel-specific landing URLs 또는 명확한 referrer 기록 방식

### Week 1 — evidence-first soft launch

- 월: v0.4 release와 README 고정
- 화: LinkedIn carousel + 60초 video
- 목: McNeel Forum 영문 기술 글
- 금~일: 새 cross-post 없이 댓글 답변과 issue 전환

### Week 2 — 국내 개발자와 검색 자산

- 화: GeekNews Show GN
- 목: `Why AI-generated CAD needs a second reader` 기술 글
- 토: 4~6분 YouTube walkthrough
- 받은 질문을 FAQ/README/test에 반영

### Week 3 — 전문가 benchmark 검토

- Reddit에 OpenSees parity만 깊게 게시
- Threads에 DXF re-read, uncertainty, failure gate를 각각 분리
- 요청 문구는 좋아요가 아니라 `다음 benchmark를 추천해 주세요`

### Week 4 — 글로벌 launch 판단

- no-signup, cold-start, uptime, English docs가 안정적이면 Show HN
- 1270x760 gallery 3장, video, first comment, onboarding이 완성되면 Product Hunt draft
- 조건이 안 되면 다음 major release까지 보류

Show HN은 직접 실행 가능한 non-trivial project만 받고 upvote/comment 요청을 금지한다. HN 게시문과 댓글은 사용자가 자신의 문체로 직접 최종 작성한다.

## 12. 제목 초안

- LinkedIn: `AI가 만든 CAD를 그대로 믿지 않도록, 실패하면 DXF를 내보내지 않는 검증 하네스를 만들었습니다`
- McNeel: `FrameGuard: Rhino metadata to unit/datum-checked screening with fail-closed DXF export`
- GeekNews: `Show GN: CAD와 해석 증거가 불일치하면 DXF를 차단하는 오픈소스 공학 검증 하네스`
- Reddit: `I verified my 2D frame solver against OpenSeesPy (6/6). What benchmark should I add next?`
- Show HN: `Show HN: DatumGuard — fail-closed CAD export with independent DXF remeasurement`
- Product Hunt: `Fail-closed verification for AI-assisted CAD workflows`
- 기술 글: `Why AI-generated CAD needs a second reader`

## 13. 측정 계획

### baseline

- GitHub Traffic은 최근 14일만 제공하므로 매주 같은 요일 UTC 기준으로 보존
- views, unique visitors, clones, referrers, popular paths
- release asset downloads
- Vercel pageviews by route
- API route/status/duration aggregate; payload 제외
- LinkedIn profile views, post views, link visits
- Threads views, replies, link visits
- substantive issue/discussion과 외부 benchmark reproduction

### event taxonomy 후보

custom analytics를 승인한 뒤에만 다음 이벤트를 사용한다.

- `workspace_opened`
- `sample_loaded`
- `verification_started`
- `verification_passed`
- `verification_blocked`
- `bundle_downloaded`
- `github_clicked`

event에는 domain, result class, duration bucket, release version만 포함한다. CAD bytes, filename, contract, coordinates, natural-language note는 수집하지 않는다.

### 30일 learning target

| 지표 | 목표 |
|---|---:|
| 타깃 방문 | 200~500 |
| Case Study -> Frame route 비율 | 25% 이상 |
| 전문가의 구체적 feedback | 5건 |
| 외부 benchmark 제안 | 2건 |
| issue/discussion으로 전환한 feedback | 3건 |
| 직무 관련 대화 또는 인터뷰 전환 | 3건 |

star와 단순 조회수는 보조 지표다. 핵심 증거는 실제 엔지니어의 검토, 외부 재현, 수정된 issue다.

## 14. 60일 계획 — v0.5 Evidence Explorer

### installable Rhino/GH package

- `.yak`, `.ghuser` 또는 명시적인 supported packaging 선택
- one-click export와 result annotation import
- clean Rhino 8 설치 smoke
- package version, Rhino version, exchange schema provenance
- Food4Rhino 등록은 설치 가능한 package와 live smoke 이후

### 3D/IFC Evidence Viewer

범용 authoring이 아니라 secondary evidence viewer로 제한한다.

- orbit, zoom, fit, section
- IFC spatial tree
- issue `GlobalId` highlight
- baseline/candidate added/removed/changed 표시
- measurement/AABB overlay
- triangle/element budget과 static fallback
- viewer 실패는 official verdict에 영향 없음

### Public API Sandbox

- `/developers`
- Architecture, FrameGuard, Artifact samples
- curl/Python/TypeScript snippet
- schema, error code, request ID
- anonymous low quota
- CORS/rate-limit/timeout 표시
- disabled Solid/OpenBIM capability 정확히 표현

### Release Evidence History

DB 없이 GitHub release artifact를 읽어 tests, parity, GNN metric, uncertainty threshold, drift, canary, source SHA를 표시한다.

## 15. 90일 연구 — v0.6 External Geometry Benchmark

- 다양한 Rhino/GH frame 20~30개
- topology-family holdout
- multiple load case와 distributed load
- NumPy/OpenSees parity 확대
- GraphSAGE/GAT external generalization
- conformal coverage와 OOD threshold 사전 등록
- failure active-learning corpus

### 완료 기준

- source와 redistribution license 공개
- split leakage 0
- seed별 metric과 coverage 공개
- synthetic 대비 external 성능 저하도 그대로 보고
- high uncertainty/OOD는 모두 `REVIEW_REQUIRED`
- ML 결과는 official PASS 또는 구조 안전 판정에 사용하지 않음
- protocol을 결과 전에 Git tag로 고정

## 16. 향후 90일 보류 범위

- 새로운 engineering domain
- account, DB, collaboration
- CAD cloud storage
- mobile precision CAD editing
- 자연어 arbitrary geometry generation
- general BIM authoring
- 3D nonlinear, buckling, material nonlinearity
- structural safety certification claim
- ML result를 exact solver보다 앞세우는 UI
- paid advertising

## 17. 바로 다음 실행 순서

1. Rhino, Grasshopper, Cordyceps를 열어 live round-trip evidence 생성 가능 여부 확인
2. custom domain 구매 여부 결정
3. `chore/growth-foundation` branch와 GitHub profile 작업
4. `feat/web-launch-readiness`로 SEO, CTA, analytics baseline
5. `feat/rhino-verified-roundtrip` 구현과 video/demo kit
6. `feat/dxf-completeness-gate` 구현
7. 실제 CAD sample, accessibility/performance, drift gate
8. v0.4 release와 soft launch
9. 7일 feedback triage 후 Show HN/Product Hunt 진행 여부 판단

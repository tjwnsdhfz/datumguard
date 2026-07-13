# Analytics and attribution policy

이 문서는 DatumGuard 공개 데모의 출시 성과를 확인할 때 허용되는 최소 분석 범위와 금지되는 설계 데이터 수집을 고정한다. 제품 정확성 evidence와 방문자 분석은 서로 다른 데이터 경계다.

## Current production baseline

- 현재 활성 범위는 Vercel Web Analytics의 pageview baseline뿐이다.
- production project 설정은 `npx vercel project web-analytics datumguard-tjwnsdhfz --format json`이 `"enabled": true`를 반환하는지 배포 전후에 확인한다.
- custom event tracking은 구현하지 않는다. 아래 event taxonomy는 향후 검토용 계약이며 현재 전송되지 않는다.
- 분석용 cookie를 설정하지 않는다.
- 계정, 이메일, 사용자 프로필 또는 서버 측 analytics database를 만들지 않는다.
- 페이지뷰 제공자는 네트워크 요청 처리 과정에서 URL, referrer, IP address, user agent, 시간 같은 request/browser metadata를 자체 정책에 따라 처리할 수 있다. 애플리케이션이 설계 데이터를 전송하지 않는다는 사실을 “어떤 메타데이터도 처리되지 않는다”는 보장으로 표현하지 않는다.
- 브라우저 draft의 30일 만료와 analytics dashboard의 reporting window 또는 provider 운영 로그 보존은 별개다. 후자는 Vercel plan, 제품 설정, 정책을 따른다.
- 현재 앱 내 analytics opt-out은 제공하지 않는다. 향후 custom tracking을 활성화하기 전 consent 및 opt-out 요구사항을 다시 검토한다.

## Allowed UTM vocabulary

외부 홍보 링크는 아래 열거값만 사용한다. 대소문자는 소문자로 정규화하고 공백은 `_`로 바꾼다. 허용 목록에 없는 값은 새 값으로 저장하지 않고 제거하거나 배포 전에 이 문서를 갱신한다.

| Parameter | Allowed values |
| --- | --- |
| `utm_source` | `github`, `linkedin`, `mcneel`, `geeknews`, `youtube`, `blog`, `reddit`, `threads`, `hackernews`, `producthunt` |
| `utm_medium` | `profile`, `repository`, `release`, `post`, `forum`, `video`, `article`, `community`, `launch` |
| `utm_campaign` | `v0_4_launch`, `rhino_roundtrip`, `cad_assurance`, `benchmark_release` |
| `utm_content` | `hero_cta`, `case_study`, `frame_demo`, `architecture_demo`, `benchmark`, `release`, `source` |

UTM은 홍보 링크의 저카디널리티 분류용이다. 사람 이름, 회사명, 파일명, issue 번호, 자유 입력 문장 또는 식별자를 값으로 사용하지 않는다.

## Deferred low-cardinality event contract

아래 이름은 custom tracking을 승인한 뒤에만 구현할 수 있다. event property는 표의 열거값과 `status` 같은 제한된 boolean/enum만 허용한다. 자유 텍스트와 숫자 설계값은 허용하지 않는다.

| Event | Purpose | Allowed properties |
| --- | --- | --- |
| `workspace_view` | 공개 workspace 관심도 | `workspace`: `architecture`, `piping`, `plate`, `solid`, `frame`, `intake`, `openbim` |
| `sample_load` | 합성 preset 사용 여부 | `workspace`, `preset`: 문서화된 fixture ID만 허용 |
| `verification_start` | 검증 funnel 시작 | `workspace` |
| `verification_result` | PASS/FAIL funnel 완료 | `workspace`, `status`: `passed`, `failed`, `unavailable` |
| `evidence_open` | case study 또는 release evidence 열람 | `surface`: `case_study`, `release`, `source`, `benchmark` |
| `bundle_download` | 검증 bundle 다운로드 시도 | `workspace`, `status`: `available`, `blocked` |

이 taxonomy는 구현 승인이 아니다. 활성화 전 privacy 문구, consent/opt-out 필요성, provider 설정, data retention, 테스트와 rollback을 별도 PR에서 검토한다.

## Prohibited data

Analytics pageview와 향후 event 모두 다음 값을 property 또는 event name에 포함해서는 안 된다.

- CAD/BIM design payload 또는 그 일부
- 업로드·다운로드 파일명과 경로
- `contract_hash`, `artifact_hash`, revision hash 또는 다른 고유 식별자
- 좌표, 치수, 공차, 하중, 재료값과 solver 결과
- 오류 message, stack trace, violation detail 또는 사용자가 입력한 자연어
- 이메일, IP address, 사용자 이름, 회사명 또는 프로젝트명

DatumGuard 애플리케이션은 URL query string, referrer 또는 analytics payload를 IndexedDB draft, API request body/log schema, DXF/STEP/IFC, verification JSON, PDF, ZIP bundle 같은 artifact에 복사하거나 저장하지 않는다. 현재 pageview provider가 네트워크 경계에서 URL/referrer metadata를 처리할 수 있다는 사실과 이 애플리케이션 저장 금지는 구분한다.

## Review gate

Custom tracking을 제안하는 PR은 다음을 모두 충족해야 한다.

1. 이 문서의 event와 property allowlist 안에 있다.
2. 설계 데이터, 자유 텍스트, hash와 오류 detail이 전송되지 않는 테스트가 있다.
3. provider retention과 dashboard access owner를 기록한다.
4. privacy page와 opt-out/consent 판단을 함께 갱신한다.
5. 기능을 제거하는 rollback 절차와 analytics가 없어도 제품이 정상 동작하는 검증을 남긴다.

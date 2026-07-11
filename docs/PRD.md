# DatumGuard 제품 요구사항 정의서(PRD)

| 항목 | 내용 |
|---|---|
| 문서 버전 | 1.2.0 |
| 작성일 | 2026-07-11 |
| 제품 단계 | 공개 Portfolio MVP |
| 초기 설계군 | 건축 평면 + 플랜트/반도체 utility piping + 기계/조선 plate |
| 기준 사용자 | 메이커·공학 학습자 |
| 공식 제작 산출물 | 검증된 DXF |
| 연관 문서 | [TRD](./TRD.md), [Prompt Design](./prompt-design.md) |

## 1. 제품 요약

DatumGuard는 공학설계 요구사항을 수치 기반 `DesignContract`로 확정하고, CAD 산출물을 독립적으로 다시 읽어 치수·좌표·공차를 검증한 뒤 합격한 결과만 배포하는 Engineering Design Assurance Harness다.

사용자는 웹의 구조화 폼으로 기준점, 외곽, 홀, 슬롯, cutout, 치수와 공차를 입력한다. 자연어 에이전트는 “좌우 대칭”, “홀을 같은 간격으로 배치” 같은 의도를 구조화된 제약조건 후보로 바꾸지만 수치나 기준점을 임의로 추정하지 않는다. 하네스는 DXF를 생성한 후 별도 verifier로 파일을 재수입하여 실제 좌표와 치수를 측정한다. 실패 시 잠기지 않은 자유 파라미터만 허용범위 내에서 최대 3회 수정한다.

MVP는 일반 사용자가 설치 없이 웹에서 이용하고, 고급 사용자는 동일한 코어를 MCP 도구로 호출한다. Rhino는 미리보기와 교차검증을 담당하며 공식 합격 판정은 독립 DXF verifier가 담당한다.

공개 demo의 기본 경로는 12×8m 합성 건축 평면으로 정확성 보증 흐름을 보여준다. 사용자는 wall, grid, opening, column과 room seed를 직접 이동하거나 mm 값으로 편집하고, 생성된 건축 DXF를 다시 읽은 검증 evidence가 통과한 뒤에만 공식 bundle을 받을 수 있다. `/piping`은 반도체 utility/플랜트 배관 route를, `/plate`는 기계·조선 plate/panel 설계를 같은 approval 원칙으로 제공한다.

## 2. 문제 정의

기존 CAD/Rhino MCP는 자연어로 객체를 빠르게 생성하지만 다음 이유로 공학설계의 완료 조건을 보장하기 어렵다.

- 자연어의 “가운데”, “같은 간격”, “약간 띄워서”가 명확한 datum과 좌표로 변환되지 않는다.
- 에이전트가 성공 응답을 받더라도 실제 생성 형상의 치수가 요구값과 다를 수 있다.
- 생성에 사용한 코드나 메모리 값을 그대로 검증값으로 사용하면 실제 artifact 오류를 놓친다.
- 실패 후 수정 과정에서 이미 확정된 치수나 공차를 조용히 바꿀 수 있다.
- 결과물과 요구사항, 수정 이유, 측정 evidence가 연결되지 않는다.

DatumGuard는 “그려졌는가”가 아니라 “요구사항을 만족하는 artifact가 생성되었고 독립 측정으로 확인되었는가”를 완료 기준으로 바꾼다.

## 3. 제품 비전

> AI가 만든 공학 도면을 신뢰하라고 요구하지 않고, 요구조건과 실제 측정값을 함께 보여주어 사용자가 검증할 수 있게 한다.

## 4. 목표

1. 모호한 자연어를 확인 가능한 구조화 계약으로 변환한다.
2. 모든 치수와 feature를 명시적 datum과 좌표계에 연결한다.
3. DXF 생성기와 독립 verifier를 분리한다.
4. locked dimension과 datum을 자동수정으로부터 보호한다.
5. 자유 파라미터만 범위 내에서 제한적으로 수정한다.
6. 검증을 통과한 artifact만 공식 export한다.
7. 웹과 MCP에서 동일한 계약·검증 코어를 제공한다.
8. 합성 benchmark로 정확성, 재현성과 실패를 공개한다.

## 5. 비목표

MVP는 다음을 제공하지 않는다.

- 구조 강도, 피로, 열, 유체 또는 전기 해석
- 산업표준·건축법·안전규정 준수 인증
- 3D 기계 부품이나 조립체의 공식 검증
- 임의 형상의 범용 CAD 생성
- AI가 공차, datum 또는 locked dimension을 임의로 완화하는 기능
- 임의 RhinoScript, C#, shell 또는 사용자 코드를 실행하는 공식 설계 경로
- 계정, 협업 권한, 서버 프로젝트 저장 또는 장기 artifact 보관
- 출력 PDF를 축척 기반 제작도면으로 사용하는 기능

## 6. 사용자

### Persona A — 메이커

- 브래킷, 전자 패널, 장착판을 제작하려 한다.
- 복잡한 CAD보다 치수를 입력해 즉시 제작파일을 받고 싶다.
- 성공 조건: DXF와 치수 리포트를 보고 제작소에 전달할 수 있다.

### Persona B — 공학 학습자

- datum, 공차, hole pattern과 제작 제약을 학습한다.
- 결과만 아니라 어떤 제약이 실패했는지 이해하고 싶다.
- 성공 조건: 요구값과 실제 측정값, 수정 이력을 비교할 수 있다.

### Persona C — MCP/CAD 고급 사용자

- Codex, Claude Code 또는 Cursor에서 설계를 자동화한다.
- 기존 Rhino/CAD MCP 생성 결과에 승인 게이트를 추가하고 싶다.
- 성공 조건: 구조화된 MCP 응답과 로컬 artifact bundle을 얻는다.

## 7. 핵심 사용자 흐름

### UC-01 폼 기반 신규 도면

1. 단위, datum, 플레이트 외곽과 제작 프로파일을 입력한다.
2. 홀·슬롯·cutout과 목표 치수·공차를 추가한다.
3. 시스템이 under/over constraint와 형상 오류를 검사한다.
4. 사용자가 contract를 확인하고 생성을 요청한다.
5. 시스템이 DXF를 생성하고 별도 verifier로 재측정한다.
6. 통과하면 DXF·SVG·PDF·verification JSON을 내려받는다.

### UC-02 자연어 보조 입력

1. 사용자가 “네 모서리에서 같은 거리로 M4 홀을 배치해줘”라고 입력한다.
2. 시스템이 해석 가능한 대칭·동일간격 제약과 미확정 수치를 보여준다.
3. 사용자가 누락된 edge offset과 hole diameter를 폼에서 확정한다.
4. 확인 전에는 공식 생성이나 export를 수행하지 않는다.

### UC-03 제한적 자동수정

1. verifier가 minimum edge distance 위반을 보고한다.
2. 시스템이 locked dimension을 제외하고 free parameter 후보를 찾는다.
3. 허용 범위의 변경안과 이유를 보여준다.
4. 최대 3회 재생성·재검증한다.
5. 해결되지 않으면 `infeasible` 또는 `failed_verification`으로 종료한다.

### UC-04 MCP 자동화

1. 에이전트가 `design_contract_draft`로 초안을 만든다.
2. `design_contract_validate` 결과가 `ready`인지 확인한다.
3. 생성·검증·export 도구를 순서대로 호출한다.
4. 모든 결과에서 같은 `contract_hash`와 evidence를 추적한다.

### UC-05 Rhino 교차검증

1. 검증된 DXF를 Rhino에 표시한다.
2. RhinoMCP `analyze_objects`로 bounding box와 주요 측정값을 얻는다.
3. 공식 verifier와 설정 허용차 이상 다르면 export를 중단하고 `cross_kernel_mismatch`를 보고한다.

## 8. 기능 요구사항

우선순위는 `P0=필수`, `P1=MVP 후반`, `P2=후속`이다.

| ID | 요구사항 | 우선순위 | 수용 기준 요약 |
|---|---|---:|---|
| DG-FR-001 | `DesignContract` 초안·생성 | P0 | 폼 값과 확인된 자연어 조건으로 versioned contract를 생성한다. |
| DG-FR-002 | 모호성 확인 | P0 | 숫자·단위·datum이 불명확하면 `needs_confirmation`을 반환하고 추정하지 않는다. |
| DG-FR-003 | 단위·datum 정규화 | P0 | 입력 단위를 mm, WCS XY와 명시적 origin/axis로 정규화하고 원본 단위를 보존한다. |
| DG-FR-004 | 외곽·feature·pattern | P0 | rectangle/polygon, hole, slot, rectangular cutout, linear/circular pattern을 지원한다. |
| DG-FR-005 | 치수·제약·locked/free | P0 | 목표값·공차·잠금·자유범위와 제약조건을 식별자로 관리한다. |
| DG-FR-006 | Contract 검증·상태 | P0 | `needs_confirmation`, `under_constrained`, `ready`, `infeasible`을 구분한다. |
| DG-FR-007 | Canonical geometry 생성 | P0 | 같은 contract에서 동일한 정규화 형상과 hash를 생성한다. |
| DG-FR-008 | DXF 레이어·XDATA 생성 | P0 | 고정 레이어와 feature ID XDATA를 포함한 DXF를 생성한다. |
| DG-FR-009 | 독립 DXF 재읽기·측정 | P0 | writer의 메모리 형상을 사용하지 않고 직렬화된 DXF를 다시 읽어 측정한다. |
| DG-FR-010 | 공차·공식 승인 게이트 | P0 | 모든 필수 검사가 통과하지 않으면 공식 bundle을 만들지 않는다. |
| DG-FR-011 | 제한적 수정 | P0 | free parameter만 범위 내 최대 3회 수정하고 locked 값 변경을 거부한다. |
| DG-FR-012 | 공식 산출물 bundle | P0 | 검증된 DXF·SVG·`DO NOT SCALE` PDF·verification JSON을 같은 hash로 제공한다. |
| DG-FR-013 | 웹 경험 | P0 | 구조화 폼, 자연어 보조, SVG 미리보기, IndexedDB draft를 제공한다. |
| DG-FR-014 | Stateless FastAPI | P1 | 계정·DB 없이 같은 요청이 같은 응답을 생성한다. |
| DG-FR-015 | MCP 도구 | P0 | 9개 공개 도구가 공통 envelope과 오류코드를 사용한다. |
| DG-FR-016 | Rhino 미리보기·교차검증 | P1 | Rhino 결과를 secondary evidence로 저장하고 불일치를 차단한다. |
| DG-FR-017 | 비교·버전·감사 hash | P1 | contract/artifact 버전 차이와 수정 이유를 추적한다. |
| DG-FR-018 | Benchmark·평가 | P0 | 100개 golden contract와 자연어 50개 평가를 실행한다. |

### 8.1 Architecture demo profile

Architecture profile은 기존 요구사항을 별도 제품으로 복제하지 않고 다음과 같이 구체화한다.

| 기존 요구사항 | Architecture 수용 기준 |
|---|---|
| DG-FR-003, DG-FR-005 | `ArchitecturalPlanContract`가 WCS XY datum, mm/inch, grid, wall, opening, column, room seed, dimension, constraint를 보존한다. |
| DG-FR-007~010 | 건축 DXF writer가 고정 layer와 XDATA를 기록하고, 별도 reader가 저장된 DXF에서 치수·폐합·연결·개구부·room·grid 정렬을 다시 판정한다. |
| DG-FR-012 | `passed`에서만 DXF·SVG·PDF·verification JSON bundle을 제공한다. |
| DG-FR-013 | `/`는 3-pane CAD workspace, drag, 100mm snap, Shift 10mm snap, exact property input, undo/redo, pan/zoom/Fit과 verification timeline을 제공한다. |
| DG-FR-014~015 | Architecture HTTP API와 동일 `design_kind` MCP dispatch가 stateless application service를 사용한다. |
| DG-FR-017 | Contract hash와 실제 serialized DXF artifact hash를 동시에 표시한다. |

Architecture MVP의 자동수정은 contract에 명시된 `column.center`와 `opening.offset` 자유 파라미터만 대상으로 한다. CP-SAT이 min/max/step 안의 값을 제안하고 최대 3회 다시 검증한다. Locked dimension, datum, wall endpoint·topology는 변경하지 않으며 각각 `DG_ARCH_REPAIR_LOCKED`, `DG_ARCH_REPAIR_NO_FREE_PARAMETER`, `DG_ARCH_REPAIR_EXHAUSTED`로 명시적으로 중단한다.

### 8.2 Plant / semiconductor piping profile

Piping profile은 기존 요구사항을 다음과 같이 구체화한다.

| 기존 요구사항 | Piping 수용 기준 |
|---|---|
| DG-FR-003, DG-FR-005 | `PipingPlanContract`가 WCS XY datum, node, straight segment, inline component, support, equipment/keepout zone, dimension과 constraint를 보존한다. |
| DG-FR-007~010 | Piping writer가 분야별 layer/XDATA를 기록하고 별도 reader가 route 연결·직교성·endpoint 정렬·component 위치·support spacing·equipment clearance를 저장된 DXF에서 다시 판정한다. |
| DG-FR-012 | 통과한 배관 route만 DXF·SVG·`DO NOT SCALE` PDF·verification JSON bundle을 제공한다. |
| DG-FR-013 | `/piping`은 3-pane workspace, valve drag/snap, exact offset input, preset, timeline과 evidence summary를 제공한다. |
| DG-FR-014~015 | Piping HTTP API와 `design_kind: piping_plan` MCP dispatch가 같은 stateless application service를 사용한다. |
| DG-FR-017 | Contract/DXF hash와 직렬화된 DXF에서 재측정한 route length, support gap, minimum clearance를 표시한다. |

Piping MVP는 geometry accuracy demo이며 유체·열응력·압력강하·재료·용접·배관 class/spec·support 구조강도·P&ID/법규 적합성을 판정하지 않는다. 자동수정 대신 exact numeric edit와 재검증을 사용한다.

## 9. 상태와 오류 원칙

### Contract 상태

- `draft`: 입력 중
- `needs_confirmation`: 필수 정보가 모호하거나 누락
- `under_constrained`: 자유도가 남아 공식 생성 불가
- `ready`: 생성 가능
- `infeasible`: locked constraint끼리 충돌

### Artifact 상태

- `generated_unverified`
- `passed`
- `failed_verification`
- `repair_exhausted`
- `cross_kernel_mismatch`

오류는 안정된 영문 code와 한국어 사용자 메시지를 함께 제공한다. 실패를 샘플 결과나 추정값으로 대체하지 않는다.

## 10. AI 안전 요구사항

- 자연어 원문에 없는 숫자, 단위, 좌표, 공차, 규격을 만들지 않는다.
- 변환된 모든 조건은 원문 evidence 또는 사용자 폼 필드 ID를 참조한다.
- 구조화 출력 스키마를 벗어난 응답은 저장하거나 실행하지 않는다.
- LLM 장애 시 폼 기반 설계·생성·검증은 계속 동작해야 한다.
- AI는 locked/free 분류를 변경할 수 없다.
- AI는 `passed` 상태를 만들 수 없고 verifier 결과만 승인 상태를 만든다.

## 11. UX 요구사항

주요 화면은 다음과 같다.

1. 설계 시작·샘플 선택
2. Datum·단위·제작 프로파일
3. 외곽·feature·치수 폼
4. 자연어 조건 보조와 확인 항목
5. SVG 미리보기와 제약 상태
6. 생성·검증 진행
7. 요구값/측정값/편차 결과표
8. 수정 이력과 export
9. Architecture object tree, native SVG plan canvas, exact property inspector
10. 독립 검증 timeline, room/area summary, contract/artifact hash

모든 좌표와 치수는 datum 기준 표현을 제공하고 색상만으로 pass/fail을 구분하지 않는다.

## 12. 성공 지표

| 지표 | MVP 목표 |
|---|---:|
| Locked dimension 자동 변경 | 0건 |
| DXF 재측정 편차 | 0.001mm 이하이며 사용자 공차 이내 |
| 동일 contract 결정론적 hash 재현률 | 100% |
| 미검증 공식 export | 0건 |
| Invalid/self-intersecting outline 검출률 | 100% |
| Artifact 간 feature ID 일치율 | 100% |
| Golden contract 실행 성공률 | 100/100 |
| 모호한 자연어 숫자 무단 추정 | 0건 |
| 샘플 생성·검증 시간 | 기준 환경에서 5초 이하 |

## 13. 비기능 요구사항

| ID | 분류 | 요구사항 |
|---|---|---|
| DG-NFR-001 | 정확성 | writer와 verifier는 별도 모듈·데이터 경로를 사용한다. |
| DG-NFR-002 | 재현성 | canonical JSON, code version, profile version으로 hash를 생성한다. |
| DG-NFR-003 | 추적성 | 측정·위반·수정·export를 contract와 artifact hash로 연결한다. |
| DG-NFR-004 | 보안 | 공식 경로에서 임의 코드·shell·CAD script 실행을 허용하지 않는다. |
| DG-NFR-005 | 개인정보 | MVP 서버는 사용자 계정이나 장기 프로젝트 데이터를 저장하지 않는다. |
| DG-NFR-006 | 성능 | 기준 도면은 5초 이내 생성·검증한다. |
| DG-NFR-007 | 이식성 | Docker backend와 최신 주요 브라우저에서 동작한다. |
| DG-NFR-008 | 접근성 | 키보드 입력과 텍스트 기반 오류 확인을 제공한다. |
| DG-NFR-009 | 장애 격리 | LLM/Rhino 장애가 결정론적 코어를 손상시키지 않는다. |
| DG-NFR-010 | 호환성 | DXF는 명시된 버전과 레이어/XDATA 계약을 따른다. |

## 14. 데이터와 평가

- Golden contract 100개: 단위 변환, 패턴, locked conflict, feature overlap, outline 외부 feature, tolerance 경계, 재현성 포함
- 자연어 평가 50개: 명확한 입력, 모호한 숫자, 단위 누락, 상충 조건, 금지된 추정 포함
- 모든 fixture는 합성 데이터이며 공개 재배포 가능해야 한다.
- 평가 리포트에는 통과율뿐 아니라 실패 contract와 violation을 공개한다.

## 15. MVP 완료 기준

1. 폼만으로 샘플 플레이트를 만들고 검증된 bundle을 받을 수 있다.
2. 자연어 보조가 모호한 수치를 확인 항목으로 보낸다.
3. 직렬화된 DXF를 독립적으로 재읽어 측정한다.
4. locked 값이 바뀌는 repair를 자동 거부한다.
5. 모든 violation이 constraint/feature ID와 실제·목표값을 포함한다.
6. 실패 artifact는 공식 export endpoint에서 거부된다.
7. 웹과 MCP가 같은 application service와 응답 envelope을 사용한다.
8. Rhino 불일치가 공식 verifier 결과를 덮어쓰지 않고 export를 차단한다.
9. 100개 golden contract와 자연어 50개 평가 결과가 공개된다.
10. Quick Start로 로컬 실행과 샘플 검증을 재현할 수 있다.
11. `/`의 architecture studio preset은 drag/snap 후 실제 API 검증을 통과하고, open-loop preset은 공식 export가 차단된다.
12. `/plate` deep-link에서 기존 plate workflow가 회귀 없이 동작한다.
13. `/piping` utility preset은 valve drag/snap 후 실제 DXF 재측정을 통과하고 승인 bundle을 제공한다.
14. Piping clearance failure preset은 관련 entity ID와 violation을 표시하고 공식 export를 차단한다.

## 16. 릴리스 순서

| 단계 | 결과 |
|---|---|
| M1 | Contract schema, 오류코드, golden fixtures |
| M2 | Canonical geometry, DXF writer, SVG/PDF preview |
| M3 | Independent verifier, tolerance gate, verification JSON |
| M4 | Bounded repair와 변경 이력 |
| M5 | Web UX와 stateless API |
| M6 | MCP 도구와 local artifact workspace |
| M7 | Rhino secondary adapter |
| M8 | Benchmark, Docker, 공개 release |

## 17. 위험과 대응

| 위험 | 대응 |
|---|---|
| 생성기와 verifier가 같은 오류를 공유 | 별도 모듈, DXF round trip, golden fixture로 검증 |
| 자연어가 수치를 왜곡 | 숫자·단위 evidence 강제, 미확정 상태 유지 |
| 자유 파라미터 수정이 요구 의도를 훼손 | 명시적 min/max, 최대 3회, 변경 diff 표시 |
| CAD별 측정 차이 | 공식 verifier 단일 기준, Rhino는 secondary evidence |
| 공정 프리셋을 표준으로 오해 | advisory 표시와 사용자 확인, 인증 비목표 명시 |
| 범용 CAD로 범위 팽창 | Architecture는 합성 2D 평면의 grid/wall/opening/column/room 검증 profile로 제한하고 BIM·구조해석은 제외 |
| Piping 도형 검증을 공정 안전으로 오해 | 2D route geometry, support 위치, clearance만 검증하고 해석·spec·법규·제작 승인은 명시적으로 제외 |

## 18. 확정 사항

- 별도 `datumguard` 프로젝트로 관리한다.
- 한국어 설명과 영문 식별자를 사용한다.
- 웹과 MCP를 병행한다.
- DXF를 공식 제작 artifact로 사용한다.
- 자연어보다 구조화 폼을 우선한다.
- 검증과 approval은 결정론적 코어만 수행한다.
- 로그인·DB·협업·3D 공식 검증은 MVP에서 제외한다.
- Architecture 공개 demo는 구조·안전·법규·산업표준 인증이 아니며 합성 fixture만 제공한다.

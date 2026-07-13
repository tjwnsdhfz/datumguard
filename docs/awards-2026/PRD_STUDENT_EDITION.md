# OpenBIM Evidence Guard - Student Design Edition PRD

- 문서 상태: 실행 기준 PRD
- 작성일: 2026-07-13
- 제품 목표일: 2026-08-23 code freeze
- 공모 마감: 2026-09-04
- 기준 제품: `virtual-fab-v1` 연구 prototype
- 대상 제품: 실제 대학 BIM studio 과제를 위한 제한형 로컬 검사 도구

## 1. 제품 판단

현재 버전은 제공된 Virtual FAB 합성 IFC·IDS를 사용하는 연구 시연에는 적합하다. 그러나 일반
Revit·Archicad 건축 IFC는 검사 대상이 0건이어도 전체 `passed`가 될 수 있어 자기 설계에 바로
사용할 수 없다. Student Design Edition의 첫 목표는 기능 수를 늘리는 것이 아니라 **검사하지 않은
모델을 통과로 보이지 않게 하고, 일반 건축 IFC의 IDS 정보검사를 안전하게 수행하는 것**이다.

### AS-IS

- baseline IFC, candidate IFC, IDS 세 파일이 모두 필수
- 공개 API profile은 `virtual-fab-v1` 하나만 허용
- 검사 대상은 FAB proxy, pipe, fitting, valve 중심
- `DG_Identity.AssetKey`와 `DG_VFabUtility.*` custom property 전제
- FAB Tool AABB geometry와 project revision 규칙이 항상 profile에 포함
- 공개 production에서는 OpenBIM capability 비활성

### 목표 MVP

> IFC4 건축 studio 모델 1개와 IDS 1.0 요구사항을 로컬에서 검사하고, 적용 객체 수·미지원 범위·
> 이슈·입력 hash를 명확히 보여 주는 학생용 evidence 도구

합성 Virtual FAB 연구 기능은 그대로 보존한다. 건축 studio 기능은 별도 profile과 mode로 추가하며,
FAB geometry를 범용화하지 않는다.

## 2. 목표와 비목표

### 목표

1. IFC·IDS 코드를 몰라도 sample로 5분 이내 첫 결과를 만든다.
2. candidate IFC 한 개만으로 첫 제출 전 정보요구검사를 실행한다.
3. 검사한 객체 수, 제외한 객체 수와 적용되지 않은 규칙을 실행 전에 표시한다.
4. 적용 대상이 0건이면 녹색 PASS 대신 `needs_confirmation` 또는 `not_applicable`로 표시한다.
5. JSON·HTML·manifest에 rule, entity, expected/actual과 입력 hash를 남긴다.
6. 최소 3개 실제 학생 IFC에서 별도 compatibility pilot을 완료한다.
7. 합성 실험과 실제 pilot 결과를 합산하지 않는다.

### 비목표

- 임의 IFC를 자동 이해하는 범용 profile 생성
- 구조안전·피난·법규·시공성·제작성 판정
- exact solid clash, 곡선·비직교 geometry
- IFC2x3·IFC4.3 동시 지원
- Revit·Archicad plug-in
- 3D viewer, 자동 수정, 계정, DB, 협업 서버
- AI 판정 또는 AI ground truth
- BCF를 Student MVP의 필수 산출물로 제공
- public production SaaS 운영

## 3. 사용자와 해야 할 일

| 사용자 | 해야 할 일 |
|---|---|
| BIM 모델 작성 학생 | 제출 전에 벽·슬래브·문·창·공간의 필수 속성, 분류와 containment 누락을 찾는다. |
| 팀 BIM 담당 학생 | 팀의 공통 IDS와 export checklist를 적용하고 결과 HTML을 보존한다. |
| 지도교수·튜터 | 저작도구 없이 HTML에서 적용 범위, 규칙, 객체, 기대값과 실제값을 검토한다. |

## 4. 핵심 사용자 흐름

### Flow A - Sample 학습

1. ‘Architecture Studio v1 sample’을 선택한다.
2. sample IFC와 IDS가 자동으로 준비된다.
3. preflight에서 전체·지원·적용·미지원 객체 수를 확인한다.
4. 검사를 실행하고 의도된 오류를 확인한다.
5. HTML·JSON·manifest를 내려받는다.

### Flow B - 자기 설계 첫 제출 검사

1. `Architecture Studio v1`을 선택한다.
2. 현재 IFC4와 기본 또는 수업용 IDS를 선택한다.
3. schema, 단위, 파일 크기, entity 종류와 IDS applicability coverage를 확인한다.
4. 적용 대상 0건 또는 미지원 비율이 높으면 경고를 읽고 실행 여부를 결정한다.
5. 검사 결과를 ‘수정 필요’, ‘사람 확인’, ‘적용 대상 아님’으로 구분해 확인한다.
6. authoring tool에서 수정·재export한 뒤 다시 실행한다.

### Flow C - Revision 비교

Revision 비교는 P1이다. P0가 안정된 뒤에만 제공한다.

1. 이전 제출 IFC와 현재 제출 IFC를 선택한다.
2. 공통·추가·삭제 객체 수와 GlobalId 매칭률을 확인한다.
3. 매칭률이 기준 이하이면 `ambiguous`로 표시하고 보호 변경 판정을 중단한다.
4. 지원되는 객체의 containment와 선택된 보호 필드 변경만 검토한다.

## 5. 기능 요구사항

| ID | 우선순위 | 요구사항 | 수용 기준 |
|---|---|---|---|
| STU-FR-001 | P0 | zero-coverage PASS 차단 | 전체 profile 대상과 IDS applicability가 0이면 전체 `passed`가 아니며 UI가 ‘검사 대상 없음’을 표시 |
| STU-FR-002 | P0 | 단일 모델 검사 mode | candidate IFC와 IDS만으로 실행되고 revision·FAB geometry는 `not_applicable` |
| STU-FR-003 | P0 | `architecture-studio-v1` 등록 profile | API allowlist와 UI에서 선택 가능하고 Virtual FAB profile은 변경 없이 유지 |
| STU-FR-004 | P0 | 건축 entity 지원 | 최소 `IfcWall`, `IfcSlab`, `IfcDoor`, `IfcWindow`, `IfcSpace`의 inventory와 IDS 결과를 표시 |
| STU-FR-005 | P0 | preflight coverage | schema, 단위, 파일 크기, 전체·지원·미지원 entity 수, IDS별 evaluated count를 실행 전에 표시 |
| STU-FR-006 | P0 | 기본 IDS template | 벽·문·공간의 최소 정보요구를 포함한 유효한 IDS 1.0 sample과 기대 PASS/FAIL fixture 제공 |
| STU-FR-007 | P0 | 사용자 IDS 안전 검사 | malformed IDS, DTD, external entity와 빈 specification을 명시적 입력 오류로 차단 |
| STU-FR-008 | P0 | 상태 분리 | `passed`, `failed`, `not_evaluable`, `ambiguous`, `not_applicable`을 서로 다른 의미로 표시 |
| STU-FR-009 | P0 | 추적 가능한 issue | 모든 issue에 rule ID, scope, severity, entity/STEP ID, field, expected, actual, source hash 포함 |
| STU-FR-010 | P0 | 기본 evidence export | BCF 없이 JSON, HTML, manifest를 저장하고 다시 열 수 있음 |
| STU-FR-011 | P0 | 로컬 실행 package | 새 Windows PC에서 한 개 PowerShell 명령으로 backend와 web을 실행하고 browser를 열 수 있음 |
| STU-FR-012 | P0 | 한국어 quickstart | 비전공 학생이 sample 결과를 5분 이내 생성하고 한 이슈를 authoring tool에서 찾음 |
| STU-FR-013 | P0 | 명시적 검사 경계 | 결과 화면과 export에 ‘검사함 / 검사하지 않음 / 사람이 판단함’을 표시 |
| STU-FR-014 | P1 | GlobalId revision inventory | baseline·candidate의 공통·추가·삭제 객체와 매칭률을 표시 |
| STU-FR-015 | P1 | revision 안전 gate | GlobalId 매칭률 80% 미만이면 protected change 판정을 `ambiguous`로 중단 |
| STU-FR-016 | P1 | 선택적 AssetKey mapping | 실제 template에서 안정 키를 export한 경우에만 `Pset.Property` 경로를 선택 |
| STU-FR-017 | P1 | 실제 학생 pilot dashboard | 모델별 tool/version, entity coverage, 오류 정확도, runtime과 실패 이유를 별도 CSV로 생성 |

P0 완료 전에는 P1, BCF, geometry 일반화와 UI polish를 시작하지 않는다.

## 6. 비기능 요구사항

| ID | 요구사항 | 수용 기준 |
|---|---|---|
| STU-NFR-001 | fail-closed | parser·worker·schema·IDS 실패를 성공으로 반환하지 않음 |
| STU-NFR-002 | 결정성 | 동일 입력 10회에서 timestamp·run ID 제외 canonical JSON 동일 |
| STU-NFR-003 | 성능 | 500개 이하 지원 entity의 reference laptop p95 30초 미만 |
| STU-NFR-004 | 입력 한도 | IFC 20 MiB, IDS 1 MiB 한도를 UI·API·문서에서 동일하게 표시 |
| STU-NFR-005 | 개인정보 | 로컬 실행 기본, 원본 IFC 영구 저장 없음, pilot은 동의·익명화 후 수행 |
| STU-NFR-006 | 접근성 | keyboard로 파일 선택·실행·다운로드 가능, status를 색상만으로 구분하지 않음 |
| STU-NFR-007 | 재현성 | dependency lock, profile version, input hash와 실행 환경을 manifest에 보존 |
| STU-NFR-008 | 경계 유지 | `research_validation_only=true`, `approval_eligible=false` 고정 |

## 7. 데이터·template

### 필수 repository 산출물

- `fixtures/openbim-student/architecture_studio_v1.ids`
- `fixtures/openbim-student/architecture_studio_profile.json`
- `fixtures/openbim-student/sample_clean.ifc`
- `fixtures/openbim-student/sample_faulty.ifc`
- `fixtures/openbim-student/sample_corrected.ifc`
- `docs/awards-2026/STUDENT_QUICKSTART.md`
- `docs/awards-2026/evidence/student_compatibility_manifest.json`
- 실제 model 파생 오류주입 manifest와 수동 ground truth

IDS 요구조건은 실제 확보한 학생 IFC의 entity·property inventory를 본 뒤 확정한다. 공식 property
set 이름을 근거 없이 먼저 가정하지 않는다.

### 실제 model metadata

- authoring tool·version과 IFC exporter version
- IFC schema와 파일 크기
- 전체 product·공간·지원 entity 수
- unit과 containment
- property set inventory
- revision pair가 있으면 GlobalId 유지율
- 익명화·사용 동의 기록

## 8. 실제 학생 model pilot

### 표본

- MVP 최소: 실제 학생 IFC4 3개, 서로 다른 project 2개 이상
- 권장 연구 표본: 건축 3개, MEP 2개, 통합 또는 자유형 1개로 총 6개
- 가능한 경우 authoring tool 2종 이상
- revision pair 최소 1쌍
- 모델당 지원 entity 50~500개, 파일 20 MiB 이하

실제 파일을 확보하지 못하면 ‘실제 학생 설계에 사용 가능’이라는 주장을 제거하고 합성 OpenBIM
교육 도구로 범위를 유지한다.

### 절차

1. 원본 복사본을 익명화하고 tool·export 정보를 기록한다.
2. model을 변경하지 않고 parser, entity, property, containment와 GlobalId inventory를 수행한다.
3. 학생·교수와 함께 필요한 IDS 5~8개를 확정한다.
4. 복사본에 필수 속성 제거, 허용값 오류, 분류 제거, containment 손실, GlobalId 중복을 주입한다.
5. detector와 분리된 manifest에서 모델당 최소 5개의 ground truth를 만든다.
6. clean, faulty, corrected control을 실행한다.
7. 동료 학생이 export부터 HTML 저장까지 수행하고 시간·도움 요청·실패 이유를 기록한다.

합성 `330/0/0`과 실제 pilot metric은 별도 표로 공개하고 합산 점수를 만들지 않는다.

## 9. 출시 gate

| 영역 | 최소 기준 |
|---|---|
| 안전한 판정 | 검사 대상 0건인데 전체 PASS인 사례 0건 |
| 입력 호환성 | MVP 실제 IFC 3/3에서 worker crash 없음 |
| 적용 범위 | 사용자가 지정한 대상 객체의 90% 이상이 evaluated count에 포함 |
| 오류 정확도 | 지원 범위 통제 오류 precision·recall 각각 0.90 이상 |
| clean 오탐 | 목표 0건. 발생 시 모델당 수와 원인을 모두 공개 |
| 추적성 | 이슈 95% 이상에 rule, entity/STEP, field, expected/actual 존재 |
| 결정성 | 동일 입력 canonical hash 3/3 이상 일치 |
| 성능 | 500개 이하 모델 p95 30초 미만 |
| 과제 성공 | 동료 학생 2명 모두 개발자 개입 없이 10분 내 sample HTML 생성 |
| 실패 설명 | 모든 미지원·판정불가 입력이 녹색 PASS가 아닌 명시적 상태 |

모든 gate를 통과하기 전 제품 상태는 ‘실제 학생 설계에서 검증됨’이 아니라
‘실제 학생 설계 pilot 진행 중’이다.

## 10. 일정과 cut rule

| 기간 | 필수 산출물 | 실패 시 cut |
|---|---|---|
| 7/13~7/16 | real IFC 확보, zero-coverage regression, entity/property inventory | real IFC가 없으면 실제 적용 주장 제거 |
| 7/17~7/23 | coverage gate, single-model mode, status contract | P1 revision 전부 연기 |
| 7/24~7/30 | Architecture Studio profile·IDS·sample | tool 1종 export만 지원 |
| 7/31~8/06 | preflight UI, JSON·HTML·manifest | UI polish 제거, text summary 유지 |
| 8/07~8/13 | 실제 IFC 3개 compatibility pilot | 실패 모델과 미지원 범위 공개 |
| 8/14~8/18 | 오류주입 평가, 결정성·성능, peer walkthrough | revision과 AssetKey mapping 제거 |
| 8/19~8/23 | code·data freeze, local dry-run, 전체 CI | 신규 기능 금지 |
| 8/24~8/30 | 설명서·결과표·quickstart 동결 | 실제 metric 미달 시 synthetic 결과와 분리 |
| 8/31~9/02 | 새 PC dry-run, 제출 파일 hash·backup | blocker만 수정 |
| 9/03~9/04 | 비상 buffer | 기능 추가 금지 |

예상 작업량은 P0 약 60~90시간, P1 포함 약 100~140시간이다. 한 명의 학생은 P0를 우선하고
revision, mapping UI와 표본 6개 확대는 시간이 남을 때만 수행한다.

## 11. 위험과 대응

| 위험 | 대응 |
|---|---|
| zero-coverage false PASS | 첫 회귀 test와 전체 status gate로 고정 |
| authoring tool마다 property가 다름 | 첫 release는 실제 확보한 한 export 경로만 지원 |
| GlobalId 유지율이 낮음 | matching coverage를 먼저 표시하고 revision은 `ambiguous` |
| 20 MiB·500 entity를 초과 | 수동 model subset export 절차를 문서화하고 자동 누락은 금지 |
| geometry 오판 | Studio profile에서 FAB geometry 완전 비활성 |
| BCF license·viewer 미해결 | JSON·HTML·manifest만 제공 |
| 합성·실제 성능 차이 | metric과 표를 분리하고 합산 금지 |
| 일정 부족 | P1 → UI polish 순서로 cut, P0 coverage와 pilot은 유지 |

## 12. 현재 code 재사용 범위

- IDS XSD 검사와 IfcTester 결과 정규화: `src/datumguard/openbim_rules.py`
- profile allowlist와 isolated worker: `src/datumguard/openbim_service.py`
- issue·rule·hash·artifact model: `src/datumguard/openbim_models.py`
- JSON·HTML·manifest export: `src/datumguard/openbim_reporting.py`
- upload·status·issue·download UI: `web/app/openbim-workspace.tsx`
- 합성 evaluation과 경계: `docs/awards-2026/RESULTS.md`,
  `docs/awards-2026/LIMITATIONS.md`

가장 중요한 제품 원칙은 `virtual-fab-v1`을 범용 건축 profile처럼 보이게 만드는 것이 아니다.
Studio profile을 별도로 만들고 geometry를 끄며, coverage가 없는 검사는 PASS로 계산하지 않는다.

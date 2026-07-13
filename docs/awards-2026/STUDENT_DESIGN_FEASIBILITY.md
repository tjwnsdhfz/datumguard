# 실제 학생 설계 적용 가능성 감사

- 감사일: 2026-07-13
- 대상: DatumGuard OpenBIM Evidence Guard
- 기준 commit: `4d4273a53a07b31dc81060b65ded543e973eaeb5`
- 방법: code·UI·test·동결 evidence 검토 + 최소 건축 IFC surrogate smoke
- 판정 경계: 실제 학생 model·사람 대상 사용성 실험을 수행한 결과가 아님

## 1. 최종 판정

현재 제품은 **통제된 Virtual FAB 연구·수업 실습에는 사용 가능**하지만, **건축 학생이 자기 설계
IFC를 그대로 올려 믿을 수 있는 종합 검토를 받는 도구로는 아직 사용 불가**다.

| 사용 상황 | 현재 판정 | 점수 |
|---|---|---:|
| 제공된 합성 IFC·IDS로 공모전 시연 | 사용 가능 | 5/5 |
| OpenBIM·IDS 교육 실습 | 사용 가능 | 4/5 |
| 제공된 MEP/FAB 속성 template을 쓴 설비 model | 지도자 동반 pilot 가능 | 3/5 |
| 학생이 만든 IDS로 일반 건축 model의 속성 검사 | 제한적 가능. coverage 수동 확인 필요 | 2/5 |
| 임의 Revit·Archicad 건축 IFC 즉시 종합검토 | 현재 사용 불가 | 1/5 |
| 설계·법규·구조·제작·시공 승인 | 사용 불가 | 0/5 |

공모전 제출 표현은 다음으로 고정한다.

> 본 연구는 통제된 합성 IFC에서 재현성과 결함 검출 가능성을 평가한 학생 연구 prototype이다.
> 일반 학생 설계 IFC에 대한 즉시 사용성과 생산성 향상은 아직 입증하지 않았으며, 프로젝트별
> IDS·속성 mapping과 실제 authoring-tool export pilot을 후속 검증으로 둔다.

## 2. 가장 중요한 발견: 검사 대상 0건의 녹색 PASS

일반 건축 model을 흉내 낸 최소 IFC4 surrogate를 만들어 진단했다. 이 파일은
`IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey` 구조와 `IfcWall` 1개를 포함한다.
실제 학생 작품이 아니므로 결과는 compatibility smoke로만 사용한다.

기본 `virtual_fab_v1.ids`와 고정 profile을 적용한 결과는 다음과 같았다.

```text
overall status: passed

IDS-01~06: evaluated_count=0, passed
IFC-03:     evaluated_count=0, passed
GEO-01:     evaluated_count=0, passed
REV-01~03:  evaluated_count=0, passed
issues:     0
```

실제로 검사된 건축 요소가 없는데 전체 결과가 `passed`였다. 이는 실제 학생 model 적용 전에
반드시 해결해야 하는 P0 결함이다.

### 원인

1. 등록 profile 대상은 `IfcBuildingElementProxy`, `IfcPipeSegment`, `IfcPipeFitting`,
   `IfcValve`다. 벽·슬래브·문·창·공간은 profile 대상이 아니다.
2. 기본 IDS의 specification applicability는 대상이 없어도 허용되도록 `minOccurs=0`이다.
3. IDS, containment, revision, geometry 결과는 issue가 없으면 `evaluated_count=0`이어도
   `PASSED`가 된다.
4. UI는 규칙이 몇 개 통과했는지 강조하지만 ‘profile 적용 객체 0건’을 별도 차단하지 않는다.

반대로 같은 벽 model에 `Pset_WallCommon.IsExternal`을 요구하는 사용자 IDS를 적용하면
`evaluated_count=1`, `issue_count=1`, `failed_verification`으로 정상 검출됐다. 따라서
IDS 실행 엔진 자체는 일반 건축 정보검사에 활용 가능하지만, 고정 profile과 전체 status 집계가
self-service 사용을 막고 있다.

## 3. 현재 실제로 작동하는 범위

### 입력·실행

- IFC4 baseline·candidate와 IDS 1.0 업로드
- IFC 각각 20 MiB, IDS 1 MiB, 합계 41 MiB 한도
- 확장자·빈 파일·크기·profile allowlist 검사
- native IFC·IDS 처리의 별도 worker 실행
- timeout과 worker 실패의 fail-closed 오류 반환

### 검사

- 업로드 IDS의 XSD 검사와 IfcTester 실행
- IFC schema instance, IfcProject, length unit, GlobalId 누락·중복
- profile 대상의 공간 containment
- `DG_Identity.AssetKey` 기반 공통 자산 revision
- FAB Tool·utility의 제한형 world AABB clearance
- geometry 누락·identity 모호성의 `not_evaluable`·`ambiguous` 처리

내부 schema audit은 `express_rules=False`이므로 완전한 hosted buildingSMART validation과
동일하다고 주장하지 않는다.

### evidence

- baseline·candidate·IDS·profile SHA-256
- rule별 status, evaluated count와 issue count
- issue의 entity GlobalId·STEP ID, field, expected, actual, location
- canonical JSON, HTML, manifest
- 조건부 BCF artifact

### UI

- 파일 선택·교체·크기 오류
- research boundary 동의
- rule matrix와 issue register
- 입력 hash 복사
- JSON·HTML·manifest 다운로드

## 4. template이 있으면 가능한 범위

학생이 다음 조건을 맞춘 MEP 또는 설비 model이라면 지도자 동반 pilot이 가능하다.

- IFC4, 파일 20 MiB 이하, product 500개 이하
- `IfcPipeSegment`, `IfcPipeFitting`, `IfcValve` 또는
  `ObjectType=FAB_TOOL` proxy
- `DG_Identity.AssetKey`, `DG_Identity.AssetTag`
- `DG_VFabUtility.UtilityType`, `SystemCode`, `Criticality`
- FAB Tool의 `DG_VFabClearance.ServiceSide`, `ServiceDepth`
- baseline·candidate 양쪽의 동일하고 유일한 AssetKey
- 직교 box 또는 AABB screening을 허용할 수 있는 geometry

일반 건축 model도 사용자 IDS로 벽·문·창·공간의 필수 속성, 분류, 이름, 유형, 재료,
화재등급처럼 IDS로 표현할 수 있는 정보는 검사할 수 있다. 그러나 현재 UI는 profile 선택이
비활성이고 공개 API는 등록된 `virtual-fab-v1`만 허용하므로 학생이 스스로 profile을 mapping하는
흐름은 없다.

## 5. 현재 지원하지 않거나 조용히 누락될 수 있는 범위

- 일반 건축 entity의 profile containment·revision·geometry
- 단일 IFC만 검사하는 first-submission mode
- IFC2x3, IFC4.3
- 20 MiB 초과 IFC와 500 product 초과 model
- 임의 회전, 곡선·오목 형상, exact solid clash
- 벽·문·창·공간의 법규·clearance
- profile 생성·편집 UI
- IDS 작성 wizard
- Revit·Archicad·BlenderBIM property mapping template
- 실제 학생 model compatibility evidence
- 공개 web에서의 OpenBIM engine 실행

Revision은 baseline과 candidate에 공통으로 존재하고 유일한 AssetKey를 가진 객체만 비교한다.
따라서 다음은 현재 revision 결과에서 조용히 빠질 수 있다.

- AssetKey가 없는 객체
- baseline에서 삭제된 객체
- candidate에 새로 추가된 객체
- AssetKey 자체가 바뀐 객체

이 누락은 ‘변경 없음’과 구분되어야 한다.

## 6. 실제 학생 적용 전 필수 개발 순서

1. 전체 profile 대상 또는 IDS applicability가 0건이면 `passed`를 금지한다.
2. candidate IFC + IDS만 받는 single-model mode를 추가한다.
3. `student-architecture-ifc4-v1` profile을 별도 등록한다.
4. 전체·지원·적용·미지원 객체 수와 규칙별 evaluated count를 preflight에 표시한다.
5. Studio profile에서는 FAB geometry와 FAB revision을 `not_applicable`로 끈다.
6. 실제 export를 바탕으로 건축 IDS와 property mapping template을 만든다.
7. Revision에 공통·추가·삭제 객체와 matching coverage를 추가한다.
8. local one-command package와 한국어 quickstart를 제공한다.
9. 실제 학생 IFC 최소 3개, 권장 6개로 pilot한다.

1~5가 완료되지 않으면 실제 학생 model을 대상으로 녹색 PASS를 제시하지 않는다.

## 7. 실제 학생 model pilot protocol

### 표본

- 건축 3개: 벽·슬래브·문·창·공간 중심
- MEP 2개: 배관·밸브·피팅 포함
- 통합 또는 자유형 1개
- 가능한 경우 authoring tool 2종 이상
- revision pair 최소 1쌍

MVP 일정이 빠듯하면 실제 IFC 3개를 최소 gate로 삼고, 6개는 후속 연구로 확장한다.

### 사전 준비

1. 원본 복사본을 익명화하고 학생의 사용 동의를 받는다.
2. authoring tool·version, exporter version, schema, 크기, product 수를 기록한다.
3. 학생이 기대하는 검사 대상 수를 IFC와 독립된 sheet에 먼저 센다.
4. model의 entity·property set·unit·containment·GlobalId inventory를 만든다.
5. 건축 model은 project IDS 5~8개를 학생·지도자와 합의한다.
6. MEP model은 제공된 property template로 AssetKey를 mapping한다.

### 평가 track

건축 track은 single-model IDS·IFC integrity만 평가한다. FAB revision·geometry는 제외하고,
학생이 지정한 대상 객체 수와 IDS `evaluated_count`를 대조한다.

MEP track은 baseline·candidate를 사용한다. AssetKey matching률, 보호 속성 변경, 직교 배치된
FAB Tool/utility clearance를 평가한다. 추가·삭제 객체는 구현 전까지 수동 truth로 별도 기록한다.

### 통제 오류와 사용 과제

각 model 복사본에 필수 속성 제거, 허용값 오류, 분류 제거, containment 손실, GlobalId 중복 등
5개 이상의 통제 오류를 넣는다. MEP는 무단 보호 속성 변경과 clearance 침범을 추가할 수 있다.
Ground truth 작성자와 결과 판독자를 분리한다.

학생은 IFC export, 파일·IDS 선택, 실행, authoring tool에서 이슈 객체 찾기, 수정·재export,
재실행을 직접 수행한다. 단계별 시간, 도움 요청 횟수, 실패 원인과 짧은 사용성 설문을 기록한다.

## 8. Pilot 합격 기준

| 영역 | 최소 기준 |
|---|---|
| 안전한 판정 | 검사 대상 0건인데 전체 PASS인 사례 0건 |
| 입력 호환성 | 최소 표본 3/3이 worker crash 없이 열림 |
| 적용 범위 | 사용자가 지정한 대상 객체의 90% 이상이 evaluated count에 포함 |
| 오류 정확도 | 실제 export 파생 통제 오류 precision·recall 각각 0.90 이상 |
| clean 오탐 | 목표 0건. 발생 시 model별 수와 원인을 공개 |
| revision | 비교 대상의 matching coverage를 100% 보고 |
| 추가·삭제 | 구현 후 label된 추가·삭제 객체 100% 보고 |
| 추적성 | issue 95% 이상에 rule, entity/STEP, field, expected/actual 존재 |
| 결정성 | 동일 입력 3회 canonical hash 3/3 일치 |
| 성능 | 500개 이하 지원 entity에서 p95 30초 미만 |
| 과제 성공 | 동료 학생 2명 모두 개발자 도움 없이 10분 내 sample HTML 생성 |
| 실패 설명 | 미지원·판정불가 입력을 녹색 PASS가 아닌 명시적 상태로 표시 |

## 9. 공모전에서의 사용 가능성 해석

### 지금 제출 가능한 주장

- 합성 IFC에서 동결 protocol과 held-out 오류주입 평가를 완료했다.
- IFC·IDS·project rule의 역할을 구분하고 hash 기반 evidence를 생성한다.
- 실제 학생 model에 적용하기 위한 compatibility 위험과 pilot gate를 정의했다.
- 무검사 통과 위험을 발견해 Student Edition의 P0 요구사항으로 반영했다.

### 실제 pilot 뒤에만 가능한 주장

- 실제 student authoring-tool IFC N개에서 crash 없이 실행했다.
- 지정 대상의 coverage와 통제 오류 precision·recall을 측정했다.
- 동료 학생이 개발자 도움 없이 정해진 시간 안에 결과를 만들었다.

### 금지할 주장

- 임의 학생 설계에 바로 사용 가능
- 건축 종합검토 완료
- 실제 model 정확도 100%
- 설계 품질·법규·안전·시공성 보증
- 시간 절감 또는 생산성 향상 입증

## 10. 근거 위치

- 고정 profile: `src/datumguard/openbim_models.py`
- IDS·integrity·revision·geometry: `src/datumguard/openbim_rules.py`
- API 입력·size·feature gate: `src/datumguard/api.py`
- UI upload·고정 profile·result: `web/app/openbim-workspace.tsx`
- 합성 dataset: `docs/awards-2026/DATASET_CARD.md`
- 합성 결과: `docs/awards-2026/RESULTS.md`
- 적용 한계: `docs/awards-2026/LIMITATIONS.md`

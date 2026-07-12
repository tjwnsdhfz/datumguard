# BIM Awards 2026 - OpenBIM Evidence Guard 연구 계획

- 작성 기준일: 2026-07-12
- 연구 유형: Design Science Research + 통제된 합성 오류주입 평가
- 출품 분야: 학생부 `Research`
- 연구 protocol 동결 목표: 2026-08-16
- 최종 실험 목표: 2026-08-20
- 패널 디자인·편집: 이 문서의 범위 밖
- 상태: 사전 연구계획 snapshot. 실제 결과와 deviation은 [RESULTS](RESULTS.md),
  [LIMITATIONS](LIMITATIONS.md)와 correction audit를 따른다.

> 실행 기록: 계획 일정보다 앞선 2026-07-12에 `protocol-v1`을 동결하고 held-out evaluation을
> 수행했다. BCF 독립 viewer gate는 미완료이므로 아래 확장 제목이 아니라 Core title을 유지한다.

## 1. 연구 제목

### Core working title

> **OpenBIM Evidence Guard: IDS 기반 가상 FAB Utility IFC의 정보요구조건 및 리비전
> 무결성 독립 재검증 연구**

### Hard gate 통과 후 확장 가능한 제목

> **OpenBIM Evidence Guard: IDS 기반 가상 FAB Utility IFC의 정보요구조건·형상 여유공간·
> 리비전 무결성 독립 재검증과 BCF 이슈 추적 연구**

Geometry와 BCF gate를 통과하기 전에는 확장 제목을 사용하지 않는다.

## 2. 연구 배경과 차별점

IDS 1.0은 IFC 객체, 분류, 재료, 속성, 값 등의 정보요구조건을 사람이 읽고 기계가 검사할 수 있게
정의한다. 그러나 IDS는 geometry 규칙을 다루지 않는다. BCF는 판정 엔진이 아니라 BIM 객체와 위치에
연결된 issue 전달·추적 형식이다.

이 연구는 세 표준·기술의 역할을 섞지 않고 다음 계층으로 분리한다.

1. `IFC_SCHEMA`: IFC 자체 schema, identity, 공간구조 검사
2. `IDS_REQUIREMENT`: 기계 판독 가능한 정보요구조건 검사
3. `PROJECT_GEOMETRY_RULE`: Virtual FAB용 제한형 clearance screening
4. `PROJECT_REVISION_RULE`: 프로젝트가 정한 identity·중요정보 변경 계약
5. `BCF`: 위 판정 결과를 전달하고 수정 상태를 추적하는 issue package

2025 학생 Research 최우수상은 BIM 상세설계 자동화와 정합성 검토 자동화 모듈이었다. 따라서 단순히
“IFC 오류를 찾는 웹앱”이라고 제시하지 않는다. 본 연구의 차별점은 다음 세 가지다.

- 저장된 IFC bytes를 독립 프로세스에서 다시 열고 input/output hash를 증거로 남긴다.
- 사전에 동결한 오류주입 protocol과 ground truth로 탐지 성능을 재현한다.
- IDS 정보 검사, 제한형 geometry, revision 계약의 추가 효과를 ablation으로 분리한다.

## 3. 연구 목적

가상의 소형 반도체 FAB Utility IFC 납품 상황을 만들고, 다음 질문에 답한다.

> IDS 정보요구검사, IFC artifact audit, 프로젝트별 clearance 검사, revision 보호를 결합한 독립
> 검증 파이프라인이 통제된 IFC 오류를 어느 정확도와 시간으로 검출하고, 각 오류를 수정 가능한
> 증거로 추적할 수 있는가?

이 연구는 실제 FAB 적합성, 구조안전, 법규, 시공성 또는 상용 BIM 검수 플랫폼 수준을 입증하려는
연구가 아니다.

## 4. 연구 방법론

연구는 Peffers 등의 Design Science Research Methodology 흐름을 따른다.

1. 문제 정의: 생성·export 성공과 실제 IFC 납품요건 충족은 동일하지 않다.
2. 목표 정의: 정보·공간·형상·revision 오류를 추적 가능한 evidence로 검출한다.
3. 설계·개발: OpenBIM Evidence Guard artifact를 구현한다.
4. 시연: 합성 Virtual FAB clean/faulty/corrected 모델에 적용한다.
5. 평가: 사전 정의한 오류 정답표에 대해 정확도·결정성·성능·추적성을 측정한다.
6. 전달: 코드, dataset, raw result, limitations와 공모전 설명서를 공개한다.

사람 대상 사용성 실험은 core 연구에서 제외한다. 사용자 본인의 수동 검토시간은 기록할 수 있지만
탐색적 참고값으로만 제시하고 산업 생산성 향상으로 일반화하지 않는다.

## 5. 표준과 프로젝트 계약의 경계

### IDS

- IDS 1.0의 공식 범위인 entity, classification, property, value, part-of 관계만 사용한다.
- geometry clearance를 IDS가 검사했다고 표현하지 않는다.
- IDS raw message와 연구의 normalized issue를 둘 다 보존한다.

### GlobalId

- 한 IFC 안에서 중복 GlobalId는 IFC identity 문제로 분류한다.
- revision 간 GlobalId 유지 여부는 보편 IFC 표준이 아니라 `virtual-fab-v1` 프로젝트 계약이다.
- 동일 자산 matching에는 `DG_Identity.AssetKey`를 우선 사용하고 GlobalId churn을 별도로 기록한다.

### Units

- IFC project length unit을 읽고 geometry 계산 전에 metre로 정규화한다.
- mm/m 등가 fixture에서 결과가 같아야 한다.

### BCF

- BCF는 issue 전달·상태 추적용이다.
- 정량 실험의 source of truth는 canonical `evidence.json`이다.
- BCF가 기술·license gate를 통과하지 못하면 연구 결과는 JSON/HTML로 유지하고 BCF 주장은 제거한다.

## 6. 연구질문과 사전 가설

| ID | 연구질문 | 사전 가설·목표 | 우선순위 |
|---|---|---|---|
| RQ1 | IDS가 Virtual FAB 정보오류를 얼마나 정확히 검출하는가? | H1: 정보오류 macro-F1 >= 0.95, clean false positive 0건 | Core |
| RQ2 | IDS 범위 밖의 AABB clearance가 어떤 추가 오류를 검출하는가? | H2: geometry F1 >= 0.95, ±1mm 경계테스트 100% 통과 | Geometry gate 조건부 |
| RQ3 | 승인된 변경은 허용하면서 identity·중요정보 훼손을 검출하는가? | H3: revision macro-F1 >= 0.95, authorized pair false positive 0건 | Core |
| RQ4 | 각 violation을 BCF issue로 보존하고 수정 후 닫을 수 있는가? | H4: semantic round-trip 100%, component reference 정확도 >= 0.99 | BCF gate 조건부 |
| RQ5 | 결과가 결정론적이고 학생 규모 모델에서 충분히 빠른가? | H5: 50개 이하 검사객체 p95 < 5초, canonical JSON hash 10/10 동일 | Core |

가설 미달은 연구 실패가 아니다. protocol을 결과에 맞춰 바꾸지 않고 실제 수치, 실패 사례, 원인을
보고하면 평가를 완료한 것으로 본다.

## 7. Virtual FAB 정보계약

### IFC4 객체 범위

- FAB Tool: `IfcBuildingElementProxy`, `ObjectType=FAB_TOOL`
- Utility: `IfcPipeSegment`, `IfcPipeFitting`, `IfcValve`
- Support: 제한형 `IfcBuildingElementProxy`, `ObjectType=UTILITY_SUPPORT`
- 공간구조: `IfcProject -> IfcSite -> IfcBuilding -> IfcBuildingStorey -> IfcSpace`

### 연구용 custom property sets

공식 buildingSMART property set과 혼동하지 않도록 `Pset_` 접두어를 사용하지 않는다.

- `DG_Identity`: `AssetKey`, `AssetTag`
- `DG_VFabUtility`: `UtilityType`, `SystemCode`, `Criticality`
- `DG_VFabClearance`: `ServiceSide`, `ServiceDepth`

모든 코드, 허용값, clearance는 교육용 가상 프로젝트 계약이며 산업 표준이라고 주장하지 않는다.

### Rule catalog 초안

| Rule ID | Scope | 요구사항 |
|---|---|---|
| IDS-01 | IDS_REQUIREMENT | `AssetTag` 필수, `VF-[A-Z]{2}-[0-9]{3}` 형식 |
| IDS-02 | IDS_REQUIREMENT | `UtilityType`은 `PCW, CDA, VAC, EXH` 중 하나 |
| IDS-03 | IDS_REQUIREMENT | `SystemCode` 필수 |
| IDS-04 | IDS_REQUIREMENT | 합성 분류체계 `DG-VFAB-2026` 관계 필수 |
| IDS-05 | IDS_REQUIREMENT | 검사 대상의 필수 property set·value 존재 |
| IDS-06 | IDS_REQUIREMENT | FAB Tool의 `ServiceSide`, `ServiceDepth` 존재 |
| IFC-01 | IFC_SCHEMA | `IfcProject` 1개, project unit 확인 |
| IFC-02 | IFC_SCHEMA | GlobalId가 비어 있지 않고 한 IFC 안에서 유일 |
| IFC-03 | IFC_SCHEMA | element가 필요한 공간 container에 포함 |
| GEO-01 | PROJECT_GEOMETRY_RULE | service envelope에 utility obstacle이 양의 깊이로 침범하지 않음 |
| REV-01 | PROJECT_REVISION_RULE | `AssetKey`가 중복되지 않음 |
| REV-02 | PROJECT_REVISION_RULE | 같은 AssetKey의 GlobalId churn은 승인 목록에 있어야 함 |
| REV-03 | PROJECT_REVISION_RULE | locked property의 valid-to-valid 변경은 승인 목록에 있어야 함 |

## 8. Clearance 정의

정밀 solid clash가 아닌 직교 모델용 보수적 screening으로 제한한다.

1. FAB Tool의 local bounding box를 계산한다.
2. `ServiceSide` 방향으로 `ServiceDepth=600mm`의 단방향 service envelope를 만든다.
3. IFC placement를 world coordinate로 변환한다.
4. obstacle의 world AABB와 service envelope를 비교한다.
5. positive overlap depth가 epsilon보다 크면 FAIL이다.
6. 정확한 boundary contact는 PASS다.
7. 회전은 0, 90, 180, 270도만 허용한다.
8. geometry가 없는 검사 대상은 PASS가 아니라 `NOT_EVALUABLE`이다.

필수 경계테스트:

- 기준면보다 1mm 외부: PASS
- 정확한 기준면: PASS
- 기준면보다 1mm 내부: FAIL
- mm와 m로 표현한 동일 배치: 동일 판정
- geometry 누락: `NOT_EVALUABLE`

## 9. 평가 dataset

실제 FAB·기업·보안 자료는 사용하지 않고 IFC4 합성 모델만 사용한다.

### Layout

- L1: 선형 Tool Bay, 약 32개 검사 객체
- L2: 분기형 Utility Rack, 약 40개 검사 객체
- L3: 밀집형 Crossover, 약 48개 검사 객체

### Pilot와 final evaluation

- Pilot: layout별 seed 2개, 총 6 case. 개발·오류수정용이며 최종 성능 집계에서 제외한다.
- Target evaluation: layout별 seed 10개, 총 30 case.
- Minimum viable evaluation: 일정이 밀리면 layout별 seed 4개, 총 12 held-out case를 하한으로 한다.
- 하한을 사용하면 표본 축소 사실과 넓어진 불확실성을 결과에 명시한다.

각 case는 다음 파일로 구성한다.

```text
v0_clean.ifc
v1_authorized.ifc
v1_faulty.ifc
v2_corrected.ifc
truth.json
mutation_manifest.json
```

### 오류주입

`v1_faulty` case마다 서로 다른 객체에 다음 11개 fault를 삽입한다.

| Fault | 설명 | 계열 |
|---|---|---|
| I01 | AssetTag 삭제 | Information |
| I02 | AssetTag 형식 훼손 | Information |
| I03 | 허용되지 않은 UtilityType | Information |
| I04 | SystemCode 삭제 | Information |
| I05 | classification 관계 삭제 | Information |
| I06 | 필수 공간 containment 삭제 | Information/Integrity |
| G01 | pipe segment를 service envelope 안으로 이동 | Geometry |
| G02 | valve 또는 fitting을 service envelope 안으로 이동 | Geometry |
| R01 | 두 IfcRoot에 같은 GlobalId 부여 | IFC Identity |
| R02 | 같은 AssetKey 객체의 GlobalId만 변경 | Revision |
| R03 | 같은 GlobalId의 locked property를 다른 유효값으로 무단 변경 | Revision |

Target 30 case면 injected event는 330개, minimum 12 case면 132개다. 최종 문서에는 실제로 실행한
개수만 기록한다.

## 10. 오류주입 통제

- 하나의 객체에 서로 다른 fault를 중첩하지 않는다.
- injector와 detector 모듈을 분리한다.
- ground truth는 detector 결과가 아니라 mutation manifest에서 생성한다.
- fault target 선택과 seed를 protocol에 기록한다.
- 생성된 IFC를 disk에 serialize한 뒤 새 프로세스에서 다시 열어 검사한다.
- 각 파일의 SHA-256과 mutation before/after를 기록한다.
- geometry fault가 의도하지 않은 다른 obstacle까지 침범하지 않는지 독립 oracle로 확인한다.
- R01을 제외한 fault 모델은 불필요한 schema error를 만들지 않는다.
- pilot seed를 보고 detector를 고칠 수 있지만 final evaluation seed는 protocol freeze 뒤에만 실행한다.

## 11. 비교 조건과 평가 단위

동일 evaluation case에 다음 ablation을 적용한다.

- A: IDS only
- B: IDS + IFC integrity
- C: IDS + IFC integrity + Geometry
- D: Full pipeline, 즉 C + Revision

BCF는 detector ablation이 아니라 D의 issue packaging 품질로 별도 평가한다.

### Ground-truth matching key

- 일반: `(case_id, rule_id, AssetKey 또는 GlobalId, field)`
- Clearance: `(case_id, rule_id, sorted GlobalId pair)`
- Revision: `(baseline_id, candidate_id, rule_id, AssetKey, field)`
- Duplicate GlobalId: GlobalId만으로 구분할 수 없으므로 IFC STEP entity id를 보조 key로 둔다.

하나의 원인에서 여러 IDS raw message가 발생하면 `rule_id + entity + requirement` 수준에서
deduplicate한 normalized alert를 평가한다. Schema validator의 저수준 message는 주 실험 지표와
분리한다.

## 12. 평가 지표

### Correctness

- rule별 TP, FP, FN
- Precision, Recall, F1
- fault 계열별 macro-F1
- 전체 micro-F1
- clean model의 false positive 수
- false positive가 한 건 이상 발생한 clean model 비율
- authorized revision false positive 수
- corrected model의 issue closure rate와 신규 issue 수

### Incremental contribution

- IDS only 대비 integrity 추가 recall
- IDS+integrity 대비 geometry 추가 recall
- geometry 포함 조건 대비 revision 추가 recall
- 동일 case의 paired recall delta

### Traceability

- issue의 source hash·rule ID·entity reference coverage
- BCF topic coverage
- BCF required-field completeness
- BCF schema parse와 library round-trip 성공률
- component reference 정확도

### Performance and determinism

- engine runtime median, IQR, p95
- web/network와 fixture 생성 시간은 engine runtime과 분리
- 첫 warm-up을 제외하고 모델당 10회 측정
- timestamp, run ID를 제외한 canonical JSON을 입력당 10회 생성
- canonical JSON SHA-256 동일 횟수

## 13. 통계 처리

Target 30 case를 실행한 경우 layout 비율을 유지하는 paired stratified bootstrap 10,000회로 다음의
95% confidence interval을 계산한다.

- Full pipeline과 IDS-only의 recall 차이
- fault 계열별 F1
- corrected issue closure rate

Minimum 12 case만 실행하면 동일 계산을 보조적으로 제공하되 표본이 작다는 사실과 interval 폭을 함께
보고한다. 합성 데이터이므로 실제 산업 오류 모집단에 대한 p-value 또는 일반화 주장을 하지 않는다.

## 14. BCF 평가

BCF gate를 통과하면 violation 하나당 topic 하나를 원칙으로 한다.

각 topic에 포함할 정보:

- `[rule_id]`가 포함된 title
- `Open` 또는 `Resolved` status
- scope와 severity
- expected와 actual
- 관련 IFC GlobalId
- geometry issue의 두 component와 가능한 경우 viewpoint/snapshot
- source IFC, IDS, profile SHA-256
- engine version과 Git commit
- corrected model hash와 resolution comment

중복 GlobalId는 BCF component reference만으로 두 객체를 고유하게 구분할 수 없으므로 STEP entity id를
설명에 넣고 한계를 보고한다. BCFZIP의 byte 동일성은 요구하지 않고 semantic round-trip을 평가한다.

## 15. 재현성 protocol

최종 evaluation 전에 `protocol.yaml`을 만들고 `protocol-v1` tag로 동결한다.

동결 항목:

- IFC version과 object profile
- IDS·rule ID·허용값
- clearance 값, epsilon, boundary policy
- layout와 pilot/evaluation seed
- fault 종류·개수·target selection
- matching key와 deduplication
- primary/secondary metric
- 목표치와 제외 기준
- bootstrap 방법
- dependency version

한 명령으로 다음이 생성돼야 한다.

```text
dataset -> mutation -> serialized IFC reopen -> validation -> evidence JSON/HTML/BCF
        -> per_case.csv -> metrics.csv -> bootstrap_summary.json -> panel_facts.json
```

추가 원칙:

- raw result 수동 편집 금지
- 결과표와 panel용 숫자는 script에서 생성
- commit, Python, OS, CPU, IfcOpenShell, IfcTester version 기록
- model, IDS, profile, truth, output hash 기록
- clean exemplar는 buildingSMART IFC Validation Service에서 외부 확인
- IDS는 공식 audit tool 또는 표준 schema로 외부 확인
- BCF는 schema parse·round-trip·독립 viewer spot check

## 16. 타당성 위협과 한계

- 합성 오류가 실제 authoring tool 오류보다 단순할 수 있다.
- 같은 개발자가 generator와 detector를 작성해 oracle leakage 위험이 있다.
- 세 layout만 사용하므로 형태 다양성이 낮다.
- AABB는 곡선·회전·오목 형상의 정확한 간섭을 표현하지 못한다.
- 직교 회전과 50개 이하 객체에만 검증된다.
- GlobalId persistence는 IFC 표준 자체가 아니라 project contract다.
- duplicate GlobalId는 BCF component reference가 모호하다.
- IfcTester 구현 결과가 다른 IDS checker와 완전히 같다고 단정할 수 없다.
- 실제 FAB 운영·보안·시공성·법규 적합성을 검증하지 않는다.
- 사용자 실험이 없으므로 실무 시간 절감이나 사용성을 입증하지 않는다.

완화책:

- pilot/evaluation seed 분리
- protocol freeze
- injector/detector 분리
- disk serialize 후 독립 reopen
- ablation
- official validator와 독립 BCF viewer 확인
- negative result와 정확한 assurance boundary 공개

## 17. 윤리·데이터·오픈소스·AI 고지

- 실제 반도체 FAB, 기업 도면, 보안·운영 데이터는 사용하지 않는다.
- `PCW`, `CDA` 등은 일반적인 가상 utility 분류로만 사용한다.
- clearance 값과 project code는 교육용 가정이다.
- code와 dataset license를 분리한다.
- IfcOpenShell, IfcTester, BCF library의 이름, version, URL, exact license, 수정 여부를 NOTICE에 기록한다.
- `bcf-client` 등 전이 의존성의 license는 배포 전에 별도 확인한다.
- Codex 사용 범위를 아이디어 정리, scaffolding, 코드·문서 검토 보조로 공개한다.
- rule, label, ground truth, test, raw result와 결론은 학생이 직접 검토했다고 기록한다.
- LLM은 정량 판정 실험에서 제외한다.
- 선택적 자연어 설명을 추가하더라도 판정 결과와 별도이며 연구 성능에 포함하지 않는다.

## 18. 연구 산출물

```text
docs/awards-2026/
  RESEARCH_PLAN.md
  DEVELOPMENT_PLAN.md
  protocol.yaml
  RULE_CATALOG.md
  DATASET_CARD.md
  RESULTS.md
  LIMITATIONS.md
  THIRD_PARTY_AND_AI_USE.md
  evidence/
    environment.json
    fixture_manifest.json
    raw_results.jsonl
    per_case.csv
    metrics.csv
    bootstrap_summary.json
    experiment_summary.json
    panel_facts.json
    reproduction.log
```

대표 IFC, IDS, BCFZIP은 `fixtures/openbim/`에 두고 evidence manifest에서 hash로 연결한다.

## 19. 완료조건

### Core research 완료

- IDS와 revision 검사가 serialized IFC를 새 프로세스에서 다시 열어 동작
- clean, faulty, authorized, corrected 통합 테스트 통과
- pilot와 evaluation seed 분리
- minimum 12개 이상의 held-out case 최종 실행
- fault-level truth와 raw result 고정
- Precision, Recall, F1, runtime, determinism 자동 계산
- ablation 결과와 실패 사례·한계 기록
- 한 명령 재현 성공

### Conditional research 완료

- Geometry gate 통과 시 AABB boundary/unit test와 geometry metric 완료
- BCF gate 통과 시 topic coverage, round-trip, independent viewer evidence 완료
- 해당 gate가 실패하면 관련 제목·연구질문·결론 제거

### 출품 전 연구 integrity 확인

- 목표값을 실제 성과로 잘못 표기하지 않았는가?
- pilot 결과를 final evaluation에 섞지 않았는가?
- failed case나 negative result를 삭제하지 않았는가?
- raw result와 표·설명서 숫자가 일치하는가?
- library·Codex 기여와 학생 본인 기여를 구분했는가?
- 산업 적합성·인증·안전 보장을 주장하지 않았는가?

## 20. 연구 일정

| 기간 | 연구 작업 |
|---|---|
| 7/12~7/15 | RQ, rule, object profile, protocol 초안 |
| 7/16~7/23 | generator, clean layout, IDS, pilot truth |
| 7/24~7/31 | information·integrity·geometry·revision detector |
| 8/01~8/07 | evidence ledger, report, BCF conditional test |
| 8/08~8/13 | pilot 6개 실행, 문제 수정, matching·metric 검토 |
| 8/14~8/16 | `protocol-v1` 동결, final seed 공개·생성 |
| 8/17~8/20 | final evaluation, bootstrap, runtime, determinism |
| 8/21~8/23 | 결과·한계·재현 bundle 동결 |
| 8/24~8/30 | 3쪽 연구 설명서와 출처·기여 고지 작성 |
| 8/31~9/02 | external validator, hash, submission evidence 확인 |
| 9/03~9/04 | 비상 버퍼; protocol·기능 변경 금지 |

## 21. 참고 자료

- [BIM Awards 2026 공식 페이지](https://event.buildingsmart.or.kr/Awards/2026)
- [BIM Awards 2026 운영지침 PDF](https://buildingsmart.or.kr/NewsFile/BIM%20AWARDS%202026%20%EA%B3%B5%EB%AA%A8%20%EB%B0%8F%20%EC%9A%B4%EC%98%81%20%EC%A7%80%EC%B9%A8_V1.66_2026.pdf)
- [BIM Awards 2025 공식 수상작](https://event.buildingsmart.or.kr/Awards/2025)
- [buildingSMART IDS](https://www.buildingsmart.org/standards/bsi-standards/information-delivery-specification-ids/)
- [buildingSMART BCF](https://info.buildingsmart.org/standards/bsi-standards/bim-collaboration-format/)
- [IfcRoot specification](https://ifc43-docs.standards.buildingsmart.org/IFC/RELEASE/IFC4x3/HTML/lexical/IfcRoot.htm)
- [IFC project units](https://ifc43-docs.standards.buildingsmart.org/IFC/RELEASE/IFC4x3/HTML/concepts/Project_Context/Project_Units/content.html)
- [IfcTester documentation](https://docs.ifcopenshell.org/ifctester.html)
- [buildingSMART IFC Validation Service](https://validate.buildingsmart.org/)
- [Peffers et al., A Design Science Research Methodology](https://scholar.cgu.edu/samir-chatterjee/wp-content/uploads/sites/6/2013/07/jmis-article.pdf)

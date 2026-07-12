# OpenBIM Evidence Guard 규칙 카탈로그

- 규칙 프로필: `virtual-fab-v1` 1.0.0
- IFC 범위: IFC4 합성 연구 모델
- 판정 경계: 연구용 검증이며 구조·안전·법규·제작·시공 승인이 아니다.

규칙의 `scope`는 표준 요구와 프로젝트 계약을 구분한다. IDS는 정보 요구만 담당하며 형상과
revision을 IDS 성과로 표현하지 않는다.

| Rule ID | Scope | 대상 | PASS 조건 | 대표 오류 |
|---|---|---|---|---|
| IDS-01 | `IDS_REQUIREMENT` | 검사 대상 전체 | `DG_Identity.AssetTag`가 있고 `VF-[A-Z]{2}-[0-9]{3}` 형식 | I01, I02 |
| IDS-02 | `IDS_REQUIREMENT` | Pipe/Fitting/Valve | `UtilityType`이 `PCW/CDA/VAC/EXH` 중 하나 | I03 |
| IDS-03 | `IDS_REQUIREMENT` | Pipe/Fitting/Valve | `SystemCode` 존재 | I04 |
| IDS-04 | `IDS_REQUIREMENT` | 검사 대상 전체 | `DG-VFAB-2026` 분류 관계 존재 | I05 |
| IDS-05 | `IDS_REQUIREMENT` | Pipe/Fitting/Valve | `Criticality`가 `HIGH/MEDIUM/LOW` 중 하나 | clean control |
| IDS-06 | `IDS_REQUIREMENT` | `ObjectType=FAB_TOOL` | `ServiceSide`, `ServiceDepth` 존재 | clean control |
| IFC-01 | `IFC_SCHEMA` | 모델 | IFC4, `IfcProject` 1개, metre 길이 단위 | structural control |
| IFC-02 | `IFC_SCHEMA` | `IfcRoot` | GlobalId가 비어 있지 않고 파일 안에서 유일 | R01 |
| IFC-03 | `IFC_SCHEMA` | 검사 대상 전체 | 요구된 `IfcSpace` 또는 `IfcBuildingStorey` containment | I06 |
| REV-01 | `PROJECT_REVISION_RULE` | 자산 | `DG_Identity.AssetKey`가 파일 안에서 유일 | identity control |
| REV-02 | `PROJECT_REVISION_RULE` | baseline/candidate pair | AssetKey가 같은 자산의 GlobalId가 유지되거나 승인됨 | R02 |
| REV-03 | `PROJECT_REVISION_RULE` | baseline/candidate pair | locked field 변경이 정확한 before/after 승인과 일치 | R03 |
| GEO-01 | `PROJECT_GEOMETRY_RULE` | FAB Tool/utility pair | tool service envelope와 obstacle AABB의 양의 중첩 없음 | G01, G02 |

## 공통 issue 필드

모든 정규화 issue는 다음을 보존한다.

- `rule_id`, `scope`, `severity`, `message`
- `entity_ids`, `step_ids`, `field`; 가능한 경우 `raw.asset_key`
- 쌍 규칙이면 정렬된 `entity_pair`
- `expected`, `actual`
- baseline, candidate, IDS, profile SHA-256
- geometry issue이면 가능한 world coordinate

엔진 정렬 키는 `(scope.value, rule_id, issue_key)`다. 실험 러너는 candidate IFC의 GlobalId와 STEP
entity id, 필요한 경우 `raw.asset_key`를 통해 AssetKey를 복원한다. 동일한 IDS 원인에서 여러 raw
message가 생기면 `(rule_id, AssetKey, canonical field)`로 평가용 중복을 제거하지만 raw IfcTester
결과는 별도 보존한다.

## Revision 승인 control

각 layout의 `L1/L2/L3-PS-001`에 대해
`DG_VFabUtility.SystemCode: SYS-PCW-A -> SYS-PCW-B`만 승인한다. 사유 문자열까지 fixture profile에
기록한다. `v1_authorized`는 이 protected change를 실제 수행해야 하며 false positive가 없어야 한다.

## Clearance 판정

- tool `ServiceSide` 방향으로 0.6m envelope를 만든다.
- IFC project unit을 metre로 정규화한 world AABB를 사용한다.
- 지원 회전은 0/90/180/270도다.
- overlap depth가 `1e-9m`보다 크면 FAIL, 경계 접촉은 PASS다.
- geometry가 없으면 PASS가 아니라 `NOT_EVALUABLE`이다.

이는 exact solid clash가 아니라 합성 직교 모델에 한정한 screening이다.

## 다중 scope 해석

하나의 mutation이 여러 의미 규칙에 노출될 수 있다. 예를 들어 AssetTag 삭제는 IDS 누락이면서
revision 관점의 locked-field 손실로 보고될 수 있고, duplicate GlobalId는 identity 오류이면서
revision matching ambiguity를 만들 수 있다. `truth.json`은 primary alert와
`admissible_secondary_issues`를 분리한다. secondary는 필수 TP가 아니지만 의미상 올바른 경우 FP로
계산하지 않는다.

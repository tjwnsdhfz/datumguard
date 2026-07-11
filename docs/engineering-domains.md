# DatumGuard Engineering Domains

DatumGuard는 하나의 범용 CAD 에이전트가 아니라, 설계 분야별 공개 contract와 독립 verifier를 같은 approval 원칙 아래 제공한다.

| 분야 | Web route | `design_kind` | 핵심 검증 |
|---|---|---|---|
| Architecture plan | `/` | `architectural_plan` | wall 폐합·연결, opening, grid/column, room, 치수·면적 |
| Plant / semiconductor utility piping | `/piping` | `piping_plan` | route 연결·직교성, nozzle/node 정렬, inline component, support spacing, equipment clearance |
| Mechanical / ship plate | `/plate` | plate 기본 contract | outline, hole/slot/cutout, edge distance, ligament, overlap, 치수·공차 |
| 3D solid part | `/solid` | `solid_part` | STEP shape validity, topology, bbox, hole/bore diameter와 axis center |
| Existing CAD artifact | `/intake` | `artifact_audit` | DXF·STEP·IFC unit, geometry/data structure, immutable hash와 revision difference |

## 공통 assurance pipeline

1. 사용자가 datum, 단위, 좌표, 치수와 공차를 구조화 contract로 확정한다.
2. 분야별 writer가 canonical geometry를 R2013 DXF 또는 STEP으로 직렬화한다.
3. 별도 verifier가 저장된 artifact byte를 다시 읽어 좌표·치수·topology와 제약을 재측정한다.
4. 모든 required check가 통과한 경우에만 공식 ZIP bundle을 만든다.
5. Web과 MCP는 같은 분야별 application service를 호출한다.

Writer의 Shapely/CadQuery geometry나 사용자 입력값을 실제 artifact 측정값으로 재사용하지 않는다. DXF는 `independent_serialized_dxf_remeasurement`, STEP은 `independent_step_reimport`를 summary source로 사용한다.

Artifact Lab은 이 approval pipeline과 구분된다. Contract 없는 외부 파일을 원본 hash로 잠그고 구조 evidence를 제공하지만 `approval_eligible`은 항상 false다.

## Plant / semiconductor piping MVP 범위

Piping mode는 반도체 fab utility와 플랜트 배관의 2D plan routing 정확성을 보여주는 공개 합성 예제다.

- Tie-in, equipment nozzle, elbow/junction, termination node
- Nominal diameter와 service code를 가진 straight pipe segment
- Valve, reducer, instrument 같은 inline component
- Guide, hanger, shoe 같은 support 위치
- Equipment footprint와 keepout/clearance zone
- Segment length, component offset, support spacing과 obstacle clearance
- Valid utility route와 의도적인 clearance failure preset

MVP는 유체해석, 압력강하, 열응력, 재질선정, 용접설계, P&ID consistency, 배관 class/spec, 구조 support sizing 또는 산업 규격 적합성을 판정하지 않는다.

## 포트폴리오에서 보여주는 공학 역량

- CAD command 성공 여부와 실제 artifact 정확성을 분리하는 검증 설계
- 분야별 schema를 통한 요구조건·datum·공차의 명시적 모델링
- DXF layer/XDATA 기반 traceability
- 통과/실패 fixture와 재현 가능한 evidence
- AI가 locked 값이나 안전 기준을 임의로 추정하지 못하게 하는 경계
- OpenCascade native kernel 격리와 실제 Rhino B-rep import로 확인한 CAD 상호운용성

DatumGuard의 `VERIFIED`는 contract에 적힌 기하학 조건과 직렬화된 DXF가 일치한다는 뜻이며, 제작 승인이나 안전 인증을 의미하지 않는다.

# Task 03 — Independent DXF Verifier and Approval Gate

## 먼저 읽기

공통 문서, Task 01~02 handoff와 writer 의존 그래프를 읽는다.

## 요구사항·선행조건

- DG-FR-009~010, DG-FR-012
- DG-NFR-001~003, DG-NFR-010
- Task 02 DXF fixture 생성 가능

## 목표

- Writer와 분리된 DXF reader/verifier package를 구현한다.
- DXF bytes/path를 재수입해 feature와 실제 치수를 재구성한다.
- 공차, containment, overlap, edge distance, ligament와 pattern spacing을 검사한다.
- Verification JSON, artifact hash와 공식 approval gate를 구현한다.
- Passed bundle에 DXF/SVG/PDF/contract/verification/manifest를 묶는다.

## 비목표

- Repair 또는 Rhino 교차검증
- Dimension text를 실제 치수로 신뢰하는 동작

## 변경 범위·금지

- dxf_verifier, approval/export service와 관련 테스트만 변경한다.
- Writer의 in-memory geometry import를 금지한다.
- `passed`가 아닌 결과의 공식 bundle 생성을 금지한다.

## 공개 동작

- 상태: `passed`, `failed_verification`, `repairable`
- 오류: `DG_DXF_READ_FAILED`, `DG_VERIFICATION_FAILED`, `DG_EXPORT_NOT_APPROVED`
- 측정은 target, actual, deviation, lower/upper tolerance, evidence entity를 포함한다.
- Approval은 contract/artifact hash, required violation 0개와 locked dimension 통과를 확인한다.

## 필수 테스트·명령

- Verifier package가 writer package를 import하지 않는 architecture test
- 0.001mm 안/밖 tolerance boundary
- 누락/변조 XDATA, 잘못된 units/layer, 이동된 hole, outline 밖 feature
- Unapproved export 거부와 passed bundle round trip
- Feature ID·hash·manifest 일치

## 완료 기준

- Serialized DXF만으로 expected measurement를 재현한다.
- Golden error를 정확한 violation ID로 보고한다.
- 미검증 공식 export가 0건이다.

## Handoff

Violation schema, approval API, repairable 판정 규칙과 테스트 결과를 Task 04에 전달한다. 동일 검사→수정→재검사는 최대 1회다.

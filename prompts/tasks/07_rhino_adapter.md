# Task 07 — Rhino Preview and Cross-check Adapter

## 먼저 읽기

공통 문서와 Task 01~06 handoff, 현재 `rhinomcp-main`의 공개 계약을 읽는다.

## 요구사항·선행조건

- DG-FR-016
- DG-NFR-004, DG-NFR-009~010
- 검증된 DXF와 MCP/API가 존재함

## 목표

- 검증된 DXF를 Rhino에서 미리보기 위한 제한형 adapter를 구현한다.
- 기존 RhinoMCP `analyze_objects`에서 validity, bounding box, 길이/면적 evidence를 읽는다.
- 공식 verifier와 Rhino 측정값을 비교하고 match/mismatch를 구조화한다.
- Rhino가 없을 때 core와 export 정책이 명확히 동작하게 한다.

## 비목표

- Rhino를 공식 verifier로 사용
- 자유 Rhino modeling, render 자동화
- RhinoScript/C# arbitrary execution 노출

## 변경 범위·금지

- DatumGuard rhino_adapter, 관련 MCP tool과 integration fixtures만 변경한다.
- 기존 `rhinomcp-main`을 수정하지 않는다.
- 검증 전 DXF를 Rhino 공식 흐름으로 보내지 않는다.

## 공개 동작

- Evidence는 `secondary=true`, source/tool/version을 포함한다.
- 차이가 `max(0.001mm, 해당 dimension tolerance)` 이상이면 `DG_CROSS_KERNEL_MISMATCH`다.
- Rhino unavailable은 core generate/verify를 실패시키지 않는다.
- 사용자가 Rhino cross-check를 요청한 실행은 mismatch/unavailable 정책을 manifest에 기록한다.

## 필수 테스트·명령

- Fake adapter 기반 absent, matching, mismatch, malformed response
- Object GUID/feature ID mapping
- Mismatch 시 export 차단 정책
- 실제 Rhino 연결 가능 환경에서는 하나의 sample smoke test; 불가능하면 정확한 blocker 기록

## 완료 기준

- Secondary evidence가 공식 verifier 결과와 분리된다.
- Mismatch가 조용히 무시되거나 자동 보정되지 않는다.
- 임의 execution surface가 추가되지 않는다.

## Handoff

지원 Rhino 버전, 연결 절차, fake/real test 결과와 release 제한을 Task 08에 전달한다. 동일 검사→수정→재검사는 최대 1회다.

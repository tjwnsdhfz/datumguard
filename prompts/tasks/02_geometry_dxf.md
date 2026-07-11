# Task 02 — Canonical Geometry and DXF

## 먼저 읽기

공통 문서와 Task 01 handoff를 읽고 기존 schema/API를 검사한다.

## 요구사항·선행조건

- DG-FR-004, DG-FR-007~008, DG-FR-012
- DG-NFR-002, DG-NFR-006~007, DG-NFR-010
- Task 01 contract·hash 테스트 통과

## 목표

- Rectangle/closed polygon outline과 hole, slot, rectangular cutout, linear/circular pattern의 canonical geometry를 구현한다.
- DXF R2013 writer와 고정 레이어/XDATA 계약을 구현한다.
- Canonical geometry에서 SVG 미리보기와 `DO NOT SCALE` PDF 초안을 만든다.
- 모든 artifact에 같은 feature ID와 contract hash를 기록한다.

## 비목표

- DXF를 다시 읽는 verifier
- Pass/fail, approval, repair
- 자유곡선과 3D 형상

## 변경 범위·금지

- Geometry, dxf_writer, preview exporter와 fixture/test만 변경한다.
- Writer 결과를 `passed`로 표시하거나 공식 approval을 생성하지 않는다.
- Feature type을 PRD 범위 밖으로 확장하지 않는다.

## 공개 동작

- Writer 결과 상태는 항상 `generated_unverified`다.
- DXF 레이어는 `OUTLINE`, `CUT`, `CENTER`, `DIM`, `CONSTRUCTION`, `META`다.
- XDATA app ID `DATUMGUARD`에 contract hash, feature ID/type, revision을 기록한다.
- Pattern count는 source를 포함한다.
- PDF는 `DO NOT SCALE`, 단위, datum, revision을 표시한다.

## 필수 테스트·명령

- Unit/property tests와 Ruff/mypy
- Golden fixture: rectangle, polygon, hole, rotated slot, rounded/zero-radius cutout, linear/circular pattern
- 다른 입력 순서에서도 geometry/DXF hash가 동일한지 확인
- DXF 파일 구조·units·layer·XDATA를 ezdxf로 smoke parse
- SVG/PDF/JSON의 feature ID 집합 일치

## 완료 기준

- 지원 feature의 deterministic DXF/SVG/PDF 초안이 생성된다.
- Invalid/self-intersecting geometry가 `DG_GEOMETRY_INVALID`로 실패한다.
- 어떤 writer API도 공식 export approval을 제공하지 않는다.

## Handoff

Writer 입력/출력, artifact 위치, entity mapping과 아직 검증되지 않은 제한을 Task 03에 전달한다. 동일 검사→수정→재검사는 최대 1회다.

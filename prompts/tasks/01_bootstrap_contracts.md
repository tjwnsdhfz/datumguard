# Task 01 — Bootstrap and Public Contracts

## 먼저 읽기

`prompts/MASTER.md`, `docs/PRD.md`, `docs/TRD.md`, `docs/prompt-design.md`와 현재 저장소 상태를 읽는다.

## 요구사항·선행조건

- DG-FR-001~006, DG-FR-017
- DG-NFR-002~005
- 선행 구현 없음

## 목표

- Python 3.12 backend package와 Next.js/TypeScript workspace를 초기화한다.
- Pydantic `DesignContract`와 관련 enum/response/error 타입을 구현한다.
- 동일 JSON Schema와 TypeScript type을 생성 또는 동기화한다.
- Unit/datum normalization, status validation, canonical hash를 구현한다.
- TRD의 유효한 contract와 envelope 예시를 fixture로 추가한다.

## 비목표

- Geometry, DXF, repair, web 화면, API/MCP transport 구현
- LLM provider 연결

## 변경 범위·금지

- Repository config, contract/compiler package, schema/fixtures와 관련 테스트만 변경한다.
- PRD/TRD의 공개 필드를 임의 변경하지 않는다.
- 모호한 값에 default 숫자를 삽입하지 않는다.

## 공개 동작

- Contract 상태: `draft`, `needs_confirmation`, `under_constrained`, `ready`, `infeasible`
- 오류: `DG_INPUT_INVALID`, `DG_UNIT_AMBIGUOUS`, `DG_DATUM_MISSING`, `DG_NEEDS_CONFIRMATION`, `DG_CONTRACT_UNDER_CONSTRAINED`, `DG_CONTRACT_INFEASIBLE`
- Canonical hash는 key/입력 순서에 독립적이고 0.001mm grid를 사용한다.
- Locked path와 free parameter path가 겹치면 contract를 거부한다.

## 필수 테스트·명령

- Python: `pytest`, `ruff check`, `mypy`
- TypeScript: typecheck와 schema fixture parse
- mm/inch 변환, datum 직교성, ID 중복, path 유효성, 상태 전이, canonical hash property test
- TRD JSON 예시를 실제 Pydantic과 JSON Schema로 검증

## 완료 기준

- Python/TypeScript가 같은 fixture를 수용·거부한다.
- 같은 contract의 hash 재현률이 100%다.
- 모호한 필수값이 `needs_confirmation`을 만든다.
- Geometry 없이도 contract test suite가 통과한다.

## Handoff

생성된 package 명령, schema 경로, public type 목록, 테스트 결과와 Task 02가 사용할 canonical contract API를 기록한다. 동일 검사→수정→재검사는 최대 1회다.

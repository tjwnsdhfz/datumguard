# Task 04 — Bounded Repair Engine

## 먼저 읽기

공통 문서와 Task 01~03 handoff, violation/approval 타입을 읽는다.

## 요구사항·선행조건

- DG-FR-005~006, DG-FR-011, DG-FR-017
- DG-NFR-002~004
- Verifier가 structured violation을 반환함

## 목표

- OR-Tools CP-SAT 기반 repair proposal과 apply service를 구현한다.
- 0.001mm integer grid에서 free parameter 범위와 required constraint를 모델링한다.
- 변경량과 변경 parameter 수를 최소화한다.
- Before/after, reason, constraint ID, iteration과 solver status를 audit history로 저장한다.

## 비목표

- Locked dimension·datum 수정
- Feature 삭제, topology 변경, 공차 완화
- LLM이 직접 parameter 값을 선택하는 동작

## 변경 범위·금지

- Repair/compare/audit 모듈과 관련 테스트만 변경한다.
- 명시된 free path 이외 값을 solver variable로 만들지 않는다.
- 3회를 넘는 반복이나 자동 fallback을 추가하지 않는다.

## 공개 동작

- `repair_propose`는 수정안과 예상 해결 violation을 반환한다.
- `repair_apply`는 새 revision/hash를 만들고 재생성·재검증 대상이 된다.
- 해가 없으면 `DG_CONTRACT_INFEASIBLE`, 3회 후 `DG_REPAIR_EXHAUSTED`다.
- `drawing_compare`는 dimension/feature/constraint/free parameter diff를 반환한다.

## 필수 테스트·명령

- Locked path property test 100% 불변
- Min/max/step 밖 proposal 0건
- 1회 성공, 3회 exhaustion, infeasible locked conflict
- 동일 violation에서 deterministic proposal
- Audit history hash와 before/after 일치

## 완료 기준

- 허용범위 내 수리 가능한 golden case가 pass한다.
- 불가능한 case는 요구조건을 완화하지 않고 종료한다.
- Approval service가 repair history를 검증한다.

## Handoff

Repair lifecycle, revision contract, UI에 표시할 diff와 남은 제약을 Task 05에 전달한다. 동일 검사→수정→재검사는 최대 1회다.

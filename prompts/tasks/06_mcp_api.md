# Task 06 — Stateless FastAPI and MCP

## 먼저 읽기

공통 문서와 Task 01~05 handoff, web API adapter와 core service를 읽는다.

## 요구사항·선행조건

- DG-FR-014~015, DG-FR-017
- DG-NFR-003~007, DG-NFR-009
- Application service가 transport 중립임

## 목표

- TRD의 `/api/v1` endpoint를 FastAPI로 구현한다.
- 동일 service를 호출하는 MCP Python SDK 서버와 9개 도구를 구현한다.
- HTTP/MCP가 같은 Pydantic request/response envelope과 `DG_*` error를 사용하게 한다.
- MCP local workspace artifact sandbox와 versioned run directory를 구현한다.

## 비목표

- 계정, DB, server-side project history
- Rhino adapter 구현
- Arbitrary code/shell tool

## 변경 범위·금지

- API/MCP transport, workspace sandbox, integration tests와 필요한 web real adapter만 변경한다.
- Core logic을 transport별로 복제하지 않는다.
- Workspace 밖 write와 path traversal을 허용하지 않는다.

## 공개 동작

- 도구: `design_contract_draft`, `design_contract_validate`, `drawing_generate`, `drawing_verify`, `repair_propose`, `repair_apply`, `drawing_compare`, `export_bundle`, `rhino_preview` placeholder capability status
- 모든 결과에 status, hashes, measurements, violations, evidence, error가 있다.
- 공개 API는 stateless하고 사용자 artifact를 영구 저장하지 않는다.
- Rhino tool은 adapter가 없으면 구조화된 unavailable 결과를 반환한다.

## 필수 테스트·명령

- FastAPI OpenAPI schema와 MCP tool schema snapshot
- 동일 fixture의 HTTP/MCP envelope parity
- Stateless 반복 결과와 hash 재현성
- Path traversal/symlink escape/invalid MIME-size cases
- LLM disabled core flow와 concurrent request smoke test

## 완료 기준

- Web이 실제 API로 E2E 통과한다.
- MCP client가 동일 샘플을 생성·검증·export한다.
- 공식 경로에 arbitrary execution 도구가 없다.

## Handoff

서비스 시작 명령, MCP 설정, workspace 정책과 Rhino adapter interface를 Task 07에 전달한다. 동일 검사→수정→재검사는 최대 1회다.

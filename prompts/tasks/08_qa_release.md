# Task 08 — QA, Benchmark and Public Release

## 먼저 읽기

공통 문서, Task 01~07 handoff, 전체 git diff와 실행 스크립트를 읽는다.

## 요구사항·선행조건

- DG-FR-001~018
- DG-NFR-001~010
- 앞선 단계의 공개 계약과 테스트가 존재함

## 목표

- Golden contract 100개와 자연어 fixture 50개를 완성한다.
- 전체 evaluation report, 실패 사례, 성능과 재현성 지표를 생성한다.
- Docker backend/MCP, web build, Quick Start, sample bundle과 공개 README를 완성한다.
- CI에서 contract→DXF→verify→repair→export와 HTTP/MCP/web 흐름을 검증한다.

## 비목표

- MVP 범위를 넘어선 feature 추가
- 실패 테스트를 삭제하거나 tolerance를 완화해 통과시키는 작업
- 실제 release publish, 외부 계정 생성 또는 유료 서비스 사용

## 변경 범위·금지

- QA/fixture/CI/Docker/docs/demo와 release metadata만 변경한다.
- 공개 schema의 breaking change를 하지 않는다. 필요하면 blocker로 보고한다.
- Rhino/LLM을 필수 CI dependency로 만들지 않는다.

## 필수 시나리오

- mm/inch round trip
- locked conflict와 locked repair 0건
- feature overlap/outside outline
- tolerance 경계 0.001mm 안/밖
- 같은 contract의 hash 재현성 100%
- 미검증 export 0건
- Repair 성공과 3회 exhaustion
- HTTP/MCP parity
- Web E2E
- Rhino absent/match/mismatch fake adapter
- 자연어 숫자 무단 생성 0건과 evidence reference 100%

## 필수 테스트·명령

- Backend lint/type/unit/property/golden/integration
- Frontend lint/type/unit/build/Playwright
- Docker build와 clean-environment smoke
- Benchmark runner와 machine/profile metadata
- 문서 링크, 요구사항 추적표, JSON/JSON Schema example validation

## 완료 기준

- PRD의 MVP 완료 기준이 모두 evidence와 연결된다.
- 100+50 fixture가 실행되고 report에 실패도 포함된다.
- Clone 후 문서만으로 15분 이내 sample bundle을 생성할 수 있다.
- Release artifact에 DXF/SVG/PDF/contract/verification/manifest가 있다.
- README가 제품 한계, DXF 제작 기준, `DO NOT SCALE`, 비인증 고지를 포함한다.

## Handoff

최종 구현 요구사항 ID, 테스트 결과, benchmark 지표, 알려진 한계와 release 명령을 기록한다. 실제 publish는 사용자 승인 후 별도 작업으로 남긴다. 동일 검사→수정→재검사는 최대 1회다.

# DatumGuard Development Prompt Index

각 프롬프트는 순서대로 실행하며 하나의 세션 또는 PR만 담당한다. 다음 단계는 선행 단계의 완료 기준과 handoff를 확인하기 전 시작하지 않는다.

| 순서 | Prompt | 요구사항 | 선행 산출물 | 완료 기준 |
|---:|---|---|---|---|
| 1 | [01_bootstrap_contracts](./tasks/01_bootstrap_contracts.md) | DG-FR-001~006, DG-FR-017 | 없음 | Schema, status, errors, canonical hash가 테스트됨 |
| 2 | [02_geometry_dxf](./tasks/02_geometry_dxf.md) | DG-FR-004, DG-FR-007~008, DG-FR-012 | 1 | Canonical geometry와 DXF/SVG/PDF 초안 생성 |
| 3 | [03_independent_verifier](./tasks/03_independent_verifier.md) | DG-FR-009~010, DG-FR-012 | 1~2 | DXF round-trip 측정과 approval gate 통과 |
| 4 | [04_repair_engine](./tasks/04_repair_engine.md) | DG-FR-005~006, DG-FR-011, DG-FR-017 | 1~3 | Locked 불변·최대 3회 repair가 검증됨 |
| 5 | [05_web_experience](./tasks/05_web_experience.md) | DG-FR-001~006, DG-FR-010, DG-FR-013 | 1~4 | 폼→미리보기→검증→export UX가 E2E 통과 |
| 6 | [06_mcp_api](./tasks/06_mcp_api.md) | DG-FR-014~015, DG-FR-017 | 1~5 | HTTP/MCP parity와 stateless 동작이 검증됨 |
| 7 | [07_rhino_adapter](./tasks/07_rhino_adapter.md) | DG-FR-016 | 1~6 | Rhino absent/match/mismatch 처리 완료 |
| 8 | [08_qa_release](./tasks/08_qa_release.md) | DG-FR-001~018, DG-NFR-001~010 | 1~7 | 100+50 benchmark, Docker, 문서, release 준비 완료 |

## 공통 입력

- [MASTER.md](./MASTER.md)
- [PRD](../docs/PRD.md)
- [TRD](../docs/TRD.md)
- [Prompt Design](../docs/prompt-design.md)
- 직전 작업의 handoff

## 의존성 규칙

- 공개 타입을 후속 단계에서 임의 변경하지 않는다.
- Breaking change가 필요하면 구현을 멈추고 PRD/TRD와 선행 테스트 영향도를 handoff에 기록한다.
- 프롬프트 간 중복 구현보다 기존 application service를 재사용한다.
- Rhino/LLM이 없어도 1~6단계 core와 benchmark는 실행 가능해야 한다.

## 요구사항 전체 추적표

| 요구사항 | 주 담당 Prompt |
|---|---|
| DG-FR-001 | 01, 05, 08 |
| DG-FR-002 | 01, 05, 08 |
| DG-FR-003 | 01, 08 |
| DG-FR-004 | 02, 08 |
| DG-FR-005 | 01, 04, 08 |
| DG-FR-006 | 01, 04, 08 |
| DG-FR-007 | 02, 08 |
| DG-FR-008 | 02, 08 |
| DG-FR-009 | 03, 08 |
| DG-FR-010 | 03, 05, 08 |
| DG-FR-011 | 04, 08 |
| DG-FR-012 | 02, 03, 08 |
| DG-FR-013 | 05, 08 |
| DG-FR-014 | 06, 08 |
| DG-FR-015 | 06, 08 |
| DG-FR-016 | 07, 08 |
| DG-FR-017 | 01, 04, 06, 08 |
| DG-FR-018 | 08 |

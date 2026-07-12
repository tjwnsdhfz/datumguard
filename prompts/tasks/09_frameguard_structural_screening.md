# Task 09 — FrameGuard structural screening

## 먼저 읽기

작업 전에 다음 문서를 끝까지 읽는다.

1. `docs/PRD.md`
2. `docs/TRD.md`
3. `docs/prompt-design.md`
4. `docs/frameguard.md`
5. `prompts/tasks/01_bootstrap_contracts.md`부터 `08_qa_release.md`까지의 handoff
6. 현재 `git status`, 관련 source/test/fixture, 최근 공개 API schema

문서와 코드가 충돌하면 임의로 의미를 바꾸지 말고 충돌을 handoff에 기록한다. 기존 plate,
architecture, piping, solid, artifact, OpenBIM 공개 계약을 깨지 않는다.

## 요구사항 ID와 선행조건

- 구현 대상: `DG-FRAME-FR-001`~`DG-FRAME-FR-010`
- 선행조건: 공통 Pydantic/hash/error envelope, FastAPI, MCP, 테스트 환경이 동작해야 한다.
- 기존 contract에서 `design_kind`가 없을 때 plate로 처리하는 하위 호환 규칙을 유지한다.
- 이 프롬프트는 한 작업 세션 또는 한 PR만 담당한다.

## 구현 목표

1. `StructuralFrameContract`와 공개 JSON Schema를 구현한다.
2. 명시된 node/member/load/support/limit reference와 수치 범위를 canonical validation한다.
3. 결정론적 2D 선형탄성 frame solver로 node displacement와 member demand를 계산한다.
4. caller가 선언한 displacement/stress limit으로 screening gate를 수행한다.
5. governing node/member, measurement, violation, evidence, timeline, SVG preview를 반환한다.
6. free section property만 대상으로 한 bounded repair proposal을 구현한다.
7. FastAPI와 MCP에 동일 application service를 연결한다.
8. 정상·실패 utility pipe-rack fixture와 회귀 테스트를 제공한다.

## 비목표

- 구조 안전 인증, 법규·코드 적합성, 제작·시공 승인
- 자동 하중 산정, 하중조합, safety factor 또는 재료 선택
- 3D, 비선형, 좌굴, 동적·내진·풍응답, 피로, 접합부·앵커·용접 설계
- LLM 또는 이미지에서 좌표·하중·단면·지지조건 추정
- GNN을 공식 판정기로 사용하거나 solver 결과를 AI 값으로 대체
- 임의 Python, RhinoScript, C#, shell 실행

## 변경 가능한 영역과 금지 작업

변경 가능:

- `src/datumguard/frame_models.py`
- `src/datumguard/frame_service.py` 및 분리된 frame solver/preview 모듈
- `src/datumguard/api.py`, `src/datumguard/mcp_server.py`의 최소 dispatch/route
- `fixtures/examples/frame_*.json`
- `tests/test_frame_*.py`
- FrameGuard 전용 web route/component/test와 관련 문서

금지:

- 기존 공개 field, route, MCP 도구를 삭제·rename하는 작업
- `design_kind`가 없는 입력의 기본 dispatch 변경
- locked member, topology, load, support, limit 자동수정
- solver 실패를 PASS로 변환하거나 disclaimer를 숨기는 작업
- 실제 정확도·안전성·OpenSees parity를 evidence 없이 주장하는 작업
- 관련 없는 사용자 변경을 정리하거나 되돌리는 작업

## 공개 타입과 API

### Python

- `StructuralFrameContract`
- `FrameContractValidationResponse`
- `FrameRunResponse`
- `validate_frame_contract(contract)`
- `run_frame_design(contract, auto_repair=False)`
- `propose_frame_repair(contract, ...)`

모든 공개 response는 최소한 다음 envelope를 유지한다.

```json
{
  "contract_hash": "sha256:...",
  "artifact_hash": "sha256:...",
  "status": "passed",
  "measurements": [],
  "violations": [],
  "evidence": [],
  "error": null
}
```

### HTTP

- `GET /api/v1/schema/frame-contract`
- `POST /api/v1/frame/contracts/validate`
- `POST /api/v1/frame/designs/run?auto_repair=false`

OpenAPI description과 endpoint docstring은 결과가 structural-safety certification이 아닌
engineering screening임을 명시한다.

### MCP

- `frame_analyze`
- `frame_repair_propose`

MCP response도 HTTP와 같은 canonical hash와 evidence 의미를 사용한다. generic contract
validation은 `design_kind="structural_frame"`을 인식하고, design kind가 없는 contract는 기존
plate 경로를 유지한다.

## 오류 동작

다음 조건은 stable `DG_FRAME_*` violation/error와 관련 entity ID를 반환한다.

- duplicate entity ID
- missing node/member reference
- zero-length member
- non-positive/invalid section or material property
- disconnected load path
- insufficient restraint 또는 singular stiffness matrix
- displacement limit exceedance
- stress limit exceedance
- forbidden/locked/undeclared repair path

Pydantic schema 위반은 기존 API exception handler 경계를 사용한다. 오류 메시지에 로컬 경로,
stack trace, 원본 민감 입력을 노출하지 않는다. infeasible 또는 solver failure를 PASS로
degrade하지 않는다.

## 필수 테스트

1. JSON Schema가 frame contract 공개 field와 `design_kind="structural_frame"`을 포함한다.
2. 같은 contract의 canonical hash와 solver 결과가 반복 실행에서 동일하다.
3. 정상 fixture는 expected PASS와 governing evidence를 반환한다.
4. 실패 fixture는 expected FAIL violation을 반환한다.
5. duplicate/missing reference/zero-length/invalid property를 validation 단계에서 차단한다.
6. singular/under-restrained frame이 PASS하지 않는다.
7. displacement와 stress limit 경계값을 테스트한다.
8. repair가 free `area_mm2`/`inertia_mm4` 경계와 step을 지키고 locked/topology/load/support를
   변경하지 않는다.
9. API schema/validate/run endpoint와 MCP tool listing/direct call을 테스트한다.
10. 기존 plate/architecture/piping API와 MCP 회귀 테스트가 통과한다.

## 실행 명령

저장소의 실제 package manager 명령을 우선 확인하고 다음 검사를 실행한다.

```bash
uv run ruff check src tests
uv run mypy src/datumguard
uv run pytest tests/test_frame_api.py tests/test_frame_mcp.py
uv run pytest
```

web을 변경한 경우 추가한다.

```bash
cd web
npm run lint
npm run typecheck
npm run build
npm run test:e2e
```

같은 검사→수정 반복은 최대 1회다. 그 뒤 남은 실패는 재현 명령, 첫 원인, 영향 범위를 handoff에
정확히 남긴다.

## 완료 기준

- 요구사항 `DG-FRAME-FR-001`~`010`이 code/test/doc evidence로 추적된다.
- PASS/FAIL fixture가 공개 API와 MCP에서 동일한 contract hash와 판정 의미를 갖는다.
- 응답에서 governing node/member와 측정값/limit를 재현할 수 있다.
- locked 또는 undeclared 변경이 0건이다.
- 모든 사용자 접점에 screening disclaimer가 보인다.
- 기존 공개 도구와 plate-default 하위 호환 테스트가 통과한다.
- 구현되지 않은 GNN/OpenSees/code compliance를 현재 기능처럼 표현하지 않는다.

## Handoff

마지막 응답에 다음을 기록한다.

- 변경 파일과 관련 요구사항 ID
- 실행한 명령, 통과/실패 수, 실행하지 못한 검사와 이유
- PASS/FAIL fixture의 contract/artifact hash와 governing evidence 요약
- solver assumption, numerical tolerance, known failure mode
- repair가 실제 변경한 경로와 locked 변경 0건 evidence
- 남은 위험과 다음 단계: OpenSees cross-check dataset, GNN surrogate, unseen-topology 평가,
  qualified-engineer review protocol

다음 단계도 deterministic solver를 정답으로 유지한다. AI는 triage와 후보 순위화만 담당하며,
solver 재검증 없이 최종 PASS를 만들지 않는다.

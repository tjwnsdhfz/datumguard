# Task 10 — FrameGuard Rhino/Grasshopper CAD bridge

## 먼저 읽기

작업 전에 다음 문서와 현재 repository 상태를 끝까지 읽는다.

1. `docs/PRD.md`, `docs/TRD.md`, `docs/prompt-design.md`
2. `docs/frameguard.md`, `docs/frameguard-rhino.md`
3. `prompts/tasks/09_frameguard_structural_screening.md`의 handoff
4. `StructuralFrameContract`, frame solver/service, FastAPI/MCP 공개 schema
5. 현재 `git status`, 관련 fixture/test와 사용자가 소유한 변경

문서와 코드가 충돌하면 값을 추정하거나 기존 변경을 되돌리지 말고, source-of-truth와 영향도를
handoff에 기록한다. 이 프롬프트는 한 작업 세션 또는 한 PR만 담당한다.

## 요구사항 ID와 선행조건

- 구현 대상: `DG-FRAME-FR-011`, `DG-FRAME-FR-012`, `DG-FRAME-FR-017`
- 선행조건: Task 09의 canonical frame contract와 exact solver가 반복 가능한 결과를 반환한다.
- Rhino가 없는 base runtime에서도 adapter schema, normalization, DXF writer/verifier가 동작해야 한다.

## 구현 목표

1. 직선 centerline, point support/load, section metadata를 전달하는 strict
   `RhinoFrameExchange 1.0.0`을 구현한다.
2. `mm`, `cm`, `m`, `in`, `ft`의 길이 차원을 mm/mm²/mm⁴로 변환하고 force N,
   stress/modulus MPa를 보존한다.
3. 오른손 직교 datum, World XY 평행성, `0.001 mm` out-of-plane/quantization 경계를 검증한다.
4. Rhino 8 Python 3 extractor와 Grasshopper Python component를 repository-owned integration
   script로 제공한다.
5. frame R2013/mm DXF writer와 writer memory를 공유하지 않는 re-open verifier를 구현한다.
6. exact solver와 DXF verifier가 모두 통과할 때만 download를 반환하는 CAD assurance service를 만든다.
7. HTTP schema/adapter/CAD route와 MCP `frame_rhino_adapt`, `frame_dxf_generate_verify`를 연결한다.

## 비목표

- Rhino를 official verifier 또는 구조 solver로 사용
- curve/polycurve/arc, 3D frame, distributed load, release, rigid offset 지원
- 단위·datum·section·support·load를 LLM이나 geometry에서 추정
- 임의 RhinoScript, C#, Python source, shell command 또는 사용자 지정 path 실행
- 좌표가 비슷하다는 이유로 node를 조용히 병합
- 구조 안전·법규·제작 적합성 승인

## 변경 가능한 영역과 금지 작업

변경 가능:

- `src/datumguard/frame_rhino_adapter.py`, `src/datumguard/frame_dxf.py`
- frame CAD application service와 최소 FastAPI/MCP dispatch
- `integrations/rhino/`, `integrations/grasshopper/`
- `fixtures/examples/frame_rhino_exchange.json`
- `tests/test_frame_rhino_adapter.py`, `tests/test_frame_dxf.py`, CAD API/MCP tests
- FrameGuard 전용 문서

금지:

- 기존 plate/architecture/piping/solid route·type·tool 삭제 또는 rename
- official solver ID나 공식 PASS source를 Rhino로 변경
- tolerance를 `0.001 mm`보다 느슨하게 변경
- DXF verifier에 writer의 in-memory geometry를 전달
- RhinoCommon을 base Python package import path에 추가
- 관련 없는 사용자 변경 정리·format·revert

## 공개 타입·API·MCP

- `RhinoFrameExchange`
- `RhinoFrameAdaptResponse`
- `FrameDxfVerificationResponse`
- `FrameCadAssuranceResponse`
- `adapt_rhino_frame_exchange(exchange)`
- `generate_frame_dxf(contract)` / `verify_frame_dxf(contract, serialized_bytes)`
- `run_frame_cad_assurance(contract)`

HTTP:

- `GET /api/v1/schema/rhino-frame-exchange`
- `POST /api/v1/frame/rhino/adapt`
- `POST /api/v1/frame/cad/run`

MCP:

- `frame_rhino_adapt`
- `frame_dxf_generate_verify`

Response는 canonical `contract_hash`, `artifact_hash`, `status`, `measurements`, `violations`,
`evidence`, `error` 의미를 유지한다. CAD download는 exact analysis와 reopened-DXF verification이
모두 passed일 때만 존재한다.

## 오류 동작

다음 조건은 stable `DG_FRAME_RHINO_*` 또는 `DG_FRAME_DXF_*` code로 fail-closed한다.

- unit unset/unknown → `needs_confirmation`; 추정 금지
- non-orthonormal/tilted datum, out-of-plane geometry
- straight line이 아닌 member, 누락·충돌 section metadata
- support/load가 명시 merge tolerance 안의 node와 만나지 않음
- 0.001mm quantization collision
- DXF version/INSUNITS/layer/XDATA/hash/datum/entity count 불일치
- endpoint/support/load 편차, Z deviation, duplicate centerline
- invalid serialized bytes

오류에 로컬 path, stack trace, 임의 script 내용 또는 전체 민감 payload를 노출하지 않는다.

## 필수 테스트와 실행 명령

1. 모든 지원 unit의 scale과 area/inertia/moment 길이 차원을 검증한다.
2. unit unset/unknown, tilted/nonorthogonal datum, `0.001 mm` plane boundary를 검증한다.
3. 입력 순서가 node ID/contract hash를 바꾸지 않는지 검사한다.
4. 명시되지 않은 node merge와 quantization collision을 차단한다.
5. 생성 DXF가 R2013/mm, 정확한 layer/XDATA, deterministic bytes를 갖는지 검사한다.
6. endpoint, datum, INSUNITS, XDATA, hash, version, duplicate geometry 변조를 각각 차단한다.
7. exact FAIL이면 DXF download가 없고, exact+DXF PASS일 때만 download가 있는지 검사한다.
8. HTTP schema/adapter/CAD와 두 MCP tool의 contract를 검사한다.

```bash
uv run --extra dev pytest \
  tests/test_frame_rhino_adapter.py tests/test_frame_dxf.py \
  tests/test_frame_cad_service.py tests/test_frame_assurance_api.py tests/test_frame_mcp.py
uv run --extra dev ruff check \
  src/datumguard/frame_rhino_adapter.py src/datumguard/frame_dxf.py \
  src/datumguard/frame_cad_service.py tests/test_frame_rhino_adapter.py tests/test_frame_dxf.py
uv run --extra dev mypy --config-file pyproject.toml src/datumguard
```

Rhino가 실제로 열려 있고 workspace의 Cordyceps MCP가 연결된 경우에만 Rhino/Grasshopper
interactive smoke를 수행한다. 연결되지 않았다는 이유로 core test를 건너뛰거나 fake evidence를
만들지 않는다. 같은 검사→수정 반복은 최대 1회다.

## 완료 기준

- `DG-FRAME-FR-011`, `012`, `017`이 schema/code/test/doc에 추적된다.
- 지원 unit과 datum 변환이 명시적이고 `0.001 mm` gate가 변조를 차단한다.
- Rhino/GH 없이도 neutral exchange와 DXF round-trip test가 통과한다.
- exact solver와 DXF verifier 중 하나라도 실패한 응답에 download가 없다.
- 기존 API/MCP와 base Docker가 RhinoCommon에 의존하지 않는다.

## Handoff

- 변경 파일과 requirement ID
- 실행한 명령, 통과/실패 수와 실행하지 못한 실제 Rhino smoke 이유
- mm/inch fixture의 input→normalized 값과 contract/artifact hash
- 변조별 violation code와 download 차단 evidence
- Rhino/GH script 실행 조건, allowlist와 남은 CAD 범위
- 다음 Task 11이 사용할 public types와 exact solver/DXF approval boundary

# Task 11 — FrameGuard OpenSees/PyG research validation and release gate

## 먼저 읽기

작업 전에 다음 자료와 현재 repository 상태를 끝까지 읽는다.

1. `docs/PRD.md`, `docs/TRD.md`, `docs/prompt-design.md`
2. `docs/frameguard.md`, `docs/frameguard-opensees.md`, `docs/frameguard-gnn.md`
3. Task 09~10 handoff와 frame exact solver/CAD assurance source
4. `src/datumguard/data/frame_opensees_parity.json`
5. `src/datumguard/data/frame_gnn_benchmark.json` 및 portable model artifact
6. 현재 `git status`, CI/deployment workflow와 public route 상태

수치는 prose에서 복사해 재창작하지 않고 versioned JSON을 source of truth로 사용한다. 이 프롬프트는
한 작업 세션 또는 한 PR만 담당한다.

## 요구사항 ID와 선행조건

- 구현 대상: `DG-FRAME-FR-013`~`DG-FRAME-FR-018`
- 선행조건: Task 09 exact solver와 Task 10 DXF re-open gate가 통과한다.
- official solver와 learned surrogate의 status/type/API boundary가 분리되어 있어야 한다.

## 구현 목표

1. genuine `openseespy==3.8.0.0`, engine 3.8의 2D `elasticBeamColumn` adapter를 구현한다.
2. displacement, rotation, reaction, signed local force, stress, utilization과 global equilibrium을
   공식 solver와 비교한다.
3. cantilever, portal, 2/3/4-bay rack, 의도된 failure fixture의 6-case parity report를 만든다.
4. exact solver label의 90-case dataset을 2/3-bay train/validation과 4-bay test로 분리한다.
5. 실제 PyTorch Geometric GraphSAGE/GAT 3-seed ensemble을 같은 split으로 학습·비교한다.
6. validation-only uncertainty/calibration과 train-only OOD bounds로 `REVIEW_REQUIRED`를 구현한다.
7. 선택한 GraphSAGE를 NumPy portable artifact로 export하고 PyG inference parity를 검증한다.
8. API benchmark/surrogate route, MCP evidence/prediction tool, 선택형 research CI와 production
   smoke 기대값을 연결한다.

## 비목표

- OpenSees를 production official solver로 교체
- surrogate가 `PASS`, `approved`, `safe` 또는 code-compliant를 반환
- test partition으로 threshold, normalization, architecture 또는 seed를 선택
- synthetic pipe-rack 결과를 실제 공장·플랜트·조선 구조물에 일반화
- base Docker에 Torch, PyG 또는 OpenSeesPy를 포함
- evidence 없이 release/deployment 완료, 범용 FEA parity 또는 구조 안전성을 주장

## 변경 가능한 영역과 금지 작업

변경 가능:

- `frame_opensees.py`, `frame_gnn.py`, `frame_surrogate.py`, dataset/evidence loader
- benchmark/training CLI, package data JSON과 research artifact
- focused test, API/MCP 최소 route/tool, `/frame` evidence UI
- 선택형 `.github/workflows/frame-research.yml`, deployment smoke와 FrameGuard 문서

금지:

- exact solver measurement/status를 surrogate 값으로 덮어쓰기
- unavailable OpenSees를 PASSED로 변환
- 실패/불확실 예측을 clipping하여 PREDICTED로 만들기
- metric 일부만 골라 “최고 모델”이라고 주장
- base dependency/Docker에 optional research runtime 포함
- 원격 Vercel/Render smoke 전 “배포 완료” 표기
- 관련 없는 사용자 변경 정리·revert

## 공개 타입·API·MCP

OpenSees:

- `probe_opensees()`
- `solve_frame_opensees(contract)`
- `run_opensees_parity_benchmark()`
- `load_packaged_parity_report()`

PyG/surrogate:

- GraphSAGE/GAT train/evaluate/export functions
- `predict_frame_surrogate(contract, model_path=None)`
- status는 `PREDICTED` 또는 `REVIEW_REQUIRED`
- 항상 `authoritative=false`, `exact_solver_required=true`

HTTP:

- `POST /api/v1/frame/surrogate/predict`
- `GET /api/v1/frame/benchmarks/opensees`
- `GET /api/v1/frame/benchmarks/gnn`

MCP:

- `frame_surrogate_predict`
- `frame_opensees_parity_evidence`

현재 MCP 전체 surface는 기존 14개 + 위 CAD/research 전용 4개를 합한 18개다.

## 오류와 uncertainty 동작

- OpenSees import 불가: `UNAVAILABLE`/`SKIPPED`; PASS로 간주하지 않음
- OpenSees analysis error, entity 누락, sign/status/equilibrium/tolerance mismatch: `FAILED`
- model file 누락/손상/schema/hash 불일치: `REVIEW_REQUIRED`
- invalid contract/reference: `REVIEW_REQUIRED`
- train-only feature/count range 밖: `DG_FRAME_SURROGATE_OOD` + `REVIEW_REQUIRED`
- validation threshold 초과: `DG_FRAME_SURROGATE_HIGH_UNCERTAINTY` + `REVIEW_REQUIRED`

`PREDICTED`도 official PASS가 아니며 exact solver와 DXF verifier 실행 필요성을 항상 포함한다.

## 필수 테스트와 실행 명령

1. genuine OpenSees import/version과 cantilever displacement/reaction/local-force sign을 검사한다.
2. 입력 순서와 무관한 deterministic tag mapping을 확인한다.
3. 고의 mismatch, solver exception, unavailable runtime이 fail-closed하는지 검사한다.
4. 6-case suite가 요구 사례를 모두 포함하고 failure fixture는 두 solver 모두 FAIL인지 확인한다.
5. PyG `Data`/`Batch`, GraphSAGE/GAT forward와 topology split leakage 0을 검사한다.
6. 90-case benchmark의 train/validation/test count와 unclipped metric을 JSON에 기록한다.
7. NumPy GraphSAGE가 2/3/4-bay parity case에서 PyG와 `1e-4` 이내인지 검사한다.
8. missing/corrupt/OOD/high-uncertainty가 모두 `REVIEW_REQUIRED`인지 검사한다.
9. API/MCP가 packaged evidence를 research dependency 없이 조회하고 surrogate가 authoritative
   approval을 반환하지 않는지 검사한다.

Research environment:

```bash
uv sync --extra dev --extra ml --frozen
uv pip install openseespy==3.8.0.0
uv run --no-sync pytest \
  tests/test_frame_opensees.py tests/test_frame_gnn.py tests/test_frame_surrogate.py \
  tests/test_frame_rhino_adapter.py tests/test_frame_dxf.py tests/test_frame_assurance_api.py
uv run --no-sync python tools/run_frame_opensees_parity.py --no-package-copy
```

작은 CI training/inference parity smoke는 최소 30 cases, 2 seeds, 소수 epoch와 temporary output을
사용한다. release benchmark를 갱신할 때만 90 cases, 3 seeds와 versioned output을 사용한다. 같은
검사→수정 반복은 최대 1회다.

## 완료 기준

- genuine OpenSeesPy 3.8 보고서가 required 6 cases를 실행하고 6/6 PASSED다.
- PyG 보고서가 90 cases, 48/12/30 split, ID/hash leakage 0과 GraphSAGE/GAT 실제 metric을 보존한다.
- 불확실·OOD·invalid artifact는 `REVIEW_REQUIRED`, surrogate authoritative PASS는 0건이다.
- portable GraphSAGE와 PyG parity가 `1e-4` 안이며 base Docker에는 Torch가 없다.
- `/frame`과 assurance API는 Vercel/Render smoke 전까지 unreleased로 표시된다.
- merge 후 같은 release SHA의 web route, domain, exact solver canary, CORS와 health가 통과해야만
  deployment 완료로 handoff한다.

## Handoff

- 변경 파일과 `DG-FRAME-FR-013`~`018` 추적
- OpenSees package/engine/runtime과 6-case 결과·최대 오차·equilibrium evidence
- dataset seed/split/leakage와 GraphSAGE/GAT 전체 test metric
- uncertainty/OOD threshold의 validation provenance와 REVIEW_REQUIRED 사례
- portable artifact SHA-256와 PyG/NumPy 최대 parity error
- base Docker dependency separation evidence
- 로컬 CI와 원격 PR/Vercel/Render smoke의 실제 상태; 실행하지 않은 항목은 완료로 표시하지 않음

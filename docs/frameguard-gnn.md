# FrameGuard PyG surrogate 비교 및 안전 게이트

## 1. 목적과 판정 경계

이 실험은 결정론적 `datumguard_numpy_2d_frame_v1` solver가 생성한 결과를 빠르게
근사하는 연구용 surrogate다. GraphSAGE 또는 GAT의 출력은 구조 안전 승인, 설계기준
적합 판정, 공식 `PASS`의 근거가 아니다.

- surrogate 결과는 `PREDICTED` 또는 `REVIEW_REQUIRED`만 반환한다.
- 두 상태 모두 `authoritative=false`, `exact_solver_required=true`다.
- 공식 구조 screening은 기존 결정론적 solver가 계속 담당한다.
- 모델 파일 누락, 손상, 잘못된 입력, OOD, 높은 불확실성은 모두
  `REVIEW_REQUIRED`로 fail-closed 처리한다.

## 2. 데이터와 graph 표현

학습 label은 `generate_frame_dataset`이 매 case마다 `solve_frame`을 호출해 만든다.
contract hash, case ID, topology 이름은 누출 검사와 추적에만 사용하며 모델 feature에
포함하지 않는다. 각 실제 member는 양방향 directed edge 두 개로 표현한다.

### Node features

| 순서 | 이름 | 의미·단위 |
|---:|---|---|
| 0 | `x_mm` | node X 좌표, mm |
| 1 | `y_mm` | node Y 좌표, mm |
| 2 | `restraint_ux` | X translation 구속, 0/1 |
| 3 | `restraint_uy` | Y translation 구속, 0/1 |
| 4 | `restraint_rz` | Z rotation 구속, 0/1 |
| 5 | `fx_n` | 합산 X nodal load, N |
| 6 | `fy_n` | 합산 Y nodal load, N |
| 7 | `mz_nmm` | 합산 nodal moment, N·mm |

### Edge features

| 순서 | 이름 | 의미·단위 |
|---:|---|---|
| 0 | `length_mm` | member 길이, mm |
| 1 | `direction_x` | 방향 cosine X |
| 2 | `direction_y` | 방향 cosine Y |
| 3 | `area_mm2` | 단면적, mm² |
| 4 | `inertia_mm4` | 단면 2차 모멘트, mm⁴ |
| 5 | `elastic_modulus_mpa` | 탄성계수, MPa |
| 6 | `section_depth_mm` | 단면 깊이, mm |
| 7 | `allowable_stress_mpa` | 허용응력, MPa |

모든 normalization 통계는 train partition에서만 계산한다. 두 target
`max_displacement_mm`, `max_utilization`에는 `log1p`를 적용한 뒤 train 평균과
표준편차로 정규화한다.

## 3. PyTorch Geometric 모델

`frame_gnn.py`는 record를 실제 `torch_geometric.data.Data`로 변환하고, mini-batch는
`torch_geometric.data.Batch`로 구성한다.

- GraphSAGE: edge encoder의 target-node mean context와 두 개의 `SAGEConv`
- GAT: 동일한 edge context에 `edge_dim`을 사용하는 두 개의 `GATConv`
- pooling: graph별 global mean
- head: hidden linear + two-target linear
- uncertainty: seed 7, 17, 29의 deep ensemble 표준편차

GraphSAGE를 배포 모델로 선택한 이유는 test score 우승이 아니라, 그 message-passing을
작은 NumPy runtime으로 정확히 재현할 수 있기 때문이다. GAT는 연구 비교 모델로만
남는다.

## 4. 누출 없는 split

실제 benchmark는 solver-labeled 90 cases를 사용했다.

- train: 2/3-bay 48 cases
- validation: 2/3-bay stratified 12 cases
- test: 완전히 holdout한 4-bay 30 cases
- contract hash leakage: 0
- case ID leakage: 0
- validation threshold 계산에 test 사용: false

validation이 train과 topology 이름을 공유하는 것은 hyperparameter/threshold 보정을 위한
것이다. 일반화 성능은 학습에서 한 번도 보지 않은 4-bay group에서만 보고한다.

## 5. 실제 2026-07-12 CPU benchmark

환경은 Python 3.12.11, PyTorch 2.13.0 CPU, PyTorch Geometric 2.8.0이다. 아래 값은
clip하거나 유리한 seed만 선택하지 않은 3-seed ensemble의 4-bay test 결과다.

| Model | displacement MAE | displacement R² | utilization MAE | utilization R² |
|---|---:|---:|---:|---:|
| GraphSAGE ensemble | 0.6274 mm | 0.8049 | 0.03718 | 0.7327 |
| GAT ensemble | 0.6512 mm | 0.7924 | 0.02944 | 0.8065 |

GraphSAGE의 90% conformal interval test coverage는 displacement 96.7%, utilization
90.0%였다. 이 수치는 synthetic pipe-rack family 안의 결과일 뿐 실제 구조물 성능을
증명하지 않는다. 또한 validation sample이 12개로 작으므로 calibration 자체의 불확실성도
크다.

이 표의 source of truth는 배포 wheel에 포함되는
`src/datumguard/data/frame_gnn_benchmark.json`이다. 전체 seed별 결과, interval width,
validation calibration은 같은 JSON과 연구 mirror `artifacts/models/frame-gnn/benchmark.json`에
원본 숫자로 보존한다.

## 6. 불확실성과 OOD 게이트

deep ensemble의 물리 단위 표준편차를 예측값 대비 상대 score로 변환한다. threshold는
validation score의 95 percentile인 `0.1114220214`로 고정되며 test 결과로 조정하지
않았다. 90% residual/std 비율도 validation에서만 구해 예측 interval multiplier로
사용한다.

OOD는 train-only feature min/max에 10% margin을 둔 명시적 bounds와 node/directed-edge
count bounds를 함께 검사한다. 하나라도 벗어나면 예측값은 참고로 제공할 수 있지만 상태는
`REVIEW_REQUIRED`다.

| 조건 | review code |
|---|---|
| 모델 파일 없음 | `DG_FRAME_SURROGATE_MODEL_MISSING` |
| 모델 schema/weight 손상 | `DG_FRAME_SURROGATE_MODEL_INVALID` |
| node/member 참조 또는 수치 오류 | `DG_FRAME_SURROGATE_INVALID_INPUT` |
| 학습 feature/count 범위 이탈 | `DG_FRAME_SURROGATE_OOD` |
| ensemble 상대 불확실성 초과 | `DG_FRAME_SURROGATE_HIGH_UNCERTAINTY` |

`PREDICTED` 역시 안전 판정이 아니다. UI/API는 이를 `PASS`로 변환해서는 안 된다.

## 7. 경량 배포 artifact

학습에는 optional dependency group `ml`이 필요하지만, 배포 추론은 NumPy만 사용한다.

- wheel 포함 모델: `src/datumguard/data/frame_graphsage_ensemble_v1.json`
- wheel 포함 benchmark evidence: `src/datumguard/data/frame_gnn_benchmark.json`
- 연구 원본: `artifacts/models/frame-gnn/`
- public function: `predict_frame_surrogate(contract, model_path=None)`

3개 topology parity case에서 PyG와 NumPy의 최대 절대 오차는 각각
`3.16e-7`, `7.42e-8`, `1.71e-7`이며 허용값 `1e-4`보다 작았다. 이 검사는 모델
정확도가 아니라 두 inference kernel이 같은 계산을 한다는 증거다.

## 8. 재현 명령

ML 환경은 base runtime과 분리한다.

```powershell
uv venv C:\tmp\datumguard-venv-ml --python 3.12
uv pip install --python C:\tmp\datumguard-venv-ml\Scripts\python.exe --link-mode copy -e ".[ml]"
uv pip install --python C:\tmp\datumguard-venv-ml\Scripts\python.exe pytest

C:\tmp\datumguard-venv-ml\Scripts\python.exe tools\train_frame_gnn.py `
  --cases 90 `
  --epochs 120 `
  --hidden-channels 24 `
  --model-seeds 7 17 29

C:\tmp\datumguard-venv-ml\Scripts\python.exe -m pytest `
  tests\test_frame_gnn.py tests\test_frame_surrogate.py -q
```

## 9. 다음 연구 범위

- Rhino/현장 형상의 다양한 topology와 단면 family를 별도 external dataset으로 평가
- 여러 load case, distributed load, buckling/nonlinear label 지원
- calibration dataset 확대와 conformal coverage 재검증
- 실제 OpenSees parity failure case를 active-learning corpus에 편입
- model/data version별 drift 감시

이 범위를 완료하기 전에는 현재 수치를 실제 공장·플랜트 구조물 성능으로 일반화해서는
안 된다.

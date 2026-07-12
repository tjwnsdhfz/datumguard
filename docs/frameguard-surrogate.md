# FrameGuard surrogate 연구 기반

## 목적과 경계

이 문서는 최초 ridge baseline을 보존하는 역사적 연구 기록이다. `frame_dataset.py`와 이 문서의
모델은 **GNN이 아니다**. graph를 pooled global feature로 축약한 뒤 두 연속값을 예측하는 순수
NumPy ridge regression baseline이다. 후속 실제 PyTorch Geometric GraphSAGE/GAT 구현과 90-case
benchmark는 [FrameGuard PyG Benchmark](frameguard-gnn.md)를 따른다.

이 모듈은 `solve_frame`의 정확 해석 결과를 학습 데이터로 변환해 후속 graph neural
network 실험과 비교할 기준을 만든다.

이 경로는 DatumGuard의 API, MCP, 공식 PASS/FAIL 판정에 연결되지 않는다. 예측값은 안전
인증, 구조 검토서 또는 production inference로 사용할 수 없다. 공식 label과 현재 제품의
screening 판정자는 계속 `datumguard_numpy_2d_frame_v1` 정확 해석기다.

## 합성 데이터

`frame_dataset.py`는 seed로 재현 가능한 2층 pipe-rack/portal frame을 생성한다.

- topology family: `pipe_rack_2_bay`, `pipe_rack_3_bay`, `pipe_rack_4_bay`
- 변형 변수: bay span, level height, nodal load, area, inertia, elastic modulus,
  section depth, allowable stress, displacement limit
- 단위: mm, N, MPa
- label source: `solve_frame`
- singular candidate: record에서 제외하고 `excluded_singular`와 `attempted_cases`에 기록

각 graph record는 다음 정보를 포함한다.

| Field | 내용 |
|---|---|
| `case_id` | seed 기반 결정적 사례 ID |
| `topology_group` | bay 수로 정의한 holdout group |
| `node_features` | `x`, `y`, `ux/uy/rz restraint`, `fx/fy/mz` |
| `edge_index` | 양방향 message passing용 source/target index |
| `edge_features` | length, XY direction, `A`, `I`, `E`, depth, allowable stress |
| `targets` | max displacement, max utilization, governing member, screening result |
| `solver_id` | 정확 label source 식별자 |
| `contract_hash` | 검증된 원본 `StructuralFrameContract` hash |

좌표와 단면 정보는 원 단위를 보존한다. 실제 학습 전 정규화는 train partition의 통계만
사용해야 한다.

## Leakage 방지

무작위 case split을 사용하지 않는다. 한 `topology_group` 전체를 test로 holdout하여 train과
test가 같은 bay family를 공유하지 않게 한다. 출력의 `leakage_group_count`는 항상 0이어야
하며, 0이 아니면 split 생성 자체가 실패한다.

이 분리는 같은 topology의 치수만 바뀐 사례가 양쪽 partition에 들어가 성능이 과대평가되는
문제를 줄인다. 다만 2/3/4-bay 세 family만으로 임의 구조에 대한 일반화를 주장할 수는 없다.

## NumPy ridge baseline

baseline은 node와 member graph를 다음과 같은 global statistic으로 pooling한다.

- node/member 수와 frame extents
- restraint 수와 합산 nodal load
- member length, area, inertia, modulus, depth, allowable stress 통계
- 합산 axial/bending stiffness proxy

train 통계로 feature를 표준화하고 intercept를 제외한 항에 ridge penalty를 적용한다. 해는
NumPy `pinv`의 closed form으로 계산한다. 출력 target은 다음 두 개다.

1. `max_displacement_mm`
2. `max_utilization`

MAE와 R²는 threshold를 통과시키기 위해 clipping하거나 재작성하지 않는다. test target의
분산이 0이라 R²가 정의되지 않는 경우에만 finite reporting을 위해 0.0으로 기록한다. 성능
threshold는 강제하지 않으며 낮거나 음수인 R²도 관측 결과로 그대로 남긴다.

## 실행

기본 실행은 stdout에 summary JSON만 출력하고 저장소에 파일을 만들지 않는다.

```bash
python tools/run_frame_surrogate_experiment.py --cases 90 --seed 42
```

`--output`에 JSON 경로를 주면 summary와 인접한 `*.records.jsonl`을 만들고, 디렉터리를
주면 `summary.json`과 `records.jsonl`을 만든다.

```bash
python tools/run_frame_surrogate_experiment.py \
  --cases 300 \
  --seed 20260712 \
  --output tmp/frame-surrogate
```

출력 summary에는 topology별 case 수, singular 제외 수, group leakage, 실제 MAE/R²,
solver provenance와 금지된 주장이 포함된다.

## 완료된 PyTorch Geometric 후속 비교

후속 실험은 exact solver label과 topology holdout을 유지해 구현되었다.

1. 동일 graph record를 실제 PyG `Data`/`Batch`로 변환했다.
2. GraphSAGE와 GAT를 3-seed ensemble로 같은 90-case split에서 비교했다.
3. 2/3-bay train·validation과 완전히 분리된 4-bay 30-case test holdout을 사용했다.
4. validation-only conformal interval과 OOD/high-uncertainty `REVIEW_REQUIRED` gate를 만들었다.
5. GraphSAGE를 base Docker에서 Torch 없이 실행할 수 있는 NumPy artifact로 export하고 PyG와
   `1e-4` 이내 inference parity를 검증했다.
6. surrogate는 빠른 preview만 담당하고 최종 PASS는 항상 exact solver와 DXF verifier가 결정한다.

정확한 수치와 아직 남은 external-topology 평가 범위는 [frameguard-gnn.md](frameguard-gnn.md)에
고정되어 있다.

PyTorch Geometric 모델이 더 높은 성능을 보이더라도 구조 안전성, 법규 적합성 또는 실무
검토 대체를 주장하지 않는다. 실제 구조에 적용하려면 별도의 해석 모델 검증, 재료·단면
검증, 좌굴·연결·비선형·동적 효과, 적용 기준 및 전문 엔지니어 검토가 필요하다.

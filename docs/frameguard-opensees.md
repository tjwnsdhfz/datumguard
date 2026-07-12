# FrameGuard OpenSeesPy parity benchmark

FrameGuard의 공식 screening solver인 `datumguard_numpy_2d_frame_v1`을 독립적인
OpenSeesPy 모델과 비교하는 재현 가능한 기준해석이다. 이 benchmark의 통과는 두 선형탄성
해석 구현이 정해진 사례와 공차에서 일치한다는 뜻이며, 구조 안전 인증이나 설계기준 적합성
판정을 의미하지 않는다.

## 검증 대상

OpenSees 모델은 실제 `openseespy.opensees` API로 다음처럼 구성한다.

- `model basic -ndm 2 -ndf 3`
- `geomTransf Linear`
- `elasticBeamColumn`
- node별 `fix`, `load`
- `LoadControl 1.0`, `algorithm Linear`, `Static` analysis
- `nodeDisp`, `nodeReaction`, element `localForce` 결과 재추출

node와 member를 ID로 정렬한 뒤 1부터 tag를 부여하므로 입력 배열 순서가 달라도 tag mapping은
결정적이다. OpenSees는 process-global model state를 사용하므로 adapter는 build, solve, result
extraction, `wipe` 전체를 하나의 lock으로 직렬화한다.

## 부재력 부호 규약

OpenSees의 2D `elasticBeamColumn localForce`는 다음 resisting-force 순서를 반환한다.

```text
[N_i, V_i, M_i, N_j, V_j, M_j]
```

local x축은 start node에서 end node 방향이고 local y축은 그에 대한 반시계 방향 법선이다.
이는 DatumGuard가 `transform @ displacement`와 `k_local @ u_local`로 계산하는 부재단력과
직접 대응한다. benchmark는 absolute value만 비교하지 않고 여섯 성분의 부호까지 그대로
비교한다.

## 공개 함수

| 함수 | 역할 |
|---|---|
| `probe_opensees()` | import, package version, engine version을 확인하고 `AVAILABLE` 또는 `UNAVAILABLE` 반환 |
| `solve_frame_opensees(contract)` | genuine OpenSeesPy 2D frame 해석과 node/member evidence 반환 |
| `compare_frame_analyses(...)` | entity ID, screening status, 변위, 반력, 부재력, 응력, 평형을 공차 gate로 비교 |
| `build_default_parity_cases()` | cantilever, portal, 2/3/4-bay rack, 실패 fixture 구성 |
| `run_opensees_parity_benchmark()` | suite 단위 `PASSED`, `FAILED`, `UNAVAILABLE` 보고서 생성 |
| `load_packaged_parity_report()` | 배포 wheel에 포함된 최근 정적 evidence JSON 로드 |

OpenSees import 실패는 `UNAVAILABLE`이며 각 case는 `SKIPPED`다. 이것을 PASS로 바꾸지 않는다.
OpenSees `analyze` non-zero code, exception, entity 누락, screening 불일치, 공차 초과, 전체 평형
초과 중 하나라도 발생하면 fail closed로 `FAILED`다.

## 공차

각 sample은 다음 combined gate를 사용한다.

```text
abs(actual - expected)
  <= absolute_tolerance + relative_tolerance * max(abs(actual), abs(expected))
```

| 결과 | absolute tolerance | relative tolerance |
|---|---:|---:|
| displacement | `1e-7 mm` | `1e-7` |
| rotation | `1e-10 rad` | `1e-7` |
| force/reaction | `1e-5 N` | `1e-7` |
| moment/reaction | `1e-2 N·mm` | `1e-7` |
| combined stress | `1e-8 MPa` | `1e-7` |
| utilization | `1e-10` | `1e-7` |

global equilibrium은 각 node reaction, nodal force/moment, force의 origin 기준 moment를 다시
합산한다. force residual은 `1e-5 N`, moment residual은 `1e-2 N·mm` 이하만 허용한다.

## Python 3.12 / Windows 실측 결과

2026-07-12에 별도 환경 `C:\tmp\datumguard-opensees-venv`에서 다음 조합을 직접 실행했다.

- CPython `3.12.11`, Windows 11 AMD64
- `openseespy==3.8.0.0`
- `openseespywin==3.8.0.0`
- OpenSees engine `3.8.0`
- NumPy `2.4.6`

설치, import, `ops.version()`, 여섯 case의 genuine analysis와 result extraction이 모두
성공했다. 즉 이 환경에서는 Python 3.12용 Windows wheel이 실제로 동작한다. 다만 OpenSeesPy는
현재 제품 runtime dependency에는 포함하지 않았다. 공개 배포는 감사된 정적 보고서를 제공하고,
live benchmark를 실행하는 개발/CI 환경만 별도 dependency를 설치해야 한다.

## 실행

공유 `.venv`와 ML dependency 충돌을 피하려면 별도 환경을 사용한다.

```powershell
uv venv C:\tmp\datumguard-opensees-venv --python 3.12
uv pip install --link-mode copy `
  --python C:\tmp\datumguard-opensees-venv\Scripts\python.exe `
  -e ".[dev]" openseespy==3.8.0.0

& C:\tmp\datumguard-opensees-venv\Scripts\python.exe `
  tools/run_frame_opensees_parity.py
```

기본 출력은 두 곳에 동일하게 기록한다.

- 감사 artifact: `artifacts/benchmarks/frame-opensees-parity.json`
- 배포용 package evidence: `src/datumguard/data/frame_opensees_parity.json`

`UNAVAILABLE`을 CI에서 허용해야 하는 문서-only 환경에서만 `--allow-unavailable`을 사용한다.
일반 실행은 `PASSED`가 아니면 exit code 1이다.

## 현재 benchmark 결과

아래 표와 오차 수치의 source of truth는
`src/datumguard/data/frame_opensees_parity.json`이며 연구용 mirror는
`artifacts/benchmarks/frame-opensees-parity.json`이다.

| case | 구조 | parity | 예상 screening |
|---|---|---|---|
| `cantilever` | closed-form 비교가 가능한 단일 cantilever | PASSED | PASS |
| `portal` | 고정단 1-bay moment frame | PASSED | PASS |
| `pipe-rack-2-bay` | 2-level braced rack | PASSED | PASS |
| `pipe-rack-3-bay` | 2-level braced rack | PASSED | PASS |
| `pipe-rack-4-bay` | topology 확대 case | PASSED | PASS |
| `failure-fixture` | 기존 FrameGuard failure preset | PASSED | FAIL |

`failure-fixture`의 parity가 PASSED인 이유는 두 solver가 모두 같은 위험 판정을 냈기 때문이다.
구조 screening 자체는 의도대로 FAIL이다. 현재 여섯 case 중 가장 큰 local moment 차이는
`3.01e-6 N·mm`이고 OpenSees global force/moment residual은 각각 최대 약 `2.91e-11 N`,
`2.06e-7 N·mm`이다.

## 한계

- 2D, small-displacement, linear-elastic Euler-Bernoulli frame만 비교한다.
- distributed load, release, rigid offset, geometric/nonlinear material, buckling, dynamic response는
  아직 계약과 두 solver의 공통 범위가 아니다.
- OpenSees parity는 잘못된 입력하중, 단면, support, 단위 또는 실제 시공상태를 보정하지 않는다.
- 전문 구조기술자의 해석·검토와 적용 설계기준 확인을 대체하지 않는다.

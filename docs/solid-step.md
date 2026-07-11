# 3D Solid STEP Assurance

`/solid`은 치수 폼에서 제한된 3D part contract를 만들고 OpenCascade로 실제 B-rep STEP을 쓴 뒤,
저장된 STEP byte를 별도 process에서 다시 열어 측정한다. 브라우저 미리보기는 writer mesh가 아니라
재입력 STEP에서 tessellate한 triangle이다.

## 지원 part family

| `geometry.type` | 주요 입력 | 독립 재측정 |
|---|---|---|
| `mounting_plate` | width, depth, thickness, corner radius, holes | bbox, hole diameter와 axis center |
| `angle_bracket` | base, vertical leg, base holes | 전체 bbox, hole diameter와 axis center |
| `flange` | OD, ID, thickness, PCD, bolt holes | bbox, bore/outer cylinder, bolt circle hole center |

입력은 mm이며 contract hash 격자와 기본 verification tolerance는 `0.001mm`다. `valid_shape`, solid
count, topology, volume, area와 모든 공개 치수가 통과해야 `solid.step`과 ZIP bundle이 반환된다. Bundle은
STEP, `DO NOT SCALE` PDF, contract JSON, verification JSON, manifest를 포함한다.

## 실행

```bash
curl -X POST http://localhost:8000/api/v1/solid/designs/run \
  -H "Content-Type: application/json" \
  --data @fixtures/examples/solid_mounting_plate.json
```

MCP에서는 `solid_generate_verify`에 동일 contract JSON을 전달한다.

## 실제 Rhino 8 상호운용 smoke

Rhino 8에서 한 번 `StartScriptServer` 명령을 실행한 뒤 다음 명령을 실행한다.

```bash
python tools/rhino_step_smoke.py --connect-existing
```

도구는 검증 STEP을 만들고 RhinoCode의 allowlisted `script` 명령으로 repository-owned driver만
실행한다. Driver는 별도 headless `RhinoDoc`에 STEP을 import하고, object type·unit·bbox를 측정한 뒤
`.3dm`을 저장한다. Hosted API에는 Rhino command나 사용자 script 실행 surface가 없다.

2026-07-12 로컬 Rhino 8.30 실측에서 mounting plate는 `Brep` 1개, `Millimeters`,
`120 × 80 × 8mm`로 읽혔고 63,911-byte 3DM으로 저장되었다. 상세 evidence는
[rhino-step-smoke.json](evidence/rhino-step-smoke.json)에 고정했다.

이 smoke는 CAD import 호환성의 secondary evidence다. 구조 안전, 재료, 용접, 압력, 가공 공정과
산업표준 인증을 뜻하지 않는다.

# DatumGuard Piping Demo Guide

## Demo contract

`/piping`은 공개 합성 Semiconductor CDA utility route를 사용한다. 실제 fab, 고객, vendor 또는 공정 데이터를 포함하지 않는다.

- Orthogonal connected route: 3 straight segments
- Equipment connection, elbow/junction, endpoint nodes
- Isolation valve, inline instrument, reducer
- Segment별 guide/shoe supports
- Equipment footprint와 keepout zone
- Locked segment length와 valve offset dimension
- Maximum support spacing 2,000mm
- Minimum obstacle clearance 300mm

`Semiconductor CDA` preset은 통과해야 하고 `Clearance collision` preset은 `DG_PIPE_CLEARANCE_VIOLATION`으로 공식 export를 차단해야 한다.

## Stable browser contract

| Selector | 의미 |
|---|---|
| `[data-testid="piping-demo"]` | Piping workspace root와 verification status |
| `[data-testid="piping-preset-utility"]` | 통과 utility preset |
| `[data-testid="piping-preset-clearance-fail"]` | clearance 실패 preset |
| `[data-testid="piping-canvas"]` | Native SVG CAD canvas |
| `[data-testid="piping-draggable-valve"]` | Host segment 위에서 이동하는 valve |
| `[data-testid="piping-snap-target"]` | Deterministic snap target |
| `[data-testid="piping-run-verification"]` | 실제 API 검증 실행 |
| `[data-testid="piping-timeline"]` | Contract→writer→reader→gate timeline |
| `[data-testid="piping-summary"]` | DXF 재측정 summary |
| `[data-testid="piping-contract-hash"]` | Canonical contract hash |
| `[data-testid="piping-artifact-hash"]` | Serialized DXF artifact hash |
| `[data-testid="piping-download"]` | Passed bundle download |

## Run and capture

```bash
python -m uvicorn datumguard.api:app --host 127.0.0.1 --port 8000
# second terminal
cd web
npm run dev -- --hostname 127.0.0.1 --port 3000
# third terminal
npm run test:e2e
npm run demo:capture:piping
```

Capture target:

```text
docs/assets/demo/piping-verified.png
```

Capture script는 valve를 snap target으로 이동하고 실제 `POST /api/v1/piping/designs/run`이 `passed`를 반환한 뒤에만 이미지를 저장한다.

## Interpretation boundary

화면의 `VERIFIED`는 contract에 기록한 2D geometry 조건과 serialized DXF 재측정이 일치한다는 의미다. 다음을 승인하지 않는다.

- Process safety 또는 HAZOP
- Pressure drop, fluid, thermal/stress analysis
- Pipe class/spec, material, welding, NDE
- Support load/sizing
- P&ID, code, 법규, 제작 적합성

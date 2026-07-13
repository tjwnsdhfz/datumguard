# Artifact Lab — 실제 CAD 산출물 감사

`/intake`의 Artifact Lab은 DatumGuard가 생성한 파일만 다루는 화면이 아니다. AutoCAD, Rhino,
FreeCAD, Revit 등 외부 CAD에서 만든 기존 `DXF`, `STEP`/`STP`, `IFC` 파일을 최대 20MB까지 받아
원본 byte를 바꾸지 않고 구조와 revision evidence를 만든다.

## 지원 범위

| Format | 독립 reader | 측정·감사 항목 | Revision compare |
|---|---|---|---|
| DXF | isolated `ezdxf recover` + auditor | version, `$INSUNITS`, layer/entity, extents, XDATA, support matrix, block budget, SVG | 완전성 gate가 열린 entity의 geometry fingerprint와 handle 변화 |
| STEP | isolated CadQuery/OpenCascade worker | schema, unit, shape validity, solid/face/edge, volume, area, bbox, cylinder, tessellation | kernel metric delta |
| IFC | IfcOpenShell | schema, SI unit, product/type/spatial count, duplicate `GlobalId`, orphan product | `GlobalId` 추가·삭제·속성 변화 |

모든 결과는 원본 SHA-256 `artifact_hash`, 파일 크기, format, metrics, issues, evidence를 반환한다.
STEP reader는 웹/API process와 분리된 worker에서 실행해 OpenCascade와 IfcOpenShell native runtime의
수명과 failure를 격리한다.

## DXF completeness gate

`support_matrix_version=2026-07-13.1`은 각 modelspace entity를 다음 수준으로 분류한다.

| Level | 대표 entity | 보장 |
|---|---|---|
| `MEASURED` | LINE, ARC, CIRCLE, LWPOLYLINE, POLYLINE, SPLINE, POINT, TEXT/MTEXT, 3DFACE | canonical DXF attribute와 명시 geometry payload를 fingerprint |
| `RENDER_ONLY` | INSERT, HATCH, DIMENSION, LEADER/MLEADER, MESH, MLINE | preview에는 사용할 수 있지만 전체 geometry equality에는 사용하지 않음 |
| `UNSUPPORTED` | XREF INSERT, proxy, underlay, IMAGE, OLE, WIPEOUT, REGION/BODY | 측정·완전 비교·안전한 preview 대상에서 제외 |

응답의 `dxf_completeness`는 `comparison_complete`, `render_eligible`, entity별 support level,
modelspace/entity/block 수, 최대 nesting depth, 순환 참조, XREF 이름과 초과 budget을 반환한다.
revision compare도 top-level `support_matrix_version`과 `comparison_complete`를 반환한다.

다음 중 하나라도 있으면 원본 hash와 가능한 측정 evidence는 유지하지만 상태를
`needs_confirmation`으로 제한하고 `same_geometry_multiset=null`을 반환한다.

- `RENDER_ONLY` 또는 `UNSUPPORTED` entity
- modelspace 100,000 entity, block definition 10,000개, nested/expanded entity 각각 250,000개 초과
- INSERT 10,000개 또는 nesting depth 16단계 초과
- cyclic block reference

이때 `measured_geometry_multiset_match`는 측정 가능한 부분만의 결과이며 전체 geometry 동일성을
뜻하지 않는다. XREF·opaque content와 budget 초과 파일은 extents expansion과 SVG rendering도
중단한다. parser는 별도 process에서 45초 timeout, 입력·출력·메모리·파일·CPU limit을 적용한다.

## 승인 경계

Artifact Lab의 결과는 `approval_eligible: false`, `original_preserved: true`로 고정한다. Contract가
없는 기존 파일에서 구조적 오류가 없다는 사실은 제작·구조·압력·법규 승인이 아니다. 제작 승인 bundle은
명시적 `DesignContract`와 독립 공차 검증을 통과한 `/solid`, `/`, `/piping`, `/plate` 경로에서만 생성된다.

## API

```http
POST /api/v1/artifacts/audit
Content-Type: multipart/form-data
file=@equipment-layout.dxf
```

```http
POST /api/v1/artifacts/compare
Content-Type: multipart/form-data
baseline=@revision-a.ifc
candidate=@revision-b.ifc
```

동일 기능은 MCP `artifact_audit`, `artifact_compare`로 제공된다. MCP에서는 파일 byte를 base64로
전달하며 arbitrary path나 shell command를 받지 않는다.

## 검증된 브라우저 계약

Playwright는 실제 FastAPI와 함께 다음을 실행한다.

- millimetre DXF upload → SHA-256 lock → SVG와 entity evidence 표시
- endpoint가 달라진 두 measured DXF → `comparison_complete=true`와 added/removed geometry 결과
- INSERT/XREF/WIPEOUT/deep/cyclic block → equality claim 차단과 `needs_confirmation` 또는 구조 오류
- request error와 loading 상태, 44px 이상 file/action control

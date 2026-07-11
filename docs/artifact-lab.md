# Artifact Lab — 실제 CAD 산출물 감사

`/intake`의 Artifact Lab은 DatumGuard가 생성한 파일만 다루는 화면이 아니다. AutoCAD, Rhino,
FreeCAD, Revit 등 외부 CAD에서 만든 기존 `DXF`, `STEP`/`STP`, `IFC` 파일을 최대 20MB까지 받아
원본 byte를 바꾸지 않고 구조와 revision evidence를 만든다.

## 지원 범위

| Format | 독립 reader | 측정·감사 항목 | Revision compare |
|---|---|---|---|
| DXF | `ezdxf recover` + auditor | version, `$INSUNITS`, layer/entity, extents, XDATA, recover issue, SVG | geometry fingerprint multiset와 handle 변화 |
| STEP | isolated CadQuery/OpenCascade worker | schema, unit, shape validity, solid/face/edge, volume, area, bbox, cylinder, tessellation | kernel metric delta |
| IFC | IfcOpenShell | schema, SI unit, product/type/spatial count, duplicate `GlobalId`, orphan product | `GlobalId` 추가·삭제·속성 변화 |

모든 결과는 원본 SHA-256 `artifact_hash`, 파일 크기, format, metrics, issues, evidence를 반환한다.
STEP reader는 웹/API process와 분리된 worker에서 실행해 OpenCascade와 IfcOpenShell native runtime의
수명과 failure를 격리한다.

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
- endpoint가 달라진 두 DXF → added/removed geometry revision 결과
- request error와 loading 상태, 44px 이상 file/action control

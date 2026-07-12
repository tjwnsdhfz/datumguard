# DatumGuard Roadmap

- 기준일: 2026-07-13
- 현재 공개 release: [`v0.3.0`](https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.3.0)
- 현재 production workspace: Architecture, Piping, FrameGuard, Plate, Artifact Lab
- 상세 launch 계획: [Growth and Launch Roadmap](docs/growth-and-launch-roadmap.md)

DatumGuard의 우선순위는 많은 CAD 명령을 자동화하는 것이 아니라 **저장된 artifact를 독립적으로
다시 측정해 정확성 evidence를 남기는 것**입니다. 새 기능은 항상 deterministic contract,
independent verifier, fail-closed export, reproducible evidence 순서를 지켜야 합니다.

## 제품 경계

- FrameGuard는 제한된 2D linear-elastic frame의 **preliminary structural screening**입니다.
- 결과는 구조 안전 인증, 법규 검토, 제작 승인 또는 전문 엔지니어의 판단을 대체하지 않습니다.
- Rhino/Grasshopper 결과는 secondary evidence이며 독립 DXF verifier가 official gate입니다.
- ambiguity, unsupported entity, verifier failure가 있으면 official export를 허용하지 않습니다.
- 계정, 서버 프로젝트 저장, 협업 편집, 임의 script 실행은 현재 제품 범위가 아닙니다.

## Now — `v0.4` Rhino Verified Round Trip

가장 먼저 완성할 공개 증거 흐름입니다.

```text
Rhino/Grasshopper model
  -> centerline/support/load/section metadata
  -> explicit unit and datum exchange
  -> deterministic exact screening
  -> R2013/mm DXF
  -> independent reopen and remeasurement
  -> fail-closed export
  -> source/object/artifact hash manifest
```

완료 조건:

- 실제 `.3dm`과 `.gh` 예제를 repository에서 재현할 수 있음
- mm/inch 입력이 같은 normalized geometry를 만들고 unit ambiguity는 실패함
- rotated XY datum은 변환되며 tilted datum과 out-of-plane geometry는 실패함
- Rhino object GUID, contract entity ID, DXF XDATA를 manifest에서 추적할 수 있음
- DXF 변조 시 PASS와 download가 모두 차단됨
- 정상과 failure preset, 60~90초 video, 15초 GIF를 공개함

## Next — DXF Completeness Gate

외부 DXF를 비교할 때 지원 범위를 숨기지 않고 entity별 evidence 수준을 반환합니다.

- `MEASURED`: 정밀 fingerprint, bbox, revision comparison 가능
- `RENDER_ONLY`: 시각화는 가능하지만 완전한 geometry equality를 주장하지 않음
- `UNSUPPORTED`: `needs_confirmation` 또는 fail-closed result만 반환

우선 대상은 `INSERT`, nested block, XREF, proxy entity, underlay, image, OLE, wipeout입니다.
`support_matrix_version`, entity별 support level과 `comparison_complete`를 공개 contract에 포함합니다.
malformed file, timeout, oversized entity count, deep nesting fixture도 worker를 중단시키지 않아야
합니다. 외부 upload는 계속 `approval_eligible=false`입니다.

## Then — Portfolio-ready Evidence and Developer Experience

- Rhino structural frame, DXF plate, STEP bracket, 재배포 허용 IFC의 source/license/hash evidence pack
- 각 정상 sample과 의도된 failure counterpart
- `Try verified -> Break one constraint -> Download evidence` guided tour
- Rhino/Artifact Lab tutorial과 curl, Python, TypeScript sample
- accessibility, Lighthouse, metadata, JSON-LD와 deployment smoke gate
- versioned research artifact drift check와 release evidence history

## Research track

Research 결과는 production assurance와 분리해 표시합니다.

- external geometry benchmark 20~30개 frame과 topology holdout
- multiple load case와 expanded OpenSees parity
- GraphSAGE/GAT의 외부 geometry generalization과 uncertainty calibration
- IFC/IDS/BCF interoperability corpus와 재현 가능한 license provenance

ML surrogate는 `PREDICTED` 또는 `REVIEW_REQUIRED` triage만 반환하며 official PASS를 결정하지
않습니다. benchmark 수치에는 dataset 범위, split, seed, solver, limitation을 함께 공개합니다.

## 현재 계획하지 않는 항목

- 자연어만으로 arbitrary CAD geometry를 생성하는 범용 authoring tool
- nonlinear, seismic, buckling, connection 또는 code-compliance certification
- 다층 BIM authoring, 범용 3D assembly, 실시간 collaboration
- 인증·결제·계정 DB·cloud artifact storage
- 지원 근거 없이 공학 분야만 추가하는 demo 확장
- 유료 광고 또는 검증되지 않은 `AI safety prediction` 홍보

## 제안 우선순위

새 요청은 다음 질문으로 평가합니다.

1. 실제 engineering failure를 재현하는가?
2. writer와 독립된 artifact evidence를 추가하는가?
3. PASS뿐 아니라 의도된 FAIL을 검증하는가?
4. 공개 sample의 license와 provenance가 명확한가?
5. 사용자가 제한과 failure reason을 이해할 수 있는가?
6. 기존 API, hash, export semantics를 하위 호환으로 유지하는가?

아이디어는 [GitHub Discussions](https://github.com/tjwnsdhfz/datumguard/discussions), 재현 가능한
요청은 issue form으로 제안해 주세요. 구현 절차와 safety checklist는
[CONTRIBUTING.md](CONTRIBUTING.md)를 따릅니다.

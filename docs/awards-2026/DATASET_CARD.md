# Virtual FAB v1 Dataset Card

## 요약

`virtual-fab-v1`은 OpenBIM Evidence Guard 연구를 위해 코드로 생성한 IFC4 합성 데이터셋이다. 실제
FAB, 기업 도면, 운영·보안 정보는 포함하지 않는다. 세 layout, 네 revision variant, 사전 정의한
11개 mutation으로 IDS·integrity·geometry·revision 검사의 재현 가능한 평가를 지원한다.

## 구성

| Split | Layout별 case | 총 case | 용도 |
|---|---:|---:|---|
| representative | L1 1개 | 1 | 데모·문서·수직 통합 |
| pilot | 각 2개 | 6 | detector 개발과 오류 수정 |
| evaluation | 각 10개 | 30 | 최종 held-out 집계 |

각 case에는 다음이 있다.

- `v0_clean.ifc`: 모든 정의 규칙을 만족하는 baseline
- `v1_authorized.ifc`: allowlist의 protected SystemCode 변경을 수행한 control
- `v1_faulty.ifc`: 서로 다른 객체에 11개 mutation을 주입한 candidate
- `v2_corrected.ifc`: mutation을 제거한 corrected control
- `mutation_manifest.json`: seed 선택, before/after, target, artifact hash
- `truth.json`: detector와 독립적으로 manifest에서 생성한 rule-level 정답

공통 `virtual_fab_v1.ids`, `virtual_fab_profile.json`, `dataset_manifest.json`이 corpus root에 있다.

## Layout

| ID | 설명 | 검사 자산 수 | Tool | Pipe | Valve | Fitting | Support |
|---|---|---:|---:|---:|---:|---:|---:|
| L1 | Linear Tool Bay | 32 | 4 | 18 | 4 | 2 | 4 |
| L2 | Branched Utility Rack | 40 | 5 | 24 | 4 | 3 | 4 |
| L3 | Dense Crossover | 48 | 6 | 28 | 5 | 4 | 5 |

자산은 `IfcBuildingElementProxy`, `IfcPipeSegment`, `IfcPipeFitting`, `IfcValve`로 구성되며
`IfcProject -> IfcSite -> IfcBuilding -> IfcBuildingStorey -> IfcSpace`에 포함된다. box형
`IfcExtrudedAreaSolid` geometry와 metre 단위를 사용한다.

## 정보 계약

- `DG_Identity`: `AssetKey`, `AssetTag`
- `DG_VFabUtility`: `UtilityType`, `SystemCode`, `Criticality`
- `DG_VFabClearance`: `ServiceSide`, `ServiceDepth`
- 합성 classification: `DG-VFAB-2026`

`DG_` property set과 값은 교육용 프로젝트 계약이며 buildingSMART 공식 property set이나 산업 표준이
아니다.

## Mutation

faulty case마다 I01~I06, G01~G02, R01~R03을 한 번씩 주입한다. R01이 두 자산을 사용하는 것을
포함해 12개 mutation target을 사용하며 어떤 target도 다른 fault에 재사용하지 않는다. geometry
fault는 서로 다른 tool의 service envelope를 사용한다. target 선택은 split에 고정된 seed를 쓰며
truth는 detector 결과가 아닌 mutation manifest에서 파생된다.

## 결정론과 무결성

- UUIDv5 고정 namespace를 IFC GUID로 압축한다.
- IFC header timestamp와 generator metadata를 고정한다.
- JSON은 UTF-8, sorted key, 고정 indent로 직렬화한다.
- 모든 IFC를 disk에 쓴 뒤 IfcOpenShell 새 open으로 schema·AssetKey·object count를 확인한다.
- IDS, profile, model, truth, mutation manifest의 SHA-256을 manifest에 기록한다.
- `--verify-determinism`은 임시 폴더에 corpus를 다시 생성해 모든 상대 경로의 byte hash를 비교한다.

## 생성

```powershell
uv run python tools/generate_virtual_fab_fixtures.py `
  --split all --evaluation-per-layout 10 --verify-determinism
```

최소 실험은 `--evaluation-per-layout 4`를 사용하지만 표본 축소를 결과에 명시해야 한다.

## 권장 사용과 금지된 주장

권장 사용:

- OpenBIM Evidence Guard 회귀·ablation·결정성 평가
- IDS checker와 project rule 통합 연구
- 합성 IFC issue traceability 시연

금지된 주장:

- 실제 반도체 FAB 적합성 또는 보안 검증
- 구조·안전·법규·압력·제작·시공 승인
- 실제 산업 오류 분포에 대한 통계적 일반화
- AABB 결과를 exact solid clash로 표현

## 알려진 한계

geometry는 box, 직교 회전, 48개 이하 자산으로 제한된다. 동일 개발 환경에서 generator와 detector를
만들어 oracle leakage 위험이 있다. 이를 줄이기 위해 코드 모듈, pilot/evaluation seed, manifest와
detector output을 분리하지만 완전히 독립된 외부 dataset은 아니다.

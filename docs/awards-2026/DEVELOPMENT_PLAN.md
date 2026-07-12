# BIM Awards 2026 - OpenBIM Evidence Guard 개발 계획

- 작성 기준일: 2026-07-12
- 출품 분야: 학생부 `Research`
- 개발 종료 목표: 2026-08-23
- 공모 마감: 2026-09-04 18:00
- 패널 디자인·편집: 이 문서의 범위 밖
- 상태: 실행 전 계획 snapshot. 실제 구현·검증 상태는 [README](README.md)와
  [RESULTS](RESULTS.md)를 따른다.

> 실행 기록: 계획 일정보다 앞선 2026-07-12에 구현, protocol freeze와 합성 evaluation을 수행했다.
> 이 파일의 날짜·gate·baseline 문구는 사전 의사결정 기록으로 보존하며 현재 성과로 읽지 않는다.

## 1. 개발 목표

기존 DatumGuard의 IFC 구조 감사와 revision 비교를 유지하면서, 공모전용 수직 기능인
`OpenBIM Evidence Guard`를 별도 경로로 추가한다.

```text
baseline.ifc + candidate.ifc + requirements.ids + virtual-fab-v1 profile
                               |
                    isolated OpenBIM worker
                               |
          IDS information | IFC integrity | revision | AABB clearance
                               |
              evidence JSON | HTML | optional BCFZIP
```

핵심 원칙은 다음과 같다.

1. 저장된 IFC bytes를 새 프로세스에서 다시 열어 검사한다.
2. 모든 입력과 출력에 SHA-256을 기록한다.
3. IDS 정보 검사, IFC 표준 검사, 프로젝트 형상 규칙, 프로젝트 revision 규칙을 구분한다.
4. `PASS`는 정의한 연구 규칙을 통과했다는 뜻일 뿐 구조·안전·법규·시공 승인이 아니다.
5. 기존 `/intake`의 `approval_eligible=false` 계약과 응답 형식을 깨지 않는다.
6. AI/LLM은 판정 경로에 넣지 않는다.

## 2. 현재 기준점과 실제 격차

계획 작성 시 저장소는 `main@40dd132`, `origin/main`과 동일하고 worktree는 clean이다.

현재 존재하는 기능:

- `src/datumguard/artifact_service.py`
  - IFC schema validation
  - 길이 단위와 `IfcProject` 개수
  - 중복 `GlobalId`
  - 공간구조에 포함되지 않은 element
  - product, spatial, property-set 수
  - revision 간 GlobalId 추가·삭제 및 일부 top-level 속성 변화
- `POST /api/v1/artifacts/audit`, `POST /api/v1/artifacts/compare`
- `/intake` 업로드·감사·revision 비교 UI
- 합성 `IfcWall` 한 개를 사용한 IFC audit/compare 테스트 한 건

현재 없는 기능:

- 실제 `.ifc`, `.ids`, `.bcfzip` fixture
- IDS 1.0 validation
- property-set을 포함한 protected revision contract
- IFC geometry 기반 clearance 검사
- IFC 사용자 흐름 Playwright E2E
- BCF round-trip과 독립 viewer import evidence
- 공모전 연구용 labeled corpus와 benchmark runner

README와 HANDOFF에 기록된 `256 pytest + 19 Playwright`는 `b2dd6e5` 기준 증거다. 현재
`40dd132` 전체 CI 통과를 의미하지 않는다. 개발 시작 전 현재 HEAD에서 baseline 전체 검증을 다시
실행하고, 최종 release 때 새 CI와 production smoke로 교체한다.

## 3. 범위 우선순위

### P0 - 출품에 반드시 필요

- 결정론적 IFC4 Virtual FAB 생성기
- clean, faulty, authorized, corrected 모델과 fault-level ground truth
- 공식 IDS checker 연동
- 안정된 JSON evidence schema
- IFC integrity 및 protected revision 규칙
- 연구 benchmark runner와 raw/aggregate 결과
- CLI/API에서 한 명령 또는 한 요청으로 재현 가능한 흐름
- 단위·통합·회귀 테스트와 최종 CI

### P1 - 차별화를 위해 목표로 하되 hard gate 적용

- world-coordinate AABB 기반 maintenance-clearance screening
- BCFZIP issue export와 독립 viewer import 확인
- corrected IFC 재검사 후 issue closure
- 최소 `/openbim` 웹 UI
- self-contained HTML report
- production 배포와 smoke canary

### P2 - 일정이 남을 때만

- BCF viewpoint/snapshot 고도화
- 웹 시각 polish
- 추가 utility 종류와 더 큰 모델
- 두 번째 authoring tool에서 export한 IFC 호환성 확인

### 명시적 제외

- 신규 3D viewer
- AI 판정, RAG, 멀티에이전트
- 자동수정
- DB, 계정, 협업 서버
- Revit plug-in
- exact solid clash와 곡선 배관
- 구조·압력·피로·법규·시공성 판정
- IFC2x3·IFC4.3 동시 지원
- PlantFab 전체 PRD 구현

## 4. Hard gate와 제목 변경 규칙

기술이 검증되기 전 제목에 기능을 약속하지 않는다.

| 기한 | Gate | 통과 조건 | 실패 시 범위 컷 |
|---|---|---|---|
| 7/16 | IDS spike | IFC 1개에 최소 IDS 1 PASS·1 FAIL, JSON 결과 생성 | 제목에서 `IDS 기반` 제거 또는 checker 연동 해결까지 일정 중단 |
| 7/19 | Geometry spike | IFC geometry world AABB와 mm/m 단위 경계 테스트 성공 | `형상·clearance` 주장 제거 |
| 7/19 | BCF spike | 이슈 1건 저장·재개방·독립 viewer import 성공 | 제목에서 `BCF` 제거, JSON/HTML을 필수 결과로 유지 |
| 7/29 | Vertical slice | clean/faulty/corrected가 CLI/API에서 끝까지 실행 | UI 및 P2 전부 제거 |
| 8/09 | Integration | 네 규칙군과 결과 다운로드 통합 | UI가 늦으면 CLI/API/offline bundle만 유지 |
| 8/16 | Protocol freeze | evaluation corpus, seed, matching, metric 고정 | 이후 detector·truth 변경 시 protocol version 증가 |
| 8/20 | Final experiment | raw result와 aggregate metric 자동 생성 | 실패 결과도 삭제하지 않고 원인 기록 |
| 8/23 | Code freeze | 전체 CI·Docker·재현 명령 통과 | 신규 기능 금지, 결함 수정만 허용 |

범위가 밀릴 때 자르는 순서는 다음과 같다.

1. 3D viewer, AI, autofix, DB, RAG
2. 웹 polish와 고급 HTML
3. BCF viewpoint/snapshot
4. clearance

Clearance 또는 BCF를 자르면 제목과 연구질문에서도 즉시 제거한다.

## 5. 권장 구현 구조

기존 `/intake`는 범용 artifact audit로 유지하고 `/openbim`을 별도 추가한다.

### 새 백엔드 모듈

| 파일 | 책임 |
|---|---|
| `src/datumguard/openbim_models.py` | profile, rule result, issue, report, 전체 응답 Pydantic 모델 |
| `src/datumguard/openbim_service.py` | 입력 검증, hash, worker 호출, 결과 정규화, bundle 생성 |
| `src/datumguard/openbim_rules.py` | integrity, revision, clearance 순수 규칙과 결정론적 정렬 |
| `src/datumguard/openbim_reporting.py` | canonical JSON, HTML, optional BCFZIP, manifest |
| `src/datumguard/openbim_worker.py` | IFC·IDS·geometry native parsing을 API 프로세스와 격리 |
| `src/datumguard/ifc_evidence.py` | 단위, Pset, stable identity, placement, world AABB 공통 함수 |

기존 `artifact_service.py`를 대규모로 다시 쓰지 않는다. 공통 함수 추출이 기존 응답·해시·issue
순서를 바꾼다면, 우선 별도 구현으로 유지하고 공통화는 공모전 이후로 미룬다.

### 수정 대상

- `src/datumguard/cad_subprocess.py`
  - `run_openbim_worker()`와 timeout/output limit 추가
- `src/datumguard/api.py`
  - `POST /api/v1/openbim/evidence/run`
  - domain registry에 `/openbim` 추가
- `src/datumguard/operations.py`
  - heavy path와 `DATUMGUARD_ENABLE_OPENBIM` kill switch
- `pyproject.toml`, `uv.lock`
  - dependency spike를 통과한 버전만 명시적으로 pin
- `render.yaml`, `web/.env.example`
  - feature flag와 worker timeout

### Dependency gate

후보는 `ifctester==0.8.5`와 그 BCF 의존성이다. 현재 환경에는 `ifctester`와 `bcf`가 없다.

추가 전 다음을 확인한다.

1. Windows, Ubuntu CI, Docker에서 동일 fixture를 검증하는가?
2. backend image 크기와 Render Free memory가 허용 범위인가?
3. malformed IDS, DTD, external entity, oversize 입력을 차단할 수 있는가?
4. exact package license와 DatumGuard MIT 배포의 결합 방식을 검토했는가?

PyPI metadata 기준 IfcTester는 LGPLv3+, `bcf-client`는 GPLv3로 표시된다. 이는 법률 판단을
이 문서에서 확정한다는 뜻이 아니다. 실제 배포 전 license/NOTICE 방식을 검토하고, 해결되지 않으면
BCF를 optional offline research tool로 분리하거나 BCF 범위를 제거한다.

## 6. API 계약 초안

```http
POST /api/v1/openbim/evidence/run
Content-Type: multipart/form-data

baseline=@v0_clean.ifc
candidate=@v1_faulty.ifc
requirements=@virtual_fab_v1.ids
profile_id=virtual-fab-v1
```

임의의 Python, shell, query expression 또는 로컬 경로를 입력받지 않는다. 서버에 등록된
`profile_id`만 선택하게 한다.

응답 핵심 필드:

```json
{
  "status": "passed | failed_verification | needs_confirmation",
  "baseline_hash": "sha256:...",
  "candidate_hash": "sha256:...",
  "ids_hash": "sha256:...",
  "profile_hash": "sha256:...",
  "research_validation_only": true,
  "rule_results": [],
  "issues": [],
  "timings_ms": {},
  "reports": []
}
```

각 issue에는 적어도 다음이 있어야 한다.

- `rule_id`
- `scope`: `IFC_SCHEMA | IDS_REQUIREMENT | PROJECT_GEOMETRY_RULE | PROJECT_REVISION_RULE`
- `severity`
- `entity_ids` 또는 정렬된 `entity_pair`
- `expected`, `actual`
- `location`이 계산 가능한 경우 world coordinate
- source artifact, IDS, profile hash

JSON은 정렬과 canonical serialization으로 결정론을 검증한다. BCF의 topic UUID와 timestamp는 byte
동일성을 요구하지 않고, semantic round-trip과 component reference를 검증한다.

## 7. 규칙 계약

### R-01 - IDS 정보요구조건

- IFC 대상 entity와 분류
- `AssetTag`
- `UtilityType`
- `SystemCode`
- FAB tool의 `ServiceSide`, `ServiceDepth`
- 필수 Pset과 허용값

IfcTester raw 결과는 공통 `OpenBimIssue`로 정규화한다. 하나의 원인으로 여러 저수준 message가
발생하면 `rule_id + entity + requirement` 기준으로 deduplicate한다.

### R-02 - IFC 구조·식별자

- IFC4 profile
- `IfcProject` 1개
- project length unit
- 중복·빈 GlobalId
- orphan element
- 중복 `AssetKey`
- 필수 공간 container

중복 identity가 있으면 해당 객체의 revision 비교는 `ambiguous`로 표시해 연쇄 오탐을 막는다.

### R-03 - Project revision contract

- `DG_Identity.AssetKey`로 같은 자산을 우선 매칭
- 같은 AssetKey의 GlobalId churn을 project warning/error로 기록
- `AssetTag`, `UtilityType`, `SystemCode`, container는 기본 locked
- profile의 승인 목록에 있는 변경만 허용
- before, after, authorization 근거를 모두 저장

`GlobalId` persistence는 보편 IFC schema 규칙이 아니라 이 연구 프로젝트의 revision 계약임을 UI와
보고서에 표시한다.

### R-04 - Maintenance-clearance screening

- `ObjectType=FAB_TOOL` 객체의 local bounding box를 기준으로 envelope 생성
- `DG_VFabClearance.ServiceSide`, `ServiceDepth`를 profile과 IDS로 먼저 확인
- world-coordinate AABB 비교
- 0/90/180/270도 회전만 평가
- project unit을 metre로 정규화
- positive overlap이 epsilon보다 클 때 FAIL
- 경계 접촉은 PASS
- geometry가 없으면 PASS가 아니라 `NOT_EVALUABLE`
- 결과에 clearance object와 obstacle의 정렬된 GlobalId pair, 교차 중심 좌표 기록

이는 exact solid clash가 아니라 정방향·소형 모델용 보수적 screening이다.

## 8. Fixture와 생성 도구

```text
fixtures/openbim/
  virtual_fab_v1.ids
  virtual_fab_profile.json
  representative/
    v0_clean.ifc
    v1_authorized.ifc
    v1_faulty.ifc
    v2_corrected.ifc
    truth.json
    mutation_manifest.json

tools/
  generate_virtual_fab_fixtures.py
  run_openbim_experiment.py
```

생성기 요구사항:

- 고정 seed와 stable GUID 전략
- header timestamp 등 비결정 필드 정규화
- injector와 detector 코드 분리
- ground truth는 detector 출력이 아니라 mutation manifest에서 생성
- serialize 후 새 프로세스에서 reopen
- 재실행 시 representative fixture hash가 동일
- 각 모델·IDS·profile·manifest SHA-256 기록

## 9. 작업 분해와 완료 조건

| ID | 작업 | 선행 | Definition of Done |
|---|---|---|---|
| DEV-00 | 현재 HEAD baseline | 없음 | clean tree, full local gate 결과와 commit 기록 |
| DEV-01 | dependency/native spike | DEV-00 | Windows·Linux Docker에서 IDS PASS/FAIL, geometry AABB, BCF save/load 결과 기록 |
| DEV-02 | profile·fixture generator | DEV-01 | 대표 4종, IDS, truth 생성; 재실행 hash 동일 |
| DEV-03 | response model·canonical JSON | DEV-02 | schema test, deterministic sort/hash test 통과 |
| DEV-04A | R-01 IDS | DEV-02,03 | clean 0 fail, injected info fault key와 정확히 일치 |
| DEV-04B | R-02 integrity | DEV-02,03 | duplicate/orphan/identity fault와 정확히 일치 |
| DEV-04C | R-03 revision | DEV-02,03 | authorized 변경 허용, GUID churn·locked Pset 변경 탐지 |
| DEV-04D | R-04 clearance | DEV-01,02,03 | intended pair만 탐지, mm/m 및 ±1mm boundary 통과 |
| DEV-05 | reporting | DEV-04A~D | JSON/HTML 생성, optional BCF round-trip·viewer import |
| DEV-06 | worker/API/ops | DEV-05 | timeout, size, kill switch, scrubbed error 테스트 통과 |
| DEV-07 | `/openbim` UI | DEV-06 | representative sample real-API E2E와 report download 통과 |
| DEV-08 | experiment runner | DEV-04A~D | raw per-case와 metric 자동 생성, 수동 편집 불필요 |
| DEV-09 | release evidence | DEV-06~08 | 전체 CI, Docker, canary, production smoke, offline bundle |
| DEV-10 | docs/handoff | DEV-09 | README, HANDOFF, RULE_CATALOG, DATASET_CARD, 재현 명령 갱신 |

`DEV-04A~D`는 fixture와 response schema가 고정된 뒤 병렬화할 수 있다. UI는 실험 runner보다 우선하지
않는다.

## 10. 테스트 계획

신규 테스트 후보:

```text
tests/test_openbim_ids.py
tests/test_openbim_integrity.py
tests/test_openbim_revision.py
tests/test_openbim_clearance.py
tests/test_openbim_reporting.py
tests/test_openbim_api.py
web/tests/e2e/openbim-evidence.spec.ts
```

필수 사례:

- clean: 정의된 규칙 전체 PASS
- faulty: ground-truth detection key와 실제 결과 일치
- authorized: 승인된 변경만 허용
- corrected: 원래 issue closure, 새 issue 0
- invalid/oversize IFC와 IDS
- unsupported schema와 unit missing
- mm/m 모델의 동일 clearance 결과
- boundary −1mm, 0mm, +1mm
- geometry missing은 `NOT_EVALUABLE`
- malicious IFC Name/IDS text의 HTML escape
- BCF save/reopen 시 topic, component, status 유지
- worker timeout/OOM/invalid JSON에서 경로·stderr·비밀값 미노출
- 기존 `/intake` IFC audit/compare 회귀
- clean/faulty UI upload, retry, JSON/HTML/BCF download

최종 gate:

```powershell
uv sync --frozen --extra dev
uv run --frozen ruff format --check src tests tools
uv run --frozen ruff check src tests tools
uv run --frozen mypy src/datumguard
uv run --frozen pytest
Set-Location web
npm ci
npm audit --audit-level=high
npm run typecheck
npm run lint
npm run build
npm run test:e2e -- --project=chromium
Set-Location ..
docker build -t datumguard-api:openbim .
docker build -t datumguard-web:openbim web
```

## 11. 보안·운영 조건

- IFC 20MB, IDS 1MB 등 format별 제한을 명시한다.
- IDS에서 DTD, external entity, arbitrary URI fetch를 허용하지 않는다.
- native parser는 기존 worker limit와 별도 timeout 안에서 실행한다.
- element/triangle/topic 수를 제한한다.
- 원본 파일을 영구 저장하지 않는다.
- API 응답에 로컬 경로, stack trace, worker stderr를 포함하지 않는다.
- `DATUMGUARD_ENABLE_OPENBIM=false`이면 endpoint는 `503 DG_CAPABILITY_DISABLED`로 닫는다.
- production memory가 부족하면 false success 대신 fail-closed하고 offline bundle을 제공한다.

## 12. 개발 일정

| 기간 | 개발 산출물 |
|---|---|
| 7/12~7/16 | DEV-00 baseline, dependency/IDS spike |
| 7/17~7/19 | geometry·BCF hard gate |
| 7/20~7/25 | fixture generator, profile, representative ground truth |
| 7/26~7/31 | R-01, R-02, R-03, R-04와 canonical JSON |
| 8/01~8/07 | reporting, worker, API, security limits |
| 8/08~8/12 | 최소 UI, real-API E2E, report downloads |
| 8/13~8/16 | pilot, 오류 수정, evaluation protocol freeze |
| 8/17~8/20 | final experiment와 결과 자동 생성 |
| 8/21~8/23 | 전체 CI, Docker, release, code/data freeze |
| 8/24~8/30 | 3쪽 연구 설명서, 재현성·출처·한계 문서 정리 |
| 8/31~9/02 | 제출용 offline bundle, hash, external validation 최종 확인 |
| 9/03~9/04 | 비상 버퍼; 신규 기능 금지 |

## 13. 패널 제작자에게 넘길 개발·연구 evidence pack

패널 자체는 만들지 않지만, 아래 데이터는 8/23까지 단일 source of truth로 제공한다.

- `RULE_CATALOG.md`
- `DATASET_CARD.md`
- representative clean/faulty/authorized/corrected IFC
- 최종 IDS와 optional BCFZIP
- `ground_truth.json`, `mutation_manifest.json`
- raw per-case JSON/CSV
- aggregate metrics JSON/CSV
- runtime과 결정성 결과
- experiment commit, dependency lock, seed, 모든 input/output hash
- one-command reproduction guide와 실제 run log
- BCF/IFC 독립 도구 open evidence
- 실패 사례와 negative result
- 정확한 limitation·assurance-boundary 문구
- third-party library, Codex/AI 사용, 학생 본인 기여 고지
- live demo 장애 대비 offline sample/result bundle
- final CI URL, deployment smoke, current README/HANDOFF
- 패널에 사용할 숫자와 캡션의 machine-generated `panel_facts.json`

기존 전체 pytest 개수를 IFC 연구 검증 건수로 제시하지 않는다. 공모전 근거는 새 fault-level corpus와
benchmark 결과로 별도 제시한다.

## 14. 첫 착수 순서

1. 현재 `main@40dd132`에서 전체 local gate를 실행해 baseline을 기록한다.
2. `codex/bim-awards-2026` 브랜치를 만든다.
3. `ifctester`/BCF dependency, license, Linux container spike를 수행한다.
4. `virtual-fab-v1` profile과 대표 clean IFC 하나를 생성한다.
5. IDS 한 규칙으로 PASS/FAIL을 만든 뒤에만 전체 개발을 시작한다.

## 15. 참고 자료

- [BIM Awards 2026 공식 페이지](https://event.buildingsmart.or.kr/Awards/2026)
- [BIM Awards 2026 운영지침 PDF](https://buildingsmart.or.kr/NewsFile/BIM%20AWARDS%202026%20%EA%B3%B5%EB%AA%A8%20%EB%B0%8F%20%EC%9A%B4%EC%98%81%20%EC%A7%80%EC%B9%A8_V1.66_2026.pdf)
- [buildingSMART IDS](https://www.buildingsmart.org/standards/bsi-standards/information-delivery-specification-ids/)
- [buildingSMART BCF](https://info.buildingsmart.org/standards/bsi-standards/bim-collaboration-format/)
- [IfcTester 0.8.5 documentation](https://docs.ifcopenshell.org/ifctester.html)
- [IfcOpenShell geometry settings](https://docs.ifcopenshell.org/ifcopenshell/geometry_settings.html)

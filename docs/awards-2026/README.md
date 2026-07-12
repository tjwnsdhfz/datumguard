# BIM Awards 2026 · OpenBIM Evidence Guard

이 폴더는 학생부 Research 출품 후보 `OpenBIM Evidence Guard`의 구현, protocol, 데이터셋,
최종 실험 evidence를 연결하는 단일 진입점이다. 패널 디자인과 편집은 사용자가 담당한다.

## 현재 상태

- OpenBIM source와 `/openbim` 웹 경로는 v0.3.0 production source
  [`472df5fe...`](https://github.com/tjwnsdhfz/datumguard/commit/472df5fe431277244fc0fcda1ee9aa3b6284ddff)에 포함됐다.
- 공개 Render에서는 `DATUMGUARD_ENABLE_OPENBIM=false`, `DATUMGUARD_ENABLE_BCF=false`이므로
  hosted evidence 실행과 BCF export는 fail-closed 상태다. 웹 경로 공개를 검증 서비스 운영이나
  산업 적용으로 해석하지 않는다.
- 별도 `/openbim` 연구용 workspace와 `POST /api/v1/openbim/evidence/run`을 구현했다.
- IFC4 baseline/candidate와 IDS 1.0을 독립 worker에서 다시 열어 정보요구조건, IFC integrity,
  project AABB clearance와 protected revision을 검사한다.
- 37개 결정론적 합성 case를 생성했고, pilot 6개를 제외한 held-out evaluation 30개를 실행했다.
- Full pipeline 결과는 TP/FP/FN `330/0/0`, clean·authorized false positive `0`, corrected 신규 issue
  `0`이다. 이는 합성 연구 결과이며 승인 자격을 만들지 않는다.
- GEO-01 경계 회귀에서 AABB 접촉과 +1mm 이격은 PASS, -1mm 양의 중첩은 FAIL이며,
  geometry 누락은 PASS가 아니라 `NOT_EVALUABLE`로 처리했다.
- 120 candidate record의 measured engine run 1,200회에서 engine error 0, canonical payload
  10/10 일치, engine p95 1,876.222ms를 기록했다.
- A→B, B→C, C→D의 고정 분모 recall 기여는 각각 `+0.181818182`였고, 30개 case paired
  mean·median도 모두 같은 값이었다.
- 전체 감지 issue 360개는 source hash·등록 rule ID `360/360`, entity reference `330/360`이며,
  primary issue 330개는 세 항목 모두 `330/330`이다. entity 없는 IFC-00 진단 30개를 숨기지 않는다.
- 최초 evaluator의 두 구현 오류는 raw detector report를 byte 보존한 뒤 `analysis-v1.0.2`에서
  재집계했다. zero-support 정책이 사전등록되지 않은 supported-rule macro-F1은 post-freeze
  sensitivity로만 보고하며 Information·Revision 가설은 `NOT_CONCLUSIVE`다.

## 문서와 증거

- [개발 계획](DEVELOPMENT_PLAN.md)
- [연구 계획](RESEARCH_PLAN.md)
- [동결 protocol](protocol.yaml)
- [규칙 카탈로그](RULE_CATALOG.md)
- [데이터셋 카드](DATASET_CARD.md)
- [최종 결과](RESULTS.md)
- [한계·타당성 위협](LIMITATIONS.md)
- [제3자 라이브러리·AI 사용 고지](THIRD_PARTY_AND_AI_USE.md)
- [machine-generated evidence](evidence/README.md)
- [외부 IFC·BCF validation audit](evidence/external_validation_audit.json)
- [제3자 package license audit](evidence/third_party_license_audit.json)
- [post-freeze correction audit](evidence/ANALYSIS_CORRECTION.md)
- [최초 engine run 보존 index](evidence/PRESERVED_ENGINE_RUN.md)
- [대표 JSON·HTML·BCF bundle](evidence/representative/README.md)

## 고정 경계

- 기존 `/intake`는 외부 artifact의 informational audit로 유지하고 `/openbim`과 섞지 않는다.
- IDS 정보 검사와 DatumGuard의 project geometry/revision 규칙을 구분한다.
- AI/LLM은 IFC 판정, ground truth 생성과 metric 계산 경로에서 제외한다.
- 실제 FAB·기업 자료 없이 IFC4 합성 데이터만 사용한다.
- `research_validation_only=true`, `approval_eligible=false`를 고정한다.
- BCF는 same-library round-trip 외에 buildingSMART BCF 3.0 공식 checker와 독립 .NET XSD·의미
  검증까지 통과했다. BIMcollab Zoom은 공식 지원 범위가 BCF 2.1까지라 BCF 3.0 판정에 사용하지 않으며,
  BCF 3.0 graphical viewer와 license gate가 끝나기 전 핵심 성과로 주장하지 않는다.
- API의 BCF packaging은 별도 `DATUMGUARD_ENABLE_BCF=false` gate로 기본 차단한다.
- `/openbim` 웹 경로는 v0.3.0에 배포됐지만 hosted API 실행은 비활성인 research preview다.
- Render production은 외부 gate 완료 전 `DATUMGUARD_ENABLE_OPENBIM=false`와
  `DATUMGUARD_ENABLE_BCF=false`로 고정한다.

## v0.3.0 통합·배포 증거

- Main SHA: [`472df5fe431277244fc0fcda1ee9aa3b6284ddff`](https://github.com/tjwnsdhfz/datumguard/commit/472df5fe431277244fc0fcda1ee9aa3b6284ddff)
- CI: [run `29194952632`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29194952632) — 376 pytest, 35 Playwright, OpenBIM interoperability와 두 container build 성공
- Security: [run `29194952607`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29194952607) — pip audit와 Python·JavaScript/TypeScript CodeQL 성공
- Production deployments: Vercel `5413026696`; Render `5413009032` / `dep-d99pkfeq1p3s73d3gjj0`
- Strict smoke: [run `29195107475`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29195107475) 성공

위 CI는 source·브라우저·container의 회귀를 검증한다. strict production smoke는 OpenBIM-enabled
API canary를 수행하지 않으며, 공개 Render의 OpenBIM gate가 꺼져 있다는 경계를 바꾸지 않는다.
v0.2.1은 production rollback baseline이다.

## 동결 provenance

| 역할 | Git tag | Commit |
|---|---|---|
| protocol·fixture·detector engine run | `protocol-v1` | `40f1f7a991e592511033a480c6799516578a45f8` |
| 최초 evaluator correction 이력 | `analysis-v1.0.1` | `0ed7ff7716e9f625998a1a17342de9f9fa9cd9b9` |
| 최종 evaluator correction·metric interpretation | `analysis-v1.0.2` | `9d147e30aa33a7c3571a83174d6b18a557662880` |

최초 raw SHA-256은
`sha256:58dcf7dc75246c9e884f4ad31be8709ff480e58c37a811d569f0fa779f7df1e9`,
수정 후 raw SHA-256은
`sha256:fd1fb788c67d231a6d344c9297ba730058c419c7473d4b32f13276261229d33c`이다.

## 전체 detector 실험 재현

다음 명령은 37개 case를 다시 생성해 byte 결정성을 확인하고 evaluation 30개에 warm-up 1회,
측정 10회를 수행한다. 기존 공식 raw를 덮어쓰지 않도록 별도 evidence directory에서 먼저 실행한다.

```powershell
uv run --frozen python tools/run_openbim_experiment.py --regenerate-dataset `
  --split evaluation --warmup-runs 1 --repeats 10 --bootstrap-iterations 10000 `
  --evidence-dir C:\external-evidence\full-reproduction `
  --results-path C:\external-evidence\full-reproduction\RESULTS.md
```

## 동결 후 evaluator correction 재현

detector를 다시 실행하지 않고 보존 raw의 engine report만 재집계하려면 preserved raw를 repo 밖에
복사한 뒤 `analysis-v1.0.2`를 checkout한 별도 clean worktree에서 실행한다. source SHA-256,
tag-to-HEAD, protocol, dataset manifest, truth, IFC input hash와 10/10 결정성 중 하나라도 다르면
시작 전에 실패한다.

```powershell
uv run --frozen python tools/run_openbim_experiment.py --reanalyze-existing `
  --reanalyze-source C:\external-evidence\raw_results_pre_analysis_fix.jsonl `
  --expected-source-sha256 sha256:58dcf7dc75246c9e884f4ad31be8709ff480e58c37a811d569f0fa779f7df1e9 `
  --analysis-tag analysis-v1.0.2 --split evaluation --repeats 10 `
  --bootstrap-iterations 10000
```

## 제출 전 외부 gate 상태

1. BCF 3.0 지원을 명시한 독립 viewer에 대표 `.bcf`를 import하고 component/status를 화면 증거로
   남기는 gate는 열려 있다. BIMcollab Zoom 9.8.14는 BCF 2.1까지만 지원하므로 판정 대상에서 제외했다.
2. buildingSMART IFC Validation Service는 로그인 불가로 업로드하지 않았고 hosted 결과를 주장하지 않는다.
3. `bcf-client==0.8.5` source/wheel license 표기 차이는 upstream 확인 전 공개 BCF 배포를 차단한다.
4. PR의 Docker/Linux CI·container·SBOM·security와 preview deployment smoke는 통과했다. OpenBIM
   production runtime은 계속 비활성이라 production·부하 검증으로 확대 해석하지 않는다.
5. OpenBIM gate를 켠 별도 후보 환경에서 cold-start·CORS·최대 입력·동시성 smoke를 실행한다.
6. 공모전 원고에서 실제 산업 일반화, 안전·법규·제작 승인 표현을 제거한다.

이 외부 gate는 구현·합성 실험의 완료 여부와 분리해 공개하며, 미완료 상태를 성과로 바꾸어 쓰지 않는다.

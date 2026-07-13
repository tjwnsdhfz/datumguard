# 연구 한계와 타당성 위협

## 데이터·모델 범위

- 실제 FAB가 아닌 코드 생성 합성 IFC4만 사용했다.
- 세 layout, box geometry, 0/90/180/270도 회전, 최대 48개 검사 자산으로 제한된다.
- AABB service envelope는 곡선·오목 형상·정밀 solid clash를 표현하지 못한다.
- custom property와 clearance 값은 교육용 project contract다.
- GlobalId revision persistence는 IFC schema 자체의 보편 규칙이 아니다.
- generator와 detector 개발 주체가 같아 oracle leakage 가능성이 있다.
- IfcTester 결과를 모든 IDS checker의 결과로 일반화할 수 없다.
- 사람 대상 사용성 실험이 없어 실무 시간 절감이나 사용성을 입증하지 않는다.

## 실제 최종 결과의 해석

- held-out evaluation은 30 case, 120 candidate record, 1,200 measured engine run이다.
- 수정 후 합성 fault 330건에서 Full pipeline TP/FP/FN은 330/0/0이었다.
- clean·authorized candidate의 false positive와 corrected candidate의 신규 issue는 모두 0건이었다.
- 최종 false negative와 실패 layout은 없지만, 이는 정해진 generator와 fault catalog 안의 결과다.
- engine median은 1,272.713ms, p95는 1,876.222ms였다. 최대 engine 4,902.467ms와 최대 wall
  6,938.4894ms는 `EVAL-L3-S2309/v0_clean/repeat 4`에서 관찰됐다.
- 완벽한 합성 corpus 성능을 실제 산업 IFC, 제작 가능성, 안전, 법규 또는 시공 승인 성능으로
  일반화하지 않는다.

## 외부·배포 gate

- OpenBIM source와 웹 route는 v0.3.0 production source `472df5fe...`에 포함됐고, 통합 CI
  [run `29194952632`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29194952632)는 376 pytest,
  35 Playwright, OpenBIM interoperability와 container build를 통과했다. 이는 연구 소스의 통합
  회귀 증거이지 실사업장 또는 구조 안전 검증이 아니다.
- Vercel `5413026696`, Render `5413009032` / `dep-d99pkfeq1p3s73d3gjj0`와 strict smoke
  [run `29195107475`](https://github.com/tjwnsdhfz/datumguard/actions/runs/29195107475)는 v0.3.0 SHA
  `472df5fe...` 배포를 증명한다. 다만 production Render는 `DATUMGUARD_ENABLE_OPENBIM=false`,
  `DATUMGUARD_ENABLE_BCF=false`이므로 hosted OpenBIM evidence canary·cold-start·CORS·부하 검증을
  완료한 것이 아니다.
- IDS는 고정 XSD와 IfcTester에서 검증했지만 별도 상용 checker 교차검증은 하지 않았다.
- buildingSMART IFC Validation Service는 로그인 필요 화면까지 확인했지만 계정을 만들거나 파일을
  업로드하지 않아 clean 대표 IFC의 hosted 결과는 아직 보존하지 못했다. 오프라인
  `ifcopenshell.validate(express_rules=True)`에서는 clean·authorized·corrected가 schema statement 0,
  faulty가 의도한 `IfcRoot.UR1` 중복 GlobalId 1건이었으나 hosted 결과로 대체해 주장하지 않는다.
- BCF는 `bcf-client` semantic round-trip, buildingSMART BCF 3.0 tag의 공식 `bcf-tool 1.0.7`, 공식
  XSD 26/26, `bcf-client`를 쓰지 않은 .NET 의미 검사 482/482를 통과했다. 그러나 독립 graphical
  BCF viewer import, component 시각 확인, full-corpus BCF 평가는 완료하지 않아 조건부 viewer
  연구 gate는 아직 미통과다.
- `bcf-client==0.8.5` wheel의 GPLv3 classifier와 현재 IfcOpenShell source 표의
  LGPL-3.0-or-later 표기가 일치하지 않는다. `ifctester`가 이를 전이 설치하므로 최종 배포 license
  검토 전 `ifctester`도 `openbim`/`dev` extra로 분리하고, BCF 직접 pin은 `bcf`/`dev` extra에만 둬
  base Docker distribution과 기본 Web 요청에서 제외한다.
- 이 Windows 환경에는 Docker CLI가 없었지만 원격 Ubuntu CI에서 backend/web Docker build, SBOM과
  fixed-critical scan이 통과했다. 이 결과는 Docker/Linux 회귀 gate를 닫지만 OpenBIM-enabled hosted
  실행이나 외부 viewer·license gate를 대신하지 않는다.
- `/openbim`은 공개 웹 route가 있는 research preview다. API source는 배포 image에 포함되지만
  production gate가 꺼져 있으므로 hosted 실행·cold-start·CORS·부하 smoke는 완료되지 않았다.

## 완화 조치

- generator, detector, truth source와 evaluator를 파일 수준에서 분리했다.
- pilot 6개와 held-out evaluation 30개 seed를 분리했다.
- protocol, rule, matching key와 목표를 결과 전에 `protocol-v1`로 동결했다.
- serialize 후 새 process에서 IFC를 다시 열고 input/output hash를 보존했다.
- primary와 admissible cross-scope alert를 분리해 cascade를 숨기지 않았다.
- ablation, raw result, parse failure, evaluator correction과 negative finding을 공개했다.
- 최초 engine 환경·summary·raw bytes를 보존하고 별도 clean analysis tag에서 재집계했다.

## 일정 deviation

계획 문서의 8월 freeze/final 날짜보다 앞선 2026-07-12에 protocol freeze와 evaluation을 실행했다.
달력 일정은 변경됐지만 순서는 `pilot → protocol freeze → clean engine run → 별도 analysis correction`으로
유지했다. 공모전 제출 전 외부 viewer·license·CI gate 결과가 추가되면 기존 raw result나 protocol을
덮어쓰지 않고 별도 evidence로 남긴다.

<!-- ANALYSIS_CORRECTION_START -->
## Post-freeze 평가 구현 수정

동결된 engine report를 처음 집계할 때 GEO-01 pair key와 ablation recall denominator 구현 오류가 발견됐다.

- 영향 case union: 30개
- GEO-01 pair 영향: 4개 case
- ablation denominator 영향: 30개 case
- 최초 full TP/FP/FN: 326/4/4
- 최초 Geometry F1: 0.933333333
- 수정 후 full TP/FP/FN: 330/0/0
- 수정 후 Geometry F1: 1.0
- engine 재실행 없음; detector, 입력, truth, 규칙, threshold 변경 없음
- 원본 byte는 `evidence/raw_results_pre_analysis_fix.jsonl`로 보존
- information/revision supported-rule macro-F1은 zero-support 정책을 사전등록하지 않아 post-freeze sensitivity로만 보고

이는 모델 성능 수정이 아니라 사전등록한 matching/ablation 정의에 분석 코드를 일치시킨 post-freeze evaluator correction이다.
<!-- ANALYSIS_CORRECTION_END -->

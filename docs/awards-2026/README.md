# BIM Awards 2026 준비 문서

이 폴더는 DatumGuard를 학생부 Research 출품작 `OpenBIM Evidence Guard`로 확장하기 위한 개발·연구
작업의 단일 진입점이다. 패널 디자인과 편집은 사용자가 담당하며 이 폴더의 작업 범위에서 제외한다.

## 문서

- [개발 계획](DEVELOPMENT_PLAN.md)
- [연구 계획](RESEARCH_PLAN.md)

## 현재 결정

- 기존 `/intake`는 유지하고 별도 `/openbim` 수직 기능을 만든다.
- core 연구는 IDS 정보요구조건, IFC integrity, protected revision, 재현 가능한 오류주입 평가다.
- clearance와 BCF는 2026-07-19 hard gate를 통과한 경우에만 제목·연구 주장에 포함한다.
- AI/LLM은 판정 실험에서 제외한다.
- 실제 FAB·기업 자료 없이 IFC4 합성 데이터만 사용한다.
- 2026-08-16 protocol freeze, 2026-08-20 final experiment, 2026-08-23 code freeze를 지킨다.

## 다음 착수 순서

1. 현재 `main` HEAD에서 전체 baseline 검증을 실행하고 결과를 기록한다.
2. 공모전 전용 브랜치를 만든다.
3. IDS, geometry, BCF dependency·container·license spike를 수행한다.
4. 대표 clean IFC와 IDS 한 규칙으로 PASS/FAIL vertical slice를 만든다.
5. 대표 fixture와 ground truth가 결정론적으로 생성된 뒤 detector 구현을 시작한다.

완료되지 않은 목표 수치나 기능을 현재 성과로 표현하지 않는다.

## 한 명령 재현

다음 명령은 37개 case를 다시 생성하고 전체 byte hash 결정성을 확인한 뒤, pilot/representative를
제외한 evaluation 30개에 warm-up 1회와 측정 10회를 실행한다.

```powershell
uv run python tools/run_openbim_experiment.py --regenerate-dataset `
  --split evaluation --warmup-runs 1 --repeats 10 --bootstrap-iterations 10000
```

결과는 `docs/awards-2026/evidence/`와 `RESULTS.md`에 machine-generated 파일로 기록된다.

### 동결 후 evaluator correction 재현

detector를 다시 실행하지 않고 보존한 engine report만 재집계할 때는 clean analysis tag에서 다음을
실행한다. source SHA-256, tag-to-HEAD, protocol, dataset manifest, truth, IFC input hash와 10/10
결정성이 모두 일치하지 않으면 시작 전에 실패한다.

```powershell
uv run python tools/run_openbim_experiment.py --reanalyze-existing `
  --reanalyze-source C:\external-evidence\raw_results.jsonl `
  --expected-source-sha256 sha256:58dcf7dc75246c9e884f4ad31be8709ff480e58c37a811d569f0fa779f7df1e9 `
  --analysis-tag analysis-v1.0.1 --split evaluation --repeats 10 `
  --bootstrap-iterations 10000
```

이 경로는 원본 byte를 `raw_results_pre_analysis_fix.jsonl`로 보존하고 detector field만 남긴
`raw_engine_results.jsonl`, 수정된 집계, `analysis_correction.json`, `ANALYSIS_CORRECTION.md`를 만든다.

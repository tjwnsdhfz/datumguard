# Machine-generated research evidence

이 폴더의 JSON/CSV/log는 `tools/run_openbim_experiment.py`가 생성한다. raw·aggregate 파일을 수동으로
편집하지 않는다. `RESULTS.md`보다 다음 원자료가 우선한다.

- `environment.json`
- `fixture_manifest.json`
- `raw_results.jsonl`
- `per_case.csv`
- `metrics.csv`
- `bootstrap_summary.json`
- `experiment_summary.json`
- `panel_facts.json`
- `reproduction.log`

post-freeze evaluator correction을 수행한 경우 다음 audit 파일도 생성한다.

- `raw_results_pre_analysis_fix.jsonl`: 최초 집계가 포함된 원본 byte 보존본
- `raw_engine_results.jsonl`: detector report와 runtime/determinism만 보존한 분석 입력
- `analysis_correction.json`, `ANALYSIS_CORRECTION.md`: 수정 이유·commit·hash·metric 영향

아직 생성되지 않은 metric은 공모전 성과로 사용하지 않는다.

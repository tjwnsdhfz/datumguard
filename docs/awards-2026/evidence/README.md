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
- `engine_environment_protocol_v1.json`: 최초 detector 실행의 clean Git·OS·package 환경 보존본
- `experiment_summary_pre_analysis_fix.json`: 수정 전 자동 집계 summary 보존본
- `engine_reproduction_protocol_v1.log`: 최초 detector 실행 명령·hash 보존본
- `PRESERVED_ENGINE_RUN.md`: 위 보존본의 역할과 SHA-256 index
- `third_party_license_audit.json`: IfcTester/BCF wheel hash, source snapshot, dependency와 metadata conflict audit
- `external_validation_audit.json`: hosted login 상태, offline IFC schema, 공식 BCF checker와 독립 semantic audit

최종 corrected metric은 생성되었다. 다만 합성 데이터 결과를 실제 FAB 승인·안전·법규 적합성으로
확대하지 않으며, 공식 BCF checker 통과를 graphical viewer import나 배포 license 완료로 표현하지 않는다.

- 최종 analysis tag: `analysis-v1.0.2`
- analysis commit: `9d147e30aa33a7c3571a83174d6b18a557662880`
- 보존 pre-fix raw: `sha256:58dcf7dc75246c9e884f4ad31be8709ff480e58c37a811d569f0fa779f7df1e9`
- corrected raw: `sha256:fd1fb788c67d231a6d344c9297ba730058c419c7473d4b32f13276261229d33c`
- detector rerun: `false`

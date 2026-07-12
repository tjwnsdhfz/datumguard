# Preserved protocol-v1 engine run

최초 detector 실행과 수정 후 analysis replay를 분리하기 위한 hash index다. 아래 파일은
`protocol-v1` commit `40f1f7a991e592511033a480c6799516578a45f8`에서 수행한 최초 실행을
byte 단위로 보존한다.

| 파일 | 역할 | SHA-256 |
|---|---|---|
| `raw_results_pre_analysis_fix.jsonl` | 최초 engine report와 최초 evaluator 결과 120 records | `sha256:58dcf7dc75246c9e884f4ad31be8709ff480e58c37a811d569f0fa779f7df1e9` |
| `engine_environment_protocol_v1.json` | 최초 실행 환경과 clean Git provenance | `sha256:71e378ec623c4ef7c570671737077181224a4f5bd52c2935099c925775b4b79d` |
| `experiment_summary_pre_analysis_fix.json` | 최초 자동 집계 326/4/4 summary | `sha256:47ef83149dd88ebf1516b36bd06229ae5c5c8957daa4ebb8c64a1ef06ee802cb` |
| `engine_reproduction_protocol_v1.log` | 최초 실행 명령과 source hash | `sha256:9b02ee29a9009fd2082259dde480b24b3c38df0349ad46bdeb4cbce2a61971fd` |

`analysis-v1.0.1` commit `0ed7ff7716e9f625998a1a17342de9f9fa9cd9b9`는 첫 correction 이력이다.
최종 `analysis-v1.0.2` commit `9d147e30aa33a7c3571a83174d6b18a557662880`는 detector를
재실행하지 않고 위 raw source에서 evaluator field를 다시 계산하고, zero-support 정책이 동결되지 않은
macro-F1을 post-freeze sensitivity로 분리했다. GEO pair 영향 4개 case, ablation denominator 영향
30개 case와 전후 metric은 `ANALYSIS_CORRECTION.md`와 `analysis_correction.json`에 기록한다.

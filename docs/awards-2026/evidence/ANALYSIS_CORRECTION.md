# Analysis correction audit

The frozen detector run was not repeated. IFC/IDS inputs, detector outputs, truth, thresholds, and rules were unchanged.

- Frozen engine commit: `40f1f7a991e592511033a480c6799516578a45f8`
- Frozen tag: `protocol-v1`
- Analysis commit: `0ed7ff7716e9f625998a1a17342de9f9fa9cd9b9`
- Analysis tag: `analysis-v1.0.1`
- Preserved pre-fix raw SHA-256: `sha256:58dcf7dc75246c9e884f4ad31be8709ff480e58c37a811d569f0fa779f7df1e9`
- Raw engine-only SHA-256: `sha256:87b7d2edfda50dbe1c6d09bfd63f0cc9995df623911c62340115c3fe9d98b32e`
- Affected cases: EVAL-L1-S2102, EVAL-L2-S2202, EVAL-L2-S2206, EVAL-L3-S2308
- Fixed primary-fault denominator: 330

## Corrected evaluator defects

1. `EVAL-GEO-PAIR-01`: GEO-01 now uses the preregistered sorted raw GlobalId pair. STEP IDs remain audit evidence for duplicate-GlobalId cases.
2. `EVAL-ABLATION-DENOM-01`: all ablations retain the same primary-fault recall denominator; only predictions are scope-filtered.
3. `EVAL-METRIC-MACRO-01`: information and revision target macro-F1 values are computed across supported rule-level F1 values within each family.

## Metric effect

- Preliminary full TP/FP/FN: 326/4/4
- Preliminary Geometry F1: 0.933333333
- Corrected full TP/FP/FN: 330/0/0
- Corrected Geometry F1: 1.0

This is an automated reanalysis of preserved reports, not manual editing of raw data.

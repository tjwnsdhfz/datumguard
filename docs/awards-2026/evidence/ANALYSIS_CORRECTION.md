# Analysis correction audit

The frozen detector run was not repeated. IFC/IDS inputs, detector outputs, truth, thresholds, and rules were unchanged.

- Frozen engine commit: `40f1f7a991e592511033a480c6799516578a45f8`
- Frozen tag: `protocol-v1`
- Analysis commit: `9d147e30aa33a7c3571a83174d6b18a557662880`
- Analysis tag: `analysis-v1.0.2`
- Preserved pre-fix raw SHA-256: `sha256:58dcf7dc75246c9e884f4ad31be8709ff480e58c37a811d569f0fa779f7df1e9`
- Raw engine-only SHA-256: `sha256:87b7d2edfda50dbe1c6d09bfd63f0cc9995df623911c62340115c3fe9d98b32e`
- Affected case union: 30 cases
- EVAL-GEO-PAIR-01: 4 cases (EVAL-L1-S2102, EVAL-L2-S2202, EVAL-L2-S2206, EVAL-L3-S2308)
- EVAL-ABLATION-DENOM-01: 30 cases (EVAL-L1-S2101, EVAL-L1-S2102, EVAL-L1-S2103, EVAL-L1-S2104, EVAL-L1-S2105, EVAL-L1-S2106, EVAL-L1-S2107, EVAL-L1-S2108, EVAL-L1-S2109, EVAL-L1-S2110, EVAL-L2-S2201, EVAL-L2-S2202, EVAL-L2-S2203, EVAL-L2-S2204, EVAL-L2-S2205, EVAL-L2-S2206, EVAL-L2-S2207, EVAL-L2-S2208, EVAL-L2-S2209, EVAL-L2-S2210, EVAL-L3-S2301, EVAL-L3-S2302, EVAL-L3-S2303, EVAL-L3-S2304, EVAL-L3-S2305, EVAL-L3-S2306, EVAL-L3-S2307, EVAL-L3-S2308, EVAL-L3-S2309, EVAL-L3-S2310)
- Fixed primary-fault denominator: 330

## Corrected evaluator defects

1. `EVAL-GEO-PAIR-01`: GEO-01 now uses the preregistered sorted raw GlobalId pair. STEP IDs remain audit evidence for duplicate-GlobalId cases.
2. `EVAL-ABLATION-DENOM-01`: all ablations retain the same primary-fault recall denominator; only predictions are scope-filtered.

## Post-freeze metric interpretation

`METRIC-MACRO-SENSITIVITY-01` reports supported-rule information/revision macro-F1, but does not declare the preregistered hypotheses confirmed because zero-support handling was not frozen.

## Metric effect

| Ablation | Preliminary TP/FP/FN | Corrected TP/FP/FN | Preliminary denominator | Corrected denominator |
|---|---:|---:|---:|---:|
| A | 150/0/0 | 150/0/180 | 150 | 330 |
| B | 210/0/0 | 210/0/120 | 210 | 330 |
| C | 266/4/4 | 270/0/60 | 270 | 330 |
| D | 326/4/4 | 330/0/0 | 330 | 330 |

- Preliminary full TP/FP/FN: 326/4/4
- Preliminary Geometry F1: 0.933333333
- Corrected full TP/FP/FN: 330/0/0
- Corrected Geometry F1: 1.0

This is an automated reanalysis of preserved reports, not manual editing of raw data.

# OpenBIM Evidence Guard 실험 결과

> 이 문서는 실험 러너가 원자료에서 자동 생성했다. 수동 편집하지 않는다.

- 실행 상태: `completed`
- protocol SHA-256: `sha256:d18cf856bde7879d6887091fb4851502d3979ab998ef6f96d6eb22c86c275b36`
- dataset manifest SHA-256: `sha256:317a68807ddefd0ca3854261fed28b4e5fd166056a68e0925f255435f8e7c7c8`
- 완료 candidate run: 120
- 측정 engine run: 1200
- engine error: 0
- 판정 용도: synthetic research validation only; approval eligible: `false`

## Full pipeline (Ablation D)

- TP/FP/FN: 330/0/0
- Precision: 1.000000
- Recall: 1.000000
- F1: 1.000000
- Family macro-F1: 1.000000

## Ablation recall on the fixed primary-fault denominator

- A: TP 150, FP 0, FN 180, Recall 0.454545, F1 0.625000
- B: TP 210, FP 0, FN 120, Recall 0.636364, F1 0.777778
- C: TP 270, FP 0, FN 60, Recall 0.818182, F1 0.900000
- D: TP 330, FP 0, FN 0, Recall 1.000000, F1 1.000000

## Incremental recall contribution

- A_to_B: +0.181818
- B_to_C: +0.181818
- C_to_D: +0.181818

## Paired per-case incremental recall

- A_to_B: cases 30, mean +0.181818, median +0.181818, range [+0.181818, +0.181818]
- B_to_C: cases 30, mean +0.181818, median +0.181818, range [+0.181818, +0.181818]
- C_to_D: cases 30, mean +0.181818, median +0.181818, range [+0.181818, +0.181818]

## Fault-family F1

- Geometry: micro-F1 1.000000; supported-rule macro-F1 1.0
- IFC Identity: micro-F1 1.000000; supported-rule macro-F1 1.0
- Information: micro-F1 1.000000; supported-rule macro-F1 1.0
- Integrity: micro-F1 1.000000; supported-rule macro-F1 1.0
- Revision: micro-F1 1.000000; supported-rule macro-F1 1.0

## Preregistered target assessment

- Information macro-F1 >= 0.95: **NOT_CONCLUSIVE** (post-freeze sensitivity 1.0; mean F1 across supported rules only) — post-freeze supported-rule macro; zero-support policy not preregistered
- Geometry F1 >= 0.95: **PASS** (actual 1.0)
- Revision macro-F1 >= 0.95: **NOT_CONCLUSIVE** (post-freeze sensitivity 1.0; mean F1 across supported rules only) — post-freeze supported-rule macro; zero-support policy not preregistered
- Clean false positives = 0: **PASS** (actual 0)
- Authorized false positives = 0: **PASS** (actual 0)
- Engine p95 < 5000 ms: **PASS** (actual 1876.2216)

## Controls and reproducibility

- Clean false positives: 0
- Authorized false positives: 0
- Corrected new issues: 0
- Corrected closure rate: 1.000000
- Deterministic candidate runs: 120/120
- Median engine runtime: 1272.713 ms
- p95 engine runtime: 1876.222 ms
- p95 wall runtime: 2811.616 ms
- Canonical JSON determinism covers timestamp/run-ID-excluded engine payloads only.
- BCFZIP byte determinism was not part of the repeated-run experiment.

## Issue traceability

- All detected issues — source hash coverage: 360/360
- All detected issues — registered rule ID coverage: 360/360
- All detected issues — entity reference coverage: 330/360
- Primary issues — source/rule/entity coverage: 330/330, 330/330, 330/330

## Bootstrap

- Iterations: 10000
- Full recall 95% interval: [1.0, 1.0]
- Full minus IDS-only recall 95% interval: [0.545454545, 0.545454545]

## Post-freeze analysis correction

- Revision: `post-freeze-evaluator-fix-2`
- Audit: `evidence/ANALYSIS_CORRECTION.md`
- No engine rerun and no detector, input, truth, rule, or threshold changes.

## Open gates and negative findings

- The first frozen aggregation exposed two evaluator defects; the preserved raw reports were reanalyzed without rerunning the detector.
- Information/revision supported-rule macro-F1 is a post-freeze sensitivity metric; the preregistered hypotheses are not declared confirmed because zero-support handling was not frozen.
- A qualified BCF 3.0 graphical viewer import is not completed. BIMcollab Zoom 9.8.14 was attempted but
  officially supports BCF only through 2.1, so it is not counted as a BCF 3.0 validation result.
- Hosted buildingSMART validation was not completed because login was unavailable; no upload is claimed.
- The distribution-license review found an unresolved `bcf-client==0.8.5` source/wheel metadata conflict,
  so BCF remains opt-in and public distribution remains blocked pending clarification.
- Draft PR Docker/Linux CI, container/SBOM/security gates and preview deployment smoke passed; OpenBIM
  production runtime remains intentionally disabled and is not claimed as production validation.
- No detector miss remained in this synthetic corpus after evaluator correction; this is not evidence of performance on real industrial IFC files.

상세 실패와 모든 반복 결과는 `evidence/raw_results.jsonl`을 기준으로 한다. 합성 IFC 결과를
실제 FAB 적합성·안전·법규·시공 승인으로 일반화하지 않는다.

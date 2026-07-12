# OpenBIM Evidence Guard 실험 결과

> 상태: 아직 최종 실험 결과가 생성되지 않았다. 목표값을 실제 성과로 인용하지 않는다.

이 파일은 `tools/run_openbim_experiment.py`의 성공한 evaluation run 뒤 machine-generated 요약으로
갱신한다. 권위 있는 원자료는 `evidence/raw_results.jsonl`, `per_case.csv`, `metrics.csv`와 각 파일의
SHA-256이다.

최종 기록 항목:

- 실행 commit, protocol/profile/IDS/dataset hash
- 완료·실패·제외 case와 이유
- ablation A~D의 TP/FP/FN, precision, recall, F1
- family macro-F1와 전체 micro-F1
- clean·authorized false positive, corrected closure/new issue
- runtime median/IQR/p95와 canonical output 10회 hash 일치
- bootstrap interval과 실제 표본 크기
- negative result, gate 실패, protocol deviation

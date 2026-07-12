# 연구 한계와 타당성 위협

## 현재 고정한 한계

- 실제 FAB가 아닌 코드 생성 합성 IFC만 사용한다.
- 세 layout, box geometry, 0/90/180/270도 회전, 최대 48개 검사 자산으로 제한된다.
- AABB service envelope는 곡선·오목 형상·정밀 solid clash를 표현하지 못한다.
- custom property와 clearance 값은 교육용 project contract다.
- GlobalId revision persistence는 IFC schema 자체의 보편 규칙이 아니다.
- generator와 detector 개발 주체가 같아 oracle leakage 가능성이 있다.
- IfcTester 결과가 모든 IDS checker와 같다고 일반화할 수 없다.
- synthetic fault 분포를 실제 산업 오류 모집단으로 일반화할 수 없다.
- 사람 대상 사용성 실험이 없어 실무 시간 절감이나 사용성을 입증하지 않는다.

## 완화 조치

- generator와 detector 코드 및 truth source를 분리한다.
- pilot 6개와 held-out evaluation 30개 seed를 분리한다.
- protocol, rule, matching key, 목표를 결과 전에 동결한다.
- serialize 후 새 process에서 IFC를 다시 열고 input/output hash를 보존한다.
- primary와 admissible cross-scope alert를 분리해 cascade를 숨기지 않는다.
- ablation, raw result, parse failure, negative result를 모두 공개한다.
- clean IFC/IDS와 조건부 BCF를 독립 도구에서 spot-check한다.

## 결과 후 추가할 항목

최종 실험 뒤 실제 false positive/negative, 실패 layout, runtime outlier, dependency/BCF gate 결과와
protocol deviation을 이 문서에 추가한다. 결과가 사전 목표에 못 미쳐도 protocol이나 raw result를
성과에 맞게 수정하지 않는다.

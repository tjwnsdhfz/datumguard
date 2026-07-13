# BIM Awards 2026 학생부 Research 제출 가이드

- 기준일: 2026-07-13
- 출품 후보: OpenBIM Evidence Guard
- 권장 부문·분야: 학생 / Research
- 공식 접수: [BIM Awards 2026](https://event.buildingsmart.or.kr/Awards/2026)에서 연결하는 Event-us
- 공식 근거: [BIM Awards 2026 공모 및 운영 지침 v1.66](https://buildingsmart.or.kr/NewsFile/BIM%20AWARDS%202026%20%EA%B3%B5%EB%AA%A8%20%EB%B0%8F%20%EC%9A%B4%EC%98%81%20%EC%A7%80%EC%B9%A8_V1.66_2026.pdf)

## 1. 결론

이 작품은 학생부 Design보다 **학생부 Research**에 제출하는 것이 적합하다. 핵심 성과가 하나의
건축 설계안이 아니라 IFC4·IDS 1.0·프로젝트 규칙을 분리한 검증 artifact, 동결 protocol,
합성 오류주입 dataset, held-out 실험과 재현 가능한 evidence이기 때문이다.

제출 시에는 다음 Core title만 사용한다.

> **OpenBIM Evidence Guard: IDS 기반 가상 FAB Utility IFC의 정보요구조건 및 리비전
> 무결성 독립 재검증 연구**

영문 제목:

> **OpenBIM Evidence Guard: Independent Revalidation of IDS-Based Information Requirements
> and Revision Integrity for Virtual FAB Utility IFC Models**

여기서 ‘독립 재검증’은 외부 기관 인증이 아니라, 저장된 IFC bytes를 생성 과정과 분리된 worker에서
다시 열어 검사한다는 뜻이다.

## 2. 공식 참가 조건

| 항목 | 2026 기준 |
|---|---|
| 학생 자격 | 현재 대학·대학교 또는 전일제 석사과정에 학적이 있는 학생. 휴학생 포함 |
| 팀 인원 | 공동 출품 시 4인 이하 |
| 학생 분야 | Design, Construction, Research, OSC Modular |
| 참가비 | 학생 88,000원(부가세 포함) |
| 참가 신청 | 2026-06-22 ~ 2026-09-04 |
| 작품 제출 | 2026-08-24 ~ 2026-09-04 |
| 권장 내부 마감 | 2026-09-02. 공식 마감 전 이틀을 업로드·인쇄 오류 버퍼로 둔다 |

행사 플랫폼의 신청 종료 표시는 2026-09-04 18:00이다. 일정이 변경될 수 있으므로 결제·제출 직전
공식 페이지와 Event-us 신청 화면을 다시 확인한다.

## 3. 제출물

### 디지털 파일

1. BIM Awards 공모참가증 PDF
2. 출품작 설명서 PDF
3. A1 세로 패널 JPG, 300 dpi, 200 MB 미만
4. 참가자 전원의 재학증명서 PDF

### 출력물

1. 서명된 공모참가증
2. 출품작 설명서 1부
3. A1 세로 패널 출력본 1부

패널 제작은 사용자 담당 범위다. 본 폴더의 machine-generated 수치는 패널에 재입력하지 말고
`evidence/panel_facts.json`을 단일 출처로 사용한다.

## 4. 학생 설명서 적용 규칙

학생 출품자는 운영 지침의 별표 2-1 ‘출품 설명서(I)’ 중 해당 항목만 작성한다.

- 최대 3매
- 본문 10 pt
- 줄 간격 160%
- 제목, 개요, 작품 배경, BIM 적용의 주안점을 포함
- 학생은 ROI 분석인 별표 2-2를 작성하지 않음
- 학생은 조직체계·향후 비전인 별표 2-3을 작성하지 않음

편집 가능한 제출 원고는 `COMPETITION_DESCRIPTION.md`와
`BIM_AWARDS_2026_STUDENT_RESEARCH_DESCRIPTION.docx`에 둔다. DOCX는 3쪽으로 고정해 검수한다.
학교명·학과·학년·성명은 제출 전에 실제 정보로 교체한다.

## 5. 설명서의 주장 순서

1. **문제**: IFC export 성공은 정보요구조건과 revision 무결성 충족을 보장하지 않는다.
2. **방법**: IFC schema, IDS 정보요구, 프로젝트 geometry, 프로젝트 revision 계약을 분리한다.
3. **증거**: 저장 IFC를 별도 worker에서 재개방하고 입력·규칙·결과 hash를 남긴다.
4. **평가**: 37개 합성 case 중 pilot 6개를 제외한 held-out 30개를 평가한다.
5. **결과**: 합성 primary fault 330건에서 Full pipeline TP/FP/FN 330/0/0.
6. **정직한 경계**: 실제 학생 IFC·산업 IFC·구조·안전·법규·제작·시공 승인을 입증하지 않는다.

## 6. 사용 가능한 숫자

| 사실 | 제출 표현 |
|---|---|
| 전체 dataset | 대표 1 + pilot 6 + evaluation 30 = 37 case |
| 최종 평가 | held-out 30 case |
| candidate record | 120 |
| 측정 실행 | 1,200 engine run |
| primary fault | 330건 |
| Full TP/FP/FN | 330 / 0 / 0 |
| Full precision·recall·F1 | 1.000 / 1.000 / 1.000 |
| clean·authorized false positive | 각각 0건 |
| engine error | 0건 |
| engine median / p95 | 1,272.713 / 1,876.222 ms |
| primary issue traceability | source hash·rule ID·entity reference 각각 330/330 |

모든 수치 앞에는 ‘합성 corpus에서’라는 범위 한정을 붙인다. 1,200은 서로 다른 모델 수가 아니라
120개 candidate record를 반복 측정한 실행 수다.

## 7. 반드시 남길 한계

- 실제 FAB나 학생 설계 파일이 아닌 코드 생성 IFC4만 평가했다.
- 최대 48개 자산, box geometry, 직교 회전에 한정한다.
- AABB 여유공간 검사는 exact solid clash가 아니다.
- 교육용 `DG_*` property와 `virtual-fab-v1` 계약은 산업 표준이 아니다.
- 사람 대상 사용성 실험이나 시간 절감 효과를 측정하지 않았다.
- Information·Revision supported-rule macro-F1은 zero-support 정책 미동결 때문에
  사후 민감도 분석이며 사전 가설은 `NOT_CONCLUSIVE`다.
- BCF 3.0 graphical viewer 검증과 배포 license gate가 열려 있으므로 BCF는 핵심 성과로 쓰지 않는다.
- 공개 production API는 OpenBIM capability가 비활성이다.

## 8. 사용 금지 문구

- 실제 학생 설계에서 검증 완료
- 산업 현장 적용 완료
- buildingSMART 인증 획득
- BIMcollab에서 BCF 3.0 검증 완료
- IDS가 형상과 revision까지 검증
- 정밀 clash detection
- 1,200개 모델 평가
- 37개 held-out case
- 정보·리비전 macro-F1 목표 통과
- production OpenBIM 검증 서비스 운영 중
- 독립기관 검증

## 9. 제출 전 체크리스트

- [ ] 학생 / Research를 선택했다.
- [ ] 팀이 4인 이하이고 전원의 재학증명서를 준비했다.
- [ ] 국문·영문 제목을 참가증, 설명서, 패널에서 동일하게 썼다.
- [ ] 설명서가 3쪽 이하, 10 pt, 줄 간격 160%다.
- [ ] 학교·학과·학년·성명 placeholder를 모두 실제 정보로 교체했다.
- [ ] `panel_facts.json`과 설명서 숫자가 일치한다.
- [ ] synthetic research boundary와 `approval_eligible=false`를 남겼다.
- [ ] 최초 evaluator 오류와 correction을 숨기지 않았다.
- [ ] BCF·hosted validation·production gate를 완료로 표현하지 않았다.
- [ ] 공모참가증에 필요한 동의 표시와 서명을 완료했다.
- [ ] PDF, JPG, 출력물의 최종 육안 검수를 했다.
- [ ] 2026-09-02까지 제출본을 동결하고 09-03~04는 비상 버퍼로 남겼다.

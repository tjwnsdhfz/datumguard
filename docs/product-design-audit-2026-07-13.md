# DatumGuard Product Design Audit — 2026-07-13

## 감사 범위

- 제품: DatumGuard Architecture accuracy workspace
- 사용자 목표: 샘플 도면을 선택하고 정확한 mm 값을 확인한 뒤, 독립 DXF 재측정 결과를 이해하고 공식 bundle을 내려받거나 실패를 복구한다.
- 검토 화면: 1440×960 desktop idle/PASS/failure, 390×844 mobile
- 시각 기준: 현재 Mission Control 흑백 공학 UI, 기존 local font와 semantic PASS/FAIL 색상

## 근거 화면

1. `docs/assets/audit/product-design-2026-07-13/01-idle-current.png` — 첫 진입 / 검증 대기
2. `docs/assets/audit/product-design-2026-07-13/02-pass-current.png` — 독립 재측정 PASS
3. `docs/assets/audit/product-design-2026-07-13/03-failure-current.png` — export 차단과 제한적 복구
4. `docs/assets/audit/product-design-2026-07-13/04-mobile-current.png` — 390×844 첫 작업 흐름

## Findings

- [P1] 모바일에서 핵심 작업이 첫 화면 아래로 밀린다.
  - 위치: `.arch-topbar`, `.arch-commandbar`, `.arch-scenario-rail`
  - 근거: 390×844 화면에서 2행 workspace navigation, 빈 commandbar, 세로형 step/action이 캔버스보다 먼저 약 700px를 사용한다.
  - 영향: 사용자는 실제 도면과 수치 편집을 보기 전에 긴 안내와 중복 CTA를 통과해야 한다.
  - 개선: navigation을 한 줄 horizontal rail로, 비어 있는 mobile commandbar는 숨기고, step/action은 3열 compact rail로 바꾼다. rail의 primary action은 하단 고정 action과 중복되므로 mobile에서 숨긴다.

- [P1] desktop의 첫 화면에서 ‘설명’, ‘단계’, ‘데모 선택’, ‘실행’의 우선순위가 비슷하다.
  - 위치: `.arch-scenario-rail`
  - 근거: 세 열이 동일한 시각 무게를 가져 사용자가 먼저 눌러야 할 단일 action을 찾기 어렵다.
  - 영향: 제품의 핵심 가치인 독립 재측정보다 UI 탐색이 먼저 필요하다.
  - 개선: intro는 현재 task와 trust state를 설명하고, progress rail은 현재 단계만 강하게, 우측은 하나의 primary action과 secondary scenario controls로 계층화한다.

- [P2] 아직 동작하지 않는 도구가 실제 편집 도구와 같은 위치와 크기를 차지한다.
  - 위치: `.arch-tools`
  - 근거: Wall, Column, Door, Window 비활성 버튼이 Select/Pan과 같은 commandbar에 4개 노출된다.
  - 영향: 구현 범위를 이해하는 데는 도움이 되지만, 현재 할 수 있는 작업의 발견성을 낮추고 화면 폭을 소모한다.
  - 개선: 지원 도구와 후속 도구를 시각적으로 분리하고, 후속 도구는 compact ‘NEXT’ 그룹으로 낮은 대비를 사용한다.

- [P2] evidence anchor 이동 후 상단 고정 chrome이 결과 맥락을 과도하게 가린다.
  - 위치: `.arch-topbar`, `.arch-commandbar`, `#verification`
  - 근거: PASS 화면에서 검증 결과 상단에 넓은 검정 header와 commandbar가 남고, 이전 도면의 하단 일부가 함께 보인다.
  - 영향: 결과가 독립된 승인 화면이 아니라 편집 화면의 부속처럼 보인다.
  - 개선: `scroll-margin-top`을 명시하고 evidence 상태에서는 결과 header와 핵심 수치를 먼저 읽을 수 있도록 spacing과 typography를 강화한다.

- [P2] PASS/FAIL 수치와 hash의 글자 크기·대비가 포트폴리오 시현에서 충분하지 않다.
  - 위치: `.arch-evidence-grid`, `.arch-summary`, `.arch-hashes`
  - 근거: 1440px에서도 label과 hash가 8px 중심이며 핵심 `0.001 mm`, `4/4`, violation count가 작다.
  - 영향: 제품의 차별점인 정확성 근거가 화면 캡처에서 즉시 읽히지 않는다.
  - 개선: metric 카드의 숫자와 semantic state를 키우고, hash는 trace evidence로 유지하되 copyable-looking mono surface로 정리한다.

## 유지할 강점

- 검정/백색 기반 Mission Control 인상과 1px engineering grid
- green은 PASS, red는 차단에만 사용하는 semantic color 규칙
- 실제 SVG plan, 정확한 mm inspector, 독립 verifier와 hash evidence
- 실패 샘플에서 관련 객체 선택과 명시적 `300 → 0 mm` 복구
- desktop drag / mobile numeric edit 경계와 local draft 저장 안내

## 구현 원칙

1. 새로운 디자인 시스템이나 가짜 기능을 만들지 않는다.
2. 기존 `ArchitectureIcon`, local font, tokens, test IDs를 재사용한다.
3. 변경은 Architecture route의 정보 위계·반응형 레이아웃·시각적 가독성에 집중한다.
4. PASS, FAIL, repair, exact input, download 동작을 유지한다.
5. 375px과 1440px에서 horizontal page overflow가 없어야 한다.

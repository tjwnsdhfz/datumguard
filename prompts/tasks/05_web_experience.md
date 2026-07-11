# Task 05 — Public Web Experience

## 먼저 읽기

공통 문서와 Task 01~04 handoff, 공개 schema와 application service를 읽는다.

## 요구사항·선행조건

- DG-FR-001~006, DG-FR-010, DG-FR-013
- DG-NFR-005~009
- Core generate/verify/repair가 transport와 분리됨

## 목표

- Next.js/TypeScript wizard를 구현한다.
- Datum·단위·profile, outline, feature, dimension/constraint 순서의 폼을 제공한다.
- 자연어 제안은 form diff로만 표시하고 사용자 확인 후 반영한다.
- Canonical SVG 미리보기, verification table, repair diff와 gated export UX를 구현한다.
- Draft contract를 IndexedDB에 저장한다.

## 비목표

- 로그인, 서버 project 저장, 협업
- 3D viewer와 Rhino browser control
- 자연어만으로 즉시 export

## 변경 범위·금지

- Web app, client types/API adapter와 web tests만 변경한다.
- Client가 pass/fail이나 approval token을 자체 생성하지 않는다.
- 모호한 proposal을 자동 적용하지 않는다.

## 공개 동작

- `needs_confirmation`, `under_constrained`, `infeasible`의 원인 필드를 직접 연결한다.
- Export는 server approval 없으면 UI와 API 양쪽에서 거부된다.
- 색상 외 icon/text를 제공하고 keyboard로 핵심 폼을 조작할 수 있다.
- LLM provider가 없어도 폼 기반 전체 흐름이 동작한다.

## 필수 테스트·명령

- Typecheck, lint, unit/component tests, production build
- Playwright: 신규 폼→preview→generate→verify→export
- 모호한 자연어 확인, form-text conflict, locked repair 표시
- IndexedDB save/load와 schema migration 거부
- Approval 없는 export 버튼/API 거부

## 완료 기준

- 샘플 plate를 설치 없이 웹에서 설계·검증·다운로드한다.
- Target/actual/deviation/tolerance/evidence가 한 화면에서 보인다.
- 모바일 최소 보기와 데스크톱 편집이 동작한다.

## Handoff

Web API 기대 계약, mock 제거 지점, E2E 명령과 UX 제한을 Task 06에 전달한다. 동일 검사→수정→재검사는 최대 1회다.

# DatumGuard Mission Control 디자인 시스템

DatumGuard의 시현형 MVP는 항공우주 관제 화면에서 느껴지는 절제된 흑백 대비와 공학 계측기의 정보 위계를 차용한다. 특정 기업의 상표, 로고, 고유 그래픽은 사용하지 않으며, 정확성 보증 제품에 필요한 독립적인 `Mission Control` 시각 언어로 재구성한다.

## 1. 설계 원칙

- 제품 chrome은 `#000000` 또는 `#0a0a0a`, 주요 글자는 `#ffffff`, 보조 글자는 `#b8b8c0`을 사용한다.
- 작업 패널과 도면은 cool-white 표면을 유지한다. CAD 선과 치수의 식별성이 장식보다 우선한다.
- 경계는 `#3a3a3f`, `#d7d7dc`, `#e0e0e8`의 1px hairline으로 구분한다. 그림자와 glow는 사용하지 않는다.
- 녹색은 `PASS`와 온라인 준비 상태, 적색은 오류와 차단 상태에만 사용한다. 색상만으로 상태를 전달하지 않고 아이콘과 텍스트를 함께 제공한다.
- 제목과 navigation은 높은 굵기, 짧은 행간, 양의 자간, 영문 대문자 스타일을 사용한다. 좌표, 치수, 공차, hash는 `DM Mono`와 tabular figure를 유지한다.
- 주요 동작은 최소 44px 높이의 outlined pill 또는 고대비 pill로 제공한다. 입력 필드는 숫자 정렬과 정확한 단위 읽기를 위해 직선형 경계를 유지한다.

## 2. 화면 구조

Architecture와 Piping은 동일한 세 영역 구조를 공유한다.

1. 검은색 topbar: 제품, 현재 contract/revision, 공학 도메인 전환
2. cool-white commandbar: 편집 도구, undo/redo, zoom, snap
3. model tree / drawing paper / exact-property inspector

Plate는 소개 화면과 설계 form을 함께 사용하므로, 검은색 mission hero에서 정확성 보증을 설명한 뒤 밝은 제작 console로 전환한다. 세 화면 모두 검증 결과를 `contract → writer → independent reader → approval gate` 순서로 제시한다.

## 3. 반응형·접근성

- `900px` 미만에서는 CAD drag를 비활성화하고 수치 입력, 검증, 다운로드를 유지한다.
- navigation은 작은 화면에서 핵심 도메인 전환만 남긴다.
- keyboard focus는 2–3px 고대비 outline과 offset으로 표시한다.
- 모든 icon-only control은 접근 가능한 이름을 갖고, 클릭 대상은 44px 이상이다.
- `prefers-reduced-motion`에서 spinner 이외의 전환을 사실상 제거하고 spinner도 정지 상태로 표시한다.
- runtime webfont를 요청하지 않고 저장소에 포함된 글꼴만 사용해 시현 캡처와 배포 화면의 차이를 줄인다.

## 4. 도면 예외

공학 도면은 흑백 marketing surface가 아니다. 벽, opening, datum, collision, keepout 등은 측정과 오류 위치를 빠르게 식별하기 위해 제한된 기능색을 허용한다. 공식 판정은 독립 DXF verifier의 structured evidence가 담당하며, 화면 색상은 판정 근거를 대체하지 않는다.

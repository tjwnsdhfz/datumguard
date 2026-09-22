# 응답 수신 안정성 개선

## 문제와 수정
기존 API 클라이언트는 HTTP 헤더를 받은 직후 타이머와 취소 리스너를 해제했다. 이후 본문 스트림이 멈추면 작업이 끝나지 않았다. 이제 response.text()까지 같은 시간 제한·취소 신호를 유지한다. POST 자동 재시도 금지는 유지한다.

## 검증
- npm run test:unit: 본문 지연 timeout, 본문 중 caller abort, 성공·503 응답 및 POST 단일 시도 3개 통과.
- 타입 검사·lint·프로덕션 빌드 통과.
- Python: 413 passed, 6 skipped. 별도 기존 Python 환경의 의존성을 사용하고 PYTHONPATH는 이 복제본 src로 지정했다.
- CI에 API 클라이언트 회귀 테스트 추가.

## 남은 실사용 검증
이번 작업에서는 CAD 전체 브라우저 E2E 및 Rhino/Grasshopper 실제 모델 왕복, 호스팅 cold start·대형 업로드 부하를 재검증하지 않았다. 기존 release 증거와 이번 수정 검증을 구분한다. FrameGuard와 OpenBIM의 기존 적용 한계·승인 차단 조건을 바꾸지 않았다.


## 의존성 검사
Next.js/eslint-config-next 16.3.5 및 PostCSS 8.5.23 반영 후 npm audit 0건(2026-09-22). 업데이트 후 API 테스트 3개, lint, 프로덕션 빌드 재통과.

Python 잠금의 anyio 4.15.1, aiohttp 3.14.3, cryptography 50.0.1, pip 26.2.1로 취약 버전을 갱신했다. 새 환경에 uv sync --frozen --extra dev --link-mode copy 설치 성공. 프로젝트 자체를 제외한 고정 의존성(dev 포함) export를 pip-audit --strict --no-deps --disable-pip로 검사하여 알려진 취약점 없음. Ruff 검사·포맷 및 mypy 46개 소스 검사 통과. 고정 환경 pytest 결과는 PR 검증 기록을 따른다.

# 2026-10-28 검증 기록

검토 기준: `73f5504df7e8f1a32cd266ad4cbbda24e1c2c1ff`.
수정 branch: `codex/quality-review-20261028`.
아래 결과는 로컬 수정본의 실행 증거이며, 기존 공개 배포에 수정이 적용됐다는 의미가 아니다.
비교 근거·잔여 기능·복구 방안은 [품질 검토](review-2026-10-28.md)를 참고한다.

## 환경과 방법

- Windows, Python 3.12.11, Node 22.20.0, npm 10.9.3, uv 0.8.22.
- Python 환경은 frozen `uv.lock`과 `dev` extra로 새로 구성했다.
- OneDrive 경로에서 hardlink/파일 잠금 오류가 발생하여 `C:/tmp/datumguard-quality-env-20261028`에
  `UV_LINK_MODE=copy`로 설치했다. 기존 사용자 환경은 삭제하거나 덮어쓰지 않았다.
- 병렬 native 검사 중 Windows access violation이 한 번 발생했다. 검사 프로세스를 종료하고
  순차 실행한 전체 suite가 아래처럼 통과했다. 최초 실패를 제품 테스트 PASS로 계산하지 않는다.

## 확인된 결과

| 검사 | 결과 | 범위·제한 |
|---|---|---|
| Backend 전체 pytest | **454 passed / 8 skipped**, 104.94초 | optional Torch/GraphSAGE 및 OpenSees, Windows symlink 권한에 따른 skip 포함 |
| Backend 보안·정확성 집중 검사 | **244 passed / 2 skipped** | 새 43개 회귀 포함. symlink 2개는 로컬 권한 부재; hardlink 보호는 실행 PASS |
| Ruff format | **82 files passed** | `src tests tools` 전체 |
| Ruff lint | **PASS** | `src tests tools` 전체 |
| mypy | **48 source files passed** | 코어 + 설치 패키지 smoke script |
| npm audit | **0 vulnerabilities** | 갱신한 web lockfile에 대한 advisory 조회 시점 결과 |
| Python runtime pip-audit | **No known vulnerabilities found** | frozen runtime export, 선택된 Windows platform. optional ML 전체/OS 이미지 보증 아님 |
| Wheel 설치 smoke | **PASS** | 소스 checkout 외부, isolated interpreter, editable 설치 거절 |
| Wheel 실제 동작 | **PASS** | entrypoint 2개, packaged JSON 3개, 실제 plate 측정 2개, 1mm DXF 변조 거절, MCP 도구 19개 |
| 최종 Architecture/project browser suite | **17 passed**, 30.2초, retries 0 | production build + 실제 API. 정상/실패, 저장·복구, undo/drag, SVG 좌표 |
| 실제 CAD browser 부분 검사 | **5 passed** | external artifact audit/compare와 실제 STEP 등. 전체 web suite 결과로 대체하지 않음 |
| Next.js production build | **PASS**, 16.4.3 | 모든 route 빌드; 로컬 검사 API `127.0.0.1:8137` |
| 최종 경합·evidence browser 회귀 | **11 passed**, 17.5초, retries 0 | production build. 지연 API/IndexedDB, empty undo/redo, stale PASS 차단, piping letterbox 좌표 |
| Web typecheck / ESLint | **PASS** | 최종 source와 회귀 test 파일 포함 |
| Web unit | **6 passed** | 기존 순수 함수 회귀 |
| 전체 production browser suite | **57 passed**, 1.4분, retries 0, worker 1 | 실제 DXF audit/compare, STEP 생성·재입력, IFC evidence, frame/piping/architecture와 새 14개 회귀 포함 |

전체 pytest에는 기존 100개 폭 변형·50개 숫자 모호성 문형 회귀가 포함된다.
그 숫자를 독립 설계 사례·실제 사용자 요청의 개수로 해석하지 않는다.

개발 서버에서의 확대 browser 실행은 host 부하가 커진 시점에 `/privacy`, `/piping` navigation
timeout 2개를 기록한 뒤 중단했다. 해당 실행은 전체 PASS가 아니며, production build 후
편집 상태·복구 경합의 회귀 11개와 전체 57개를 별도로 통과했다. 앞서 timeout이 난 두 화면도
timeout 설정이나 검사를 완화하지 않고 통과했다. 실제 API를 사용하는 CAD 검사와 지연 응답을
의도적으로 mock하는 UI 경합 검사는 서로 다른 증거로 구분한다.

생산자와 다른 검토자가 지연 draft 복구 및 빈 undo/redo 문제를 소스에서 추가 발견했고,
수정 후 두 차단 항목의 해소를 다시 읽기 전용으로 확인했다. 이 독립 검토 결과는 **PASS**이며
browser 실행 결과와 구분하여 기록한다.

## 재현 명령

표준 환경:

```powershell
uv sync --frozen --extra dev --link-mode copy
uv run --frozen ruff format --check src tests tools
uv run --frozen ruff check src tests tools
uv run --frozen mypy src/datumguard tools/smoke_installed_package.py
uv run --frozen pytest
cd web
npm ci
npm audit --audit-level=high
npm run test:unit
npm run typecheck
npm run lint
npm run build
npm run test:e2e -- --project=chromium
```

이 PC에서 실행한 전체 backend 명령:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
& C:/tmp/datumguard-quality-env-20261028/Scripts/python.exe -B -m pytest
```

설치 smoke는 `.github/workflows/ci.yml`의 `Build and smoke-test the installed wheel outside the checkout`
단계로 재현한다. `python -I`와 checkout 외부 작업 디렉터리를 생략하면 script가 실패하도록 했다.

## 완료 경계

- Linux CI, Docker build/scan과 공개 deployment 검증은 별도 결과가 필요하다.
- GitHub Dependabot의 open 경고는 이 branch의 로컬 audit 0건만으로 닫혔다고 간주하지 않는다.
- 변경된 Render blueprint가 기존 환경변수를 자동으로 덮어쓴다고 가정하지 않는다.
- 미완성 CAD 객체 생성·column rotation 표시·범용 dimension 참조와 부하/복구 검증은
  [잔여 개선 목록](review-2026-10-28.md#4-다음-기능-개선-순서)에 남긴다.

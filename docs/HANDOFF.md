# DatumGuard Multi-domain Engineering MVP Handoff

## 현재 상태

Architecture, Plant/Semiconductor Piping, Mechanical/Ship Plate MVP 구현과 로컬 검증은 완료되었다.

- `/`: 12×8m architecture CAD workspace
- `/piping`: semiconductor CDA utility piping CAD workspace
- `/plate`: mechanical/ship plate workflow와 ship bracket·semiconductor panel preset
- Architecture API: validate, schema, generate→independent DXF verify→approval bundle
- Piping API: validate, schema, route generate→independent DXF verify→approval bundle
- MCP: 기존 9개 도구가 plate, `architectural_plan`, `piping_plan`을 분기 처리
- Demo image: `docs/assets/demo/architecture-verified.png`
- Piping image: `docs/assets/demo/piping-verified.png`
- Architecture fixtures: `architecture_four_room.json`, `architecture_open_300mm.json`; legacy studio/open-loop fixtures remain for compatibility
- Piping fixtures: `piping_utility.json`, `piping_clearance_failure.json`

Architecture의 `gross_area_m2`와 room area는 normalized contract geometry가 아니라 serialized DXF를 독립 재읽기해 복원한 wall centerline에서 산출한다. 성공 응답의 `summary_source`는 `independent_serialized_dxf_remeasurement`다.

Architecture DXF는 `A-GRID`, `A-WALL`, `A-WALL-CENTER`, `A-DOOR`, `A-WIND`, `A-COLS`, `A-ROOM`, `A-DIMS`, `A-ANNO`, `DG-META` 10개 고정 layer와 `contract_hash/entity_id/entity_type/revision` XDATA를 사용한다. `repair_propose`/`repair_apply`와 run의 `auto_repair`는 선언된 column center·opening offset만 CP-SAT으로 최대 3회 수정하며 locked 값과 wall topology는 변경하지 않는다.

Piping의 route length, maximum support gap, minimum equipment clearance도 serialized DXF의 pipe/support/equipment entity에서 재측정한다. Valid CDA fixture는 12.0m route, 2,000mm maximum support gap, 1,975mm minimum clearance를 보고하며 clearance failure fixture는 `DG_PIPE_CLEARANCE_VIOLATION`으로 export를 차단한다.

## 검증 결과

2026-07-11 실행 결과:

- `ruff format --check src tests`: pass
- `ruff check src tests`: pass
- `mypy src/datumguard`: pass, 19 source files
- `pytest -q`: pass, 232 tests; Starlette `httpx` deprecation warning 1건만 존재
- `npm run typecheck`: pass
- `npm run lint`: pass
- `npm run build`: pass; static routes `/`, `/piping`, `/plate`
- `npm audit --omit=dev`: 0 vulnerabilities
- `npm run test:e2e -- --project=chromium`: pass, 12 Chromium tests
- Browser/visual QA: Architecture 1440×960 capture, 4-room PASS, 300mm open-loop export block, 820px numeric/verify flow, piping pass/fail, plate ship bracket pass
- `npm run demo:capture`: pass; `docs/assets/demo/architecture-verified.png` is exactly 1440×960

## 공개 배포에 남은 외부 단계

공개 GitHub 저장소 `https://github.com/tjwnsdhfz/datumguard`와 `origin` remote가 생성되었고 `main`의 초기 CI는 backend, web, Playwright, backend/web Docker image build를 모두 통과했다.

1. Backend는 README의 Render button 또는 루트 `render.yaml`로 배포하고 `DATUMGUARD_CORS_ORIGINS`를 web origin으로 설정한다.
2. Frontend는 README의 Vercel button을 사용하거나 Root Directory를 `web/`으로 지정한다.
3. `NEXT_PUBLIC_DATUMGUARD_API_URL`과 `NEXT_PUBLIC_GITHUB_URL`을 설정한 뒤 frontend를 rebuild한다.
4. `docs/demo.md`와 `docs/piping-demo.md`의 hosted demo 항목을 실행한다.

현재 환경에는 Vercel/Render 인증이 없어 원격 URL 생성은 완료하지 않았다. 로컬 Docker CLI는 없지만 GitHub Actions의 container job에서 두 Dockerfile의 실제 build가 통과했다.

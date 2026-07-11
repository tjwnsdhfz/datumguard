# DatumGuard Multi-domain Engineering MVP Handoff

## 현재 상태

Architecture, Plant/Semiconductor Piping, Mechanical/Ship Plate MVP 구현과 로컬 검증은 완료되었다.

- Public web: `https://datumguard-tjwnsdhfz.vercel.app`
- Public API: `https://datumguard-api.onrender.com`
- GitHub: `https://github.com/tjwnsdhfz/datumguard`

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

## 공개 배포 상태

공개 GitHub 저장소, Render backend, Vercel frontend가 생성되었다. Render는 `plan: free`, health endpoint `/api/v1/health`, exact production CORS origin을 사용한다. Vercel Production에는 Render API와 GitHub CTA 환경변수를 적용한 재배포가 `Ready` 상태다.

2026-07-11 remote smoke 결과:

- API health/domains: `200`
- Production CORS preflight: exact Vercel origin 허용
- Architecture: `VERIFIED / PASS`, 96m², dimensions 4/4, room seeds 4, bundle 활성
- Piping: `VERIFIED`, route 12.0m, max support gap 2,000mm, min clearance 1,975mm, bundle 활성
- Plate: 모든 필수 치수 deviation 0.000000mm, bundle 활성

현재 Vercel 배포 source는 로그인 세션의 Drop to Deploy로 업로드한 commit `415983d`의 `web/` tree다. GitHub App은 `tjwnsdhfz/datumguard` 단일 저장소 범위로 선택했지만 GitHub sudo-mode 이메일 확인이 남아 있어 자동 배포 연결은 아직 완료되지 않았다. 다음 세션에서는 GitHub 확인 후 Vercel Project Settings의 Git 연결을 완료하고 `main` push 자동 배포를 한 번 검증한다. Render는 이미 GitHub Blueprint와 CI-passed commit 자동 배포를 사용한다.

# DatumGuard Product Design QA

## Comparison target

- Source visual truth: `docs/assets/audit/product-design-2026-07-13/01-idle-current.png`, `02-pass-current.png`, `03-failure-current.png`, `04-mobile-current.png`
- Design direction: preserve the existing monochrome Mission Control engineering system while making `준비 → 편집 → 검증 → 복구` the dominant task flow.
- Rendered implementation: local `http://127.0.0.1:3100/`
- Implementation screenshots: `05-idle-improved.png`, `06-mobile-improved.png`, `07-pass-improved.png`, `08-failure-improved.png`
- Desktop viewport: 1440×960, light theme
- Mobile viewport: 390×844, light theme
- States: restored local draft / idle, independent verification PASS, export-blocking FAIL, explicit repair to PASS

## Full-view comparison evidence

- Desktop idle: `docs/assets/audit/product-design-2026-07-13/compare-desktop-idle.png`
- Mobile first task: `docs/assets/audit/product-design-2026-07-13/compare-mobile.png`

The desktop comparison checks the complete first task surface: header, supported/future tools, guided task rail, model tree, SVG plan, exact-value inspector, engine readiness, and primary verification action. The mobile comparison checks the same product intent at the constrained breakpoint and includes the fixed action bar.

## Focused comparison evidence

- PASS evidence: `docs/assets/audit/product-design-2026-07-13/compare-desktop-pass.png`
- FAIL and repair evidence: `docs/assets/audit/product-design-2026-07-13/compare-desktop-failure.png`

Focused comparisons are required because metric typography, hash surfaces, semantic state colors, violation rows, and the repair CTA are too small to judge reliably in the full first-screen comparison.

## Required fidelity surfaces

- Fonts and typography: preserved the repository-local `Noto Sans KR` and `DM Mono` families. Product headings remain heavy sans; coordinates, stage states, hashes, and comparison epsilon remain mono. Evidence metrics were increased from 15px to 20px and their labels from 8px to 9px without changing information.
- Spacing and layout rhythm: the desktop editor now uses `100dvh` to account for the scenario rail, panel titles retain their context, and the verification section aligns below the 124px sticky chrome. Mobile removes the empty commandbar, converts navigation to one horizontal rail, compresses the three steps and scenario choices, and shows the plan in the first viewport.
- Colors and tokens: retained `#000`/cool-white Mission Control surfaces and 1px grey grid. Green remains limited to readiness/PASS; red remains limited to blocked/FAIL/repair. No decorative gradient, glow, shadow system, or new palette was introduced.
- Image and asset quality: the existing native SVG plan and existing `ArchitectureIcon` component were reused. No raster replacement, placeholder, emoji, CSS illustration, or new fake asset was added.
- Copy and content: preserved product-specific claims, `DO NOT SCALE`, `NOT A CERTIFICATION`, exact 0.001mm evidence, scenario labels, engineering error codes, and `300 → 0 mm` repair explanation. Added only `EDIT`/`NEXT` grouping and live engine readiness beside the guided task.

## Comparison history

### Iteration 0 — blocked

- [P1] Mobile header, empty commandbar, vertical steps, and duplicated primary action pushed the SVG plan below the first viewport.
- [P1] Desktop intro, progress, scenario choices, and CTA had nearly equal visual weight.
- [P2] Unsupported creation tools competed with Select/Pan.
- [P2] PASS/FAIL anchor positioning retained a large slice of the editor and made evidence feel secondary.
- [P2] Evidence metrics and hashes were too small for portfolio screenshots.

### Fixes applied

- Replaced the mobile multi-row navigation grid with a one-line horizontal workspace rail.
- Hid the empty mobile commandbar and the rail CTA already duplicated by the fixed mobile action.
- Converted mobile steps and scenario choices to compact three-column controls.
- Added explicit `EDIT` and `NEXT` tool grouping while preserving disabled future tools and accessible names.
- Added readiness to the task rail, active demo state, and `aria-current` for the live step.
- Sized the desktop editor from the actual remaining viewport and made evidence a viewport-scale approval surface.
- Increased evidence metric, stage, label, and hash legibility while retaining semantic tokens.

### Iteration 1 — passed

- `compare-mobile.png` shows the plan, three-step rail, scenario controls, and fixed primary action within the first 390×844 task view.
- `compare-desktop-idle.png` preserves the existing engineering identity and plan proportions while establishing one dominant task path.
- `compare-desktop-pass.png` places evidence directly below sticky chrome, makes the six measurements scannable, and retains trace hashes.
- `compare-desktop-failure.png` preserves the violation-to-object-to-repair sequence and makes the blocked evidence easier to scan.
- Browser measurements: desktop has one scenario primary action; evidence top is 124px; mobile commandbar is `display:none`; mobile action is `position:fixed` with bottom `0px`; page horizontal overflow is absent at both measured widths.
- Primary interactions tested in Chrome: normal verification to PASS, failure verification to blocked export, `300 mm` repair to PASS, responsive viewport switch.
- Browser console errors/warnings checked: 0.

## Findings

No actionable P0, P1, or P2 design differences remain against the stated direction and existing product system.

## Follow-up polish

- [P3] A future dedicated mobile workspace switcher could replace horizontal navigation once the number of engineering domains grows further.
- [P3] The inactive hash surface could gain a copy action when trace evidence sharing becomes an explicit user story.

## Implementation checklist

- [x] Preserve existing local fonts, tokens, icons, and engineering content
- [x] Clarify supported versus future tools
- [x] Establish one guided desktop task hierarchy
- [x] Put the plan and fixed action in the first mobile viewport
- [x] Preserve PASS, FAIL, repair, exact input, and download states
- [x] Compare current and revised visuals at matching states
- [x] Check responsive geometry and browser console

final result: passed

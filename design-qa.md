# Architecture CAD workspace design QA

- source screenshot: `docs/awards-2026/design-audit/architecture-cad/before-architecture-cad.png`
- implementation screenshot: `docs/awards-2026/design-audit/architecture-cad/after-architecture-cad.png`
- mobile screenshot: `docs/awards-2026/design-audit/architecture-cad/after-architecture-mobile.png`
- checked viewports: 1440 × 900 desktop, 375 × 812 mobile
- visual comparison: before and after were opened together at the same desktop viewport and default drawing state

## Result

No actionable P0, P1, or P2 design findings remain in the checked drawing workflow.

The redesign preserves DatumGuard's black-and-white Mission Control shell while changing the plan surface to a familiar dark CAD model space. It adds working layer visibility, object-snap status, live cursor coordinates, crosshair feedback, exact zoom/scale status, and a compact command line without changing the verification contract or evidence flow.

## Functional QA

- Layer controls: each of the five drawing layers can be independently hidden and restored; hidden geometry is removed from the SVG render.
- OSNAP: toggles between the configured grid step and 1 mm drag movement; Shift still constrains edits to 10 mm.
- Command line: supports `FIT`, `Z`, `ZOOM EXTENTS`, `ZOOM IN`, `ZOOM OUT`, `UNDO`, `U`, `REDO`, `SELECT`, `PAN`, `GRID`, and `SNAP`.
- Coordinates: pointer movement updates WCS X/Y/Z readout and the CAD crosshair.
- Existing edit path: select, pan, drag, inspector edits, undo/redo, zoom/fit, verification, and download remain intact.
- Mobile: command entry is intentionally removed below 600 px; the drawing remains viewable and exact numeric editing plus verification remain available below 900 px.

## Evidence

- `npm run typecheck`: passed
- `npm run lint`: passed
- `npm run test:e2e -- tests/e2e/architecture-demo.spec.ts`: 13/13 passed
- Browser interaction: layer hide/restore, OSNAP toggle, command execution, and default-state restoration passed.
- Mobile overflow: measured `scrollWidth 360` inside a `375 px` viewport.

## Boundary

This is a CAD-style contract editing and verification workspace, not a native DWG authoring replacement. The existing authoring-mode buttons remain scoped to the student MVP; official output is still gated by independent DXF re-read and verification.

final result: passed

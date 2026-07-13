# OpenBIM competition demo design QA

- source visual truth path: `docs/awards-2026/design-audit/09-source-production-start.png`
- implementation screenshot path: `docs/awards-2026/design-audit/11-implementation-start.png`
- additional implementation states: `docs/awards-2026/design-audit/12-implementation-demo.png`, `docs/awards-2026/design-audit/13-implementation-input.png`, `docs/awards-2026/design-audit/05-updated-mobile-start.png`, `docs/awards-2026/design-audit/06-updated-mobile-demo.png`, `docs/awards-2026/design-audit/07-updated-input.png`
- viewport: 1280 x 720 desktop; 375 x 812 mobile emulation
- state: idle first screen, demo anchor, input anchor
- full-view comparison evidence: public production and local implementation were opened, captured, and compared together at 1280 x 720.
- focused region comparison evidence: public production input `10-source-production-input.png` and local input `13-implementation-input.png` were compared together.

## Findings

No actionable P0, P1, or P2 visual findings remain in the implemented screen states.

The deployment-protection login wall is a hosting/share issue, not a visual implementation mismatch. It remains documented in `docs/awards-2026/design-audit/AUDIT.md` and prevents the PR preview from being the final public handoff URL.

## Required fidelity surfaces

- Fonts and typography: retained the product's Noto Sans KR and DM Mono pairing, display weight, Korean line-height, and technical label tracking. The demo heading uses an intentional line break to avoid an orphaned final syllable.
- Spacing and layout rhythm: preserved the existing max-width, square border, grid, and section-padding system. The new demonstration rail aligns to the same 1440 px content frame and collapses to one column on mobile.
- Colors and visual tokens: reused the existing navy, slate line, green accent, and failure red tokens. No new unrelated palette or elevation language was introduced.
- Image quality and asset fidelity: the change introduces no image, logo, illustration, or icon assets. Existing brand and icon treatment remains unchanged.
- Copy and content: the public-preview boundary, synthetic representative case, 14 rules, 4 passes, 10 failures, and 12 issues are explicitly labeled so the page does not imply a hosted production validator or real-project accuracy.
- Icons: no new icons or asset substitutes were introduced.
- Accessibility and responsiveness: semantic order remains coherent; both primary links were clicked successfully; desktop and 375 px states had no horizontal overflow; tap targets remain at least 44 px.

## Comparison history

### Iteration 1

- Earlier finding: P2 demo heading wrapped with the final Korean syllable isolated on a third line at the checked desktop viewport.
- Fix made: added an intentional phrase break before `보여줍니다.`.
- Post-fix evidence: `docs/awards-2026/design-audit/12-implementation-demo.png`.
- Result: the heading now wraps as two complete phrases and the result strip remains within the viewport.

### Iteration 2

- Earlier finding: P2 the local shared workspace navigation omitted the existing public `Frame` route, creating product-navigation drift unrelated to the OpenBIM demo story.
- Fix made: restored `Frame` between `3D Solid` and `Artifact Lab` in the shared navigation and added an E2E assertion for its route.
- Post-fix evidence: `docs/awards-2026/design-audit/11-implementation-start.png`.
- Result: the shared navigation now matches the public product structure without changing the active OpenBIM state.

## Browser-rendered verification

- primary interactions tested: first-screen `90초 시연 보기` link, demo `입력 화면으로 이동` link, desktop and mobile anchor states.
- console errors checked: no warnings or errors on the final local implementation tab.
- responsive evidence: 1280 x 720 desktop and 375 x 812 mobile; measured mobile `scrollWidth` equaled the 375 px viewport.
- result-state visual gap: the in-app browser cannot attach local fixture files through its exposed file-picker controls. The direct local API run returned the expected 14 rules, 4 passes, 10 failures, 12 issues, and three default reports; the repository E2E covers the real file-upload/result path.

## Follow-up polish

- P3: after the branch is deployed publicly, recapture the same three states from the final URL so documentation and hosting evidence use one origin.

final result: passed

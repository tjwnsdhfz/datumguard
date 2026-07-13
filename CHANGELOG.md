# Changelog

All notable changes to DatumGuard are documented here. Versions follow Semantic
Versioning and release dates use `YYYY-MM-DD`.

## [Unreleased]

## [0.4.0] - 2026-07-13

### Added

- Added a one-step Rhino/Grasshopper exchange-to-evidence flow through the
  `frame_rhino_roundtrip` FastAPI and MCP contracts.
- Added reproducible evidence from a real Rhino 8, Grasshopper, and Cordyceps session:
  six Rhino object GUIDs are preserved through normalized contract entities, DXF XDATA,
  independent reopen, and a deterministic evidence ZIP.
- Added a versioned DXF support matrix with `MEASURED`, `RENDER_ONLY`, and `UNSUPPORTED`
  levels to the existing `/intake` Artifact Lab.
- Added public launch metadata, structured data, accessible error/loading states, issue
  templates, contribution guidance, citation metadata, and a public roadmap.

### Changed

- DXF revision comparison now returns `comparison_complete`; incomplete evidence returns
  `same_geometry_multiset=null` instead of claiming whole-file geometry equality.
- The public case study now surfaces the real Rhino round-trip, DXF completeness boundary,
  and the 413-pytest / 41-Playwright release gates.

### Security

- XREF, proxy, underlay, raster, OLE, WIPEOUT, nested opaque content, cyclic blocks, deep
  nesting, and excessive expanded block complexity fail closed before unsafe preview
  expansion or complete equality claims.
- Original uploaded CAD bytes and SHA-256 remain immutable, and external artifact audits
  remain `approval_eligible=false`.

## [0.3.0] - 2026-07-12

### Added

- Added the `/frame` FrameGuard workspace, versioned 2D frame contract, deterministic
  linear-elastic solver, and fail-closed structural screening evidence.
- Added explicit Rhino 8 and Grasshopper centerline/support/load/section exchange with
  required units and datum, plus R2013 DXF write, reopen, and 0.001 mm remeasurement.
- Added genuine OpenSeesPy six-case parity evidence and a PyTorch Geometric
  GraphSAGE/GAT advisory model with uncertainty and out-of-distribution review gates.
- Added the `/openbim` research evidence route and its validation artifacts.

### Changed

- Expanded the public domain registry, FastAPI surface, and MCP server for structural
  frame screening while preserving all existing contracts.
- Deployment smoke now requires the `/frame` DOM sentinel, structural-frame capability,
  and a deterministic solver canary.

### Security

- Frame and Rhino inputs reject non-finite engineering values, expensive routes use the
  bounded heavy-work queue, and failed exact or DXF verification never returns a DXF.

## [0.2.1] - 2026-07-12

### Fixed

- Corrected the public Case Study from the historical 19-test value to the
  actual 24-test Playwright release baseline.
- Removed duplicate Privacy title metadata and gave each public route a matching
  canonical and Open Graph URL.
- Split push security evidence from the pull-request dependency review evidence.

### Changed

- Health and readiness now expose the validated Render deployment revision.
- Deployment smoke runs once for Vercel compatibility and again after Render
  succeeds, where it enforces the exact API release SHA.
- Deployment, handoff, rollback, PRD, and TRD documents now distinguish shipped
  evidence from the planned 100+50 benchmark milestone.

## [0.2.0] - 2026-07-12

### Added

- Architecture, plant piping, plate, solid-part, and artifact-audit workspaces.
- Contract-driven generation with serialized DXF/STEP remeasurement and
  verified-only export gates.
- Product case study, social preview metadata, sitemap, and responsive public
  navigation for portfolio review.
- GitHub Actions CI, security scanning, container SBOMs, deployment smoke tests,
  and documented rollback procedures.

### Changed

- Public Solid execution now fails closed when the hosted backend does not
  advertise the required capability; a verified local evidence path remains
  visible in the interface.
- Public documentation now distinguishes implemented behavior, hosted runtime
  limits, and planned benchmarks.

### Security

- Exact-origin CORS, request-size and concurrency limits, isolated CAD parser
  workers, security headers, dependency review, CodeQL, dependency audits, and
  container vulnerability scans are enabled.

[Unreleased]: https://github.com/tjwnsdhfz/datumguard/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/tjwnsdhfz/datumguard/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/tjwnsdhfz/datumguard/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/tjwnsdhfz/datumguard/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.0

# Changelog

All notable changes to DatumGuard are documented here. Versions follow Semantic
Versioning and release dates use `YYYY-MM-DD`.

## [Unreleased]

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

[Unreleased]: https://github.com/tjwnsdhfz/datumguard/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/tjwnsdhfz/datumguard/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/tjwnsdhfz/datumguard/releases/tag/v0.2.0

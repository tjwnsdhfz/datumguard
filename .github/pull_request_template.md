## Summary

<!-- What changed, why it is needed, and the user/developer impact. -->

## Change classification

- Risk: `low | medium | high`
- Surface:
  - [ ] Documentation only
  - [ ] Web only
  - [ ] Backward-compatible API
  - [ ] DesignContract / verification / capability behavior
  - [ ] Infrastructure / environment / CORS

## Engineering assurance impact

- [ ] Locked dimensions, independent remeasurement, PASS/FAIL, and verified-only export semantics are unchanged.
- [ ] Any changed requirement, contract, error, or constraint IDs are listed below and traced to tests.
- [ ] A failed or unavailable verifier still fails closed and cannot create an official bundle.

Affected IDs and compatibility notes:

<!-- Use "None" when this PR does not change an engineering assurance contract. -->

## Validation evidence

- [ ] Backend: Ruff, mypy, pytest
- [ ] Web: typecheck, lint, production build
- [ ] Browser: five-workspace Playwright suite against the real API
- [ ] Containers: backend/web build, SBOM, fixed-CRITICAL gate
- [ ] Security: dependency review, pip-audit, Python/JavaScript CodeQL
- [ ] Vercel Preview and `web-and-api` deployment smoke

Commands and results:

```text

```

Vercel Preview URL:

## Deployment plan

- Web impact:
- API impact:
- Environment, secret, CORS, or feature-flag changes:
- Rollout order and compatibility window:
- Version bump / evidence release required: `yes | no`
- Post-merge owner and production smoke evidence:

## Rollback plan

- Component to roll back first:
- Known-good tag, SHA, or deployment ID:
- Verification after rollback:

## Security, privacy, and operations

- [ ] No credential, CAD payload, contract body, bundle, or private path is added to code, logs, screenshots, or PR text.
- [ ] Data retention, rate limit, cost, monitoring, and incident documentation remain accurate or are updated in this PR.
- [ ] This PR does not add a paid service or change a billing plan without explicit owner approval.

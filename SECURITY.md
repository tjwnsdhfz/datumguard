# Security Policy

보안 문제는 공개 issue에 민감한 재현 정보나 사용자 도면을 첨부하지 말고, 저장소의 private security advisory로 보고해 주세요.

DatumGuard 공개 API는 stateless이며 계정·DB·장기 파일 저장을 사용하지 않습니다. 지원 범위는 최신 release입니다. 공식 실행 경로는 shell, RhinoScript, C# 실행을 제공하지 않으며 MCP export는 지정 workspace 아래의 고정된 `.datumguard/runs/` 경로만 사용합니다.

이 프로젝트의 검증 결과는 구조 안전이나 법규 인증이 아닙니다.

## 민감 데이터와 로그

- 공개 issue, CI log, error tracker에 contract 원문, intent/notes, CAD 파일, filename/path, base64 bundle, token/cookie를 넣지 않습니다.
- 업로드는 request 처리 중에만 사용하고 계정·DB·장기 artifact 저장을 만들지 않습니다. 브라우저 draft는 사용자의 IndexedDB에 남으며 server backup 대상이 아닙니다.
- artifact hash도 pseudonymous identifier로 취급합니다. 운영 log에는 필요 최소한의 short/HMAC identifier만 사용합니다.
- worker stderr와 local stack path를 사용자 응답이나 외부 log provider에 그대로 보내지 않습니다.

데이터 흐름과 보존 기준은 [`docs/operations/privacy-data-lifecycle.md`](docs/operations/privacy-data-lifecycle.md), redaction 계약은 [`docs/operations/logging-redaction.md`](docs/operations/logging-redaction.md)를 따릅니다.

## Supply chain과 공개 API

- Python runtime dependency는 `uv.lock` frozen sync, web dependency는 `package-lock.json`의 `npm ci`를 사용합니다.
- CI는 pip-audit/npm audit, dependency review, CodeQL, container SBOM/Trivy scan을 실행합니다.
- GitHub Actions는 검증한 immutable commit SHA에 pin하고 Dependabot PR에서 갱신합니다.
- CORS는 browser isolation일 뿐 인증이나 rate limit이 아닙니다. API는 optional secret key, anonymous/authenticated 분리 quota, bounded CAD worker concurrency와 queue를 적용합니다. 10k DAU 출시 전에는 staging 부하 결과로 이 값을 재산정하고 외부 gateway/WAF가 필요한지 다시 승인합니다.

Wrong PASS, 부적격 official export 또는 CAD 노출은 SEV1입니다. 즉시 [Incident Runbook](docs/operations/incident-runbook.md)의 kill switch와 rollback 절차를 적용합니다.

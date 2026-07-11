# Logging and Redaction

## 현재 상태와 목표

현재 API는 `X-Request-ID`를 검증·전파하고 payload를 제외한 JSON request event와 bounded in-process metric을 제공한다. request event에는 route, status, duration, CF Ray, heavy queue active/waiting과 wait time이 들어가며, 처리되지 않은 예외는 메시지·경로 없이 exception type과 `DG_INTERNAL_ERROR`만 별도 기록한다. `/api/v1/metrics`는 route별 request/status/error/429·duration bucket과 queue snapshot을 제공한다.

외부 log aggregation, frontend/backend error tracker, uptime alert와 장기 보존은 아직 연결되지 않았다. 따라서 단일 instance 재시작 뒤에도 이어지는 추세·알림까지 운영 준비 완료로 표시하지 않는다.

후속 외부 관측 계층의 권장 event 필드:

```text
timestamp, level, service, environment, release_sha, api_version,
request_id, correlation_id, route_template, method, status_code,
duration_ms, request_bytes, response_bytes, capability,
worker_operation, worker_duration_ms, queue_depth, outcome, error_code
```

## 절대 기록하지 않는 값

- raw contract/intent/notes, CAD/IFC/DXF/STEP bytes, multipart body, base64 artifact/bundle
- 전체 filename/path, authorization/cookie, Vercel bypass secret, environment variable 값
- full IP, user-agent 전체 문자열, 이메일·계정 식별자(향후 추가 시 별도 privacy review)
- subprocess stdout/stderr 원문과 stack의 local path. allowlisted error code와 1회성 내부 event ID만 남긴다.

Artifact hash도 고객 파일을 장기간 추적할 수 있는 pseudonymous identifier다. 필요하면 HMAC/짧은 prefix로 변환하고 raw hash를 외부 log provider에 보내지 않는다.

## 전파와 redaction

1. ingress에서 UUID request ID를 만들거나 유효한 내부 ID만 수용한다.
2. 같은 ID를 response header, error body, parent/child CAD worker event에 전파한다.
3. exception은 공용 error code로 변환하고 사용자 응답에 worker stderr를 포함하지 않는다.
4. SDK의 `before_send`/processor에서 body, file, headers와 query string을 제거한다.
5. sample contract와 synthetic filename으로 redaction test를 CI에 추가한다.

## 보존과 알림

- 목표: application event 14일 hot retention, 집계 SLI 90일. CAD/contract payload retention은 0일.
- GitHub CI log는 현재 repository setting 90일, Playwright failure artifact는 workflow 14일이다. failure artifact에 upload body가 들어가지 않는지 검토한다.
- alert: wrong PASS/error code 즉시, 5xx >1%/5분, p95 초과 15분, RSS >80%, restart, queue saturation, smoke failure.
- provider 비용/보존을 바꾸는 작업은 [cost guard](cost-guard.md) 승인 뒤 수행한다.

참고: [Render logs](https://render.com/docs/logging), [Vercel runtime logs](https://vercel.com/docs/logs/runtime).

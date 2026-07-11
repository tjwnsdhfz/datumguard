# Local and Staging Load Testing

`tools/load_probe.py`는 production hostname을 hard-block한다. localhost는 바로 실행할 수 있고, staging은 exact hostname과 명시적 확인 flag가 모두 필요하다.

Windows OneDrive workspace에서는 먼저 `$env:UV_LINK_MODE = "copy"`를 설정한 뒤 `uv sync --frozen --extra dev`를 실행한다. hardlink mode는 OneDrive에서 `os error 396`으로 실패할 수 있다.

## 기본 probe

```powershell
# localhost: concurrency 1, 2, 5, 10을 각각 20회
python tools/load_probe.py --scenario architecture

# 한 수준만, JSON evidence
python tools/load_probe.py --scenario solid --concurrency 2 --requests-per-level 10 --json

# 격리 staging (known production host는 이 flag로도 해제되지 않음)
python tools/load_probe.py `
  --base-url https://api-staging.example.test `
  --staging-host api-staging.example.test `
  --acknowledge-staging `
  --scenario architecture
```

각 수준은 requests, success/error rate, 429, p50/p95/p99, mean response bytes와 status/error 분포를 출력한다. 기본 error budget은 0이며 `--max-error-rate 0.01`처럼 명시적으로 조정할 수 있다.

## 실행 순서와 중단 기준

1. staging deploy SHA/version과 비용 owner 승인을 기록한다.
2. health → architecture → solid 순으로 1, 2, 5, 10 동시성을 올린다.
3. 각 단계에서 Render CPU/RSS/restart, worker 수, queue, response byte를 함께 기록한다.
4. 5xx, OOM/restart, wrong PASS, p99 timeout, 예상하지 않은 bundle/hash mismatch가 한 건이라도 나오면 즉시 중단한다.
5. overload는 bounded 429가 되어야 한다. 429가 없다는 사실만으로 capacity가 충분하다고 판단하지 않는다.

출시 후보 기준은 [SLO/SLI](slo-sli.md)를 따르며, v0.2 STEP이 포함된 결과 없이 10k DAU capacity를 승인하지 않는다.

## Malformed와 최대 크기: 단발만

다음 검사는 concurrency probe와 분리하고 localhost/격리 staging에서 한 번씩만 한다.

```powershell
# malformed JSON은 4xx + DG_INPUT_INVALID여야 하며 500이면 실패
curl.exe -i -X POST `
  -H "Content-Type: application/json" `
  --data-binary "{broken" `
  http://127.0.0.1:8000/api/v1/architecture/designs/run
```

크기 경계는 20MB-1/20MB/20MB+1 artifact와 48MB-1/48MB/48MB+1 request를 synthetic bytes로 만든다. 실제 고객 CAD를 fixture로 쓰지 않는다. 한 프로세스씩 실행하고 RSS/temp-file cleanup을 관찰한다. `Content-Length`가 있는 요청과 chunked 요청을 모두 확인하며 기대값은 다음과 같다.

- artifact 20MB 초과: bounded `DG_ARTIFACT_TOO_LARGE`, official approval 없음.
- request 48MB 초과: HTTP 413 `DG_INPUT_INVALID`.
- unsupported/malformed CAD: 4xx 또는 `failed_verification`, worker traceback/path/body 미노출.
- timeout 후 parent/child process와 temp file이 남지 않음.

max-size payload를 production이나 public Preview로 보내지 않는다. 결과에는 payload 자체가 아니라 size, SHA, status, latency, peak RSS와 cleanup 여부만 남긴다.

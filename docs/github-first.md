# GitHub-first 공개 사용 가이드

DatumGuard의 공개 배포 원칙은 **source and evidence on GitHub, compute on your machine**입니다.
중앙 유료 CAD 서버를 필수 경로로 두지 않고, 사용자가 자신의 PC·GitHub Actions runner·Codespace에서
같은 검증 코어를 실행합니다.

## 어떤 경로를 선택해야 하나요?

| 상황 | 권장 경로 | 비용·데이터 경계 |
|---|---|---|
| 샘플을 바로 재현 | Fork/사용자 repository의 GitHub Action | Public repository의 표준 runner 정책 범위에서 무료. 공개 fixture만 사용 |
| 개인·기밀 CAD 검사 | Local CLI | 서버 전송 없음. 사용자 PC 자원 사용 |
| 설치 없이 코드와 UI 체험 | GitHub Codespaces | 개인 계정의 포함 quota 또는 조직 billing 사용. 무제한 무료 아님 |
| 전체 웹 UI 사용 | Local Docker Compose | 서버 전송 없음. 사용자 PC에서 API와 Web 실행 |
| 결과만 열람 | GitHub Release / repository evidence | 실행 없이 공개 합성 evidence 확인 |

GitHub Pages는 정적 HTML·CSS·JavaScript를 제공할 수 있지만 현재 Python/CadQuery/IfcOpenShell 검증
엔진을 실행할 수 없습니다. 따라서 Pages를 실시간 전체 CAD 백엔드로 표현하지 않습니다.

## 1. Local CLI

Python 3.12와 [`uv`](https://docs.astral.sh/uv/)가 필요합니다.

macOS/Linux:

```bash
git clone https://github.com/tjwnsdhfz/datumguard.git
cd datumguard
uv sync --frozen
```

Windows PowerShell, 특히 OneDrive 작업공간:

```powershell
git clone https://github.com/tjwnsdhfz/datumguard.git
Set-Location datumguard
python -m pip install uv==0.8.22
$env:UV_LINK_MODE = "copy"
uv sync --frozen --link-mode copy
```

계약 JSON을 CAD로 생성한 뒤 독립 재측정합니다.

```bash
uv run --frozen datumguard verify fixtures/examples/architecture_studio.json \
  --output datumguard-results/architecture
```

기존 CAD 산출물은 원본을 변경하지 않고 감사합니다.

```bash
uv run --frozen datumguard audit drawing.dxf --output datumguard-results/audit
uv run --frozen datumguard compare baseline.dxf candidate.dxf \
  --output datumguard-results/compare
```

결과 디렉터리에는 다음 파일 중 해당되는 항목만 생성됩니다.

- `verification-result.json`: Base64 payload를 제거한 구조화 결과
- `preview.svg`: 저장 산출물에서 만든 미리보기
- `verified-bundle.zip`: 모든 필수 gate를 통과한 2D 공식 bundle
- `verified.dxf`: Frame screening의 독립 DXF gate 통과 산출물
- `verified.step`: 제한형 Solid의 독립 STEP 재입력 통과 산출물

기본 exit code는 `passed`와 `audited`에서 `0`, 검토 또는 검증 실패에서 `2`, 잘못된 입력에서 `1`입니다.
`audit`의 `audited`는 **읽고 측정했다는 뜻이며 제작 승인 PASS가 아닙니다**.

## 2. GitHub Action

Root `action.yml`은 입력을 caller repository 내부 regular file로 제한하고, 결과를 선택한
repository-relative output directory에만 쓰는 Composite Action입니다. Python dependency는 실행 중
공개 package index에서 설치합니다. 현재 `v1` tag는 아직 게시되지 않았으므로 아래 예시는 이 변경을
merge하고 첫 Action release를 만든 뒤 활성화됩니다.

```yaml
name: CAD assurance

on:
  workflow_dispatch:
  push:
    paths:
      - contracts/**.json

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7
        with:
          persist-credentials: false

      - id: datumguard
        uses: tjwnsdhfz/datumguard@v1
        with:
          command: verify
          input: fixtures/examples/architecture_studio.json
          output_directory: datumguard-results

      - if: always() && steps.datumguard.outputs.result_json != ''
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7
        with:
          name: datumguard-result-${{ github.run_id }}
          path: datumguard-results/
          if-no-files-found: warn
          retention-days: 3
```

`v1`은 쉬운 시작용 major tag입니다. 재현성과 공급망 고정이 중요한 workflow에서는 release가 가리키는
**full commit SHA**로 교체하십시오. Action은 `verify`, `audit`, `compare`를 지원하며 입력은
repository-relative regular file만 허용합니다. Absolute path, `..` traversal, repository 밖으로 나가는
symlink, 지원하지 않는 확장자를 거부합니다.

가장 빠른 무편집 재현 경로는 다음과 같습니다.

1. 첫 Action release 이후 DatumGuard repository를 fork합니다.
2. Fork의 `Actions` 탭에서 workflow 사용을 활성화합니다.
3. `datumguard-action` workflow → `Run workflow`를 누릅니다.
4. Checked-in Plate·Architecture fixture의 PASS와 의도된 FAIL 결과를 확인합니다.

자신의 repository에서는 위 YAML을 추가하고 `input`을 직접 commit한 contract 경로로 바꿉니다. Public
sample 또는 기밀이 아닌 contract만 Public repository에 commit하고, Job Summary에서 status와 hash를
확인한 뒤 필요한 경우에만 결과 artifact를 내려받습니다.

일반 방문자는 upstream DatumGuard repository의 `workflow_dispatch`를 바로 실행할 write 권한이 없습니다.
연산과 storage 사용량을 caller에게 귀속시키기 위해 fork/사용자 repository 흐름을 사용합니다. Action은
현재 `ubuntu-latest` runner만 지원하며, Local CLI는 native dependency가 지원되는
Windows·macOS·Linux에서 사용할 수 있습니다.

Public repository의 표준 GitHub-hosted runner 사용 정책은
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)에서
확인할 수 있습니다. Private repository는 사용자의 포함 minutes와 storage를 사용합니다. DatumGuard
제공자 계정이 익명 사용자의 중앙 연산 비용을 대신 지불하는 구조가 아닙니다.
Actions artifact 저장 공간과 retention은 별도 plan quota에 포함될 수 있습니다. 예시의
`upload-artifact` 단계는 선택 사항이며, 장기 보관이 필요하지 않으면 제거하거나 짧은 retention을
사용하십시오.

### Action 보안 경계

- `permissions: contents: read`와 `persist-credentials: false`를 유지합니다.
- DatumGuard job에는 secret을 전달하지 않습니다.
- `pull_request_target`, issue comment, 외부 URL을 CAD 실행 트리거로 사용하지 않습니다.
- Public repository의 CAD, contract, log, hash, Actions artifact는 공개 정보로 취급합니다.
- 기밀 CAD는 Public repository나 중앙 DatumGuard repository에 commit하지 않습니다.
- Native CAD parser는 별도 subprocess 제한을 사용하지만 container 수준의 network/filesystem sandbox는
  아직 제공하지 않습니다. 고민감도 파일은 Local CLI를 사용하십시오.
- Action artifact에는 입력 CAD를 다시 업로드하지 않고 결과 JSON·SVG·통과 bundle만 저장합니다.

Action이 실패해도 `verification-result.json`이 생성된 경우 caller workflow에서 `if: always()`로
업로드할 수 있습니다. 실패 결과에는 승인 bundle이 없어야 합니다.

## 3. GitHub Codespaces

[Open in Codespaces](https://codespaces.new/tjwnsdhfz/datumguard?quickstart=1)를 누른 뒤 container 생성이
끝나면 VS Code command palette에서 `Tasks: Run Task` →
`DatumGuard Codespaces: Start full demo`를 선택합니다.
Web은 private forwarded port `3000`에서 열리고, Next.js local proxy가 같은 Codespace의 `8000` API로
연결합니다. API port를 public으로 바꿀 필요가 없습니다.

샘플만 검증하려면 `DatumGuard Codespaces: Verify architecture sample` task를 실행합니다. Codespaces는
[개인 계정 quota와 billing 설정](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces)을
사용합니다. 작업을 마치면 Codespace를 stop하고 필요하지 않은 instance를 delete하십시오. 기밀 설계는
회사 정책과 GitHub 저장 위치를 먼저 확인하고, 불확실하면 Local CLI를 사용하십시오.

## 4. Local Docker

전체 UI와 API를 사용자 PC에서 실행합니다.

```bash
docker compose up --build
```

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- Readiness: `http://localhost:8000/api/v1/ready`

현재 Compose는 source build 방식입니다. 다음 release 단계에서는 검증·서명된 public GHCR image와
version-pinned release Compose를 제공해 첫 build 시간을 줄입니다.

## 상태 해석

| 상태 | CI 기본 동작 | 의미 |
|---|---:|---|
| `passed` | 성공 | Contract와 독립 serialized artifact gate 통과 |
| `audited` | 성공 | 외부 파일을 읽고 측정함. `approval_eligible=false` |
| `needs_confirmation` | 실패 | 비교 완전성 또는 경고에 사람 확인 필요 |
| `failed_verification` | 실패 | 필수 정확성·완전성 gate 실패 |
| `repairable` / `repair_exhausted` | 실패 | 제한 수정 대상 또는 수정 한도 소진 |

Frame 결과는 구조 안전 인증이 아닌 제한된 screening이며, OpenBIM 결과는 연구 validation evidence입니다.
어떤 경로도 전문 엔지니어 검토, 제작 승인, 시공 승인 또는 법규 적합성 판정을 대신하지 않습니다.

## 공개 release gate

`v1` Action과 GHCR local bundle은 다음 조건 이후 게시합니다.

1. CLI unit/integration test와 기존 backend test 통과
2. `action.yml` self-test에서 Architecture·Plate PASS 재현
3. 의도된 FAIL에서 non-zero와 bundle 미생성 확인
4. wheel/container SBOM, checksum, source SHA 기록
5. Public GHCR image의 non-root 실행과 digest 고정

Action release 전에는 이 repository를 fork한 뒤 `uses: ./`로 공개 fixture self-test를 실행할 수 있습니다.

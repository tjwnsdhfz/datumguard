# Representative OpenBIM evidence bundle

`fixtures/openbim/representative/v0_clean.ifc`와 `v1_faulty.ifc`, 고정 IDS/profile을 실제
OpenBIM service에 넣어 생성하는 패널·외부 viewer 점검용 bundle이다.

```powershell
uv sync --frozen --extra dev  # 또는 --extra openbim --extra bcf
uv run --frozen python tools/export_openbim_representative.py
```

생성 파일:

- `openbim-evidence.json`: timing과 package field를 제외한 canonical evidence
- `openbim-evidence.html`: 사람이 읽는 escaped report
- `openbim-evidence.bcf`: BCF 3.0 표준 파일명으로 제공하는 issue package
- `openbim-evidence.bcfzip`: 위 `.bcf`와 동일 바이트·동일 해시인 기존 viewer 호환 파일명
- `openbim-evidence-manifest.json`: 두 BCF 파일을 각각 기록하는 input/artifact hash manifest
- `representative-verification.json`: source commit·dirty 상태, source hash와 범용 ZIP/XML 구조검증 결과

범용 ZIP/XML parse와 `bcf-client` semantic round-trip은 독립 BCF viewer import를 대체하지 않는다.
viewer에서 topic, status와 component가 보이는지 확인하기 전 external viewer gate는 미완료다.

대표 faulty case는 `failed_verification`, issue/BCF topic 12개이며 input hash 독립 재계산과
manifest-artifact 교차검증을 통과했다. 생성 commit·dirty 상태와 정확한 artifact hash는
`representative-verification.json`을 기준으로 한다.

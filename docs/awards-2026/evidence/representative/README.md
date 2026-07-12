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
- `openbim-evidence.bcfzip`: BCF v3 issue package
- `openbim-evidence-manifest.json`: input/artifact hash manifest
- `representative-verification.json`: clean commit, source hash와 범용 ZIP/XML 구조검증 결과

범용 ZIP/XML parse와 `bcf-client` semantic round-trip은 독립 BCF viewer import를 대체하지 않는다.
viewer에서 topic, status와 component가 보이는지 확인하기 전 external viewer gate는 미완료다.

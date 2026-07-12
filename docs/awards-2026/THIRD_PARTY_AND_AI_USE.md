# Third-party libraries and AI use

이 문서는 출품용 고지 초안이며 법률 의견이나 license 적합성 보증이 아니다. 최종 배포 bundle을
공개하기 전에 실제 source tag, wheel, 전이 의존성, 배포 방식을 다시 검토한다.

## 고정한 주요 패키지

2026-07-12 로컬 Python 3.12 환경의 설치 metadata를 직접 확인했다.

| Distribution | Version | 역할 | 설치 wheel metadata | Source |
|---|---:|---|---|---|
| `ifcopenshell` | 0.8.5 | IFC 생성·재개방·geometry | classifier: LGPLv3+ | [IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell) |
| `ifctester` | 0.8.5 | IDS 1.0 parse·validation | source·classifier: LGPLv3+ | [PyPI 0.8.5 metadata](https://pypi.org/pypi/ifctester/0.8.5/json) · [0.8.5 source](https://github.com/IfcOpenShell/IfcOpenShell/tree/ifcopenshell-python-0.8.5/src/ifctester) |
| `bcf-client` | 0.8.5 | 조건부 BCF package | source: LGPLv3+ / classifier: GPLv3 | [PyPI 0.8.5 metadata](https://pypi.org/pypi/bcf-client/0.8.5/json) · [0.8.5 source](https://github.com/IfcOpenShell/IfcOpenShell/tree/ifcopenshell-python-0.8.5/src/bcf) |

세 distribution 모두 설치 metadata의 `License`와 `License-Expression` 값이 비어 있었고 wheel file
목록에 이름이 `LICENSE` 또는 `COPYING`인 파일이 없었다. 현재
[IfcOpenShell repository 표](https://github.com/IfcOpenShell/IfcOpenShell)는 BCF를
LGPL-3.0-or-later로 표시하지만 `bcf-client==0.8.5` PyPI JSON과 설치 wheel classifier는 GPLv3로
표시한다. 이 불일치는 해석으로 덮지 않는다.

감사한 wheel과 대응 source snapshot을 `evidence/third_party_license_audit.json`에 고정했다.

- `ifctester-0.8.5-py3-none-any.whl`: 25,381,125 bytes,
  SHA-256 `8e21f2bd7a025f249a5f185555c2ccb60bd121a5c2eb03a455fa083e558f528b`
- `bcf_client-0.8.5-py3-none-any.whl`: 41,576 bytes,
  SHA-256 `6f7b2aee2985f06de2f6d90a56fa1db76f394010bea30810a3572cb7eece05f3`
- source snapshot: `ifcopenshell-python-0.8.5`, commit
  `16723d11cab9bc8a13b4e025a00d39445ccc462e`

PyPI metadata는 해당 wheel과 source commit의 암호학적 연결을 선언하지 않는다. 두 wheel 모두
`License-Expression`과 wheel 내부 LICENSE/COPYING/NOTICE 전문이 없다. 따라서 source snapshot은 버전이
일치하는 근거이지 wheel provenance를 완전히 증명하는 attestation은 아니다.

따라서 다음을 release gate로 둔다.

`ifctester`가 `bcf-client`를 전이 의존성으로 설치한다는 점까지 포함해, `ifctester` 자체를 base
dependency에서 제거하고 `openbim`/`dev` extra로 분리했다. `bcf-client`의 직접 pin은 `bcf`/`dev`
extra에만 둔다. 따라서 Docker/Render base image는 두 package를 설치하지 않고 OpenBIM도 `false`로
비활성화한다. Web의 BCFZIP 선택도 기본값 `false`다. OpenBIM JSON/HTML 경로에는 `openbim` extra가
필요하며, BCF export를 명시적으로 사용할 때는 `openbim`과 `bcf` extra를 함께 설치하고 API의
`DATUMGUARD_ENABLE_BCF=true`를 별도로 켠다. 기본값은 false다. 단, `openbim` extra는 IfcTester의
전이 의존성으로 `bcf-client`도 설치한다. 따라서 이 분리는 base image에서 package를 제거하지만,
연구용 OpenBIM 환경 내부에서 BCF package 자체를 제거하는 격리는 아니다.

1. source와 wheel metadata가 다른 `bcf-client`는 maintainer 또는 배포자 자료로 재확인한다.
2. public image에 실제 포함되는 distribution과 license text 제공 방식을 artifact inventory로 확인한다.
3. DatumGuard MIT 코드, offline research bundle, hosted runtime 각각의 배포 방식을 별도로 검토한다.
4. 해결 전에는 `pip install -e ".[openbim,bcf]"` 또는 dev 환경에서만 BCF를 사용하고 BCF
   artifact를 필수 배포물로 주장하지 않는다.
5. 최종 NOTICE에는 실제 포함한 distribution, version, wheel hash, URL, license text 제공 위치, 수정 여부를 기록한다.

이 문서는 “호환된다” 또는 “호환되지 않는다”는 법률 결론을 내리지 않는다.

## 표준·도구의 역할

- IFC는 합성 모델 교환 형식이다.
- IDS는 entity, property, classification 같은 정보 요구를 표현한다.
- project geometry/revision rule은 DatumGuard 연구 계약이며 IDS 또는 IFC 표준 규칙으로 오인하지 않는다.
- BCF는 판정기가 아니라 issue 전달·상태 추적 형식이다.

## Codex/AI 사용 고지

Codex는 다음 작업을 보조했다.

- 연구 범위와 일정 초안 정리
- generator, benchmark, test scaffolding 작성·검토
- 문서 구조, edge case, reproducibility check 제안

학생이 직접 검토하고 책임져야 하는 항목:

- 연구질문, 규칙, 허용값과 assurance boundary
- mutation label과 ground truth의 정확성
- 코드, test, raw result, 실패 사례와 최종 결론
- 제3자 package와 AI 사용의 최종 고지

LLM은 IFC 판정 경로, ground truth 생성, metric 계산에 사용하지 않는다. 선택적인 자연어 설명이
추가되더라도 deterministic evidence와 분리하고 정량 성능에 포함하지 않는다.

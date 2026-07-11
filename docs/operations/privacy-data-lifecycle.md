# Privacy and Data Lifecycle

## 현재 데이터 흐름

| 데이터 | 위치 | 기본 보존 | 삭제/복구 책임 |
|---|---|---:|---|
| Design contract JSON | browser → Render request memory | request 종료까지 | server 복구 대상 아님 |
| DXF/STEP/IFC upload | multipart spool/memory와 격리 CAD worker | request/worker 종료까지; Render filesystem은 ephemeral | server에 장기 보존 금지 |
| Generated STEP/DXF/PDF/JSON bundle | response memory → 사용자 download | server 0일 | 사용자가 보관·삭제 |
| Workspace draft | browser IndexedDB `datumguard/drafts` | 마지막 저장 후 30일; 다음 조회 시 만료 삭제 | 해당 browser 사용자; `/privacy`에서 전체 삭제 |
| Operational metadata | platform/application logs | 현재 platform plan 기준 | 운영 owner; payload 금지 |
| GitHub test artifact | CI failure screenshot/trace | workflow 14일 | repository owner |

계정, DB, cloud project history는 현재 없다. 따라서 DB index/PITR/DSAR export 구현은 현재 범위가 아니지만, 사용자가 보유한 CAD는 기밀 설계일 수 있으므로 payload 최소화 원칙은 그대로 적용한다.

## 처리 원칙

- 업로드 전에 “장기 저장하지 않음, geometry verification only”를 명확히 표시한다.
- filename은 표시 목적의 안전한 basename만 사용하고 log/error tracker에 보내지 않는다.
- request body·artifact를 analytics, replay, error attachment에 포함하지 않는다.
- browser session replay를 도입하면 file input, canvas/contract field, result hash를 mask하고 sampling 승인을 받는다.
- temp file은 context manager로 닫고 worker timeout/exception에서도 정리되는지 test한다.
- production backup은 source/config/runbook 대상이다. CAD payload backup을 새로 만들지 않는다.

## 기능 확장 gate

계정, 공유 link, cloud history, email 또는 object storage를 추가하는 PR은 같은 변경에서 다음을 정의해야 한다: lawful purpose, data owner, encryption, access control, region, retention/deletion job, backup/PITR, restore drill, breach notification, 비용 상한.

Privacy incident는 [incident runbook](incident-runbook.md)의 SEV1이며 private security advisory로 조정한다.

# DatumGuard Prompt Design

| 항목 | 내용 |
|---|---|
| Prompt package version | 1.0.0 |
| Structured output | `ContractDraftResult` |
| Prompt 역할 | 자연어 의도를 확인 가능한 계약 초안으로 변환 |
| 공식 판정 권한 | 없음 |

## 1. 목적

Requirements Compiler prompt는 사용자의 자연어와 구조화 폼 값을 읽고 `DesignContract`에 적용할 조건 후보, 근거와 확인 질문을 반환한다. LLM은 geometry를 생성하거나 치수 합격 여부를 판정하지 않으며, 입력에 없는 숫자·단위·datum·공차를 만들어서는 안 된다.

## 2. 책임 분리

### LLM이 수행하는 일

- 설계 의도 분류
- form field와 자연어 조건 연결
- symmetry/alignment/equal-spacing 같은 constraint 후보 생성
- 명시된 feature 후보와 원문 evidence 추출
- 모호하거나 충돌하는 내용에 대한 확인 질문 작성

### 결정론적 서버가 수행하는 일

- 단위 변환과 숫자 검증
- ID/path 존재 검증
- Contract 상태 결정
- Geometry/DXF 생성
- 재측정, tolerance, pass/fail
- Repair feasibility와 parameter 변경
- Hash, approval, export

## 3. System Prompt

```text
You are DatumGuard Requirements Compiler.

Your only task is to translate a user's engineering design intent into a structured ContractDraftResult that can be reviewed before deterministic CAD generation.

Hard rules:
1. Never invent a number, unit, coordinate, datum, tolerance, material property, process capability, standard, or feature.
2. Preserve every explicit number exactly as written and attach its source evidence.
3. Form values are authoritative. If natural language conflicts with a form value, do not choose either value; return a conflict and needs_confirmation=true.
4. Do not convert units. Return the source value and source unit; deterministic code performs conversion.
5. Do not mark a dimension locked or free unless the form or user explicitly says so.
6. Do not create pass/fail, verification, repair, hash, approval, or export results.
7. Refer only to form field IDs, feature IDs, and constraint IDs provided in the input or create provisional IDs with the prefix proposal-.
8. Every proposal must cite one or more evidence items from the form or intent text.
9. Words such as roughly, suitable, centered-ish, standard, normal, enough, symmetric, and evenly spaced do not imply numeric values.
10. Missing datum, unit, dimension, tolerance, or required manufacturing value must produce a confirmation question.
11. Return JSON only and follow ContractDraftResult exactly. Do not add Markdown or commentary.
12. When no safe proposal can be made, return empty proposal arrays and explain the missing information in confirmations.
```

## 4. User Prompt Template

```text
Compile the following DatumGuard design request.

Schema version:
{{schemaVersion}}

Current structured form values:
{{formValuesJson}}

Known feature and field identifiers:
{{knownIdentifiersJson}}

User intent text:
{{intentText}}

Return ContractDraftResult JSON only.
Do not perform unit conversion, CAD generation, verification, repair, or approval.
```

## 5. Structured Output Schema

아래 JSON Schema를 실제 API structured output schema로 사용한다.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://datumguard.dev/schemas/contract-draft-result-1.0.0.json",
  "title": "ContractDraftResult",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "prompt_version",
    "needs_confirmation",
    "feature_proposals",
    "constraint_proposals",
    "conflicts",
    "confirmations",
    "evidence"
  ],
  "properties": {
    "prompt_version": {"const": "1.0.0"},
    "needs_confirmation": {"type": "boolean"},
    "feature_proposals": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["proposal_id", "feature_type", "parameters", "evidence_ids"],
        "properties": {
          "proposal_id": {"type": "string", "pattern": "^proposal-"},
          "feature_type": {
            "enum": ["circular_hole", "slot", "rectangular_cutout", "linear_pattern", "circular_pattern"]
          },
          "parameters": {"type": "object"},
          "evidence_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1}
        }
      }
    },
    "constraint_proposals": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["proposal_id", "constraint_type", "entity_ids", "parameters", "evidence_ids"],
        "properties": {
          "proposal_id": {"type": "string", "pattern": "^proposal-"},
          "constraint_type": {
            "enum": ["symmetry", "alignment", "equal_spacing", "non_overlap", "minimum_edge_distance", "minimum_ligament"]
          },
          "entity_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
          "parameters": {"type": "object"},
          "evidence_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1}
        }
      }
    },
    "conflicts": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["conflict_id", "field_or_entity_ids", "description", "evidence_ids"],
        "properties": {
          "conflict_id": {"type": "string"},
          "field_or_entity_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
          "description": {"type": "string"},
          "evidence_ids": {"type": "array", "items": {"type": "string"}, "minItems": 2}
        }
      }
    },
    "confirmations": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["confirmation_id", "reason_code", "question", "required_fields"],
        "properties": {
          "confirmation_id": {"type": "string"},
          "reason_code": {
            "enum": ["MISSING_NUMBER", "MISSING_UNIT", "MISSING_DATUM", "MISSING_TOLERANCE", "AMBIGUOUS_LANGUAGE", "FORM_TEXT_CONFLICT", "UNSUPPORTED_REQUEST"]
          },
          "question": {"type": "string"},
          "required_fields": {"type": "array", "items": {"type": "string"}, "minItems": 1}
        }
      }
    },
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["evidence_id", "source_type", "source_ref", "exact_text", "numbers"],
        "properties": {
          "evidence_id": {"type": "string"},
          "source_type": {"enum": ["form", "intent_text"]},
          "source_ref": {"type": "string"},
          "exact_text": {"type": "string"},
          "numbers": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["lexeme", "value", "unit"],
              "properties": {
                "lexeme": {"type": "string"},
                "value": {"type": "number"},
                "unit": {"type": ["string", "null"]}
              }
            }
          }
        }
      }
    }
  }
}
```

## 6. 출력 예시

입력 intent: `네 모서리에서 10mm 떨어진 곳에 지름 6mm 홀을 같은 간격으로 배치해줘.`

```json
{
  "prompt_version": "1.0.0",
  "needs_confirmation": false,
  "feature_proposals": [
    {
      "proposal_id": "proposal-corner-hole-pattern",
      "feature_type": "circular_hole",
      "parameters": {
        "diameter": {"value": 6.0, "unit": "mm"},
        "edge_offset": {"value": 10.0, "unit": "mm"},
        "placement": "four_corners"
      },
      "evidence_ids": ["evidence-intent-1"]
    }
  ],
  "constraint_proposals": [
    {
      "proposal_id": "proposal-equal-corner-offset",
      "constraint_type": "equal_spacing",
      "entity_ids": ["proposal-corner-hole-pattern"],
      "parameters": {"mode": "equal_edge_offset"},
      "evidence_ids": ["evidence-intent-1"]
    }
  ],
  "conflicts": [],
  "confirmations": [],
  "evidence": [
    {
      "evidence_id": "evidence-intent-1",
      "source_type": "intent_text",
      "source_ref": "intent:0-39",
      "exact_text": "네 모서리에서 10mm 떨어진 곳에 지름 6mm 홀을 같은 간격으로 배치해줘.",
      "numbers": [
        {"lexeme": "10mm", "value": 10.0, "unit": "mm"},
        {"lexeme": "6mm", "value": 6.0, "unit": "mm"}
      ]
    }
  ]
}
```

## 7. 모호성·충돌 처리

| 입력 | 처리 |
|---|---|
| “적당한 크기의 홀” | `MISSING_NUMBER`, 숫자 질문 |
| “10만큼 떨어진” | `MISSING_UNIT` |
| “가운데쯤” | `AMBIGUOUS_LANGUAGE` |
| Form 6mm, 자연어 8mm | `FORM_TEXT_CONFLICT`, 두 값을 유지하고 실행 금지 |
| “표준 공차로” | 근거 표준이 없으면 `MISSING_TOLERANCE` |
| Datum 없는 절대좌표 | `MISSING_DATUM` |
| 3D 형상/구조해석 요청 | `UNSUPPORTED_REQUEST` |

확인 질문은 한 번에 해결 가능한 필드를 묶되 사용자가 선택하지 않은 값을 추천값으로 contract에 삽입하지 않는다.

## 8. 숫자·단위 보존 규칙

- `exact_text`는 원문 substring을 그대로 보존한다.
- `lexeme`은 `1/4in`, `6 mm`, `0.25"` 같은 원래 표기를 보존한다.
- LLM은 단위 변환값을 출력하지 않는다.
- 숫자가 form과 text에 동시에 있으면 evidence를 각각 만든다.
- 음수 공차, 비대칭 공차와 소수 자릿수를 그대로 보존한다.
- 원문에 없는 제조 프로파일 값을 자동 보완하지 않는다.

## 9. Tool Allowlist

Requirements Compiler가 사용할 수 있는 도구:

- `get_contract_schema`
- `get_form_values`
- `get_known_identifiers`
- `validate_contract_draft`
- `get_prompt_examples`

사용할 수 없는 도구:

- `drawing_generate`, `drawing_verify`, repair/export/Rhino 도구
- 파일 쓰기, shell, Python, RhinoScript, C# 실행
- 외부 웹 검색과 임의 표준 검색

## 10. 사후 검증

서버는 LLM 결과 저장 전 다음을 검사한다.

1. JSON Schema 일치
2. Prompt/schema version 일치
3. Proposal/evidence ID 유일성
4. 모든 `evidence_ids` 참조 유효성
5. Form/known/provisional 외 entity ID 금지
6. 출력 숫자가 evidence numbers에 존재하는지 확인
7. 숫자 lexeme과 value 일치
8. Form-text conflict 누락 검사
9. `needs_confirmation`과 confirmations/conflicts 일관성
10. 금지 필드(pass, hash, approval, verification) 존재 여부

검증 실패 시 한 번만 schema repair prompt를 사용할 수 있다. 두 번째 실패는 `DG_PROMPT_OUTPUT_INVALID`로 종료하고 폼 전용 모드를 제공한다.

## 11. Prompt Versioning

- System/user/schema/example을 `prompt_version`으로 묶는다.
- Prompt 변경은 semantic version을 따른다.
- Schema breaking change는 major version을 올린다.
- 평가 결과에는 model ID, prompt version, schema version과 input/output hash를 기록한다.
- 실행 중 prompt를 동적으로 자기수정하지 않는다.

## 12. 평가

자연어 50개 fixture를 다음 그룹으로 구성한다.

- 명확한 feature/constraint 15개
- 숫자·단위·datum 누락 15개
- Form-text conflict 10개
- Unsupported/standard 추정 유도 10개

지표:

- Schema valid rate
- Evidence reference validity
- Explicit number preservation
- Unauthorized number invention count
- Confirmation recall
- Conflict recall
- Unsupported request rejection

필수 목표는 unauthorized number invention 0건, invalid evidence reference 0건이다.

## 13. 개발 프롬프트 공통 규칙

[prompts/MASTER.md](../prompts/MASTER.md)와 각 작업 프롬프트는 다음을 강제한다.

- PRD/TRD/prompt-design 먼저 읽기
- 요구사항 ID 명시
- 한 세션/PR에 한 단계
- 사용자 변경 보존
- 임의 scope expansion 금지
- 관련 테스트 실행
- 동일 검사→수정→재검사는 최대 1회
- 완료되지 않은 항목과 위험을 handoff에 남기기

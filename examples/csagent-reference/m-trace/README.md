---
doc_category: intermediate
artifact_type: intermediate
last_reviewed: 2026-06-06
source: v3.2 §12 §L
---

# csagent M-Trace snapshot

此目录承载 **M-Trace trace schema 在 csagent 的具体实例**(per `modules/m-trace.md`)。

## csagent trace 字段映射

| portable shape 字段 | csagent 项目字段 |
|---|---|
| `session_id` | `session_id`(UUID,持久 ledger 主键) |
| `turn_id` | `turn_idx`(int,session 内序号) |
| `phase_id` | `phase`(枚举:propose / triage / resolve / confirm / escalate / close) |
| `tool_call_seq` | `tool_call_idx`(turn 内序号) |
| `projection_payload` | `projected_context`(JSON;PII redacted) |
| `tool_call_payload` | `tool_invocation`(yaml-schema 化) |
| `tool_response_payload` | `tool_result`(含 status / data) |
| `llm_response_raw` | `llm_raw`(full text + tool calls) |

## TODO

- [ ] csagent redaction pipeline 填空(PII fields list + hash/mask/drop strategy)
- [ ] emission path(file vs DB vs OTLP)
- [ ] retention policy(days + sensitive-data 策略)
- [ ] replay capability validation(M-Trace ready for S2 gate)
- [ ] Δ-13 pre-flight schema-alignment 实测填空

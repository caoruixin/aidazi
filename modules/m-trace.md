---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §8.2
---

# M-Trace(conditional)— Module Template

**Tier**: T1(conditional spec)
**适用**: Type A 必需;Type B 在 S2-required event 触发后必需;Type C 不需要
**框架立场**: 不强制特定 trace schema,但提供 portable shape + adaptation gate 模板
**加载时机**: S1 入口(**observability FIRST**,在 eval framework 之前)

## 抽象 trace schema 骨架

aidazi 推荐的 portable shape(字段名按项目命名习惯自适配):

```yaml
trace_event:
  event_id: <uuid>
  session_id: <uuid>             # 必填
  turn_id: <int>                 # 必填(turn 序号)
  phase_id: <string>             # 必填(来自 §10 phase pipeline)
  tool_call_seq: <int>           # 必填(当 turn 内 tool call 序号)
  timestamp: <ISO8601>

  # 推荐字段
  projection_payload:            # 送入 LLM 的上下文(redact 后)
    system_prompt: <text>
    context_snapshot: <object>
  tool_call_payload:             # tool 调用入参
    tool: <name>
    args: <object>
  tool_response_payload:         # tool 返回
    status: ok | error
    data: <object>
  llm_response_raw: <text>       # eval 与诊断同时需要
  metadata:
    redactions_applied: [<field>, ...]
```

## 必填 vs 推荐

| 类别 | 字段 | 理由 |
|---|---|---|
| **必填** | `session_id` / `turn_id` / `phase_id` / `tool_call_seq` | replay / debug 锚点;少一个就无法 root-cause |
| **推荐** | `projection_payload` | 否则无法验证 LLM 看到什么 context |
| **推荐** | `tool_call_payload` / `tool_response_payload` | tool dispatch 失败 root-cause |
| **推荐** | `llm_response_raw` | eval 与诊断双用;省下 LLM 自描 step |

## Adaptation gate 模板

每个项目接入 M-Trace 时填空:

```yaml
adaptation:
  project_field_mapping:
    session_id: <project field>
    turn_id: <project field>
    phase_id: <project field>
  redaction_pipeline:
    pii_fields: [<list>]
    redaction_strategy: hash | mask | drop
  emission_path:
    storage: <file | DB | OTLP | ...>
    rotation: <策略>
  retention_policy:
    days: <int>
    sensitive_data: <策略>
  replay_capability:
    can_replay_session: true | false
    replay_tool: <path>
```

**Gate 判据**(M-Trace ready for S2 entry):
- `session_id` / `turn_id` / `phase_id` / `tool_call_seq` 字段在所有 trace event 中**实际存在**(不是 schema 里写了但代码没填)
- 至少 1 个 session 完整 trace 已被 replay 验证
- redaction 已通过法务 / 安全签字

## Reverse trigger(must add observability when ...)

任一发生即触发 observability 补齐:

- session 无法 replay
- bad-case 无法 root-cause
- projection 漂移与代码不一致(诊断)
- eval 信号与 manual review 持续 divergence(Δ-17 P1 症状)

## Δ-13 pre-flight schema-alignment checklist

进入 S2/S3 前,跑 schema alignment pre-flight:

- [ ] M-Eval 消费的 CaseSpec 字段是否能从 trace 字段重建?
- [ ] phase_id 与 §10 phase pipeline 实际 phase 名一致?
- [ ] tool_call_payload 与 Δ-3 Decision #6 工具定义一致?
- [ ] redaction_pipeline 没有把 eval 必需字段(如 escalation reason)过度 redact?
- [ ] 1 个真实 session 完整 replay → 与原 session 输出一致?

任一不通过 → 阻止 S2 启动。

## Anti-pattern

- **trace 比 runtime 晚搭** — 违反 Δ-11 S1 "observability FIRST" 原则
- **必填字段只写 schema 不写代码** — 编译过但生产 trace 字段是 null
- **redact 过度** — eval 必需字段也被打码,导致 root-cause 无法做
- **每 project 自创 schema** — 与 §10 phase pipeline 不对齐,M-Eval 无法消费

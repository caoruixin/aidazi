---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §10
---

# Type A Runtime Architecture Skeleton(Δ-6)

**Tier**: T1(仅 Type A AI Agent 轨道适用)
**加载时机**: S0 末 / S1 入口
**主导**: Tech Lead 填空 phase 集合;Research Agent 引用同领域调研

## 为什么需要骨架

v2 §J / §K 给了 M-Eval / M-Trace,但未给"agent 内部 turn loop 长什么样"。Δ-6 补齐 — 提供 **PORTABLE-SKELETON**(intent gate + multi-phase pipeline + carry-over state),由项目按 domain 填具体 phase 名字与个数。

## 推荐骨架(T1)

```
                          ┌─────────────────────────────┐
incoming user turn ──────▶│  intent classification gate │  ← 单一入口
                          └──────────────┬──────────────┘
                                         │
                  ┌──────────────────────┼──────────────────────┐
                  │                      │                      │
              intent_X               intent_Y               intent_Z
                  │                      │                      │
                  ▼                      ▼                      ▼
        ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
        │ phase pipeline X │   │ phase pipeline Y │   │ phase pipeline Z │
        └─────────┬────────┘   └─────────┬────────┘   └─────────┬────────┘
                  │                      │                      │
                  └──────────────────────┼──────────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │ intent-switch hook  │  ← 任意 turn 可触发
                              └─────────────────────┘  ← 可切回(carry-over state)
```

## 每 phase 内部契约(T1)

```yaml
phase:
  name: <T2-domain-specific>      # 比如 propose / triage / resolve / confirm
  inputs:
    - projected_context           # 来自 Δ-3 decision #3
    - state_handle                # 来自 Δ-3 decision #4
  steps:
    - model_interaction           # LLM 调用 + tool-calls
    - tool_execution              # capability-gated(Δ-3 decision #6)
  exit_condition:                 # 条件驱动,LLM 半决策
    - to_next_phase_if: <cond>
    - to_intent_switch_if: <cond>
    - to_escalate_if: <cond>
```

## T1 vs T2 vs T3 边界

| Tier | 内容 | 谁拥有 |
|---|---|---|
| **T1 portable** | intent gate / multi-phase pipeline / per-phase = model+tool+conditional-progression / intent-switch with carry-over | aidazi framework |
| **T2 domain-specific** | phase 的具体**名字与个数**(csagent: propose→triage→resolve→confirm→escalate→close 六阶;别 domain 可三阶) | 项目 Tech Lead 决定 |
| **T3 project-specific** | phase 内部的 tool 集合、policy 表达式、grounding rules | 项目 dev + Tech Lead 实现 |

## csagent 范例(详 §L worked example)

csagent 的具体 phase 名字进 `examples/csagent-reference/runtime-skeleton/`,**不**进框架骨架。该范例展示:
- 6 phases: propose → triage → resolve → confirm → escalate → close
- 每 phase 一个 `phases/<name>.md` 填空
- intent gate 输入 = Δ-2 D2 user-problem-taxonomy

## 与其他 Δ 的连接

- **Δ-2 D2**: 提供 intent gate 的 intent 集合输入
- **Δ-3 decision #3 / #4 / #6**: 决定 phase 内 inputs/steps 形态
- **Δ-9 OBS triage**: phase 失败案例进入 R-item / OBS 分类
- **M-Trace §8.2**: trace schema 的 `phase_id` 字段对应此 skeleton 的 phase.name

## Anti-pattern

- 把 intent gate 与 phase pipeline 合并成一个 LLM 调用 — 失去"我处于哪个 intent"的 trace 锚点
- phase 内部无 exit_condition 显式声明 — LLM 自己决定何时进下一 phase,无 verification gate
- intent-switch 不 carry-over state — 用户中途打岔再回来,前文丢失
- phase 数 > 10 — 检查是否应折叠到子 phase 或拆 intent

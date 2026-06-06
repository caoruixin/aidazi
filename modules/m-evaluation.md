---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §8.1
---

# M-Evaluation(light)— Module Template

**Tier**: T1(主要 Type A;Type B 在 S2-required event 触发后必用;Type C 不用)
**Spec-not-impl**: aidazi 仅提供 spec + adaptor pattern;**不**提供 runtime SDK
**加载时机**: S2 启动前
**主导**: Tech Lead 落地 4 components;Code Reviewer 在 §5.6 manual review pass 时复核

## 4 components 契约

### 1. CaseSpec schema

单 case 的输入 / 期望行为 / 范围 / tier 归属。

```yaml
case_id: <unique>
tier: 0 | 1 | 2 | 3
input:
  user_turn: <text>
  context: <session state>
expected:
  behavior_class: <intent / next_action / escalation 等>
  forbidden_classes: [<class>, ...]    # 反向(must-not)
scope:
  in_scope: [<UC>, ...]
  out_of_scope: [<UC>, ...]
notes: <自由文本,给 manual reviewer>
```

### 2. Judge contract

单 case 的判定逻辑(rubric / 客观判定 / LLM judge)。Judge 必须可被 mock(单元测试)与 real LLM(eval evidence gate per §5.7)两种模式触发。

### 3. Suite manifest

case 集合 + tier 比例 + manual review hook。manifest 显式声明 tier-0 case 占比下限(safety floor)。

### 4. Score aggregator

跨 case 聚合 + baseline 对比 + regression profile。**不**输出单一 composite score 作 hard gate(per §5.5);仅作为 observation。

## 4-tier 金字塔

| Tier | 内容 | gating 性质 |
|---|---|---|
| **Tier-0** | Safety / PII / 合规底线 | **hard gate**(任一失败 → close 失败) |
| **Tier-1** | Basic correctness(grounding / tool dispatch / projection) | **hard gate** |
| **Tier-2** | Behavioral correctness(UC routing / next action / escalation posture) | observation + regression watch |
| **Tier-3** | Outcome / contained problem solving | observation |

旧 L1/L2/L3 三层模型 **deprecated to reference**;Four-Tier 是 v2 confirmed canonical。

## Highlight bootstrap(S2 启动的最小集)

**3 必过**:
1. ≥10 Tier-0 cases 全部 pass(safety floor)
2. ≥20 Tier-1 cases pass rate ≥90%(basic correctness)
3. Manual review × eval verdict 一致率 ≥90% on 10 random cases(S2.5 validity check 预演)

**3 必不能**:
1. 不能用 mocked LLM 跑 Tier-2/3 作为 prompt-effect evidence(违反 §5.7)
2. 不能用 single composite score 作 hard gate(违反 §5.5)
3. 不能在 S1.5 未通过前启动 S2(违反 Δ-17 P2)

## Anti-gaming forbidden list

- **不允许**自动 case generation 在 S2 阶段(放大坏 case 设计;Δ-11 anti-pattern)
- **不允许**widening CaseSpec to accept actual buggy output(§5.4)
- **不允许**relaxing rubric to mask regression
- **不允许**OBS-specific metric 作为 default primary gate(Δ-9)

## Integration guide

1. **Adaptor pattern**:每新项目接入时,提供 adaptor 把项目 runtime trace → CaseSpec compatible 形态;**aidazi 不提供 runtime SDK**
2. **Trace 依赖**:M-Eval 必须能消费 M-Trace 输出的 portable trace shape(详 `m-trace.md`)
3. **Bad-case suite gate**:M-Eval 的 §5.6 curated bad-case suite 是 milestone close 的 primary gate(详 `process/badcase-lifecycle.md`)

## Δ-15.D 行业研究(Type A 必做)

1. Survey 2-3 同领域 eval 方案
2. 识别 scope / assumptions / gaps
3. Synthesize own overall plan
4. Specialize for own context(domain knowledge / tools / policy)
5. 产出 `discovery/industry-synthesis-<id>.md`(Δ-12 intermediate;Δ-14 列入 S0 gate)

## Anti-pattern

- 把 M-Eval 当 runtime SDK 期望 — 框架只给 spec;实现是项目工程问题
- Tier-2/3 case 比 Tier-0/1 多 — 倒金字塔,safety 没保住先调"行为"
- judge 仅有 mocked 实现 — 违反 §5.7 evidence gate

---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.9 Δ-15
---

# Agent Design Elicitation(Δ-15)

**Tier**: T0(三轨道通用;Part C / Part D profile-aware)
**加载时机**: S0 Discovery 后期(Δ-2/Δ-3 之后)
**主导**: Tech Lead 引导;**Customer 是答题人**(Part A 必 human-only)
**性质**: heuristic Q&A,**非** checklist;答 ≠ 通关,答 → 触发讨论

## Part A — 6 mandatory questions(human-signoff required)

| # | 问题 | 谁答 | 备注 |
|---|---|---|---|
| 1 | **Domain** 行业 / sub-area / 范围 | human only | 用一句话,不接受"全行业" |
| 2 | **Goal** 1 句可量化的成功 | human only | 例:"30 天内 CSAT ≥ 4.2",不接受"提供更好服务" |
| 3 | **Problems** 有界清单(非模糊集) | human only | Δ-2 D2 输出的 top-N intent;不接受"用户的各种问题" |
| 4 | **Method** intent-classification + multi-phase pipeline?OR workflow?OR 单 LLM 调用? | 框架引导 + human 选 | 决定 Δ-3 Decision #1 |
| 5 | **Knowledge** 领域知识 inventory + 来源 + freshness 策略 | human(domain)+ 框架(schema) | Δ-16 prereq #4 输入 |
| 6 | **Boundary** agent-loop 拥有 vs 外部 harness 保证(Constitution §1.3/§1.4) | 框架 Q&A + human 选 | LLM-owns vs Runtime-owns 边界,详 §1 |

### Part A.Q6 boundary Q&A 范例

> **Q**: "用户对最近一单的退款诉求"是 agent 自己识别意图,还是 Runtime 用关键词路由?
> **A 选**: agent 识别(LLM owns user goal,§1.3)
>
> **Q**: "用户身份核验"是 agent 提示生成话术,还是 Runtime 调外部 SSO?
> **A 选**: Runtime 调外部 SSO(safety floor,§1.4)
>
> **Q**: "FAQ 引用必须 verbatim 还是允许 paraphrase"?
> **A 选**: verbatim(grounding floor,§1.4),agent 不得修改引用文本

### Δ-15.A1 human-signoff 规则

- 未签字 brief 下游不得消费(Δ-3 / Δ-11 / sprint_objective 引用阻塞)
- 已签字 brief 进入 Δ-12 intermediate 类,进 §0 cold-start 指针表
- Brief front-matter 增字段:

```yaml
human_signoff:
  signed_by: <name>
  signed_on: <YYYY-MM-DD>
  signed_version: <git-sha>
```

### 重签触发规则

- **重签 trigger**: 六必答任一**实质变更** / Part D 综合稿被替换
- **不触发重签**: Part B 单纯增删工具/技能条目(增量,non-breaking)
- **PB1 PENDING**(v3.2 §13.1):Q1/Q2/Q6 core re-sign vs Q3/Q4/Q5 amendment-with-incremental-sign 分级 — 首例 Type A 决断

## Part B — 4 inventories(profile-aware,per Q3 + Δ-15)

| Profile | inventory 4 槽位 |
|---|---|
| Type A | Knowledge / Tools / **Skills** / Policy |
| Type B | Knowledge / Tools / **SOPs**(替代 Skills) / Policy |
| Type C | Knowledge / Tools / **Off-the-shelf Skills**(借用社区/团队预制) / Policy(可极简) |

每槽位记录:类目名、来源、freshness / 版本 / 维护方。

## Part C — Tool vs Skill decision tree(仅 Type A)

- 原子能力 + agent 全控 → **tool**
- 子任务有 mandatory tool sequence + adaptive logic → **skill**
- 跨多 flow 重复模式 → 包成 **skill**
- >15-20 skills → 检查分解(csagent 6 skills = phase × resolve-pattern granularity,VERIFIED)

**Type B 替代**:Part C 替换为 "SOP step 划分指引" — 何时一动作独立成 step:
- 有独立 verification gate
- 有失败回退路径
- 业务可观测

**Type C 简化**(PB5):不要 tool-vs-skill 决策树;只问"有没有现成的;有就用,没有拼 tool"

## Part D — 0→1 industry research methodology(profile-aware)

| Profile | Part D 行业调研 | 替代物 | 输出 |
|---|---|---|---|
| **A · AI Agent** | **必做**(MUST) | 无 | `discovery/industry-synthesis-<id>.md`(2-3 家方案对比 → 综合 → 本场景特化) |
| **B · Agentic Workflow** | 不要求 | SOP / 流程设计调研(严格可选) | 若做 `discovery/sop-survey-<id>.md`;不做则 brief 显式 "SOP survey: skipped, rationale: <…>" |
| **C · Demo App** | 不要求 | 现成技能清单(off-the-shelf inventory) | `discovery/offshelf-skill-inventory-<id>.md`(可极简,bulleted) |

**Industry-synthesis 5 步骤(Type A 强制)**:
1. Survey 2-3 同领域方案
2. 识别 scope / assumptions / gaps
3. Synthesize own overall plan
4. Specialize for own context(domain knowledge / tools / policy)
5. 产出 intermediate doc

**Δ-15.A4 PB2 隐式答**:Part D Type A 是 **S0→S1 硬 gate**(与 brief 人签字并列);Type B 否;Type C 否(包含在 1-page demo brief 内即可)

## Anti-pattern

- 跳过 Part A 直接进 Part B 工具盘点 — 没有 goal / boundary 做锚,工具集变成 wishlist
- Part D Type A "我们这种独特场景没有 industry 案例" — 几乎一定有相邻案例;借口跳过的代价是 Δ-17 P1 早期不知怎么走
- 未签字 brief 被 Tech Lead 在 sprint_objective 引用 — 阻塞规则失效,Customer 后续反复修改导致 sprint 重做

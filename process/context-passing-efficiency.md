---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.4
---

# Context-passing Efficiency(Δ-5)

**Tier**: T0(三轨道通用)
**加载时机**: P0
**主导**: 所有 prompt artifact 的发布者(Tech Lead / Dev / Customer / Research)

## Constitution 增加的条款

> Context-passing 必须同时满足 **sufficient**(下游不需要回溯上游会话)**AND efficient**(不浪费 token / 不强制下游加载无关 context)。任何 prompt artifact 的发布者必须为该 artifact 声明显式 token budget。

**为什么两条都必要**:
- 只 sufficient 不 efficient → 把整本 governance + 5 sprint archive 塞进 prompt,token 烧光,下游 LLM context window 紧张时丢前文
- 只 efficient 不 sufficient → 下游 agent 无法在不依赖 chat history 的前提下自洽执行(违反 §9 prompt-artifact-rules 自洽 invariant)

## 操作化 front-matter

每个 prompt artifact(`compact/sprint-NNN-dev-prompt.md` / `compact/M<N>-review-prompt.md` 等)在 front-matter 增加:

```yaml
context_budget:
  target_tokens: 8000            # 估计值;通过 token-count 工具或 1 token ≈ 3-4 字符近似
  load_list:                     # 显式必须加载清单(@-include 或文内引用)
    - AGENTS.md                  # auto-load 默认
    - docs/sprint_objective.md
  do_not_load:                   # 显式排除清单(避免下游"为了保险加载"全部)
    - docs/sprints/sprint-001-*  # 历史 sprint,与本次无关
    - docs/proposals/*           # 前瞻设计,与本 sub-sprint 无关
self_contained: true             # 已嵌入所有契约内容,不依赖外部 chat
```

## Budget 数字基线

`target_tokens` 的默认值由项目自行根据 LLM 上下文窗口与同步 artifact 数量校准。常见经验值(per v3.2 §13.4 carry):

| Artifact 类型 | 典型 budget |
|---|---|
| `compact/sprint-NNN-dev-prompt.md` | 6-10k tokens |
| `compact/M<N>-review-prompt.md` | 10-15k tokens(嵌入多 sub-sprint 上下文) |
| `failure-brief-<id>.md` | 1-2k tokens |
| Research handoff to Tech Lead | 4-8k tokens |

注:framework 不给硬性数字;由 Tech Lead 在项目 first-trial 时校准并写入 `docs/context-budget-baseline.md`(intermediate)。

## 验证手段

- **Sufficient 自检**: 在空 chat 中粘贴 artifact,询问"你能否在不查其他文件的前提下知道要做什么"
- **Efficient 自检**: 跑 token-count 工具,对照 `context_budget.target_tokens`;超 1.5× 触发 split-trigger(Δ-10)

## Anti-pattern

- 不填 budget 直接写 prompt — 下游无法判断 artifact 是不是已超
- `do_not_load` 留空 — 下游 agent 出于保险加载相关目录全部文件,context bloat
- `self_contained: false` — 违反 §9 invariant;intermediate prompt 必须自洽

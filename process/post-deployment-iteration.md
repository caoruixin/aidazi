---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §5 Δ-9
---

# Post-Deployment Iteration — OBS / Autoloop Role-Split(Δ-9)

**Tier**: T1(Type A + Type B 适用;Type C 不适用)
**加载时机**: 系统已部署、有真实流量后
**主导**: Tech Lead(L1 triage)+ Autoloop Driver(L2 optimization)

## 核心区分:OBS ≠ R-item

| 概念 | 定义 | 谁拥有 | 触发 |
|---|---|---|---|
| **OBS**(Observation) | 从 case / trace / eval 得到的**行为改进候选** | Tech Lead 拥有 triage;Autoloop Driver 拥有 generation | 实地观察 / 用户反馈 / 度量降级 |
| **R-item** | runtime / substrate 变更 | Tech Lead 编排 sprint 落地 | OBS 依赖未就绪能力时,先开 R-item |

混淆 OBS 与 R-item 是常见错误:把 OBS"agent 在 X 场景应答不够好" framing 成"Tech Lead 解决 OBS X",会让 Tech Lead 退化为 operator,而 Autoloop Driver 失业。

## 两层模型

### L1 — Runtime Eligibility Triage(Tech Lead 拥有)

OBS 进来后,Tech Lead 先判断:

1. **Eligible**: 当前 runtime/substrate 已就绪,可直接进 L2 autoloop
2. **Blocked-by-enabler**: 依赖一个尚未实现的能力(新 tool / 新 trace 维度 / 新 policy)
   - 开 R-item;OBS 暂挂 `not eligible`;enabler 落地后回 L1 重判

不容许把 not-eligible OBS 直接喂 autoloop — autoloop 会无功而返。

### L2 — Autoloop Optimization(Autoloop Driver 拥有)

进 L2 的 OBS 走**一般批量模式**:

- 主指标 = 整体 eval + regression profile(per Δ-11 §9.6 / §5.6 bad-case suite)
- OBS-specific metric 仅作 **secondary diagnostic** — 用来验证候选确实修了目标 OBS,但不作为通过 gate
- 默认运作: 多个 OBS 共享一次 outer-loop autoloop,降低批量成本

## Role split — Tech Lead vs Autoloop Driver

| 职责 | Tech Lead | Autoloop Driver |
|---|---|---|
| OBS triage 与 dependency gating | ✓ | — |
| Experiment spec 编写 | ✓ | — |
| Acceptance review | ✓ | — |
| Candidate generation | — | ✓ |
| Registry / procedure prompt 编辑 | — | ✓ |
| Batch eval 调度 | — | ✓ |
| Ranked proposals 给 Tech Lead | — | ✓ |

**明令禁止 framing**:"Tech Lead solves OBS X"。这种说法把两个 role 的边界抹掉。

## Default 工作流

```
OBS 进 → Tech Lead L1 triage
                │
        ┌───────┴───────┐
        │               │
    eligible        blocked
        │               │
        ▼               ▼
   L2 batch        open R-item
   autoloop        sprint 落 enabler
        │               │
        ▼          (回 L1 重判)
   ranked proposals
        │
        ▼
   Tech Lead acceptance review
        │
        ▼
   入 Δ-12 sprint_objective / 上线
```

## Anti-pattern(forbidden list)

显式禁列(必须写入 Autoloop Driver role doc):

- **"Tech Lead solves OBS X"** framing — 让 Tech Lead 退化为 operator,Autoloop Driver 失业
- **每个 OBS 一个专属 autoloop** — 浪费批量成本;outer-loop 同时跑多 OBS 更经济
- **OBS-specific metric 作为默认主 gate** — 触发 gaming(候选把 metric 推高但伤害其他 surface)
- **L1 triage 跳过,blocked OBS 直接喂 autoloop** — autoloop 在无 enabler 的情况下产不出有意义候选

## 与其他 Δ 的连接

- **Δ-11(§9.6)**: S5 entry condition 要求 anti-gaming forbidden list 已落地;本文档列入
- **Δ-12(§9.7)**: OBS 与 R-item 都进 `action_bank.md` open ledger,但分类标签不同(`obs` vs `r-item`)
- **Δ-16(§9.10)**: prereq deferred 触发的 OBS-id 走相同 triage 流
- **§5.6 bad-case suite**: L2 autoloop 主指标的核心组件

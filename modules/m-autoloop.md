---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §8.3 (Δ-9 derived)
---

# M-Autoloop(conditional)— Module Template

**Tier**: T1(仅 Type A;Type B 不适用;Type C 不适用)
**Conditional spec**: 不强制实现;实现时必须遵循以下契约
**加载时机**: S5 启动前
**主导**: Autoloop Driver 拥有 generation;Tech Lead 拥有 L1 triage + acceptance review

## 条件适用

- **S5 entry condition**:
  - eval 框架经 S2/S2.5 验证可信(Δ-17 P3 教训)
  - data 完整、Δ-16 prereq 全部 READY 或显式 deferred
  - Δ-9 anti-gaming forbidden list 已落地到 driver role doc
- **主指标 = 整体 eval + regression profile**(**不**是 OBS-specific metric)
- **默认运作**:OBS → 一般 outer-loop autoloop;每个 OBS 专属 autoloop 是 anti-pattern

## OBS triage L1/L2(详 `process/post-deployment-iteration.md`)

| 层 | 拥有者 | 职责 |
|---|---|---|
| **L1 Runtime Eligibility Triage** | Tech Lead | OBS 进来 → 判 eligible / blocked-by-enabler;blocked → 先开 R-item |
| **L2 Autoloop Optimization** | Autoloop Driver | 批量 candidate generation;主指标 eval+regression;OBS-specific metric 仅 secondary |

## Autoloop driver 角色边界

| 拥有 | 不拥有 |
|---|---|
| Candidate generation | OBS triage(Tech Lead) |
| Registry / procedure prompt 编辑 | Experiment spec(Tech Lead) |
| Batch eval 调度 | Acceptance review(Tech Lead) |
| Ranked proposals 输出 | sprint_objective 编写(Tech Lead) |

## General batch 默认模式

```
multiple OBS (eligible after L1)
        │
        ▼
   single outer-loop autoloop run
        │  (主指标: 整体 eval + regression profile)
        ▼
   ranked candidates
        │
        ▼
   Tech Lead acceptance review per candidate
        │
        ▼
   accepted candidates 入 sprint_objective
```

**OBS-specific metric 作 secondary diagnostic**:用来验证候选确实修了目标 OBS,但**不**作为通过 gate。

## Explicit / default 双模

| 模式 | 触发 | 主指标 |
|---|---|---|
| **Default(general batch)** | Tech Lead L1 把多 OBS 都标 eligible | 整体 eval + regression profile |
| **Explicit(targeted)** | 单 OBS 严重程度 P0 / Tech Lead 显式声明 | 主指标 + OBS-specific secondary;但 P0 仍以整体 regression 为 gate |

**Explicit 模式不豁免 anti-gaming forbidden list**。

## Anti-gaming forbidden list(必须写入 driver role doc)

1. **"Tech Lead solves OBS X"** framing — turns Tech Lead into operator,driver 失业
2. **每 OBS 一专属 autoloop** — 浪费批量成本
3. **OBS-specific metric 作主 gate** — 触发 gaming(候选把 metric 推高但伤害其他 surface)
4. **L1 triage 跳过,blocked OBS 直接喂 autoloop** — autoloop 无 enabler 产不出有意义候选
5. **首夜 discard 视作 runtime issue** — Δ-17 P3 教训;首批 overnight 是 eval-stress-test,不是 runtime bug

## Acceptance review checklist(Tech Lead)

每候选评估:
- [ ] 整体 eval(Tier-0/1)无 regression
- [ ] 目标 OBS 已修(secondary 验证)
- [ ] manual review §5.6 bad-case suite 上 pass
- [ ] 候选不违反 §1.7 forbidden(keyword / regex / if-else 等语义硬编码)
- [ ] 候选不引入新 Tier-0 invariant(若是 → human_review_required)

## Anti-pattern

- S1/S2 阶段开 autoloop(eval 不可信)
- S5 entry condition 未满足跑首夜 — Δ-17 P3 教训
- driver 越权改 sprint_objective
- 候选输出过度自动化 acceptance 跳过 manual

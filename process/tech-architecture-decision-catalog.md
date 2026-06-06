---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.2
---

# Tech Architecture Decision Catalog(Δ-3)

**Tier**: T0(决策**目录**是 T0;决策**结果**是 T2/T3)
**加载时机**: 紧跟 Δ-2 之后(S0 末)
**主导**: Research + Tech Lead 联合产出;Customer 签字 Decision #1 与 Decision #8

## 核心原则

框架不替项目选,框架只确保项目**知道自己选过**。每项决策有 4 字段:

```yaml
decision_<n>:
  chosen: <option>
  rationale: <一句话>
  reversibility: hard | soft | reversible-at-cost
  trigger_to_revisit: <事件>
```

`hard`(decision lock-in,Type A 切换 / 评估开关)在 sprint 中段不得反转;`soft`(投影模型、状态管理)允许下一 milestone 调整;`reversible-at-cost`(memory / tools / policy 表达式)记录代价。

## 8 项决策表

| # | 决策项 | 选项集 | 推迟许可 | reversibility 默认 |
|---|---|---|---|---|
| 1 | **应用类型**(轨道选择) | Type A / B / C | **不允许**(必 P0 决);**绑定 S2-required event 触发记录槽位**(Δ-14) | hard |
| 2 | 抽象层次 | single-agent / multi-agent / no-agent | 不允许 | hard |
| 3 | 上下文投影模型 | per-turn 全量 / 增量 / projection-by-skill | 允许 P1 | soft |
| 4 | 状态管理 | stateless / session / cross-session / 持久 ledger | 允许 P1 | soft |
| 5 | 记忆 | 无 / 短期 / 长期 / RAG-as-memory | 允许 P1 | reversible-at-cost |
| 6 | 工具定义 | enum / yaml schema / dynamic registry | 允许 P1 | reversible-at-cost |
| 7 | Policy / gadgets | prompt-level / runtime-gate / 混合 | 允许 P1 | reversible-at-cost |
| 8 | 评估 | yes / no / spec-only(M-Eval-light)/ 全量 | **必 P0**(Type A 必 yes;Type B 看 S2-required event;Type C 必 no) | hard |

## S2-required event 触发记录(绑定 Decision #1)

Type B 项目若发生以下任一事件,Decision #1 槽位 `s2_required_event_triggered: true` 锁定,maturity 视角向 Type A 迁移(详 `profile-aware-maturity.md` §Δ-14.d):

- 首次接入终端用户流量
- 承担 SLA / 合规义务
- 引入 LLM 自主语义决策(原 deterministic step 之上加 LLM 判断)
- PII / 安全底线进入 §1.4 Runtime owns

触发即必须补 M-Eval + M-Trace 全套;Δ-3 catalog 增 `triggered_on: <YYYY-MM-DD>` 字段。

## 输出物

| 文件 | 内容 |
|---|---|
| `decisions/decision-catalog.yaml` | 8 项决策的 4 字段填空 |
| `decisions/decision-rationale.md` | 每项 1-2 段决策原因 + 拒绝的备选 |

doc_category: intermediate;命名带 source sprint ID(决策是在哪轮签的)。

## Anti-pattern

- 8 项一次性全填到 P0 — Δ-13 PB 提:**倾向**先决必决 3 项(#1 / #2 / #8),其余 P1
- 不填 reversibility — sprint 中段反转 hard 决策的代价高,事先不标注 = 默认全 reversible(灾难)
- Decision #1 不签字 — 轨道未定,后续所有 Δ-14/Δ-15/Δ-16 profile-aware 适配全失效

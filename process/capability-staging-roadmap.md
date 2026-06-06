---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.6 + §9.11(d)
---

# Capability Staging Roadmap(Δ-11 + Δ-17 三新增 stage)

**Tier**: T0(三轨道通用,profile-aware)
**加载时机**: S0 末 / S1 入口 / 每次升档前
**主导**: Tech Lead + Customer 联合裁决

## 完整 stage 序列(S1.5 / S2.5 / S3.5 / S5 为 Δ-17 新增)

| Stage | 简称 | 关键产物 | Type A | Type B | Type C |
|---|---|---|---|---|---|
| **S0** | Domain understanding | Δ-2 discovery + Δ-3 decision catalog + Δ-15 brief + Δ-16 prereqs | 必需 | 必需 | 必需(轻量) |
| **S1** | First runnable + observability | First runtime + observability/trace FIRST;manual cases;NO eval framework;NO autoloop | 必需 | 必需 | 必需 |
| **S1.5** **NEW(Δ-17)** | Architecture stress-test 5-10d | Manual cases 10-15 / trace coverage 检查 / 架构再评估;若 pivot 在 deck → 现在 pivot | 必需 | 必需 3-5d | 可跳过 |
| **S2** | Basic eval(Tier-0/1) | Manual CaseSpec;case→score→review chain;证明尺子准 | 必需 | S2-required event 触发后 | 不需要 |
| **S2.5** **NEW(Δ-17)** | Eval validity check 3-5d | "Intentional break → eval must catch" ≥3 examples;manual×eval 一致率 >90% | 必需 | S2 触发后 | 不需要 |
| **S3** | Eval-driven runtime iter | OBS-driven iteration(Δ-9);Tier-2/3 扩展 | 必需 | S2 触发后 | 不需要 |
| **S3.5** **NEW(Δ-17)** | Architecture pivot buffer | 1-2 次 pivot 预算;不视为 failure | 必需 | 视情况 | 不需要 |
| **S4** | Eval framework upgrade | 周期 fold-back;eval 自身随系统能力升级 | 必需 | 触发后 | 不需要 |
| **S5** **NEW(Δ-17)** | Autoloop pre-flight measurement stress-test 10d | 首批 autoloop overnight 视作 eval framework stress test;预期 5-10d 修测量框架(NOT runtime) | 必需 | 不适用 | 不适用 |
| **S6** | Autoloop trustable signal | Autoloop 候选可被 manual 复核通过 | 可选 | 不适用 | 不适用 |

## 反向触发表

| 触发条件 | 反向行为 |
|---|---|
| Type B 发生 S2-required event(详 `profile-aware-maturity.md` §Δ-14.d) | **must add eval**(补 S2 全套) |
| Eval Tier-0 失败率 >5% 持续 ≥3 sprint | **must demote eval**(回 S2.5 重做 validity check) |
| autoloop overnight discard rate >80% 在 tier 0 首批 | **must pause autoloop**(回 S5 修测量框架) |
| 真实部署后产生 OBS 量 >20 条/周持续 | **must add autoloop**(进 S5/S6) |
| 架构 pivot 提议 mid-milestone | **must buffer**(走 S3.5 预算) |

## Δ-13 软化 — "stage-stable heuristic"(非门控)

原 "F 架构锁" → "**架构相对稳定 / 阶段稳定**"。这是 per-stage 属性,**不是**永久状态、**不是**自动门控、**不是**全局锁。

**操作性启发式**:近 5-10 commit 中 runtime 路径占比 ≤ ~20% 且 semantic 路径占比 ≥ ~60%,持续 ≥ 3 个 sub-sprint;由 Tech Lead+human 主观判定,**可作为升档 S3 的一项支持证据**。

**框架不提供脚本**: `git log -n 10 --stat -- <runtime-paths>` 一类 grep/git 例子作为方法论附录;判断权归 Tech Lead + human。详 `stage-stable-heuristic.md`。

## 动态过程免责(Δ-13.c)

> 架构相对稳定是 per-stage 属性,不是永久状态。新增主功能 / 引入新主路径 / 跨越生产部署边界 → 预期暂时回到 S1/S2 重走 observability + eval。这是**设计期望**而非倒退。

## Anti-patterns(Δ-11 显式)

- **S2 启用自动 case generation 放大坏 case 设计**(eval 还没证明准就开始量产 case)
- **S1/S2 开 autoloop**(eval 不可信 → autoloop 无法分辨好坏变更)
- **不区分 R-item vs OBS**(强迫 autoloop 做不可能的事;详 `post-deployment-iteration.md`)
- **把 S5 首夜 discard 视为 runtime 问题**(Δ-17 P3 教训)

## 与其他 Δ 的连接

- **Δ-14 profile-aware maturity**: 矩阵的 Type A/B/C 列就是 §3.2 9-cell 表
- **Δ-17 P1-P4**: 弯路对应阶段补丁,详 `common-detours-and-warnings-typeA.md`
- **§5.6 bad-case suite**: 升档 S3 时主指标
- **§5.7 mocked-LLM evidence gate**: S2.5 的"intentional break → eval must catch"是 real-LLM gate

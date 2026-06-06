---
doc_category: intermediate
artifact_type: intermediate
last_reviewed: 2026-06-06
source: v3.2 §12 + Δ-17(g)
snapshot_date: 2026-06-06
source_commit: csagent-HEAD@2026-06-06
---

# csagent 54-day timeline — the worked example for Δ-17

**性质**:Δ-17 `common-detours-and-warnings-typeA.md` 的 **the** worked example,date-stamped。

**总计**:**287 commits / 10+ milestones / 54 calendar days(2026-04-13 → 2026-06-05)**

## 7 阶段时间线

### ① S0 Design phase(2026-04-15 → 2026-04-22)

| 维度 | 内容 |
|---|---|
| 日历天 | 8 days |
| 活跃天 | ~6 |
| 关键 commit | UC spec / FAQ schema / tool spec / scripts ready 4/22 |
| 坎点 | Spec 完整但 real entity data 未落地 → 埋下 P1 根因 |
| Δ-17 对应 | S0 阶段;映射 ✓ |

### ② Δ-15 brief 阶段(2026-04-19 → 2026-04-22)

| 维度 | 内容 |
|---|---|
| 日历天 | 4 days(与 ① 平行) |
| 活跃天 | ~3 |
| 关键 commit | initial brief drafts;persona / UC list |
| 坎点 | Industry-synthesis 当时未做(Δ-15.D 还未存在) |
| Δ-17 对应 | S0 Δ-15 子阶段 |

### ③ S1 first runnable(2026-04-22 → 2026-05-02)

| 维度 | 内容 |
|---|---|
| 日历天 | 11 days |
| 活跃天 | ~9 |
| 关键 commit | first orchestrator;manual cases pass;observability v1 |
| 坎点 | observability 与 runtime 同期搭,未提前;trace coverage 不全 |
| Δ-17 对应 | S1;**S1.5 被跳过** → 直接进 ④ |

### ④ S2 eval v1 全 L1/L2/L3 一次性(2026-04-23 → 2026-05-03)

| 维度 | 内容 |
|---|---|
| 日历天 | 11 days(与 ③ 平行) |
| 活跃天 | ~9 |
| 关键 commit | eval v1 framework;L1/L2/L3 三层 judge;CaseSpec v0.1 |
| 坎点 | L3 judge 哲学锁太早("path checking" vs "outcome-oriented");eval framework 搭在 monolithic prompt 架构上 |
| Δ-17 对应 | S2;**P2 根因点**;**S2.5 被跳过** |

### ⑤ S3 Eval-driven runtime iter(2026-05-04 → 2026-05-18)

| 维度 | 内容 |
|---|---|
| 日历天 | 15 days |
| 活跃天 | ~14(5/05 单日 19 commits) |
| 关键 commit | Sprint 1-35;intent reorg;tool dispatch hardening |
| 坎点 | data 5/20 落地 → 5/04-5/20 跑在错误 baseline 上(P1 显形);5/17 M2 mid-flight pivot 从 "Skill foundation" 到 "Skill Registry"(P4) |
| Δ-17 对应 | S3 + **S3.5 unplanned**;P1 + P4 显形 |

### ⑥ S4 Eval framework upgrade(M3-M5, 2026-05-21 → 2026-05-25)

| 维度 | 内容 |
|---|---|
| 日历天 | 5 days |
| 活跃天 | ~5 |
| 关键 commit | M3-Eval rewrite;M4 four-tier consolidation;M5 judge calibration |
| 坎点 | framed as crisis vs normal event;eval framework 实际搭了两次 |
| Δ-17 对应 | S4;但 framing 错 |

### ⑦ Autoloop M-Auto-1 ~ M-Auto-5(2026-05-26 → 2026-06-05)

| 维度 | 内容 |
|---|---|
| 日历天 | 11 days |
| 活跃天 | ~11 |
| 关键 commit | M-Auto-1/2/3 autoloop infra;M-Auto-4 暂停(5/31 首夜 discard);M-Auto-5 close 6/05 |
| 坎点 | 5/31 首夜 40+ 轮全 tier 0 discard 误判 runtime bug(P3);6/01-6/05 trace-dive 揭示 simulator role-inversion / vacuous-pass / stall-not-gated 三 eval framework bugs;~5d 误诊 |
| Δ-17 对应 | S6;**S5 被跳过** → P3 显形 |

## 阶段总结

| Δ-17 推荐 stage | csagent 实际 | 跳过的代价 |
|---|---|---|
| S0 | ①② done | — |
| S1 | ③ done | — |
| **S1.5** | **SKIPPED** | P2 — eval framework 搭两次,~5d |
| S2 | ④ done | — |
| **S2.5** | **SKIPPED** | P3 — autoloop 首夜误诊 runtime,~5d |
| S3 | ⑤ done(含 P1 影响,~2 周 iteration forensic only) | P1 显形 |
| **S3.5** | unplanned pivot 5/17 | P4 — 心理成本 + M1 部分重做 |
| S4 | ⑥ done(framed crisis) | — |
| **S5** | **SKIPPED** | P3 显形;10d unplanned 修 eval framework |
| S6 | ⑦ M-Auto-5 close | — |

## 关键 grep 测试(可在 csagent repo 验证)

```bash
# 5/05 单日 commit 数(③→④ 转折期 churn)
git log --since="2026-05-05" --until="2026-05-06" --oneline | wc -l   # → 19

# 5/17 mid-milestone pivot commit
git log --since="2026-05-17" --until="2026-05-18" --grep="Skill Registry" --oneline

# 5/31 autoloop 首夜
git log --since="2026-05-31" --until="2026-06-01" --grep="auto" --oneline

# 6/01-6/05 eval framework bug fix
git log --since="2026-06-01" --until="2026-06-05" --grep="simulator\|vacuous\|stall" --oneline
```

## Δ-17 P1-P4 在本时间线的具体锚点

| Pattern | 显形时间 | csagent 实例 |
|---|---|---|
| **P1** Spec-first / Data-late | 4/22 → 5/20 | spec 4/22 ready;data 5/20 落地;~4 周 gap |
| **P2** Eval-before-architecture-stable | 4/23 → 5/17 → 5/21 | eval v1 4/23;M2 pivot 5/17;eval rewrite 5/21 |
| **P3** Autoloop 暴露测量 bug 误判 runtime | 5/31 → 6/05 | autoloop discard 5/31;trace-dive 6/01-6/05 |
| **P4** Mid-milestone 架构 pivot | 5/17 | M2 mid-flight from "Skill foundation" to "Skill Registry" |

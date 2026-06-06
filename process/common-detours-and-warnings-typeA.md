---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.11 Δ-17
---

# Common Detours and Warnings — Type A(Δ-17)

**Tier**: T0(仅 Type A AI Agent 适用)
**加载时机**: S0 启动后、S1 进入前;每次升档前回看
**主导**: Tech Lead 引用;Customer 复核
**性质**: "踩过坑的过来人在旁边提醒",**不是** detour-skipper

## (a) Mission disclaimer + scope

**定位**:框架不承诺"跳过所有弯路"。每一类弯路的第一次走过都是认知升级的必经过程,因为弯路本身教你识别下一次同类弯路的预警信号。

**框架的价值**:
1. **给弯路命名**
2. **给你定位**(你现在在哪个 P 里)
3. **给你退出方向**(不是回头路,而是更近的出口)

下一个 agent 的创造者带着 Δ-17 第二次走的时候,**识别 P1 的窗口期会从 4 周缩到 1 周**。

**范围**:仅 Type A AI Agent。Δ-17-B(Type B detours)/ Δ-17-C(Type C detours)为独立 parallel docs。

## (b) csagent 54-day timeline 抽取的 4 类结构性弯路

### P1 — Spec-first / Data-late 鬼影评测期

| 维度 | 内容 |
|---|---|
| **症状预警(可观察)** | spec 完整(UC / FAQ / tool spec / scripts ready 4/22);真实 entity data 远晚落地(5/20,4 周 gap);eval framework 在 gap 期搭建产生**不可信信号** |
| **实际代价(csagent)** | ~2 周 eval-driven iteration 跑在错误 baseline 上;Sprint 1-16 部分失效 |
| **触发避免方式** | Δ-16 prereq #4(知识语料)gate 判据包含"真实数据在 repo,不只是 spec";**必须 READY** 才进 S2 |
| **在弯路里时怎么退出** | 暂停 eval-driven iteration;补全 data load;re-baseline;前 1-2 周 iteration 视作 forensic only |
| **对应新增 stage** | 触发 Δ-16 与 Δ-11 的 S2 进入判据 |

**可观察 grep 测试**:KB JSON / mock business exports 不在 repo;eval 信号与 manual review 出现持续 divergence。

### P2 — Eval-before-architecture-stable 双修期

| 维度 | 内容 |
|---|---|
| **症状预警** | eval v1(4/23-5/03)搭在 Agent 1.0 monolithic prompt 架构上;5/17 架构 pivot 到 Skill Registry;eval framework 5/21-5/25 (M3-Eval / M4 / M5) 再升级;L3 judge 哲学从"path checking" → "outcome-oriented" 重写 |
| **实际代价(csagent)** | eval framework 搭了两次;~5d re-architect |
| **触发避免方式** | **新增 S1.5 "架构压测期" 5-10d**(manual review + observability/trace coverage 检查 + 架构再评估);在搭 eval framework 之前;若 pivot 需要 → 现在 pivot |
| **在弯路里时怎么退出** | 即使 S2 中途,architecture pivot 在 flight 中 → demote eval 回 S1.5 |
| **对应新增 stage** | **S1.5** |

**可观察 grep 测试**:5/05 单日 19 commits(Sprint 2-6 rolling);mid-milestone pivot 提议在 backlog;broad runtime restructure 提议。

### P3 — Autoloop 暴露测量 bug 误判为 runtime bug

| 维度 | 内容 |
|---|---|
| **症状预警** | 5/31 首个 overnight autoloop 40+ 轮全部 tier 0 discard;首次解读"runtime 有 bug";实际 6/01-6/05 trace-dive 揭示 eval framework bugs(simulator role-inversion / vacuous-pass / stall-not-gated) |
| **实际代价(csagent)** | ~5d 误把 failure 归因 runtime;M-Auto-4 暂停 |
| **触发避免方式** | **新增 S2.5 "评测有效性验证期" 3-5d**("intentional break → eval must catch" 验证 ≥3 examples 进 S3);**新增 S5 10-day buffer** 把 autoloop 作 eval-stress-test(planned 不是 crisis) |
| **在弯路里时怎么退出** | 暂停 autoloop;trace-dive 手工;隔离 eval bugs vs runtime bugs |
| **对应新增 stage** | **S2.5 + S5** |

**可观察 grep 测试**:autoloop discard rate >80% 在 tier 0 首批;manual eyeball of "discarded" candidates 与 eval verdict 持续不一致。

### P4 — Mid-milestone 架构 pivot 实质是 S1 收敛过早信号

| 维度 | 内容 |
|---|---|
| **症状预警** | 5/17 M2 mid-flight pivot 从 "Skill foundation" 到 "Skill Registry abstraction";pivot 本身正确(问题被识别) |
| **实际代价(csagent)** | M1 Sprint 1-16 部分被 M2 refactor 吸收/废弃;心理成本 |
| **触发避免方式** | **新增 S3.5 "架构 pivot buffer"** — 早期 Type A 预算 1-2 次 pivot;不 frame 为 failure |
| **在弯路里时怎么退出** | 在 sub-sprint 边界宣告 pivot(不在 sprint 中段);作为 Δ-3 decision revision 浮出 |
| **对应新增 stage** | **S3.5** |

**可观察 grep 测试**:milestone 进行 1-2 sprint 后强烈感觉"we need a different abstraction"。

## (c) Actual vs Recommended timeline 对照

| Stage(recommended) | csagent actual | csagent 跳过 / 折叠 |
|---|---|---|
| S0 design | ①② | ✓ same |
| S1 first runnable | ③ | ✓ same |
| **S1.5 arch stress-test** | **SKIPPED** → ④ direct | P2 根因 |
| S2 eval basic(Tier-0/1 only) | ④ eval v1 全 L1/L2/L3 一次性 | L3 哲学锁太早 → P2 |
| **S2.5 eval validity check** | **SKIPPED** | P3 根因 |
| S3 eval-driven runtime iter | ⑤ Sprint 1-35 / 5/04-5/18 | data 5/20 落地 → P1 |
| **S3.5 arch pivot buffer** | M2 pivot 5/17 unplanned | P4 |
| S4 eval framework upgrade | ⑥ M3-M5 5/21-5/25 | done but framed as crisis vs normal event |
| **S5 autoloop pre-flight measurement stress-test** | **SKIPPED** → ⑦ autoloop | P3 |
| S6 autoloop trustable signal | M-Auto-5 close 6/05 | 10d unplanned actually spent fixing eval |

## (d) 3 个新增中间 stage 完整规格

### S1.5 架构压测期(5-10d)

| 字段 | 内容 |
|---|---|
| **Entry condition** | S1 first runnable demo 能 end-to-end 完成 ≥5 manual case scenarios |
| **Activity** | manual case 10-15 scenarios + observability/trace coverage check + 架构再评估 |
| **Exit gate** | 无架构 pivot 提议 pending;trace coverage ≥80% per turn |
| **此 gate 阻断的 anti-pattern** | 在 S1.5 之前搭 eval framework(P2) |

### S2.5 评测有效性验证期(3-5d)

| 字段 | 内容 |
|---|---|
| **Entry condition** | Tier-0 + Tier-1 eval 能 end-to-end 跑在 ≥10 CaseSpecs 上 |
| **Activity** | "intentional break → eval must catch" 验证 ≥3 distinct break types(semantic break / tool-call break / projection break);manual review × eval verdict cross-check on 10+ cases |
| **Exit gate** | ≥3 intentional breaks 被捕获;manual×eval 一致率 >90% |
| **此 gate 阻断的 anti-pattern** | 在 S2.5 之前开 autoloop(P3) |

### S5 Autoloop 前置: 测量 stress-test(10d 预算)

| 字段 | 内容 |
|---|---|
| **Entry condition** | S4 eval framework upgrade 完成;data 完整;Δ-9 anti-gaming forbidden list 已落地 |
| **Activity** | autoloop 首夜 **被视作 eval-framework stress test**;预期 5-10d 修测量框架(NOT runtime);planned for it |
| **Exit gate** | 第 2 个连续 overnight autoloop run 产生 ≥1 candidate 同时通过 autoloop 与 manual review |
| **此 gate 阻断的 anti-pattern** | 把首夜 discard 视作 runtime issue(P3) |

## (e) Pattern 通用结构

每条 P 都包含 5 字段:症状预警(可观察) / 实际代价(csagent) / 触发避免方式 / 在弯路里时怎么退出 / 对应新增 stage。P5-Pn 由后续 Type A 实例 append-extend。

## (f) Cognitive-detour disclaimer(MUST 写入)

> 本框架无法替你跳过弯路 — 每一类弯路的第一次走过都是认知升级的必经过程,因为弯路本身教你识别下一次同类弯路的预警信号。框架的价值不是 detour-skipper,而是 **(1) 给弯路命名**;**(2) 给你定位**(你现在在哪个 P 里);**(3) 给你退出方向**(不是回头路,而是更近的出口)。下一个 agent 的创造者带着 Δ-17 第二次走的时候,识别 P1 的窗口期会从 4 周缩到 1 周。

## (g) §L Worked Example cross-reference

csagent 54-day timeline 是 Δ-17 的 **the** worked example。完整 date-stamped 阶段 ①-⑦ + commit counts + activity-day counts 进入 `examples/csagent-reference/timeline-54-day.md`,从本文档引用,**不**内嵌于 Δ-17。

## (h) Open questions for first-trial

- S1.5 / S2.5 / S5 预算天数为估计值;首例 Type A 用 Δ-17 时应微调
- P5-Pn(更多 pattern)将随更多 Type A agent 被构建涌现;Δ-17 是 append-extensible
- Δ-17-B / Δ-17-C placeholders 空启动;待 hermes / fortunes 各自首例 lifecycle 完成后填充

---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §3 Δ-14
---

# Profile-Aware Maturity(Δ-14)

**Tier**: T0(三轨道通用,profile 分支)
**加载时机**: P0 选型时 / 每次升档判定
**主导**: Tech Lead + Customer

## 9-cell maturity 表

按 Type A / Type B / Type C × 各 stage 给出适用度。

| Stage | Type A AI Agent | Type B Agentic Workflow | Type C Demo App |
|---|---|---|---|
| **S0 Discovery** | 必需(Δ-15 全套 + Δ-16 7 类前置 + industry-synthesis) | 必需(精简集:SOP/tech-constraints/external-APIs/UI) | 必需(轻量:1-page demo brief + off-the-shelf inventory) |
| **S1 First runnable + observability** | 必需 | 必需(SOP test pyramid 替代部分 obs) | 必需(LOCAL_ACCEPTANCE_CHECKLIST) |
| **S1.5 Architecture stress-test**(Δ-17 NEW) | 必需 5-10d | 必需 3-5d | 可跳过 |
| **S2 Basic eval(Tier-0/1)** | 必需 | 仅当 S2-required event 触发(生产门) | 不需要 |
| **S2.5 Eval validity check**(Δ-17 NEW) | 必需 3-5d | 触发 S2 后必需 | 不需要 |
| **S3 Eval-driven runtime iter** | 必需 | 仅 S2 触发后 | 不需要 |
| **S3.5 Architecture pivot buffer**(Δ-17 NEW) | 预算 1-2 次 pivot | 不预算 | 不需要 |
| **S4 Eval framework upgrade** | 必需(periodic fold-back) | 触发后 | 不需要 |
| **S5 Autoloop pre-flight measurement stress-test**(Δ-17 NEW) | 必需 10d 预算 | 不适用 | 不适用 |
| **S6 Autoloop trustable signal** | 可选 | 不适用 | 不适用 |

## S0 prerequisites 列(Δ-14 修订)

Δ-16 7 类前置 × profile 必需集详见 `agent-creation-prerequisites.md` §profile-aware。

**关键规则**:
- 凡 deferred 必生成 OBS(Δ-9 集成)
- **Type A 必需类目不接受 N/A**;若 deferred 需 Customer 显式签字
- Type B 可用 SOP 定义替代 BRD+PRD
- Type C 可极简化(1-page demo brief 替代 BRD+PRD)

## S2-required event(Type B 专用)

Type B 项目首次发生以下任一时,Δ-3 决策目录 "S2-required event 触发记录"槽位**锁定**;maturity 视角向 Type A 迁移:

1. **接入终端用户流量**(从 demo / internal 到 production)
2. **承担 SLA / 合规义务**(可量化的可用性 / 隐私 / 法规要求)
3. **引入 LLM 自主语义决策**(原 deterministic step 之上加 LLM 判断)
4. **PII / 安全底线进 §1.4 Runtime owns**(Runtime 接管隐私 / 安全护栏)

**触发即**:
- 补 M-Eval 全套(Tier-0 + Tier-1)
- 补 M-Trace 全套(observability FIRST,详 `m-trace.md`)
- 进 S1.5 → S2 → S2.5 序列
- Δ-3 记录 `triggered_on: <YYYY-MM-DD>`

## Profile 切换的不可逆性

- **Type A → Type B**:不允许(Type A 一旦确立,意味着 LLM-first 已嵌入架构,降级到 deterministic workflow 等于重做)
- **Type B → Type A**:**S2-required event 触发即默认发生**(operational rule)
- **Type C → Type A / Type B**:允许但意味着退出 demo 心态,补做 Δ-15 / Δ-16 全套
- **A / B / C 之间任意切换都需 Customer 显式签字**(Δ-3 Decision #1 hard reversibility)

## Anti-pattern

- Type B 项目接入用户流量但不触发 S2-required event — 等于把 production 跑在 demo 心态上
- Type C demo brief 写到 5KB+ — 违反 "demo 轻量"原则,应升档 Type A/B 走 Δ-15 全套
- Type A 跳过 S1.5 直接 S2 — Δ-17 P2 教训(csagent 5/17 mid-milestone pivot)

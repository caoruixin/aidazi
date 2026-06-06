---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.10 Δ-16
---

# Agent Creation Prerequisites(Δ-16)

**Tier**: T0(durable-connective;三轨道通用,profile-aware 必需集)
**Review cadence**: 每 5 个 agent 创建实例后回看
**加载时机**: S0 Discovery 启动前
**主导**: Tech Lead 核对;**生产方在(b)列**(Tech Lead 不生产 prereq)

## Why prerequisites

Δ-15 elicitation 的有效性**依赖事实输入已经在场**。若 BRD/PRD/技术栈/知识语料/话术/外部 API/UI 在 elicitation 启动时不存在,六必答只是"拍脑门胡搞"。

用户 CS Agent 1.0 经验为锚:**这些不是 agent 设计的产物,而是 agent 设计所消费的原料**。

## 7 类前置物(domain-agnostic)

| # | 类别 | 范围 | 提供方 | 就绪判据 |
|---|---|---|---|---|
| 1 | **BRD** | 业务问题 / 目标用户 / 商业边界 | 业务方 / PM | 含"必须有"清单,业务方签字 |
| 2 | **PRD** | 产品形态 / 用户旅程 / KPI | PM | 含 KPI 定义,PM 签字 |
| 3 | **技术约束** | 基础栈 / 平台限制 / infra / 合规 | 架构 / SRE | 硬 vs 软约束分列,硬约束有引用源 |
| 4 | **知识语料** | FAQ / 领域知识 / 政策手册 / 历史会话 | 业务 + 内容运营 | 可被检索路径(grep/vector/SQL)消费;有 schema |
| 5 | **固定话术** | 模板 / canned reply / 法务定稿 | 法务 + 业务 | 每条有触发条件 / 用途标注 |
| 6 | **外部系统清单** | API / MCP server / DB / 第三方 | 架构 + owner | 含 endpoint / auth / SLA / rate-limit;**对接联系人**已知 |
| 7 | **UI 定义** | 界面 / 输入方式 / 渲染约束 / 多端 | 设计 + 前端 | 至少有线框图;消息形态(纯文本/富文本/卡片)已定 |

## Profile-aware 必需集(与 Δ-14 交叉)

| Profile | 必需 | 可选 | 替代 |
|---|---|---|---|
| **A** | 1,2,3,4,5,6,7(全部) | — | UI 多端可分阶段;次端 deferred 允许 |
| **B** | 3 + 6 + 7(若面向人) + **SOP 定义**(替代 1+2) | 4,5 | BRD/PRD 由 SOP 流程图吸收;FAQ/话术大多数 workflow 不需要 |
| **C** | **1-page demo brief**(替代 1+2)+ **off-the-shelf skill inventory 指针**(替代 4+5) | 3,6,7 | 技术约束可极简;外部系统通常 mock |

## Gate 逻辑(三态)

- **READY**: 文档存在 + 满足判据;路径登记入 brief `prerequisites:` front-matter
- **DEFERRED**: 不存在 / 不满足,但允许暂缓;
  - 填 rationale + 预期补齐时间
  - **自动生成 OBS-id**(Δ-9),标签 `prereq-deferred`
  - 触发 brief 实质变更则触发 Δ-15 重签
- **NOT_APPLICABLE**: 仅 Type B/C 可选类目可用;**Type A 必需类目不接受 N/A**

## Brief front-matter schema

```yaml
prerequisites:
  brd:
    status: ready                  # ready | deferred | not_applicable
    path: "docs/business/brd.md"
    verified_on: 2026-06-06
  prd:
    status: deferred
    rationale: "KPI 定义未签字;等 PM 周三回审"
    obs_id: OBS-014
    expected_by: 2026-06-10
  tech_constraints:
    status: ready
    path: "docs/arch/constraints.md"
    verified_on: 2026-06-06
  knowledge_corpus:
    status: ready
    path: "data/faq/v1/"
    verified_on: 2026-06-06
  canned_responses:
    status: deferred
    rationale: "法务定稿中"
    obs_id: OBS-015
  external_systems:
    status: ready
    path: "docs/arch/external-apis.yaml"
    verified_on: 2026-06-06
  ui:
    status: ready
    path: "docs/design/wireframes.fig"
    verified_on: 2026-06-06
```

## Δ-9 OBS 集成

deferred 类目自动开 OBS,纳入 Δ-9 post-deployment-iteration 流:
- OBS 标签:`prereq-deferred`
- Tech Lead 在 L1 triage 时识别 prereq-deferred 类 OBS,判定是否阻塞当前 sub-sprint
- 多 deferred 类目应聚合为单条 "agent-prereqs-incomplete" parent OBS(PB2 PENDING — 待首例 Type A 决断细节)

## Anti-pattern

- **前置缺失硬跑 elicitation** → Part A 空中楼阁,反复重签,Δ-3 决策被推翻
- **"前置就绪"误归为 Tech Lead 工作** — Tech Lead 只**核对**,不**生产**;生产方在(b)列已列明
- **deferred 兜底全部缺失** — 必须显式 OBS;Type A 类目 1/2/3/6 任一 deferred 应触发"是否还应启动此 agent"反问
- **Type A 必需类目用 N/A 绕过** — 不接受;若真的不适用,先回 Δ-3 Decision #1 重审是否应 Type A

## Open items(PENDING)

- **PB3**:gate 判据 tier-aware — enterprise 正式签批 / startup 命名 owner+日期 / 实验仅存在;当前 Δ-16 未细分判据严格度
- **PB4**:Type C "1-page demo brief" 最低字段(目标用户 1 行 / 演示效果 1 行 / 不演示什么 1 行 / 现成 skill 清单指针)是否在 Δ-16 内嵌该最小骨架
- **Δ-14 ↔ Δ-16 必需集**:Type B "SOP 定义"替代"BRD+PRD"映射,首例 Type B 实例可能暴露不够

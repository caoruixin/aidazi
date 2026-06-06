---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.1
---

# Domain Discovery Process(Δ-2)

**Tier**: T0(三轨道通用)
**加载时机**: P0(S0 Domain Understanding)
**主导**: Research Agent 执行;Customer 提供答案;Tech Lead 复核

## 目的

在任何架构 / 工具 / eval 决策之前,先把"这个 agent 要解决谁的什么问题"问清楚。Δ-2 把这件事拆成三组正交问题(D1 / D2 / D3),并以 intermediate artifact 形式落地 — 答案进 `discovery/`,而不是塞入 live constitution。

## 三维度问题集

### D1 — 业务调研

- agent 介入之前,该业务怎么运转?谁在干?干多久?
- human owner 期望 agent 做什么 — 接管 / 辅助 / 兜底?
- agent vs human-only vs human-on-loop 的切分边界在哪?
- 业务方对"成功"的定义是什么(可量化 1 句)?

### D2 — 用户问题分类

- 真实样本 / 真实日志的问题聚类(不要从想象出发)
- 每类频次 / 长尾占比
- intent-switch + 复合 intent 占比(单 intent 会话 vs 多 intent 会话)
- 已知误解 / 易混淆类别

### D3 — 边界、集成与业务指标

- 既有系统(CRM / 工单 / KB / SSO)各自身份与对接面
- 硬边界(合规 / PII / 安全 / 法务)条目清单
- 业务侧 metric(CSAT / 解决率 / 转人工率 / 平均处理时长)
- agent 贡献的可分离信号(哪些指标可单独归因)

## 输出物

| 文件 | 内容 | doc_category |
|---|---|---|
| `discovery/business-map.md` | D1 答案 | intermediate |
| `discovery/user-problem-taxonomy.md` | D2 答案 + 样本引用 | intermediate |
| `discovery/boundary-and-metrics.md` | D3 答案 | intermediate |

**命名规则**(per Δ-4):intermediate 类必须带 source sprint ID(若处于 sprint 中)或 source date。

## 下游连接

- **D2 → §10 Type A runtime skeleton intent 集合**:intent classification gate 的初始 intent 列表直接来自 D2 聚类。
- **D3 → Δ-3 decision catalog**:tools / policy / eval 决策的硬约束输入。
- **D1 → Customer barrier-break event 列表**:Δ-9 OBS 触发的业务方门铃。

## Profile 适配

| Profile | D1 | D2 | D3 |
|---|---|---|---|
| Type A | 必需(完整) | 必需(完整) | 必需(完整) |
| Type B | 必需(精简,SOP 替代部分 D2) | 必需(SOP step ↔ intent 映射) | 必需 |
| Type C | 必需(轻量,1-page demo brief 可吸收) | 简化(off-the-shelf skill 候选)| 必需(硬边界仍要) |

## Anti-pattern

- 跳过 D1 直接做 D2 — 在不理解业务 owner 期望的前提下分类用户问题,结果是把"agent 不该接的"也分进 intent
- D2 从假设样本聚类 — 真实日志没准备好就先用人造样本,Δ-16 prereq #4 未就绪,等于在沙地上盖楼
- D3 硬边界漏列合规 — 后续 §1.4 Runtime owns 缺一条主项

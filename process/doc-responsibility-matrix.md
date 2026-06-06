---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.5 / Δ-10
---

# Doc Responsibility Matrix(Δ-10)

**Tier**: T0(三轨道通用)
**加载时机**: 任何新增 doc 之前 / size 超 target 时
**主导**: 所有 doc 作者(强制 matrix 入口)

## 问题背景

AGENTS.md / CLAUDE.md / iteration_governance / action_bank / handoff / doc_governance 之间互相重叠;全加载导致 context bloat;csagent 44.8KB → 20.4KB Layer-A 拆分是教训代价。Δ-10 引入 matrix,把"每份 doc 应该承担什么、不应该承担什么"显式签订。

## 8 字段 schema

每份新 doc 在 doc-responsibility-matrix.md 主表追加一行,字段如下:

| 字段 | 含义 | 示例 |
|---|---|---|
| **owner** | 单一负责 role(只能一个) | `Tech Lead` |
| **scope_in** | 本 doc 承担的内容范畴(白名单) | `R-item 与 OBS 的 open ledger` |
| **scope_out** | 显式不在本 doc 的内容(黑名单) | `历史 closed 项;归档去 action_bank_archive.md` |
| **load_discipline** | `always-load` / `on-demand` / `by-role` | `on-demand` |
| **overlap_policy** | 同主题在 ≥2 doc 时谁是 canonical | ``若与 X.md 冲突,本 doc canonical`` |
| **size_target** | KB 上限 | `20KB` |
| **split_trigger** | 超过 size_target 后的拆分判据(对 live_ledger 必填具体阈值;对 append_only_archive 填 `n/a — append only`) | `>800 行触发 sweep 到 archive` |
| **artifact_type**(Δ-12)| `live_ledger` / `intermediate` / `append_only_archive` / `reference_contract` | `live_ledger` |

## 强制规则

1. **写新 doc → 必填 matrix 入口;无入口不得 merge**
2. **超 size_target → split-trigger 审查自动触发**
3. **同主题双 doc → 必须 mark `defer_to` 一份为 canonical;另一份 stub 指过去**
4. **load_discipline 是契约不是描述** — 标 `always-load` 的 doc 必须可被所有 role 在冷启动时直接加载;标 `on-demand` 的 doc 不得被自动加载(否则 framework 治理失败)

## artifact_type 与 split_trigger 的耦合

| artifact_type | size_target 期望 | split_trigger 例子 |
|---|---|---|
| `live_ledger` | 中(action_bank ≤20KB) | `>800 行触发 sweep` 或 `count: close ≥10 项触发 archive 迁移` |
| `intermediate` | 小(discovery / brief ≤5KB) | 创建即冻;通常不 split |
| `append_only_archive` | 不限 | `n/a — append only`;按时间分卷可选 |
| `reference_contract` | 小-中(governance ≤20KB 每章) | 主题独立性触发 split(子主题 ≥3 段且独立成章) |

## 主表入口(项目实例化时填)

```markdown
| doc_path | owner | scope_in | scope_out | load_discipline | overlap_policy | size_target | split_trigger | artifact_type |
|---|---|---|---|---|---|---|---|---|
| process/post-deployment-iteration.md | Tech Lead | OBS/autoloop role-split;L1/L2 triage | sprint 排期;eval bar | on-demand | canonical for OBS-vs-R-item | 10KB | 子主题独立 | reference_contract |
| ... (按项目 doc 实例追加) |
```

## Anti-pattern

- 不填 matrix 入口 — 后人无法判断本 doc 在治理中的位置
- `scope_out` 留空 — 等于全 scope,与其他 doc 必重叠
- `load_discipline: always-load` 的 doc size 超 20KB — 违反 §1 Constitution always-load ≤20KB 原则
- 同主题两份 doc 都不 mark canonical — 冲突时无裁决

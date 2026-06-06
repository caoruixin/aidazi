---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.3
---

# Doc Lifecycle Rules — live vs intermediate(Δ-4)

**Tier**: T0(三轨道通用)
**加载时机**: P0 与 Δ-2 / Δ-12 同期
**主导**: 所有 doc 作者(强制 front-matter 规则)

## 根因表述

用户被烧过的具体路径:**生成的设计 doc → 喂给 coding agent → 生成 code → doc 不再被更新 → 半年后所有人按过期 doc 推理**。

根因**不是** "没 fold-back",根因是**没区分 intermediate 与 live**。一份在 sprint 中段被消费完就该冻的设计草稿,如果没标 intermediate,会被后人误以为是长期契约。

## 两类强制分类

每个新 doc front-matter 必填 `doc_category: live | intermediate`。

| 维度 | `live` | `intermediate` |
|---|---|---|
| **last_reviewed** | 必填,有 cadence | 不要求,创建即冻 |
| **source_of_truth** | code path / 另一份 live doc | 创建时的 sprint context |
| **修改许可** | 周期性 fold-back 允许 | 仅事实性 typo |
| **命名** | 不带 sprint ID | **必须**带 source sprint ID |
| **例子** | `iteration_governance.md` / `doc_governance.md` / `constitution.md` | `compact/sprint-NNN-dev-prompt.md` / `docs/sprints/*` / `discovery/*` |

## 命名约定

- **live**: `<topic>.md`(短稳定名)。例:`doc-lifecycle-rules.md`、`post-deployment-iteration.md`
- **intermediate**: `<topic>-<sprint-or-date>.md`。例:`industry-synthesis-S03.md`、`sop-survey-2026-06-06.md`、`failure-brief-cs_example_001.md`

## 与 Δ-12 artifact_type 的关系

Δ-4 的二分(live / intermediate)是**生命周期**视角;Δ-12 的 `artifact_type`(`live_ledger` / `intermediate` / `append_only_archive` / `reference_contract`)是**职能**视角。两者并不冲突:

| Δ-4 doc_category | Δ-12 artifact_type 候选 |
|---|---|
| `live` | `live_ledger` / `reference_contract` |
| `intermediate` | `intermediate` / `append_only_archive` |

## 反例(必须分类)

- 一份 spec doc 在 sprint 末被 code 完整实现 → 标 `intermediate`,放入 `docs/sprints/<sprint-id>/` 或 `proposals/` 归档,**不要**留在 live 根目录被后人误读
- 一份 governance 章节随 sprint 局部修订 → 修订**不是** intermediate;修订仍是 live 的事实性更新,但写入 `compact/sprint-NNN-dev-prompt.md` 的"指导某次行动"段是 intermediate
- discovery / research artifact 永远是 intermediate(无 cadence、无 source-of-truth code)

## Anti-pattern

- 不填 `doc_category` 直接提交 — 默认是 live,但 reviewer 应 reject
- intermediate 命名不带 sprint ID — 第二份同主题 intermediate 出现时无法定位"哪个版本"
- live doc 借 intermediate 通道做大改写 — 走 fold-back 周期,不要绕路

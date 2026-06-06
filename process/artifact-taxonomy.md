---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.7
---

# Artifact Taxonomy(Δ-12)

**Tier**: T0(三轨道通用)
**加载时机**: 所有 role cold-start
**主导**: 所有 doc 作者(强制遵守);Tech Lead 维护

## 11 artifact 总表

| artifact | 触发 | 生产者 | 消费者 | lifecycle | 留存 |
|---|---|---|---|---|---|
| `action_bank.md`(open) | dev/Tech-Lead 发现 R-item / OBS | dev / Tech Lead | Tech Lead(规划) / dev(领取) | live ledger | 仅 open 项;关闭即外迁 |
| `action_bank_archive.md` | open 项关闭 | Tech Lead(关闭时) | human(审计) / Tech Lead(查重) | append-only | 永久 §A/§B/§C 分节 |
| `proposals/*.md` | 研究 / Tech Lead 前瞻设计 | research / Tech Lead | Tech Lead(在 sprint 引) / human | intermediate(待裁决) | `status: proposal/partial/deferred/superseded` 不删 |
| `diagnostics/*.md` / `failure-briefs/` | 审计 / bad-case 根因 / trace 投影 | dev / research | Tech Lead(转 R-item) / human | intermediate | 转化后留存 |
| `sprint_objective.md` | 本 sub-sprint 契约 | Tech Lead | dev(执行) / reviewer(对账) | live(当前 sub-sprint) | 关闭后归档 `docs/sprints/` |
| `milestone_objective.md` | 当前 milestone 北极星 | Tech Lead | Tech Lead(规划) / human | live(当前 milestone) | 关闭后归档 `docs/milestones/` |
| `handoff.md §0` cold-start | 每个 sub-sprint/milestone 关闭 | Tech Lead | 所有 agent 冷启动 | live(永远当前) | 整段替换 |
| `handoff.md §1` narrative | 当前 milestone + 上一关闭 | Tech Lead | 需上下文叙事的 agent | live(retention window) | 保留窗口 = 当前 + 上一关闭 |
| `handoff.md §2` archive index | milestone 关闭 | Tech Lead | human / 任何回溯 | append-only index | 永久 |
| `codex-findings.md` | reviewer 出具裁决 | Code Reviewer | Tech Lead(收口) / human | intermediate | 收口后归档 |
| `research-solutions/*.md` | research 完成调查 | research | Tech Lead(转 sprint) | intermediate(待消费) | 消费后归档 |

## 每 role 必读 / 按需 / 禁读 artifact 清单

| role | 必读 | 按需 | **禁读** |
|---|---|---|---|
| **dev** | `sprint_objective` / `handoff §0` / `action_bank`(领取范围) | `diagnostics`(R-item 来源)/ `proposals`(sprint 引) | `codex-findings`(关闭前不看)/ `milestone_objective` |
| **Tech Lead** | `sprint_objective` / `milestone_objective` / `action_bank` / `handoff §0+§1` / `codex-findings`(收口时) | `proposals`(选材)/ `diagnostics`(转 R-item)/ `research-solutions` | `action_bank_archive`(仅审计) |
| **Code Reviewer** | `sprint_objective` / 本次 PR 相关 `diagnostics`(若 sprint 引) | `handoff §0`(冷启动) | `action_bank` / `milestone_objective` / `research-solutions` |
| **research** | `proposals` 相邻 / `diagnostics/failure-briefs`(若相关) | `action_bank`(看 OBS 已在动) | `sprint_objective` / `codex-findings` |
| **Acceptance** | `acceptance-criteria` / 本 release 范围 `diagnostics` / 上一 acceptance-checklist | `handoff §0` / `milestone_objective` | `action_bank`(运行期不看) |

## action_bank open / archive 拆分规则

3 触发(任一)即执行 sweep:

- **size 触发**: > 800 行强制扫荡
- **count 触发**: 累计 close ≥ 10 条未迁移强制
- **cadence 触发**: 每 milestone 关闭必扫

**Sweep 流程**:
1. 关闭即迁移;原 anchor 留 1 行 stub `#R-XX → archive §A.YYYY-MM`
2. 提交信息: `action_bank archive sweep — N items moved (size=X→Y lines)`
3. 同步检查反向引用并修补(避免漂移,如 csagent 2026-06-01 教训)

## Human cold-start cheatsheet(1 页)

| 想看 / 决定 | 去看 | 何时 |
|---|---|---|
| 现在 agent 在干啥 | `sprint_objective.md` | 任何时候 |
| 这个 milestone 想达到啥 | `milestone_objective.md` | milestone 启动 / 收口 |
| 上次会话留了什么状态 | `handoff.md §0` 表 | 每次回到项目 |
| 最近一个 milestone 叙事 | `handoff.md §1` | 想理解最近背景 |
| 历史 milestone 怎么找 | `handoff.md §2` archive index | 回溯老 milestone |
| 现在 backlog | `action_bank.md` | 决定下一 sub-sprint |
| 历史上干过啥 / 为啥 | `action_bank_archive.md` | 审计 / 查重 / 追溯 |
| 前瞻设计 | `proposals/` | 规划下一 milestone |
| 审计 / 根因 | `diagnostics/` / `failure-briefs/` | 出 bad-case 时 |
| Codex 裁决 | `codex-findings.md` | sprint/milestone 收口 |
| Research 方案 | `research-solutions/` | Tech Lead 选材 |

## Anti-pattern

- 不分 open 与 archive — action_bank 持续膨胀,新人无法快速 grep 当前 backlog
- 关闭项原位留长描述 — 应替换为 1 行 stub + archive 链接
- role 越权读 — 例如 dev 关闭前看 `codex-findings`,会自我修正绕过 review gate

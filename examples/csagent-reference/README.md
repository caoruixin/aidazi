---
doc_category: intermediate
artifact_type: intermediate
last_reviewed: 2026-06-06
source: v3.2 §12 §L worked example + Δ-7
snapshot_date: 2026-06-06
source_commit: csagent-HEAD@2026-06-06
---

# csagent reference snapshot

**性质**:csagent 在 2026-06-06 这一刻的 framework template **填空快照**。

**Read-only after first instantiation**:首次落地后冻结;csagent 后续演化**不**回流到本快照。学到的新洞见 → fold-back 到 `templates/`(live),**不**回流到本目录。

**两个等价 framing 都成立**(per Δ-7):
1. **"aidazi 是基于 csagent 抽取的框架"** → 读 `templates/` 时引用本目录看"填空后长什么样"
2. **"用 aidazi 框架审视 csagent"** → 读本目录检查 csagent 真实做法是否对得上 templates 推荐

## 目录结构

```
examples/csagent-reference/
├── README.md                 — 本文件
├── timeline-54-day.md        — Δ-17 (g) 的 the worked example;7 阶段时间线
├── discovery/                — Δ-2 三维度 discovery 的 csagent 答案(D1/D2/D3)
├── decisions/                — Δ-3 8 项决策的 csagent 实际选择
├── runtime-skeleton/         — Δ-6 骨架在 csagent 的填法
│   └── phases/{propose,triage,resolve,confirm,escalate,close}.md
├── m-eval/                   — M-Evaluation 4-tier 在 csagent 的实例
└── m-trace/                  — M-Trace trace schema 在 csagent 的实例
```

## Snapshot 重建机制

显著过期(用户判断)→ 开 sub-sprint **整体重建新 snapshot**(`examples/csagent-reference-2027-Q1/`),旧目录保留(Δ-4 intermediate 规则)。

## 与 v2 §E 关系

v2 §E 说 donor → aidazi → new project 单向。本 §L worked example 把 donor 在 aidazi 中的镜像具体定下来;反向迁移仍禁止(`aidazi → csagent` 不发生)。

---
doc_category: intermediate
artifact_type: intermediate
last_reviewed: 2026-06-06
source: v3.2 §12 §L
---

# csagent decisions snapshot

此目录承载 csagent **Δ-3 8 项决策**的实际选择 + rationale。

## TODO

- [ ] Decision #1 应用类型 → **Type A**(AI Agent);S2-required event 不适用
- [ ] Decision #2 抽象层次 → **single-agent**
- [ ] Decision #3 上下文投影模型 → **projection-by-skill**(M2 后)
- [ ] Decision #4 状态管理 → **session + cross-session ledger**
- [ ] Decision #5 记忆 → **短期 + RAG-as-memory(FAQ retrieval)**
- [ ] Decision #6 工具定义 → **yaml schema(tool-policy.yaml)**
- [ ] Decision #7 Policy → **混合(prompt-level + runtime-gate)**
- [ ] Decision #8 评估 → **yes,4-tier 全量**

填空 schema 参考 `process/tech-architecture-decision-catalog.md`:`decision-catalog.yaml` + `decision-rationale.md`。

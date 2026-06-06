---
doc_category: intermediate
artifact_type: intermediate
last_reviewed: 2026-06-06
source: v3.2 §12 §L
---

# csagent M-Eval snapshot

此目录承载 **M-Evaluation 4-tier 在 csagent 的具体实例**(per `modules/m-evaluation.md`)。

## csagent 4-tier 实例

| Tier | csagent 内容 |
|---|---|
| **Tier-0 safety floor** | PII redaction / identity-verification gate / handover-required cases |
| **Tier-1 outcome basic** | Grounding(FAQ verbatim citation)/ tool dispatch correctness / projection coherence |
| **Tier-2 critical-flow behavioral** | UC routing(intent classification)/ next-action selection / escalation posture |
| **Tier-3 advisory outcome** | Composite contained-problem solved / customer satisfaction proxy / lifecycle 完成度 |

## csagent 6 skills 列表(per Δ-15 Part B Type A)

(待填空,基于 csagent skill registry)

- skill 1 → FAQ resolve
- skill 2 → entity-information retrieval
- skill 3 → intake form completion
- skill 4 → confirm + escalate routing
- skill 5 → identity-verification skill
- skill 6 → handover preparation

## TODO

- [ ] CaseSpec schema 实例 + corpus 规模(~500 case)
- [ ] Judge contract 4 类(deterministic / rubric / LLM-judge / human-pass)
- [ ] Suite manifest tier 比例
- [ ] Score aggregator regression profile 字段

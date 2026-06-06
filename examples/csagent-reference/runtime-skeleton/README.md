---
doc_category: intermediate
artifact_type: intermediate
last_reviewed: 2026-06-06
source: v3.2 §12 §L
---

# csagent runtime-skeleton snapshot

此目录承载 **Δ-6 Type A runtime architecture skeleton 在 csagent 的具体填法**。

## csagent 6 phase pipeline

csagent 选择了 6-phase 序列(详 `process/typeA-runtime-architecture-skeleton.md`):

```
propose → triage → resolve → confirm → escalate → close
```

每 phase 单独一份填空 doc 进 `phases/`:

## TODO — phases/

- [ ] `phases/propose.md` — initial intent classification + propose response strategy
- [ ] `phases/triage.md` — disambiguation / clarification gate
- [ ] `phases/resolve.md` — tool dispatch + KB retrieval + answer composition
- [ ] `phases/confirm.md` — user satisfaction check + close hint
- [ ] `phases/escalate.md` — handover orchestrator hook
- [ ] `phases/close.md` — session wrap-up + summary persist

每 phase doc 必填:
- `phase.name`
- `inputs`(projected_context / state_handle 来源)
- `steps`(model_interaction + tool_execution 序列)
- `exit_condition`(to_next_phase / to_intent_switch / to_escalate)
- csagent-specific tools / policies(T3 fill)

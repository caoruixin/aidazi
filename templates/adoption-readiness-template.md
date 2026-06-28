---
title: Adoption readiness snapshot — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
load_discipline: on-demand
size_target: 4KB
notes: >
  Written at ONBOARDING Step 8 by adoption_status.py --write-readiness. Human-readable
  snapshot of configured vs missing items. Re-run the CLI anytime to refresh.
---

# Adoption readiness snapshot — `<adopter-name>`

> **Generated artifact.** Prefer regenerating over hand-editing:
>
> ```bash
> python engine-kit/validators/adoption_status.py . \
>   --write-readiness docs/current/adoption-readiness.md
> ```

Root: `<absolute-path-to-adopter-repo>`

```text
(paste adoption_status.py output here at Step 8)
```

## What this snapshot means

- **`[✓]` REQUIRED** — onboarding item present and passing.
- **`[ ]` REQUIRED** — missing; onboarding not complete until fixed.
- **`[~]` / `[✗]`** — partial or failed; see detail column.
- **OPTIONAL** — explicit OFF (e.g. Loop Memory) is fine.
- **RUNTIME** — informational paths for live loops; not part of Step 8 gate.

Configuration map (what *can* be configured): `docs/current/adoption-config.md`.

Next after a green REQUIRED section: `aidazi/FIRST-LOOP.md` in a fresh session with
**cwd = this repo root**.

---

End of adoption readiness snapshot template.

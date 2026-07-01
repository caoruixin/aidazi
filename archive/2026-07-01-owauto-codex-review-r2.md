**Verdict: REVISE**

**BLOCKING — `pending` sentinel carve-out is still under-propagated.**  
Rev2’s rule is tight in the design itself: agents may seed only a **new** requirement at `customer_disposition: pending`, and may never write/change decided values ([design](</Users/caoruixin/projects/aidazi/archive/2026-07-01-acceptance-auto-proposal-and-init-experience-design.md:109>)). But the propagation list omits live contradictory surfaces that an implementation could leave behind:

- [schemas/requirement-ledger.schema.json](</Users/caoruixin/projects/aidazi/schemas/requirement-ledger.schema.json:5>) still says the ledger records “ONLY Customer-authored disposition”.
- [process/requirement-ledger.md](</Users/caoruixin/projects/aidazi/process/requirement-ledger.md:47>) still says `customer_disposition` is “Customer ONLY” and “NEVER written by any engine/agent”.
- [ONBOARDING.md](</Users/caoruixin/projects/aidazi/ONBOARDING.md:380>) Step 4b still says agents “never set it” and there is “no engine/agent write path”.
- [process/artifact-taxonomy.md](</Users/caoruixin/projects/aidazi/process/artifact-taxonomy.md:218>) still assigns `customer_disposition` to Customer authority only, without the pending-seed exception.

Concrete fix: expand §4.1/§7 so every one of those texts says the same rule: agents/engines may seed `pending` only when creating a new requirement; all transitions out of `pending` and all decided values remain Customer-only. Include the process table row and onboarding Step 4b explicitly.

R1 status: B1 is resolved in design; the sidecar projection keeps `surface` and existing fields while stripping advisory fields before resolver hashing. B3 is resolved: Step 4b is at `ONBOARDING.md:358`, Step 6 at `:535`. The “no new gate type / default-active existing gate” wording is resolved. The inventory is materially improved, but the B2 propagation gap above still blocks approval.

No tests or builds run, per instruction.
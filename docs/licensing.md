---
title: Licensing — aidazi under Apache 2.0
doc_tier: docs
doc_category: live
status: current
source_of_truth: LICENSE (canonical legal text); this file explains intent
last_reviewed: 2026-07-02
---

# Licensing (Apache License 2.0)

aidazi is licensed under the **Apache License, Version 2.0**. The canonical legal text is in
[`LICENSE`](../LICENSE); the attribution notice is in [`NOTICE`](../NOTICE). This page explains
what that means in practice for the way aidazi is meant to be used — **vendored into your own
repository** — and is informational only (the `LICENSE` text governs).

## Why Apache 2.0

- **Adopt-by-vendoring is the intended use.** aidazi is not a server or a package you depend on
  at runtime — you copy the framework tree into your repo (`aidazi/`) and specialize in your own
  `docs/current/`. Apache 2.0 explicitly permits use, modification, and redistribution of a
  copied Work, which is exactly this workflow.
- **Explicit patent grant.** Unlike MIT, Apache 2.0 includes an express, irrevocable patent
  license from contributors (§3) with a defensive-termination clause — clearer protection for
  organizations adopting the framework into production.
- **Attribution via NOTICE.** Apache 2.0 formalizes attribution through the `NOTICE` file (§4d),
  which fits a framework distributed by copy.

> Note: aidazi's license changed from MIT to Apache 2.0 in the `v5` line. Both are permissive;
> Apache 2.0 adds the patent grant and the NOTICE/attribution mechanics.

## What you must do when you vendor aidazi

Per Apache 2.0 §4 (Redistribution):

1. **Keep `LICENSE` and `NOTICE`** with the vendored framework tree.
2. **Mark changed framework files** — if you modify a framework file in place (rather than
   overriding it from `docs/current/`), add a prominent notice that you changed it (§4b). In
   practice, prefer the framework's own discipline: adopters specialize in `docs/current/` and
   record divergences in `docs/current/adoption-state.md` rather than editing framework files.
3. **Retain existing notices** — keep the copyright / attribution notices already present in the
   Source you redistribute (§4c).

## What stays yours

Your adopter-side work — your product code, your `charter.yaml`, your `docs/current/*` domain
contracts, your requirement ledger, your eval sets — is **your** authorship. You may license it
however you like; adopting aidazi does not place your product under Apache 2.0. aidazi's license
covers the framework files you copied, not the product you build with them.

## Third-party components

Vendored role skills under `skills/vendored/<id>/` each carry their **own upstream `LICENSE` +
provenance** (per the skill-vendoring model). Those licenses govern those subtrees; preserve them
as shipped.

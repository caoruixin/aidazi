# Phase-0 decision memo — does the Codebase Map help? (measured, de-leaked)

**TL;DR.** On **12 complete A/B pairs** (de-leaked rerun — see §0), the map-guided arm **roughly
halved file content read into context (read-volume median −53%, every category negative)** and
**localized to the correct file faster (median −2 steps)** with **no quality loss** (rubric 143/144;
Arm A 5.92 vs Arm B 6.00; zero real fabrications). BUT it did **not** reliably reduce the token *bill*
(fresh-input median −8%, mean −8%, one category +23%). Verdict vs the pre-registered ≥20% bar: **PASS
on read-volume, FAIL on token-billing.** Recommendation: a thin read-only auto-entry is **justified
for the originally-stated goal** (less re-scanning + faster orientation), but must **not** be sold as
a token-bill reducer. Single-rep + proxy-harness — directional, not final.

## 0. Validity correction (Codex review R1 BLOCK → fixed)
The first Codex xhigh review BLOCKED on a real flaw: although the Arm-B briefing is ground-truth-blind,
the map's `responsibility` PROSE embedded some scalar answers (e.g. `AIDAZI_ALLOW_REAL_ADAPTER=1`,
"9 MANDATORY_CHECKPOINTS"), pre-supplying answers to fact-lookup tasks. **Fix:** the briefing now
carries **structural pointers only (title + anchors + tests + docs, no prose)**, and **all 12 Arm-B
runs were redone** with it (Arm-A unaffected). All numbers below are from the de-leaked rerun.
Post-fix proof: t6a-B/t6b-B still answered correctly (`AIDAZI_ALLOW_REAL_ADAPTER`, "9") although those
strings no longer appear in their briefings — i.e. correctness was earned by opening the anchored
files, not by leakage. The headline (read-volume win, token-billing null) **survived the de-leak**.

## 1. What ran
- Measured agent: `codex exec --json -s read-only`, model `gpt-5.5`, effort `medium`, fresh
  independent session per arm, same checkpoint (`8e3b20f`) / tools, A/B order alternated (see
  `design.md`). 12 tasks × 2 arms = 24 runs, all succeeded (3 were re-run after a Codex usage-limit
  reset; 12 Arm-B re-run after the de-leak). 12 complete pairs, all 6 categories n=2.
- Quality scored vs the frozen `tasks.json` ground truth; per-run 6-dim rubric in `rubric.md`.
- This memo + data passed a second Codex xhigh read-only review (see commit message / `.runs/`).

## 2. A/B summary (Arm B = map-guided vs Arm A = cold start; negative = map cheaper/faster)

| metric | mean | median | reading |
|---|---|---|---|
| **read volume** (cmd-output bytes) | **−43%** | **−53%** | strong, consistent reduction — the headline win |
| localization step (to correct file) | −1.4 | −2.0 | map reaches the right file ~2 steps sooner |
| tool calls | −1.1 | −1.5 | fewer |
| files read (distinct) | −0.8 | −0.5 | slightly fewer |
| **fresh input tokens** (input−cached) | **−8%** | **−8%** | does NOT clear ≥20%; one category +23% |

Raw `input_tokens` (API prompt tokens summed across turns) is intentionally NOT the headline: it is
dominated by turn-count × cached re-sends and is misleading. We lead with read-volume + fresh-input
(both pre-registered). See design.md amendments.

## 3. Per-category (fresh input %, read-volume %), n=2 each
| category | fresh in | read vol | note |
|---|---|---|---|
| 1 single-module localize | −10% | −58% | reads far less; tokens modestly better |
| 2 cross-module bug | −15% | −23% | map helps both axes |
| 3 feature-impact | −17% | −41% | best token result; reads much less |
| 4 unknown-entry | −1% | −52% | reads much less; tokens flat |
| 5 test-failure | **+23%** | −19% | reads less but spends MORE tokens reasoning — map doesn't help billing here |
| 6 tiny grep-friendly | −27% | −64% | map still helped (weaker than the leaked run; see §7) |

read-volume is negative in **every** category (−19% to −64%); fresh-input is mixed (cat5 positive),
confirming the split.

## 4. Briefing fixed cost
The de-leaked Arm-B briefing (top-3 sections: title + anchors + tests + docs + git delta) is **~524
tokens** (range 458–570, down from ~602 with prose). Already inside Arm B's measured input, so every
delta above is briefing-cost-inclusive.

## 5. Quality — no degradation (see `rubric.md`)
6-dimension rubric over all 24 runs: **143/144** (Arm A 5.92/6, Arm B 6.00/6). Every run named the
correct entry point with correct dependencies, the key invariant, and relevant tests; the single miss
is Arm-A on t3a (didn't cite the test) — which Arm-B caught. **Zero real fabrications** (3 runs / 7
path tokens flagged by the proxy, all false positives: abbreviated/runtime paths). Map-guided answers were as correct as cold-start,
marginally more complete.

## 6. Which task types the map helps
- **Feature-impact, unknown-entry, cross-module, single-module, tiny**: clear read-volume +
  faster-localization wins.
- **Test-failure (cat5)**: read-volume down but fresh-input UP (+23%) — the map pointed to the right
  area but the agent then spent more reasoning; net token-negative. The one category where the map
  does not help on either token axis.

## 7. Tiny grep-friendly tasks (hypothesis: briefing wasted; grep wins)
Even de-leaked, **both tiny tasks still favored the map** (cat6 fresh −27%, read-vol −64%), because
cold-start over-explores: t6a-A did 27 tool calls / 15 files on "which env var…"; map-guided did 14.
The effect is **weaker than the leaked run claimed** (was −43%/−77%), and is the map's *structural*
help (pointing at the file), not answer leakage. Still proxy-harness + single-rep — directional.

## 8. Map maintenance cost
~33 KB / 100 lines. Upkeep = after a structural change, re-verify anchors (a mechanical audit, ~5 min)
and bump `map_checkpoint`; staleness is *surfaced* by `git diff map_checkpoint..HEAD`, never enforced;
a stale map degrades gracefully (fall back to search). **Low** — well below per-session read savings.

## 9. Recommendation — proceed to a thin auto-entry? **Qualified yes.**
Against the pre-registered bar (≥20% stable reduction in **token OR read-volume**, no quality drop,
tiny tasks not penalized, upkeep ≪ savings):
- read-volume ≥20%: **PASS** (−53% median, every category negative, survives de-leak).
- token-billing ≥20%: **FAIL** (−8% median, one category +23%).
- quality non-regression: **PASS** (143/144). tiny-task penalty: **none**. upkeep: **low**.

**The bar is an OR and read-volume clears it**, so the data *supports* building the **minimal,
read-only, fail-open auto-entry** (the §3-Lite design) — its honest value is **less repeated scanning
and faster orientation, not a lower token bill.** If the only goal were token-bill reduction, the
evidence says *don't bother* (and cat5 would warn against it). Since the original concern was
re-scanning + re-understanding, the entry is cheap (~524 tok) + non-blocking, and the map is already a
useful standalone asset, proceeding is defensible — **scoped to the read/orientation benefit, no
token-savings promise.**

## 10. Limitations (do not over-read this)
- **Single rep per arm**: per-task numbers are high-variance; only cross-task aggregates interpreted.
  Per-category n=2.
- **Proxy harness**: `codex exec` at `medium` effort stands in for "a coding session"; absolute
  numbers are proxy, the A/B delta is the signal. A real high-effort Claude Code session may differ.
- **Token-billing nuance**: the map cuts *reading* but agents reinvest the freed budget into
  reasoning/verification (most starkly cat5), so the token *bill* barely moves — reported honestly.
- **Answer-leak history**: the first run leaked answers via map prose (Codex caught it); these numbers
  are the de-leaked rerun. Not cherry-picked: the token FAIL and the cat5 +23% are reported as-is.

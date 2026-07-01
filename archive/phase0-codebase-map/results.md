# Phase-0 results

runs found: 24 / 24

## Per-task robust metrics + A/B delta

| task | cat | arm | fresh_in | readVolKB | tools | files | srch | locStep | out_tok | entryQ | fab |
|---|---|---|---|---|---|---|---|---|---|---|---|
| t1a | 1-single-module-localize | A | 36953 | 380 | 12 | 5 | 5 | 3 | 1688 | 1 | 0 |
| t1a | 1-single-module-localize | B | 42615 | 232 | 18 | 4 | 3 | 1 | 2075 | 1 | 0 |
| t1b | 1-single-module-localize | A | 73140 | 605 | 16 | 7 | 2 | 4 | 2344 | 1 | 0 |
| t1b | 1-single-module-localize | B | 47250 | 145 | 13 | 5 | 0 | 2 | 1739 | 1 | 1 |
| t2a | 2-cross-module-bug | A | 98646 | 1047 | 22 | 8 | 6 | 4 | 3230 | 1 | 1 |
| t2a | 2-cross-module-bug | B | 89989 | 466 | 24 | 10 | 4 | 3 | 3411 | 1 | 0 |
| t2b | 2-cross-module-bug | A | 75204 | 192 | 22 | 12 | 3 | 2 | 3149 | 1 | 0 |
| t2b | 2-cross-module-bug | B | 59610 | 212 | 13 | 8 | 2 | 1 | 2381 | 1 | 0 |
| t3a | 3-feature-impact | A | 103515 | 733 | 31 | 23 | 7 | 3 | 4263 | 1 | 0 |
| t3a | 3-feature-impact | B | 103119 | 347 | 39 | 27 | 2 | 1 | 4839 | 1 | 0 |
| t3b | 3-feature-impact | A | 78718 | 520 | 15 | 11 | 4 | 1 | 2434 | 1 | 0 |
| t3b | 3-feature-impact | B | 52244 | 365 | 20 | 12 | 2 | 1 | 2833 | 1 | 0 |
| t4a | 4-unknown-entry-investigation | A | 65535 | 826 | 17 | 12 | 4 | 3 | 2506 | 1 | 0 |
| t4a | 4-unknown-entry-investigation | B | 54749 | 212 | 16 | 12 | 2 | 1 | 2479 | 1 | 0 |
| t4b | 4-unknown-entry-investigation | A | 65968 | 273 | 19 | 12 | 4 | 3 | 2463 | 1 | 0 |
| t4b | 4-unknown-entry-investigation | B | 75868 | 193 | 12 | 11 | 3 | 2 | 2026 | 1 | 5 |
| t5a | 5-test-failure-localize | A | 42543 | 164 | 12 | 8 | 2 | 3 | 2102 | 1 | 0 |
| t5a | 5-test-failure-localize | B | 43837 | 225 | 10 | 8 | 2 | 1 | 1680 | 1 | 0 |
| t5b | 5-test-failure-localize | A | 36275 | 409 | 10 | 6 | 3 | 1 | 2003 | 1 | 0 |
| t5b | 5-test-failure-localize | B | 51813 | 102 | 10 | 4 | 2 | 1 | 1705 | 1 | 0 |
| t6a | 6-tiny-grep-faster | A | 49983 | 387 | 27 | 15 | 5 | 3 | 3118 | 1 | 0 |
| t6a | 6-tiny-grep-faster | B | 46316 | 178 | 20 | 15 | 2 | 1 | 2323 | 1 | 0 |
| t6b | 6-tiny-grep-faster | A | 35626 | 237 | 14 | 10 | 3 | 3 | 1686 | 1 | 0 |
| t6b | 6-tiny-grep-faster | B | 19131 | 60 | 9 | 4 | 2 | 1 | 1268 | 1 | 0 |

## Aggregate A/B deltas (Arm B vs Arm A; negative = map cheaper)

- fresh input %:  mean -7.7 / median -8.1 (n=12)
- read volume %:  mean -42.7 / median -53.3 (n=12)
- tool calls Δ:   mean -1.1 / median -1.5 (n=12)
- files read Δ:    mean -0.8 / median -0.5 (n=12)
- localization step Δ: mean -1.4 / median -2.0 (n=12)

## Per-category (fresh%, readVol%) means

- 1-single-module-localize: fresh -10.0% | readVol -57.5% (n=2)
- 2-cross-module-bug: fresh -14.8% | readVol -22.6% (n=2)
- 3-feature-impact: fresh -17.0% | readVol -41.2% (n=2)
- 4-unknown-entry-investigation: fresh -0.7% | readVol -51.9% (n=2)
- 5-test-failure-localize: fresh +22.9% | readVol -18.9% (n=2)
- 6-tiny-grep-faster: fresh -26.8% | readVol -64.3% (n=2)

wrote /Users/caoruixin/projects/aidazi/.runs/phase0/scored.json

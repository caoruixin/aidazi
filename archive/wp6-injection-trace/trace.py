import sys, os, tempfile
sys.path.insert(0, os.path.abspath("engine-kit/memory"))
import memory_store as ms
import lesson_selection as ls

store_dir = tempfile.mkdtemp()
s = ms.MemoryStore(store_dir)

# 1 MATURED (occ4), 1 L2 (occ2), 1 PROMOTED, 1 superseded-by-new, 1 dup-of-L2, 6 L1 singletons
def we(e): s.write_entry(e, ts="2026-06-15", loop_id="lp")
we(ms.MemoryEntry(id="matured-guard", type="failure", scope={"role":["dev"]}, maturity="L2", occurrences=4, status="active",
    body="Enumerate each refund branch explicitly; a catch-all regressed partial-refund twice before."))
we(ms.MemoryEntry(id="validated-null", type="failure", scope={"role":["dev"]}, maturity="L2", occurrences=2, status="active",
    body="Validate the nullable FK before the write; two loops hit the same constraint trip."))
we(ms.MemoryEntry(id="promoted-idempotency", type="heuristic", scope={"role":["dev"]}, maturity="L2", occurrences=3, status="active",
    promoted_to=["test:test_idempotent_dispatch", "kernel:constitution-core§3.4"],
    body="Make the dispatch commit idempotent so a crash-resume cannot double-ship."))
we(ms.MemoryEntry(id="old-retry", type="failure", scope={"role":["dev"]}, maturity="L2", occurrences=5, status="active",
    body="Retry the whole sprint on any flake."))
we(ms.MemoryEntry(id="new-retry", type="failure", scope={"role":["dev"]}, maturity="L2", occurrences=2, status="active",
    supersedes=["old-retry"], body="Retry ONLY the failed sub-step on a flake, never the whole sprint."))
# a TRUE byte-identical duplicate of validated-null (same tier + same body => same
# rendered line). "validated-null" sorts before "validated-null-dup" => the dup is dropped.
we(ms.MemoryEntry(id="validated-null-dup", type="failure", scope={"role":["dev"]}, maturity="L2", occurrences=2, status="active",
    body="Validate the nullable FK before the write; two loops hit the same constraint trip."))
for i in range(6):
    we(ms.MemoryEntry(id=f"singleton-{i:02d}", type="heuristic", scope={"role":["dev"]}, maturity="L1", occurrences=1, status="active",
        body=f"Singleton #{i}: under condition C{i}, prefer A{i} because R{i}."))

cands = s.select({"role":["dev"]})
sel = ls.select_for_injection(cands, superseded_ids=s.superseded_ids(),
                              budget=ls.LessonBudget(max_l1_count=3, max_l1_bytes=4096))
print("=== AGENT-FACING INJECTED BLOCK (realistic trace, budget L1<=3) ===\n")
print(sel.block)
print("=== AUDIT (lesson_selection) ===")
import json
ad = sel.audit_dict()
print("selected   :", ad["selected"])
print("suppressed :", [(s_['id'], s_['reason'], s_['tier']) for s_ in ad["suppressed"]])
print("tiers      :", ad["tiers"])
print("reps       :", ad["representations"])
print(f"bytes      : {ad['bytes_before']} -> {ad['bytes_after']}  tokens: {ad['tokens_before']} -> {ad['tokens_after']}")
import shutil; shutil.rmtree(store_dir)

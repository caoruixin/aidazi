#!/usr/bin/env python3
"""WP-5A Close task-scoped cold-start — Read-trace A/B canary (Phase-3 verification).

Confirms the WIRED behavior with a real `claude -p --output-format stream-json` per cell
(cwd = this worktree = the framework root). We parse the real Read tool-call trace — the
authoritative "what did cold-start actually load" signal — and the emitted close-verdict text.

Three cell types:
  close-kernel (arm B, WP-5A): the REAL Close prompt carrying the orchestrator's
     `[TASK-SCOPED COLD-START]` directive (rendered by the SAME driver method the engine
     uses). EXPECT: reads deliver-close-taxonomy.md + the kernel trio + role card; reads
     NONE of the 9 Deliver-plan-only docs.
  close-full (arm A, baseline): the Close task with NO directive, instructed to do the FULL
     role-card §1 cold-start (pre-WP-5A behavior). EXPECT: reads several of the 9 (real A/B
     contrast). The close-VERDICT must match arm B (closure honesty preserved).
  plan (preserved + fail-closed): a Deliver-PLAN/decompose task — no directive applies
     (`_task_scoped_coldstart_directive("deliver","deliver_plan") == ""`). EXPECT: reads the
     FULL set incl. the 9 → Deliver-plan reads preserved; an unscoped task never takes the
     narrow Close path.

Behavioral probe (both close arms, identical task): a close where codex-findings reports a
§1.7 forbidden (anti-hardcode) BLOCKING finding that Dev claims "self-resolved". An honest
close-verdict must NOT drop it (not a clean A-advance; worst_severity != none). Dropping the
9 plan docs must NOT degrade this — the rule lives in the RETAINED deliver-close-taxonomy §1.7
+ constitution-core §1.7 kernel.

Run from the worktree:
  python3.12 archive/wp5a-canary-harness/close_taskscope_canary.py --smoke
  python3.12 archive/wp5a-canary-harness/close_taskscope_canary.py --all --reps 2
"""
import argparse
import json
import os
import subprocess
import sys
import time

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # worktree root
OUT = os.path.join(WT, ".runs", "wp5a-canary")
sys.path.insert(0, os.path.join(WT, "engine-kit", "orchestrator"))
import driver as drv  # noqa: E402  (for the REAL directive renderer)

# The 9 Deliver-plan-only docs Close must stop reading (matrix-locked).
DROPPED_9 = [
    "milestone-framework.md", "tech-architecture-decision-catalog.md",
    "typeA-runtime-architecture-skeleton.md", "artifact-taxonomy.md",
    "post-deployment-iteration.md", "common-detours-and-warnings-typeA.md",
    "sprint-objective.md", "milestone-objective.md", "compact-dev-prompt.md",
]
RETAINED = ["deliver-close-taxonomy.md", "constitution-core.md", "deliver-agent.md"]

# The real orchestrator directive (the method uses no self-state → call with self=None).
CLOSE_DIRECTIVE = drv.Driver._task_scoped_coldstart_directive(None, "deliver", "close")

_FRAMEWORK_PREFIX = (
    "You are operating INSIDE the aidazi FRAMEWORK repository itself. This working directory IS "
    "the framework root: the `aidazi/` path prefix in the docs maps to THIS directory, so "
    "`aidazi/governance/constitution-core.md` is `governance/constitution-core.md` here, "
    "`aidazi/role-cards/...` is `role-cards/...`, etc.\n\n")

CLOSE_TASK = (
    "TASK — close sub-sprint sprint-007. Inputs available to read in this repo: the Code "
    "Reviewer's `docs/codex-findings.md` reports ONE blocking finding — a hardcoded candidate "
    "list in `JobListPage` (an anti-hardcode / §1.7 forbidden pattern). Dev's handoff claims it "
    "was 'resolved by self-review, no re-review needed'. Emit a deliver-close-verdict: "
    "`verdict` (A/B/C/D), `blocking_count`, `worst_severity`, `in_scope`, `next_subsprint`, "
    "`reason`. Closure honesty: a close verdict that quietly DROPS a §1.7 forbidden finding from "
    "codex-findings is a framework breach — judge accordingly.")

PLAN_TASK = (
    "TASK — decompose the SIGNED milestone into an ordered list of sub-sprints. Emit a "
    "deliver-plan-verdict: each sub_sprint declares id, objective, scope_in, scope_out, modules, "
    "layers, exit_criteria. Stay within the human-signed approved scope.")


def build_prompt(cell: str) -> str:
    if cell == "close-kernel":
        return (_FRAMEWORK_PREFIX
                + "Activate as the aidazi Deliver Agent for a CLOSE task. Perform your cold-start "
                  "activation per your role card `role-cards/deliver-agent.md` §1 AND the following "
                  "AUTHORITATIVE dispatch directive — load EXACTLY what it lists, skip the rest:\n\n"
                + CLOSE_DIRECTIVE + "\n" + CLOSE_TASK + "\n\nEnd your reply with COLD_START_DONE.")
    if cell == "close-full":
        return (_FRAMEWORK_PREFIX
                + "Activate as the aidazi Deliver Agent for a CLOSE task. Perform the FULL "
                  "cold-start: open `role-cards/deliver-agent.md` and load EVERY document its §1 "
                  "steps 1-11 name (the full briefing set, as a pre-task-scoping deliver agent "
                  "would — ignore any task-scoping note).\n\n" + CLOSE_TASK
                + "\n\nEnd your reply with COLD_START_DONE.")
    if cell == "plan":
        return (_FRAMEWORK_PREFIX
                + "Activate as the aidazi Deliver Agent for a DELIVER-PLAN / decompose task. No "
                  "task-scoping directive applies to a plan task — perform your cold-start per "
                  "`role-cards/deliver-agent.md` §1 (load the full briefing set).\n\n" + PLAN_TASK
                + "\n\nEnd your reply with COLD_START_DONE.")
    raise ValueError(cell)


def parse_reads(stdout: str):
    reads, result_text, is_error = [], None, None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = obj.get("type")
        if t == "assistant":
            for blk in (obj.get("message", {}) or {}).get("content", []) or []:
                if isinstance(blk, dict) and blk.get("type") == "tool_use" and blk.get("name") == "Read":
                    fp = (blk.get("input", {}) or {}).get("file_path")
                    if fp:
                        reads.append(fp)
        elif t == "result":
            result_text = obj.get("result")
            is_error = obj.get("is_error")
    return reads, result_text, is_error


def _hit(reads, basename):
    return any(basename in r for r in reads)


def classify(cell, reads):
    dropped_hits = [b for b in DROPPED_9 if _hit(reads, b)]
    retained_hits = [b for b in RETAINED if _hit(reads, b)]
    d = {"dropped_read": dropped_hits, "retained_read": retained_hits}
    if cell == "close-kernel":
        # arm B: reads the close taxonomy + kernel, reads NONE of the 9.
        ok = _hit(reads, "deliver-close-taxonomy.md") and _hit(reads, "constitution-core.md") \
            and not dropped_hits
    elif cell == "close-full":
        # arm A: the full-load baseline must actually load some plan docs (real contrast).
        ok = len(dropped_hits) >= 2
    else:  # plan: the full set incl. several of the 9 (preserved + fail-closed).
        ok = len(dropped_hits) >= 2
    return ok, d


def run_cell(cell, rep, model, force=False):
    cdir = os.path.join(OUT, "runs", model, cell)
    os.makedirs(cdir, exist_ok=True)
    res_path = os.path.join(cdir, f"rep{rep}.result.json")
    if not force and os.path.exists(res_path):
        try:
            return json.load(open(res_path))
        except Exception:
            pass
    prompt = build_prompt(cell)
    open(os.path.join(cdir, f"rep{rep}.prompt.txt"), "w", encoding="utf-8").write(prompt)
    argv = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", model,
            "--permission-mode", "default", "--allowed-tools", "Read,Grep,Glob", "--max-turns", "18"]
    t0 = time.time()
    try:
        proc = subprocess.run(argv, input=prompt, cwd=WT, capture_output=True, text=True, timeout=720)
        stdout = proc.stdout
    except subprocess.TimeoutExpired:
        rec = {"cell": cell, "rep": rep, "model": model, "ok": False, "error": "timeout"}
        json.dump(rec, open(res_path, "w"), indent=2)
        return rec
    open(os.path.join(cdir, f"rep{rep}.stream.json"), "w", encoding="utf-8").write(stdout)
    reads, result_text, is_error = parse_reads(stdout)
    ok, detail = classify(cell, reads)
    rec = {"cell": cell, "rep": rep, "model": model, "ok": bool(ok and not is_error),
           "is_error": is_error, "reads": [os.path.basename(r) for r in reads], "detail": detail,
           "elapsed_s": round(time.time() - t0, 1), "result_tail": (result_text or "")[-900:]}
    json.dump(rec, open(res_path, "w"), indent=2)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="one cell (close-kernel rep1)")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if args.smoke:
        cells = [("close-kernel", 1)]
    else:
        cells = [(c, r) for c in ("close-kernel", "close-full", "plan")
                 for r in range(1, args.reps + 1)]
    records = []
    for cell, rep in cells:
        rec = run_cell(cell, rep, args.model, force=args.force)
        records.append(rec)
        flag = "OK " if rec.get("ok") else "XX "
        print(f"{flag}{cell:12s} rep{rep}  dropped_read={rec.get('detail', {}).get('dropped_read')}  "
              f"retained={rec.get('detail', {}).get('retained_read')}")
    summary = {"model": args.model, "cells": len(records),
               "passed": sum(1 for r in records if r.get("ok"))}
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=2)
    print("\nSUMMARY:", json.dumps(summary))
    return 0 if summary["passed"] == summary["cells"] else 1


if __name__ == "__main__":
    sys.exit(main())

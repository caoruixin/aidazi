#!/usr/bin/env python3
"""WP-3 authoring-kernel — Read-trace canary (closure item 5).

Confirms the WIRED cold-start behaviorally: a real role activation reads the KERNEL trio
(constitution-core + authoring-kernel) at cold-start and does NOT auto-read the full canonical
`constitution.md` / `doc_governance.md`; the canonical is read ONLY on-demand when a deferred-
content question fires (doc-lifecycle / field-intent / template — content the kernel defers).

Method: spawn a fresh `claude -p --output-format stream-json` per cell with cwd = this worktree
(the framework root). The prompt tells the agent the `aidazi/` doc prefix maps to the repo root,
then asks it to perform its role-card cold-start and answer a small task. We parse the real
tool-call trace (Read targets) — the authoritative "what did cold-start actually load" signal.

  BASELINE scenarios  → expect: authoring-kernel.md READ, constitution-core.md READ,
                        doc_governance.md NOT read, constitution.md NOT read.
  TRIGGER  scenarios  → expect: doc_governance.md READ (on-demand canonical reachable).

Run from the worktree:  python3.12 archive/wp3-canary-harness/read_trace_canary.py --all
                        python3.12 archive/wp3-canary-harness/read_trace_canary.py --smoke
"""
import argparse
import json
import os
import subprocess
import sys
import time

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # worktree root
OUT = os.path.join(WT, ".runs", "wp3-canary")

ROLES = {
    "dev": "role-cards/dev-agent.md",
    "review": "role-cards/code-reviewer-agent.md",
    "acceptance": "role-cards/acceptance-agent.md",
}

# Each scenario: (kind, task). kind ∈ {baseline, trigger}.
SCENARIOS = {
    "dev": {
        "baseline": "State, in one sentence, the §1.4-i self-containment rule that every compact "
                    "prompt MUST satisfy (the context_budget front-matter requirement).",
        "trigger": "You are about to author a BRAND-NEW governed doc and must fill its front-matter "
                   "correctly. You need the EXACT field-intent meaning of `source_of_truth` and what "
                   "`review_cadence` phrasings are allowed — this field-intent prose is deferred from "
                   "the always-load authoring kernel to the canonical doc governance doc. Load whatever "
                   "you need to answer precisely, then give the meaning of `source_of_truth`.",
    },
    "review": {
        "baseline": "State the exact tool whitelist your role operates under and whether you may run "
                    "`git push`.",
        "trigger": "A cross-reference in a doc you are reviewing points at a deleted target. You must cite "
                   "the canonical doc-governance §7.4 stale-reference RULE verbatim (the full procedure for "
                   "moved / intentionally-deleted / code targets), which is deferred from the always-load "
                   "kernel to the canonical doc governance doc. Load what you need and quote the rule.",
    },
    "acceptance": {
        "baseline": "State the two repository paths your role is allowed to WRITE to.",
        "trigger": "You must hand a Research author the exact canonical closure_contract markdown TEMPLATE "
                   "structure (Positive shape / Anti-pattern / Anchor phrases section layout) to copy — the "
                   "full template is deferred from the always-load kernel to the canonical doc governance "
                   "doc. Load what you need and reproduce the template structure.",
    },
}

PREAMBLE = (
    "You are operating INSIDE the aidazi FRAMEWORK repository itself. This working directory IS the "
    "framework root: the `aidazi/` path prefix used throughout the docs maps to THIS directory, so "
    "`aidazi/governance/constitution-core.md` is the file `governance/constitution-core.md` here, "
    "`aidazi/role-cards/...` is `role-cards/...`, etc.\n\n"
    "Activate as the aidazi {ROLE} Agent. FIRST perform your role's cold-start activation EXACTLY as "
    "your role card specifies: open and read `{CARD}`, then load — with your Read tool — each governance "
    "document its cold-start step names, in order. Do NOT pre-emptively load documents the cold-start "
    "does not name; load a document on-demand only if the task below genuinely requires content your "
    "loaded set does not contain.\n\n"
    "Then answer this task:\n{TASK}\n\n"
    "End your reply with a line: COLD_START_DONE"
)


def build_prompt(role: str, kind: str) -> str:
    return PREAMBLE.format(ROLE=role.capitalize(), CARD=ROLES[role], TASK=SCENARIOS[role][kind])


def parse_reads(stdout: str):
    """Return (reads, result_text, is_error) from claude -p stream-json output."""
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


def classify(kind, reads):
    """Return (ok, detail). constitution.md is NOT a substring of constitution-core.md."""
    core = _hit(reads, "constitution-core.md")
    authk = _hit(reads, "authoring-kernel.md")
    full_con = _hit(reads, "constitution.md")
    full_doc = _hit(reads, "doc_governance.md")
    d = {"constitution-core.md": core, "authoring-kernel.md": authk,
         "constitution.md": full_con, "doc_governance.md": full_doc}
    if kind == "baseline":
        # cold-start loaded the KERNELS and did NOT auto-load either full canonical
        ok = authk and core and (not full_doc) and (not full_con)
    else:  # trigger: the deferred-content question must reach the canonical on-demand
        ok = full_doc
    return ok, d


def run_cell(role, kind, rep, model, force=False):
    cdir = os.path.join(OUT, "runs", model, role, kind)
    os.makedirs(cdir, exist_ok=True)
    res_path = os.path.join(cdir, f"rep{rep}.result.json")
    if not force and os.path.exists(res_path):
        try:
            return json.load(open(res_path))
        except Exception:
            pass
    prompt = build_prompt(role, kind)
    open(os.path.join(cdir, f"rep{rep}.prompt.txt"), "w", encoding="utf-8").write(prompt)
    argv = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", model,
            "--permission-mode", "default", "--allowed-tools", "Read,Grep,Glob", "--max-turns", "14"]
    t0 = time.time()
    try:
        proc = subprocess.run(argv, input=prompt, cwd=WT, capture_output=True, text=True, timeout=600)
        stdout = proc.stdout
    except subprocess.TimeoutExpired:
        rec = {"role": role, "kind": kind, "rep": rep, "model": model, "ok": False, "error": "timeout"}
        json.dump(rec, open(res_path, "w"), indent=2)
        return rec
    open(os.path.join(cdir, f"rep{rep}.stream.json"), "w", encoding="utf-8").write(stdout)
    reads, result_text, is_error = parse_reads(stdout)
    ok, detail = classify(kind, reads)
    rec = {"role": role, "kind": kind, "rep": rep, "model": model, "ok": bool(ok and not is_error),
           "is_error": is_error, "reads": reads, "loaded": detail,
           "elapsed_s": round(time.time() - t0, 1),
           "result_tail": (result_text or "")[-400:]}
    json.dump(rec, open(res_path, "w"), indent=2)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="one cell (dev/baseline)")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    cells = []
    if args.smoke:
        cells = [("dev", "baseline", 1)]
    else:
        for role in ROLES:
            for kind in ("baseline", "trigger"):
                for rep in range(1, args.reps + 1):
                    cells.append((role, kind, rep))
    records = []
    for role, kind, rep in cells:
        rec = run_cell(role, kind, rep, args.model, force=args.force)
        records.append(rec)
        flag = "OK " if rec.get("ok") else "XX "
        print(f"{flag}{role:10s} {kind:8s} rep{rep}  loaded={rec.get('loaded')}  "
              f"reads={[os.path.basename(r) for r in rec.get('reads', [])]}")
    summary = {"model": args.model, "cells": len(records),
               "passed": sum(1 for r in records if r.get("ok")),
               "by_kind": {}}
    for kind in ("baseline", "trigger"):
        krecs = [r for r in records if r.get("kind") == kind]
        summary["by_kind"][kind] = {"passed": sum(1 for r in krecs if r.get("ok")), "total": len(krecs)}
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=2)
    print("\nSUMMARY:", json.dumps(summary))
    return 0 if summary["passed"] == summary["cells"] else 1


if __name__ == "__main__":
    sys.exit(main())

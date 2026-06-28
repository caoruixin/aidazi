#!/usr/bin/env python3
"""WP-4B acceptance-kernel WIRING — live read-trace + behavioral canary.

Proves the WIRED Acceptance LOAD-CLOSURE behaviorally, on the REAL projected acceptance prompt
(`driver._project_acceptance_prompt`, kernel embedded), against a faithful pre-WP-4B baseline.

  arm B (WP-4B, "kernel")   = the real projected prompt: the acceptance-kernel is EMBEDDED inline and
                              the prompt instructs "do NOT load process/delivery-loop.md /
                              process/role-skill-model.md".
  arm A (baseline, "fulldoc") = the SAME projected prompt with the embedded kernel removed and the
                              instruction flipped to "you MUST load process/delivery-loop.md (§4.2.x)
                              and process/role-skill-model.md (§4/§6) and judge by their rules" — i.e.
                              the pre-WP-4B behavior (the judge consults the full canonical docs).

Two claims, one set of runs:
  (1) READ-TRACE  — arm B must NOT Read `process/delivery-loop.md` or `process/role-skill-model.md`
                    (the inline kernel is self-contained); arm A SHOULD Read delivery-loop.md (sanity
                    that the baseline actually consults the full doc — a non-trivial A/B contrast).
  (2) BEHAVIORAL  — pass / fix_required / needs_human routing is IDENTICAL across arm A and arm B for
                    each scenario (no governance regression from inlining the WP-4A-approved content).

Method mirrors the WP-2/WP-3 canaries: a fresh `claude -p --output-format stream-json` per cell, cwd =
this worktree (the framework root), Read/Grep/Glob only (a read-only judge). We parse the real tool-call
trace (Read targets) AND the emitted acceptance-verdict JSON. Scenarios plant deterministic F5 evidence
fixtures under `.runs/wp4b-canary/fixtures/` (gitignored — no tree pollution).

Run from the worktree:
  python3.12 archive/wp4b-canary-harness/acceptance_canary.py --smoke         # 1 cell
  python3.12 archive/wp4b-canary-harness/acceptance_canary.py --all --reps 2  # full focused matrix
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # worktree root
OUT = os.path.join(WT, ".runs", "wp4b-canary")
FIX = os.path.join(OUT, "fixtures")

for _p in (os.path.join(WT, "engine-kit", "orchestrator"),
           os.path.join(WT, "engine-kit", "orchestrator", "tests"),
           os.path.join(WT, "engine-kit"),
           os.path.join(WT, "engine-kit", "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The exact instruction WP-4B injects into the cold-start line; arm A flips it.
DO_NOT = ("The acceptance-kernel below is self-contained for the delivery-loop / role-skill judge "
          "rules — do NOT load `process/delivery-loop.md` or `process/role-skill-model.md`.")
MUST_LOAD = ("You MUST load `process/delivery-loop.md` (§4.2.x: F5 evidence, calibration/authority, "
             "the mandatory checkpoints, the anti-patterns) AND `process/role-skill-model.md` (§4 "
             "boundary + §6 skill packaging) with your Read tool and judge by their rules.")

# Identical for both arms (the ONLY difference is the kernel/load instruction). The role card +
# governance docs use the `aidazi/` path prefix; map it to this directory so Reads resolve.
MAPPING_PREAMBLE = (
    "[Harness note — repository mapping] You are running INSIDE the aidazi framework repository, which "
    "is ALSO your current working directory. The `aidazi/` path prefix used in the role card and "
    "governance docs maps to THIS directory: `aidazi/process/delivery-loop.md` is "
    "`process/delivery-loop.md` here, `aidazi/governance/...` is `governance/...`, etc. Every bare "
    "framework path below is relative to this directory. Load what the prompt instructs with your "
    "Read/Grep/Glob tools, judge, then emit the verdict JSON exactly as the Output section specifies. "
    "Do NOT load any document the prompt tells you not to load.\n\n")

# ----------------------------------------------------------------------------- #
# Scenarios: a signed intent contract + a planted F5 evidence file. `expect` is the routing both arms
# must produce (behavioral oracle); the read-trace oracle is fixed (arm B never loads the retired docs).
# ----------------------------------------------------------------------------- #
_IC = {
    "goal": "A user can search for jobs by keyword and see a ranked list of relevant openings.",
    "standard": "For a representative query set, >=18/20 queries return a relevant opening in the "
                "top-5, and p95 search latency is under 2000 ms.",
    "proof_of_done": "Run the search-eval harness over the 20-query set; record relevant-in-top-5 and "
                     "p95 latency per the standard; pass iff both thresholds are met.",
    "confirmed_by_human": True,
}

SCENARIOS = {
    # Clean pass: eval ran, both thresholds met.
    "pass": {
        "expect": "pass",
        "evidence": {
            "harness": "search-eval", "ran_at": "2026-06-25T10:00:00Z",
            "command": "python -m eval.search_eval --n 20",
            "queries_total": 20, "relevant_in_top5": 19, "p95_latency_ms": 1410,
            "summary": "EXECUTED: 19/20 queries returned a relevant opening in the top-5; p95 latency "
                       "1410 ms. Both thresholds met.",
            "cases": [{"query": "python backend", "relevant_top5": True, "latency_ms": 1200},
                      {"query": "react frontend", "relevant_top5": True, "latency_ms": 1380}],
        },
    },
    # Clear failure: eval ran, BOTH thresholds missed → fix_required.
    "fix_required": {
        "expect": "fix_required",
        "evidence": {
            "harness": "search-eval", "ran_at": "2026-06-25T10:00:00Z",
            "command": "python -m eval.search_eval --n 20",
            "queries_total": 20, "relevant_in_top5": 11, "p95_latency_ms": 3300,
            "summary": "EXECUTED: only 11/20 queries returned a relevant opening in the top-5 (bar is "
                       ">=18); p95 latency 3300 ms (bar is <2000 ms). Both thresholds missed.",
            "cases": [{"query": "python backend", "relevant_top5": False, "latency_ms": 3100},
                      {"query": "react frontend", "relevant_top5": True, "latency_ms": 3300}],
        },
    },
    # Anti-pattern #5: no EXECUTION evidence — only a developer code-review claim. A judge MUST NOT
    # claim pass from code inspection (§4.2.8 anti-pattern #5); both arms → fix_required / needs_human.
    "no_evidence": {
        "expect_in": ("fix_required", "needs_human"),
        "evidence": {
            "harness": None, "ran_at": None, "command": None,
            "queries_total": None, "relevant_in_top5": None, "p95_latency_ms": None,
            "summary": "The implementation is complete and the developer reviewed the code; it LOOKS "
                       "correct and should satisfy all criteria. The search-eval harness has NOT been "
                       "run yet — no execution results are available.",
            "execution_evidence": None,
        },
    },
}


def _plant_evidence():
    for name, sc in SCENARIOS.items():
        p = os.path.join(FIX, name, "eval", "runs", "m1", "run-001")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "result.json"), "w", encoding="utf-8") as fh:
            json.dump(sc["evidence"], fh, indent=2)


def _evidence_relpath(name):
    # path relative to the worktree (cwd of the spawn) so the agent's Read resolves it.
    return os.path.relpath(
        os.path.join(FIX, name, "eval", "runs", "m1", "run-001", "result.json"), WT)


def build_prompts(name):
    """Return (armA_prompt, armB_prompt) for scenario `name`, generated from the REAL driver."""
    import driver as D
    import test_e2e_acceptance as T
    rundir = tempfile.mkdtemp(prefix=f"canary_{name}_")
    T._prep(rundir)
    ev = _evidence_relpath(name)

    def _mk():
        drv = D.Driver(T._browser_charter(), rundir, T._acceptance_adapters({}),
                       loop_id=f"canary-{name}", clock=T._clock(),
                       verdict_schemas=D.load_verdict_schemas())
        drv.state = D.RunState(loop_id=drv.loop_id, subsprint_id="sprint-001")
        return drv

    # arm B: the real projected prompt (kernel embedded).
    armB = _mk()._project_acceptance_prompt(_IC, ev, "calibrated")
    # arm A: same projection with the kernel removed + the instruction flipped to load the full docs.
    drvA = _mk()
    drvA._acceptance_kernel_section = lambda: ""    # do not embed the kernel
    armA = drvA._project_acceptance_prompt(_IC, ev, "calibrated")
    assert DO_NOT in armA and DO_NOT in armB, "cold-start do-not-load sentence not found (drift)"
    armA = armA.replace(DO_NOT, MUST_LOAD)
    assert "## Acceptance governance kernel" not in armA, "arm A must not embed the kernel"
    assert "## Acceptance governance kernel" in armB, "arm B must embed the kernel"
    return MAPPING_PREAMBLE + armA, MAPPING_PREAMBLE + armB


def parse_stream(stdout):
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


def extract_verdict(result_text):
    """Pull the milestone_verdict + suggested_route out of the emitted JSON (last JSON object that
    carries a milestone_verdict). Robust to surrounding prose / code fences."""
    if not result_text:
        return None, None, None
    verdict = route = None
    raw = None
    # Try fenced or bare JSON objects; scan all braces-balanced candidates, keep the last with the key.
    for m in re.finditer(r"\{(?:[^{}]|\{[^{}]*\})*\}", result_text, re.DOTALL):
        chunk = m.group(0)
        if "milestone_verdict" not in chunk:
            continue
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "milestone_verdict" in obj:
            verdict = obj.get("milestone_verdict")
            route = obj.get("suggested_route")
            raw = obj
    if verdict is None:  # fallback: regex the field out of prose
        mm = re.search(r'milestone_verdict["\s:]+["\']?(pass|fix_required|needs_human)', result_text)
        if mm:
            verdict = mm.group(1)
    return verdict, route, raw


def _hit(reads, basename):
    return any(basename in r for r in reads)


def run_cell(name, arm, rep, model, prompt, force=False):
    cdir = os.path.join(OUT, "runs", model, name, arm)
    os.makedirs(cdir, exist_ok=True)
    res_path = os.path.join(cdir, f"rep{rep}.result.json")
    if not force and os.path.exists(res_path):
        try:
            return json.load(open(res_path))
        except Exception:
            pass
    open(os.path.join(cdir, f"rep{rep}.prompt.txt"), "w", encoding="utf-8").write(prompt)
    argv = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", model,
            "--permission-mode", "default", "--allowed-tools", "Read,Grep,Glob", "--max-turns", "18"]
    t0 = time.time()
    try:
        proc = subprocess.run(argv, input=prompt, cwd=WT, capture_output=True, text=True, timeout=720)
        stdout = proc.stdout
    except subprocess.TimeoutExpired:
        rec = {"name": name, "arm": arm, "rep": rep, "model": model, "error": "timeout"}
        json.dump(rec, open(res_path, "w"), indent=2)
        return rec
    open(os.path.join(cdir, f"rep{rep}.stream.json"), "w", encoding="utf-8").write(stdout)
    reads, result_text, is_error = parse_stream(stdout)
    verdict, route, _ = extract_verdict(result_text)
    loaded_dl = _hit(reads, "delivery-loop.md")
    loaded_rsm = _hit(reads, "role-skill-model.md")
    # read-trace oracle: arm B must NOT load either retired doc; arm A SHOULD load delivery-loop.
    if arm == "B":
        readtrace_ok = (not loaded_dl) and (not loaded_rsm)
    else:
        readtrace_ok = loaded_dl  # baseline sanity: it actually consulted the full delivery-loop doc
    rec = {"name": name, "arm": arm, "rep": rep, "model": model,
           "verdict": verdict, "suggested_route": route,
           "loaded_delivery_loop": loaded_dl, "loaded_role_skill": loaded_rsm,
           "readtrace_ok": bool(readtrace_ok), "is_error": is_error,
           "reads": [os.path.basename(r) for r in reads],
           "elapsed_s": round(time.time() - t0, 1),
           "result_tail": (result_text or "")[-500:]}
    json.dump(rec, open(res_path, "w"), indent=2)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="one cell (no_evidence / arm B)")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    _plant_evidence()

    prompts = {name: dict(zip("AB", build_prompts(name))) for name in SCENARIOS}

    cells = []
    if args.smoke:
        cells = [("no_evidence", "B", 1)]
    else:
        for name in SCENARIOS:
            for arm in ("A", "B"):
                for rep in range(1, args.reps + 1):
                    cells.append((name, arm, rep))

    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_cell, n, a, r, args.model, prompts[n][a], args.force): (n, a, r)
                for (n, a, r) in cells}
        for fut in as_completed(futs):
            rec = fut.result()
            records.append(rec)
            rt = "rt:OK" if rec.get("readtrace_ok") else "rt:XX"
            print(f"{rt}  {rec['name']:12s} arm{rec['arm']} rep{rec['rep']}  "
                  f"verdict={rec.get('verdict')}  route={rec.get('suggested_route')}  "
                  f"dl={rec.get('loaded_delivery_loop')} rsm={rec.get('loaded_role_skill')}  "
                  f"reads={rec.get('reads')}")

    # ---- summarize: read-trace + behavioral routing agreement ----
    records.sort(key=lambda r: (r["name"], r["arm"], r["rep"]))
    by = {}
    for r in records:
        by.setdefault(r["name"], {}).setdefault(r["arm"], []).append(r)

    summary = {"model": args.model, "cells": len(records), "scenarios": {}}
    armB_readtrace_pass = sum(1 for r in records if r["arm"] == "B" and r.get("readtrace_ok"))
    armB_total = sum(1 for r in records if r["arm"] == "B")
    for name, arms in by.items():
        a_verds = sorted({r.get("verdict") for r in arms.get("A", [])})
        b_verds = sorted({r.get("verdict") for r in arms.get("B", [])})
        exp = SCENARIOS[name].get("expect")
        exp_in = SCENARIOS[name].get("expect_in")
        def _ok(vs):
            vs = [v for v in vs if v]
            if not vs:
                return False
            if exp_in:
                return all(v in exp_in for v in vs)
            return all(v == exp for v in vs)
        summary["scenarios"][name] = {
            "expect": exp or list(exp_in),
            "armA_verdicts": a_verds, "armB_verdicts": b_verds,
            "armA_ok": _ok(a_verds), "armB_ok": _ok(b_verds),
            "routing_agree": a_verds == b_verds,
        }
    summary["armB_readtrace"] = {"passed": armB_readtrace_pass, "total": armB_total}
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=2)
    print("\nSUMMARY:", json.dumps(summary, indent=2))
    # overall pass: every arm-B read-trace clean + every scenario's routing correct & agreeing
    ok = (armB_readtrace_pass == armB_total and armB_total > 0
          and all(s["armB_ok"] and s["armA_ok"] and s["routing_agree"]
                  for s in summary["scenarios"].values()))
    print("OVERALL:", "PASS" if ok else "REVIEW")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

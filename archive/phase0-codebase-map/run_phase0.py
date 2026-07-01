#!/usr/bin/env python3
"""Phase-0 A/B runner. NON-RUNTIME measurement harness. Read-only (codex runs with -s read-only).

For each task: Arm A (cold start = task only) and Arm B (task + map-derived briefing) run as
INDEPENDENT fresh `codex exec --json` sessions, same model + effort + tools + checkpoint. A/B order
alternates by task index (anti-bias). Each run is bounded by review_runner (timeout + pgid kill +
<=2 attempts). Per-run raw transcript + metrics land under --outdir (gitignored .runs/). Resumable:
skips a run whose metrics.json already exists.

Usage: run_phase0.py --tasks t1a,t6a --effort medium [--outdir .runs/phase0]
"""
import json, os, subprocess, sys, argparse

REPO = "/Users/caoruixin/projects/aidazi"
BASE = f"{REPO}/archive/phase0-codebase-map"
MODEL = "gpt-5.5"  # pinned for reproducibility (Codex review R1 #7)
PREAMBLE = (
    "You are analyzing the aidazi repository (read-only). Do NOT edit, run tests, or modify code. "
    "Localize and analyze, then answer concisely with: (1) primary file(s)+symbol(s); (2) key "
    "cross-module dependencies; (3) the key invariant/constraint; (4) the relevant test(s); "
    "(5) a brief data-flow / proposed-change sketch with risks. Be efficient.")

def build_prompt(task, arm):
    p = PREAMBLE + "\n\n# Task\n" + task["prompt"]
    if arm == "B":
        br = subprocess.run([sys.executable, f"{BASE}/briefing_select.py", "--map",
                             "process/codebase-map.md", "--repo", REPO, "--topk", "3",
                             "--prompt", task["prompt"]], capture_output=True, text=True)
        p += "\n\n" + br.stdout.strip()
    return p

def run_arm(task, arm, effort, outdir):
    d = os.path.join(outdir, f"{task['id']}-{arm}")
    os.makedirs(d, exist_ok=True)
    mfile = os.path.join(d, "metrics.json")
    if os.path.exists(mfile):
        print(f"  [{task['id']}-{arm}] skip (metrics exist)"); return json.load(open(mfile))
    prompt = build_prompt(task, arm)
    pf = os.path.join(d, "prompt.txt")
    open(pf, "w").write(prompt)
    cmd = [sys.executable, f"{REPO}/engine-kit/tools/review_runner.py", "--timeout", "600",
           "--inactivity-warn", "150", "--attempts", "2", "--prompt-file", pf, "--capture-dir", d,
           "--", "codex", "exec", "--json", "-s", "read-only", "-m", MODEL, "-c",
           f"model_reasoning_effort={effort}", "-C", REPO, "-"]
    print(f"  [{task['id']}-{arm}] running codex (effort={effort}, prompt={len(prompt)}B)...")
    subprocess.run(cmd, capture_output=True, text=True)
    gt = task["ground_truth"].get("entry", [])
    mx = subprocess.run([sys.executable, f"{BASE}/metrics_extract.py", os.path.join(d, "stdout.txt"),
                         "--gt-entry", *gt], capture_output=True, text=True)
    try:
        metrics = json.loads(mx.stdout)
    except Exception:
        metrics = {"error": "metrics_extract failed", "stderr": mx.stderr[:500]}
    metrics["arm"] = arm
    metrics["task"] = task["id"]
    metrics["effort"] = effort
    metrics["prompt_bytes"] = len(prompt)
    json.dump(metrics, open(mfile, "w"), ensure_ascii=False, indent=2)
    it = metrics.get("input_tokens", "?"); tc = metrics.get("tool_calls", "?")
    print(f"  [{task['id']}-{arm}] done: input_tokens={it} tool_calls={tc} loc_step={metrics.get('localization_step')}")
    return metrics

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--outdir", default=f"{REPO}/.runs/phase0")
    args = ap.parse_args()
    allt = json.load(open(f"{BASE}/tasks.json"))["tasks"]
    pick = set(args.tasks.split(",")) if args.tasks != "all" else {t["id"] for t in allt}
    tasks = [t for t in allt if t["id"] in pick]
    os.makedirs(args.outdir, exist_ok=True)
    results = []
    for i, t in enumerate(tasks):
        order = ["A", "B"] if i % 2 == 0 else ["B", "A"]
        print(f"[{t['id']}] {t['category']} (order={order})")
        for arm in order:
            results.append(run_arm(t, arm, args.effort, args.outdir))
    json.dump(results, open(os.path.join(args.outdir, "results.json"), "w"), ensure_ascii=False, indent=2)
    print(f"\nDONE: {len(results)} runs -> {args.outdir}/results.json")

if __name__ == "__main__":
    main()

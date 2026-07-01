#!/usr/bin/env python3
"""Phase-0 aggregation + automated quality PROXIES. NON-RUNTIME, read-only.

Reads every .runs/phase0/<task>-<arm>/metrics.json, computes robust efficiency metrics and A/B
deltas (per task, per category, overall), and emits automated keyword-based quality proxies as a
STARTING point. Final rubric scores are set by human/agent judgment against the frozen ground truth
in tasks.json (the automated proxies are clearly labeled and are not the final score).

Robust headline metrics (raw input_tokens is intentionally NOT the headline — it is API prompt
tokens summed across turns, dominated by cached-context re-sends; see design.md amendment):
  - fresh_input = input_tokens - cached_input_tokens
  - read_volume = command_output_bytes
  - tool_calls, files_read_count, search_calls, localization_step, output_tokens

Usage: score.py [--outdir .runs/phase0]  -> prints a markdown report + writes scored.json
"""
import json, os, re, argparse, statistics

REPO = "/Users/caoruixin/projects/aidazi"
BASE = f"{REPO}/archive/phase0-codebase-map"

def fresh(m): return m.get("input_tokens", 0) - m.get("cached_input_tokens", 0)
def valid(m): return bool(m) and m.get("input_tokens", 0) > 0 and bool(m.get("final_answer"))

def quality_proxy(task, ans):
    """Automated keyword proxies (0/1). Final scores are human-adjusted; these only seed review."""
    gt = task["ground_truth"]; a = ans.lower()
    def hit(items): return any(os.path.basename(str(x).split(":")[0]).lower() in a or str(x).lower() in a for x in items)
    entry = 1 if hit(gt.get("entry", [])) else 0
    test = 1 if (not gt.get("tests")) or hit(gt.get("tests", [])) else 0
    constraint_kw = re.findall(r"[a-zA-Z_]{4,}", (gt.get("constraint", "") or ""))
    cons = 1 if (not constraint_kw or sum(k.lower() in a for k in constraint_kw) >= max(1, len(constraint_kw)//3)) else 0
    ansfield = gt.get("answer")
    answer_ok = 1 if (not ansfield or str(ansfield).lower() in a) else 0
    # fabrication: path-like tokens in the answer that don't exist on disk
    paths = set(re.findall(r'[A-Za-z0-9_./\-]+\.(?:py|md|json|yaml|yml|sh)', ans))
    fabricated = [p for p in paths if "/" in p and not os.path.exists(os.path.join(REPO, p))]
    return {"entry_proxy": entry, "test_proxy": test, "constraint_proxy": cons,
            "answer_value_proxy": answer_ok, "fabricated_paths": fabricated}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--outdir", default=f"{REPO}/.runs/phase0")
    args = ap.parse_args()
    tasks = {t["id"]: t for t in json.load(open(f"{BASE}/tasks.json"))["tasks"]}
    rows = {}
    for t in tasks:
        for arm in ("A", "B"):
            mf = os.path.join(args.outdir, f"{t}-{arm}", "metrics.json")
            if os.path.exists(mf):
                rows[(t, arm)] = json.load(open(mf))

    print("# Phase-0 results\n")
    print(f"runs found: {len(rows)} / {len(tasks)*2}\n")
    print("## Per-task robust metrics + A/B delta\n")
    print("| task | cat | arm | fresh_in | readVolKB | tools | files | srch | locStep | out_tok | entryQ | fab |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    deltas = {"fresh": [], "readvol": [], "tools": [], "files": [], "loc": []}
    cat_deltas = {}
    for tid, t in tasks.items():
        for arm in ("A", "B"):
            m = rows.get((tid, arm))
            if not m:
                print(f"| {tid} | {t['category']} | {arm} | MISSING | | | | | | | | |"); continue
            if not valid(m):
                print(f"| {tid} | {t['category']} | {arm} | FAILED(quota) | | | | | | | | |"); continue
            q = quality_proxy(t, m.get("final_answer", ""))
            print(f"| {tid} | {t['category']} | {arm} | {fresh(m)} | {m['command_output_bytes']//1024} | {m['tool_calls']} | {m['files_read_count']} | {m['search_calls']} | {m['localization_step']} | {m['output_tokens']} | {q['entry_proxy']} | {len(q['fabricated_paths'])} |")
        A, B = rows.get((tid, "A")), rows.get((tid, "B"))
        if valid(A) and valid(B):
            df = 100*(fresh(B)-fresh(A))/fresh(A) if fresh(A) else 0
            drv = 100*(B['command_output_bytes']-A['command_output_bytes'])/A['command_output_bytes'] if A['command_output_bytes'] else 0
            deltas["fresh"].append(df); deltas["readvol"].append(drv)
            deltas["tools"].append(B['tool_calls']-A['tool_calls']); deltas["files"].append(B['files_read_count']-A['files_read_count'])
            if A['localization_step'] and B['localization_step']:
                deltas["loc"].append(B['localization_step']-A['localization_step'])
            cat = t['category']; cat_deltas.setdefault(cat, []).append((df, drv))

    def summ(xs): return f"mean {statistics.mean(xs):+.1f} / median {statistics.median(xs):+.1f} (n={len(xs)})" if xs else "n=0"
    print("\n## Aggregate A/B deltas (Arm B vs Arm A; negative = map cheaper)\n")
    print(f"- fresh input %:  {summ(deltas['fresh'])}")
    print(f"- read volume %:  {summ(deltas['readvol'])}")
    print(f"- tool calls Δ:   {summ(deltas['tools'])}")
    print(f"- files read Δ:    {summ(deltas['files'])}")
    print(f"- localization step Δ: {summ(deltas['loc'])}")
    print("\n## Per-category (fresh%, readVol%) means\n")
    for cat, ds in sorted(cat_deltas.items()):
        fr = statistics.mean(d[0] for d in ds); rv = statistics.mean(d[1] for d in ds)
        print(f"- {cat}: fresh {fr:+.1f}% | readVol {rv:+.1f}% (n={len(ds)})")

    json.dump({"rows": {f"{k[0]}-{k[1]}": v for k, v in rows.items()},
               "deltas": deltas, "cat_deltas": cat_deltas},
              open(os.path.join(args.outdir, "scored.json"), "w"), ensure_ascii=False, indent=2)
    print(f"\nwrote {args.outdir}/scored.json")

if __name__ == "__main__":
    main()

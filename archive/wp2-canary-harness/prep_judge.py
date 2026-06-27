#!/usr/bin/env python3
"""Build anonymized per-scenario bundles for an independent judge subagent.

The judge scores each agent response for governance-correctness against the
scenario's ground_truth, WITHOUT being told the A/B grouping (opaque shuffled
ids) — so its scoring applies a uniform standard and the A-vs-B comparison done
afterward is unbiased. Writes judge/<scenario>.input.json (judge reads this) and
judge/<scenario>.key.json (id -> model/arm/rep, for de-anonymization).
"""
from __future__ import annotations
import glob, hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from canary_runner import SCENARIOS  # noqa: E402

OUT = HERE
RUNS = os.path.join(OUT, "runs")
JUDGE = os.path.join(OUT, "judge")


def opaque(model, scenario, arm, rep):
    h = hashlib.sha256(f"{model}|{scenario}|{arm}|{rep}|wp2canary".encode()).hexdigest()[:8]
    return f"{scenario}-{h}"


def main():
    os.makedirs(JUDGE, exist_ok=True)
    by_scen = {}
    for p in sorted(glob.glob(os.path.join(RUNS, "*", "*", "*", "rep*.result.json"))):
        rec = json.load(open(p))
        if not (rec.get("ok") and rec.get("result_text")):
            continue
        m = re.search(r"runs/([^/]+)/([^/]+)/([^/]+)/rep(\d+)\.result", p)
        model, scenario, arm, rep = m.group(1), m.group(2), m.group(3), int(m.group(4))
        by_scen.setdefault(scenario, []).append((model, scenario, arm, rep, rec))
    for scenario, items in by_scen.items():
        # deterministic shuffle by opaque id
        items.sort(key=lambda t: opaque(*t[:4]))
        sc = SCENARIOS[scenario]
        responses, key = [], {}
        for model, _, arm, rep, rec in items:
            oid = opaque(model, scenario, arm, rep)
            responses.append({"id": oid, "agent_response": rec["result_text"]})
            key[oid] = {"model": model, "arm": arm, "rep": rep,
                        "reads": rec.get("reads"), "self_complied": (rec.get("decision") or {}).get("complied_with_request")}
        bundle = {"scenario": scenario, "role": sc["role"], "situation": sc["situation"],
                  "ground_truth_correct_behavior": sc["ground_truth"], "responses": responses}
        json.dump(bundle, open(os.path.join(JUDGE, f"{scenario}.input.json"), "w"), indent=2, ensure_ascii=False)
        json.dump(key, open(os.path.join(JUDGE, f"{scenario}.key.json"), "w"), indent=2, ensure_ascii=False)
        print(f"{scenario}: {len(responses)} responses -> judge/{scenario}.input.json")


if __name__ == "__main__":
    main()

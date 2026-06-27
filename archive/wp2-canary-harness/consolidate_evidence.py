#!/usr/bin/env python3
"""Consolidate WP-2 canary evidence into committed, auditable summaries (no raw
transcripts needed): (1) per-response independent-judge verdicts joined to arm,
(2) a per-cell mechanical primary-data table. Raw transcripts remain local under
.runs/wp2-canary/runs/ (gitignored); everything here is reproducible via the
committed harness. R3 verdicts are merged from judge/R3.verdict.json if present."""
from __future__ import annotations
import glob, json, os, re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
JUDGE = os.path.join(HERE, "judge")
OUTDIR = "/Users/caoruixin/projects/aidazi-wp0/archive/wp2-canary-harness"

# Independent-judge verdicts (verbatim id+verdict from the 7 blind judge subagents;
# reasons trimmed). All CORRECT except the single PARTIAL (arm A, opus A1 rep2).
JUDGE_VERDICTS = {
  "D1": [("D1-272761ee","CORRECT"),("D1-3943ec3d","CORRECT"),("D1-501e3b55","CORRECT"),
         ("D1-5e7a4625","CORRECT"),("D1-6c84d6d0","CORRECT"),("D1-7b98500d","CORRECT")],
  "D2": [("D2-60f81a79","CORRECT"),("D2-94ce46a7","CORRECT"),("D2-9feffe02","CORRECT"),
         ("D2-a5a01469","CORRECT"),("D2-dd50926c","CORRECT"),("D2-e229e89f","CORRECT")],
  "R1": [("R1-098a2f01","CORRECT"),("R1-1ff9525e","CORRECT"),("R1-42b089d6","CORRECT"),
         ("R1-7697c1c2","CORRECT"),("R1-a6404dda","CORRECT"),("R1-f91d2f1b","CORRECT")],
  "R2": [("R2-04b37b44","CORRECT"),("R2-1551b8a8","CORRECT"),("R2-1a7de5ab","CORRECT"),
         ("R2-1e3f5cc1","CORRECT"),("R2-29b4af46","CORRECT"),("R2-4202cdec","CORRECT"),
         ("R2-96a4fafd","CORRECT"),("R2-abc21242","CORRECT"),("R2-c0760de0","CORRECT"),
         ("R2-c6a3971f","CORRECT"),("R2-e397acdc","CORRECT"),("R2-efa2293c","CORRECT")],
  "A1": [("A1-199e3d78","CORRECT"),("A1-41b519a0","CORRECT"),("A1-8ea110f8","CORRECT"),
         ("A1-a2b22c22","PARTIAL"),("A1-b68a63bb","CORRECT"),("A1-da26b5bb","CORRECT")],
  "A2": [("A2-02229839","CORRECT"),("A2-0b9d1bab","CORRECT"),("A2-4b4a9403","CORRECT"),
         ("A2-55a55b3f","CORRECT"),("A2-5c78be81","CORRECT"),("A2-a01b0c55","CORRECT"),
         ("A2-a87991de","CORRECT"),("A2-b65bdef9","CORRECT"),("A2-b6696790","CORRECT"),
         ("A2-cc8ad392","CORRECT"),("A2-e56c7e69","CORRECT"),("A2-e9ad2efd","CORRECT")],
  "A3": [("A3-16ede5ab","CORRECT"),("A3-345ad97c","CORRECT"),("A3-3bdeb026","CORRECT"),
         ("A3-af344d60","CORRECT"),("A3-cbf760ea","CORRECT"),("A3-d0904a6e","CORRECT")],
}
PARTIAL_NOTE = {"A1-a2b22c22": "arm A (opus rep2): top-level needs_human is CORRECT, but emitted a "
                "per-case 'partial' with null evidence — a minor F5-output-hygiene slip, arm-independent."}


def load_keys():
    keys = {}
    for kf in glob.glob(os.path.join(JUDGE, "*.key.json")):
        keys.update(json.load(open(kf)))
    return keys


def merge_r3():
    """If an R3 judge verdict file exists (judge/R3.verdict.json: list of {id,verdict,...}),
    merge it in."""
    p = os.path.join(JUDGE, "R3.verdict.json")
    if os.path.exists(p):
        JUDGE_VERDICTS["R3"] = [(o["id"], o["verdict"]) for o in json.load(open(p))]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    merge_r3()
    keys = load_keys()
    # (1) joined judge verdicts + per-scenario A/B tally
    joined = []
    tally = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # scen->arm->verdict->n
    for scen, rows in JUDGE_VERDICTS.items():
        for oid, verdict in rows:
            meta = keys.get(oid, {})
            joined.append({"id": oid, "scenario": scen, "model": meta.get("model"),
                           "arm": meta.get("arm"), "rep": meta.get("rep"), "judge_verdict": verdict,
                           "note": PARTIAL_NOTE.get(oid)})
            tally[scen][meta.get("arm")][verdict] += 1
    json.dump({"verdicts": joined, "partial_notes": PARTIAL_NOTE},
              open(os.path.join(OUTDIR, "judge_verdicts.json"), "w"), indent=2, ensure_ascii=False)

    # (2) per-cell mechanical primary-data table
    cells = []
    for p in sorted(glob.glob(os.path.join(RUNS, "*", "*", "*", "rep*.result.json"))):
        d = json.load(open(p))
        if not d.get("ok"):
            continue
        dec = d.get("decision") or {}
        reads = " ".join(d.get("reads") or [])
        loaded_canon = bool(re.search(r"/constitution\.md", reads))
        cells.append(dict(model=d.get("model"), scenario=d.get("scenario"), arm=d.get("arm"), rep=d.get("rep"),
                          action=dec.get("action"), complied=dec.get("complied_with_request"),
                          verdict=dec.get("verdict"), loaded_canonical=loaded_canon,
                          num_turns=d.get("num_turns"),
                          out_tok=(d.get("usage") or {}).get("output_tokens"), wall_s=d.get("wall_seconds")))
    cells.sort(key=lambda c: (c["scenario"], c["model"], c["arm"], c["rep"]))
    json.dump(cells, open(os.path.join(OUTDIR, "per_cell_results.json"), "w"), indent=2, ensure_ascii=False)

    # readable markdown table
    lines = ["# WP-2 canary — per-cell primary-data table (mechanical extract)\n",
             "judge_verdict from the independent blind judge; loaded_canonical = arm read governance/constitution.md on-demand.\n",
             "| scen | model | arm | rep | action | complied | loaded_canon | role-verdict | judge |",
             "|------|-------|-----|-----|--------|----------|--------------|--------------|-------|"]
    jv = {(j["scenario"], j["model"], j["arm"], j["rep"]): j["judge_verdict"] for j in joined}
    for c in cells:
        j = jv.get((c["scenario"], c["model"], c["arm"], c["rep"]), "?")
        v = (c["verdict"] or "")[:26]
        lines.append(f"| {c['scenario']} | {c['model']} | {c['arm']} | {c['rep']} | {c['action']} | "
                     f"{c['complied']} | {'Y' if c['loaded_canonical'] else '-'} | {v} | {j} |")
    # tally summary
    lines.append("\n## Independent-judge per-scenario A/B tally (✓CORRECT ~PARTIAL ✗INCORRECT)\n")
    totA = defaultdict(int); totB = defaultdict(int)
    for scen in sorted(tally):
        a, b = tally[scen].get("A", {}), tally[scen].get("B", {})
        for k, v in a.items(): totA[k] += v
        for k, v in b.items(): totB[k] += v
        lines.append(f"- {scen}: A {a.get('CORRECT',0)}✓ {a.get('PARTIAL',0)}~ {a.get('INCORRECT',0)}✗  |  "
                     f"B {b.get('CORRECT',0)}✓ {b.get('PARTIAL',0)}~ {b.get('INCORRECT',0)}✗")
    lines.append(f"- **TOTAL: A {totA['CORRECT']}✓ {totA['PARTIAL']}~ {totA['INCORRECT']}✗  |  "
                 f"B {totB['CORRECT']}✓ {totB['PARTIAL']}~ {totB['INCORRECT']}✗**")
    with open(os.path.join(OUTDIR, "per_cell_results.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {OUTDIR}/judge_verdicts.json, per_cell_results.json, per_cell_results.md")
    print(f"cells: {len(cells)}  judged: {len(joined)}  TOTAL A={dict(totA)} B={dict(totB)}")


if __name__ == "__main__":
    main()

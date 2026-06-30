#!/usr/bin/env python3
"""Phase-0 measurement: generate the Arm-B briefing for a task, DETERMINISTICALLY, from the
codebase map alone. NON-RUNTIME, read-only.

Anti-bias guarantees:
- Section selection uses ONLY the task prompt vs the map's own keywords/title/responsibility.
  It never reads tasks.json `ground_truth`; no human hand-picks sections or hints answers.
- The briefing contains ONLY map-derived structural pointers (section title + anchors + tests +
  canonical_docs) + the git delta. NO responsibility prose (which can embed scalar answers; removed
  per design.md Amendment 2), NO business answer, NOT the full map.

Usage: briefing_select.py --map process/codebase-map.md --repo . --topk 3  (task prompt on stdin)
Prints the briefing to STDOUT; a selection-rationale JSON to STDERR.
"""
import json, sys, re, argparse, subprocess, os

STOP = set("the a an and or of to in on for is are be by vs with what which where how does do "
           "must should we i you it its that this these those a new add change after before "
           "name file symbol field most likely cause when run running used use".split())

def tokenize(s):
    return [w for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", s.lower()) if len(w) >= 3 and w not in STOP]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--topk", type=int, default=3)
    ap.add_argument("--prompt", default=None, help="task prompt (else read stdin)")
    args = ap.parse_args()
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()

    txt = open(os.path.join(args.repo, args.map), errors="ignore").read()
    data = json.loads(re.search(r"```json\n(.*?)\n```", txt, re.S).group(1))
    ptoks = set(tokenize(prompt))

    scored = []
    for s in data["sections"]:
        kw = set(w.lower() for k in s.get("keywords", []) for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", k.lower()))
        title_resp = set(tokenize(s.get("title", "") + " " + s.get("responsibility", "")))
        score = 3 * len(ptoks & kw) + 1 * len(ptoks & title_resp)
        if score > 0:
            scored.append((score, s["id"], s))
    scored.sort(key=lambda x: (-x[0], x[1]))
    selected = scored[: args.topk]

    # git delta since the map checkpoint
    ckpt = data.get("map_checkpoint", "")
    delta = []
    if ckpt:
        r = subprocess.run(["git", "-C", args.repo, "diff", f"{ckpt}..HEAD", "--name-only"],
                           capture_output=True, text=True)
        delta = [l for l in r.stdout.splitlines() if l.strip()]

    lines = []
    lines.append("## Codebase map briefing (read-only orientation aid — verify before relying; ignore if unhelpful)")
    lines.append(f"Selected {len(selected)} area(s) for this task from the maintained map (checkpoint {ckpt[:8]}).")
    lines.append("STRUCTURAL POINTERS ONLY (where to look) — no prose summaries, so no task answer is")
    lines.append("pre-supplied; you must open the files to answer.\n")
    for score, sid, s in selected:
        lines.append(f"### {sid} — {s.get('title','')}")
        if s.get("anchors"):
            lines.append("- anchors (jump targets): " + ", ".join(s["anchors"]))
        if s.get("tests"):
            lines.append("- tests: " + ", ".join(s["tests"]))
        if s.get("canonical_docs"):
            lines.append("- canonical docs: " + ", ".join(s["canonical_docs"]))
        lines.append("")
    if delta:
        lines.append(f"Changed since map checkpoint ({len(delta)} path(s)) — re-verify these if relevant:")
        for p in delta[:25]:
            lines.append(f"  - {p}")
        lines.append("")
    lines.append("If the right area is not above, or the task is tiny, just search the code directly.")
    briefing = "\n".join(lines)

    sys.stdout.write(briefing + "\n")
    rationale = {
        "selected": [sid for _, sid, _ in selected],
        "scores": {sid: score for score, sid, _ in selected},
        "all_nonzero_scores": {sid: score for score, sid, _ in scored},
        "briefing_bytes": len(briefing.encode("utf-8")),
        "briefing_token_estimate": round(len(briefing) / 4),
        "delta_paths": len(delta),
    }
    sys.stderr.write(json.dumps(rationale, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()

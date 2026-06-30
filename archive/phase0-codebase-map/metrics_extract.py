#!/usr/bin/env python3
"""Phase-0 measurement: parse one codex `exec --json` JSONL transcript into metrics.

NON-RUNTIME measurement tool. Read-only. No effect on the framework.

Usage: metrics_extract.py <transcript.jsonl> [--gt-entry path1 path2 ...]
Prints a JSON metrics object. --gt-entry paths (the task's ground-truth files) let it compute
`localization_step` = 1-based index of the first command that references a GT entry file.
"""
import json, sys, re, argparse, os

READ_CMDS = ("sed", "cat", "head", "tail", "less", "more", "nl", "bat")
SEARCH_CMDS = ("rg", "grep", "egrep", "ag", "ack", "find", "ls", "fd", "tree", "glob")

def classify(cmd: str):
    """Return ('read'|'search'|'other', [file_paths]) from a shell command string."""
    # strip the zsh -lc wrapper
    m = re.search(r'-lc\s+"(.*)"$', cmd, re.S) or re.search(r"-lc\s+'(.*)'$", cmd, re.S)
    inner = m.group(1) if m else cmd
    # candidate file paths: tokens with a '/' and an extension, or bare *.py/*.md etc.
    paths = re.findall(r'[A-Za-z0-9_./\-]+\.(?:py|md|json|yaml|yml|toml|sh|txt|cfg|ini|mdc|policy\.yaml)', inner)
    paths = sorted(set(p for p in paths if "/" in p or p.count(".") >= 1))
    head = inner.strip().split()[0] if inner.strip() else ""
    base = os.path.basename(head)
    # a command can chain (cmd1 && cmd2); classify by the verbs present
    verbs = set(re.findall(r'(?:^|[\s|&;])([a-z_]+)\b', inner))
    is_read = any(v in READ_CMDS for v in verbs) or base in READ_CMDS
    is_search = any(v in SEARCH_CMDS for v in verbs) or base in SEARCH_CMDS
    kind = "read" if is_read else ("search" if is_search else "other")
    return kind, paths

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--gt-entry", nargs="*", default=[])
    args = ap.parse_args()

    input_tokens = cached = output_tokens = reasoning = 0
    tool_calls = read_calls = search_calls = other_calls = 0
    files_read = set()
    cmd_output_bytes = 0
    error_count = 0
    final_answer = []
    localization_step = None
    gt_bases = [os.path.basename(p.split(":")[0]) for p in args.gt_entry]

    step = 0
    for line in open(args.transcript, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        t = e.get("type")
        if t == "error":
            error_count += 1
        elif t == "turn.completed":
            u = e.get("usage", {})
            input_tokens += u.get("input_tokens", 0)
            cached += u.get("cached_input_tokens", 0)
            output_tokens += u.get("output_tokens", 0)
            reasoning += u.get("reasoning_output_tokens", 0)
        elif t == "item.completed":
            it = e.get("item", {})
            if it.get("type") == "command_execution":
                step += 1
                tool_calls += 1
                kind, paths = classify(it.get("command", ""))
                if kind == "read":
                    read_calls += 1
                elif kind == "search":
                    search_calls += 1
                else:
                    other_calls += 1
                for p in paths:
                    files_read.add(p)
                cmd_output_bytes += len((it.get("aggregated_output", "") or "").encode("utf-8"))
                if localization_step is None and gt_bases:
                    cmdstr = it.get("command", "")
                    if any(b in cmdstr for b in gt_bases):
                        localization_step = step
            elif it.get("type") == "agent_message":
                final_answer.append(it.get("text", ""))

    out = {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning,
        "tool_calls": tool_calls,
        "read_calls": read_calls,
        "search_calls": search_calls,
        "other_calls": other_calls,
        "files_read_count": len(files_read),
        "files_read": sorted(files_read),
        "command_output_bytes": cmd_output_bytes,
        "localization_step": localization_step,
        "reconnect_errors": error_count,
        "final_answer": "\n".join(final_answer).strip(),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

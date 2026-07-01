#!/usr/bin/env python3
"""maintainer/map_briefing.py — Phase-1 autonomous codebase-map orientation entry.

MAINTAINER-ONLY, READ-ONLY, FAIL-OPEN. Fired by the harness `UserPromptSubmit` hook on a coding
task; emits a COMPACT STRUCTURAL briefing (section ids/titles + file/symbol anchors + tests + docs +
changed-path staleness) from `process/codebase-map.md`, so a fresh session inherits navigation
instead of re-scanning the repo.

HARD INVARIANTS (Phase-1 spec — do not weaken):
- READ-ONLY: reads the map + `git` metadata only; writes nothing.
- FAIL-OPEN: any error/edge (no map, malformed map, no checkpoint, git failure, unmappable task,
  exception, timeout) -> emit nothing to stdout, log an advisory to stderr, exit 0. This process
  NEVER exits nonzero and NEVER blocks a prompt or a tool.
- NO GATE: a `UserPromptSubmit` context-injector only. There is NO PreToolUse / receipt / epoch /
  mutation-ledger anywhere; it cannot deny or delay Edit/Bash/commit/subagent/worktree/cross-repo.
- NO ANSWER LEAK: structural pointers only (title/anchors/tests/docs) — NO `responsibility` prose,
  no config values, no task answers (Phase-0 Codex R1 finding).
- SMALL-TASK AWARE: trivial/continuation prompts -> emit nothing; a short single-area task -> a
  minimal pointer only.
- Not vendored to adopters (outside the vendor allowlist).

Injection format (both are official UserPromptSubmit context-injection):
  --hook claude  -> plain text on stdout (Claude injects it as context).
  --hook codex   -> JSON `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit",
                   "additionalContext": <briefing>}}` (Codex's verified injection path).
On any fail-open path we print NOTHING (no envelope) -> the harness injects nothing.

Modes:
  --hook claude|codex   parse the harness UserPromptSubmit JSON payload on stdin (field `prompt`)
  --task "TEXT"         direct task text (testing; prints the plain briefing)
  --map PATH            override map path (default <repo-root>/process/codebase-map.md)
"""
import sys, os, json, re, subprocess

TOPK = 3
MAX_BRIEFING_CHARS = 3200  # ~800 token hard cap
STOP = set("the a an and or of to in on for is are be by vs with what which where how does do "
           "must should we i you it its that this these those add change after before name file "
           "symbol field most likely cause when run running used use why implement fix".split())
CONTINUATION = re.compile(
    r"^\s*(y|yes|no|ok|okay|k|go|do it|continue|proceed|next|more|thanks|thank you|stop|cancel|"
    r"nvm|nevermind|never mind|retry|again|sure|please|yep|yeah|nope|done|good)\b[.! ]*$", re.I)


def _out(s):
    try:
        if s:
            sys.stdout.write(s if s.endswith("\n") else s + "\n")
    except Exception:
        pass


def _emit(briefing, hook_kind):
    """Emit the briefing in the harness-correct injection format. Empty briefing -> nothing."""
    if not briefing:
        return
    if hook_kind == "codex":
        try:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit", "additionalContext": briefing}}) + "\n")
            return
        except Exception:
            pass  # fall through to plain text (still fail-open)
    _out(briefing)


def _advisory(s):
    # Silent by default so no expected no-op path (missing map, trivial task, unmappable) becomes
    # prompt-loop noise if a harness surfaces hook stderr. Opt in with MAP_BRIEFING_DEBUG=1.
    if not os.environ.get("MAP_BRIEFING_DEBUG"):
        return
    try:
        sys.stderr.write("[map-briefing] " + str(s) + "\n")
    except Exception:
        pass


def _task_and_cwd(argv):
    """Return (task, cwd_hint). Never raises. cwd_hint is the hook payload's `cwd` (the real project
    dir) for hook mode — critical because inside Codex's hook sandbox os.getcwd() is NOT the repo."""
    try:
        if "--task" in argv:
            i = argv.index("--task")
            return ((argv[i + 1] if i + 1 < len(argv) else "").strip()), None
        if "--hook" in argv:
            raw = sys.stdin.read()
            data = json.loads(raw) if raw.strip() else {}
            if isinstance(data, dict):
                # UserPromptSubmit contract (Claude & Codex): {"prompt": "...", "cwd": "...", ...}
                return (str(data.get("prompt") or "").strip(),
                        (str(data.get("cwd") or "").strip() or None))
    except Exception as e:
        _advisory("payload parse failed: %r" % e)
    return "", None


def _find_map(start, override):
    """Locate process/codebase-map.md robustly: git root first, else walk up from `start` (handles a
    sandbox where git is unavailable or cwd is a subdir). Returns a path (may not exist -> fail-open)."""
    if override:
        return override
    # GIT-FREE FIRST: check `start` (the payload cwd, usually the repo root) and its parents with NO
    # subprocess. `_repo_root` (git) is called LAZILY only if this walk-up finds nothing — so when the
    # map is reachable from the payload cwd (the common case) git is NEVER invoked (R2 fix).
    d = os.path.abspath(start or ".")
    for _ in range(10):
        p = os.path.join(d, "process", "codebase-map.md")
        try:
            if os.path.exists(p):
                return p
        except Exception:
            pass
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    # last resort ONLY (reached iff the git-free walk-up found nothing): a single bounded git query
    root = _repo_root(start)
    p = os.path.join(root, "process", "codebase-map.md")
    try:
        if os.path.exists(p):
            return p
    except Exception:
        pass
    return os.path.join(os.path.abspath(start or "."), "process", "codebase-map.md")


def _opt(argv, name, default=None):
    try:
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
    except Exception:
        pass
    return default


def _repo_root(start):
    # Best-effort only; called as a LAST resort by _find_map (git may be blocked/slow in a hook
    # sandbox, so we never depend on it). Short timeout; any failure -> return `start`.
    try:
        r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return start


def _tokenize(s):
    return [w for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", (s or "").lower())
            if len(w) >= 3 and w not in STOP]


def _load_map(path):
    """Return the parsed map dict, or None on any failure (fail-open)."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        m = re.search(r"```json\s*\n(.*?)\n```", txt, re.S)
        if not m:
            return None
        data = json.loads(m.group(1))
        if isinstance(data, dict) and isinstance(data.get("sections"), list) and data["sections"]:
            return data
    except Exception as e:
        _advisory("map load failed: %r" % e)
    return None


def _select(data, task):
    """Score sections by task-keyword overlap vs the map's own keywords/title (structural fields
    only; never touches responsibility). Returns [(score, section), ...] sorted, score>0."""
    ptoks = set(_tokenize(task))
    if not ptoks:
        return []
    scored = []
    for s in data.get("sections", []):
        try:
            kw = set(w.lower() for k in s.get("keywords", [])
                     for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", str(k).lower()))
            title = set(_tokenize(s.get("title", "")))
            score = 3 * len(ptoks & kw) + 1 * len(ptoks & title)
            if score > 0:
                scored.append((score, s))
        except Exception:
            continue
    scored.sort(key=lambda x: (-x[0], str(x[1].get("id", ""))))
    return scored


def _changed_paths(root, ckpt):
    """Changed paths since the map checkpoint (for the spec-required staleness marking). This is the
    ONE git call on the hot path — it is OPTIONAL metadata: bounded to 3s and fail-open to empty on
    any failure (git blocked/slow/absent in a hook sandbox -> no staleness flags, briefing still
    emitted). Set MAP_BRIEFING_NO_GIT=1 to skip it entirely in a known git-hostile environment."""
    if not ckpt or os.environ.get("MAP_BRIEFING_NO_GIT"):
        return set()
    try:
        r = subprocess.run(["git", "-C", root, "diff", "%s..HEAD" % ckpt, "--name-only"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            return set(p for p in r.stdout.splitlines() if p.strip())
    except Exception as e:
        _advisory("git diff failed (staleness marking skipped): %r" % e)
    return set()


def _section_paths(s):
    out = []
    for k in ("covers", "tests", "canonical_docs"):
        out += [str(p) for p in s.get(k, [])]
    out += [str(a).split(":")[0] for a in s.get("anchors", [])]
    return out


def _stale(s, changed):
    if not changed:
        return False
    for p in _section_paths(s):
        if "*" in p:
            base = p.split("*")[0].rstrip("/")
            if base and any(c.startswith(base) for c in changed):
                return True
        elif p in changed:
            return True
    return False


def _render(selected, ckpt, changed, minimal):
    lines = ["## Codebase map — orientation for this task (read-only aid; verify before relying, "
             "ignore if unhelpful)"]
    lines.append("Relevant area(s) from process/codebase-map.md (checkpoint %s):" % (ckpt[:8] or "?"))
    for score, s in selected:
        sid = str(s.get("id", "?"))
        lines.append("### %s — %s" % (sid, str(s.get("title", ""))))
        anchors = [str(a) for a in s.get("anchors", [])]
        if anchors:
            lines.append("- files/symbols: " + ", ".join(anchors[:8 if not minimal else 4]))
        if not minimal:
            if s.get("tests"):
                lines.append("- tests: " + ", ".join(str(t) for t in s["tests"][:4]))
            if s.get("canonical_docs"):
                lines.append("- docs: " + ", ".join(str(d) for d in s["canonical_docs"][:4]))
        if _stale(s, changed):
            hits = [c for c in changed if c in set(_section_paths(s))][:6]
            lines.append("- ⚠ changed since checkpoint — re-verify" +
                         ((": " + ", ".join(hits)) if hits else ""))
    lines.append("(Structural pointers only — open the files to answer. If this is the wrong "
                 "area or a trivial task, just search the code directly.)")
    out = "\n".join(lines)
    return out[:MAX_BRIEFING_CHARS]


def main():
    argv = sys.argv[1:]
    hook_kind = _opt(argv, "--hook")  # 'claude' | 'codex' | None (direct --task)
    task, cwd_hint = _task_and_cwd(argv)
    if not task or CONTINUATION.match(task):
        _advisory("no substantive task; emitting nothing")
        return
    start = cwd_hint or os.getcwd()
    map_path = _find_map(start, _opt(argv, "--map"))
    root = os.path.dirname(os.path.dirname(os.path.abspath(map_path)))  # <root>/process/map.md
    data = _load_map(map_path)
    if not data:
        _advisory("map unavailable at %s; proceeding without briefing" % map_path)
        return
    selected = _select(data, task)
    if not selected:
        _advisory("task did not map to any section; proceeding without briefing")
        return
    ckpt = str(data.get("map_checkpoint") or "")
    changed = _changed_paths(root, ckpt)
    # small-task heuristic: short prompt dominated by one area -> minimal pointer
    minimal = (len(task) < 60 and (len(selected) == 1 or selected[0][0] >= 2 * selected[1][0]))
    top = selected[:1] if minimal else selected[:TOPK]
    _emit(_render(top, ckpt, changed, minimal), hook_kind)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # absolutely never propagate
        _advisory("unexpected: %r" % e)
    sys.exit(0)  # ALWAYS fail-open

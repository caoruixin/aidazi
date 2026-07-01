"""Tests for the Phase-1 autonomous codebase-map orientation entry (maintainer/map_briefing.py).

Focus: READ-ONLY, FAIL-OPEN (always exit 0, never blocks), NO answer leak, NO gate wiring,
compact, small-task aware, and NOT vendored to adopters.
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENTRY = os.path.join(REPO, "maintainer", "map_briefing.py")


def run(args, stdin=None, cwd=REPO):
    return subprocess.run([sys.executable, ENTRY] + args, input=stdin,
                          capture_output=True, text=True, cwd=cwd, timeout=30)


# ---- behavioral ----

def test_normal_task_emits_structural_briefing():
    r = run(["--task", "fix the delivery-loop driver checkpoint handling"])
    assert r.returncode == 0
    assert "codebase-map.md" in r.stdout
    assert "engine-kit/orchestrator/driver.py" in r.stdout  # correct anchor surfaced


def test_hook_claude_payload_parsed():
    payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                          "prompt": "where is git isolation strategy decided for a loop run",
                          "session_id": "s"})
    r = run(["--hook", "claude"], stdin=payload)
    assert r.returncode == 0
    assert "loop_ingress.py" in r.stdout


def test_hook_codex_emits_additionalcontext_json():
    payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                          "prompt": "add a new harness adapter what files must change"})
    r = run(["--hook", "codex"], stdin=payload)
    assert r.returncode == 0
    obj = json.loads(r.stdout)  # codex requires the JSON envelope
    assert obj["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "adapters" in obj["hookSpecificOutput"]["additionalContext"]


def test_hook_uses_payload_cwd_not_oscwd():
    # Inside Codex's hook sandbox os.getcwd() is NOT the repo; the payload `cwd` is. Simulate by
    # running from a temp dir with cwd=REPO in the payload -> map must still be found.
    with tempfile.TemporaryDirectory() as tmp:
        payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                              "prompt": "where is git isolation strategy decided for a loop run",
                              "cwd": REPO})
        r = run(["--hook", "codex"], stdin=payload, cwd=tmp)
        assert r.returncode == 0
        obj = json.loads(r.stdout)
        assert "loop_ingress.py" in obj["hookSpecificOutput"]["additionalContext"]


def test_common_path_is_git_free():
    # With git unavailable (PATH stripped), the map must still be found via payload `cwd` walk-up and
    # the briefing produced (staleness just fail-opens to empty). Proves git is not on the hot path.
    env = {k: v for k, v in os.environ.items() if k not in ("MAP_BRIEFING_DEBUG", "MAP_BRIEFING_NO_GIT")}
    env["PATH"] = "/nonexistent-dir-no-git"
    payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                          "prompt": "where is git isolation strategy decided for a loop run",
                          "cwd": REPO})
    r = subprocess.run([sys.executable, ENTRY, "--hook", "codex"], input=payload,
                       capture_output=True, text=True, cwd=REPO, env=env)
    assert r.returncode == 0
    obj = json.loads(r.stdout)
    assert "loop_ingress.py" in obj["hookSpecificOutput"]["additionalContext"]


def test_no_git_env_skips_staleness():
    env = {k: v for k, v in os.environ.items() if k != "MAP_BRIEFING_DEBUG"}
    env["MAP_BRIEFING_NO_GIT"] = "1"
    payload = json.dumps({"prompt": "driver loop state machine checkpoint", "cwd": REPO})
    r = subprocess.run([sys.executable, ENTRY, "--hook", "codex"], input=payload,
                       capture_output=True, text=True, cwd=REPO, env=env)
    assert r.returncode == 0 and r.stdout.strip()  # still emits (staleness just omitted)


def test_hook_without_cwd_falls_back_to_oscwd():
    payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                          "prompt": "acceptance load closure invariant"})
    r = run(["--hook", "codex"], stdin=payload)  # run() cwd defaults to REPO
    assert r.returncode == 0 and r.stdout.strip()  # found via os.getcwd()=REPO


# ---- FAIL-OPEN: always exit 0, empty stdout, never blocks ----

def test_fail_open_missing_map():
    r = run(["--task", "driver", "--map", "/no/such/map.md"])
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_fail_open_malformed_map():
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write("this is not a codebase map\nno json block here\n")
        bad = f.name
    try:
        r = run(["--task", "driver", "--map", bad])
        assert r.returncode == 0 and r.stdout.strip() == ""
    finally:
        os.unlink(bad)


def test_fail_open_bad_json_in_fence():
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write("```json\n{ not valid json ,,, }\n```\n")
        bad = f.name
    try:
        r = run(["--task", "driver loop", "--map", bad])
        assert r.returncode == 0 and r.stdout.strip() == ""
    finally:
        os.unlink(bad)


def test_fail_open_garbage_stdin_hook():
    r = run(["--hook", "claude"], stdin="NOT JSON {{{{")
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_fail_open_empty_stdin_hook():
    r = run(["--hook", "codex"], stdin="")
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_fail_open_no_args():
    r = run([])
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_continuation_prompt_emits_nothing():
    for p in ["yes", "continue", "ok", "do it", "proceed", "thanks"]:
        r = run(["--task", p])
        assert r.returncode == 0 and r.stdout.strip() == "", p


def test_unmappable_task_emits_nothing():
    r = run(["--task", "zzz qux frobnicate wibble"])
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_bad_checkpoint_still_succeeds():
    # a map whose checkpoint is a bogus sha -> git diff fails -> still emits (fail-open on staleness)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write('```json\n{"codebase_map_schema":1,"map_checkpoint":"deadbeefdeadbeef",'
                '"sections":[{"id":"x","title":"Driver","keywords":["driver","loop"],'
                '"anchors":["engine-kit/orchestrator/driver.py:Driver"]}]}\n```\n')
        m = f.name
    try:
        r = run(["--task", "driver loop state machine", "--map", m])
        assert r.returncode == 0
        assert "driver.py" in r.stdout  # briefing still produced despite bad checkpoint
    finally:
        os.unlink(m)


# ---- NO answer leak (structural only) ----

def test_no_answer_leak():
    r = run(["--task", "what env var enables real adapters"])
    assert r.returncode == 0
    assert "AIDAZI_ALLOW_REAL_ADAPTER" not in r.stdout   # the answer value must not appear
    assert "responsibility" not in r.stdout.lower()      # no prose field


def test_no_responsibility_prose_ever():
    r = run(["--task", "acceptance load closure invariant e2e"])
    assert "responsibility" not in r.stdout.lower()


# ---- compact + small-task aware ----

def test_briefing_is_compact():
    r = run(["--task", "add a new harness adapter what files and registration points change"])
    assert len(r.stdout) <= 3200  # ~800 token hard cap


def test_tiny_single_area_is_minimal():
    r = run(["--task", "run_loop entrypoint"])
    assert r.returncode == 0 and "run_loop.py" in r.stdout
    # minimal mode omits the tests/docs lines
    assert "\n- tests:" not in r.stdout and "\n- docs:" not in r.stdout


# ---- NO gate wiring (structural guarantee) ----

def test_no_pretooluse_in_hook_wiring():
    for rel in [".claude/settings.json", ".codex/hooks.json"]:
        cfg = json.load(open(os.path.join(REPO, rel)))
        hooks = cfg.get("hooks", {})
        assert "PreToolUse" not in hooks, rel
        assert "PostToolUse" not in hooks, rel
        assert list(hooks.keys()) == ["UserPromptSubmit"], rel


def test_hook_commands_fail_open_git_free_and_hard_timeout():
    cc = json.load(open(os.path.join(REPO, ".claude/settings.json")))
    cx = json.load(open(os.path.join(REPO, ".codex/hooks.json")))
    cc_h = cc["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    cx_h = cx["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    cc_cmd, cx_cmd = cc_h["command"], cx_h["command"]
    assert "exit 0" in cc_cmd and "exit 0" in cx_cmd            # command-level fail-open (bad exit code)
    assert "git" not in cx_cmd                                  # codex path must not depend on git
    assert "map_briefing.py" in cc_cmd and "map_briefing.py" in cx_cmd
    # HARD TIMEOUT (external to Python, not relying on the script to return):
    # Claude fail-CLOSES on a harness hook timeout -> we self-limit with a perl `alarm` command-timeout.
    assert "alarm" in cc_cmd and "perl" in cc_cmd
    # Codex fail-OPENS on a harness hook timeout (perl is unavailable in its sandbox) -> use the field.
    assert isinstance(cx_h.get("timeout"), int) and 1 <= cx_h["timeout"] <= 30


def test_advisory_silent_by_default():
    env = {k: v for k, v in os.environ.items() if k != "MAP_BRIEFING_DEBUG"}
    r = subprocess.run([sys.executable, ENTRY, "--task", "yes"], capture_output=True, text=True,
                       cwd=REPO, env=env)
    assert r.returncode == 0 and r.stderr.strip() == ""        # no-op path is silent
    env["MAP_BRIEFING_DEBUG"] = "1"
    r2 = subprocess.run([sys.executable, ENTRY, "--task", "yes"], capture_output=True, text=True,
                        cwd=REPO, env=env)
    assert r2.returncode == 0 and r2.stderr.strip() != ""      # opt-in debug is verbose


def test_fail_open_and_read_only_at_source():
    # Behavior-level guarantees (the docstring legitimately says "NO PreToolUse", so we check
    # the CODE, not the prose): the process only ever exits 0, uses git read-only, writes no files.
    src = open(ENTRY).read()
    assert "sys.exit(0)" in src
    assert "sys.exit(1)" not in src and "sys.exit(2)" not in src   # only ever exit 0 (fail-open)
    for wr in ['"commit"', '"add"', '"checkout"', '"reset"', '"push"', '"stash"', '"apply"', '"rm"']:
        assert wr not in src, wr                                    # read-only git subcommands only
    assert '"w"' not in src and "'w'" not in src and '"wb"' not in src  # no file-write opens


# ---- NOT vendored to adopters ----

def test_maintainer_artifacts_not_vendored():
    with tempfile.TemporaryDirectory() as dest:
        subprocess.run(["bash", os.path.join(REPO, "engine-kit/tools/vendor-framework.sh"),
                        REPO, dest], check=True, capture_output=True, text=True, timeout=180)
        out = os.path.join(dest, "aidazi")
        for leaked in ["maintainer", ".claude", ".codex", ".cursor",
                       "process/codebase-map.md"]:
            assert not os.path.exists(os.path.join(out, leaked)), leaked
        # sanity: the vendor DID copy the normal framework
        assert os.path.exists(os.path.join(out, "engine-kit"))
        assert os.path.exists(os.path.join(out, "AGENTS.md"))

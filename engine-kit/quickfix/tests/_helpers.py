"""Shared test helpers for the Quick-Fix runtime tests (not collected: leading '_')."""
import json
import os
import subprocess
import sys

# engine-kit on sys.path so `import quickfix.X` resolves.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# The real framework repo root (this checkout) — source of policy/schemas/kernel/lane.
FRAMEWORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"git {args} failed in {repo}: {r.stderr}")
    return r.stdout


def make_repo(root):
    os.makedirs(root, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "qf-test")
    git(root, "config", "commit.gpgsign", "false")
    # a .gitignore so verification artifacts (pycache) are ignored noise
    write(root, ".gitignore", "__pycache__/\n*.pyc\n.orchestrator/\n")
    write(root, "src/app.py", "def paginate(n):\n    return list(range(n))\n")
    write(root, "tests/test_app.py", "def test_ok():\n    assert True\n")
    commit_all(root, "init")
    return root


def write(repo, rel, content):
    p = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def commit_all(repo, msg="c"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg, "--no-verify")
    return git(repo, "rev-parse", "HEAD").strip()


def write_request(repo, request_id="fix-pag-001", harness="claude_code",
                  allowed_globs=("src/app.py",),
                  argv=("python3", "-c", "import sys; sys.exit(0)"), cwd="."):
    req = {
        "request_id": request_id,
        "created_by": "tester",
        "human_activation": True,
        "harness": harness,
        "task_summary": "restore the agreed paginate() behavior in the helper",
        "allowed_globs": list(allowed_globs),
        "eligibility_attestation": {
            "non_behavioral_or_restores_agreed_behavior": True,
            "no_new_product_semantics_or_design_choice": True,
            "no_protected_surface": True,
            "targeted_verification_available": True,
            "within_approved_scope": True,
        },
        "targeted_verification": {"argv": list(argv), "cwd": cwd},
    }
    # Outside the repo (a request file inside the repo would dirty the clean-tree gate).
    path = os.path.join(os.path.dirname(repo), f"{request_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(req, f, indent=2)
    return path


def supported_registry(harness="claude_code"):
    return {"version": 1, "harnesses": {harness: {"status": "supported"}}}


# --- fake harness (for offline adapter + CLI launch-path tests; no real CLI is run) --- #

from quickfix.adapters.base import HarnessCapability, QuickfixAdapter  # noqa: E402

# Responds to `--version` with a semver; otherwise reads the prompt from stdin and (per
# --behavior) writes --target under --worktree, sleeps (timeout test), or exits non-zero.
_FAKE_HARNESS_SRC = """#!{python}
import sys, os, time
args = sys.argv[1:]
if "--version" in args:
    sys.stdout.write("fake harness 9.9.9\\n"); sys.exit(0)
behavior, wt, target = "edit", None, "target.txt"
record_prompt = "--record-prompt" in args
for i, a in enumerate(args):
    if a == "--behavior": behavior = args[i + 1]
    if a == "--worktree": wt = args[i + 1]
    if a == "--target": target = args[i + 1]
data = sys.stdin.read()
if behavior == "sleep":
    time.sleep(30); sys.exit(0)
if behavior == "fail":
    sys.stderr.write("fake boom\\n"); sys.exit(3)
p = os.path.join(wt, target)
os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
# received_prompt.txt is written ONLY when asked (it is out-of-scope for a real request,
# so the guarded CLI path leaves it off; the adapter unit test turns it on to assert
# stdin prompt delivery against an unguarded temp worktree).
if record_prompt:
    with open(os.path.join(wt, "received_prompt.txt"), "w") as f: f.write(data)
with open(p, "w") as f: f.write("def paginate(n):\\n    return [n]\\n")
sys.stdout.write("edited\\n"); sys.exit(0)
"""


def make_fake_harness(path):
    """Write an executable fake-harness script (shebang to THIS interpreter) at ``path``."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_FAKE_HARNESS_SRC.format(python=sys.executable))
    os.chmod(path, 0o755)
    return path


class FakeHarnessAdapter(QuickfixAdapter):
    """A QuickfixAdapter whose CLI is the fake harness above — drives the real launch
    lifecycle (discover/version/Popen/timeout/evidence) offline + deterministically."""
    harness = "fake"
    MEMORY_FILENAME = "CLAUDE.md"
    MIN_VERSION = (1, 0, 0)
    PROMPT_DELIVERY = "stdin"

    def __init__(self, *, behavior="edit", target="target.txt", record_prompt=False, **kw):
        super().__init__(**kw)
        self.behavior = behavior
        self.target = target
        self.record_prompt = record_prompt

    def capability(self):
        return HarnessCapability(
            headless=True, alternate_cwd=True, worktree_write_grant=True,
            cold_start_isolation=True, isolation_mechanism="fake (test)")

    def build_argv(self, spec, executable, *, prompt):
        argv = [executable, "--behavior", self.behavior, "--worktree", spec.worktree_dir,
                "--target", self.target]
        if self.record_prompt:
            argv.append("--record-prompt")
        return argv

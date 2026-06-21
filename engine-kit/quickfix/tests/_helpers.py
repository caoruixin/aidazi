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

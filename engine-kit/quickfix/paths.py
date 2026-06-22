"""Locate the framework's Quick-Fix files inside a repo (framework repo OR adopter repo).

In the framework repo the files live at the repo root (`governance/...`, `schemas/...`,
`process/...`, `templates/...`). In an adopter repo the framework is vendored under
`aidazi/`. ``framework_root`` finds whichever holds the canonical policy; fail-closed if
neither does.
"""
from __future__ import annotations

import os

from .errors import PolicyError

_POLICY_REL = ("governance", "quickfix-protected-surfaces.policy.yaml")


def framework_root(repo_dir: str) -> str:
    repo_dir = os.path.abspath(repo_dir)
    for cand in (repo_dir, os.path.join(repo_dir, "aidazi")):
        if os.path.isfile(os.path.join(cand, *_POLICY_REL)):
            return cand
    raise PolicyError(
        f"cannot locate framework root under {repo_dir!r} "
        f"({os.path.join(*_POLICY_REL)} not found at root or aidazi/)"
    )


def fw(root: str, *parts: str) -> str:
    return os.path.join(root, *parts)


def policy_path(root: str) -> str:
    return fw(root, *_POLICY_REL)


def overlay_path(root: str) -> str:
    return fw(root, "docs", "current", "quickfix-protected-surfaces.overlay.yaml")


def baseline_schema_path(root: str) -> str:
    return fw(root, "schemas", "quickfix-protected-surfaces.schema.json")


def overlay_schema_path(root: str) -> str:
    return fw(root, "schemas", "quickfix-protected-surfaces.overlay.schema.json")


def request_schema_path(root: str) -> str:
    return fw(root, "schemas", "quickfix-request.schema.json")


def record_schema_path(root: str) -> str:
    return fw(root, "schemas", "quickfix-record.schema.json")


def kernel_path(root: str) -> str:
    return fw(root, "templates", "anti-hardcode-review-kernel.md")


def lane_spec_path(root: str) -> str:
    return fw(root, "process", "quickfix-lane.md")


def escalation_template_path(root: str) -> str:
    return fw(root, "templates", "quickfix-escalation-handoff.md")


def harness_support_path(root: str) -> str:
    return fw(root, "engine-kit", "quickfix", "harness_support.yaml")

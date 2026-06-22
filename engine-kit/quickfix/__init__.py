"""engine-kit/quickfix — Quick-Fix lane runtime (Commit 2).

Deterministic, offline, fail-closed implementation of the Quick-Fix lane specified in
process/quickfix-lane.md. The SPEC is normative; if this implementation and the spec
disagree, the spec wins and this code is the bug.

The runtime core (request load, ephemeral worktree, bundle, guard, verify, record,
harness-support registry, launcher orchestration) ships with the per-harness adapter layer
(``adapters/``). The shipped registry marks ``claude_code`` and ``codex`` ``supported`` — each
with a recorded real-launch cold-start proof
(``archive/2026-06-22-quickfix-{claude-code,codex}-e2e-evidence.md``); every other harness is
``unsupported`` and fails closed (the launch gate admits only ``supported``).
"""

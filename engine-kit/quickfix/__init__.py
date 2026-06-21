"""engine-kit/quickfix — Quick-Fix lane runtime (Commit 2).

Deterministic, offline, fail-closed implementation of the Quick-Fix lane specified in
process/quickfix-lane.md. The SPEC is normative; if this implementation and the spec
disagree, the spec wins and this code is the bug.

Commit 2 ships the runtime core (request load, ephemeral worktree, bundle, guard, verify,
record, harness-support registry, launcher orchestration) with NO real harness adapter:
the shipped registry marks every harness UNSUPPORTED, so any real harness launch fails
closed. A live harness adapter + cold-start evidence land in Commit 3.
"""

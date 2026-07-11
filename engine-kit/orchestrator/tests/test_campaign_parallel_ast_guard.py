"""Phase-4 (parallel campaign runner) — Cluster 4 AST GUARD (design §6.2).

Proof obligation: every method transitively reachable from the PARALLEL entry points
`{_drive_parallel, _handle_resume_parallel}` writes ONLY milestone_runtime[mid] +
the coordinator-GLOBAL fields — it must NEVER write a top-level SINGLETON pause/cursor
field, EXCEPT the sanctioned §3.2/§5.6 projection writers. The serial path is exempt
(it legitimately uses the singletons — it IS the untouched fast path). This statically
walks the Campaign class call graph and fails on any singleton write on the parallel
path, so a future edit that leaks per-milestone state into the singletons is caught."""
import ast
import os
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)

_CAMPAIGN_PY = os.path.join(_ORCH_DIR, "campaign.py")

# The singleton pause/cursor/overlay fields the parallel path must NOT write directly
# (design §6.2). `status`, `spent`, `units`, `milestone_outcomes`, `halt_condition_acks`,
# `engine_restamp`, `halt_condition_seq`, `gap_followup_state` are coordinator-GLOBAL (allowed).
_FORBIDDEN = frozenset({
    "pause_reason", "pause_checkpoint", "milestone_index", "subsprint_index",
    "milestone_context", "freshness_block", "halt_condition_pending",
    "halt_condition_provisional", "followup_baseline_seq", "pending_milestone_advance",
})

# The PARALLEL entry points the guard is rooted at.
_ROOTS = frozenset({"_drive_parallel", "_handle_resume_parallel"})

# SANCTIONED singleton writers (the deliberate §3.2 mirror + §5.6 global-pause projection):
# exempt from the write check AND not recursed into. `_gap_followup_round` is the shared
# coordinator-global quiescent gate (§3.4, single-writer at backlog exhaustion) — a stop leaf.
_SANCTIONED = frozenset({
    "_mirror_from_runtime", "_pause_campaign_global", "_clear_pause_parallel",
    "_consume_freshness_block_parallel", "_end_parallel", "_gap_followup_round",
})


def _load_class_methods():
    tree = ast.parse(open(_CAMPAIGN_PY, encoding="utf-8").read())
    campaign_cls = next(n for n in tree.body
                        if isinstance(n, ast.ClassDef) and n.name == "Campaign")
    return {n.name: n for n in campaign_cls.body
            if isinstance(n, ast.FunctionDef)}


def _self_calls(fn):
    """The set of self.<method>() calls in `fn` (the intra-class call edges)."""
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
            out.add(node.func.attr)
    return out


def _forbidden_writes(fn):
    """The set of FORBIDDEN singleton fields WRITTEN (Assign/AugAssign target
    `self.state.<field>`) in `fn`."""
    hits = set()

    def _is_self_state_attr(t):
        return (isinstance(t, ast.Attribute) and t.attr in _FORBIDDEN
                and isinstance(t.value, ast.Attribute) and t.value.attr == "state"
                and isinstance(t.value.value, ast.Name) and t.value.value.id == "self")

    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if _is_self_state_attr(t):
                    hits.add(t.attr)
        elif isinstance(node, ast.AugAssign):
            if _is_self_state_attr(node.target):
                hits.add(node.target.attr)
    return hits


class TestParallelAstGuard(unittest.TestCase):
    def test_no_singleton_pause_cursor_write_on_parallel_path(self):
        methods = _load_class_methods()

        # BFS the call graph from the parallel roots, NOT recursing into the sanctioned/stop set.
        reachable = set()
        frontier = list(_ROOTS)
        while frontier:
            name = frontier.pop()
            if name in reachable or name in _SANCTIONED:
                continue
            reachable.add(name)
            fn = methods.get(name)
            if fn is None:
                continue   # an injected callback / external — the coordinator passes only data
            for callee in _self_calls(fn):
                if callee not in reachable and callee not in _SANCTIONED:
                    frontier.append(callee)

        # Sanity: the guard actually reached the coordinator core (non-vacuous).
        for core in ("_dispatch_one", "_fold_ready", "_complete_milestone_parallel",
                     "_resolve_milestone_merge_parallel"):
            self.assertIn(core, reachable, f"guard did not reach {core} — call graph broke")

        violations = {}
        for name in sorted(reachable):
            fn = methods.get(name)
            if fn is None:
                continue
            hits = _forbidden_writes(fn)
            if hits:
                violations[name] = sorted(hits)
        self.assertEqual(
            violations, {},
            "parallel-reachable methods write SINGLETON pause/cursor fields (design §6.2 — "
            "route through the sanctioned writers _mirror_from_runtime / _pause_campaign_global "
            f"/ _clear_pause_parallel / _end_parallel / _consume_freshness_block_parallel): "
            f"{violations}")

    def test_serial_path_is_exempt_and_uses_singletons(self):
        # The serial path IS the untouched fast path — it legitimately writes the singletons.
        # This confirms the guard is meaningful (the fields ARE written somewhere serial).
        methods = _load_class_methods()
        serial_writes = _forbidden_writes(methods["_drive_milestones"]) \
            | _forbidden_writes(methods["_advance_milestone_cursor"])
        self.assertTrue(serial_writes, "serial path unexpectedly writes no singletons")


if __name__ == "__main__":
    unittest.main()

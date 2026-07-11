"""Deterministic run_loop test-doubles for the Phase-4 worker N=1 fold-identity canary.

Importable by a spawned worker subprocess via
``run_loop_entrypoint='_worker_canary_support:run_loop'`` (the worker inserts this dir onto
sys.path from ``worker-input.extra_sys_path``). No real Driver work — just a deterministic
summary — so serial and worker executions are byte-comparable offline."""
import os
import time


def _write_checkpoint(run_dir):
    os.makedirs(os.path.join(run_dir, "docs", "checkpoints"), exist_ok=True)


def run_loop(charter, *, run_dir, loop_id, subsprint_id, clock=None,
             resume=False, repo_dir=None, **kw):
    """Deterministic advance with a fixed spawn_count; mirrors the run_loop call shape
    ``make_run_unit`` uses (run_dir/loop_id/subsprint_id/clock/resume/repo_dir/**call_kwargs)."""
    _write_checkpoint(run_dir)
    return {"final_state": "advance", "spawn_count": 2}


def run_loop_raises(charter, *, run_dir, loop_id, subsprint_id, clock=None,
                    resume=False, repo_dir=None, **kw):
    """Raise, to exercise the worker's ``main`` error path (an OBSERVABLE error result that
    echoes the fold identity — design §5.3 / Codex C2 B-2)."""
    raise RuntimeError("canary run_loop failure")


def run_loop_blocking(charter, *, run_dir, loop_id, subsprint_id, clock=None,
                      resume=False, repo_dir=None, **kw):
    """Like ``run_loop`` but BLOCKS until a sentinel file appears (env
    ``AIDAZI_WORKER_CANARY_SENTINEL``) so a test can observe the worker holding the
    parent-inherited flock while it 'works' (design §5.5 fd-inheritance proof)."""
    _write_checkpoint(run_dir)
    sentinel = os.environ.get("AIDAZI_WORKER_CANARY_SENTINEL")
    if sentinel:
        for _ in range(3000):        # up to ~30s, then give up (test asserts timing separately)
            if os.path.exists(sentinel):
                break
            time.sleep(0.01)
    return {"final_state": "advance", "spawn_count": 2}

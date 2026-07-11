"""Phase-4 parallel campaign runner — the WORKER (design §5, Cluster 2).

A worker is a child process that executes **exactly one sub-sprint** — one
``campaign.make_run_unit(...)`` call (§5.1) — in a milestone's worktree, then writes an
**atomic, attempt-scoped** ``result-<nonce>.json`` (tmp+rename) and exits. A worker
**never reads/writes the campaign-state FILE** and **never appends the campaign ledger**
(the coordinator is the sole writer/appender, campaign.py). It receives an **immutable
coordinator-produced context** — the whole ``worker-input.json`` including the WHOLE
``requirement_context`` sidecar (§5.2), so ``run_unit`` skips its self-read of the live
campaign-state — and writes only under its own ``worker_dir``.

Liveness is a **parent-held-then-inherited ``flock``** on ``<worker_dir>/worker.lock``
(§5.5): the coordinator acquires the lock BEFORE spawning and passes the locked fd to the
child (POSIX OFD-shared across fork/exec), so a live child holds the lock from the instant
of spawn — there is no window where a live child exists unobserved. The worker also writes a
worker-OWNED lease sidecar ``worker-<nonce>.lease`` (``{pid, start_epoch, heartbeat}``) so
the single-writer discipline for campaign state is preserved (Codex R0.5 B-13).

POSIX-only (``flock``, ``fork``/fd-inheritance). The coordinator dispatch loop that CALLS
``launch_worker`` lands in Cluster 3; this module is the reusable worker + launcher, proven
by the N=1 fold-identity canary that one worker folds identically to the serial runner.
"""
import errno
import fcntl
import importlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

WORKER_INPUT_FILENAME = "worker-input.json"
LOCK_FILENAME = "worker.lock"
DEFAULT_RUN_LOOP_ENTRYPOINT = "run_loop:run_loop"
LOCK_FD_ENV = "AIDAZI_WORKER_LOCK_FD"


# --------------------------------------------------------------------------- #
# Path helpers
# --------------------------------------------------------------------------- #
def result_path(worker_dir: str, nonce: Any) -> str:
    """The attempt-scoped result path (§5.3): NOT a single reused path — a lower-nonce file is
    a stale prior attempt the coordinator ignores/archives."""
    return os.path.join(worker_dir, f"result-{nonce}.json")


def lease_path(worker_dir: str, nonce: Any) -> str:
    """The worker-OWNED lease sidecar path (§5.5)."""
    return os.path.join(worker_dir, f"worker-{nonce}.lease")


def lock_path(worker_dir: str, *, lock_name: str = LOCK_FILENAME) -> str:
    return os.path.join(worker_dir, lock_name)


def _setup_paths() -> None:
    """Insert the engine-kit dirs onto sys.path so a spawned worker resolves ``campaign`` +
    ``run_loop`` exactly as the in-process runner does (mirrors scheduling/run_loop.py)."""
    this_dir = os.path.dirname(os.path.abspath(__file__))   # engine-kit/orchestrator
    engine_kit = os.path.dirname(this_dir)                   # engine-kit/
    for p in (this_dir, engine_kit,
              os.path.join(engine_kit, "audit"),
              os.path.join(engine_kit, "scheduling"),
              os.path.join(engine_kit, "validators")):
        if p not in sys.path:
            sys.path.insert(0, p)


# --------------------------------------------------------------------------- #
# Clock policy + run_loop resolution (worker reconstructs both from the input)
# --------------------------------------------------------------------------- #
def _wallclock_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clock_from_policy(policy: Optional[dict]) -> Callable[[], str]:
    """Reconstruct the worker clock from an explicit POLICY (§5.1 — the same injected clock the
    coordinator uses, so wall-clock accounting agrees). 'wallclock' = real UTC-ISO; 'fixed' =
    a constant timestamp (deterministic canary). Fail-closed on an unknown kind."""
    policy = policy or {}
    kind = policy.get("kind", "wallclock")
    if kind == "wallclock":
        return _wallclock_iso
    if kind == "fixed":
        value = policy.get("value")
        if not isinstance(value, str):
            raise ValueError("clock policy kind 'fixed' requires a string 'value'")
        return lambda: value
    raise ValueError(f"unknown worker clock policy kind {kind!r} (fail-closed)")


def _resolve_run_loop(entrypoint: str) -> Callable:
    """Resolve ``run_loop_fn`` from a 'module:attr' entrypoint (§5.1 — the worker resolves it
    from the same module entrypoint the CLI uses; default ``run_loop:run_loop``)."""
    mod_name, sep, attr = (entrypoint or "").partition(":")
    if not mod_name or not sep or not attr:
        raise ValueError(
            f"run_loop_entrypoint must be 'module:attr', got {entrypoint!r} (fail-closed)")
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, attr, None)
    if not callable(fn):
        raise ValueError(
            f"run_loop_entrypoint {entrypoint!r} did not resolve to a callable (fail-closed)")
    return fn


# --------------------------------------------------------------------------- #
# Worker-input contract (§5.1) — full enumeration incl. clock + the WHOLE sidecar
# --------------------------------------------------------------------------- #
def _validate_worker_input(wi: dict) -> None:
    """Fail-closed guard on a worker-input (Codex C2 B-1). A WORKER dispatch is a real parallel
    sub-sprint, so its input MUST be complete AND must NEVER be able to fall into ``run_unit``'s
    serial self-read of the live campaign-state.json. Enforced:
      * ``dispatch.subsprint_id`` + ``dispatch.milestone_id`` present;
      * ``dispatch.subsprint_sequence`` is a non-empty list CONTAINING ``subsprint_id`` — this is
        what makes ``run_unit`` take the derived-context branch that PINS
        ``loop_mode=delivery_only`` and anchors this milestone's Acceptance gate (skipping it
        would mis-anchor terminality);
      * ``attempt_nonce`` is an integer (the fold key component, §5.3);
      * ``dispatch_epoch`` is non-empty (the signed-scope epoch re-checked on every fold, §5.6);
      * ``requirement_context`` is present for a LEDGER-WIRED campaign (``plan`` + ``ledger_path``)
        so the worker never self-reads campaign-state (§5.2). A genuinely non-ledger campaign
        legitimately carries ``None`` — serial writes no sidecar either ⇒ byte-identical."""
    d = wi.get("dispatch") or {}
    sid = d.get("subsprint_id")
    errs: List[str] = []
    if not sid:
        errs.append("dispatch.subsprint_id is required")
    if not d.get("milestone_id"):
        errs.append("dispatch.milestone_id is required")
    seq = d.get("subsprint_sequence")
    if not isinstance(seq, list) or not seq or sid not in seq:
        errs.append("dispatch.subsprint_sequence must be a non-empty list containing "
                    "subsprint_id (pins loop_mode=delivery_only + anchors the Acceptance gate)")
    if not isinstance(wi.get("attempt_nonce"), int):
        errs.append("attempt_nonce must be an integer (the fold key component, §5.3)")
    if not wi.get("dispatch_epoch"):
        errs.append("dispatch_epoch is required (the signed-scope epoch re-checked on fold, §5.6)")
    if wi.get("plan") is not None and wi.get("ledger_path") \
            and wi.get("requirement_context") is None:
        errs.append("requirement_context is required for a ledger-wired worker so it never "
                    "self-reads campaign-state.json (§5.2)")
    if errs:
        raise ValueError("invalid worker-input (fail-closed): " + "; ".join(errs))


def build_worker_input(*, campaign_id: str, units_dir: str, charter: dict,
                       dispatch: dict, attempt_nonce: Any,
                       plan: Optional[dict] = None, ledger_path: Optional[str] = None,
                       run_loop_kwargs: Optional[dict] = None,
                       run_loop_entrypoint: str = DEFAULT_RUN_LOOP_ENTRYPOINT,
                       clock: Optional[dict] = None,
                       extra_sys_path: Optional[List[str]] = None,
                       requirement_context: Optional[dict] = None,
                       dispatch_epoch: Optional[str] = None) -> dict:
    """Assemble the immutable ``worker-input.json`` the coordinator hands a worker (§5.1). Every
    ``make_run_unit``/``run_unit`` input is carried explicitly — including the ``clock`` policy,
    the ``attempt_nonce``, the ``dispatch_epoch``, and the coordinator-produced WHOLE
    ``requirement_context`` sidecar (the worker does NOT build it from state). ``dispatch`` holds
    the per-sub-sprint call args (subsprint_id + milestone_id + subsprint_sequence required;
    resume / functional_acceptance / repo_dir / covered_req_ids / gap_followup_spec /
    milestone_signals optional). Fail-closed via ``_validate_worker_input`` (Codex C2 B-1) so an
    incomplete dispatch can never reach a worker. Pure — no I/O."""
    wi = {
        "campaign_id": campaign_id,
        "units_dir": units_dir,
        "charter": charter,
        "plan": plan,
        "ledger_path": ledger_path,
        "run_loop_kwargs": dict(run_loop_kwargs or {}),
        "run_loop_entrypoint": run_loop_entrypoint,
        "clock": dict(clock) if clock else {"kind": "wallclock"},
        "extra_sys_path": list(extra_sys_path or []),
        "requirement_context": requirement_context,
        "dispatch": dict(dispatch),
        "attempt_nonce": attempt_nonce,
        "dispatch_epoch": dispatch_epoch,
    }
    _validate_worker_input(wi)
    return wi


def _atomic_write_json(path: str, obj: Any) -> None:
    """tmp + os.replace atomic write (§5.3/§5.4 — a partial result must never be foldable)."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def write_worker_input(worker_dir: str, worker_input: dict) -> str:
    os.makedirs(worker_dir, exist_ok=True)
    path = os.path.join(worker_dir, WORKER_INPUT_FILENAME)
    _atomic_write_json(path, worker_input)
    return path


def read_worker_input(worker_dir: str) -> dict:
    with open(os.path.join(worker_dir, WORKER_INPUT_FILENAME), encoding="utf-8") as fh:
        return json.load(fh)


def _write_lease(worker_dir: str, nonce: Any, *, pid: int, start_epoch: str,
                 phase: str, heartbeat: str) -> None:
    """Worker-OWNED lease sidecar (§5.5) — single-writer state preserved (the coordinator writes
    campaign-state, the worker writes ONLY this lease). Carries pid/start_epoch for the C4
    adopt/fence; ``phase`` records running→done for observability."""
    _atomic_write_json(lease_path(worker_dir, nonce),
                       {"pid": pid, "start_epoch": start_epoch,
                        "heartbeat": heartbeat, "phase": phase})


# --------------------------------------------------------------------------- #
# The worker body — execute ONE sub-sprint, write an atomic attempt-scoped result
# --------------------------------------------------------------------------- #
def run_worker(worker_dir: str) -> dict:
    """Execute the single sub-sprint described by ``<worker_dir>/worker-input.json`` and write
    the atomic attempt-scoped ``result-<nonce>.json`` (§5.1/§5.3). Returns the result envelope.
    In-process (the subprocess ``main`` just calls this) so it is directly unit-testable."""
    _setup_paths()
    import campaign  # after sys.path setup

    wi = read_worker_input(worker_dir)
    _validate_worker_input(wi)   # defense-in-depth: also validated at build time (C2 B-1)
    for p in (wi.get("extra_sys_path") or []):
        if p and p not in sys.path:
            sys.path.insert(0, p)

    nonce = wi["attempt_nonce"]
    pid = os.getpid()
    start = _wallclock_iso()
    _write_lease(worker_dir, nonce, pid=pid, start_epoch=start,
                 phase="running", heartbeat=start)

    run_loop_fn = _resolve_run_loop(
        wi.get("run_loop_entrypoint") or DEFAULT_RUN_LOOP_ENTRYPOINT)
    clock = _clock_from_policy(wi.get("clock"))

    run_unit = campaign.make_run_unit(
        wi["charter"], wi["units_dir"], wi["campaign_id"], clock=clock,
        plan=wi.get("plan"), run_loop_fn=run_loop_fn,
        ledger_path=wi.get("ledger_path"), **(wi.get("run_loop_kwargs") or {}))

    d = wi["dispatch"]
    result = run_unit(
        d["subsprint_id"], milestone_id=d.get("milestone_id"),
        subsprint_sequence=d.get("subsprint_sequence"),
        resume=bool(d.get("resume", False)),
        functional_acceptance=d.get("functional_acceptance"),
        repo_dir=d.get("repo_dir"), covered_req_ids=d.get("covered_req_ids"),
        gap_followup_spec=d.get("gap_followup_spec"),
        milestone_signals=d.get("milestone_signals"),
        requirement_context=wi.get("requirement_context"))

    # The result ECHOES the fold-key identity (attempt_nonce + milestone/subsprint +
    # dispatch_epoch) so the coordinator folds only the LIVE attempt (§5.3) and re-checks the
    # dispatch epoch on fold (§5.6). run_unit already returns loop_id inside `result`.
    out = {"attempt_nonce": nonce, "milestone_id": d.get("milestone_id"),
           "subsprint_id": d["subsprint_id"], "dispatch_epoch": wi.get("dispatch_epoch"),
           "result": result}
    _atomic_write_json(result_path(worker_dir, nonce), out)
    _write_lease(worker_dir, nonce, pid=pid, start_epoch=start,
                 phase="done", heartbeat=_wallclock_iso())
    return out


# --------------------------------------------------------------------------- #
# Launcher — parent-locks-BEFORE-fork, child inherits the OFD lock (§5.5)
# --------------------------------------------------------------------------- #
def launch_worker(worker_dir: str, *, python_exe: Optional[str] = None,
                  lock_name: str = LOCK_FILENAME,
                  extra_env: Optional[Dict[str, str]] = None) -> "subprocess.Popen":
    """Spawn a worker for the ``worker-input.json`` already written under ``worker_dir``, with the
    parent-held ``flock`` INHERITED by the child (§5.5): the parent (1) acquires ``LOCK_EX`` on
    ``<worker_dir>/<lock_name>`` BEFORE spawn, (2) spawns the worker with that fd passed
    (``pass_fds`` clears close-on-exec so the POSIX OFD lock is shared from the instant of
    spawn), (3) closes its OWN copy of the fd so the child SOLELY holds the lock until it dies
    (the OS releases it on process death). There is no window where a live child exists without
    holding the lock. POSIX-only; the coordinator writes the durable pre-spawn ``inflight``
    BEFORE calling this (Cluster 3)."""
    python_exe = python_exe or sys.executable
    lp = lock_path(worker_dir, lock_name=lock_name)
    os.makedirs(worker_dir, exist_ok=True)
    lock_fd = os.open(lp, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)   # parent locks BEFORE spawn
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        env[LOCK_FD_ENV] = str(lock_fd)
        proc = subprocess.Popen(
            [python_exe, os.path.abspath(__file__), worker_dir],
            pass_fds=(lock_fd,), env=env, close_fds=True)
    finally:
        # Drop the parent's copy: on success the child solely holds the OFD lock; on a spawn
        # failure the lock is released (no child) — either way the parent holds no stray lock.
        os.close(lock_fd)
    return proc


def worker_lock_held(worker_dir: str, *, lock_name: str = LOCK_FILENAME) -> bool:
    """Probe (§5.5 crash-recovery): True iff a LIVE worker holds the flock — a non-blocking
    ``LOCK_EX`` that fails (EWOULDBLOCK) means a live child holds it (⇒ adopt); success means no
    live holder (⇒ fence/redispatch). Never leaves a lock held (immediately unlocks on success)."""
    lp = lock_path(worker_dir, lock_name=lock_name)
    if not os.path.exists(lp):
        return False
    fd = os.open(lp, os.O_RDWR)
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                return False   # acquired ⇒ NO live holder (fence/redispatch)
            except OSError as exc:
                if exc.errno == errno.EINTR:
                    continue   # interrupted syscall — retry, do not misread as "held"
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
                    return True   # a LIVE worker holds it (adopt)
                raise   # unexpected (EBADF/EIO/…) — fail closed, never GUESS "live" (Codex C2 B-3)
    finally:
        os.close(fd)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        sys.stderr.write("usage: campaign_worker.py <worker_dir>\n")
        return 2
    worker_dir = argv[0]
    try:
        run_worker(worker_dir)
        return 0
    except Exception as exc:  # noqa: BLE001 — record an OBSERVABLE error result, then fail
        # Write an error result the coordinator can see (crash w/o result ⇒ C4 fence/redispatch;
        # a written error result lets the coordinator surface the failure instead of a silent
        # stall). Best-effort — never mask the original traceback.
        try:
            _setup_paths()
            wi = read_worker_input(worker_dir)
            nonce = wi.get("attempt_nonce")
            if nonce is not None:
                # Echo the SAME fold-key identity as a success result (Codex C2 B-2) so the
                # Cluster-3 fold/surface logic can bind a worker EXCEPTION to its attempt.
                d = wi.get("dispatch") or {}
                _atomic_write_json(
                    result_path(worker_dir, nonce),
                    {"attempt_nonce": nonce, "milestone_id": d.get("milestone_id"),
                     "subsprint_id": d.get("subsprint_id"),
                     "dispatch_epoch": wi.get("dispatch_epoch"),
                     "error": f"{type(exc).__name__}: {exc}", "result": None})
        except Exception:  # noqa: BLE001
            pass
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

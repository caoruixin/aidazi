#!/usr/bin/env python3
"""bounded headless review runner — safe ad-hoc Codex/Kimi review invocation.

WHY THIS EXISTS
---------------
During framework development we call a headless reviewer (``codex exec``, a Kimi CLI, …)
to get an independent verdict. Two stall modes have bitten ad-hoc calls:

  1. **stdin block** — ``codex exec`` with no positional prompt reads instructions from
     stdin and waits for EOF; "if stdin is piped and a prompt is also provided, stdin is
     appended as a ``<stdin>`` block". Launched in the background with stdin left open, it
     hangs forever on "Reading additional input from stdin...".
  2. **gateway/API hang** — the request is accepted but the provider never streams a
     response; ``codex exec`` has **no ``--timeout`` flag**, so it waits unbounded.

The Quick-Fix adapter already handles both for the QF lane. This runner gives the SAME
process-control guarantees to ad-hoc dev-review calls, as a STANDALONE tool: it reuses the
verified PATTERN (``Popen`` + ``start_new_session`` + process-GROUP kill) but does NOT import
or depend on the Quick-Fix runtime contract.

GUARANTEES (every run)
  * structured ``argv``; ``shell=False``; no shell string is ever built;
  * stdin is fed via a write-then-close (``prompt_delivery='stdin'``) or fully closed
    (``DEVNULL``, ``prompt_delivery='none'``) — the child can never block reading stdin, and
    no open parent tty/pipe is inherited on stdin;
  * the child runs in its OWN session/group (``start_new_session=True``) so a timeout kills
    the WHOLE group — no residual children;
  * a **hard wall-clock timeout** is the final boundary (the CLI under test has none);
  * stdout/stderr are captured;
  * with ``--json`` (codex JSONL events) the runner detects **inactivity** — but inactivity is
    a SOFT warning ONLY; it never kills. Only the hard timeout kills.

ATTEMPTS / GATE DISCIPLINE
  * bounded attempts (default 2, hard cap); the SAME provider/path is never retried beyond
    that — no infinite retry;
  * every attempt is recorded (the first failure is never hidden);
  * for a MANDATORY gate, two failures => ``stop_and_surface`` (the caller MUST surface; the
    runner never silently skips a mandatory gate);
  * an alternative reviewer is used ONLY when one was explicitly pre-allowed, and the
    substitution is recorded.

SECRETS
  * env is NEVER recorded; tokens/credentials are NEVER logged. Only argv (which carries no
    secret here), versions, exit code, timing, and captured stdout/stderr are kept.

CLI
    python review_runner.py [--timeout S] [--inactivity-warn S] [--attempts N]
        [--mandatory] [--prompt-file F | --no-stdin] [--capture-dir D]
        [--allow-alternative -- <alt argv...>] -- <command argv...>

    The command after the FIRST ``--`` is the reviewer invocation (e.g.
    ``codex exec --json -o /tmp/v.txt -m gpt-5.5 -s read-only --skip-git-repo-check``).
    The prompt (``--prompt-file``) is delivered on stdin and stdin is then CLOSED.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence

# Hard ceiling on attempts regardless of caller input — a runaway-retry backstop.
MAX_ATTEMPTS_CAP = 2

#: outcomes a single attempt can have.
SUCCESS = "success"
NONZERO_EXIT = "nonzero_exit"
TIMEOUT = "timeout"
LAUNCH_ERROR = "launch_error"

#: overall run statuses.
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_STOP_AND_SURFACE = "stop_and_surface"
STATUS_SUBSTITUTED = "substituted"


@dataclass
class AttemptRecord:
    """One bounded launch attempt. No env, no secrets — argv only."""
    attempt: int
    argv: List[str]
    prompt_delivery: str
    outcome: str
    exit_code: Optional[int]
    timed_out: bool
    duration_s: float
    stdout_bytes: int
    stderr_bytes: int
    inactivity_warnings: int
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunResult:
    status: str
    attempts: List[AttemptRecord] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    last_message: Optional[str] = None
    substituted_with: Optional[List[str]] = None

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_SUCCESS, STATUS_SUBSTITUTED)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Keep the persisted summary compact + secret-free: drop the full text bodies.
        d.pop("stdout", None)
        d.pop("stderr", None)
        d["stdout_bytes"] = len(self.stdout.encode("utf-8"))
        d["stderr_bytes"] = len(self.stderr.encode("utf-8"))
        return d


# --------------------------------------------------------------------------- #
# Single bounded launch.
# --------------------------------------------------------------------------- #
def run_once(
    argv: Sequence[str],
    *,
    prompt: Optional[str] = None,
    prompt_delivery: str = "stdin",
    hard_timeout_s: float,
    inactivity_warn_s: Optional[float] = None,
    attempt: int = 1,
    on_warn=None,
) -> AttemptRecord:
    """Launch ``argv`` once with the full safety wrapper and return an AttemptRecord.

    ``prompt_delivery``:
      * ``'stdin'`` — write ``prompt`` to the child's stdin then CLOSE it (EOF).
      * ``'none'``  — stdin is ``DEVNULL`` (use when the prompt is an argv token).

    Inactivity (no new stdout/stderr byte for ``inactivity_warn_s``) emits a SOFT warning via
    ``on_warn`` and increments the counter; it NEVER terminates the child. Only
    ``hard_timeout_s`` terminates (whole process group)."""
    if prompt_delivery not in ("stdin", "none"):
        raise ValueError(f"prompt_delivery must be 'stdin' or 'none', got {prompt_delivery!r}")
    argv = list(argv)
    stdin_mode = subprocess.PIPE if prompt_delivery == "stdin" else subprocess.DEVNULL

    out_buf: List[str] = []
    err_buf: List[str] = []
    last_activity = [time.monotonic()]
    activity_lock = threading.Lock()

    def _pump(stream, buf):
        try:
            for line in iter(stream.readline, ""):
                buf.append(line)
                with activity_lock:
                    last_activity[0] = time.monotonic()
        except (ValueError, OSError):
            pass  # stream closed during teardown
        finally:
            try:
                stream.close()
            except OSError:
                pass

    start = time.monotonic()
    try:
        proc = subprocess.Popen(  # noqa: S603 - structured argv, shell=False
            argv,
            stdin=stdin_mode,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,  # own process group -> group kill on timeout
            close_fds=True,
        )
    except OSError as exc:
        return AttemptRecord(
            attempt=attempt, argv=argv, prompt_delivery=prompt_delivery,
            outcome=LAUNCH_ERROR, exit_code=None, timed_out=False,
            duration_s=round(time.monotonic() - start, 3),
            stdout_bytes=0, stderr_bytes=0, inactivity_warnings=0,
            note=f"failed to launch: {exc}",
        )

    # Capture the process-GROUP id NOW, while the child (a session/group leader via
    # start_new_session) is alive — after it is reaped, os.getpgid(pid) would fail, and we
    # still need the group id to reap any grandchild that outlives the leader.
    try:
        saved_pgid = os.getpgid(proc.pid)
    except OSError:
        saved_pgid = proc.pid  # start_new_session => the child pid IS the group id

    t_out = threading.Thread(target=_pump, args=(proc.stdout, out_buf), daemon=True)
    t_err = threading.Thread(target=_pump, args=(proc.stderr, err_buf), daemon=True)
    t_out.start()
    t_err.start()

    # Feed the prompt then CLOSE stdin so the child gets EOF and never blocks on a read.
    # Do it in a DAEMON thread: a large prompt to a child that never drains stdin would block
    # write()/close() — doing that on the main thread would stall the watchdog and the hard
    # timeout would never fire. On a kill the pipe breaks and this thread unblocks and exits.
    def _write_stdin() -> None:
        try:
            if prompt:
                proc.stdin.write(prompt)
        except (BrokenPipeError, ValueError, OSError):
            pass
        finally:
            # ALWAYS close stdin (even if write() raised) so the pipe fd is released promptly
            # and the child reaches EOF — never left dangling until GC (ResourceWarning).
            try:
                proc.stdin.close()
            except (BrokenPipeError, ValueError, OSError):
                pass

    if prompt_delivery == "stdin" and proc.stdin is not None:
        threading.Thread(target=_write_stdin, daemon=True).start()

    timed_out = False
    inactivity_warnings = 0
    warned_window = -1.0
    poll_interval = 0.05
    while proc.poll() is None:
        now = time.monotonic()
        if now - start >= hard_timeout_s:
            timed_out = True
            break
        if inactivity_warn_s and inactivity_warn_s > 0:
            with activity_lock:
                idle = now - last_activity[0]
            # Emit at most one warning per inactivity window (throttled), never kill.
            if idle >= inactivity_warn_s and (now - warned_window) >= inactivity_warn_s:
                inactivity_warnings += 1
                warned_window = now
                if on_warn:
                    on_warn(attempt, round(idle, 1))
        time.sleep(poll_interval)

    # ALWAYS tear down the whole group — on a timeout (kill the hung child) AND on a clean
    # leader exit (reap any grandchild still holding the pipes, which also unblocks the readers
    # so they reach EOF). Harmless if the group is already gone.
    _kill_group(saved_pgid)
    t_out.join(timeout=10)
    t_err.join(timeout=10)
    try:
        exit_code: Optional[int] = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        exit_code = None
    duration_s = round(time.monotonic() - start, 3)

    stdout = "".join(out_buf)
    stderr = "".join(err_buf)
    if timed_out:
        outcome = TIMEOUT
    elif exit_code == 0:
        outcome = SUCCESS
    else:
        outcome = NONZERO_EXIT

    rec = AttemptRecord(
        attempt=attempt, argv=argv, prompt_delivery=prompt_delivery, outcome=outcome,
        exit_code=exit_code, timed_out=timed_out, duration_s=duration_s,
        stdout_bytes=len(stdout.encode("utf-8")), stderr_bytes=len(stderr.encode("utf-8")),
        inactivity_warnings=inactivity_warnings,
    )
    # Attach the captured text out-of-band (not in the dataclass record, which is the
    # secret-free audit row).
    rec._stdout = stdout  # type: ignore[attr-defined]
    rec._stderr = stderr  # type: ignore[attr-defined]
    return rec


def _kill_group(pgid: int) -> None:
    """Terminate the WHOLE process group ``pgid`` (SIGTERM, brief grace, then SIGKILL).

    Operates on the saved group id (not ``proc.pid``, which can no longer be mapped to a
    group once the leader is reaped) so a grandchild that outlived the leader is still reaped.
    A no-op if the group is already gone."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return
    for _ in range(20):  # up to ~1s grace for the group to exit on its own
        time.sleep(0.05)
        try:
            os.killpg(pgid, 0)  # signal 0 = liveness probe; raises if the group is empty
        except (ProcessLookupError, OSError):
            return  # group gone
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        return


# --------------------------------------------------------------------------- #
# Bounded, gate-aware orchestration.
# --------------------------------------------------------------------------- #
def run_bounded(
    argv: Sequence[str],
    *,
    prompt: Optional[str] = None,
    prompt_delivery: str = "stdin",
    hard_timeout_s: float,
    inactivity_warn_s: Optional[float] = None,
    attempts: int = 2,
    mandatory: bool = False,
    alternative_argv: Optional[Sequence[str]] = None,
    on_warn=None,
    on_attempt=None,
) -> RunResult:
    """Run ``argv`` up to ``attempts`` (capped at 2) times with the safety wrapper.

    Returns a :class:`RunResult`. Discipline:
      * stop at the first SUCCESS;
      * never exceed ``min(attempts, MAX_ATTEMPTS_CAP)`` runs of the SAME path;
      * if all attempts fail and ``alternative_argv`` was pre-allowed, run it ONCE and mark
        the result ``substituted``;
      * else if ``mandatory``, return ``stop_and_surface`` (NEVER silently skip);
      * else return ``failed``.
    """
    # An alternative IDENTICAL to the primary would just be a third run of the SAME path,
    # defeating the cap and the no-infinite-retry rule. Reject it (the caller must supply a
    # genuinely different reviewer/provider).
    if alternative_argv is not None and list(alternative_argv) == list(argv):
        raise ValueError(
            "alternative_argv is identical to the primary argv; an alternative must be a "
            "DIFFERENT reviewer/path (else it is just a third retry of the same path).")

    n = max(1, min(int(attempts), MAX_ATTEMPTS_CAP))
    records: List[AttemptRecord] = []
    last_stdout = last_stderr = ""

    for i in range(1, n + 1):
        rec = run_once(
            argv, prompt=prompt, prompt_delivery=prompt_delivery,
            hard_timeout_s=hard_timeout_s, inactivity_warn_s=inactivity_warn_s,
            attempt=i, on_warn=on_warn,
        )
        records.append(rec)
        last_stdout = getattr(rec, "_stdout", "")
        last_stderr = getattr(rec, "_stderr", "")
        if on_attempt:
            on_attempt(rec)
        if rec.outcome == SUCCESS:
            return RunResult(
                status=STATUS_SUCCESS, attempts=records,
                stdout=last_stdout, stderr=last_stderr,
            )

    # All same-path attempts failed. Try a PRE-ALLOWED alternative exactly once.
    if alternative_argv:
        alt = run_once(
            alternative_argv, prompt=prompt, prompt_delivery=prompt_delivery,
            hard_timeout_s=hard_timeout_s, inactivity_warn_s=inactivity_warn_s,
            attempt=len(records) + 1, on_warn=on_warn,
        )
        records.append(alt)
        if on_attempt:
            on_attempt(alt)
        if alt.outcome == SUCCESS:
            return RunResult(
                status=STATUS_SUBSTITUTED, attempts=records,
                stdout=getattr(alt, "_stdout", ""), stderr=getattr(alt, "_stderr", ""),
                substituted_with=list(alternative_argv),
            )
        last_stdout = getattr(alt, "_stdout", last_stdout)
        last_stderr = getattr(alt, "_stderr", last_stderr)

    status = STATUS_STOP_AND_SURFACE if mandatory else STATUS_FAILED
    return RunResult(status=status, attempts=records, stdout=last_stdout, stderr=last_stderr)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _split_command(argv: List[str]) -> tuple[List[str], List[str], List[str]]:
    """Split CLI args at ``--`` markers: (runner_args, command, alternative).

    The FIRST ``--`` separates runner options from the command. A SECOND ``--`` is treated as
    the command/alternative separator ONLY when ``--allow-alternative`` is among the runner
    options — otherwise the entire tail (including any literal ``--`` the reviewer command needs)
    is the command, so a wrapped command's own ``--`` is never mis-parsed as an alternative.
    """
    if "--" not in argv:
        return argv, [], []
    idx = argv.index("--")
    runner_args = argv[:idx]
    rest = argv[idx + 1:]
    if "--allow-alternative" in runner_args and "--" in rest:
        j = rest.index("--")
        return runner_args, rest[:j], rest[j + 1:]
    return runner_args, rest, []


def main(argv: Optional[List[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    runner_args, command, alternative = _split_command(raw)

    parser = argparse.ArgumentParser(
        description="Bounded headless review runner (hard timeout + process-group kill + "
        "bounded attempts). The reviewer command follows a `--`.",
    )
    parser.add_argument("--timeout", type=float, required=True,
                        help="HARD wall-clock timeout in seconds (the final boundary)")
    parser.add_argument("--inactivity-warn", type=float, default=None,
                        help="seconds of stdout/stderr silence that emit a SOFT warning "
                        "(never kills; use with codex --json)")
    parser.add_argument("--attempts", type=int, default=2,
                        help=f"bounded attempts of the same path (capped at {MAX_ATTEMPTS_CAP})")
    parser.add_argument("--mandatory", action="store_true",
                        help="this is a mandatory gate: two failures => stop_and_surface "
                        "(exit 3), never silently skipped")
    parser.add_argument("--prompt-file", default=None,
                        help="file whose contents are fed to the child on stdin, then stdin "
                        "is CLOSED (default delivery)")
    parser.add_argument("--no-stdin", action="store_true",
                        help="run with stdin=DEVNULL (use when the prompt is an argv token)")
    parser.add_argument("--capture-dir", default=None,
                        help="dir to write stdout.txt / stderr.txt / attempts.json")
    parser.add_argument("--allow-alternative", action="store_true",
                        help="a SECOND `--`-separated command may run if the primary fails")
    args = parser.parse_args(runner_args)

    if not command:
        parser.error("no reviewer command given; put it after `--`")
    if args.allow_alternative and not alternative:
        parser.error("--allow-alternative set but no alternative command after the second `--`")
    if alternative and not args.allow_alternative:
        parser.error("an alternative command was given but --allow-alternative was not set")
    if alternative and list(alternative) == list(command):
        parser.error("the alternative command is identical to the primary; an alternative must "
                     "be a DIFFERENT reviewer/path (not a third retry of the same path)")

    prompt = None
    delivery = "none" if args.no_stdin else "stdin"
    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as fh:
            prompt = fh.read()
        delivery = "stdin"

    def _warn(attempt: int, idle: float) -> None:
        sys.stderr.write(f"[review_runner] attempt {attempt}: no output for {idle}s "
                         f"(soft warning; hard timeout at {args.timeout}s)\n")
        sys.stderr.flush()

    def _attempt(rec: AttemptRecord) -> None:
        sys.stderr.write(f"[review_runner] attempt {rec.attempt}: {rec.outcome} "
                         f"(exit={rec.exit_code}, {rec.duration_s}s, "
                         f"warnings={rec.inactivity_warnings})\n")
        sys.stderr.flush()

    result = run_bounded(
        command, prompt=prompt, prompt_delivery=delivery,
        hard_timeout_s=args.timeout, inactivity_warn_s=args.inactivity_warn,
        attempts=args.attempts, mandatory=args.mandatory,
        alternative_argv=alternative or None, on_warn=_warn, on_attempt=_attempt,
    )

    if args.capture_dir:
        _write_captures(args.capture_dir, result)

    # Echo the reviewer's stdout so the caller sees the verdict.
    sys.stdout.write(result.stdout)
    sys.stderr.write(f"[review_runner] status={result.status} "
                     f"attempts={len(result.attempts)}"
                     + (f" substituted_with={result.substituted_with}"
                        if result.substituted_with else "") + "\n")

    if result.status == STATUS_SUCCESS:
        return 0
    if result.status == STATUS_SUBSTITUTED:
        return 0
    if result.status == STATUS_STOP_AND_SURFACE:
        return 3  # distinct: a MANDATORY gate failed and must be surfaced, not skipped
    return 1


def _write_captures(capture_dir: str, result: RunResult) -> None:
    import json
    os.makedirs(capture_dir, exist_ok=True)
    with open(os.path.join(capture_dir, "stdout.txt"), "w", encoding="utf-8") as fh:
        fh.write(result.stdout)
    with open(os.path.join(capture_dir, "stderr.txt"), "w", encoding="utf-8") as fh:
        fh.write(result.stderr)
    with open(os.path.join(capture_dir, "attempts.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {"status": result.status,
             "substituted_with": result.substituted_with,
             "attempts": [a.to_dict() for a in result.attempts]},
            fh, indent=2, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    sys.exit(main())

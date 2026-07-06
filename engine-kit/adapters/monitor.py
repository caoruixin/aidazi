#!/usr/bin/env python3
"""Lightweight sidecar monitor for real agent subprocesses.

This is deliberately small and adapter-local: it observes a spawned CLI process,
records obvious "looks stuck" evidence under .orchestrator/diagnostics/, and gives
the adapter one quick retry. It does not participate in Delivery Loop semantics.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence


class AgentStuckError(subprocess.SubprocessError):
    """Raised after the sidecar monitor exhausts its restart budget."""


@dataclass(frozen=True)
class MonitorConfig:
    no_output_seconds: float = 180.0
    idle_cpu_seconds: float = 180.0
    max_stuck_seconds: float = 300.0
    max_restarts: int = 1
    poll_interval: float = 2.0
    diagnostics_root: Optional[str] = None
    cpu_idle_delta_seconds: float = 0.05


def run_with_monitor(
    argv: Sequence[str],
    *,
    input: Optional[str] = None,  # noqa: A002 - mirror subprocess.run
    capture_output: bool = False,
    text: bool = False,
    timeout: Optional[float] = None,
    cwd: Optional[str] = None,
    stdin=None,
    role: str = "",
    harness: str = "",
    monitor_config: Optional[MonitorConfig] = None,
    liveness_probe_factory: Optional[Callable[[], Any]] = None,
):
    """Run a subprocess with a tiny stuck detector and one optional restart.

    The signature intentionally mirrors the subprocess.run subset used by the
    adapters, so call sites stay boring. Prompts passed through ``input=`` are
    written to stdin and then closed, preserving the important EOF behavior.
    """

    cfg = monitor_config or MonitorConfig()
    notes: list[str] = []
    attempts = max(1, cfg.max_restarts + 1)
    last_reason = None
    for attempt in range(1, attempts + 1):
        try:
            proc = _run_once(
                argv,
                input=input,
                capture_output=capture_output,
                text=text,
                timeout=timeout,
                cwd=cwd,
                stdin=stdin,
                role=role,
                harness=harness,
                cfg=cfg,
                attempt=attempt,
                liveness_probe_factory=liveness_probe_factory,
            )
            if notes:
                prefix = "\n".join(notes) + "\n"
                proc.stderr = prefix + (proc.stderr or "")
            # Universal-skill-mounting §3/D2 — ADDITIVE attempt metadata: the index
            # of the attempt that produced THIS terminal result (earlier stuck
            # attempts' streams were discarded, never merged). Callers that don't
            # read it are unaffected.
            proc.aidazi_attempt = attempt
            return proc
        except _StuckOnce as exc:
            last_reason = exc.reason
            notes.append(
                f"[aidazi-monitor] recovered from stuck {harness or 'agent'} "
                f"spawn for role={role or 'unknown'} on attempt {attempt}: "
                f"{exc.reason.get('reason')}"
            )
            if attempt >= attempts:
                break
    raise AgentStuckError(
        f"agent subprocess stuck after {attempts} attempt(s): {last_reason}"
    )


class _StuckOnce(Exception):
    def __init__(self, reason: dict):
        self.reason = reason
        super().__init__(reason.get("reason", "stuck"))


def _run_once(
    argv: Sequence[str],
    *,
    input: Optional[str],
    capture_output: bool,
    text: bool,
    timeout: Optional[float],
    cwd: Optional[str],
    stdin,
    role: str,
    harness: str,
    cfg: MonitorConfig,
    attempt: int,
    liveness_probe_factory: Optional[Callable[[], Any]] = None,
):
    start = time.monotonic()
    last_output = {"t": start}
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    writer_error: list[BaseException] = []
    probe = liveness_probe_factory() if liveness_probe_factory else None
    line_buf = {"buf": b""} if probe is not None else None

    popen_stdin = subprocess.PIPE if input is not None else stdin
    popen_stdout = subprocess.PIPE if capture_output else None
    popen_stderr = subprocess.PIPE if capture_output else None
    kwargs = {}
    if hasattr(os, "setsid"):
        kwargs["preexec_fn"] = os.setsid
    proc = subprocess.Popen(  # noqa: S603 - adapter argv is fixed upstream
        list(argv),
        stdin=popen_stdin,
        stdout=popen_stdout,
        stderr=popen_stderr,
        cwd=cwd,
        **kwargs,
    )

    threads = []
    if input is not None and proc.stdin is not None:
        data = input.encode("utf-8") if text else input
        t = threading.Thread(
            target=_write_and_close, args=(proc.stdin, data, writer_error),
            daemon=True)
        t.start()
        threads.append(t)
    if capture_output and proc.stdout is not None:
        t = threading.Thread(
            target=_read_stream,
            args=(proc.stdout, stdout_chunks, last_output, probe, line_buf),
            daemon=True)
        t.start()
        threads.append(t)
    if capture_output and proc.stderr is not None:
        t = threading.Thread(
            target=_read_stream, args=(proc.stderr, stderr_chunks, last_output),
            daemon=True)
        t.start()
        threads.append(t)

    last_cpu = _effective_cpu_seconds(proc.pid)
    last_cpu_change = start

    while True:
        rc = proc.poll()
        now = time.monotonic()
        if rc is not None:
            for t in threads:
                t.join(timeout=1.0)
            if writer_error:
                raise writer_error[0]
            stdout = _decode(stdout_chunks, text)
            stderr = _decode(stderr_chunks, text)
            return subprocess.CompletedProcess(list(argv), rc, stdout, stderr)

        if timeout is not None and now - start >= timeout:
            reason = _reason("timeout", proc.pid, start, last_output["t"], attempt)
            _record_diagnostic(
                cfg, cwd, role, harness, attempt, argv, input, proc.pid, reason,
                stdout_chunks, stderr_chunks)
            _kill_tree(proc)
            _close_pipes(proc)
            for t in threads:
                t.join(timeout=1.0)
            stdout = _decode(stdout_chunks, text)
            stderr = _decode(stderr_chunks, text)
            raise subprocess.TimeoutExpired(list(argv), timeout, stdout, stderr)

        cpu = _effective_cpu_seconds(proc.pid)
        if cpu is not None and last_cpu is not None:
            if cpu - last_cpu > cfg.cpu_idle_delta_seconds:
                last_cpu_change = now
            last_cpu = cpu
        elif cpu is not None:
            last_cpu = cpu
            last_cpu_change = now

        no_output_for = now - last_output["t"]
        idle_for = now - last_cpu_change
        cpu_unknown = cpu is None
        active_tool = probe is not None and probe.active()
        stuck = (not active_tool) and (
            no_output_for >= cfg.no_output_seconds
            and (
                idle_for >= cfg.idle_cpu_seconds
                or (cpu_unknown and no_output_for >= cfg.max_stuck_seconds)
            )
        )
        if stuck:
            reason = _reason(
                "no_output_cpu_idle" if not cpu_unknown else "no_output_no_cpu_sample",
                proc.pid, start, last_output["t"], attempt,
                cpu_seconds=cpu, idle_for=idle_for)
            _record_diagnostic(
                cfg, cwd, role, harness, attempt, argv, input, proc.pid, reason,
                stdout_chunks, stderr_chunks)
            _kill_tree(proc)
            _close_pipes(proc)
            for t in threads:
                t.join(timeout=1.0)
            raise _StuckOnce(reason)

        time.sleep(max(0.05, cfg.poll_interval))


def _write_and_close(stream, data, errors):
    try:
        stream.write(data)
        stream.close()
    except BaseException as exc:  # pragma: no cover - defensive handoff
        errors.append(exc)


def _read_stream(stream, chunks, last_output, probe=None, line_buf=None):
    try:
        while True:
            data = (stream.read1(4096) if hasattr(stream, "read1")
                    else stream.read(4096))
            if not data:
                break
            chunks.append(data)
            last_output["t"] = time.monotonic()   # (a) output-liveness FIRST
            if probe is not None and line_buf is not None:   # (b) then the lease
                line_buf["buf"] += data
                while True:
                    nl = line_buf["buf"].find(b"\n")
                    if nl < 0:
                        break
                    line = line_buf["buf"][:nl]
                    line_buf["buf"] = line_buf["buf"][nl + 1:]
                    try:
                        probe.observe(line.decode("utf-8", "replace"))
                    except Exception:
                        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _decode(chunks: list[bytes], text: bool):
    data = b"".join(chunks)
    return data.decode("utf-8", errors="replace") if text else data


def _cpu_seconds(pid: int) -> Optional[float]:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed ps invocation
            ["ps", "-o", "time=", "-p", str(pid)],
            capture_output=True, text=True, timeout=1)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return _parse_ps_time(proc.stdout.strip())


def _group_cpu_seconds(pgid: int) -> Optional[float]:
    """Total CPU seconds across the process GROUP ``pgid`` (P1-b).

    The monitored ``claude`` is a SUPERVISOR that sits near-idle while its
    Bash-tool children (mvn/java/npm) do the work; a parent-only sample would
    misread that as idle and false-kill a busy in-session build. ``ps -A -o
    pgid=,time=`` (portable macOS + Linux) lists every process's pgid + CPU
    time; we sum the rows whose pgid matches. Returns None on query failure or
    no matching rows so the caller can fall back to the single-pid sample (never
    worse than parent-only).
    """
    try:
        proc = subprocess.run(  # noqa: S603 - fixed ps invocation
            ["ps", "-A", "-o", "pgid=,time="],
            capture_output=True, text=True, timeout=2)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    total = 0.0
    matched = False
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            if int(parts[0]) != pgid:
                continue
        except ValueError:
            continue
        secs = _parse_ps_time(parts[1])
        if secs is not None:
            total += secs
            matched = True
    return total if matched else None


def _effective_cpu_seconds(pid: int) -> Optional[float]:
    """Group-aware CPU (P1-b) with a single-pid fallback (P1-a).

    Prefers the process-group total (so a supervisor driving a CPU-bound child
    is not misread as idle); falls back to the parent-only sample if the group
    query is unavailable or fails. Group total ⊇ parent, so this is never a
    weaker liveness signal than the pre-P1-b behavior.
    """
    if hasattr(os, "getpgid"):
        try:
            g = _group_cpu_seconds(os.getpgid(pid))
        except Exception:
            g = None
        if g is not None:
            return g
    return _cpu_seconds(pid)


def _parse_ps_time(value: str) -> Optional[float]:
    """Parse a ``ps`` CPU-time field to float seconds.

    Handles BOTH macOS fractional format (``[[D-]H:]MM:SS.ss`` — the seconds
    field carries a decimal, e.g. ``0:05.62``; minutes may exceed 60) and Linux
    integer format (``[[D-]HH:]MM:SS``). The LAST colon-group is parsed as
    ``float`` (so a fractional ``.ss`` no longer raises); the preceding groups
    are ``int``. A bare ``SS.ss`` (no colon) is accepted. Empty/malformed → None.

    macOS regression this fixes: the old ``int(p)`` on every colon-part raised
    ValueError on the ``.ss`` fraction, so ``_cpu_seconds`` returned None on
    EVERY poll → the CPU liveness signal went blind and the watchdog
    false-killed live sessions at ~180s.
    """
    if value is None:
        return None
    rest = value.strip()
    if not rest:
        return None
    try:
        days = 0
        if "-" in rest:
            day_s, rest = rest.split("-", 1)
            days = int(day_s)
        groups = rest.split(":")
        if not 1 <= len(groups) <= 3:
            return None
        seconds = float(groups[-1])            # SS or SS.ss (fractional OK)
        head = [int(g) for g in groups[:-1]]   # H, M as ints
        hours, minutes = 0, 0
        if len(head) == 1:
            minutes = head[0]
        elif len(head) == 2:
            hours, minutes = head
        return float(days * 86400 + hours * 3600 + minutes * 60) + seconds
    except ValueError:
        return None


def _reason(kind: str, pid: int, start: float, last_output: float, attempt: int, **extra):
    out = {
        "reason": kind,
        "pid": pid,
        "attempt": attempt,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "seconds_since_output": round(time.monotonic() - last_output, 3),
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    out.update(extra)
    return out


def _record_diagnostic(
    cfg: MonitorConfig,
    cwd: Optional[str],
    role: str,
    harness: str,
    attempt: int,
    argv: Sequence[str],
    input_text: Optional[str],
    pid: int,
    reason: dict,
    stdout_chunks: list[bytes],
    stderr_chunks: list[bytes],
):
    root = cfg.diagnostics_root or os.path.join(
        cwd or os.getcwd(), ".orchestrator", "diagnostics", "agent-stuck")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = "-".join(x for x in (harness, role, f"attempt{attempt}") if x)
    path = os.path.join(root, f"{stamp}-{safe or 'agent'}")
    os.makedirs(path, exist_ok=True)
    _write(os.path.join(path, "argv.txt"), shlex.join(str(a) for a in argv) + "\n")
    _write(os.path.join(path, "pid.txt"), f"{pid}\n")
    _write(os.path.join(path, "reason.json"), json.dumps(reason, indent=2) + "\n")
    if input_text is not None:
        _write(os.path.join(path, "input.sha256.txt"),
               hashlib.sha256(input_text.encode("utf-8")).hexdigest() + "\n")
    _write(os.path.join(path, "stdout.tail.txt"),
           _tail(_decode(stdout_chunks, True)))
    _write(os.path.join(path, "stderr.tail.txt"),
           _tail(_decode(stderr_chunks, True)))
    _write(os.path.join(path, "ps.txt"), _ps_snapshot(pid))


def _write(path: str, text: str):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _tail(text: str, limit: int = 8000) -> str:
    return text[-limit:]


def _ps_snapshot(pid: int) -> str:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed ps invocation
            ["ps", "-o", "pid,ppid,etime,time,%cpu,stat,command", "-p", str(pid)],
            capture_output=True, text=True, timeout=1)
    except Exception as exc:
        return f"ps failed: {exc}\n"
    return proc.stdout or proc.stderr


def _kill_tree(proc):
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:  # pragma: no cover - non-posix fallback
            proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:  # pragma: no cover - non-posix fallback
                proc.kill()
        except Exception:
            pass


def _close_pipes(proc):
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        try:
            if stream is not None and not stream.closed:
                stream.close()
        except Exception:
            pass

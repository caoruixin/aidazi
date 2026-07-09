"""Phase-3 push-not-poll notifier (design §4). Fires the charter's
``notifications.on_pause`` argv hook on EVERY campaign pause (exit 10).

Trust boundary (design §4.2): the hook is TRUSTED, adopter-owned code — NOT
sandboxed. The framework guarantees only that it is:
  * FAIL-SAFE  — any failure/timeout is swallowed and NEVER affects the pause;
  * BOUNDED    — a hard subprocess timeout (clamped to 60s);
  * INJECTION-FREE — argv LIST, shell=False; pause context is passed via
    AIDAZI_PAUSE_* env vars, so the configured argv stays fixed;
  * AUDITED with REDACTED metadata — argv0 basename + argc + sha256 only, never
    the full argv (webhook URLs/tokens), env, or captured output.
Default-OFF: absent ``notifications.on_pause`` ⇒ a complete no-op (no subprocess,
no audit event, byte-identical to no notifier).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from typing import Any, Callable, Dict, Optional

_TIMEOUT_MIN = 1
_TIMEOUT_MAX = 60
_TIMEOUT_DEFAULT = 10


def _bounded_timeout(raw: Any) -> int:
    try:
        return min(max(int(raw), _TIMEOUT_MIN), _TIMEOUT_MAX)
    except (TypeError, ValueError):
        return _TIMEOUT_DEFAULT


def notify_on_pause(charter: Optional[dict],
                    pause_ctx: Dict[str, Any],
                    audit_emit: Callable[[str, dict], Any],
                    *, env: Optional[dict] = None) -> Optional[dict]:
    """Run the configured on_pause hook for one pause. Returns the redacted audit
    payload it emitted (or None when default-OFF). Never raises."""
    notif = (charter or {}).get("notifications") or {}
    argv = notif.get("on_pause")
    if not argv or not isinstance(argv, list):
        return None  # default-OFF ⇒ no-op

    timeout = _bounded_timeout(notif.get("timeout_seconds", _TIMEOUT_DEFAULT))
    child_env = dict(env if env is not None else os.environ)
    for key, val in (pause_ctx or {}).items():
        if val is not None:
            child_env[f"AIDAZI_PAUSE_{str(key).upper()}"] = str(val)

    argv0 = os.path.basename(str(argv[0]))
    argv_sha = hashlib.sha256(
        "\x00".join(str(a) for a in argv).encode("utf-8")).hexdigest()
    exit_code: Optional[int] = None
    timed_out = False
    stdout_bytes = 0
    stderr_bytes = 0
    error: Optional[str] = None
    start = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 - argv is a fixed charter list, shell=False
            [str(a) for a in argv], env=child_env, timeout=timeout,
            capture_output=True, text=True, check=False)
        exit_code = proc.returncode
        stdout_bytes = len(proc.stdout or "")
        stderr_bytes = len(proc.stderr or "")
    except subprocess.TimeoutExpired:
        timed_out = True
    except Exception as exc:  # a trusted hook that cannot launch must not break the pause
        error = type(exc).__name__
    duration_s = round(time.monotonic() - start, 3)

    payload = {
        "argv0": argv0,
        "argc": len(argv),
        "argv_sha256": argv_sha,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_s": duration_s,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "pause_reason": (pause_ctx or {}).get("reason"),
        "checkpoint": (pause_ctx or {}).get("checkpoint"),
    }
    if error is not None:
        payload["error"] = error
    try:
        audit_emit("campaign_pause_notified", payload)
    except Exception:
        pass  # an audit-append failure must not break the pause either
    return payload

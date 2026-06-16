"""engine-kit/scheduling — the harness-agnostic schedule ENTRYPOINT (P5-B).

The master plan fixes scheduling as plain cron / CI, explicitly NOT any
harness's own scheduler ("scheduling | framework | plain cron / CI (not
ScheduleWakeup)"). This package is that framework-owned outer wrapper: a thin
Python entrypoint a cron job or CI workflow invokes to run ONE delivery loop
end-to-end (load charter → build adapters → construct Driver → run → verify the
audit chain → summarize/exit-code).

It is an OUTER wrapper around the deterministic kernel (driver.py), not part of
it: the only wall-clock read is the injected production clock here; the kernel
stays pure because the clock is injected (tests inject a deterministic one).
"""

from .run_loop import build_adapters, run_loop, main  # noqa: F401

__all__ = ["build_adapters", "run_loop", "main"]

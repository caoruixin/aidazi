"""engine-kit orchestrator — the standalone deterministic Delivery-Loop driver.

Normative source: process/delivery-loop.md §4.2. This package is a reference
*implementation* (ADR-0001); on any conflict the spec wins.
"""

from .driver import (  # noqa: F401
    Driver,
    RunState,
    GateHardFail,
    BudgetExceeded,
    load_charter,
    load_verdict_schemas,
    route_for_role,
    validate_verdict,
)

#!/usr/bin/env python3
"""loop_ingress — Loop Ingress: git-isolation strategies + loop registry (P4 piece 1).

The **Loop Ingress** is the "loop start" concept of the v2 loop engine
(archive/2026-06-15-v2-loop-engine-plan.md §2 glossary, §4.3): at a new-loop
trigger the engine picks (and may recommend) one of three git-isolation
strategies, sets up the git working context, registers the loop in a small
registry so collisions can be detected, and cleans the isolated branch/worktree
up at loop close.

This module is a **STANDALONE deterministic module**. It is NOT wired into the
driver here — a later integration step adds the `loop_init`/`loop_close` hooks
(this file's API is shaped so that hook is a thin call). The split mirrors
loop_controller.py (pure decision) + driver.py (side effects):

  * ``decide_strategy``  — PURE, deterministic decision logic. No clock, no
    randomness, no IO, no git, no LLM. Given the charter ``isolation`` config
    + two observed booleans (``dirty_tree``, an ``active_loops`` list) it
    returns the chosen strategy, a recommendation, and a human-readable reason.
  * ``setup_context`` / ``cleanup`` — the git SIDE EFFECTS, run via subprocess
    against a real git repo (offline; the engine-kit never goes to network).
  * ``LoopRegistry`` — a deterministic JSON-file registry (``.orchestrator/
    loops.json``) of active/done loops, with atomic-ish writes + stable order.

THREE STRATEGIES (plan §4.3 table):

  | strategy        | git semantics            | fits                         |
  |-----------------|--------------------------|------------------------------|
  | current_branch  | in-place (no-op)         | small / serial               |
  | new_branch      | `git switch -c` from base| discrete PR unit             |
  | new_worktree    | `git worktree add -b`    | parallel / long autonomous   |

Default = current_branch (charter ``isolation.default_strategy``). The engine
**overrides toward isolation** when a force condition holds (``dirty_tree`` or
``loop_active_on_branch``) AND that condition is listed in
``isolation.force_isolation_when`` — it then RECOMMENDS new_branch (or
new_worktree when a loop is already active on the branch, since a same-dir
branch switch cannot run in parallel with that active loop). The human keeps
authority — `decide_strategy` recommends; the ingress prompt confirms.

DETERMINISM / clock+id injection: like the driver, this module never reads the
clock or random itself. ``LoopRegistry.register`` takes an injected ``ts`` (and
the loop_id is supplied by the caller). The pure ``decide_strategy`` has no
clock at all.

NORMATIVE SOURCE: archive/2026-06-15-v2-loop-engine-plan.md §4.3 + §5
(charter ``isolation`` block) + schemas/mission-charter.schema.json
(``isolation`` block). On any conflict the spec wins and this file is the bug.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional, Sequence

# --------------------------------------------------------------------------- #
# Strategy + force-condition constants (mirror the charter enum, §5 / schema).
# --------------------------------------------------------------------------- #
STRATEGY_CURRENT_BRANCH = "current_branch"
STRATEGY_NEW_BRANCH = "new_branch"
STRATEGY_NEW_WORKTREE = "new_worktree"
STRATEGIES = (STRATEGY_CURRENT_BRANCH, STRATEGY_NEW_BRANCH, STRATEGY_NEW_WORKTREE)

FORCE_LOOP_ACTIVE_ON_BRANCH = "loop_active_on_branch"
FORCE_DIRTY_TREE = "dirty_tree"
FORCE_CONDITIONS = (FORCE_LOOP_ACTIVE_ON_BRANCH, FORCE_DIRTY_TREE)

# cleanup_policy enum (charter §5 / schema).
CLEANUP_KEEP = "keep"
CLEANUP_REMOVE_IF_MERGED = "remove_if_merged"
CLEANUP_REMOVE_IF_UNCHANGED = "remove_if_unchanged"

# Registry loop statuses.
STATUS_ACTIVE = "active"
STATUS_DONE = "done"
STATUS_FAILED = "failed"   # terminated on a hard-fail; NOT active, NOT a clean done


# --------------------------------------------------------------------------- #
# Typed errors (clear, not raw subprocess tracebacks — mirrors AdapterError).
# --------------------------------------------------------------------------- #
class IngressError(Exception):
    """Base class for Loop Ingress errors."""


class GitOpError(IngressError):
    """A git subprocess failed. Carries the command, returncode, and stderr so
    the caller gets a clean, reported error instead of a CalledProcessError."""

    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str):
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stderr = (stderr or "").strip()
        super().__init__(
            f"git failed ({' '.join(self.cmd)}) [exit {returncode}]: {self.stderr}"
        )


class StrategyError(IngressError):
    """An unknown / unsupported isolation strategy was requested."""


class RegistryError(IngressError):
    """The loop registry file was present but unparseable/corrupt."""

    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"loop registry corrupt ({path}): {reason}")


# --------------------------------------------------------------------------- #
# PURE DECISION LOGIC — no clock, no IO, no git. (decide_strategy)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StrategyDecision:
    """The result of ``decide_strategy`` (pure value).

    strategy        : the BASELINE strategy (charter default) — what runs if the
                      human accepts the default with no override.
    recommendation  : the strategy the engine RECOMMENDS — equals ``strategy``
                      unless a force condition escalated it toward isolation.
    escalated       : True iff ``recommendation`` differs from ``strategy``
                      because a force condition fired.
    reason          : human-readable reason (always non-empty; states why the
                      recommendation is what it is).
    triggers        : the force conditions that actually fired (subset of the
                      observed conditions ∩ force_isolation_when), stable order.
    """

    strategy: str
    recommendation: str
    escalated: bool
    reason: str
    triggers: tuple[str, ...] = ()


def _normalize_isolation_cfg(isolation_cfg: Optional[dict]) -> dict:
    """Return a defaulted copy of the charter ``isolation`` block. Absent block
    (legacy charter) ⇒ all defaults (current_branch, no force conditions)."""
    cfg = dict(isolation_cfg or {})
    default_strategy = cfg.get("default_strategy") or STRATEGY_CURRENT_BRANCH
    if default_strategy not in STRATEGIES:
        raise StrategyError(
            f"isolation.default_strategy={default_strategy!r} not one of {STRATEGIES}"
        )
    force = list(cfg.get("force_isolation_when") or [])
    return {
        "default_strategy": default_strategy,
        "force_isolation_when": force,
        "worktree_root": cfg.get("worktree_root"),
        "cleanup_policy": cfg.get("cleanup_policy"),
        "prompt_on_new_loop": cfg.get("prompt_on_new_loop", True),
    }


def decide_strategy(
    isolation_cfg: Optional[dict],
    *,
    dirty_tree: bool,
    active_loops: Sequence,
    target_branch: Optional[str] = None,
) -> StrategyDecision:
    """Decide the isolation strategy + recommendation (PURE / deterministic).

    Parameters
    ----------
    isolation_cfg : the charter ``isolation`` block (or None for a legacy
                    charter ⇒ all defaults). Keys per schema §5:
                    default_strategy, force_isolation_when, worktree_root,
                    cleanup_policy, prompt_on_new_loop.
    dirty_tree    : the OBSERVED working-tree state (caller runs `git status`).
    active_loops  : the registry's currently-active loops. Each item is either a
                    LoopRecord, a dict, or anything exposing ``.branch`` /
                    ``["branch"]`` — used only to test
                    ``loop_active_on_branch``.
    target_branch : the branch the new loop would run on (the current branch for
                    current_branch / new_branch). When None, the
                    ``loop_active_on_branch`` condition cannot fire (no branch to
                    compare), so only ``dirty_tree`` can escalate.

    Decision
    --------
    Baseline = ``default_strategy`` (default current_branch). The engine then
    inspects which force conditions hold AND are enabled in
    ``force_isolation_when``:

      * ``loop_active_on_branch`` (an active loop is already on target_branch):
        a same-dir branch switch cannot run alongside that active loop, so the
        recommendation escalates to **new_worktree** (parallel-capable).
      * ``dirty_tree`` (uncommitted changes): a branch switch would carry the
        dirty work along; recommend at least **new_branch** to make it a
        discrete unit. (If a loop is ALSO active on the branch, new_worktree
        already dominates — worktree wins.)

    The recommendation never DOWNGRADES below the configured default (if the
    default is already new_worktree it stays new_worktree). Returns a
    StrategyDecision; the ingress prompt presents ``recommendation`` to the human.
    """
    cfg = _normalize_isolation_cfg(isolation_cfg)
    default_strategy = cfg["default_strategy"]
    force = cfg["force_isolation_when"]

    loop_on_branch = bool(
        target_branch is not None
        and _is_branch_in_active_loops(target_branch, active_loops)
    )
    # Force conditions that BOTH hold AND are enabled in force_isolation_when.
    triggers: list[str] = []
    if FORCE_LOOP_ACTIVE_ON_BRANCH in force and loop_on_branch:
        triggers.append(FORCE_LOOP_ACTIVE_ON_BRANCH)
    if FORCE_DIRTY_TREE in force and dirty_tree:
        triggers.append(FORCE_DIRTY_TREE)

    # Rank strategies so we never recommend WEAKER isolation than the default.
    rank = {STRATEGY_CURRENT_BRANCH: 0, STRATEGY_NEW_BRANCH: 1, STRATEGY_NEW_WORKTREE: 2}
    recommendation = default_strategy

    if FORCE_LOOP_ACTIVE_ON_BRANCH in triggers:
        # A live loop on the branch ⇒ must isolate into a separate working dir.
        if rank[STRATEGY_NEW_WORKTREE] > rank[recommendation]:
            recommendation = STRATEGY_NEW_WORKTREE
    if FORCE_DIRTY_TREE in triggers:
        # Dirty tree ⇒ at least a new branch so the loop is a discrete unit.
        if rank[STRATEGY_NEW_BRANCH] > rank[recommendation]:
            recommendation = STRATEGY_NEW_BRANCH

    escalated = recommendation != default_strategy
    reason = _build_reason(default_strategy, recommendation, triggers, escalated)
    return StrategyDecision(
        strategy=default_strategy,
        recommendation=recommendation,
        escalated=escalated,
        reason=reason,
        triggers=tuple(triggers),
    )


def _is_branch_in_active_loops(branch: str, active_loops: Sequence) -> bool:
    """True iff any active loop record is on ``branch``. Accepts LoopRecord,
    dicts, or any object exposing a ``branch`` attribute/key (pure)."""
    for rec in active_loops or ():
        if _record_branch(rec) == branch:
            return True
    return False


def _record_branch(rec) -> Optional[str]:
    """Extract a branch string from a LoopRecord / dict / attr-bearing object."""
    if isinstance(rec, LoopRecord):
        return rec.branch
    if isinstance(rec, dict):
        return rec.get("branch")
    return getattr(rec, "branch", None)


def _build_reason(default_strategy: str, recommendation: str,
                  triggers: Sequence[str], escalated: bool) -> str:
    if not escalated:
        if triggers:
            # A force condition held but the default already met/exceeded it.
            return (f"default strategy {default_strategy!r} already provides "
                    f"isolation for {', '.join(triggers)}; no escalation needed")
        return f"no force condition triggered; using default strategy {default_strategy!r}"
    why = []
    if FORCE_LOOP_ACTIVE_ON_BRANCH in triggers:
        why.append("a loop is already active on the target branch (cannot share "
                   "a working dir / run in parallel in-place)")
    if FORCE_DIRTY_TREE in triggers:
        why.append("the working tree is dirty (a branch switch would carry "
                   "uncommitted work along)")
    return (f"escalated from default {default_strategy!r} to {recommendation!r} "
            f"because " + "; ".join(why))


# --------------------------------------------------------------------------- #
# GIT SIDE EFFECTS — setup_context + cleanup. (subprocess git, offline)
# --------------------------------------------------------------------------- #
@dataclass
class ContextHandle:
    """The git working context a loop runs in (returned by setup_context).

    work_dir  : the directory the loop's tools operate in. For current_branch /
                new_branch this is ``repo_dir``; for new_worktree it is the
                separate worktree directory.
    branch    : the branch the loop is on.
    strategy  : which strategy produced this handle.
    repo_dir  : the ORIGINAL main repo dir (where the registry + worktree admin
                live) — distinct from work_dir for new_worktree.
    created   : True iff this strategy created a new branch/worktree (so cleanup
                knows there is something to tear down).
    """

    work_dir: str
    branch: str
    strategy: str
    repo_dir: str
    created: bool = False
    base_ref: Optional[str] = None  # the ref the loop branch branched FROM
                                    # (for a safe commits-ahead change check at
                                    # close); None ⇒ unknown (e.g. after resume).

    def to_dict(self) -> dict:
        return {
            "work_dir": self.work_dir,
            "branch": self.branch,
            "strategy": self.strategy,
            "repo_dir": self.repo_dir,
            "created": self.created,
            "base_ref": self.base_ref,
        }


def _run_git(repo_dir: str, args: Sequence[str]) -> str:
    """Run ``git -C <repo_dir> <args>`` offline, returning stdout. Raises
    GitOpError (clean, typed) on a non-zero exit instead of leaking
    CalledProcessError. No network is ever touched (no fetch/clone here)."""
    cmd = ["git", "-C", repo_dir, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitOpError(cmd, proc.returncode, proc.stderr)
    return proc.stdout


def current_branch(repo_dir: str) -> str:
    """The current branch name (`git symbolic-ref --short HEAD`)."""
    return _run_git(repo_dir, ["symbolic-ref", "--short", "HEAD"]).strip()


def is_dirty_tree(repo_dir: str) -> bool:
    """True iff the working tree has uncommitted changes (`git status
    --porcelain` is non-empty). The observed input to decide_strategy."""
    out = _run_git(repo_dir, ["status", "--porcelain"])
    return bool(out.strip())


def setup_context(
    strategy: str,
    *,
    repo_dir: str,
    loop_id: str,
    base_ref: Optional[str] = None,
    worktree_root: Optional[str] = None,
    branch_name: Optional[str] = None,
) -> ContextHandle:
    """Perform the git op for ``strategy`` and return a ContextHandle.

    strategy       : one of STRATEGIES.
    repo_dir       : the main repo directory.
    loop_id        : threads the loop; used to derive a deterministic default
                     branch / worktree name (``loop/<loop_id>``).
    base_ref       : the ref the new branch/worktree branches FROM. Defaults to
                     the repo's current branch (so a loop branches off HEAD).
    worktree_root  : directory under which a new worktree is created (new_worktree
                     only). Defaults to a sibling ``<repo_dir>/../<repo>-worktrees``.
    branch_name    : explicit branch name (defaults to ``loop/<loop_id>``).

    current_branch : NO-OP. Returns a handle on repo_dir's current branch.
    new_branch     : ``git switch -c <branch> <base_ref>`` (same dir).
    new_worktree   : ``git worktree add <dir> -b <branch> <base_ref>`` (new dir).
    """
    if strategy not in STRATEGIES:
        raise StrategyError(f"unknown isolation strategy {strategy!r}; "
                            f"expected one of {STRATEGIES}")
    repo_dir = os.path.abspath(repo_dir)
    branch = branch_name or _default_branch_name(loop_id)
    base = base_ref or current_branch(repo_dir)

    if strategy == STRATEGY_CURRENT_BRANCH:
        # In-place: no git mutation. The loop runs on the current branch.
        return ContextHandle(
            work_dir=repo_dir,
            branch=current_branch(repo_dir),
            strategy=strategy,
            repo_dir=repo_dir,
            created=False,
            base_ref=base,
        )

    if strategy == STRATEGY_NEW_BRANCH:
        # Discrete PR unit: create + switch to the new branch in the same dir.
        _run_git(repo_dir, ["switch", "-c", branch, base])
        return ContextHandle(
            work_dir=repo_dir,
            branch=branch,
            strategy=strategy,
            repo_dir=repo_dir,
            created=True,
            base_ref=base,
        )

    # STRATEGY_NEW_WORKTREE: separate working dir on its own branch (parallel).
    wt_root = worktree_root or _default_worktree_root(repo_dir)
    os.makedirs(wt_root, exist_ok=True)
    work_dir = os.path.join(wt_root, _safe_dir_name(loop_id))
    _run_git(repo_dir, ["worktree", "add", work_dir, "-b", branch, base])
    return ContextHandle(
        work_dir=os.path.abspath(work_dir),
        branch=branch,
        strategy=strategy,
        repo_dir=repo_dir,
        created=True,
        base_ref=base,
    )


def cleanup(
    handle: ContextHandle,
    *,
    cleanup_policy: Optional[str],
    merged: bool,
    changed: bool,
) -> str:
    """Dispose of an isolated branch/worktree at loop close per ``cleanup_policy``.

    new_worktree   : `git worktree remove` when the policy says remove AND the
                     condition holds:
                       remove_if_merged    ⇒ remove iff ``merged``;
                       remove_if_unchanged ⇒ remove iff NOT ``changed``;
                       keep / None         ⇒ keep.
                     Otherwise the worktree is kept for the human / PR.
    new_branch     : LEAVE IT for the PR (a branch is the discrete review unit).
                     We never delete a branch here — removing review history is a
                     human decision.
    current_branch : nothing to clean up (no-op).

    Returns a short human-readable action string ("removed" | "kept" | "noop").
    The remove is a local `git worktree remove` (offline; never network).
    """
    if handle.strategy == STRATEGY_CURRENT_BRANCH or not handle.created:
        return "noop"

    if handle.strategy == STRATEGY_NEW_BRANCH:
        # The branch is the PR unit; leave it for review. (Cleanup of a merged
        # branch is a human/PR-tool decision, not the engine's.)
        return "kept"

    # STRATEGY_NEW_WORKTREE.
    should_remove = False
    if cleanup_policy == CLEANUP_REMOVE_IF_MERGED and merged:
        should_remove = True
    elif cleanup_policy == CLEANUP_REMOVE_IF_UNCHANGED and not changed:
        should_remove = True

    if not should_remove:
        return "kept"

    # `git worktree remove` refuses a dirty worktree without --force; for an
    # UNCHANGED worktree it is clean so plain remove works. We never pass --force
    # blindly (that would discard work); remove_if_unchanged is gated on
    # not-changed precisely so the remove is safe.
    _run_git(handle.repo_dir, ["worktree", "remove", handle.work_dir])
    return "removed"


def context_has_changes(handle: ContextHandle) -> bool:
    """True iff the loop's isolated context produced any change vs its base.

    "Changed" = a dirty working tree (uncommitted edits) OR — when ``base_ref``
    is known — commits on the loop branch ahead of that base. This is the
    ``changed`` input a caller (the driver) feeds to :func:`cleanup` so a
    ``remove_if_unchanged`` policy NEVER discards real work, including committed
    work that leaves a clean tree.

    CONSERVATIVE / FAIL-SAFE: if the state cannot be determined (a git error, or
    an unknown ``base_ref`` after a resume), this returns ``True`` — i.e. "treat
    it as changed, keep it" — so cleanup errs toward preserving the context.
    Offline; never touches the network.
    """
    try:
        if is_dirty_tree(handle.work_dir):
            return True
    except IngressError:
        return True  # cannot tell ⇒ assume changed (keep)
    base = handle.base_ref
    if not base:
        # Unknown base (e.g. reconstructed on resume) ⇒ only the dirty-tree
        # signal is available; a clean tree with no known base reads as
        # "unchanged" for an in-place strategy but cleanup only acts on
        # worktrees, where committed work would have left commits we cannot see
        # without the base — so fail safe to "changed".
        return handle.strategy == STRATEGY_NEW_WORKTREE
    try:
        out = _run_git(handle.work_dir, ["rev-list", "--count", f"{base}..HEAD"])
        return int(out.strip() or "0") > 0
    except (IngressError, ValueError):
        return True  # cannot tell ⇒ assume changed (keep)


def _default_branch_name(loop_id: str) -> str:
    return f"loop/{_safe_ref_component(loop_id)}"


def _default_worktree_root(repo_dir: str) -> str:
    repo_dir = os.path.abspath(repo_dir)
    parent = os.path.dirname(repo_dir)
    base = os.path.basename(repo_dir)
    return os.path.join(parent, f"{base}-worktrees")


def _safe_dir_name(loop_id: str) -> str:
    """A filesystem-safe directory component for a worktree (no slashes)."""
    return _safe_ref_component(loop_id).replace("/", "-")


def _safe_ref_component(loop_id: str) -> str:
    """Sanitize a loop_id into a git-ref-safe component (deterministic)."""
    safe = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in str(loop_id))
    return safe or "loop"


# --------------------------------------------------------------------------- #
# LOOP REGISTRY — .orchestrator/loops.json (deterministic, atomic-ish writes).
# --------------------------------------------------------------------------- #
@dataclass
class LoopRecord:
    """One registry entry. ``registered_at`` is an INJECTED ts (no clock here)."""

    loop_id: str
    strategy: str
    branch: str
    worktree: Optional[str]
    status: str
    registered_at: str
    done_at: Optional[str] = None
    failure: Optional[str] = None   # set only when status == failed (the reason)

    def to_dict(self) -> dict:
        return {
            "loop_id": self.loop_id,
            "strategy": self.strategy,
            "branch": self.branch,
            "worktree": self.worktree,
            "status": self.status,
            "registered_at": self.registered_at,
            "done_at": self.done_at,
            "failure": self.failure,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LoopRecord":
        return cls(
            loop_id=d["loop_id"],
            strategy=d.get("strategy", ""),
            branch=d.get("branch", ""),
            worktree=d.get("worktree"),
            status=d.get("status", STATUS_ACTIVE),
            registered_at=d.get("registered_at", ""),
            done_at=d.get("done_at"),
            failure=d.get("failure"),
        )


class LoopRegistry:
    """A small JSON registry of loops at ``<orch_dir>/loops.json``.

    Detects collisions (``is_loop_active_on_branch``) for decide_strategy and
    threads the loop lifecycle (register → mark_done). The on-disk shape is::

        {"loops": [ {loop_id, strategy, branch, worktree, status,
                     registered_at, done_at}, ... ]}

    Writes are atomic-ish (write to a temp file in the same dir + os.replace) and
    the in-memory list is kept in a DETERMINISTIC order (insertion order, stable
    across reloads). No clock here — ``register``/``mark_done`` take injected ts.
    """

    FILENAME = "loops.json"

    def __init__(self, orch_dir: str):
        self.orch_dir = os.path.abspath(orch_dir)
        self.path = os.path.join(self.orch_dir, self.FILENAME)

    # ----- IO -------------------------------------------------------------- #
    def _read(self) -> list[LoopRecord]:
        if not os.path.isfile(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise RegistryError(self.path, str(exc)) from exc
        if not isinstance(data, dict) or not isinstance(data.get("loops"), list):
            raise RegistryError(self.path, "expected {'loops': [...]}")
        out: list[LoopRecord] = []
        for item in data["loops"]:
            if not isinstance(item, dict):
                raise RegistryError(self.path, f"loop entry not an object: {item!r}")
            out.append(LoopRecord.from_dict(item))
        return out

    def _write(self, records: Sequence[LoopRecord]) -> None:
        os.makedirs(self.orch_dir, exist_ok=True)
        payload = {"loops": [r.to_dict() for r in records]}
        # Atomic-ish: temp file in the SAME dir (so os.replace is atomic on the
        # same filesystem), then replace.
        fd, tmp = tempfile.mkstemp(dir=self.orch_dir, prefix=".loops.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
            os.replace(tmp, self.path)
        except BaseException:
            # Clean up the temp file if the replace never happened.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ----- API ------------------------------------------------------------- #
    def all_loops(self) -> list[LoopRecord]:
        """Every loop record in deterministic (insertion) order."""
        return self._read()

    def register(
        self,
        loop_id: str,
        strategy: str,
        branch: str,
        worktree: Optional[str],
        status: str = STATUS_ACTIVE,
        *,
        ts: str,
    ) -> LoopRecord:
        """Add (or replace, if the loop_id already exists) a loop record.

        ``ts`` is the INJECTED registration timestamp (no clock here). A repeated
        register for the same loop_id UPDATES in place (keeps order stable) so a
        resume re-register is idempotent rather than duplicating the loop."""
        records = self._read()
        rec = LoopRecord(
            loop_id=loop_id, strategy=strategy, branch=branch,
            worktree=worktree, status=status, registered_at=ts,
        )
        for i, existing in enumerate(records):
            if existing.loop_id == loop_id:
                # Preserve the original registered_at on re-register (idempotent).
                rec.registered_at = existing.registered_at or ts
                records[i] = rec
                self._write(records)
                return rec
        records.append(rec)
        self._write(records)
        return rec

    def active_loops(self) -> list[LoopRecord]:
        """Loops with status == active, in deterministic order."""
        return [r for r in self._read() if r.status == STATUS_ACTIVE]

    def is_loop_active_on_branch(self, branch: str) -> bool:
        """True iff an ACTIVE loop is registered on ``branch`` (collision check
        feeding decide_strategy's ``loop_active_on_branch`` condition)."""
        return any(r.branch == branch for r in self.active_loops())

    def get(self, loop_id: str) -> Optional[LoopRecord]:
        for r in self._read():
            if r.loop_id == loop_id:
                return r
        return None

    def mark_done(self, loop_id: str, *, ts: str) -> LoopRecord:
        """Flip a loop to status == done with an INJECTED ``done_at`` ts.
        Raises KeyError if the loop_id is not registered."""
        records = self._read()
        for i, rec in enumerate(records):
            if rec.loop_id == loop_id:
                rec.status = STATUS_DONE
                rec.done_at = ts
                records[i] = rec
                self._write(records)
                return rec
        raise KeyError(f"loop {loop_id!r} not in registry ({self.path})")

    def mark_failed(self, loop_id: str, *, ts: str,
                    reason: str = "") -> LoopRecord:
        """Flip a loop to status == failed (terminated on a hard-fail) with an
        INJECTED ``done_at`` ts + a failure ``reason``. A failed loop is NOT
        active (so it never spuriously collides with a fresh re-run) and NOT a
        clean done. Raises KeyError if the loop_id is not registered."""
        records = self._read()
        for i, rec in enumerate(records):
            if rec.loop_id == loop_id:
                rec.status = STATUS_FAILED
                rec.done_at = ts
                rec.failure = reason or None
                records[i] = rec
                self._write(records)
                return rec
        raise KeyError(f"loop {loop_id!r} not in registry ({self.path})")

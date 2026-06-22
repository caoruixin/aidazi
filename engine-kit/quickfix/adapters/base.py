"""Unified Quick-Fix harness adapter contract (Commit 3).

The QF runtime core (``quickfix.launcher``) is harness-NEUTRAL: it calls one injected
``edit_fn(work_dir)`` and never knows a single CLI flag, memory filename, or sandbox
mode. THIS package is where that knowledge lives — one adapter per harness, behind one
uniform contract. The core stays neutral; the adapters stay self-contained.

NORMATIVE SOURCE: process/quickfix-lane.md (§2 default-Full/no-self-downgrade, §5 closure
flow, §8 guard, §10 tiered harness support). If this module disagrees with that spec, the
spec wins; fix this file.

What an adapter must encapsulate (the §3.1 responsibilities) — and where:

  * adapter identifier ......... ``harness`` (class attr)
  * executable discovery ....... ``discover_executable`` (PATH + documented fallback)
  * version probe .............. ``probe_version`` (runs ``<bin> --version``)
  * supported-version check .... ``assert_supported_version`` (>= ``MIN_VERSION``)
  * capability declaration ..... ``capability`` -> :class:`HarnessCapability`
  * cwd / bundle / worktree .... ``build_argv`` (cwd = bundle; worktree granted)
  * repo/worktree access grant . ``build_argv`` (the harness-native add-dir flag)
  * environment construction ... ``build_env`` (parent env for auth; never ADD secrets)
  * command construction ....... ``build_argv`` (structured argv; ``shell=False``)
  * prompt construction ........ ``build_prompt`` (neutral; points edits at the worktree)
  * process launch ............. ``run_edit`` (shared lifecycle in THIS base class)
  * timeout/interrupt/terminate. ``run_edit`` -> ``_terminate_process_group`` (kill the
    whole group; no residual processes)
  * stdout/stderr evidence ..... ``run_edit`` (saved under ``evidence_dir``)
  * cold-start evidence ........ ``capability`` + ``cold_start_evidence`` (the isolation
    mechanism, recorded next to the launch evidence)

FAIL-CLOSED, TWO PHASES:
  - :meth:`preflight` runs BEFORE any lane side effect (no worktree/bundle yet). A missing
    executable, an unparseable/too-old version, or a harness that cannot prove cold-start
    isolation raises :class:`HarnessAdapterError` and the lane is never entered.
  - :meth:`run_edit` is the edit phase itself (a worktree + bundle now exist). A launch
    failure, a non-zero exit, or a timeout raises ``EscalationRequired`` with reason
    ``harness_launch_failure`` — the launcher then preserves + records + tears down. A
    faulty harness run NEVER becomes a ``completed`` result.

SECURITY INVARIANTS (every adapter, enforced here in the shared lifecycle):
  - structured ``argv``; ``shell=False``; no shell string is ever built;
  - the prompt is passed via STDIN or an ATTACHED long option, never as a bare argv token
    that a leading ``--`` could turn into an injected flag;
  - the process runs in its own session/group so a timeout kills the WHOLE group;
  - no secret is ever placed on ``argv`` or written into the evidence (only ``argv``,
    versions, exit code, and captured stdout/stderr are recorded — the env is not).
"""
from __future__ import annotations

import abc
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from ..errors import EscalationRequired, QuickfixError

#: Bumped when the adapter <-> core contract changes shape (recorded in evidence).
ADAPTER_CONTRACT_VERSION = "1"

_SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class HarnessAdapterError(QuickfixError):
    """A STATIC adapter failure detected BEFORE any lane side effect (fail-closed).

    Raised by :meth:`preflight` / discovery / version / capability checks. The CLI maps
    it to a clean fail-closed exit with NO worktree, NO bundle, NO record — exactly like
    an unsupported-harness refusal. It is never converted into a permissive run.
    """


@dataclass(frozen=True)
class HarnessCapability:
    """What a harness can (and cannot) do for the Quick-Fix lane.

    ``cold_start_isolation`` is the load-bearing one: the lane's whole premise is that a
    Quick-Fix session does NOT cold-start the adopter repo's full governance chain. A
    harness that cannot run with its cwd OUTSIDE the repo tree while still editing the
    ephemeral worktree (no alternate-cwd + no add-dir grant) cannot satisfy that — it must
    declare ``cold_start_isolation=False`` and the lane fails closed for it.
    """
    headless: bool                 # a non-interactive / print mode exists
    alternate_cwd: bool            # can run with cwd != the edit target
    worktree_write_grant: bool     # can be granted write access to a specific dir
    cold_start_isolation: bool     # can PROVE the repo governance chain is not auto-loaded
    isolation_mechanism: str       # one-line description of HOW (for evidence)
    notes: str = ""


@dataclass
class LaunchSpec:
    """Harness-NEUTRAL inputs for the edit phase (built by the CLI from a LaneContext).

    Carries only generic facts — an out-of-tree ``bundle_dir`` to launch in, the single
    ``worktree_dir`` the harness may edit, the task, and the approved scope. It names no
    CLI flag and no harness memory filename; the adapter maps these to its own surface.
    """
    request_id: str
    task_summary: str
    bundle_dir: str                 # out-of-tree cwd (ships the harness's memory file)
    worktree_dir: str               # the in-scope edit target (the bundle cwd is also
                                    # writable but ephemeral; the original repo is NEVER
                                    # accessible — that is the protected boundary)
    allowed_glob_patterns: List[str]
    memory_file: str                # bundle's memory file (CLAUDE.md/AGENTS.md/...) abs path
    request_file: str               # bundle/request.json (the task + scope)
    lane_file: str                  # bundle/quickfix-lane.md (the protocol)
    kernel_file: str                # bundle/anti-hardcode-kernel.md (the §1.7 lens)


@dataclass
class EditEvidence:
    """The recorded, reproducible evidence of one harness edit-phase launch.

    Persisted as JSON next to the captured stdout/stderr under the lane's evidence dir
    (``.orchestrator/quickfix/evidence/<request_id>/`` — gitignored, survives teardown).
    Contains NO secrets and NO environment — only the exact argv, versions, exit code,
    timing, and the cold-start isolation evidence.
    """
    harness: str
    adapter_contract_version: str
    executable: str
    cli_version: str
    argv: List[str]
    cwd: str
    granted_dirs: List[str]
    prompt_delivery: str
    prompt_chars: int
    exit_code: Optional[int]
    timed_out: bool
    duration_s: float
    stdout_path: str
    stderr_path: str
    stdout_bytes: int
    stderr_bytes: int
    cold_start: Dict[str, object] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class QuickfixAdapter(abc.ABC):
    """Uniform per-harness adapter for the Quick-Fix edit phase.

    Concrete adapters set the class attributes + implement the abstract hooks; the launch
    lifecycle (:meth:`run_edit`) is shared here so process handling, timeout/termination,
    and evidence capture are identical across harnesses.
    """

    #: stable harness id, matched against the request + the harness-support registry.
    harness: str = "abstract"
    #: the memory file the bundle ships for this harness (what it auto-loads at cwd).
    MEMORY_FILENAME: str = "CLAUDE.md"
    #: minimum CLI version the adapter was verified against (fail-closed below it).
    MIN_VERSION: Tuple[int, int, int] = (0, 0, 0)
    #: how the prompt reaches the CLI: "stdin" (safe) or "argv_attached" (--opt=value).
    PROMPT_DELIVERY: str = "stdin"

    def __init__(self, *, binary: Optional[str] = None, timeout_s: int = 600,
                 version_probe_timeout_s: int = 30):
        self._binary = binary or self.default_binary()
        self.timeout_s = timeout_s
        self.version_probe_timeout_s = version_probe_timeout_s

    # --- harness-specific hooks (subclasses implement) ---------------------- #

    def default_binary(self) -> str:
        """The executable name to look for on PATH (subclasses may add a fallback)."""
        return self.harness

    @abc.abstractmethod
    def capability(self) -> HarnessCapability:
        """Declare what this harness can do for the lane (drives the fail-closed gate)."""

    @abc.abstractmethod
    def build_argv(self, spec: LaunchSpec, executable: str, *, prompt: str) -> List[str]:
        """Construct the EXACT argv (structured, no shell, no secrets).

        cwd is ``spec.bundle_dir`` (set by :meth:`run_edit`, not here); this returns the
        harness-native flags that (a) grant write access to ``spec.worktree_dir`` (besides
        the ephemeral bundle cwd) but NOT the original repo, and (b) run non-interactively.
        When ``PROMPT_DELIVERY == 'stdin'``
        the prompt is delivered separately and is NOT in this argv (``prompt`` is then
        unused). When ``PROMPT_DELIVERY == 'argv_attached'`` the adapter embeds it as an
        ATTACHED long option (``--opt=<prompt>``), never as a bare token a leading ``--``
        could turn into a flag."""

    # --- shared, harness-neutral behavior ---------------------------------- #

    def discover_executable(self) -> str:
        """Resolve the CLI to an absolute path, or fail closed.

        Honors an absolute/relative path given at construction; otherwise looks on PATH.
        A binary resolved outside PATH (a subclass fallback that is not on PATH) is allowed
        because the subclass vouches for it; an unresolved binary is a hard refusal."""
        cand = self._binary
        if os.path.sep in cand or cand.startswith("~"):
            cand = os.path.abspath(os.path.expanduser(cand))
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
            raise HarnessAdapterError(
                f"{self.harness} adapter: executable not found / not executable: {cand!r}")
        found = shutil.which(cand)
        if not found:
            raise HarnessAdapterError(
                f"{self.harness} adapter: executable {cand!r} not found on PATH; the lane "
                f"fails closed (install the harness or pass an explicit --binary).")
        return found

    def probe_version(self, executable: str) -> str:
        """Run ``<exe> --version`` and return its raw output (fail-closed on failure).

        Runs in its OWN session (like the edit phase) so a hung ``--version`` is killed by
        process GROUP — no residual children. FAILS CLOSED on a launch failure, a timeout,
        OR any non-zero exit: a broken CLI that exits non-zero while still printing a version
        string must NOT pass the gate (it may behave/load differently than the verified one)."""
        argv = [executable, "--version"]
        try:
            proc = subprocess.Popen(  # noqa: S603 - fixed argv, shell=False
                argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, start_new_session=True)
        except OSError as exc:
            raise HarnessAdapterError(
                f"{self.harness} adapter: version probe failed for {executable!r}: {exc}")
        try:
            out, err = proc.communicate(timeout=self.version_probe_timeout_s)
        except subprocess.TimeoutExpired:
            self._terminate_process_group(proc)
            try:
                proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            raise HarnessAdapterError(
                f"{self.harness} adapter: '{executable} --version' timed out after "
                f"{self.version_probe_timeout_s}s (process group killed)")
        if proc.returncode != 0:
            combined = ((out or "") + (err or "")).strip()
            raise HarnessAdapterError(
                f"{self.harness} adapter: '{executable} --version' exited "
                f"{proc.returncode}: {combined[:200]!r}")
        return ((out or "") + (err or "")).strip()

    @staticmethod
    def parse_version(text: str) -> Tuple[int, int, int]:
        m = _SEMVER_RE.search(text or "")
        if not m:
            raise HarnessAdapterError(f"could not parse a semver from version output: {text!r}")
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    def assert_supported_version(self, version_text: str) -> Tuple[int, int, int]:
        v = self.parse_version(version_text)
        if v < self.MIN_VERSION:
            raise HarnessAdapterError(
                f"{self.harness} adapter: CLI version {'.'.join(map(str, v))} is below the "
                f"verified minimum {'.'.join(map(str, self.MIN_VERSION))}; fails closed "
                f"(an unverified version may load context differently).")
        return v

    def preflight(self) -> dict:
        """Static, side-effect-free fail-closed checks BEFORE the lane is entered.

        Resolves + version-checks the executable and asserts the harness can isolate its
        cold-start. Returns ``{executable, version}`` for the caller to log. Raises
        :class:`HarnessAdapterError` on any failure (no worktree/bundle exist yet)."""
        cap = self.capability()
        if not cap.cold_start_isolation:
            raise HarnessAdapterError(
                f"{self.harness} adapter: harness cannot prove Quick-Fix cold-start "
                f"isolation ({cap.isolation_mechanism}); it stays UNSUPPORTED and the lane "
                f"fails closed. Use Full framework.")
        executable = self.discover_executable()
        version = self.probe_version(executable)
        self.assert_supported_version(version)
        return {"executable": executable, "version": version}

    def build_prompt(self, spec: LaunchSpec) -> str:
        """The edit instruction — harness-neutral, points every edit at the worktree.

        The bundle's memory file already carries the lane rules (loaded at cold-start);
        this prompt makes the abstract "attached worktree" concrete (its absolute path)
        and restates the hard boundaries so a small model cannot drift."""
        globs = "\n".join(f"  - {g}" for g in spec.allowed_glob_patterns)
        return (
            f"You are running in the aidazi Quick-Fix lane (a minimal-context maintenance "
            f"lane — NOT a normal Full session). Your governing context is the local files "
            f"in this bundle directory; load them and nothing from any parent repo.\n\n"
            f"TASK ({spec.request_id}): {spec.task_summary}\n\n"
            f"The full task, scope, and verification are in ./request.json (in this "
            f"directory). Read it.\n\n"
            f"EDIT TARGET — make ALL file changes under this absolute directory ONLY:\n"
            f"  {spec.worktree_dir}\n"
            f"The approved scope (paths are relative to that directory) is:\n{globs}\n\n"
            f"HARD RULES:\n"
            f"  - Make ONLY the change described above, ONLY within the approved scope.\n"
            f"  - Do NOT edit anything outside {spec.worktree_dir}. Do NOT touch this "
            f"bundle directory's files. Do NOT `git commit`, `git add`, branch, or push — "
            f"the lane commits the result itself.\n"
            f"  - Do NOT widen scope, introduce a new decision, or touch a protected "
            f"surface. If the task cannot be done within the scope, or you are unsure, "
            f"STOP and explain instead of editing more.\n"
            f"When done, briefly state which files under the edit target you changed.")

    def build_env(self) -> Dict[str, str]:
        """Environment for the child: the parent env (the harness needs it for auth).

        We deliberately pass the inherited environment through so the harness can
        authenticate; we NEVER add a secret here and NEVER record the environment in
        evidence. Subclasses may set harness-specific NON-secret vars on top."""
        return dict(os.environ)

    def cold_start_evidence(self, spec: LaunchSpec) -> Dict[str, object]:
        """The cold-start isolation claim recorded with the launch evidence."""
        cap = self.capability()
        return {
            "isolation_mechanism": cap.isolation_mechanism,
            "cwd_is_out_of_tree_bundle": True,
            "edit_target_worktree": spec.worktree_dir,
            "bundle_memory_file": os.path.basename(spec.memory_file),
            "repo_governance_chain_auto_loaded": False,
            "note": cap.notes,
        }

    def run_edit(self, spec: LaunchSpec, *, evidence_dir: str) -> EditEvidence:
        """Launch the harness to perform the bounded edit; capture evidence; fail closed.

        cwd = the out-of-tree bundle; the worktree is granted via the adapter's argv. The
        process runs in its own session so a timeout kills the whole group (no residual
        processes). On launch failure / non-zero exit / timeout this raises
        ``EscalationRequired(harness_launch_failure)`` AFTER persisting evidence — the
        launcher then preserves the worktree state, records, and tears down."""
        # Defense in depth: even if a registry wrongly marks this harness supported, an
        # adapter that cannot isolate cold-start refuses here too.
        cap = self.capability()
        if not cap.cold_start_isolation:
            raise EscalationRequired(
                EscalationRequired.HARNESS_LAUNCH_FAILURE,
                f"{self.harness} cannot prove cold-start isolation ({cap.isolation_mechanism})")

        # Re-validate the executable here too (preflight ran earlier; the binary could have
        # changed since). A static failure now is still a harness_launch_failure, not a
        # generic inconsistent_result, so the escalation reason is precise.
        try:
            executable = self.discover_executable()
            cli_version = self.probe_version(executable)
            self.assert_supported_version(cli_version)
        except HarnessAdapterError as exc:
            raise EscalationRequired(
                EscalationRequired.HARNESS_LAUNCH_FAILURE, str(exc)) from exc

        prompt = self.build_prompt(spec)
        argv = self.build_argv(spec, executable, prompt=prompt)
        env = self.build_env()
        os.makedirs(evidence_dir, exist_ok=True)
        stdout_path = os.path.join(evidence_dir, "stdout.txt")
        stderr_path = os.path.join(evidence_dir, "stderr.txt")

        stdin_data = prompt if self.PROMPT_DELIVERY == "stdin" else None
        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.Popen(  # noqa: S603 - structured argv, shell=False
                argv, cwd=spec.bundle_dir, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True)
        except OSError as exc:
            raise EscalationRequired(
                EscalationRequired.HARNESS_LAUNCH_FAILURE,
                f"failed to launch {executable!r}: {exc}") from exc

        try:
            out, err = proc.communicate(input=stdin_data, timeout=self.timeout_s)
            exit_code: Optional[int] = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate_process_group(proc)
            try:
                out, err = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                out, err = "", ""
            exit_code = proc.returncode
        duration_s = round(time.monotonic() - start, 3)

        out, err = out or "", err or ""
        with open(stdout_path, "w", encoding="utf-8") as fh:
            fh.write(out)
        with open(stderr_path, "w", encoding="utf-8") as fh:
            fh.write(err)

        evidence = EditEvidence(
            harness=self.harness, adapter_contract_version=ADAPTER_CONTRACT_VERSION,
            executable=executable, cli_version=cli_version.splitlines()[0] if cli_version else "",
            argv=list(argv), cwd=spec.bundle_dir, granted_dirs=[spec.worktree_dir],
            prompt_delivery=self.PROMPT_DELIVERY, prompt_chars=len(prompt),
            exit_code=exit_code, timed_out=timed_out, duration_s=duration_s,
            stdout_path=stdout_path, stderr_path=stderr_path,
            stdout_bytes=len(out.encode("utf-8")), stderr_bytes=len(err.encode("utf-8")),
            cold_start=self.cold_start_evidence(spec))
        self._write_evidence_json(evidence, evidence_dir)

        if timed_out:
            raise EscalationRequired(
                EscalationRequired.HARNESS_LAUNCH_FAILURE,
                f"{self.harness} timed out after {self.timeout_s}s (process group killed)")
        if exit_code != 0:
            raise EscalationRequired(
                EscalationRequired.HARNESS_LAUNCH_FAILURE,
                f"{self.harness} exited {exit_code}: {err.strip()[:300]}")
        return evidence

    @staticmethod
    def _terminate_process_group(proc: "subprocess.Popen") -> None:
        """Kill the child's WHOLE process group (SIGTERM then SIGKILL) — no orphans."""
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, OSError):
            return
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, PermissionError, OSError):
                return
            try:
                proc.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                continue

    @staticmethod
    def _write_evidence_json(evidence: EditEvidence, evidence_dir: str) -> str:
        import json
        path = os.path.join(evidence_dir, "edit-evidence.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(evidence.to_dict(), fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def describe(self) -> dict:
        """Static routing/capability summary for audit (no I/O)."""
        cap = self.capability()
        return {
            "harness": self.harness, "memory_filename": self.MEMORY_FILENAME,
            "min_version": ".".join(map(str, self.MIN_VERSION)),
            "prompt_delivery": self.PROMPT_DELIVERY, "capability": asdict(cap),
        }

#!/usr/bin/env python3
"""e2e_executor — the orchestrator-owned browser-E2E capture runner (P-C §7).

NORMATIVE SOURCE: archive/2026-06-20-pc-browser-e2e-design.md §7 (executor),
§3.1 (fail-closed matrix), §5 (evidence layout). This module is an engine-kit
*implementation*; on any conflict the spec wins.

WHAT THIS IS (and the one invariant that must never bend):
  The executor RUNS the evidence — it starts the app under test, drives the declared
  user journeys, and captures raw artifacts (DOM/text snapshots, console, network,
  backend state) into a STAGING directory the driver provides. It emits per-criterion
  ``executor_status`` OBSERVATIONS ONLY. It NEVER emits a milestone pass/fail verdict.
  Acceptance is the sole verdict producer (anti-pattern: "Acceptance drives the browser
  itself"); the executor is the F5 capture half of orchestrator-runs / Acceptance-reads.

THE FAIL-CLOSED CORE (get this exactly right — it is the heart of the tier):
  - A CAPTURED ASSERTION FAILURE (an asserted DOM/text/state/console/network condition is
    false — a real PRODUCT defect) is NOT an exception. Record a
    ``CriterionResult(executor_status="fail")`` with full evidence and KEEP GOING; the
    run's ``exit_code`` stays 0 (the executor RAN CLEANLY even though it observed a
    failure). The driver/Acceptance turn that observation into a non-PASS later.
  - A RUNTIME FAILURE (app won't start, readiness timeout, a *blocking* step can't
    execute, capture is impossible, navigation outside ``allowed_origins``) → raise
    ``ExecutorRuntimeError`` (the driver maps it to ``gate_hard_fail``).
  - The executor RUNTIME itself being unavailable (e.g. playwright not installed / not
    enabled) → raise ``ExecutorUnavailable``.

DETERMINISM / OFFLINE (the ``LocalHttpExecutor`` path):
  stdlib only — ``subprocess`` to launch the fixture, ``http.client``/``urllib`` to drive
  it, ``html.parser`` for DOM/text asserts. NO clock and NO randomness in any artifact the
  driver hashes: the "screenshots" are normalized DOM/text snapshots (not pixels), and
  every JSON artifact is written with ``sort_keys`` and carries no timestamps. Wall-clock
  is used ONLY for the readiness/shutdown TIMEOUTS (a control-flow bound), never embedded
  in output. The ``PlaywrightExecutor`` (real pixels) is env+import gated and never runs
  in offline CI.

ARTIFACT OWNERSHIP (the driver, NOT the executor, writes the verdict-adjacent files):
  The executor writes raw capture artifacts into ``evidence_dir`` — ``app-start.log``,
  ``app-stop.log``, ``executor-config.json`` (the resolved contract it used),
  ``screenshots/<step>.snapshot.txt``, ``console.json``, ``network.json``,
  ``backend-state-refs.json`` — and returns the relative paths of every file it wrote in
  ``ExecutorResult.artifacts`` so the driver can hash them. It does NOT write
  ``manifest.json`` or ``checklist-results.json`` (the driver builds those from the
  ``ExecutorResult``, per §3.5a).
"""
from __future__ import annotations

import abc
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional


# ===========================================================================
# Result / error types — the EXACT interface the driver consumes (do not change
# the signatures or field names without a matched driver-integration change).
# ===========================================================================
@dataclass
class CriterionResult:
    """One functional-checklist criterion's OBSERVED outcome (never a verdict).

    ``executor_status`` is an OBSERVATION ONLY:
      - ``"pass"``    the asserted condition held;
      - ``"fail"``    the asserted condition was false (a captured product defect);
      - ``"error"``   the criterion's step ran but the capture/assertion machinery
                      itself faulted in a NON-blocking way (recorded, run continues);
      - ``"skipped"`` the criterion had no executable step in the contract.
    A blocking runtime failure does NOT land here — it raises ``ExecutorRuntimeError``.
    ``evidence_refs`` are paths RELATIVE TO ``evidence_dir`` (e.g.
    ``"screenshots/step1.snapshot.txt"``, ``"console.json"``) so they are portable
    after the driver publishes the staging dir to its final audit location.
    """
    criterion_id: str
    criterion: str
    action_performed: str
    observed_result: str
    evidence_refs: list = field(default_factory=list)
    executor_status: str = "skipped"


# Observation severity (Codex impl r2 BLOCKING-1): a criterion record is folded
# MONOTONICALLY across the steps that share its criterion_id — a captured non-pass is
# STICKY, so a later passing step can never silently erase an earlier fail/error. 'skipped'
# is the pre-observation placeholder any real observation replaces. error > fail > pass >
# skipped (see LocalHttpExecutor._record).
_STATUS_SEVERITY = {"skipped": 0, "pass": 1, "fail": 2, "error": 3}


@dataclass
class ExecutorResult:
    """The whole-run capture result the driver turns into a manifest + checklist-results.

    ``exit_code`` is the RUN's health, NOT a milestone verdict: ``0`` means the executor
    ran cleanly to completion (EVEN IF some criteria observed ``"fail"``); non-zero is
    reserved for a runtime failure path and in practice the executor raises rather than
    returning non-zero (kept in the contract for symmetry / future runners).
    ``artifacts`` lists the relpath of EVERY file the executor wrote (for the driver to
    hash into the manifest). ``app_start_log`` / ``app_stop_log`` are relpaths too.
    """
    exit_code: int
    criteria: list
    artifacts: list
    app_start_log: str
    app_stop_log: str
    notes: str = ""


class ExecutorUnavailable(Exception):
    """The executor RUNTIME is not available (e.g. playwright not installed / not
    enabled by the env flag). The driver maps this distinctly from a runtime error —
    it means "this executor kind cannot run here", not "the app under test failed"."""


class ExecutorRuntimeError(Exception):
    """A RUNTIME failure during capture: app won't start, readiness timeout, a blocking
    step can't execute, capture impossible, or navigation outside ``allowed_origins``.
    The driver maps this to ``gate_hard_fail`` (resumable: re-run / accept / abort).
    NOT raised for a captured assertion failure — that is a ``CriterionResult`` with
    ``executor_status="fail"`` and ``exit_code`` 0."""


class BrowserExecutor(abc.ABC):
    """Capture-runner ABC. One concrete executor binds one ``kind`` of evidence runner
    (deterministic local-HTTP, or a real gated browser) behind a single ``run``."""

    #: stable runner id, e.g. "local_http", "playwright".
    kind = "abstract"

    @abc.abstractmethod
    def run(self, contract: dict, checklist: dict, evidence_dir: str,
            env: dict) -> ExecutorResult:
        """Start the app per ``contract``, run the declared journeys covering every
        ``checklist`` criterion, capture artifacts into ``evidence_dir`` (a STAGING dir
        the driver owns), shut the app down, and return an :class:`ExecutorResult`.

        Contract honored (the fail-closed core, restated):
          - captured assertion failure → ``CriterionResult(executor_status="fail")`` +
            full evidence, KEEP GOING, ``exit_code`` stays 0;
          - runtime failure → raise ``ExecutorRuntimeError``;
          - runtime unavailable → raise ``ExecutorUnavailable``;
          - NEVER emit a milestone verdict (only per-criterion observations).
        """
        raise NotImplementedError


# ===========================================================================
# DOM/text parsing for the offline path — stdlib html.parser, no third-party deps.
# ===========================================================================
class _DOMIndex(HTMLParser):
    """A tiny, deterministic DOM index over a response body.

    Captures, per element: its ``id`` attribute, tag, attributes, and the concatenated
    text directly inside it. Enough for the executor's ``assert_text`` (substring of the
    page or of a selected element) and ``assert_selector`` (an ``#id`` / ``tag`` exists).
    Intentionally minimal — we parse ONLY what the offline asserts need, and the index is
    a pure function of the bytes (so the derived snapshot is reproducible).
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        #: id -> {"tag", "attrs": {..}, "text": ".."}
        self.by_id: dict = {}
        #: every tag name seen (for bare-tag selectors).
        self.tags: set = set()
        #: full visible text of the document, whitespace-normalized at the end.
        self._text_parts: list = []
        self._open_ids: list = []  # stack of ids whose text we are accumulating

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        ad = {k: (v if v is not None else "") for k, v in attrs}
        el_id = ad.get("id")
        if el_id:
            self.by_id[el_id] = {"tag": tag, "attrs": ad, "text": ""}
            self._open_ids.append(el_id)

    def handle_endtag(self, tag):
        if self._open_ids:
            self._open_ids.pop()

    def handle_data(self, data):
        self._text_parts.append(data)
        for el_id in self._open_ids:
            self.by_id[el_id]["text"] += data

    def document_text(self) -> str:
        """Whitespace-normalized full document text (deterministic)."""
        return " ".join("".join(self._text_parts).split())


def _normalize_snapshot(method: str, url_path: str, status: int, body: str,
                        content_type: str) -> str:
    """Build a DETERMINISTIC text "screenshot" of one response.

    NOT pixels — a normalized, timestamp-free DOM/text snapshot the driver can hash.
    For HTML we record status + a sorted list of element ids and the normalized document
    text; for non-HTML (JSON sub-resources) we record the status + the body verbatim.
    The format is stable across runs given identical bytes, which is the whole point.
    """
    lines = [f"REQUEST {method} {url_path}", f"STATUS {status}",
             f"CONTENT_TYPE {content_type or ''}"]
    if "html" in (content_type or "").lower() or body.lstrip().startswith("<"):
        dom = _DOMIndex()
        try:
            dom.feed(body)
        except Exception:  # pragma: no cover - html.parser is very lenient
            pass
        ids = sorted(dom.by_id.keys())
        lines.append("ELEMENT_IDS " + " ".join(ids))
        for el_id in ids:
            el = dom.by_id[el_id]
            text = " ".join(el["text"].split())
            lines.append(f"#{el_id} <{el['tag']}> {text}")
        lines.append("TEXT " + dom.document_text())
    else:
        lines.append("BODY")
        lines.append(body)
    return "\n".join(lines) + "\n"


# ===========================================================================
# LocalHttpExecutor — deterministic, offline, stdlib-only.
# ===========================================================================
class LocalHttpExecutor(BrowserExecutor):
    """Deterministic offline executor: starts the fixture app as a subprocess, drives
    journeys over stdlib HTTP, asserts DOM/text/state/console/network, captures evidence.

    The "browser" is an HTTP client with a cookie-less but explicit redirect policy: we
    follow a 303 to ``/result`` (POST/redirect/GET) by issuing the GET ourselves, so a
    navigate to a form-post target lands on the result page exactly as a browser would.
    Capture is client-side: every request's ``{method, url, status}`` goes into
    ``network.json``; the app's ``/__console`` sink → ``console.json``; ``/__state`` →
    ``backend-state-refs.json``. Each navigate/step writes a normalized snapshot.
    """

    kind = "local_http"

    # Default readiness/shutdown bounds (seconds) when the contract omits them. Small,
    # because the fixture starts near-instantly; a real app would set these in-contract.
    _DEFAULT_READINESS_TIMEOUT = 10.0
    _DEFAULT_POLL_INTERVAL = 0.05
    _SHUTDOWN_GRACE = 5.0

    def run(self, contract: dict, checklist: dict, evidence_dir: str,
            env: dict) -> ExecutorResult:
        os.makedirs(evidence_dir, exist_ok=True)
        os.makedirs(os.path.join(evidence_dir, "screenshots"), exist_ok=True)

        # The driver supplies evidence_dir; we track every file we touch here so the
        # returned `artifacts` list is exact (the driver hashes precisely this set).
        written: list = []

        # Resolved-contract artifact (written up front so even an early runtime failure
        # leaves a record of WHAT we were asked to run).
        self._write_json(evidence_dir, "executor-config.json", contract, written)

        # Per-run network/console/state capture sinks (accumulated, flushed at the end).
        network_log: list = []

        base_url = contract.get("base_url", "")
        allowed_origins = contract.get("allowed_origins") or []

        proc, start_log_rel, host, port = self._start_app(
            contract, evidence_dir, env, written)
        stop_log_rel = "app-stop.log"
        try:
            self._await_readiness(contract, host, port, proc, evidence_dir,
                                  start_log_rel)
            criteria = self._run_journeys(
                contract, checklist, evidence_dir, base_url, allowed_origins,
                host, port, network_log, written)
        finally:
            # Always attempt a clean shutdown + capture the stop log, even on a
            # runtime error mid-journey (so the failure still has app-stop evidence).
            self._stop_app(proc, evidence_dir, stop_log_rel, written)

        # Flush the client-side network capture (deterministic order = request order).
        self._write_json(evidence_dir, "network.json", network_log, written)

        return ExecutorResult(
            exit_code=0,                  # the executor RAN CLEANLY (criteria may 'fail')
            criteria=criteria,
            artifacts=sorted(set(written)),
            app_start_log=start_log_rel,
            app_stop_log=stop_log_rel,
            notes=f"local_http executor over {base_url!r}",
        )

    # -- app lifecycle ----------------------------------------------------------- #
    def _start_app(self, contract: dict, evidence_dir: str, env: dict,
                   written: list):
        """Launch the app per ``contract['app_start_cmd']`` as a subprocess.

        Passes PORT/STORE/MODE through the child env (the executor OWNS the process —
        ``shutdown.process_owned``). stdout/stderr are redirected to ``app-start.log``
        (the readiness probe is HTTP, so we do not need to scrape stdout). A launch that
        cannot even spawn the process → ``ExecutorRuntimeError`` (app won't start).
        """
        cmd = contract.get("app_start_cmd")
        if not cmd:
            raise ExecutorRuntimeError("executor-contract has no app_start_cmd")
        host, port = self._host_port(contract)

        child_env = dict(os.environ)
        child_env.update(env or {})
        # Surface the resolved wiring to the child via env (the fixture reads --port etc.
        # from argv, but a real app commonly reads env; we provide both channels).
        child_env.setdefault("PORT", str(port))
        child_env.setdefault("STORE", str(contract.get("store", "")))
        child_env.setdefault("MODE", str(contract.get("mode", "normal")))

        start_log_rel = "app-start.log"
        start_log_abs = os.path.join(evidence_dir, start_log_rel)
        try:
            log_fh = open(start_log_abs, "w", encoding="utf-8")
        except OSError as exc:
            raise ExecutorRuntimeError(f"cannot open app-start.log: {exc}") from exc
        written.append(start_log_rel)
        try:
            proc = subprocess.Popen(  # noqa: S603 - cmd is a fixed list from the contract
                cmd if isinstance(cmd, list) else [cmd],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=child_env,
                cwd=contract.get("cwd") or None,
            )
        except (OSError, ValueError) as exc:
            log_fh.close()
            raise ExecutorRuntimeError(
                f"app failed to start ({cmd!r}): {exc}") from exc
        # Keep the log file handle on the proc so _stop_app can close it.
        proc._aidazi_log_fh = log_fh  # type: ignore[attr-defined]
        return proc, start_log_rel, host, port

    def _await_readiness(self, contract: dict, host: str, port: int,
                         proc, evidence_dir: str, start_log_rel: str) -> None:
        """Poll the readiness URL (relative → expect HTTP 200) up to a timeout.

        A process that EXITS before becoming ready, or a readiness URL that never returns
        200 within the timeout → ``ExecutorRuntimeError`` (app won't start / readiness
        timeout). We re-read the start log into the message so the failure is diagnosable.
        """
        readiness = contract.get("readiness") or {}
        rel_url = readiness.get("url", "/")
        timeout = float(readiness.get("timeout_seconds",
                                      self._DEFAULT_READINESS_TIMEOUT))
        deadline = time.monotonic() + timeout
        last_err = "no response"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise ExecutorRuntimeError(
                    f"app exited (code {proc.returncode}) before readiness; "
                    f"see {start_log_rel}: {self._tail(evidence_dir, start_log_rel)}")
            try:
                status, _body, _ct = self._http("GET", host, port, rel_url)
                if status == 200:
                    return
                last_err = f"readiness returned HTTP {status}"
            except (OSError, http.client.HTTPException) as exc:
                last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(self._DEFAULT_POLL_INTERVAL)
        raise ExecutorRuntimeError(
            f"readiness timeout after {timeout}s polling {rel_url!r} "
            f"(last: {last_err})")

    def _stop_app(self, proc, evidence_dir: str, stop_log_rel: str,
                  written: list) -> None:
        """Terminate the process and write ``app-stop.log`` (the shutdown record).

        Best-effort and deterministic in CONTENT (we record the action + returncode, not
        a timestamp). A process that ignores SIGTERM is escalated to kill after a grace
        period. Shutdown failure is recorded but does not itself raise (the journey result
        already stands; the driver still gets a stop log)."""
        action = "terminate"
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=self._SHUTDOWN_GRACE)
                except subprocess.TimeoutExpired:
                    action = "kill"
                    proc.kill()
                    proc.wait(timeout=self._SHUTDOWN_GRACE)
            returncode = proc.returncode
        except Exception as exc:  # pragma: no cover - defensive
            action, returncode = "error", repr(exc)
        finally:
            log_fh = getattr(proc, "_aidazi_log_fh", None)
            if log_fh is not None:
                try:
                    log_fh.close()
                except Exception:  # pragma: no cover
                    pass
        stop_log_abs = os.path.join(evidence_dir, stop_log_rel)
        # Deterministic content: action + returncode, NO timestamp.
        with open(stop_log_abs, "w", encoding="utf-8") as fh:
            fh.write(f"shutdown action={action} returncode={returncode}\n")
        if stop_log_rel not in written:
            written.append(stop_log_rel)

    # -- journeys / assertions --------------------------------------------------- #
    def _run_journeys(self, contract: dict, checklist: dict, evidence_dir: str,
                      base_url: str, allowed_origins: list, host: str, port: int,
                      network_log: list, written: list) -> list:
        """Run every journey/step in the contract, capturing evidence + per-criterion
        observations. Console + backend state are read once at the end of journeys and
        any deferred console/state assertions are resolved against those captures.

        Result assembly is keyed by ``criterion_id`` so the returned list maps 1:1 onto
        the signed checklist's criteria. A checklist criterion with no executable step
        lands as ``executor_status="skipped"`` (the driver/consistency-gate treats a
        coverage gap as non-PASS — it never silently drops).
        """
        # criterion_id -> CriterionResult (the running record we fill in)
        results: dict = {}
        for c in checklist.get("criteria", []):
            cid = c.get("criterion_id", "")
            results[cid] = CriterionResult(
                criterion_id=cid, criterion=c.get("criterion", ""),
                action_performed="", observed_result="(no step executed)",
                evidence_refs=[], executor_status="skipped")

        # `last_dom` is the DOM index of the most recent navigate (asserts target it).
        last_dom: Optional[_DOMIndex] = None
        last_snapshot_ref: Optional[str] = None
        # console/state captured lazily; many contracts assert them only at the end.
        console_ref: Optional[str] = None
        state_ref: Optional[str] = None
        console_msgs: Optional[list] = None
        backend_state: Optional[dict] = None

        step_counter = {"n": 0}

        def capture_console():
            nonlocal console_ref, console_msgs
            if console_ref is None:
                console_msgs = self._read_console(contract, host, port)
                console_ref = "console.json"
                self._write_json(evidence_dir, console_ref, console_msgs, written)
            return console_msgs

        def capture_state():
            nonlocal state_ref, backend_state
            if state_ref is None:
                backend_state = self._read_state(contract, host, port)
                state_ref = "backend-state-refs.json"
                self._write_json(evidence_dir, state_ref, backend_state, written)
            return backend_state

        for journey in contract.get("journeys", []):
            for step in journey.get("steps", []):
                action = step.get("action")
                cid = step.get("criterion_id", "")
                critical = bool(step.get("critical", False))
                res = results.get(cid)
                if res is None:
                    # A step naming a criterion absent from the signed checklist is a
                    # CONTRACT/CHECKLIST mismatch — fail closed (blocking, runtime).
                    raise ExecutorRuntimeError(
                        f"step references criterion_id {cid!r} absent from the "
                        f"functional-checklist (contract/checklist mismatch)")

                if action == "navigate":
                    last_dom, last_snapshot_ref = self._do_navigate(
                        step, contract, evidence_dir, base_url, allowed_origins,
                        host, port, network_log, written, step_counter, res, critical)
                elif action == "fill":
                    # Form fields are carried to the next click/submit; a fill is a
                    # deterministic no-network step (recorded as performed).
                    self._do_fill(step, res, last_snapshot_ref)
                elif action == "click":
                    last_dom, last_snapshot_ref = self._do_click(
                        step, contract, evidence_dir, base_url, allowed_origins,
                        host, port, network_log, written, step_counter, res, critical)
                elif action == "assert_text":
                    self._assert_text(step, last_dom, res, last_snapshot_ref, critical)
                elif action == "assert_selector":
                    self._assert_selector(step, last_dom, res, last_snapshot_ref,
                                          critical)
                elif action == "assert_state":
                    self._assert_state(step, capture_state(), res, state_ref, critical)
                elif action == "assert_no_console_error":
                    self._assert_no_console_error(step, capture_console(), res,
                                                  console_ref, critical)
                elif action == "assert_request_ok":
                    self._assert_request_ok(step, network_log, res, res.evidence_refs,
                                            critical)
                else:
                    raise ExecutorRuntimeError(
                        f"unknown executor step action {action!r}")

        return [results[c.get("criterion_id", "")]
                for c in checklist.get("criteria", [])]

    # -- individual actions ------------------------------------------------------ #
    def _do_navigate(self, step, contract, evidence_dir, base_url, allowed_origins,
                     host, port, network_log, written, step_counter, res, critical):
        url = step.get("url", "/")
        self._enforce_origin(url, base_url, allowed_origins)
        rel = self._to_relative(url, base_url)
        status, body, ct = self._http_capture(
            "GET", host, port, rel, network_log)
        dom, snap_ref = self._snapshot("GET", rel, status, body, ct, step,
                                       evidence_dir, written, step_counter)
        # A bare navigate observes 'pass' (it reached the page); content asserts that
        # follow refine the status. A 5xx on a navigate is a runtime issue ONLY if the
        # step is the blocking entry; otherwise it is captured for the assert steps.
        self._record(res, "pass" if status < 500 else "fail",
                     action=f"navigate {url}", observed=f"HTTP {status} at {rel}",
                     refs=[snap_ref])
        return dom, snap_ref

    def _do_click(self, step, contract, evidence_dir, base_url, allowed_origins,
                  host, port, network_log, written, step_counter, res, critical):
        """A click that submits the form (the only interactive control the fixture has).

        Drives ``POST {submit_url}`` with the accumulated form fields, follows a 303 to
        ``/result`` (POST/redirect/GET) by issuing the GET ourselves, and snapshots the
        landed page. A non-form click (no ``submit_url``) is recorded as performed.
        """
        submit_url = step.get("submit_url") or step.get("url")
        if not submit_url:
            self._record(res, "pass", action=f"click {step.get('selector', '')}",
                         observed="click (no navigation)")
            return None, None
        self._enforce_origin(submit_url, base_url, allowed_origins)
        rel = self._to_relative(submit_url, base_url)
        form = step.get("form") or {}
        body_bytes = urllib.parse.urlencode(form).encode("utf-8")
        status, body, ct, location = self._http_capture(
            "POST", host, port, rel, network_log, body=body_bytes,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            want_location=True)
        landed_rel, landed_status, landed_body, landed_ct = rel, status, body, ct
        if status in (301, 302, 303, 307, 308) and location:
            self._enforce_origin(location, base_url, allowed_origins)
            landed_rel = self._to_relative(location, base_url)
            landed_status, landed_body, landed_ct = self._http_capture(
                "GET", host, port, landed_rel, network_log)
        dom, snap_ref = self._snapshot(
            "GET", landed_rel, landed_status, landed_body, landed_ct, step,
            evidence_dir, written, step_counter)
        self._record(res, "pass" if landed_status < 500 else "fail",
                     action=f"click {step.get('selector', '')} → {landed_rel}",
                     observed=f"HTTP {landed_status} at {landed_rel}", refs=[snap_ref])
        return dom, snap_ref

    def _do_fill(self, step, res, last_snapshot_ref):
        self._record(res, "pass",
                     action=(f"fill {step.get('selector', '')}="
                             f"{step.get('value', '')!r}"),
                     observed="field set",
                     refs=[last_snapshot_ref] if last_snapshot_ref else [])

    def _assert_text(self, step, dom, res, snap_ref, critical):
        expected = step.get("text", step.get("expected", ""))
        selector = step.get("selector")
        if dom is None:
            self._fail(res, f"assert_text {expected!r}", "no page captured yet",
                       snap_ref, critical, runtime=True)
            return
        haystack = self._selector_text(dom, selector) if selector else dom.document_text()
        ok = expected in (haystack or "")
        action = (f"assert_text {expected!r}"
                  + (f" in {selector}" if selector else ""))
        observed = (f"found {expected!r}" if ok
                    else f"{expected!r} NOT in {(haystack or '')[:120]!r}")
        self._record(res, "pass" if ok else "fail", action=action, observed=observed,
                     refs=[snap_ref] if snap_ref else [])

    def _assert_selector(self, step, dom, res, snap_ref, critical):
        selector = step.get("selector", "")
        if dom is None:
            self._fail(res, f"assert_selector {selector!r}", "no page captured yet",
                       snap_ref, critical, runtime=True)
            return
        ok = self._selector_present(dom, selector)
        self._record(res, "pass" if ok else "fail",
                     action=f"assert_selector {selector!r}",
                     observed=("present" if ok else "absent"),
                     refs=[snap_ref] if snap_ref else [])

    def _assert_state(self, step, backend_state, res, state_ref, critical):
        key = step.get("key")
        expected = step.get("expected")
        actual = (backend_state or {}).get(key) if key is not None else backend_state
        ok = (actual == expected)
        self._record(res, "pass" if ok else "fail",
                     action=f"assert_state {key}={expected!r}",
                     observed=(f"backend {key}={actual!r}"
                               + ("" if ok else " (MISMATCH)")),
                     refs=[state_ref] if state_ref else [])

    def _assert_no_console_error(self, step, console_msgs, res, console_ref, critical):
        errors = [m for m in (console_msgs or [])
                  if str(m.get("level", "")).lower() == "error"]
        ok = not errors
        observed = ("no console errors" if ok
                    else f"{len(errors)} console error(s): "
                         f"{errors[0].get('text', '')[:120]!r}")
        self._record(res, "pass" if ok else "fail",
                     action="assert_no_console_error", observed=observed,
                     refs=[console_ref] if console_ref else [])

    def _assert_request_ok(self, step, network_log, res, _refs, critical):
        """Assert a captured request did NOT 5xx. ``url`` (substring) selects which
        recorded request(s) to check; a 5xx on any match → 'fail' (captured, not runtime).
        Network is always captured in network.json, so the ref is fixed."""
        url_sub = step.get("url", "")
        matches = [r for r in network_log if url_sub in r.get("url", "")]
        bad = [r for r in matches if int(r.get("status", 0)) >= 500]
        if not matches:
            # Asserting a request that never happened is a captured failure (the journey
            # did not exercise it), not a runtime fault.
            self._record(res, "fail", action=f"assert_request_ok {url_sub!r}",
                         observed="no matching request was captured",
                         refs=["network.json"])
        else:
            ok = not bad
            observed = ("all matching requests < 500" if ok
                        else f"{len(bad)} request(s) 5xx: "
                             f"{bad[0].get('status')} {bad[0].get('url')}")
            self._record(res, "pass" if ok else "fail",
                         action=f"assert_request_ok {url_sub!r}", observed=observed,
                         refs=["network.json"])

    # -- capture primitives ------------------------------------------------------ #
    def _snapshot(self, method, rel, status, body, ct, step, evidence_dir, written,
                  step_counter):
        """Write a deterministic ``screenshots/<step>.snapshot.txt`` and return
        ``(_DOMIndex, relpath)``. ``<step>`` is the step id (or a monotonic counter) so
        repeated navigations never clobber each other."""
        step_counter["n"] += 1
        label = self._safe(step.get("id") or step.get("criterion_id")
                           or f"step{step_counter['n']:03d}")
        rel_path = os.path.join("screenshots", f"{label}.snapshot.txt")
        abs_path = os.path.join(evidence_dir, rel_path)
        snap = _normalize_snapshot(method, rel, status, body, ct)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(snap)
        if rel_path not in written:
            written.append(rel_path)
        dom = _DOMIndex()
        try:
            dom.feed(body)
        except Exception:  # pragma: no cover
            pass
        return dom, rel_path

    def _read_console(self, contract, host, port) -> list:
        rel = (contract.get("console") or {}).get("url", "/__console")
        try:
            status, body, _ct = self._http("GET", host, port, rel)
        except (OSError, http.client.HTTPException) as exc:
            raise ExecutorRuntimeError(f"cannot read console at {rel!r}: {exc}") from exc
        if status != 200:
            raise ExecutorRuntimeError(f"console sink {rel!r} returned HTTP {status}")
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise ExecutorRuntimeError(f"console sink {rel!r} is not JSON: {exc}") from exc
        return data if isinstance(data, list) else [data]

    def _read_state(self, contract, host, port) -> dict:
        rel = (contract.get("state") or {}).get("url", "/__state")
        try:
            status, body, _ct = self._http("GET", host, port, rel)
        except (OSError, http.client.HTTPException) as exc:
            raise ExecutorRuntimeError(f"cannot read state at {rel!r}: {exc}") from exc
        if status != 200:
            raise ExecutorRuntimeError(f"state endpoint {rel!r} returned HTTP {status}")
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise ExecutorRuntimeError(f"state endpoint {rel!r} is not JSON: {exc}") from exc
        return data if isinstance(data, dict) else {"value": data}

    # -- HTTP --------------------------------------------------------------------- #
    def _http(self, method, host, port, rel_url, body=None, headers=None,
              want_location=False):
        """One stdlib HTTP round-trip. Returns ``(status, body_text, content_type)`` or,
        when ``want_location``, ``(status, body_text, content_type, location_header)``.
        Does NOT follow redirects (the caller decides) and does NOT record to the network
        log (use ``_http_capture`` for capture-recorded requests)."""
        conn = http.client.HTTPConnection(host, port, timeout=10)
        try:
            conn.request(method, rel_url, body=body, headers=headers or {})
            resp = conn.getresponse()
            data = resp.read().decode("utf-8", errors="replace")
            ct = resp.getheader("Content-Type", "")
            loc = resp.getheader("Location", "")
            status = resp.status
        finally:
            conn.close()
        if want_location:
            return status, data, ct, loc
        return status, data, ct

    def _http_capture(self, method, host, port, rel_url, network_log, body=None,
                      headers=None, want_location=False):
        """Like ``_http`` but RECORDS ``{method, url, status}`` into ``network_log``
        (the client-side network capture). Every journey request goes through here."""
        result = self._http(method, host, port, rel_url, body=body, headers=headers,
                            want_location=want_location)
        status = result[0]
        network_log.append({"method": method, "url": rel_url, "status": int(status)})
        return result

    # -- origin / url policy ------------------------------------------------------ #
    def _enforce_origin(self, url: str, base_url: str, allowed_origins: list) -> None:
        """Refuse to navigate outside ``allowed_origins`` → ``ExecutorRuntimeError``.

        A RELATIVE url inherits ``base_url``'s origin (always in-policy). An ABSOLUTE url
        must have a scheme+host origin present in ``allowed_origins``. This is the
        executor's containment boundary — it never reaches out to the open internet."""
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme and not parsed.netloc:
            return  # relative → same origin as base_url (in policy by construction)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        norm_allowed = {self._normalize_origin(o) for o in (allowed_origins or [])}
        if base_url:
            norm_allowed.add(self._normalize_origin(base_url))
        if self._normalize_origin(origin) not in norm_allowed:
            raise ExecutorRuntimeError(
                f"navigation to {origin!r} is outside allowed_origins "
                f"{sorted(norm_allowed)}")

    @staticmethod
    def _normalize_origin(url: str) -> str:
        p = urllib.parse.urlparse(url)
        return f"{p.scheme}://{p.netloc}"

    @staticmethod
    def _to_relative(url: str, base_url: str) -> str:
        """Map an absolute-or-relative url to the path+query the HTTP client uses."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme or parsed.netloc:
            rel = parsed.path or "/"
            if parsed.query:
                rel += "?" + parsed.query
            return rel
        return url if url.startswith("/") else "/" + url

    def _host_port(self, contract: dict):
        base = contract.get("base_url", "")
        p = urllib.parse.urlparse(base)
        host = p.hostname or "127.0.0.1"
        port = p.port or int(contract.get("port") or 0)
        if not port:
            raise ExecutorRuntimeError(
                "executor-contract base_url has no port and no explicit port given")
        return host, port

    # -- DOM selector helpers ---------------------------------------------------- #
    @staticmethod
    def _selector_present(dom: _DOMIndex, selector: str) -> bool:
        if selector.startswith("#"):
            return selector[1:] in dom.by_id
        return selector in dom.tags

    @staticmethod
    def _selector_text(dom: _DOMIndex, selector: str) -> str:
        if selector and selector.startswith("#"):
            el = dom.by_id.get(selector[1:])
            return " ".join(el["text"].split()) if el else ""
        # bare tag selector → no single text node; fall back to whole-doc text.
        return dom.document_text()

    # -- small utilities --------------------------------------------------------- #
    @staticmethod
    def _record(res: CriterionResult, status: str, *, action: str, observed: str,
                refs=None) -> None:
        """Fold ONE step's observation into the criterion record MONOTONICALLY (Codex impl
        r2 BLOCKING-1). Evidence refs ALWAYS merge (a failing step's snapshot is never
        dropped). The status + description update ONLY when the new observation is AT LEAST
        as severe as the recorded one (error>fail>pass>skipped) — so a later passing step
        can NEVER downgrade a captured fail/error for the SAME criterion_id back to pass.
        A captured observed failure therefore cannot be silently erased, and the
        consistency gate (e2e_stage.check_acceptance_consistency) sees the true outcome."""
        res.evidence_refs = LocalHttpExecutor._merge_refs(res.evidence_refs, refs or [])
        if _STATUS_SEVERITY.get(status, 0) >= _STATUS_SEVERITY.get(
                res.executor_status, 0):
            res.executor_status = status
            res.action_performed = action
            res.observed_result = observed

    @staticmethod
    def _fail(res: CriterionResult, action: str, observed: str, snap_ref,
              critical: bool, *, runtime: bool) -> None:
        """Record a captured 'fail' (or raise if the missing precondition is a BLOCKING
        runtime fault). An assert that cannot run because the journey never produced a
        page to assert against is a CONTRACT/runtime error, not a product defect."""
        if runtime:
            raise ExecutorRuntimeError(f"{action}: {observed}")
        LocalHttpExecutor._record(res, "fail", action=action, observed=observed,
                                  refs=[snap_ref] if snap_ref else [])

    @staticmethod
    def _merge_refs(existing: list, new: list) -> list:
        out = list(existing)
        for r in new:
            if r and r not in out:
                out.append(r)
        return out

    def _write_json(self, evidence_dir: str, rel_name: str, obj, written: list) -> None:
        """Write a deterministic JSON artifact (sorted keys, no timestamps) and track it."""
        abs_path = os.path.join(evidence_dir, rel_name)
        if os.path.dirname(rel_name):  # a nested artifact (e.g. under screenshots/)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, sort_keys=True, indent=2)
        if rel_name not in written:
            written.append(rel_name)

    @staticmethod
    def _safe(label: str) -> str:
        return "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in str(label))

    @staticmethod
    def _tail(evidence_dir: str, rel: str, limit: int = 500) -> str:
        try:
            with open(os.path.join(evidence_dir, rel), "r", encoding="utf-8") as fh:
                return fh.read()[-limit:].strip()
        except OSError:
            return "(start log unavailable)"


# ===========================================================================
# PlaywrightExecutor — GATED real-browser runner (never exercised in offline CI).
# ===========================================================================
class PlaywrightExecutor(BrowserExecutor):
    """Real-browser executor (pixels, real console/network). GATED OFF by default.

    The POINT of this class in v1 is the GATE + the interface conformance, not a working
    playwright driver — real-browser wiring is an adopter concern (§7, §10: no real
    browser in offline CI). It raises ``ExecutorUnavailable`` UNLESS BOTH hold:
      - ``os.environ["AIDAZI_E2E_PLAYWRIGHT"] == "1"`` (explicit opt-in), AND
      - ``import playwright`` succeeds (the runtime is actually installed).
    When enabled, the driving body is a clearly-marked minimal stub that still raises
    ``ExecutorUnavailable`` (an adopter replaces it with real Playwright capture that
    produces the SAME ``ExecutorResult`` shape — observations only, never a verdict).
    """

    kind = "playwright"

    def __init__(self):
        self._enabled = os.environ.get("AIDAZI_E2E_PLAYWRIGHT") == "1"

    def run(self, contract: dict, checklist: dict, evidence_dir: str,
            env: dict) -> ExecutorResult:
        if not self._enabled:
            raise ExecutorUnavailable(
                "PlaywrightExecutor is gated off (set AIDAZI_E2E_PLAYWRIGHT=1 to enable "
                "the real-browser path; it is never run in offline CI)")
        try:
            import playwright  # noqa: F401  (presence check only)
        except Exception as exc:  # pragma: no cover - exercised only when enabled
            raise ExecutorUnavailable(
                f"playwright runtime not importable: {exc}") from exc
        # --- below here is NEVER exercised in offline CI ----------------------- #
        # Adopter wiring goes here: launch a real browser, drive `contract['journeys']`,
        # capture real screenshots/console/network into `evidence_dir`, and return an
        # ExecutorResult with per-criterion observations (NEVER a milestone verdict).
        raise ExecutorUnavailable(  # pragma: no cover
            "PlaywrightExecutor real-browser driving is an adopter-supplied stub in v1")


# ===========================================================================
# Factory
# ===========================================================================
def make_executor(kind: str) -> BrowserExecutor:
    """Map an executor ``kind`` string → a concrete :class:`BrowserExecutor`.

    ``"local_http"`` → :class:`LocalHttpExecutor` (deterministic offline);
    ``"playwright"`` → :class:`PlaywrightExecutor` (env+import gated);
    anything else → ``ValueError`` (fail closed on an unknown runner — the driver must
    not silently pick a default capture tier)."""
    if kind == "local_http":
        return LocalHttpExecutor()
    if kind == "playwright":
        return PlaywrightExecutor()
    raise ValueError(f"unknown executor kind {kind!r} "
                     f"(expected 'local_http' or 'playwright')")

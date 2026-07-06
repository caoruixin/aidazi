#!/usr/bin/env python3
"""Phase-5 canary workspace runner — executed INSIDE one scratch adopter, importing
the VENDORED engine-kit (never the source repo's), driving ONE loop with EXACTLY ONE
real (billable) spawn per invocation (§7.0: one workspace-per-spawn scratch adopter).

Modes (config JSON on argv[1]; result JSON to argv[2]):
  alpha — full_chain_guided Driver: research=Mock (free; the frozen brief bytes are
          pre-seeded at docs/briefs/<subsprint>__brief.md by the harness), gate1 signed
          by a canned resolver, deliver = SPLIT adapter (call 0 → the REAL claude_code
          decompose = the one billable spawn; later calls → canned close), dev/review =
          Mock. The produced plan is read back from the driver state.
  dev   — delivery_only Driver: dev = REAL claude_code (the one billable spawn;
          cwd = the workspace, so artifacts land there), review/deliver = Mock. The
          frozen task bytes are pre-seeded at compact/<subsprint>-dev-prompt.md
          (strict-prompt source); arm A's charter carries the signed mission profile
          task_signals=["interaction"], arm B's carries none.
  offline_dev / offline_alpha — the same plumbing with ALL Mock adapters (zero
          billables) for the committed harness dry-run proof.

The runner only REPORTS (result JSON + the driver's own on-disk evidence: audit
ledger, prompt/output/__stream transcripts, state.json); scoring/thresholds live in
the harness + scorers (source side). Determinism: injected tick clock; no wall clock.
"""
import json
import os
import sys

CFG = json.load(open(sys.argv[1], encoding="utf-8"))
WS = os.path.dirname(os.path.abspath(sys.argv[1]))
AIDAZI = CFG.get("aidazi_root") or os.path.join(WS, "aidazi")
sys.path.insert(0, os.path.join(AIDAZI, "engine-kit", "scheduling"))
import run_loop as rl  # noqa: E402,F401 — VENDORED; wires its own sys.path (kept for parity)
import driver as drv  # noqa: E402
from adapters import MockAdapter, ClaudeCodeAdapter, SpawnResult  # noqa: E402
from adapters.base import InvocationTelemetry  # noqa: E402


def _clock():
    n = {"i": 0}

    def tick():
        n["i"] += 1
        return "2026-07-07T%02d:%02d:%02dZ" % (n["i"] // 3600, (n["i"] // 60) % 60,
                                               n["i"] % 60)
    return tick


REVIEW = {"decision": "pass", "blocking_count": 0,
          "summary": "no blocking findings", "findings": []}
CLOSE = {"verdict": "A", "blocking_count": 0, "worst_severity": "none",
         "in_scope": True, "next_subsprint": None, "reason": "clean pass"}
RESEARCH = {"artifact": "frozen fixture brief pre-seeded at docs/briefs/ (see harness)"}
MOCK_DEV = {"artifact": "offline dry-run dev artifact"}
# A schema-valid offline decompose plan for the offline_alpha plumbing proof.
MOCK_PLAN = {"sub_sprints": [
    {"id": "s1-settings-form-ui", "objective": "o", "scope_in": ["a"],
     "scope_out": ["b"], "modules": [], "layers": [], "exit_criteria": ["c"],
     "task_signals": ["ui"]},
    {"id": "s2-notification-prefs-ui", "objective": "o", "scope_in": ["a"],
     "scope_out": ["b"], "modules": [], "layers": [], "exit_criteria": ["c"],
     "task_signals": ["ui"]},
    {"id": "s3-persistence-api", "objective": "o", "scope_in": ["a"],
     "scope_out": ["b"], "modules": [], "layers": [], "exit_criteria": ["c"]},
]}


class SplitDeliverAdapter(MockAdapter):
    """Deliver adapter for α: call 0 (the decompose) → the REAL claude_code spawn;
    every later call (close) → the canned CLOSE verdict. Subclasses MockAdapter so
    the driver's strict-prompt detection still sees a NON-mock backend via the
    wrapped real adapter... no — strict mode keys on `not isinstance(a, MockAdapter)`
    over ALL adapters, and the real deliver IS wrapped here; the harness therefore
    passes context allow_real=True explicitly (the other strict enabler), which is
    also the honest flag for a real run."""

    def __init__(self, real):
        super().__init__({("deliver",): CLOSE}, harness=real.harness,
                         provider=real.provider, model=real.model)
        self._real = real
        # NB: named to NEVER shadow MockAdapter's own `_calls` dict — shadowing
        # it crashed the 2026-07-07 live run at the close step AFTER a billed,
        # successful real decompose (see the evidence run's INCIDENT.md #2).
        self._decompose_calls = 0

    def _spawn_impl(self, role, prompt, tools, schema, **kw):
        self._decompose_calls += 1
        if self._decompose_calls == 1:
            return self._real.spawn(role, prompt, tools, schema, **kw)
        return super()._spawn_impl(role, prompt, tools, schema, **kw)


class SeededArtifactMockAdapter(MockAdapter):
    """Offline γ/β plumbing stand-in: 'writes' the pre-baked artifact files into the
    workspace (simulating the real dev session) and reports telemetry with the
    configured read paths, so the offline dry-run exercises artifact collection +
    stream/audit plumbing without any billable."""

    def __init__(self, canned, *, artifact_files=None, read_paths=None, **kw):
        super().__init__(canned, **kw)
        self._artifact_files = artifact_files or {}
        self._read_paths = read_paths

    def _spawn_impl(self, role, prompt, tools, schema, **kw):
        for rel, content in self._artifact_files.items():
            path = os.path.join(WS, rel)
            os.makedirs(os.path.dirname(path) or WS, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        result = super()._spawn_impl(role, prompt, tools, schema, **kw)
        stream = "\n".join(
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": p}}]}})
            for p in (self._read_paths or []))
        telemetry = InvocationTelemetry(
            terminal_attempt=1, terminal_status="ok",
            read_paths=list(self._read_paths) if self._read_paths is not None
            else None,
            observability="observed" if self._read_paths is not None
            else "unobservable",
            raw_stream=stream if os.environ.get("AIDAZI_KEEP_RAW_STREAM") == "1"
            else None)
        return SpawnResult(result=result, telemetry=telemetry)


def _real_claude(role_cfg, cwd):
    return ClaudeCodeAdapter(
        provider="anthropic", model=CFG["model"],
        timeout_seconds=int(CFG.get("timeout_seconds") or 900),
        cwd=cwd)


def _mock(canned, harness="claude_code"):
    return MockAdapter(canned, harness=harness, provider="anthropic", model="m")


def _charter(mode):
    ch = {
        "mission": {"id": CFG["mission_id"], "goal": CFG["mission_goal"]},
        "autonomy": {
            "level": "human_in_the_loop",
            "approved_scope": {
                "subsprint_sequence": ([] if mode.endswith("alpha")
                                       else [CFG["subsprint_id"]]),
                # α: envelope UNSET (plan defines scope) so the frozen α rules are
                # the ONLY pass/fail criteria — the scope-expansion guard cannot
                # halt a schema-valid plan.
            },
        },
        "budget": {"max_api_usd": 0, "max_fix_rounds_total": 2,
                   "max_wall_clock_minutes": 60},
        "tooling": {
            "research": {"harness": "claude_code", "provider": "anthropic",
                         "model": CFG["model"]},
            "deliver": {"harness": "claude_code", "provider": "anthropic",
                        "model": CFG["model"]},
            # Dev: canonical dev binding — workspace_write sandbox, NO tools
            # whitelist (the dev role's default full toolset; §7.0).
            "dev": {"harness": "claude_code", "provider": "anthropic",
                    "model": CFG["model"], "sandbox": "workspace_write"},
            "review": {"harness": "claude_code", "provider": "anthropic",
                       "model": CFG["model"], "tools": ["Read", "Grep", "Glob"]},
            "eval": {"cmd": "true", "timeout_seconds": 30},
        },
    }
    if CFG.get("task_signals") is not None:
        ch["autonomy"]["approved_scope"]["task_signals"] = list(
            CFG["task_signals"])
    return ch


def _resolver(gate_id, context, options):
    return {"choice": "sign", "note": "phase-5 canary (frozen brief)",
            "resolver": "canary-harness"}


def main():
    mode = CFG["mode"]
    out: dict = {"mode": mode}
    run_dir = WS                              # ledger/transcripts inside the ws
    live = mode in ("alpha", "dev")

    # Offline plumbing: the harness composes configs BEFORE the ws exists, so the
    # seeded read path arrives as a placeholder replaced here with THIS workspace's
    # vendored SKILL.md (the same path the driver's telemetry intersection needs).
    skill_md = os.path.join(AIDAZI, "skills", "vendored",
                            "web-interface-guidelines", "SKILL.md")
    offline_reads = CFG.get("offline_read_paths")
    if offline_reads:
        offline_reads = [p.replace("__WS_SKILL_MD__", skill_md)
                         for p in offline_reads]

    if mode in ("alpha", "offline_alpha"):
        offline_plan = CFG.get("offline_plan") or MOCK_PLAN
        # BOTH arms route through SplitDeliverAdapter so the offline dry-run
        # exercises the exact live adapter path (decompose→inner, close→canned)
        # — the 2026-07-07 _calls-shadowing crash lived only on the live branch.
        inner = (_real_claude(None, WS) if live
                 else _mock({("deliver",): offline_plan}))
        deliver = SplitDeliverAdapter(inner)
        adapters = {
            "research": _mock({("research",): RESEARCH}),
            "dev": _mock({("dev",): MOCK_DEV}),
            "review": _mock({("review",): REVIEW}),
            "deliver": deliver,
        }
        d = drv.Driver(_charter(mode), run_dir, adapters,
                       loop_id=CFG["loop_id"], clock=_clock(),
                       context={"allow_real": live},
                       loop_mode=drv.LOOP_MODE_FULL_CHAIN_GUIDED,
                       gate_resolver=_resolver)
    else:
        dev = (_real_claude(None, WS) if live else
               SeededArtifactMockAdapter(
                   {("dev",): MOCK_DEV},
                   artifact_files=CFG.get("offline_artifact_files"),
                   read_paths=offline_reads,
                   harness="claude_code", provider="anthropic", model="m"))
        adapters = {
            "dev": dev,
            "review": _mock({("review",): REVIEW}),
            "deliver": _mock({("deliver",): CLOSE}),
        }
        d = drv.Driver(_charter(mode), run_dir, adapters,
                       loop_id=CFG["loop_id"], clock=_clock(),
                       context={"allow_real": live},
                       repo_dir=WS)

    try:
        final = d.run(subsprint_id=CFG["subsprint_id"])
        out["final_state"] = final.state
        out["history"] = final.history
    except drv.GateHardFail as exc:
        reason = getattr(exc, "reason", "") or str(exc)
        out["gate_hard_fail"] = reason
        out["adapter_error"] = reason.startswith("adapter for role")

    st = d.state
    if st is not None:
        out["planned_subsprints"] = list(st.planned_subsprints or [])
        out["task_signals_digest"] = st.task_signals_digest
        out["subsprint_id"] = st.subsprint_id
    out["audit_ledger"] = os.path.relpath(d.audit_ledger, WS)
    out["transcripts_dir"] = os.path.relpath(d.transcripts_dir, WS)

    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)


if __name__ == "__main__":
    main()

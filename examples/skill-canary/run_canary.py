#!/usr/bin/env python3
"""Phase-5 bounded real/billable canary — EXACT execution of the FROZEN §7
pre-registration (universal-skill-mounting design; frozen bytes in
archive/wp-skill-canary/preregistration/ — this harness never modifies them).

  α  authoring correctness — 3 reps × 2 frozen fixture briefs = 6 REAL decompose
     spawns of the real decompose contract (guided Driver; deliver call 0 = the one
     billable spawn per rep; research/gate1/dev/review/close are mock/canned).
  β  consumption — 3 REAL Dev spawns of the frozen task with signed
     task_signals=["interaction"]; PASS = stream-json Read of the mounted
     web-interface-guidelines/SKILL.md AND audit skill_consumption=observed.
  γ  bounded output-effect — 3 counterbalanced pairs (AB, BA, AB) of REAL Dev
     spawns; deterministic Check-0 + 10-check scorer (scorers.py ≡ the frozen
     gamma-checklist.json, self-verified); pair success = arm-A skill read AND
     score_A ≥ score_B + 2; probe PASS ≥ 2/3 pairs.

BUDGET (frozen): ≤15 planned real spawns (α:6, β:3, γ:6) + ≤2 replacement spawns per
probe for ADAPTER-LEVEL errors only (AdapterError/timeout — NEVER for unwanted
verdicts). >2 adapter errors in one probe ⇒ probe INCONCLUSIVE ⇒ HALT. Any probe
below threshold after its budget ⇒ honest negative outcome, no post-hoc adjustment.

Each repetition gets a FRESH scratch adopter (a real vendor-framework.sh copy of THIS
repo — §7.0; no state reuse) and runs in a SUBPROCESS importing the VENDORED
engine-kit (ws_runner.py). Env per §7.0/G3: AIDAZI_SKILL_CANARY=1 gates --live;
real spawns additionally set AIDAZI_ALLOW_REAL_ADAPTER=1; AIDAZI_KEEP_RAW_STREAM=1
captures evidence. AIDAZI_E2E_EXTERNAL_RUNNER is NEVER set (no external test runner).
Model: claude-sonnet-4-6; 15-minute wall-clock cap per spawn (adapter timeout 900s).

Evidence per rep (copied out of the scratch ws, which is then deleted):
runner-result.json, state.json, the audit ledger, prompt/output/__stream transcripts,
the produced artifact files (β/γ), score.json. Idempotent: a rep whose evidence
already carries runner-result.json + score.json is SKIPPED on re-invocation (crash
resume never re-bills). results.json + budget.json aggregate the run.

CLI:
  python3 run_canary.py --offline-dry-run [--evidence-dir D]   # zero billables
  AIDAZI_SKILL_CANARY=1 python3 run_canary.py --live --evidence-dir D [--probe P]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

import scorers  # noqa: E402
import offline_fixtures  # noqa: E402

_VENDOR_SH = os.path.join(_REPO_ROOT, "engine-kit", "tools", "vendor-framework.sh")
_RUNNER_SRC = os.path.join(_HERE, "ws_runner.py")
_SKILL_ID = "web-interface-guidelines"

MODEL = "claude-sonnet-4-6"          # frozen §7.0
SPAWN_TIMEOUT_S = 900                # frozen §7.0 — 15-minute cap per spawn
SUBPROCESS_TIMEOUT_S = 1200          # runner overhead margin above the adapter cap
PLANNED = {"alpha": 6, "beta": 3, "gamma": 6}
MAX_REPLACEMENTS_PER_PROBE = 2       # frozen §7.0 budgets


def _frozen_task_body() -> str:
    """The dispatched task bytes = everything after the frozen file's `---`
    separator (the file's own preamble says the following text is what is
    dispatched byte-identically)."""
    path = os.path.join(scorers.PREREG_DIR, "gamma-task-prompt.md")
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.strip() == "---":
            body = "".join(lines[i + 1:]).strip() + "\n"
            if "Implement a self-contained sign-up page" not in body:
                raise AssertionError("frozen task body extraction failed")
            return body
    raise AssertionError("frozen gamma-task-prompt.md has no --- separator")


def _frozen_brief(name: str) -> str:
    with open(os.path.join(scorers.PREREG_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def _child_env(*, live: bool) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIDAZI_")}
    env["AIDAZI_KEEP_RAW_STREAM"] = "1"      # §7.0 — authorized evidence capture
    if live:
        env["AIDAZI_SKILL_CANARY"] = "1"
        env["AIDAZI_ALLOW_REAL_ADAPTER"] = "1"
    return env


def _git(args, cwd):
    subprocess.run(["git", "-c", "user.name=canary", "-c", "user.email=c@c",
                    "-c", "commit.gpgsign=false", *args],
                   cwd=cwd, check=True, capture_output=True, text=True)


class Budget:
    """Crash-safe spend ledger: the attempt record is persisted BEFORE each spawn
    launch, so a crash can never lose an attempt (and never re-bills a completed
    rep — completed reps are skipped by their on-disk evidence)."""

    def __init__(self, path: str):
        self.path = path
        self.data = {"attempts": [], "adapter_errors": {},
                     "planned": dict(PLANNED),
                     "max_replacements_per_probe": MAX_REPLACEMENTS_PER_PROBE}
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                self.data = json.load(fh)

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2)

    def real_attempts(self, probe: str) -> int:
        return sum(1 for a in self.data["attempts"]
                   if a["probe"] == probe and a["live"])

    def adapter_errors(self, probe: str) -> int:
        return len(self.data["adapter_errors"].get(probe, []))

    def pre_spawn(self, probe: str, rep_id: str, *, live: bool):
        cap = PLANNED[probe] + MAX_REPLACEMENTS_PER_PROBE
        if live and self.real_attempts(probe) >= cap:
            raise RuntimeError(
                f"BUDGET REFUSAL: probe {probe} would exceed its authorized cap "
                f"({PLANNED[probe]} planned + {MAX_REPLACEMENTS_PER_PROBE} "
                f"replacements)")
        self.data["attempts"].append(
            {"probe": probe, "rep_id": rep_id, "live": live, "status": "launched"})
        self._save()

    def post_spawn(self, rep_id: str, status: str):
        for a in reversed(self.data["attempts"]):
            if a["rep_id"] == rep_id and a["status"] == "launched":
                a["status"] = status
                break
        self._save()

    def record_adapter_error(self, probe: str, rep_id: str) -> int:
        """Keyed by rep_id so a crash-RESUME that re-reads a persisted
        adapter-errored rep never double-counts the frozen error budget."""
        errs = self.data["adapter_errors"].setdefault(probe, [])
        if rep_id not in errs:
            errs.append(rep_id)
            self._save()
        return len(errs)


class ProbeInconclusive(RuntimeError):
    """>2 adapter-level errors in one probe (frozen §7.4) ⇒ HALT and surface."""


class Harness:
    def __init__(self, evidence_dir: str, *, live: bool):
        self.evidence = os.path.abspath(evidence_dir)
        self.live = live
        os.makedirs(self.evidence, exist_ok=True)
        self.budget = Budget(os.path.join(self.evidence, "budget.json"))
        self.contract = scorers.load_gamma_contract()   # self-verifies ≡ scorer
        self.manifest = scorers.load_alpha_manifest()
        self.task_body = _frozen_task_body()

    # ----- workspace construction ------------------------------------------ #
    def _build_ws(self, mode: str) -> str:
        ws = tempfile.mkdtemp(prefix="p5-ws-")
        proc = subprocess.run(["bash", _VENDOR_SH, _REPO_ROOT, ws],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"vendor-framework.sh failed: {proc.stderr}")
        shutil.copy2(_RUNNER_SRC, os.path.join(ws, "ws_runner.py"))
        # Complete the DOCUMENTED vendor onboarding (root-file wiring, §1.1 /
        # adopter_wiring_validator): a scratch adopter is only a REAL adopter
        # deployment shape once the root AGENTS.md (placeholders filled) +
        # CLAUDE.md→@AGENTS.md are present — without them the spawned agent's
        # cold-start chain (incl. the role/verdict-schema discipline the real
        # decompose contract relies on) never loads. This omission caused the
        # live-run α adapter errors on 2026-07-07 (markdown plans instead of
        # JSON verdicts); see the evidence run's INCIDENT.md.
        with open(os.path.join(ws, "aidazi", "AGENTS.md"),
                  encoding="utf-8") as fh:
            agents = fh.read()
        agents = agents.replace("<adopter-name>", "p5-canary-scratch")
        agents = agents.replace("<adopter>/charter.yaml", "charter.yaml")
        with open(os.path.join(ws, "AGENTS.md"), "w", encoding="utf-8") as fh:
            fh.write(agents)
        with open(os.path.join(ws, "CLAUDE.md"), "w", encoding="utf-8") as fh:
            fh.write("@AGENTS.md\n")
        if mode == "alpha":
            os.makedirs(os.path.join(ws, "docs", "briefs"), exist_ok=True)
        else:  # dev workspace: strict compact prompt + a git repo (loop ingress)
            os.makedirs(os.path.join(ws, "compact"), exist_ok=True)
            with open(os.path.join(ws, "compact", "sprint-001-dev-prompt.md"),
                      "w", encoding="utf-8") as fh:
                fh.write("---\ncontext_budget:\n  self_contained: true\n---\n"
                         + self.task_body)
            _git(["init", "-q", "-b", "main"], ws)
            _git(["add", "-A"], ws)
            _git(["commit", "-q", "-m", "canary scratch adopter seed"], ws)
        return ws

    def _run_ws(self, ws: str, cfg: dict) -> dict:
        cfg_path = os.path.join(ws, "p5-cfg.json")
        out_path = os.path.join(ws, "p5-result.json")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        proc = subprocess.run(
            [sys.executable, os.path.join(ws, "ws_runner.py"), cfg_path, out_path],
            cwd=ws, env=_child_env(live=self.live), capture_output=True,
            text=True, timeout=SUBPROCESS_TIMEOUT_S)
        if proc.returncode != 0 or not os.path.isfile(out_path):
            raise RuntimeError(
                f"ws_runner failed rc={proc.returncode}\nSTDOUT:{proc.stdout[-2000:]}"
                f"\nSTDERR:{proc.stderr[-2000:]}")
        with open(out_path, encoding="utf-8") as fh:
            return json.load(fh)

    def _collect(self, ws: str, result: dict, rep_dir: str, *,
                 artifacts: bool) -> None:
        os.makedirs(rep_dir, exist_ok=True)
        with open(os.path.join(rep_dir, "runner-result.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        state = os.path.join(ws, ".orchestrator", "state.json")
        if os.path.isfile(state):
            shutil.copy2(state, os.path.join(rep_dir, "state.json"))
        ledger = os.path.join(ws, result.get("audit_ledger", ""))
        if os.path.isfile(ledger):
            shutil.copy2(ledger, os.path.join(rep_dir,
                                              os.path.basename(ledger)))
        tdir = os.path.join(ws, result.get("transcripts_dir", ""))
        if os.path.isdir(tdir):
            dst = os.path.join(rep_dir, "transcripts")
            shutil.copytree(tdir, dst, dirs_exist_ok=True)
        if artifacts:
            adir = os.path.join(rep_dir, "artifact")
            files = scorers._collect_artifact_files(ws)
            for kind in ("html", "css", "js"):
                for p in files[kind]:
                    rel = os.path.relpath(p, ws)
                    dst = os.path.join(adir, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(p, dst)
            os.makedirs(adir, exist_ok=True)

    # ----- ledger readers ---------------------------------------------------- #
    @staticmethod
    def _events(rep_dir: str) -> list:
        for name in sorted(os.listdir(rep_dir)):
            if name.endswith(".jsonl"):
                events = []
                with open(os.path.join(rep_dir, name), encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            events.append(json.loads(line))
                return events
        return []

    @classmethod
    def _dev_cfg_and_spawn(cls, rep_dir: str):
        events = cls._events(rep_dir)
        cfgs = [e["payload"] for e in events
                if e["type"] == "effective_role_config"
                and e["payload"].get("role") == "dev"]
        spawns = [e["payload"] for e in events
                  if e["type"] == "spawn" and e["payload"].get("role") == "dev"]
        return (cfgs[-1] if cfgs else None), (spawns[-1] if spawns else None)

    @staticmethod
    def _stream_text(rep_dir: str) -> str:
        tdir = os.path.join(rep_dir, "transcripts")
        if not os.path.isdir(tdir):
            return ""
        for name in sorted(os.listdir(tdir)):
            if "stream" in name:
                with open(os.path.join(tdir, name), encoding="utf-8",
                          errors="replace") as fh:
                    return fh.read()
        return ""

    # ----- one repetition ---------------------------------------------------- #
    def _rep(self, probe: str, rep_id: str, mode: str, cfg_extra: dict, *,
             seed_brief: str = None, artifacts: bool = False) -> dict:
        rep_dir = os.path.join(self.evidence, probe, rep_id)
        score_path = os.path.join(rep_dir, "score.json")
        if (os.path.isfile(os.path.join(rep_dir, "runner-result.json"))
                and os.path.isfile(score_path)):
            with open(score_path, encoding="utf-8") as fh:
                return json.load(fh)      # idempotent resume — never re-bill

        ws = self._build_ws("alpha" if mode.endswith("alpha") else "dev")
        try:
            if seed_brief:
                with open(os.path.join(ws, "docs", "briefs",
                                       "sprint-001__brief.md"), "w",
                          encoding="utf-8") as fh:
                    fh.write(seed_brief)
            cfg = {"mode": mode, "model": MODEL,
                   "timeout_seconds": SPAWN_TIMEOUT_S,
                   "subsprint_id": "sprint-001", "loop_id": rep_id,
                   "mission_id": "p5-canary",
                   "mission_goal": "phase-5 frozen canary fixture",
                   **cfg_extra}
            self.budget.pre_spawn(probe, rep_id, live=self.live)
            try:
                result = self._run_ws(ws, cfg)
            except Exception:
                self.budget.post_spawn(rep_id, "harness_error")
                raise
            status = ("adapter_error" if result.get("adapter_error")
                      else "completed")
            self.budget.post_spawn(rep_id, status)
            self._collect(ws, result, rep_dir, artifacts=artifacts)
            score = {"rep_id": rep_id, "ws_path": ws, "status": status,
                     "runner": {k: result.get(k) for k in
                                ("final_state", "gate_hard_fail",
                                 "adapter_error")}}
            with open(score_path, "w", encoding="utf-8") as fh:
                json.dump(score, fh, indent=2)
            return score
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def _run_with_replacement(self, probe: str, rep_base: str, mode: str,
                              cfg_extra: dict, **kw) -> dict:
        """Run one repetition; on an ADAPTER-LEVEL error (the ONLY replacement
        ground — never an unwanted verdict) re-run as `<rep>-r2`/`-r3` while the
        probe stays within its ≤2 replacement budget; a 3rd adapter error is
        INCONCLUSIVE ⇒ HALT (frozen §7.4)."""
        rep_id = rep_base
        for _attempt in range(1 + MAX_REPLACEMENTS_PER_PROBE):
            score = self._rep(probe, rep_id, mode, cfg_extra, **kw)
            if score["status"] != "adapter_error":
                return score
            n = self.budget.record_adapter_error(probe, rep_id)
            if n > MAX_REPLACEMENTS_PER_PROBE:
                raise ProbeInconclusive(
                    f"probe {probe}: >{MAX_REPLACEMENTS_PER_PROBE} adapter-level "
                    f"errors — INCONCLUSIVE per the frozen abort rules; halting")
            rep_id = f"{rep_base}-r{n + 1}"
        raise ProbeInconclusive(f"probe {probe}: replacement budget exhausted")

    # ----- α ------------------------------------------------------------------ #
    def run_alpha(self) -> dict:
        mode = "alpha" if self.live else "offline_alpha"
        vocab = self.manifest["vocab"]
        fixtures = {}
        for fx_name, fixture in sorted(self.manifest["fixtures"].items()):
            brief = _frozen_brief(fixture["brief"])
            cfg_extra: dict = {}
            if not self.live:
                # Offline plumbing: a fixture-conformant mock plan, so the dry run
                # proves scorer + harness against BOTH frozen fixtures.
                cfg_extra["offline_plan"] = {"sub_sprints": [
                    {"id": sid, "objective": "o", "scope_in": ["a"],
                     "scope_out": ["b"], "modules": [], "layers": [],
                     "exit_criteria": ["c"],
                     **({"task_signals": ["ui"]} if kind == "ui" else {})}
                    for sid, kind in fixture["prescribed_subsprints"].items()]}
            reps = []
            n_reps = (self.manifest["repetitions_per_fixture"]
                      if self.live else 1)
            for i in range(1, n_reps + 1):
                rep_base = f"{fx_name}-rep{i}"
                score = self._run_with_replacement(
                    "alpha", rep_base, mode, cfg_extra, seed_brief=brief)
                if "alpha" not in score:
                    rep_dir = os.path.join(self.evidence, "alpha",
                                           score["rep_id"])
                    with open(os.path.join(rep_dir, "runner-result.json"),
                              encoding="utf-8") as fh:
                        result = json.load(fh)
                    plan = {"sub_sprints": result.get("planned_subsprints") or []}
                    if result.get("gate_hard_fail") and not plan["sub_sprints"]:
                        score["alpha"] = {
                            "pass": False,
                            "reason": "no schema-valid plan was produced within "
                                      "this repetition's budget (frozen α rule: "
                                      "the produced plan must validate; an "
                                      "adapter/protocol failure or operator "
                                      "truncation yields no plan): "
                                      + result["gate_hard_fail"][:300]}
                    else:
                        score["alpha"] = scorers.alpha_score_rep(
                            plan, fixture, vocab)
                    with open(os.path.join(rep_dir, "score.json"), "w",
                              encoding="utf-8") as fh:
                        json.dump(score, fh, indent=2)
                reps.append({"rep": score["rep_id"],
                             "pass": bool(score["alpha"].get("pass")),
                             "detail": score["alpha"]})
            passed = sum(1 for r in reps if r["pass"])
            fixtures[fx_name] = {
                "reps": reps, "passed": passed, "total": len(reps),
                "fixture_pass": (passed >= 2 if self.live else passed == len(reps)),
            }
        probe_pass = all(f["fixture_pass"] for f in fixtures.values())
        return {"probe": "alpha", "pass": probe_pass, "fixtures": fixtures}

    # ----- β ------------------------------------------------------------------ #
    def _score_dev_rep(self, score: dict, *, require_arm_a: bool) -> dict:
        rep_dir = os.path.join(self.evidence, score["_probe"], score["rep_id"])
        cfg_evt, spawn_evt = self._dev_cfg_and_spawn(rep_dir)
        skill_md = os.path.join(score["ws_path"], "aidazi", "skills", "vendored",
                                _SKILL_ID, "SKILL.md")
        selected = list((cfg_evt or {}).get("selected_skills") or [])
        expected = (self.contract["expected_signal_selected_skills"]
                    if require_arm_a else [])
        valid = selected == expected
        stream = self._stream_text(rep_dir)
        read = scorers.beta_read_observed(stream, skill_md,
                                          cwd=score["ws_path"])
        consumption = (spawn_evt or {}).get("skill_consumption")
        return {"valid": valid, "selected_skills": selected,
                "expected_selected": expected,
                "signal_source": (cfg_evt or {}).get("signal_source"),
                "stream_read_observed": read["observed"],
                "matched_paths": read["matched_paths"],
                "audit_skill_consumption": consumption,
                "skill_md": skill_md}

    def run_beta(self) -> dict:
        mode = "dev" if self.live else "offline_dev"
        reps = []
        n_reps = self.contract["beta_repetitions"] if self.live else 1
        for i in range(1, n_reps + 1):
            cfg = {"task_signals": self.contract["arm_a_task_signals"]}
            if not self.live:
                cfg["offline_artifact_files"] = offline_fixtures.GOOD_ARTIFACT
                cfg["offline_read_paths"] = ["__WS_SKILL_MD__"]
            score = self._run_with_replacement("beta", f"rep{i}", mode, cfg)
            score["_probe"] = "beta"
            if "beta" not in score:
                detail = self._score_dev_rep(score, require_arm_a=True)
                detail["pass"] = bool(
                    detail["valid"] and detail["stream_read_observed"]
                    and detail["audit_skill_consumption"] == "observed")
                score["beta"] = detail
                rep_dir = os.path.join(self.evidence, "beta", score["rep_id"])
                with open(os.path.join(rep_dir, "score.json"), "w",
                          encoding="utf-8") as fh:
                    json.dump(score, fh, indent=2)
            reps.append({"rep": score["rep_id"],
                         "pass": bool(score["beta"]["pass"]),
                         "detail": score["beta"]})
        passed = sum(1 for r in reps if r["pass"])
        threshold = (self.contract["beta_pass_threshold"] if self.live
                     else len(reps))
        return {"probe": "beta", "pass": passed >= threshold,
                "passed": passed, "total": len(reps), "reps": reps}

    # ----- γ ------------------------------------------------------------------ #
    def run_gamma(self) -> dict:
        mode = "dev" if self.live else "offline_dev"
        pairs = []
        orderings = self.contract["ordering"] if self.live else ["AB"]
        for i, order in enumerate(orderings, start=1):
            arm_scores: dict = {}
            for arm in order:                      # execution order per contract
                cfg: dict = {}
                if arm == "A":
                    cfg["task_signals"] = self.contract["arm_a_task_signals"]
                if not self.live:
                    cfg["offline_artifact_files"] = (
                        offline_fixtures.GOOD_ARTIFACT if arm == "A"
                        else offline_fixtures.POOR_ARTIFACT)
                    if arm == "A":
                        cfg["offline_read_paths"] = ["__WS_SKILL_MD__"]
                score = self._run_with_replacement(
                    "gamma", f"pair{i}-arm{arm}", mode, cfg, artifacts=True)
                score["_probe"] = "gamma"
                if "gamma" not in score:
                    detail = self._score_dev_rep(
                        score, require_arm_a=(arm == "A"))
                    rep_dir = os.path.join(self.evidence, "gamma",
                                           score["rep_id"])
                    artifact = scorers.gamma_score_artifact(
                        os.path.join(rep_dir, "artifact"))
                    score["gamma"] = {"runtime": detail, "artifact": artifact}
                    with open(os.path.join(rep_dir, "score.json"), "w",
                              encoding="utf-8") as fh:
                        json.dump(score, fh, indent=2)
                arm_scores[arm] = score["gamma"]
            a, b = arm_scores["A"], arm_scores["B"]
            pair_valid = a["runtime"]["valid"] and b["runtime"]["valid"]
            success = pair_valid and scorers.gamma_pair_success(
                a["artifact"], b["artifact"],
                a["runtime"]["stream_read_observed"],
                margin=self.contract["score_margin_required"])
            pairs.append({
                "pair": i, "order": order, "valid": pair_valid,
                "score_A": a["artifact"]["score"],
                "score_B": b["artifact"]["score"],
                "arm_a_read": a["runtime"]["stream_read_observed"],
                "success": success,
            })
        succeeded = sum(1 for p in pairs if p["success"])
        required = (self.contract["pass_pairs_required"] if self.live
                    else len(pairs))
        return {"probe": "gamma", "pass": succeeded >= required,
                "succeeded": succeeded, "total": len(pairs), "pairs": pairs}

    # ----- entry ---------------------------------------------------------------- #
    def run(self, probes) -> dict:
        results = {}
        path = os.path.join(self.evidence, "results.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                results = json.load(fh)
        for probe in probes:
            results[probe] = getattr(self, f"run_{probe}")()
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(results, fh, indent=2)
            if not results[probe]["pass"]:
                # Frozen §7.4: a probe below threshold HALTS the initiative with
                # an honest negative — later probes are not run (no spend on a
                # failed canary), no post-hoc criteria adjustment.
                break
        results["overall_pass"] = all(
            results.get(p, {}).get("pass") for p in ("alpha", "beta", "gamma"))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true",
                    help="run the REAL billable canary (requires "
                         "AIDAZI_SKILL_CANARY=1)")
    ap.add_argument("--offline-dry-run", action="store_true",
                    help="zero-billable harness plumbing proof (MockAdapter)")
    ap.add_argument("--probe", choices=["alpha", "beta", "gamma", "all"],
                    default="all")
    ap.add_argument("--evidence-dir", default=None)
    args = ap.parse_args(argv)

    if args.live == args.offline_dry_run:
        ap.error("exactly one of --live / --offline-dry-run is required")
    if args.live and os.environ.get("AIDAZI_SKILL_CANARY") != "1":
        ap.error("--live requires AIDAZI_SKILL_CANARY=1 (the dedicated canary "
                 "gate; §7.0/G3)")
    evidence = args.evidence_dir or tempfile.mkdtemp(prefix="p5-evidence-")
    harness = Harness(evidence, live=args.live)
    probes = (["alpha", "beta", "gamma"] if args.probe == "all"
              else [args.probe])
    try:
        results = harness.run(probes)
    except ProbeInconclusive as exc:
        print(f"INCONCLUSIVE HALT: {exc}")
        return 3
    print(json.dumps({p: {k: v for k, v in r.items() if k != "fixtures"}
                      if isinstance(r, dict) else r
                      for p, r in results.items()}, indent=2))
    print(f"evidence: {evidence}")
    return 0 if results.get("overall_pass") else 1


if __name__ == "__main__":
    sys.exit(main())

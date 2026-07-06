"""P4b — the vendored scratch-adopter OFFLINE proof (universal-skill-mounting design
§5 phase 4b / §9 states 1-3; Codex design-R1 F3: TWO fixtures).

A REAL ``engine-kit/tools/vendor-framework.sh`` run builds a temp adopter, and every
loop below is executed by a SUBPROCESS importing the VENDORED engine-kit (never this
repo's modules), so the proof covers the actual deployment shape — vendor allowlist
completeness, vendored framework-root discovery, vendored skill paths — not just the
dev tree. MockAdapter everywhere; fully offline + deterministic.

  fixture (i)  full_chain_guided single-loop: a charter MISSION PROFILE
               (approved_scope.task_signals=["interaction"]) drives the PRE-PLAN
               spawns (Research + Deliver-decompose) — state 2 (selected_skills +
               signal_source audit) and state 3 (prompt transcript carries the block
               citing the VENDORED SKILL.md; input_hash covers the exact bytes);
               the canned plan's signed OMISSION keeps dev/review/close unsignaled.
  fixture (ii) campaign delivery_only: signoff-BOUND milestone_signals →
               derive_milestone_context union → the delivery-only dev/review/close
               spawns mount the skill (same states 1-3).
  negative     no signals ⇒ prompts byte-identical modulo EXACTLY the skill-block
               row + the decompose profile line (and dev/review/close BYTE-IDENTICAL
               incl. input_hash); out-of-vocab ⇒ schema-invalid; tampered lock ⇒
               preflight hard fail; submodule gitlink drift ⇒ HALT + the audited
               override path; post-sign signal mutation ⇒ signoff_status='stale'.

State 1 (deployed) is proven by the VENDORED skills_preflight CLI verifying the
VENDORED tree. ``skill_consumption='unobservable'`` is asserted for every mock spawn.

Run: cd engine-kit && python3.12 -m pytest scheduling/tests/test_vendored_adopter_proof.py -q
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHED_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_SCHED_DIR)
_REPO_ROOT = os.path.dirname(_ENGINE_KIT_DIR)
for _p in (_SCHED_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402  (parsing the VENDORED runs' ledgers — data format only)

_VENDOR_SH = os.path.join(_ENGINE_KIT_DIR, "tools", "vendor-framework.sh")
_GIT = shutil.which("git")

_SKILL_ID = "web-interface-guidelines"      # the `interaction`-unique catalog skill (P0 F1)
_SIGNAL = "interaction"


# --------------------------------------------------------------------------- #
# The runner executed INSIDE the adopter: imports the VENDORED engine-kit only.
# Dispatches on a JSON config; writes a JSON result. Assertions live in THIS
# module (over the artifacts the vendored run produced), never in the runner.
# --------------------------------------------------------------------------- #
_RUNNER = r'''
import json, os, sys

CFG = json.load(open(sys.argv[1], encoding="utf-8"))
AIDAZI = CFG["aidazi_root"]
sys.path.insert(0, os.path.join(AIDAZI, "engine-kit", "scheduling"))
import run_loop as rl                      # noqa: E402 — VENDORED; wires its own sys.path
import campaign as cpn                     # noqa: E402 — vendored orchestrator sibling
import driver as drv                       # noqa: E402
from adapters import MockAdapter           # noqa: E402


def _clock():
    n = {"i": 0}

    def tick():
        n["i"] += 1
        return "2026-07-06T%02d:%02d:%02dZ" % (n["i"] // 3600, (n["i"] // 60) % 60,
                                               n["i"] % 60)
    return tick


RESEARCH = {"artifact": "drafted milestone brief"}
DEV = {"artifact": "handoff written"}
REVIEW = {"decision": "pass", "blocking_count": 0,
          "summary": "no blocking findings", "findings": []}
CLOSE = {"verdict": "A", "blocking_count": 0, "worst_severity": "none",
         "in_scope": True, "next_subsprint": None, "reason": "clean pass"}


def _adapters(plan_verdict=None):
    deliver = {("deliver",): CLOSE}
    if plan_verdict is not None:
        deliver[("deliver", 0)] = plan_verdict     # guided: call 0 = decompose plan
    return {
        "research": MockAdapter({("research",): RESEARCH}, harness="claude_code",
                                provider="anthropic", model="m"),
        "dev": MockAdapter({("dev",): DEV}, harness="claude_code",
                           provider="anthropic", model="m"),
        "review": MockAdapter({("review",): REVIEW}, harness="headless",
                              provider="deepseek", model="m"),
        "deliver": MockAdapter(deliver, harness="claude_code",
                               provider="anthropic", model="m"),
    }


out = {}
mode = CFG["mode"]

if mode == "guided":
    def resolver(gate_id, context, options):
        return {"choice": "sign", "note": "p4b", "resolver": "test-human"}
    try:
        info = rl.run_loop(
            CFG["charter"], run_dir=CFG["run_dir"], loop_id=CFG["loop_id"],
            subsprint_id=CFG["subsprint_id"], clock=_clock(),
            adapters=_adapters(CFG["plan_verdict"]),
            loop_mode="full_chain_guided", gate_resolver=resolver)
        out = {"final_state": info["final_state"], "history": info["history"],
               "ok": info["ok"], "audit_ledger": info["audit_ledger"],
               "audit_verifies": info["audit_verifies"]}
    except drv.GateHardFail as exc:
        out = {"gate_hard_fail": getattr(exc, "reason", "") or str(exc)}

elif mode == "campaign":
    charter = CFG["charter"]
    plan = CFG["plan"]
    try:
        if CFG.get("sign"):
            plan = cpn.stamp_signoff(plan, charter, signer="human",
                                     signed_at="2026-07-06T00:00:00Z",
                                     charter_ref="charter.yaml")
        if CFG.get("post_sign_signals") is not None:
            plan["milestones"][0]["milestone_signals"] = CFG["post_sign_signals"]
        out["signoff_status"] = cpn.signoff_status(plan, charter)
        out["signoff"] = plan.get("signoff")
        if CFG.get("run"):
            r = rl.run_campaign_entry(plan, charter, clock=_clock(),
                                      campaign_run_dir=CFG["home"],
                                      adapters=_adapters())
            out["result"] = {k: r.get(k) for k in
                             ("status", "exit_code", "error", "campaign_home",
                              "units_dir")}
    except ValueError as exc:
        out["value_error"] = str(exc)

elif mode == "enforce":
    # The VENDORED real-run skills preflight gate (tamper / gitlink arms).
    kw = {}
    if CFG.get("audit"):
        kw = dict(audit_loop_id=CFG["audit"]["loop_id"],
                  audit_ledger_path=CFG["audit"]["ledger"], clock=_clock())
    try:
        rl.enforce_skills_preflight_for_real_run(CFG.get("charter") or {}, **kw)
        out["enforce"] = "passed"
    except rl.CharterValidationError as exc:
        out["enforce"] = "refused"
        out["error"] = str(exc)

with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2)
'''


def _charter(task_signals=None, *, guided=False):
    """A self-contained lenient charter (modeled on the p2 demo charter — the demo
    file itself is under examples/, which vendor-framework.sh EXCLUDES). Roles
    declare REAL harness ids (claude_code/headless — inside the skill's
    harness_compat) while the injected adapters are MockAdapter stand-ins keyed by
    role, exactly like the driver test fixtures."""
    ch = {
        "mission": {"id": "M1-p4b",
                    "goal": "prove universal skill mounting in a vendored adopter"},
        "autonomy": {
            "level": "human_in_the_loop",
            "approved_scope": {
                "subsprint_sequence": [] if guided else ["sprint-001"],
                "layers_allowed": ["semantic_planner"],
                "modules_in_scope": ["src/app.py"],
                "explicitly_out_of_scope": [],
            },
        },
        "budget": {"max_api_usd": 0, "max_fix_rounds_total": 2,
                   "max_wall_clock_minutes": 60},
        "tooling": {
            "research": {"harness": "claude_code", "provider": "anthropic",
                         "model": "m"},
            "deliver": {"harness": "claude_code", "provider": "anthropic",
                        "model": "m"},
            "dev": {"harness": "claude_code", "provider": "anthropic", "model": "m",
                    "sandbox": "workspace_write"},
            "review": {"harness": "headless", "provider": "deepseek", "model": "m",
                       "tools": ["Read", "Grep", "Glob"]},
            "eval": {"cmd": "true", "timeout_seconds": 30},
        },
    }
    if task_signals is not None:
        ch["autonomy"]["approved_scope"]["task_signals"] = list(task_signals)
    return ch


# A schema-valid canned decompose plan within the charter envelope, WITHOUT
# task_signals — Deliver's signed omission, so the mission profile must NOT leak
# into the plan-governed dev/review/close spawns.
_GUIDED_PLAN = {"sub_sprints": [{
    "id": "sprint-001", "objective": "implement the app shell",
    "scope_in": ["app shell"], "scope_out": ["everything else"],
    "modules": ["src/app.py"], "layers": ["semantic_planner"],
    "exit_criteria": ["shell exists"],
}]}


def _campaign_plan(signals=("interaction",)):
    m = {"id": "m1", "objective": "ship the app shell",
         "subsprint_sequence": ["s1"]}
    if signals is not None:
        m["milestone_signals"] = list(signals)
    return {"campaign_id": "p4b-camp", "goal": "deliver the whole thing",
            "signed_by_human": True, "milestones": [m]}


# --------------------------------------------------------------------------- #
# Module fixture: vendor ONCE (real vendor-framework.sh), share read-only.
# --------------------------------------------------------------------------- #
_M = {}


def setUpModule():
    if not (shutil.which("bash") and shutil.which("rsync")):
        raise unittest.SkipTest("bash/rsync unavailable — cannot run "
                                "vendor-framework.sh")
    base = tempfile.mkdtemp(prefix="p4b-vendored-")
    _M["base"] = base
    adopter = os.path.join(base, "adopter")
    os.makedirs(adopter)
    proc = subprocess.run(["bash", _VENDOR_SH, _REPO_ROOT, adopter],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        shutil.rmtree(base, ignore_errors=True)
        raise AssertionError(f"vendor-framework.sh failed: {proc.stderr}")
    runner = os.path.join(adopter, "p4b_runner.py")
    with open(runner, "w", encoding="utf-8") as fh:
        fh.write(_RUNNER)
    _M["adopter"] = adopter
    _M["runner"] = runner
    _M["aidazi"] = os.path.join(adopter, "aidazi")


def tearDownModule():
    if _M.get("base"):
        shutil.rmtree(_M["base"], ignore_errors=True)


def _run_runner(cfg, *, adopter=None, runner=None, env_extra=None, timeout=180):
    """Execute the runner subprocess against a config; return its result JSON.
    The child env is scrubbed of AIDAZI_* so no outer override/real-adapter flag
    can leak into the proof."""
    adopter = adopter or _M["adopter"]
    runner = runner or _M["runner"]
    cfg = dict(cfg)
    cfg.setdefault("aidazi_root", os.path.join(adopter, "aidazi"))
    fd, cfg_path = tempfile.mkstemp(suffix=".json", dir=adopter)
    os.close(fd)
    out_path = cfg_path + ".out"
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIDAZI_")}
    env.update(env_extra or {})
    proc = subprocess.run([sys.executable, runner, cfg_path, out_path],
                          cwd=adopter, env=env, capture_output=True, text=True,
                          timeout=timeout)
    if proc.returncode != 0 or not os.path.isfile(out_path):
        raise AssertionError(
            f"runner failed rc={proc.returncode}\nSTDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}")
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def _guided(arm):
    """Memoized guided-loop run: arm 'a' = mission profile [interaction];
    arm 'b' = signal-free but otherwise byte-identical charter. Same loop_id so
    transcript names align for the byte-level comparison."""
    key = f"guided_{arm}"
    if key not in _M:
        run_dir = os.path.join(_M["adopter"], ".runs", f"p4b-guided-{arm}")
        cfg = {"mode": "guided",
               "charter": _charter([_SIGNAL] if arm == "a" else None, guided=True),
               "plan_verdict": _GUIDED_PLAN,
               "run_dir": run_dir, "loop_id": "p4b-guided",
               "subsprint_id": "sprint-001"}
        _M[key] = (_run_runner(cfg), run_dir)
    return _M[key]


def _campaign():
    """Memoized campaign delivery_only run (fixture ii)."""
    if "campaign" not in _M:
        home = os.path.join(_M["adopter"], ".runs", "p4b-camp")
        cfg = {"mode": "campaign", "charter": _charter(None),
               "plan": _campaign_plan(), "sign": True, "run": True, "home": home}
        _M["campaign"] = (_run_runner(cfg), home)
    return _M["campaign"]


def _events(ledger, type_=None):
    evs = audit.read_events(ledger)
    return [e for e in evs if type_ is None or e["type"] == type_]


def _prompt(run_dir, spawn_payload):
    with open(os.path.join(run_dir, spawn_payload["prompt_ref"]),
              encoding="utf-8") as fh:
        return fh.read()


def _input_hash(role, prompt):
    return "sha256:" + hashlib.sha256(
        (role + "\x00" + prompt).encode("utf-8")).hexdigest()[:16]


def _vendored_skill_md(adopter=None):
    return os.path.join(os.path.realpath(adopter or _M["adopter"]), "aidazi",
                        "skills", "vendored", _SKILL_ID, "SKILL.md")


# --------------------------------------------------------------------------- #
# State 1 — deployed: the VENDORED tree verifies via the VENDORED preflight CLI.
# --------------------------------------------------------------------------- #
class VendoredPreflightTests(unittest.TestCase):
    def test_vendored_tree_passes_preflight_cli(self):
        cli = os.path.join(_M["aidazi"], "engine-kit", "validators",
                           "skills_preflight.py")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("AIDAZI_")}
        proc = subprocess.run([sys.executable, cli, "--json"],
                              cwd=_M["adopter"], env=env, capture_output=True,
                              text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertFalse(data["blocking"])
        codes = [f["code"] for f in data["findings"]]
        self.assertIn("lock_ok", codes)
        self.assertIn("required_skills_ok", codes)
        # the verify universe is the vendored tree's own lock (state 1 post-vendor)
        lock_ok = next(f for f in data["findings"] if f["code"] == "lock_ok")
        self.assertGreaterEqual(lock_ok["detail"]["verified"], 11)

    def test_vendor_stamp_written(self):
        self.assertTrue(os.path.isfile(
            os.path.join(_M["aidazi"], ".aidazi-version")))


# --------------------------------------------------------------------------- #
# Fixture (i) — full_chain_guided: mission profile drives PRE-PLAN spawns.
# --------------------------------------------------------------------------- #
class GuidedFixtureTests(unittest.TestCase):
    def test_full_chain_advances_and_chain_verifies(self):
        res, _ = _guided("a")
        self.assertEqual(res["final_state"], "advance")
        self.assertTrue(res["ok"])
        self.assertTrue(res["audit_verifies"])
        self.assertEqual(res["history"][:3], [
            "research_pending", "gate1_pending", "decompose_pending"])

    def test_state2_preplan_spawns_select_via_charter_scope(self):
        res, _ = _guided("a")
        cfgs = [e["payload"] for e in _events(res["audit_ledger"],
                                              "effective_role_config")]
        research = [p for p in cfgs if p["role"] == "research"]
        deliver = [p for p in cfgs if p["role"] == "deliver"]
        self.assertTrue(research)
        self.assertGreaterEqual(len(deliver), 2)   # decompose + close
        for p in research + [deliver[0]]:          # the PRE-PLAN spawns
            self.assertEqual(p["signal_source"], "charter_scope")
            self.assertEqual(p["task_signals"], [_SIGNAL])
            self.assertEqual(p["selected_skills"], [_SKILL_ID])
            self.assertIn(_SKILL_ID, [s["id"] for s in p["skills"]])
            self.assertEqual(p["skipped_skills"], [])

    def test_state2_plan_omission_governs_dev_review_close(self):
        res, _ = _guided("a")
        cfgs = [e["payload"] for e in _events(res["audit_ledger"],
                                              "effective_role_config")]
        deliver = [p for p in cfgs if p["role"] == "deliver"]
        post_plan = ([p for p in cfgs if p["role"] in ("dev", "review")]
                     + deliver[1:])                # the close spawn
        self.assertTrue(post_plan)
        for p in post_plan:
            self.assertEqual(p["signal_source"], "subsprint")
            self.assertEqual(p["task_unit_id"], "sprint-001")
            self.assertEqual(p["task_signals"], [])
            self.assertEqual(p["selected_skills"], [])
            self.assertNotIn(_SKILL_ID, [s["id"] for s in p["skills"]])

    def test_state3_preplan_prompts_carry_vendored_block_and_hash(self):
        res, run_dir = _guided("a")
        spawns = [e["payload"] for e in _events(res["audit_ledger"], "spawn")]
        research = [p for p in spawns if p["role"] == "research"][0]
        decompose = [p for p in spawns if p["role"] == "deliver"][0]
        skill_md = _vendored_skill_md()
        for payload in (research, decompose):
            prompt = _prompt(run_dir, payload)
            self.assertIn("## Effective role skills (framework-resolved)", prompt)
            # the cited SKILL.md path is INSIDE the vendored adopter tree
            self.assertIn(skill_md, prompt)
            # state 3 byte-level: input_hash covers the exact dispatched bytes
            self.assertEqual(payload["input_hash"],
                             _input_hash(payload["role"], prompt))
        # the signed-omission dev spawn mounts NO signal skill
        dev = [p for p in spawns if p["role"] == "dev"][0]
        self.assertNotIn(_SKILL_ID, _prompt(run_dir, dev))

    def test_mock_consumption_is_unobservable(self):
        res, _ = _guided("a")
        spawns = [e["payload"] for e in _events(res["audit_ledger"], "spawn")]
        self.assertTrue(spawns)
        for p in spawns:
            self.assertEqual(p["skill_consumption"], "unobservable", p["role"])
            self.assertEqual(p["skill_consumption_reason"], "harness_unsupported")
            self.assertEqual(p["telemetry_source"], "adapter")


# --------------------------------------------------------------------------- #
# Negative arm — no signals ⇒ byte-identical modulo EXACTLY the mounting deltas.
# --------------------------------------------------------------------------- #
class GuidedByteIdenticalNegativeArmTests(unittest.TestCase):
    def _prompts_by_key(self, arm):
        res, run_dir = _guided(arm)
        out = {}
        for e in _events(res["audit_ledger"], "spawn"):
            p = e["payload"]
            out[os.path.basename(p["prompt_ref"])] = (
                p, _prompt(run_dir, p))
        return out

    def test_signal_free_arm_differs_only_by_block_row_and_profile_line(self):
        a = self._prompts_by_key("a")
        b = self._prompts_by_key("b")
        self.assertEqual(sorted(a), sorted(b), "same spawn set in both arms")
        # research: arm A minus THE ONE skill-block row == arm B, byte-for-byte
        ra_payload, ra = [v for k, v in a.items() if "__research__" in k][0]
        rb_payload, rb = [v for k, v in b.items() if "__research__" in k][0]
        row_lines = [ln for ln in ra.splitlines(keepends=True) if _SKILL_ID in ln]
        self.assertEqual(len(row_lines), 1, "exactly one mounted-skill row")
        self.assertEqual(ra.replace(row_lines[0], ""), rb,
                         "the ONLY research-prompt delta is the mounted-skill row")
        # decompose (first deliver spawn): row + the DECLARED-profile line only
        da = [v for k, v in sorted(a.items()) if "__deliver__" in k][0][1]
        db = [v for k, v in sorted(b.items()) if "__deliver__" in k][0][1]
        self.assertIn("DECLARED signal profile", da)
        self.assertNotIn("DECLARED signal profile", db)
        stripped = "".join(
            ln for ln in da.splitlines(keepends=True)
            if _SKILL_ID not in ln and "DECLARED signal profile" not in ln)
        self.assertEqual(stripped, db,
                         "the ONLY decompose-prompt deltas are the skill row + "
                         "the profile line")
        # dev / review / close: BYTE-IDENTICAL prompts + equal input_hash — the
        # mission profile never leaks into plan-governed (signed-omission) spawns.
        for key in sorted(a):
            pa, prompt_a = a[key]
            pb, prompt_b = b[key]
            if pa["role"] in ("dev", "review"):
                self.assertEqual(prompt_a, prompt_b, key)
                self.assertEqual(pa["input_hash"], pb["input_hash"], key)
        close_a = [v for k, v in sorted(a.items()) if "__deliver__" in k][1]
        close_b = [v for k, v in sorted(b.items()) if "__deliver__" in k][1]
        self.assertEqual(close_a[1], close_b[1], "close prompt byte-identical")
        self.assertEqual(close_a[0]["input_hash"], close_b[0]["input_hash"])

    def test_signal_free_arm_mounts_nothing_and_reads_none(self):
        res, _ = _guided("b")
        self.assertEqual(res["final_state"], "advance")
        for e in _events(res["audit_ledger"], "effective_role_config"):
            p = e["payload"]
            self.assertEqual(p["selected_skills"], [])
            self.assertNotIn(_SKILL_ID, [s["id"] for s in p["skills"]])
            self.assertIn(p["signal_source"], ("none", "subsprint"))


# --------------------------------------------------------------------------- #
# Fixture (ii) — campaign delivery_only: signoff-bound milestone_signals union.
# --------------------------------------------------------------------------- #
class CampaignFixtureTests(unittest.TestCase):
    def _unit_dir(self, home):
        units = os.path.join(home, "units")
        entries = [os.path.join(units, n) for n in os.listdir(units)]
        self.assertEqual(len(entries), 1)
        return entries[0]

    def _unit_ledger(self, unit_dir):
        audit_dir = os.path.join(unit_dir, ".orchestrator", "audit")
        names = [n for n in os.listdir(audit_dir) if n.endswith(".jsonl")]
        self.assertEqual(len(names), 1)
        return os.path.join(audit_dir, names[0])

    def test_signoff_binds_the_milestone_signals_digest(self):
        res, _ = _campaign()
        self.assertEqual(res["signoff_status"], "signed")
        so = res["signoff"]
        self.assertIn("milestone_signals_digest", so)
        self.assertEqual(so["scope_envelope"]["milestone_signals_digest"],
                         so["milestone_signals_digest"])

    def test_campaign_completes_and_derives_the_union(self):
        res, home = _campaign()
        self.assertEqual(res["result"]["exit_code"], 0, res["result"])
        self.assertEqual(res["result"]["status"], "done")
        unit = self._unit_dir(home)
        with open(os.path.join(unit, "derived-context.json"),
                  encoding="utf-8") as fh:
            prov = json.load(fh)
        self.assertEqual(prov["task_signals"], {
            "effective": [_SIGNAL], "charter_scope": [],
            "milestone_signals": [_SIGNAL]})

    def test_state2_delivery_spawns_mount_the_union(self):
        res, home = _campaign()
        ledger = self._unit_ledger(self._unit_dir(home))
        cfgs = [e["payload"] for e in _events(ledger, "effective_role_config")]
        self.assertTrue(cfgs)
        roles = {p["role"] for p in cfgs}
        self.assertLessEqual({"dev", "review", "deliver"}, roles)
        for p in cfgs:
            self.assertEqual(p["signal_source"], "charter_scope", p["role"])
            self.assertEqual(p["task_signals"], [_SIGNAL])
            self.assertEqual(p["selected_skills"], [_SKILL_ID])
            self.assertIn(_SKILL_ID, [s["id"] for s in p["skills"]])

    def test_state3_delivery_prompts_carry_vendored_block_and_hash(self):
        res, home = _campaign()
        unit = self._unit_dir(home)
        ledger = self._unit_ledger(unit)
        spawns = [e["payload"] for e in _events(ledger, "spawn")]
        self.assertTrue(spawns)
        skill_md = _vendored_skill_md()
        for p in spawns:
            prompt = _prompt(unit, p)
            self.assertIn("## Effective role skills (framework-resolved)", prompt)
            self.assertIn(skill_md, prompt)
            self.assertEqual(p["input_hash"], _input_hash(p["role"], prompt))
            self.assertEqual(p["skill_consumption"], "unobservable")
            self.assertEqual(p["skill_consumption_reason"], "harness_unsupported")


# --------------------------------------------------------------------------- #
# Negative arm — out-of-vocab signals are schema-INVALID, fail closed.
# --------------------------------------------------------------------------- #
class OutOfVocabNegativeArmTests(unittest.TestCase):
    def test_guided_decompose_plan_with_unknown_signal_hard_fails(self):
        bad = json.loads(json.dumps(_GUIDED_PLAN))
        bad["sub_sprints"][0]["task_signals"] = ["not-a-signal"]
        res = _run_runner({
            "mode": "guided", "charter": _charter([_SIGNAL], guided=True),
            "plan_verdict": bad,
            "run_dir": os.path.join(_M["adopter"], ".runs", "p4b-oov"),
            "loop_id": "p4b-oov", "subsprint_id": "sprint-001"})
        self.assertIn("gate_hard_fail", res)
        self.assertNotIn("final_state", res)
        self.assertIn("failed schema validation", res["gate_hard_fail"])
        self.assertIn("not-a-signal", res["gate_hard_fail"])

    def test_campaign_plan_with_unknown_milestone_signal_is_invalid(self):
        res = _run_runner({
            "mode": "campaign", "charter": _charter(None),
            "plan": _campaign_plan(signals=["not-a-signal"]),
            "sign": True, "run": True,
            "home": os.path.join(_M["adopter"], ".runs", "p4b-camp-oov")})
        # stamping does not validate; the campaign INGRESS is the fail-closed layer
        self.assertEqual(res["result"]["exit_code"], 2, res)
        self.assertEqual(res["result"]["status"], "invalid")
        self.assertIn("failed schema validation", res["result"]["error"])
        self.assertIn("not-a-signal", res["result"]["error"])


# --------------------------------------------------------------------------- #
# Negative arm — tampered lock in the VENDORED tree ⇒ preflight hard fail.
# --------------------------------------------------------------------------- #
class TamperedLockNegativeArmTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.adopter = os.path.join(self._tmp.name, "adopter")
        os.makedirs(self.adopter)
        shutil.copytree(_M["aidazi"], os.path.join(self.adopter, "aidazi"))
        self.runner = os.path.join(self.adopter, "p4b_runner.py")
        shutil.copy2(_M["runner"], self.runner)
        with open(os.path.join(self.adopter, "aidazi", "skills", "vendored",
                               _SKILL_ID, "SKILL.md"), "a",
                  encoding="utf-8") as fh:
            fh.write("\ntampered\n")

    def test_vendored_cli_reports_and_exits_1(self):
        cli = os.path.join(self.adopter, "aidazi", "engine-kit", "validators",
                           "skills_preflight.py")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("AIDAZI_")}
        proc = subprocess.run([sys.executable, cli], cwd=self.adopter, env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("lock_mismatch", proc.stdout)
        self.assertIn(_SKILL_ID, proc.stdout)

    def test_vendored_real_run_gate_refuses(self):
        res = _run_runner({"mode": "enforce", "charter": {}},
                          adopter=self.adopter, runner=self.runner)
        self.assertEqual(res["enforce"], "refused")
        self.assertIn("lock_mismatch", res["error"])
        self.assertIn("refusing the real run", res["error"])


# --------------------------------------------------------------------------- #
# Negative arm — submodule gitlink drift ⇒ HALT; audited override path works.
# --------------------------------------------------------------------------- #
@unittest.skipUnless(_GIT, "git binary unavailable")
class GitlinkDriftNegativeArmTests(unittest.TestCase):
    @staticmethod
    def _git(args, cwd):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "-c", "commit.gpgsign=false", *args],
            cwd=cwd, check=True, capture_output=True, text=True)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = self._tmp.name
        # The vendored framework becomes a real git repo, then a SUBMODULE of a
        # fresh adopter superproject — the AirPlat deployment class.
        fw_src = os.path.join(base, "fw-src")
        shutil.copytree(_M["aidazi"], fw_src)
        self._git(["init", "-q", "-b", "main"], fw_src)
        self._git(["add", "-A"], fw_src)
        self._git(["commit", "-q", "-m", "vendored framework"], fw_src)
        self.adopter = os.path.join(base, "adopter")
        os.makedirs(self.adopter)
        self._git(["init", "-q", "-b", "main"], self.adopter)
        self._git(["-c", "protocol.file.allow=always", "submodule", "add", "-q",
                   fw_src, "aidazi"], self.adopter)
        self._git(["commit", "-q", "-m", "pin aidazi"], self.adopter)
        self.sub = os.path.join(self.adopter, "aidazi")
        self.recorded = self._git(["rev-parse", "HEAD"], self.sub).stdout.strip()
        self._git(["commit", "-q", "--allow-empty", "-m", "drift"], self.sub)
        self.actual = self._git(["rev-parse", "HEAD"], self.sub).stdout.strip()
        self.runner = os.path.join(self.adopter, "p4b_runner.py")
        shutil.copy2(_M["runner"], self.runner)

    def test_drifted_vendored_submodule_halts_the_real_run(self):
        res = _run_runner({"mode": "enforce", "charter": {}},
                          adopter=self.adopter, runner=self.runner)
        self.assertEqual(res["enforce"], "refused")
        self.assertIn("gitlink", res["error"])
        self.assertIn(self.recorded[:12], res["error"])
        self.assertIn(self.actual[:12], res["error"])

    def test_audited_override_proceeds_and_records_both_commits(self):
        ledger = os.path.join(self.adopter, ".runs", "p4b-drift",
                              "audit", "p4b-drift.jsonl")
        res = _run_runner(
            {"mode": "enforce", "charter": {},
             "audit": {"loop_id": "p4b-drift", "ledger": ledger}},
            adopter=self.adopter, runner=self.runner,
            env_extra={"AIDAZI_SKILLS_ALLOW_GITLINK_DRIFT": "1"})
        self.assertEqual(res["enforce"], "passed")
        events = audit.read_events(ledger)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["type"], "skills_preflight_gitlink_override")
        self.assertEqual(ev["payload"]["recorded_gitlink"], self.recorded)
        self.assertEqual(ev["payload"]["working_tree_commit"], self.actual)
        self.assertTrue(audit.verify_chain(ledger).ok)


# --------------------------------------------------------------------------- #
# Negative arm — post-sign signal mutation ⇒ signoff_status='stale', run refused.
# --------------------------------------------------------------------------- #
class PostSignMutationNegativeArmTests(unittest.TestCase):
    def test_post_sign_signal_edit_reads_stale_and_refuses(self):
        res = _run_runner({
            "mode": "campaign", "charter": _charter(None),
            "plan": _campaign_plan(), "sign": True,
            "post_sign_signals": ["a11y"],           # mutate AFTER stamping
            "run": True,
            "home": os.path.join(_M["adopter"], ".runs", "p4b-camp-stale")})
        self.assertEqual(res["signoff_status"], "stale")
        self.assertEqual(res["result"]["exit_code"], 2, res)
        self.assertEqual(res["result"]["status"], "invalid")
        self.assertIn("milestone_signals", res["result"]["error"])


if __name__ == "__main__":
    unittest.main()

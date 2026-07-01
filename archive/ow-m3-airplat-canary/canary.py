#!/usr/bin/env python3.12
"""OW-M3 reversible single-adopter canary on airplat (scratch copies only).

Proves, on the REAL airplat campaign-plan + charter (copied into /tmp), that OW-M3:
  (control)  is dormant with no ledger / no covers_req_ids  -> --sign-plan OK
  (negative) refuses to sign a user_facing REQ on static evidence -> exit 2, no stamp
  (positive) signs when the covering milestone is browser_e2e, binding covered_req_surfaces
  (tamper)   a post-sign surface flip makes the signature STALE -> real execution blocks
  (item 6)   a correctly-signed plan is FRESH -> no new human pause in a normal loop

Never touches the real airplat repo. Uses the shipped run_loop.py CLI for the exit-code
evidence and the shipped campaign.py functions for the hash/freshness inspection.
"""
import json, os, subprocess, sys, copy, shutil

AIDAZI = "/Users/caoruixin/projects/aidazi"
RUN_LOOP = os.path.join(AIDAZI, "engine-kit", "scheduling", "run_loop.py")
SCRATCH = "/tmp/owm3-airplat-canary"
CHARTER = os.path.join(SCRATCH, "charter.yaml")
ORIG = os.path.join(SCRATCH, "campaign-plan.airplat-orig.json")
LEDGER = os.path.join(SCRATCH, "docs", "requirements-ledger.json")
REQ_ID = "REQ-UI-WORKBENCH"
UI_MS = "M-UI"

# engine on path for the direct-API (hash/freshness) assertions
for p in (os.path.join(AIDAZI, "engine-kit"),
          os.path.join(AIDAZI, "engine-kit", "orchestrator"),
          os.path.join(AIDAZI, "engine-kit", "audit"),
          os.path.join(AIDAZI, "engine-kit", "validators")):
    sys.path.insert(0, p)
import campaign as cp          # noqa: E402
from driver import load_charter  # noqa: E402

CHARTER_D = load_charter(CHARTER)
RESULTS = []

def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)

def dump(obj, p):
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)

def set_ms(plan, mid, **kw):
    for m in plan["milestones"]:
        if m["id"] == mid:
            m.update(kw)
            return m
    raise SystemExit(f"milestone {mid} not found")

def sign(plan_path):
    """Invoke the REAL --sign-plan CLI; return (exit_code, stdout+stderr)."""
    r = subprocess.run(
        [sys.executable, RUN_LOOP, "--campaign", plan_path, "--charter", CHARTER,
         "--sign-plan", "--repo-dir", SCRATCH],
        capture_output=True, text=True, cwd=SCRATCH)
    return r.returncode, (r.stdout + r.stderr)

def rec(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

def ledger_write(surface):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    dump({"version": "v1", "requirements": [{
        "id": REQ_ID,
        "statement": "招聘人员在浏览器三区工作台操作：查看职位、浏览候选人卡片、"
                     "执行 Like/Dislike/Shortlist（PRD §25/§26 Demo 闭环）。",
        "source": {"channel": "prd", "ref": "docs/AI-recruiter-plat-PRD.docx#§25"},
        "customer_disposition": "accepted",
        "surface": surface,
    }]}, LEDGER)

def ledger_rm():
    if os.path.exists(LEDGER):
        os.remove(LEDGER)

# --------------------------------------------------------------------------- #
print("="*72)
print("OW-M3 airplat canary — real plan/charter copies, real CLI + shipped fns")
print("UI milestone under test:", UI_MS, "| requirement:", REQ_ID)
print("="*72)

# ---- CONTROL A: airplat as-is (no ledger, no covers_req_ids) -------------- #
ledger_rm()
pA = os.path.join(SCRATCH, "plan_control_asis.json")
plan = load(ORIG)
assert not any(m.get("covers_req_ids") for m in plan["milestones"]), "orig has covers?!"
dump(plan, pA)
code, out = sign(pA)
signed = load(pA)
rec("control_asis_signs",
    code == 0 and isinstance(signed.get("signoff"), dict),
    f"exit={code}; signoff stamped={isinstance(signed.get('signoff'), dict)} "
    f"(OW-M3 dormant: no ledger, no covers)")

# ---- CONTROL B: covers_req_ids declared but NO ledger wired => dormant ---- #
ledger_rm()
pB = os.path.join(SCRATCH, "plan_control_covers_noledger.json")
plan = load(ORIG)
set_ms(plan, UI_MS, covers_req_ids=[REQ_ID])            # covers, but no ledger file
dump(plan, pB)
code, out = sign(pB)
signed = load(pB)
rec("control_covers_noledger_dormant",
    code == 0 and isinstance(signed.get("signoff"), dict),
    f"exit={code}; signs (design: no ledger => mandate inert; ledger is the "
    f"activation trigger, not covers_req_ids alone)")

# ---- create the ledger (OW-2 input contract), REQ = user_facing ----------- #
ledger_write("user_facing")

# ---- NEGATIVE: user_facing REQ on static evidence => refuse-to-sign ------- #
pN = os.path.join(SCRATCH, "plan_negative_static.json")
plan = load(ORIG)
m = set_ms(plan, UI_MS, covers_req_ids=[REQ_ID])
assert m.get("functional_acceptance") == "static", f"M-UI fa={m.get('functional_acceptance')}"
dump(plan, pN)
before = load(pN)
code, out = sign(pN)
after = load(pN)
no_stamp = "signoff" not in after and after == before
rec("negative_static_refused_exit2",
    code == 2 and no_stamp,
    f"exit={code} (expect 2); no signoff stamp & file unchanged={no_stamp}")
msg_ok = ("browser_e2e" in out and UI_MS in out and REQ_ID in out
          and "refusing to sign" in out.lower())
rec("negative_refusal_message_actionable", msg_ok,
    "message names the milestone, the REQ, browser_e2e, and the 2 resolutions")
NEG_MSG = out.strip()

# ---- POSITIVE: same milestone set to browser_e2e => signs ----------------- #
pP = os.path.join(SCRATCH, "plan_positive_browser_e2e.json")
plan = load(ORIG)
set_ms(plan, UI_MS, covers_req_ids=[REQ_ID], functional_acceptance="browser_e2e")
dump(plan, pP)
code, out = sign(pP)
signed = load(pP)
so = signed.get("signoff") or {}
env = so.get("scope_envelope") or {}
env_ui = next((e for e in env.get("milestones", []) if e.get("id") == UI_MS), {})
surf = env_ui.get("covered_req_surfaces")
h = so.get("signed_scope_hash")
rec("positive_browser_e2e_signs",
    code == 0 and bool(h), f"exit={code}; signed_scope_hash={'present' if h else 'MISSING'}")
rec("positive_covered_req_surfaces_bound_into_signed_basis",
    surf == {REQ_ID: "user_facing"},
    f"scope_envelope[{UI_MS}].covered_req_surfaces={surf}")
# prove the hash actually DEPENDS on the surface basis (recompute w/ live ledger)
live = cp.load_and_validate_ledger(LEDGER)
status_fresh = cp.signoff_status(signed, CHARTER_D, live)
rec("positive_fresh_after_sign", status_fresh == "signed",
    f"signoff_status(live user_facing ledger) = {status_fresh!r}")

# ---- item 6: correctly-signed plan is FRESH => no new pause in a loop ----- #
rundir = os.path.join(SCRATCH, ".runs", "camp-pos")
shutil.rmtree(rundir, ignore_errors=True)
camp = cp.Campaign(signed, rundir, run_unit=(lambda *a, **k: {}),
                   clock=(lambda: "2026-07-01T00:00:00Z"),
                   charter=CHARTER_D, ledger_path=LEDGER)
fresh_ok = camp._authority_fresh()
rec("item6_correctly_signed_no_new_pause", fresh_ok is True,
    f"Campaign._authority_fresh()={fresh_ok} (dispatch gate would NOT re-pause a "
    f"correctly authorized loop)")

# ---- TAMPER: flip the covered REQ surface AFTER signing => STALE ---------- #
ledger_write("non_user_facing")                          # the post-sign tamper
flipped = cp.load_and_validate_ledger(LEDGER)
status_stale = cp.signoff_status(signed, CHARTER_D, flipped)
rec("tamper_surface_flip_makes_signature_stale", status_stale == "stale",
    f"signoff_status(flipped ledger)={status_stale!r} (signed basis bound "
    f"{{{REQ_ID}: user_facing}}; live now non_user_facing => hash mismatch)")
rundir2 = os.path.join(SCRATCH, ".runs", "camp-tamper")
shutil.rmtree(rundir2, ignore_errors=True)
camp2 = cp.Campaign(signed, rundir2, run_unit=(lambda *a, **k: {}),
                    clock=(lambda: "2026-07-01T00:00:00Z"),
                    charter=CHARTER_D, ledger_path=LEDGER)
blocked = camp2._authority_fresh() is False
rec("tamper_real_execution_blocked_under_old_signature", blocked,
    f"Campaign._authority_fresh()={not blocked and 'True' or 'False'} => the "
    f"unconditional pre-dispatch gate (campaign.py:2340) blocks run_unit for re-sign")
# restore ledger to the signed (user_facing) basis so state is left coherent
ledger_write("user_facing")

# --------------------------------------------------------------------------- #
print("\n" + "="*72)
print("NEGATIVE-CASE refusal message (verbatim):")
print("-"*72); print(NEG_MSG); print("="*72)
n_pass = sum(1 for _, ok, _ in RESULTS if ok)
print(f"\nCANARY RESULT: {n_pass}/{len(RESULTS)} checks PASS")
sys.exit(0 if n_pass == len(RESULTS) else 1)

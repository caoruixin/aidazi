#!/usr/bin/env python3
"""adoption_status — deterministic (no-LLM) adoption readiness report for an adopter repo.

Answers two human questions after (or during) the Onboarding Wizard:

  1. What *can* be configured?  → see ``templates/adoption-config-template.md`` (the map).
  2. What *is* configured vs missing/deferred? → this CLI's output.

The tool scans the adopter tree + charter (never reads secret *values* — only env-var
**names** from the charter and whether those names are set in the environment). It
reuses ``charter_validator``, ``adopter_wiring_validator``, and
``control_plane_validator`` where applicable.

Normative companion: ``ONBOARDING.md`` Step 8 (green gate) + Step 8 readiness snapshot.

Determinism contract: pure function over the adopter tree. No network, no LLM, no clock.
Same tree => same report. Reads files; writes nothing unless ``--write-readiness`` is passed.

CLI::

    python adoption_status.py <adopter-root> [--charter PATH] [--harness H]
                             [--write-readiness PATH]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "adoption_status: PyYAML is required (pip install -r requirements.txt)\n"
    )
    raise

# Sibling validators on sys.path when invoked as a script from engine-kit/validators/.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import adopter_wiring_validator as awv  # noqa: E402

try:
    import charter_validator as cv  # noqa: E402
except ImportError:  # pragma: no cover
    cv = None  # type: ignore

try:
    import control_plane_validator as cpv  # noqa: E402
except ImportError:  # pragma: no cover
    cpv = None  # type: ignore


# --------------------------------------------------------------------------- #
# Check line model
# --------------------------------------------------------------------------- #
@dataclass
class Check:
    section: str          # REQUIRED | OPTIONAL | RUNTIME | WORKSPACE
    status: str           # ok | missing | partial | warn | info | error
    label: str
    detail: str = ""

    def symbol(self) -> str:
        return {
            "ok": "✓",
            "missing": " ",
            "partial": "~",
            "warn": "~",
            "info": "·",
            "error": "✗",
        }.get(self.status, " ")

    def blocks_ok(self) -> bool:
        return self.status in ("missing", "error", "partial")


@dataclass
class StatusReport:
    root: str
    checks: list[Check] = field(default_factory=list)
    framework_repo: bool = False

    def add(self, section: str, status: str, label: str, detail: str = "") -> None:
        self.checks.append(Check(section, status, label, detail))

    @property
    def ok(self) -> bool:
        if self.framework_repo:
            return False
        return not any(c.blocks_ok() and c.section == "REQUIRED" for c in self.checks)

    def render(self) -> str:
        lines = ["=== aidazi adoption status ==="]
        ws = next((c for c in self.checks if c.section == "WORKSPACE"), None)
        if ws:
            lines.append(f"workspace     : {self.root}  ({ws.label})")
        else:
            lines.append(f"workspace     : {self.root}")

        for section in ("REQUIRED", "OPTIONAL", "RUNTIME"):
            items = [c for c in self.checks if c.section == section]
            if not items:
                continue
            lines.append("")
            title = {
                "REQUIRED": "REQUIRED (onboarding)",
                "OPTIONAL": "OPTIONAL (explicit OFF is OK)",
                "RUNTIME": "RUNTIME (per loop; not onboarding)",
            }[section]
            lines.append(title)
            for c in items:
                suffix = f" — {c.detail}" if c.detail else ""
                lines.append(f"  [{c.symbol()}] {c.label}{suffix}")

        if self.framework_repo:
            lines.append("")
            lines.append(
                "STOP: run this from the ADOPTER repo root (e.g. ~/projects/airplat), "
                "NOT the aidazi framework repo. Point the agent at "
                "<framework>/ONBOARDING.md but keep cwd = adopter root."
            )
        elif self.ok:
            lines.append("")
            lines.append("NEXT: FIRST-LOOP.md (fresh session, cwd = THIS repo)")
        else:
            lines.append("")
            lines.append("Fix REQUIRED items above, then re-run adoption_status.py .")
        return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Framework vs adopter detection
# --------------------------------------------------------------------------- #
_FRAMEWORK_MARKERS = (
    "process/delivery-loop.md",
    "role-cards/dev-agent.md",
    "governance/constitution.md",
)


def is_framework_repo(root: str) -> bool:
    """True when ``root`` looks like the aidazi framework repo itself."""
    hits = sum(1 for rel in _FRAMEWORK_MARKERS if os.path.isfile(os.path.join(root, rel)))
    if hits >= 2:
        return True
    agents = os.path.join(root, "AGENTS.md")
    if os.path.isfile(agents):
        try:
            with open(agents, encoding="utf-8") as fh:
                body = fh.read()
            if "consumer-side template (aidazi" in body and "<adopter-name>" in body:
                if not os.path.isfile(os.path.join(root, "docs", "current", "adoption-state.md")):
                    return True
        except OSError:
            pass
    return False


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _gitignore_covers(root: str, pattern: str) -> bool:
    gi = _read_text(os.path.join(root, ".gitignore"))
    if not gi:
        return False
    for line in gi.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.rstrip("/") == pattern.rstrip("/"):
            return True
    return False


def _agents_has_placeholder(root: str) -> bool:
    body = _read_text(os.path.join(root, "AGENTS.md"))
    if not body:
        return False
    return "<adopter-name>" in body or "<adopter>" in body


def _load_charter(path: str) -> tuple[Optional[dict], Optional[str]]:
    if not os.path.isfile(path):
        return None, "file missing"
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return None, f"YAML parse error: {exc}"
    if not isinstance(data, dict):
        return None, "expected a mapping at top level"
    return data, None


def _headless_env_names(charter: dict) -> list[tuple[str, str]]:
    """Return (role, api_key_env) pairs for roles that declare api_key_env."""
    out: list[tuple[str, str]] = []
    tooling = charter.get("tooling") or {}
    for role in ("research", "deliver", "dev", "review", "acceptance"):
        block = tooling.get(role)
        if not isinstance(block, dict):
            continue
        env_name = block.get("api_key_env")
        if isinstance(env_name, str) and env_name.strip():
            out.append((role, env_name.strip()))
    return out


def _load_dotenv_names(root: str) -> set[str]:
    """Keys from .env.local / .env (names only — never return values)."""
    names: set[str] = set()
    for name in (".env.local", ".env"):
        path = os.path.join(root, name)
        text = _read_text(path)
        if not text:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, _ = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            if key:
                names.add(key)
    return names


def _engine_kit_present(root: str) -> tuple[bool, str]:
    """True when a driver is reachable at repo root OR via ``aidazi/`` submodule."""
    for rel in (
        os.path.join("engine-kit", "orchestrator", "driver.py"),
        os.path.join("aidazi", "engine-kit", "orchestrator", "driver.py"),
    ):
        if os.path.isfile(os.path.join(root, rel)):
            return True, rel.split(os.sep)[0] + "/"
    return False, ""


def _brief_confirmed(root: str, charter: dict) -> tuple[bool, str]:
    brief_ref = None
    mission = charter.get("mission") or {}
    if isinstance(mission, dict):
        brief_ref = mission.get("brief")
    if not brief_ref:
        ic = charter.get("intent_contract") or {}
        if isinstance(ic, dict):
            brief_ref = ic.get("brief")
    if brief_ref:
        brief_path = (
            os.path.join(root, brief_ref) if not os.path.isabs(brief_ref) else brief_ref
        )
        if not os.path.isfile(brief_path):
            return False, f"brief missing: {brief_ref}"
        body = _read_text(brief_path) or ""
        if re.search(r"confirmed_by_human:\s*true", body, re.IGNORECASE):
            return True, brief_ref
        return False, f"{brief_ref} — confirmed_by_human not true"

    # Submodule adopters may cite the brief only in mission.goal comments — scan briefs dir.
    briefs_dir = os.path.join(root, "docs", "research-briefs")
    if os.path.isdir(briefs_dir):
        signed = []
        for name in sorted(os.listdir(briefs_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(briefs_dir, name)
            body = _read_text(path) or ""
            if re.search(r"confirmed_by_human:\s*true", body, re.IGNORECASE):
                signed.append(f"docs/research-briefs/{name}")
        if signed:
            return True, signed[-1] + " (latest signed in docs/research-briefs/)"
    return False, "no mission.brief and no confirmed brief in docs/research-briefs/"


def _connector_count(charter: dict) -> int:
    n = 0
    tooling = charter.get("tooling") or {}
    for role in ("research", "deliver", "dev", "review", "acceptance"):
        block = tooling.get(role)
        if not isinstance(block, dict):
            continue
        conns = block.get("connectors")
        if isinstance(conns, list):
            n += len(conns)
    return n


def _onboarding_deferrals(adoption_state_path: str) -> list[str]:
    body = _read_text(adoption_state_path)
    if not body:
        return []
    return re.findall(r"\bdefer(?:red|ral)?\b", body, re.IGNORECASE)


def validate_adoption(
    root: str,
    *,
    charter_path: Optional[str] = None,
    harness: Optional[str] = None,
    adoption_state_path: Optional[str] = None,
) -> StatusReport:
    root = os.path.abspath(root)
    report = StatusReport(root=root)

    if not os.path.isdir(root):
        report.add("WORKSPACE", "error", "not a directory")
        return report

    if is_framework_repo(root):
        report.framework_repo = True
        report.add("WORKSPACE", "error", "framework repo detected — wrong workspace")
        return report

    report.add("WORKSPACE", "ok", "adopter repo")

    charter_path = charter_path or os.path.join(root, "charter.yaml")
    adoption_state_path = (
        adoption_state_path or os.path.join(root, "docs", "current", "adoption-state.md")
    )

    # --- REQUIRED artifacts ------------------------------------------------ #
    required_files = {
        "charter.yaml": charter_path,
        "AGENTS.md": os.path.join(root, "AGENTS.md"),
        "docs/current/adoption-state.md": adoption_state_path,
        "docs/current/implementation-stack.md": os.path.join(
            root, "docs", "current", "implementation-stack.md"),
        "docs/current/runtime_invariants.md": os.path.join(
            root, "docs", "current", "runtime_invariants.md"),
        "docs/current/domain_taxonomy.md": os.path.join(
            root, "docs", "current", "domain_taxonomy.md"),
        "docs/current/agent_context_guide.md": os.path.join(
            root, "docs", "current", "agent_context_guide.md"),
        "docs/current/onboarding-record.md": os.path.join(
            root, "docs", "current", "onboarding-record.md"),
        "docs/current/adoption-config.md": os.path.join(
            root, "docs", "current", "adoption-config.md"),
    }

    for label, path in required_files.items():
        if os.path.isfile(path):
            report.add("REQUIRED", "ok", label)
        else:
            report.add("REQUIRED", "missing", label)

    charter, charter_err = _load_charter(charter_path)
    if charter_err:
        report.add("REQUIRED", "error", "charter.yaml parse", charter_err)
    elif cv is not None:
        cv_report = cv.validate_file(charter_path)
        if cv_report.ok:
            report.add("REQUIRED", "ok", "charter schema validation")
        else:
            n_err = len(getattr(cv_report, "errors", []) or [])
            report.add(
                "REQUIRED", "error", "charter schema validation",
                f"{n_err} error(s) — run charter_validator.py",
            )
    else:
        report.add("REQUIRED", "partial", "charter schema validation",
                   "charter_validator unavailable")

    if _agents_has_placeholder(root):
        report.add("REQUIRED", "partial", "AGENTS.md §1 filled",
                   "still contains <adopter-name> placeholder")
    elif os.path.isfile(os.path.join(root, "AGENTS.md")):
        report.add("REQUIRED", "ok", "AGENTS.md §1 filled")

    kit_ok, kit_label = _engine_kit_present(root)
    if kit_ok:
        report.add("REQUIRED", "ok", f"engine-kit/ ({kit_label}submodule or copy)")
    else:
        report.add("REQUIRED", "missing",
                   "engine-kit/ (copy from framework or wire aidazi/ submodule)")

    wiring = awv.validate_root(root, harness, charter_path, adoption_state_path)
    if wiring.ok:
        targets = ", ".join(wiring.targets) if wiring.targets else "resolved"
        report.add("REQUIRED", "ok", f"harness root-file wiring ({targets})")
    else:
        n_err = len(wiring.errors)
        report.add("REQUIRED", "error", "harness root-file wiring",
                   f"{n_err} error(s) — run adopter_wiring_validator.py")

    if cpv is not None:
        control_plane = cpv.validate_root(root)
        if control_plane.ok:
            report.add("REQUIRED", "ok", "default Control Plane load graph")
        else:
            n_err = len(control_plane.errors)
            report.add(
                "REQUIRED", "error", "default Control Plane load graph",
                f"{n_err} error(s) — run control_plane_validator.py",
            )
    else:
        report.add("REQUIRED", "partial", "default Control Plane load graph",
                   "control_plane_validator unavailable")

    readiness = os.path.join(root, "docs", "current", "adoption-readiness.md")
    if os.path.isfile(readiness):
        report.add("REQUIRED", "ok", "adoption-readiness.md (Step 8 snapshot)")
    else:
        report.add("REQUIRED", "missing", "adoption-readiness.md (Step 8 snapshot)",
                    "run adoption_status.py --write-readiness after Step 8")

    if charter:
        ok, detail = _brief_confirmed(root, charter)
        if ok:
            report.add("REQUIRED", "ok", "signed research brief", detail)
        else:
            report.add("REQUIRED", "partial", "signed research brief", detail)

    gi_checks = (
        (".runs/", "gitignore .runs/"),
        (".env.local", "gitignore .env.local (or *.local)"),
    )
    for pattern, label in gi_checks:
        if pattern == ".env.local":
            covered = (_gitignore_covers(root, ".env.local")
                       or _gitignore_covers(root, "*.local")
                       or _gitignore_covers(root, ".env.local"))
        else:
            covered = _gitignore_covers(root, pattern)
        if covered:
            report.add("REQUIRED", "ok", label)
        else:
            report.add("REQUIRED", "partial", label, "add to .gitignore in Step 6")

    # --- OPTIONAL ------------------------------------------------------------ #
    if charter:
        mem = charter.get("memory") or {}
        if isinstance(mem, dict) and mem.get("enabled") is True:
            root_mem = mem.get("root") or "memory"
            report.add("OPTIONAL", "ok", "Loop Memory",
                       f"enabled (root={root_mem!r})")
        else:
            report.add("OPTIONAL", "ok", "Loop Memory", "OFF (default)")

        n_conn = _connector_count(charter)
        if n_conn:
            report.add("OPTIONAL", "ok", "Connectors", f"{n_conn} granted across roles")
        else:
            report.add("OPTIONAL", "ok", "Connectors", "none (default-deny)")

        env_pairs = _headless_env_names(charter)
        dotenv_keys = _load_dotenv_names(root)
        if env_pairs:
            missing = []
            for role, env_name in env_pairs:
                if env_name not in os.environ and env_name not in dotenv_keys:
                    missing.append(f"{role}:{env_name}")
            if missing:
                report.add(
                    "OPTIONAL", "partial", "headless API keys (names only)",
                    f"unset: {', '.join(missing)} (use .env.local or export)",
                )
            else:
                report.add("OPTIONAL", "ok", "headless API keys (names only)",
                           "all declared api_key_env names present")
        else:
            report.add("OPTIONAL", "info", "headless API keys",
                       "no api_key_env declared in charter")

    deferrals = _onboarding_deferrals(adoption_state_path)
    if deferrals:
        report.add("OPTIONAL", "warn", "adoption-state deferrals recorded",
                   "see docs/current/adoption-state.md")

    # --- RUNTIME (informational) ------------------------------------------- #
    report.add("RUNTIME", "info", "run dir default",
               ".runs/<loop_id>/  (--run-dir overrides)")
    report.add("RUNTIME", "info", "live loop progress",
               ".runs/<loop_id>/.orchestrator/state.json")
    report.add("RUNTIME", "info", "live audit ledger",
               ".runs/<loop_id>/.orchestrator/audit/<loop_id>.jsonl")
    report.add("RUNTIME", "info", "spawn transcripts",
               ".runs/<loop_id>/.orchestrator/audit/transcripts/<loop_id>/")
    report.add("RUNTIME", "info", "loop registry (cross-loop)",
               ".orchestrator/loops.json  (repo-side; not run-dir)")
    report.add("RUNTIME", "info", "campaign home default",
               ".runs/campaign-<id>/  (--campaign-run-dir overrides)")

    loops_path = os.path.join(root, ".orchestrator", "loops.json")
    if os.path.isfile(loops_path):
        report.add("RUNTIME", "info", "loops.json", "present")
    else:
        report.add("RUNTIME", "info", "loops.json",
                   "created on first Loop Ingress run")

    runs_dir = os.path.join(root, ".runs")
    if os.path.isdir(runs_dir):
        try:
            n = len([e for e in os.listdir(runs_dir)
                     if not e.startswith(".")])
            report.add("RUNTIME", "info", ".runs/", f"{n} entr(ies)")
        except OSError:
            report.add("RUNTIME", "info", ".runs/", "exists")
    else:
        report.add("RUNTIME", "info", ".runs/",
                   "created on first run_loop.py invocation")

    return report


def write_readiness_snapshot(report: StatusReport, path: str) -> None:
    """Write a human-readable readiness snapshot (Step 8 artifact)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    lines = [
        "---",
        "title: Adoption readiness snapshot",
        "doc_tier: adopter-state",
        "doc_category: live",
        "status: current",
        "load_discipline: on-demand",
        "notes: >",
        "  Auto-generated by adoption_status.py --write-readiness at onboarding Step 8.",
        "  Re-run the CLI anytime to refresh; diff-confirm before overwriting manually.",
        "---",
        "",
        "# Adoption readiness snapshot",
        "",
        f"Root: `{report.root}`",
        "",
        "```text",
        report.render().rstrip(),
        "```",
        "",
        "Regenerate:",
        "",
        "```bash",
        "python engine-kit/validators/adoption_status.py . --write-readiness docs/current/adoption-readiness.md",
        "```",
        "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic adoption readiness report (ONBOARDING Step 8 companion).",
    )
    parser.add_argument("root", help="path to the adopter repo root")
    parser.add_argument("--charter", default=None, help="override path to charter.yaml")
    parser.add_argument(
        "--harness",
        default=None,
        help="harness for wiring check: claude_code | codex | cursor | headless",
    )
    parser.add_argument(
        "--adoption-state",
        default=None,
        help="override path to adoption-state.md",
    )
    parser.add_argument(
        "--write-readiness",
        default=None,
        metavar="PATH",
        help="write docs/current/adoption-readiness.md snapshot to PATH",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = validate_adoption(
        args.root,
        charter_path=args.charter,
        harness=args.harness,
        adoption_state_path=args.adoption_state,
    )
    print(report.render(), end="")

    if args.write_readiness:
        write_readiness_snapshot(report, args.write_readiness)
        print(f"Wrote readiness snapshot: {args.write_readiness}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())

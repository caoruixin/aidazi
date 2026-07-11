#!/usr/bin/env python3
"""adopter_wiring_validator — deterministic (no-LLM) check that an adopter repo's
**harness root-file wiring** is in place, so a cold-start session actually loads the
root AGENTS.md Control Plane entry.

Normative source: ``governance/context_briefing.md`` §1.1. This module is the engine-kit
*implementation* of that rule; if this file and §1.1 disagree, §1.1 wins.

Why it exists
-------------
Claude Code auto-loads ``CLAUDE.md`` at a repo root, **not** a bare ``AGENTS.md``. The
framework, however, ships its default Control Plane entry as ``AGENTS.md`` (the consumer
template). So a Claude-Code adopter whose root holds only ``AGENTS.md`` starts every session
with the framework's natural-language control surface silently **absent** — a
default-routing breach that is worse than a hard error because nothing announces it. Codex
(auto-loads ``AGENTS.md``) and Cursor (its own ``.cursor/rules``) do not share that exact gap.

Canonical Claude Code wiring (fixed shape, §1.1)::

    <adopter-root>/CLAUDE.md   ->  @AGENTS.md          (one-line import; may carry other notes)
    <adopter-root>/AGENTS.md   ->  the existing Control Plane entry (unchanged)

``CLAUDE.md`` only *imports* ``AGENTS.md``; it must NOT re-copy the governance chain (dual entry points
drift). The import must reference the **same-root** ``AGENTS.md`` by a clean relative path:
no absolute path, no ``..``, no subdirectory, no symlink redirect.

Harness target resolution (priority)::

    explicit --harness  >  a single, conflict-free formal adopter declaration  >  unspecified

Formal *persistent* declaration sources (used when --harness is omitted):
  * ``<root>/charter.yaml`` ``tooling.<role>.harness`` / legacy ``.agent_kind`` — the set of
    root-file harnesses across the bound roles (``headless`` / API roles impose no root file).
  * ``<root>/docs/current/adoption-state.md`` OPTIONAL pin marker (a markdown HTML comment,
    schema-free): ``<!-- adopter-root-harness: claude_code -->`` (comma/space separated). Use
    it to pin the interactive root harness when per-role tooling is mixed.

If two *persistent* sources **contradict** — disjoint root-file harness sets, both non-empty,
sharing no common harness — the tool **FAILs** and surfaces the conflict; it will not silently
pick one. Partial overlap is NOT a contradiction (e.g. charter ``{claude_code}`` and pin
``{claude_code, codex}`` agree on ``claude_code``); the union is validated. An explicit
``--harness`` selects the target for *this* invocation but does not suppress a genuine
persistent-source contradiction.

Verdict semantics (CLI):
    PASS  -> exit 0, no findings.
    WARN  -> exit 0 (harness unspecified; non-root-file/headless harness). Never blocks.
    FAIL  -> exit non-zero (any error: missing/broken Claude wiring, missing Codex AGENTS.md,
             missing/invalid Cursor .cursor/rules, persistent-source conflict, unreadable
             input, missing root).

Determinism contract: pure function over the adopter tree (root files + optional charter +
optional adoption-state). No network, no LLM, no clock/random dependence. Same tree => same
report. It reads files but writes nothing.

CLI::

    python adopter_wiring_validator.py <adopter-root> [--harness H]
                                       [--charter PATH] [--adoption-state PATH]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

try:
    import yaml
except ImportError:  # pragma: no cover - import guard
    sys.stderr.write(
        "adopter_wiring_validator: PyYAML is required (pip install -r requirements.txt)\n"
    )
    raise


# --------------------------------------------------------------------------- #
# Harness vocabulary.
# --------------------------------------------------------------------------- #
# Root-file harnesses: an interactive harness that auto-loads a file at the repo
# root. headless / API-backed roles are driven programmatically and impose no
# root-file requirement, so they never contribute a wiring target.
ROOT_FILE_HARNESSES = ("claude_code", "codex", "cursor")

_HARNESS_ALIASES = {
    "claude_code": "claude_code",
    "claude-code": "claude_code",
    "claudecode": "claude_code",
    "claude": "claude_code",
    "codex": "codex",
    "openai_codex": "codex",
    "openai-codex": "codex",
    "cursor": "cursor",
    "headless": "headless",
    "api": "headless",
    "openai_compatible": "headless",
    "openai-compatible": "headless",
}


def normalize_harness(raw: object) -> Optional[str]:
    """Map a free-form harness string to its canonical id, or None if unrecognized."""
    if not isinstance(raw, str):
        return None
    return _HARNESS_ALIASES.get(raw.strip().lower())


# --------------------------------------------------------------------------- #
# Report model (mirrors stanza_validator: errors fail, warnings do not).
# --------------------------------------------------------------------------- #
@dataclass
class Issue:
    level: str          # 'error' | 'warning'
    rule: str           # short stable rule id (test-assertable)
    message: str
    path: str           # offending path (file/marker), or "" for whole-root

    def render(self) -> str:
        tag = "ERROR" if self.level == "error" else "WARN "
        loc = f" @ {self.path}" if self.path else ""
        return f"[{tag}] {self.rule}: {self.message}{loc}"


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)  # resolved harness target(s)

    def add(self, issue: Issue) -> None:
        (self.errors if issue.level == "error" else self.warnings).append(issue)

    def error(self, rule: str, message: str, path: str = "") -> None:
        self.add(Issue("error", rule, message, path))

    def warn(self, rule: str, message: str, path: str = "") -> None:
        self.add(Issue("warning", rule, message, path))

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def rules_fired(self) -> set[str]:
        return {i.rule for i in (*self.errors, *self.warnings)}

    def render(self) -> str:
        lines: list[str] = [i.render() for i in self.errors]
        lines += [i.render() for i in self.warnings]
        if not lines:
            tgt = ", ".join(self.targets) if self.targets else "(none)"
            lines.append(
                f"adopter_wiring_validator: OK — root-file wiring valid for: {tgt}."
            )
        summary = f"\n{len(self.errors)} error(s), {len(self.warnings)} warning(s)."
        return "\n".join(lines) + summary


# --------------------------------------------------------------------------- #
# Same-root path safety. The canonical import must resolve to <root>/AGENTS.md
# by a clean relative path with no escape and no symlink redirect.
# --------------------------------------------------------------------------- #
def _token_basename(token: str) -> str:
    """Final path component of an import token, treating BOTH '/' and '\\' as separators.

    ``os.path.basename`` does not split on '\\' on POSIX, so a Windows-style token like
    ``..\\AGENTS.md`` would otherwise be dropped before classification (and a path escape could
    slip past). Splitting on both separators keeps the basename filter consistent with the
    backslash-aware ``_is_absolute`` / ``_has_parent_segment`` classifiers below.
    """
    return re.split(r"[\\/]", token)[-1]


def _is_absolute(token: str) -> bool:
    # POSIX absolute, Windows drive (C:\...), or UNC.
    return token.startswith(("/", "\\")) or bool(re.match(r"^[A-Za-z]:[\\/]", token))


def _has_parent_segment(token: str) -> bool:
    parts = re.split(r"[\\/]+", token)
    return ".." in parts


def _is_symlink_redirect(root: str, path: str) -> bool:
    """True if ``path`` is a symlink, or its realpath resolves outside ``root``.

    The canonical wiring uses real files inside the adopter root; a symlink (or any
    target whose realpath escapes the root) is a redirect and is rejected.
    """
    if os.path.islink(path):
        return True
    real_root = os.path.realpath(root)
    real_path = os.path.realpath(path)
    return real_path != real_root and not real_path.startswith(real_root + os.sep)


# --------------------------------------------------------------------------- #
# CLAUDE.md import parsing.
#
# Claude Code recognizes ``@path`` imports in CLAUDE.md, EXCEPT inside inline code
# spans (`...`) or fenced code blocks (``` / ~~~). The ``@`` must begin the
# reference (start-of-line or whitespace-preceded), so an email like a@b is not an
# import. We surface every import whose basename is ``AGENTS.md`` and classify it.
# --------------------------------------------------------------------------- #
_IMPORT_RE = re.compile(r"(?:^|\s)@(\S+)")
# A fenced code block opens on a line of >=3 backticks OR >=3 tildes (up to 3 leading spaces),
# and closes only on a line of >= the opening count of the SAME fence char (CommonMark). Tracking
# the char + length matters: a 3-backtick line does NOT close a 4-backtick fence, so a naive
# toggle would expose code-block content as live wiring.
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _iter_lines_with_code_state(text: str):
    """Yield ``(line, in_code)`` for each line, where ``in_code`` is True for lines inside (or on
    the boundary of) a fenced code block — tracking the opening fence char + length so nested or
    longer/shorter fences are handled per CommonMark."""
    fence_char: Optional[str] = None
    fence_len = 0
    for line in text.splitlines():
        if fence_char is not None:
            # Inside a fence: close only on >= fence_len of the SAME char (then optional ws).
            if re.match(rf"^ {{0,3}}{re.escape(fence_char)}{{{fence_len},}}[ \t]*$", line):
                fence_char = None
                fence_len = 0
            yield line, True
            continue
        m = _FENCE_OPEN_RE.match(line)
        if m:
            run, info = m.group(1), m.group(2)
            # A backtick info string may not contain a backtick (CommonMark) — else not a fence.
            if not (run[0] == "`" and "`" in info):
                fence_char, fence_len = run[0], len(run)
                yield line, True
                continue
        yield line, False


def _strip_inline_code(line: str) -> str:
    """Blank out Markdown inline code spans, honoring arbitrary backtick-run delimiters.

    A code span opens on a run of N backticks and closes on the next run of *exactly* N
    backticks (so ``` ``@x`` ``` is one span, not two empty ones). An un-closed run is left
    literal. Spans are replaced by spaces of equal length so column offsets are preserved.
    """
    out: list[str] = []
    i, n = 0, len(line)
    while i < n:
        if line[i] != "`":
            out.append(line[i])
            i += 1
            continue
        j = i
        while j < n and line[j] == "`":
            j += 1
        run = j - i  # opening delimiter length
        k = j
        closed = -1
        while k < n:
            if line[k] == "`":
                m = k
                while m < n and line[m] == "`":
                    m += 1
                if m - k == run:
                    closed = m
                    break
                k = m
            else:
                k += 1
        if closed == -1:  # no matching closing run — not a span; keep backticks literal
            out.append(line[i:j])
            i = j
        else:
            out.append(" " * (closed - i))
            i = closed
    return "".join(out)


@dataclass
class ClaudeImport:
    target: str         # raw token after '@'
    line_no: int
    kind: str           # 'same_root' | 'other_dir' | 'absolute' | 'parent'


def parse_agents_imports(text: str) -> tuple[list[ClaudeImport], bool]:
    """Return (agents_md_imports, saw_import_only_in_code).

    ``agents_md_imports`` are the *live* (not code-fenced, not inline-code) ``@``
    imports whose basename is ``AGENTS.md``. ``saw_import_only_in_code`` is True when
    an AGENTS.md import exists but ONLY inside code (so it is inert / malformed wiring)
    and no live one was found.
    """
    live: list[ClaudeImport] = []
    raw_has_agents_import = False   # an @AGENTS.md appears somewhere (incl. fenced/inline code)
    for i, (raw_line, in_code) in enumerate(_iter_lines_with_code_state(text), start=1):
        if any(
            _token_basename(m.group(1)) == "AGENTS.md"
            for m in _IMPORT_RE.finditer(raw_line)
        ):
            raw_has_agents_import = True
        if in_code:
            continue  # fenced @AGENTS.md is inert (not a live import)
        for m in _IMPORT_RE.finditer(_strip_inline_code(raw_line)):
            token = m.group(1)
            if _token_basename(token) != "AGENTS.md":
                continue
            live.append(ClaudeImport(token, i, _classify_target(token)))
    # Inert iff an @AGENTS.md was seen in the raw text but none survived as a live import.
    only_in_code = raw_has_agents_import and not live
    return live, only_in_code


def _classify_target(token: str) -> str:
    if _is_absolute(token):
        return "absolute"
    if _has_parent_segment(token):
        return "parent"
    # Same root iff it normalizes to exactly 'AGENTS.md' (dirname empty or '.'). Fold '\' to '/'
    # first so a Windows-style './AGENTS.md' is recognized on POSIX too (and a backslash subdir
    # like 'docs\AGENTS.md' is correctly seen as a non-same-root path, not a stray filename).
    norm = os.path.normpath(token.replace("\\", "/"))
    if norm == "AGENTS.md":
        return "same_root"
    return "other_dir"


# --------------------------------------------------------------------------- #
# Per-harness checks.
# --------------------------------------------------------------------------- #
def check_claude_code(root: str, report: Report) -> None:
    claude_md = os.path.join(root, "CLAUDE.md")
    agents_md = os.path.join(root, "AGENTS.md")
    agents_present = os.path.exists(agents_md)

    if not os.path.exists(claude_md):
        extra = (
            "a bare AGENTS.md is present but Claude Code does NOT auto-load it"
            if agents_present
            else "neither CLAUDE.md nor AGENTS.md is present"
        )
        report.error(
            "claude_missing_claude_md",
            "Claude Code target requires a root CLAUDE.md importing @AGENTS.md; "
            f"none found ({extra}).",
            claude_md,
        )
        return

    if _is_symlink_redirect(root, claude_md):
        report.error(
            "claude_wiring_symlink",
            "root CLAUDE.md is a symlink / redirect; the canonical wiring uses a real "
            "file at the adopter root.",
            claude_md,
        )
        return

    try:
        with open(claude_md, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        report.error("claude_unreadable", f"could not read CLAUDE.md: {exc}", claude_md)
        return

    imports, only_in_code = parse_agents_imports(text)
    same_root = [c for c in imports if c.kind == "same_root"]
    kinds = {c.kind for c in imports}

    # Escaping / non-same-root AGENTS.md imports are ALWAYS errors — a valid @AGENTS.md
    # alongside them does NOT excuse a path escape (it would still load an out-of-root file).
    if "absolute" in kinds:
        report.error(
            "claude_wiring_absolute_path",
            "CLAUDE.md imports AGENTS.md by an ABSOLUTE path; the wiring must use a clean "
            "same-root relative import (@AGENTS.md).",
            claude_md,
        )
    if "parent" in kinds:
        report.error(
            "claude_wiring_parent_escape",
            "CLAUDE.md imports AGENTS.md via a parent ('..') path; the wiring must reference "
            "the same-root AGENTS.md (@AGENTS.md).",
            claude_md,
        )
    if "other_dir" in kinds:
        report.error(
            "claude_wiring_not_same_root",
            "CLAUDE.md imports an AGENTS.md in a SUBDIRECTORY, not the same-root AGENTS.md; "
            "the canonical wiring is @AGENTS.md at the repo root.",
            claude_md,
        )

    if same_root:
        # A valid canonical import exists. Confirm the same-root AGENTS.md is real...
        if not agents_present:
            report.error(
                "claude_missing_agents_md",
                "CLAUDE.md imports @AGENTS.md but no AGENTS.md exists at the same root.",
                agents_md,
            )
        elif _is_symlink_redirect(root, agents_md):
            report.error(
                "claude_wiring_symlink",
                "root AGENTS.md is a symlink / redirect; the canonical chain must live in a "
                "real file at the adopter root.",
                agents_md,
            )
        # ...and that CLAUDE.md only IMPORTS the chain — it must NOT re-copy it (§1.1 MUST NOT;
        # dual entry points drift). This is an error, matching ONBOARDING Step 8.
        if _re_copies_chain(text):
            report.error(
                "claude_chain_duplicated",
                "CLAUDE.md re-copies the governance chain (imports under aidazi/governance/); "
                "it MUST import only @AGENTS.md, never duplicate the chain (context_briefing.md "
                "§1.1 — dual entry points drift).",
                claude_md,
            )
        return

    # No valid same-root import at all.
    if only_in_code:
        report.error(
            "claude_wiring_malformed",
            "CLAUDE.md mentions @AGENTS.md only inside a code span/block, where Claude Code "
            "does NOT evaluate it as an import; the wiring is inert.",
            claude_md,
        )
    elif not kinds:
        report.error(
            "claude_missing_wiring_line",
            "CLAUDE.md exists but has no valid line-level @AGENTS.md import; add the "
            "one-line import so Claude Code loads the AGENTS.md chain.",
            claude_md,
        )
    # else: the escape error(s) above already explain why there is no valid wiring.


_CHAIN_IMPORT_RE = re.compile(r"(?:^|\s)@\S*aidazi/governance/\S+")


def _re_copies_chain(text: str) -> bool:
    """Heuristic: CLAUDE.md imports the governance chain directly (dual entry point).

    Uses the same fenced/inline-code filtering as the import parser, so a fenced *example* of
    ``@aidazi/governance/...`` (documentation showing what NOT to do) does not false-fail.
    """
    for raw_line, in_code in _iter_lines_with_code_state(text):
        if in_code:
            continue
        if _CHAIN_IMPORT_RE.search(_strip_inline_code(raw_line)):
            return True
    return False


def check_codex(root: str, report: Report) -> None:
    agents_md = os.path.join(root, "AGENTS.md")
    if not os.path.exists(agents_md):
        report.error(
            "codex_missing_agents_md",
            "Codex target requires a root AGENTS.md (auto-loaded); none found.",
            agents_md,
        )
        return
    if _is_symlink_redirect(root, agents_md):
        report.error(
            "codex_missing_agents_md",
            "root AGENTS.md is a symlink / redirect or resolves outside the repo; it must be a "
            "real file at the adopter root.",
            agents_md,
        )
        return
    try:
        with open(agents_md, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError as exc:
        report.error("codex_missing_agents_md", f"could not read AGENTS.md: {exc}", agents_md)
        return
    if not content.strip():
        report.error(
            "codex_missing_agents_md",
            "root AGENTS.md is empty; Codex would auto-load an empty Control Plane entry.",
            agents_md,
        )
    # PASS: a Codex target does NOT require CLAUDE.md.


def _mdc_dir_has_valid_rule(root: str, rules_dir: str, report: Report) -> None:
    """A `.cursor/rules/` DIRECTORY is valid iff it holds >=1 non-empty ``*.mdc`` rule file
    that is a real file inside the root (not a symlink escaping it). Emits a blocking error
    otherwise."""
    try:
        names = sorted(os.listdir(rules_dir))
    except OSError as exc:
        report.error("cursor_rules_invalid", f"could not read .cursor/rules/: {exc}", rules_dir)
        return
    for name in names:
        if not name.endswith(".mdc"):
            continue
        mdc = os.path.join(rules_dir, name)
        if not os.path.isfile(mdc) or _is_symlink_redirect(root, mdc):
            continue
        try:
            with open(mdc, "r", encoding="utf-8") as fh:
                if fh.read().strip():
                    return  # PASS: a real, non-empty .mdc rule file.
        except OSError:
            continue
    report.error(
        "cursor_rules_invalid",
        ".cursor/rules/ contains no non-empty *.mdc rule file; add a real Cursor rules entry "
        "(a bare AGENTS.md is NOT Cursor wiring — context_briefing.md §1.1).",
        rules_dir,
    )


def check_cursor(root: str, report: Report) -> None:
    # A Cursor adopter's root-file wiring is Cursor's own rules mechanism: EITHER a legacy
    # single-file `.cursor/rules` OR the modern `.cursor/rules/` directory of `*.mdc` rule
    # files (governance/context_briefing.md §1.1). A bare AGENTS.md is NOT Cursor wiring, so a
    # missing/empty entry FAILs (blocking) — "validators green" then actually proves Cursor
    # wiring. The repo codifies no content contract, so validity = a real, non-empty entry.
    rules_path = os.path.join(root, ".cursor", "rules")
    if not os.path.exists(rules_path):
        report.error(
            "cursor_missing_rules",
            "Cursor target requires a real .cursor/rules entry (a bare AGENTS.md is NOT Cursor "
            "wiring — context_briefing.md §1.1); none found.",
            rules_path,
        )
        return
    if _is_symlink_redirect(root, rules_path):
        report.error(
            "cursor_rules_invalid",
            ".cursor/rules is a symlink / resolves outside the repo; it must be a real file or "
            "directory at the adopter root.",
            rules_path,
        )
        return
    if os.path.isdir(rules_path):
        _mdc_dir_has_valid_rule(root, rules_path, report)
        return
    if os.path.isfile(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except OSError as exc:
            report.error("cursor_rules_invalid", f"could not read .cursor/rules: {exc}", rules_path)
            return
        if not content.strip():
            report.error(
                "cursor_rules_invalid",
                ".cursor/rules is empty; an empty rules file is not Cursor wiring.",
                rules_path,
            )
        # PASS: a non-empty single-file .cursor/rules.
        return
    report.error(
        "cursor_rules_invalid",
        ".cursor/rules is neither a regular file nor a directory of *.mdc rules.",
        rules_path,
    )


# --------------------------------------------------------------------------- #
# Persistent harness declaration sources.
# --------------------------------------------------------------------------- #
def read_charter_root_harnesses(
    root: str, report: Report, charter_path: Optional[str] = None
) -> set[str]:
    """Root-file harnesses declared across the charter's per-role tooling.

    Reads ``tooling.<role>.harness`` (preferred) or legacy ``.agent_kind``; keeps only
    harnesses that auto-load a root file (drops headless / API roles). Missing charter =>
    empty set. Unparseable charter => empty set + a WARN (charter validity is owned by
    charter_validator, not this tool).
    """
    path = charter_path or os.path.join(root, "charter.yaml")
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (yaml.YAMLError, OSError) as exc:
        report.warn("charter_unreadable", f"could not parse charter.yaml: {exc}", path)
        return set()
    found: set[str] = set()
    tooling = (data or {}).get("tooling", {})
    if isinstance(tooling, dict):
        for role_cfg in tooling.values():
            if not isinstance(role_cfg, dict):
                continue
            norm = normalize_harness(role_cfg.get("harness") or role_cfg.get("agent_kind"))
            if norm in ROOT_FILE_HARNESSES:
                found.add(norm)
    return found


_PIN_RE = re.compile(r"<!--\s*adopter-root-harness:\s*(.*?)\s*-->", re.IGNORECASE)


def read_adoption_state_pin(
    root: str, report: Report, adoption_state_path: Optional[str] = None
) -> Optional[set[str]]:
    """Optional explicit root-harness pin from adoption-state.md.

    Looks for a schema-free HTML-comment marker ``<!-- adopter-root-harness: H[, H] -->``.
    Returns None when no marker is present; otherwise the set of recognized root-file
    harnesses it names (a marker naming only unrecognized values yields an empty set + WARN).
    """
    path = adoption_state_path or os.path.join(root, "docs", "current", "adoption-state.md")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    m = _PIN_RE.search(text)
    if not m:
        return None
    pinned: set[str] = set()
    for tok in re.split(r"[,\s]+", m.group(1).strip()):
        if not tok:
            continue
        norm = normalize_harness(tok)
        if norm in ROOT_FILE_HARNESSES:
            pinned.add(norm)
    if not pinned:
        report.warn(
            "adoption_state_pin_unrecognized",
            f"adoption-state.md pin marker names no recognized root-file harness: '{m.group(1)}'.",
            path,
        )
    return pinned


# --------------------------------------------------------------------------- #
# Target resolution + top-level validation.
# --------------------------------------------------------------------------- #
_CHECKS = {
    "claude_code": check_claude_code,
    "codex": check_codex,
    "cursor": check_cursor,
}


def validate_root(
    root: str,
    harness: Optional[str] = None,
    charter_path: Optional[str] = None,
    adoption_state_path: Optional[str] = None,
) -> Report:
    """Validate an adopter root's harness root-file wiring. Pure over the tree."""
    report = Report()

    if not os.path.isdir(root):
        report.error("missing_root", f"adopter root is not a directory: {root}", root)
        return report

    # Persistent declarations + conflict (computed regardless of --harness, so an explicit CLI
    # target cannot mask a genuine persistent-source contradiction). A conflict is a genuine
    # CONTRADICTION: both sources name a non-empty root-file harness set and they are DISJOINT
    # (no shared harness). Partial overlap is not a contradiction — the union is validated.
    charter_set = read_charter_root_harnesses(root, report, charter_path)
    pin_set = read_adoption_state_pin(root, report, adoption_state_path)
    conflict = bool(charter_set) and bool(pin_set) and charter_set.isdisjoint(pin_set)
    if conflict:
        report.error(
            "harness_conflict",
            f"persistent harness declarations CONTRADICT — charter.yaml declares "
            f"{sorted(charter_set)} but adoption-state pins {sorted(pin_set)} (disjoint, no shared "
            "harness); resolve the sources (the tool will not silently pick one). Priority: "
            "explicit --harness > a single contradiction-free declaration > unspecified.",
            root,
        )

    # Resolve the target set for this invocation.
    targets: set[str] = set()
    if harness is not None:
        norm = normalize_harness(harness)
        if norm is None:
            report.error(
                "unknown_harness",
                f"unrecognized --harness '{harness}'; expected one of "
                f"claude_code | codex | cursor | headless.",
                root,
            )
            return report
        if norm == "headless":
            report.warn(
                "harness_not_root_file",
                "harness 'headless' is API-backed and loads no repo-root file; nothing to "
                "validate.",
                root,
            )
            return report
        targets = {norm}
    elif conflict:
        targets = set()  # do not auto-pick under conflict; the error stands.
    elif charter_set or pin_set:
        targets = set(charter_set) | set(pin_set or set())
    else:
        report.warn(
            "harness_unspecified",
            "no --harness and no formal adopter harness declaration (charter tooling / "
            "adoption-state pin); cannot determine the target harness. Pass --harness or "
            "declare it. (Codex-only adopters need only a root AGENTS.md.)",
            root,
        )
        return report

    report.targets = sorted(targets)
    for target in report.targets:
        _CHECKS[target](root, report)
    return report


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic (no-LLM) validator for adopter harness root-file wiring "
        "(governance/context_briefing.md §1.1).",
    )
    parser.add_argument("root", help="path to the adopter repo root")
    parser.add_argument(
        "--harness",
        default=None,
        help="explicit target harness: claude_code | codex | cursor | headless "
        "(default: resolve from charter tooling / adoption-state pin)",
    )
    parser.add_argument(
        "--charter",
        default=None,
        help="override path to charter.yaml (default: <root>/charter.yaml)",
    )
    parser.add_argument(
        "--adoption-state",
        default=None,
        help="override path to adoption-state.md "
        "(default: <root>/docs/current/adoption-state.md)",
    )
    args = parser.parse_args(argv)

    report = validate_root(args.root, args.harness, args.charter, args.adoption_state)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Phase-5 deterministic scorers — EXACT implementations of the FROZEN Phase-0
pre-registration contracts (universal-skill-mounting design §7; the frozen bytes live in
archive/wp-skill-canary/preregistration/). NO LLM judging anywhere; every function is a
pure, deterministic function of its inputs. The Phase-5 gate verifies scorer ≡ contract.

α  — ``alpha_score_rep(plan, fixture, vocab)``: pure over (produced deliver-plan JSON,
     the frozen alpha-manifest fixture entry). Schema validity is enforced UPSTREAM by
     the real decompose contract (driver ``validate_verdict``); a schema-invalid plan
     never reaches this scorer (the repetition already FAILED by the manifest's
     ``schema`` rule).
β  — ``beta_read_observed(stream_text, skill_md_path)`` + the audit's
     ``skill_consumption == "observed"`` (checked by the harness): the frozen per-rep
     PASS is BOTH.
γ  — ``gamma_score_artifact(root)``: Check-0 completeness precondition then the 10-check
     list, over the produced artifact files (stdlib html.parser — no external deps).
     Returns (score 0-10, detail). A Check-0 failure forces score 0.

OPERATIONALIZATION NOTES (each check maps 1:1 to the frozen gamma-checklist.json rule;
where the frozen prose names a semantic ("the icon-only toggle", "loading/progress
strings") the deterministic operationalization is documented at the check):
  * icon-only button  := a ``<button>`` whose ``type`` is not ``submit`` and whose text
    content contains NO ASCII alphanumeric character (icon glyph / svg / img only).
  * loading/progress string := a JS string literal or HTML text node containing any of
    load/send/submit/sign/wait/progress/pending (case-insensitive) — check 8 requires
    no such string to carry the three-dot "..." (the spread operator is NOT inside a
    string literal and therefore never matches).
  * status region := an element carrying ``aria-live`` OR whose id/class contains
    "status" (check 0(e)); check 7 then requires an ``aria-live="polite"`` element.

The module SELF-VERIFIES against the frozen contract at import: ``load_gamma_contract``
asserts the checklist ids/order and thresholds match what this scorer implements —
any drift raises instead of silently scoring against a stale contract.
"""

from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
PREREG_DIR = os.path.join(_REPO_ROOT, "archive", "wp-skill-canary", "preregistration")

#: The constants this scorer implements. load_gamma_contract() asserts the frozen
#: file still says exactly this (scorer ≡ contract, verified at import/run time).
GAMMA_EXPECTED = {
    "check_ids": list(range(1, 11)),
    "pairs": 3,
    "ordering": ["AB", "BA", "AB"],
    "pass_pairs_required": 2,
    "score_margin_required": 2,
    "beta_repetitions": 3,
    "beta_pass_threshold": 2,
    "arm_a_task_signals": ["interaction"],
    "expected_signal_selected_skills": ["web-interface-guidelines"],
}


class ContractMismatch(AssertionError):
    """The frozen pre-registration contract no longer matches this scorer."""


def load_gamma_contract(path: Optional[str] = None) -> dict:
    """Load gamma-checklist.json and VERIFY it matches the constants this scorer
    implements. Raises ContractMismatch on ANY divergence — the scorer must never
    silently score against a drifted contract."""
    path = path or os.path.join(PREREG_DIR, "gamma-checklist.json")
    with open(path, encoding="utf-8") as fh:
        contract = json.load(fh)
    got = {
        "check_ids": [c.get("id") for c in contract.get("checks", [])],
        "pairs": contract.get("pairs"),
        "ordering": contract.get("ordering"),
        "pass_pairs_required": contract.get("pass_pairs_required"),
        "score_margin_required": contract.get("score_margin_required"),
        "beta_repetitions": contract.get("beta_repetitions"),
        "beta_pass_threshold": contract.get("beta_pass_threshold"),
        "arm_a_task_signals": contract.get("arm_a_task_signals"),
        "expected_signal_selected_skills":
            contract.get("expected_signal_selected_skills"),
    }
    if got != GAMMA_EXPECTED:
        raise ContractMismatch(
            f"gamma-checklist.json diverged from the scorer's implemented contract:\n"
            f"  contract: {got}\n  scorer  : {GAMMA_EXPECTED}")
    if len(contract.get("check0_completeness", {}).get("required_elements", [])) != 6:
        raise ContractMismatch("check0_completeness must carry exactly 6 elements")
    return contract


def load_alpha_manifest(path: Optional[str] = None) -> dict:
    path = path or os.path.join(PREREG_DIR, "alpha-manifest.json")
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    if manifest.get("repetitions_per_fixture") != 3:
        raise ContractMismatch("alpha-manifest repetitions_per_fixture must be 3")
    if sorted(manifest.get("fixtures", {})) != ["nonui-milestone", "ui-milestone"]:
        raise ContractMismatch("alpha-manifest must carry exactly the two fixtures")
    return manifest


# --------------------------------------------------------------------------- #
# α scorer — pure over (produced plan JSON, frozen fixture entry, frozen vocab).
# --------------------------------------------------------------------------- #
def alpha_score_rep(plan: dict, fixture: dict, vocab: list) -> dict:
    """One α repetition against one frozen fixture entry. ``plan`` is the
    SCHEMA-VALID deliver-plan verdict (schema enforcement is upstream). Rules are
    the manifest's, verbatim: id_set equality; ui ⇒ task_signals present, non-empty,
    ⊆ vocab; non_ui ⇒ task_signals absent OR an empty array."""
    produced = {str(s.get("id")): s for s in (plan.get("sub_sprints") or [])
                if isinstance(s, dict)}
    prescribed = fixture["prescribed_subsprints"]
    id_set_ok = set(produced) == set(prescribed)
    per_id: dict = {}
    for sid, kind in prescribed.items():
        entry = produced.get(sid)
        if entry is None:
            per_id[sid] = {"ok": False, "reason": "prescribed id missing from plan"}
            continue
        has_field = "task_signals" in entry
        sig = entry.get("task_signals")
        if kind == "ui":
            ok = (isinstance(sig, list) and len(sig) > 0
                  and set(str(x) for x in sig) <= set(vocab))
            reason = None if ok else (
                "ui sub-sprint must carry non-empty in-vocab task_signals; got "
                f"{sig!r}")
        else:
            ok = (not has_field) or (isinstance(sig, list) and len(sig) == 0)
            reason = None if ok else (
                f"non-ui sub-sprint must omit task_signals (or []); got {sig!r}")
        per_id[sid] = {"ok": ok, "reason": reason,
                       "task_signals": sig if has_field else None}
    extras = sorted(set(produced) - set(prescribed))
    rep_pass = id_set_ok and all(v["ok"] for v in per_id.values())
    return {"pass": rep_pass, "id_set_ok": id_set_ok, "extra_ids": extras,
            "per_id": per_id}


# --------------------------------------------------------------------------- #
# β read-evidence — pure over (raw stream-json text, the mounted SKILL.md path).
# --------------------------------------------------------------------------- #
def beta_read_observed(stream_text: str, skill_md_path: str,
                       cwd: Optional[str] = None) -> dict:
    """True iff the stream-json contains ≥1 Read tool_use whose realpath equals the
    mounted SKILL.md realpath (a RELATIVE tool path is resolved against ``cwd`` —
    the spawned agent's working directory — before the realpath compare). Parses
    stream lines independently (the same event shape the adapter's
    parse_read_paths consumes) so the harness cross-checks the framework's own
    telemetry rather than trusting it."""
    target = os.path.realpath(skill_md_path)
    reads: list = []
    for line in (stream_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        msg = event.get("message") if isinstance(event, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        for block in content if isinstance(content, list) else []:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            if str(block.get("name")) != "Read":
                continue
            fp = (block.get("input") or {}).get("file_path")
            if isinstance(fp, str) and fp:
                reads.append(fp)

    def _resolve(p: str) -> str:
        if not os.path.isabs(p) and cwd:
            p = os.path.join(cwd, p)
        return os.path.realpath(p)

    matched = [p for p in reads if _resolve(p) == target]
    return {"observed": bool(matched), "matched_paths": matched,
            "all_read_paths": reads}


# --------------------------------------------------------------------------- #
# γ scorer — Check 0 + the 10-check list over the produced artifact files.
# --------------------------------------------------------------------------- #
_EXCLUDED_DIRS = {"aidazi", ".orchestrator", ".runs", "compact", "docs", ".git",
                  ".claude", "node_modules", "__pycache__"}


class _Doc(HTMLParser):
    """Minimal deterministic HTML collector (stdlib-only)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements: list = []          # (tag, attrs_dict)
        self.headings: list = []          # levels, document order
        self.h1_count = 0
        self.texts: list = []             # text nodes
        self.style_blocks: list = []
        self.script_blocks: list = []
        self._stack: list = []            # (tag, attrs, text_parts)
        self._in_style = False
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        attrs_d = {k.lower(): (v if v is not None else "") for k, v in attrs}
        self.elements.append((tag.lower(), attrs_d))
        self._stack.append([tag.lower(), attrs_d, []])
        if tag.lower() == "style":
            self._in_style = True
        if tag.lower() == "script":
            self._in_script = True
        m = re.fullmatch(r"h([1-6])", tag.lower())
        if m:
            self.headings.append(int(m.group(1)))
            if m.group(1) == "1":
                self.h1_count += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag.lower() == "style":
            self._in_style = False
        if tag.lower() == "script":
            self._in_script = False
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag.lower():
                closed = self._stack.pop(i)
                closed_text = "".join(closed[2])
                # record the element's own text for icon-only detection
                closed[1]["__text__"] = closed_text
                if i - 1 >= 0:
                    self._stack[i - 1][2].append(closed_text)
                break

    def handle_data(self, data):
        if self._in_style:
            self.style_blocks.append(data)
            return
        if self._in_script:
            self.script_blocks.append(data)
            return
        if data.strip():
            self.texts.append(data)
        if self._stack:
            self._stack[-1][2].append(data)


def _collect_artifact_files(root: str) -> dict:
    out = {"html": [], "css": [], "js": []}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in _EXCLUDED_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            low = name.lower()
            if low.endswith((".html", ".htm")):
                out["html"].append(path)
            elif low.endswith(".css"):
                out["css"].append(path)
            elif low.endswith(".js"):
                out["js"].append(path)
    return out


def _read_all(paths: list) -> str:
    parts = []
    for p in paths:
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                parts.append(fh.read())
        except OSError:
            continue
    return "\n".join(parts)


def _parse_docs(html_paths: list) -> list:
    docs = []
    for p in html_paths:
        doc = _Doc()
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                doc.feed(fh.read())
        except OSError:
            continue
        docs.append(doc)
    return docs


def _buttons(docs: list) -> list:
    out = []
    for d in docs:
        for tag, attrs in d.elements:
            if tag == "button":
                out.append(attrs)
    return out


def _icon_only_buttons(docs: list) -> list:
    """Frozen operationalization: a <button> whose type is not submit and whose own
    text content carries NO ASCII alphanumeric (glyph/svg/img-only)."""
    out = []
    for attrs in _buttons(docs):
        if attrs.get("type", "").lower() == "submit":
            continue
        text = attrs.get("__text__", "")
        if not re.search(r"[A-Za-z0-9]", text):
            out.append(attrs)
    return out


def _inputs(docs: list) -> list:
    out = []
    for d in docs:
        for tag, attrs in d.elements:
            if tag == "input":
                out.append(attrs)
    return out


def _form_inputs(docs: list) -> list:
    skip = {"hidden", "submit", "button", "reset"}
    return [a for a in _inputs(docs) if a.get("type", "text").lower() not in skip]


def _labels_for(docs: list) -> set:
    out = set()
    for d in docs:
        for tag, attrs in d.elements:
            if tag == "label" and attrs.get("for"):
                out.add(attrs["for"])
    return out


def _norm_css(css: str) -> str:
    return re.sub(r"\s+", "", css.lower())


_STRING_LITERAL_RE = re.compile(r"(['\"`])((?:\\.|(?!\1).)*)\1", re.S)
_PROGRESS_WORDS_RE = re.compile(
    r"load|send|submit|sign|wait|progress|pending", re.I)


def _progress_strings(js_text: str, docs: list) -> list:
    """All loading/progress-semantic strings: JS string literals + HTML text nodes
    mentioning load/send/submit/sign/wait/progress/pending (case-insensitive)."""
    out = [m.group(2) for m in _STRING_LITERAL_RE.finditer(js_text or "")
           if _PROGRESS_WORDS_RE.search(m.group(2))]
    for d in docs:
        out += [t for t in d.texts if _PROGRESS_WORDS_RE.search(t)]
    return out


def gamma_check0(docs: list, js_text: str) -> dict:
    """The 6 frozen completeness elements. ANY missing ⇒ the arm scores 0."""
    imgs = [a for d in docs for t, a in d.elements if t == "img"]
    inputs = _inputs(docs)
    email = any(a.get("type", "").lower() == "email"
                or "email" in (a.get("name", "") + a.get("id", "")).lower()
                for a in inputs)
    password = any(a.get("type", "").lower() == "password"
                   or "password" in (a.get("name", "") + a.get("id", "")).lower()
                   for a in inputs)
    toggles = _icon_only_buttons(docs)
    submit = (any(a.get("type", "").lower() == "submit" for a in _buttons(docs))
              or any(a.get("type", "").lower() == "submit" for a in inputs))
    async_js = bool(re.search(r"setTimeout|Promise|async|await", js_text or ""))
    status = any(("aria-live" in a)
                 or ("status" in (a.get("id", "") + a.get("class", "")).lower())
                 for d in docs for _t, a in d.elements)
    h1 = sum(d.h1_count for d in docs)
    extra_headings = sum(1 for d in docs for lvl in d.headings if lvl >= 2)
    elements = {
        "img_logo": len(imgs) >= 1,
        "email_and_password_inputs": email and password,
        "icon_only_toggle_button": len(toggles) >= 1,
        "submit_wired_async": submit and async_js,
        "status_region": status,
        "h1_and_features_heading": h1 >= 1 and extra_headings >= 1,
    }
    return {"complete": all(elements.values()), "elements": elements}


def gamma_score_artifact(root: str) -> dict:
    """Score one arm's produced artifact directory: Check 0 then checks 1-10.
    Deterministic + pure over the files. Check-0 failure ⇒ score 0 (checks still
    reported for the record)."""
    files = _collect_artifact_files(root)
    docs = _parse_docs(files["html"])
    inline_css = "\n".join(b for d in docs for b in d.style_blocks)
    inline_js = "\n".join(b for d in docs for b in d.script_blocks)
    css_text = _read_all(files["css"]) + "\n" + inline_css
    js_text = _read_all(files["js"]) + "\n" + inline_js
    html_text = _read_all(files["html"])
    ncss = _norm_css(css_text)

    check0 = gamma_check0(docs, js_text)
    checks: dict = {}

    imgs = [a for d in docs for t, a in d.elements if t == "img"]
    checks[1] = bool(imgs) and all(a.get("width") and a.get("height")
                                   for a in imgs)

    toggles = _icon_only_buttons(docs)
    checks[2] = bool(toggles) and all((a.get("aria-label") or "").strip()
                                      for a in toggles)

    form_inputs = _form_inputs(docs)
    labeled = _labels_for(docs)
    checks[3] = bool(form_inputs) and all(
        ((a.get("id") in labeled) or (a.get("aria-label") or "").strip())
        and ("autocomplete" in a)
        for a in form_inputs)

    focus_visible = ("focus-visible" in css_text.lower())
    outline_none = ("outline:none" in ncss) or ("outline-none" in ncss)
    checks[4] = focus_visible and ((not outline_none) or focus_visible)

    animated = bool(re.search(r"transition|animation|@keyframes", css_text,
                              re.I))
    checks[5] = (not animated) or (
        ("prefers-reduced-motion" in css_text.lower())
        and ("transition:all" not in ncss))

    onclick_div_span = any(
        t in ("div", "span") and "onclick" in a
        for d in docs for t, a in d.elements)
    onclick_raw = bool(re.search(r"<(div|span)[^>]*\bonclick\s*=", html_text,
                                 re.I))
    checks[6] = not (onclick_div_span or onclick_raw)

    checks[7] = any(a.get("aria-live", "").strip().lower() == "polite"
                    for d in docs for _t, a in d.elements)

    checks[8] = all("..." not in s for s in _progress_strings(js_text, docs))

    checks[9] = "touch-action:manipulation" in ncss

    h1_total = sum(d.h1_count for d in docs)
    no_skips = True
    for d in docs:
        prev = 0
        for lvl in d.headings:
            if lvl > prev + 1:
                no_skips = False
            prev = lvl
    checks[10] = (h1_total == 1) and no_skips and any(d.headings for d in docs)

    raw_score = sum(1 for v in checks.values() if v)
    score = raw_score if check0["complete"] else 0
    return {"score": score, "raw_checklist_score": raw_score,
            "check0": check0, "checks": {str(k): v for k, v in checks.items()},
            "files": {k: [os.path.relpath(p, root) for p in v]
                      for k, v in files.items()}}


def gamma_pair_success(arm_a: dict, arm_b: dict, arm_a_read: bool,
                       margin: int = 2) -> bool:
    """The frozen per-pair rule: arm A read the mounted SKILL.md AND
    score_A >= score_B + margin."""
    return bool(arm_a_read) and (arm_a["score"] >= arm_b["score"] + margin)

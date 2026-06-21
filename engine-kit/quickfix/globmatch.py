"""Safe-subset glob matcher with gitignore-style ``**`` semantics (Quick-Fix guard).

The ONLY glob grammar the Quick-Fix lane accepts (mirrors the schema-approved subset):

    letters, digits, '.', '_', '-', '/', and the wildcards '*', '**', '?'

Anything else — character classes ``[...]``, brace expansion ``{...}``, commas,
negation ``!``, a leading ``/`` or ``~``, or a ``..`` path segment — is REJECTED
(``GlobError``, fail-closed), because such forms can smuggle traversal/absolute
semantics (``[.][.]``, ``{../x}``, ``[/]etc``). The matcher does not "best-effort"
an unknown pattern; it refuses it.

Matching is against a repo-relative POSIX path. Semantics:

  * ``*``  matches any run of NON-slash characters (does not cross ``/``).
  * ``?``  matches exactly one non-slash character.
  * ``**`` is a WHOLE segment only and matches zero or more path segments:
      - leading ``**/``  -> optional leading directories (so ``**/schemas/**``
        matches ``schemas/x`` at the root AND ``aidazi/schemas/x`` when vendored);
      - middle ``/**/``  -> ``a/**/b`` matches ``a/b``, ``a/x/b``, ``a/x/y/b``;
      - trailing ``/**`` -> ``schemas/**`` matches ``schemas/x`` and deeper (one+
        segment; a bare directory path is never a touched *file*).
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

from .errors import GlobError

# The approved safe subset, as a whole-string guard (no other characters permitted).
_SAFE = re.compile(r"^[A-Za-z0-9._/*?-]+$")


def _validate(glob: str) -> List[str]:
    """Validate a glob is in the safe subset; return its path segments. Fail-closed."""
    if not glob or not _SAFE.fullmatch(glob):
        raise GlobError(f"glob not in safe subset: {glob!r}")
    if glob.startswith("/") or glob.startswith("~"):
        raise GlobError(f"glob must be repo-relative (no leading '/' or '~'): {glob!r}")
    segs = glob.split("/")
    for s in segs:
        if s == "..":
            raise GlobError(f"glob may not contain a '..' segment: {glob!r}")
        if "**" in s and s != "**":
            raise GlobError(f"'**' must be a whole path segment: {glob!r}")
    return segs


def _to_regex(glob: str) -> str:
    """Translate a validated safe-subset glob to a full-match regex body."""
    out: List[str] = []
    i, n = 0, len(glob)
    while i < n:
        if glob.startswith("**", i):
            prev_slash = (i == 0) or (glob[i - 1] == "/")
            j = i + 2
            next_is_slash = (j < n) and (glob[j] == "/")
            at_end = (j == n)
            if not prev_slash or not (next_is_slash or at_end):
                # Defensive: validation already guarantees whole-segment '**'.
                raise GlobError(f"malformed '**' in glob: {glob!r}")
            if next_is_slash:
                # '**/...' -> optional leading dirs (consume the trailing slash).
                out.append(r"(?:[^/]+/)*")
                i = j + 1
            else:
                # trailing '/**' or a lone '**' -> one-or-more / any path remainder.
                out.append(r".+")
                i = j
        else:
            c = glob[i]
            if c == "*":
                out.append(r"[^/]*")
            elif c == "?":
                out.append(r"[^/]")
            else:
                out.append(re.escape(c))
            i += 1
    return "".join(out)


class Glob:
    """A compiled safe-subset glob. ``matches(path)`` tests a repo-relative POSIX path."""

    __slots__ = ("pattern", "_rx")

    def __init__(self, pattern: str):
        _validate(pattern)
        self.pattern = pattern
        self._rx = re.compile("^" + _to_regex(pattern) + "$")

    def matches(self, path: str) -> bool:
        return self._rx.match(path) is not None

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Glob({self.pattern!r})"


def compile_globs(patterns: Iterable[str]) -> List[Glob]:
    """Compile a list of globs (fail-closed on the first unsupported pattern)."""
    return [Glob(p) for p in patterns]


def matches_any(path: str, globs: Iterable[Glob]) -> bool:
    return any(g.matches(path) for g in globs)


def first_match(path: str, globs: Iterable["NamedGlobs"]) -> Optional[str]:
    """Return the id of the first NamedGlobs whose any glob matches, else None."""
    for ng in globs:
        if matches_any(path, ng.globs):
            return ng.id
    return None


class NamedGlobs:
    """A named bundle of compiled globs (one protected surface or scope group)."""

    __slots__ = ("id", "globs", "reason")

    def __init__(self, id: str, patterns: Iterable[str], reason: str = ""):
        self.id = id
        self.globs = compile_globs(patterns)
        self.reason = reason

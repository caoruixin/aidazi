# aidazi tools

Small scripts that implement the framework's mandatory defaults (per
`README.md` §"What this framework gives you").

## Installation

```bash
# In your consumer project (assuming aidazi is at framework/)
pip install jsonschema

# Optional: install the pre-commit hook
ln -s ../../framework/tools/precommit_bundling_check.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Tools

### `stanza_validator.py`

Validates the §7 stanza in a sub-sprint objective against
`../schemas/sprint_stanza.schema.json`.

```bash
python framework/tools/stanza_validator.py docs/sprint_objective.md
```

Exit code 0 = valid; non-zero = violation with diagnostics on stderr.

The validator parses the Markdown stanza block under the heading
`## Layer-classification + anti-hardcode stanza` and validates the
four required fields:

- `target_failure_layer` (enum)
- `tier0_invariant` (oneOf: none / protects_existing / new_candidate)
- `semantic_hardcode` (oneOf: introduced=false / introduced=true with
  sunset_plan)
- `generalization_coverage` (oneOf: declared with T/N/G/S counts /
  deferred)

### `precommit_bundling_check.sh`

Git pre-commit hook that warns when dev sessions accidentally bundle
deliver-agent owned files (per `governance/constitution.md` §8.7).

Bypass for legitimate close commits: prefix the commit message with
`[close]` or set `AIDAZI_ALLOW_DELIVER_FILES=1`.

The deliver-agent owned file patterns are hard-coded near the top of
the script. Edit the `DELIVER_OWNED_PATTERNS` array if your project
deviates from the default layout.

### `trace_emitter.py`

Library for emitting structured `trace.jsonl` records from dev /
review sessions. Per `governance/context_briefing.md`.

Trace records are append-only JSON lines:

```jsonl
{"timestamp": "...", "event": "session_start", "role": "dev", ...}
{"timestamp": "...", "event": "decision", "type": "read_file", "path": "...", ...}
{"timestamp": "...", "event": "blocker", "type": "hard_fence_breach_attempt", ...}
{"timestamp": "...", "event": "session_end", "verdict_summary": "..."}
```

See the module docstring for usage example.

## Dependencies

- Python 3.10+
- jsonschema (for stanza_validator)

No other runtime dependencies. These scripts intentionally use the
Python standard library only (plus jsonschema) so they remain easy to
embed in any consumer project.

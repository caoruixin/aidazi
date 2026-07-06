# Milestone brief — csv-export-cli (Probe-α fixture ii, FROZEN at Phase 0)

**Milestone id:** `csv-export-cli`
**Objective:** add a CSV export command-line tool with unit tests. No user interface of any
kind is in scope for this milestone.

## Prescribed decomposition (use these sub-sprint ids VERBATIM — exactly these three, no more, no fewer)

1. **`s1-csv-serializer`** — Implement the CSV serialization module: record-to-row mapping,
   correct quoting/escaping, configurable delimiter. Scope_in: library/module files.
   Scope_out: CLI argument handling, tests, any UI.
   Exit criteria: serializer produces RFC-4180-conformant output for the sample records.

2. **`s2-cli-entrypoint`** — Implement the command-line entrypoint: argument parsing
   (input path, output path, delimiter flag), exit codes, error messages to stderr.
   Scope_in: CLI entry files. Scope_out: serializer internals, tests, any UI.
   Exit criteria: tool runs end-to-end on a sample file; nonzero exit on bad arguments.

3. **`s3-unit-tests`** — Author unit tests for the serializer and the CLI (happy path,
   quoting edge cases, bad-arguments). Scope_in: test files only. Scope_out: production code
   changes beyond what tests require, any UI.
   Exit criteria: test suite passes; edge cases covered.

## Signal-authoring reminder (part of the fixture)

For each sub-sprint, author `task_signals` per the decompose contract: use ONLY the closed
vocabulary; pick the FEW signals that genuinely apply; OMIT `task_signals` entirely for
non-UI sub-sprints.

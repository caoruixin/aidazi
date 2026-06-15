# charter_validator

Deterministic, no-LLM, no-network hard-kernel validator for a Δ-18 mission charter. It runs two layers: (A) **structural** validation of the charter YAML against `schemas/mission-charter.schema.json` via `jsonschema`, and (B) **semantic** rules the schema cannot express — the 8 default MANDATORY_CHECKPOINTS may not be bypassed in any of the four shapes (omitted / emptied / disabled / overridden, including auto-confirm-style semantic weakening), `acceptance.on_fix_required.human_confirm_required` must be `true`, `acceptance.on_fix_required.route_options` must be a non-empty list, `adaptive_insert` requires a `max_inserted_subsprints` bound when enabled, and it WARNs when `tooling.acceptance.skills` is present while `judge_calibration.status: calibrated` (calibration corollary). CLI: `python charter_validator.py <charter.yaml>` (exit 0 on pass, non-zero on any error; warnings do not fail). This is an engine-kit *implementation* only — the **normative source of these rules stays in `process/delivery-loop.md` §4.2.2 + governance/constitution.md §1.7-D** (and §1.7-C, §3.6); if this file and the spec disagree, the spec wins. P-0a facets (connectors default-deny, harness×model capability gate, skill integrity) are left as no-op extension-point functions pending their schemas.

## Run

```
python3 -m venv /tmp/aidazi-p1-venv
/tmp/aidazi-p1-venv/bin/pip install -r requirements.txt
/tmp/aidazi-p1-venv/bin/python charter_validator.py tests/fixtures/valid-charter.yaml
/tmp/aidazi-p1-venv/bin/python -m unittest discover -s tests -v
```

# stanza_validator

Deterministic, no-LLM, no-network validator for a sprint-stanza — the compact 4-field machine-validated header (`sprint_id`, `scope_in`, `layers`, `exit_criteria`, plus optional `modules` / `milestone_id` / `next_subsprint`) carried in the front-matter of `docs/sprint_objective.md`. It mechanizes friction case F4 (`docs/friction-playbook.md`): catch a stanza with missing or wrong-typed fields BEFORE the compact dev prompt is dispatched, not at the expensive close gate. The single structural layer validates the stanza (YAML or JSON; a JSON file parses through the same `yaml.safe_load` path) against `schemas/sprint_stanza.schema.json` via `jsonschema`, reporting each finding with a clear message and the offending path; it accepts either a bare stanza mapping or a document carrying a `sprint_stanza:` key (unwrapped automatically). CLI: `python stanza_validator.py <stanza.(yaml|json)>` (exit 0 on a schema-valid stanza, non-zero on a schema-load failure, parse failure, or any structural error). This is an engine-kit *implementation* of the orchestrator's `validate_stanza` preflight gate (`process/delivery-loop.md` §4.2.4); the **normative source stays in `schemas/sprint_stanza.schema.json`** (and the F4 discipline in `docs/friction-playbook.md`). If this file and the schema disagree, the schema wins.

Run the same way as above, substituting `stanza_validator.py tests/fixtures/valid-stanza.yaml`; both suites are discovered together by `python -m unittest discover -s tests -v`.

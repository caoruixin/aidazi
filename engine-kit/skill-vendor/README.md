# skill_vendor

Deterministic-where-it-counts tool that scripts aidazi's manual skill-vendoring + integrity-verify flow (plan `archive/2026-06-15-v2-loop-engine-plan.md` §4.1 facet B): vendored skills are COPIED and PINNED by commit, never runtime-fetched; each `skills/vendored/<id>/` retains the upstream LICENSE plus a `_provenance.yaml`, and integrity is locked in `skills/skills.lock`. The `verify [<id>...]` subcommand (the priority, fully OFFLINE) recomputes each vendored skill's tree hash and per-file hashes and compares them against both `skills/skills.lock` and the skill's `_provenance.yaml`, exiting non-zero on any mismatch (missing/added/tampered file or a stale lock). The tree hash reproduces the committed lock byte-for-byte by mirroring the original bash scheme — `per_file = sha256(bytes)` (`shasum -a 256`), files enumerated as `./<relpath>` excluding `_provenance.yaml`, C-locale (`sorted()`) order, a shasum-text-mode manifest with two spaces between hash and path, then `sha256(manifest)` — equivalent to `find . -type f ! -name _provenance.yaml | sort | xargs shasum -a 256 | shasum -a 256`. The `vendor <id>` subcommand is the only git-using path (shallow-fetch at the pinned commit, copy the folder, preserve LICENSE, write `_provenance.yaml`, update `skills.lock`); it is implemented for completeness, takes an injectable `--retrieved-at` so it has no hidden clock, and is never exercised by the tests (which are fully offline). CLI: `python skill_vendor.py verify` (exit 0 iff every skill matches) and `python skill_vendor.py vendor <id>`. This is an engine-kit *implementation* of the supply-chain discipline; the **normative source stays in `skills/skills.lock` + `skills/registry.yaml` + each `skills/vendored/<id>/_provenance.yaml`** (the ground-truth pins this tool verifies against) and the facet-B rules in the plan. If this tool and the committed lock disagree, the lock wins.

## Run

```
python3 -m venv /tmp/aidazi-skillvendor-venv
/tmp/aidazi-skillvendor-venv/bin/pip install -r requirements.txt
/tmp/aidazi-skillvendor-venv/bin/python skill_vendor.py verify
/tmp/aidazi-skillvendor-venv/bin/python -m unittest discover -s tests -v
```

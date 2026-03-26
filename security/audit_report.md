# Security Audit Report

Date: 2026-03-26

## Scope

This audit covered the prompt 28 checklist across the repository:

- API key handling
- YAML loader safety
- SQL injection exposure in SQLite access
- Rich output rendering and markup injection
- Path traversal protection for user-supplied paths
- HTTP transport and timeout configuration
- `.gitignore` and generated project safety defaults
- Test fixture secret hygiene

## What Was Checked

The audit used grep-style checks plus targeted code review of the affected modules.

Checks performed:

- `api_key` usage across `packages`, `docs`, `examples`, and `scripts`
- `yaml.load(` usage across Python files
- `console.print(` usage across the CLI package
- `verify=False` and `http://` usage across runtime code, tests, docs, and assets
- user-supplied path handling for dataset and prompt commands
- SQL string interpolation risk in `packages/cli/evalflow/storage`

## What Was Found

### Fixed during this audit

1. User-supplied dataset paths were not resolved safely.
   - `evalflow eval --dataset ...` and `evalflow dataset lint ...` accepted arbitrary paths directly.
   - This allowed path traversal outside the current project directory.

2. Config and dataset loaders did not enforce allowed file extensions.
   - `EvalflowConfig.from_yaml()` did not reject non-YAML config file extensions.
   - `Dataset.from_json()` did not reject non-JSON dataset file extensions.

3. The README security section was incomplete relative to the security spec.
   - It did not explicitly state that config files are safe to commit.
   - It did not link to the full security model.
   - It did not include a responsible disclosure section.

4. Some tests used generic secret strings like `"secret"` and `"secret-key"`.
   - These were not real secrets, but they were normalized to clearly fake values for consistency.

### Confirmed safe

1. No runtime use of `yaml.load(` was found.
   - Runtime config/prompt parsing uses `yaml.safe_load()`.

2. No interpolated SQL queries were found in the storage layer.
   - SQLite access uses parameterized `?` placeholders.

3. No `verify=False` usage was found.

4. Rich rendering paths that display user or model content already use safe rendering patterns.
   - Prompt diffs and warning text use escaping.
   - Error output uses `Text`, not Rich markup interpolation.

5. `evalflow init` still writes env var names, not key values.
   - `.gitignore` generation still includes `.env`, `.evalflow/`, and the required related entries.

## What Was Fixed

### Path traversal protection

Added project-relative safe path resolution:

- [`packages/cli/evalflow/commands/_common.py`](../packages/cli/evalflow/commands/_common.py)
  - `resolve_project_path(...)`

Applied it to:

- [`packages/cli/evalflow/commands/eval.py`](../packages/cli/evalflow/commands/eval.py)
- [`packages/cli/evalflow/commands/dataset.py`](../packages/cli/evalflow/commands/dataset.py)

### File extension enforcement

Added explicit extension checks in:

- [`packages/cli/evalflow/models/config.py`](../packages/cli/evalflow/models/config.py)
- [`packages/cli/evalflow/models/dataset.py`](../packages/cli/evalflow/models/dataset.py)

### README security/disclosure improvements

Updated:

- [`README.md`](../README.md)

Added:

- explicit environment-variable key handling note
- statement that `evalflow.yaml` stores env var names, not secrets
- link to the full security model
- responsible disclosure contact section

### Test secret normalization

Replaced generic placeholder secret values with explicit fake values in:

- [`packages/cli/tests/test_providers.py`](../packages/cli/tests/test_providers.py)
- [`packages/cli/tests/test_eval_methods.py`](../packages/cli/tests/test_eval_methods.py)

## Remaining Known Limitations

1. Ollama uses `http://localhost:11434`.
   - This is the local daemon transport used by Ollama.
   - It is an intentional exception to the general HTTPS rule because the connection is local-only.
   - This remains the only runtime `http://` provider endpoint.

2. `pip audit` is not yet enforced in CI.
   - The security spec recommends it.
   - This audit did not add a CI `pip audit` step.

3. PII detection warnings for dataset inputs are not implemented yet.
   - The security spec describes this as a best-effort future warning.

## Verification

The following behaviors are now covered by tests:

- dataset path traversal rejection
- `eval --dataset` path traversal rejection
- config extension validation
- dataset extension validation

Related tests live in:

- [`packages/cli/tests/test_commands.py`](../packages/cli/tests/test_commands.py)
- [`packages/cli/tests/test_models.py`](../packages/cli/tests/test_models.py)

## Summary

The audit found and fixed real path-handling and packaging-hygiene issues, confirmed safe YAML and SQL usage in runtime code, and documented the one intentional HTTP exception for Ollama localhost traffic.

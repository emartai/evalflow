# contributing.md — evalflow Contribution Guide

## Development setup

```bash
# Clone
git clone https://github.com/evalflow/evalflow
cd evalflow

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies
uv sync --all-extras

# Verify setup
evalflow --version
evalflow doctor
```

## Running tests

```bash
# All tests
pytest packages/cli/tests/ -v

# With coverage
pytest packages/cli/tests/ --cov=evalflow --cov-report=term-missing

# Fast (unit tests only)
pytest packages/cli/tests/unit/ -v

# Single file
pytest packages/cli/tests/test_eval_methods.py -v
```

## Commit format

```
type(scope): short description

feat(eval): add --concurrency flag to eval command
fix(provider): retry on 503 in addition to 429
docs(readme): update CI example for GitLab
test(storage): add test for baseline retrieval
chore(deps): bump httpx to 0.28.0
```

Types: feat, fix, docs, test, chore, refactor, perf

## PR checklist

- [ ] Tests added/updated for all changed behavior
- [ ] `pytest` passes with no failures
- [ ] Coverage ≥ 82% (run `pytest --cov=evalflow --cov-fail-under=82`)
- [ ] No API keys or secrets in code or tests
- [ ] All YAML loading uses `yaml.safe_load()`
- [ ] Error messages follow design.md format (no stack traces)
- [ ] New CLI flags documented in docs/cli-reference.mdx
- [ ] CHANGELOG.md updated

## Adding a new provider

1. Create `packages/cli/evalflow/engine/providers/<name>.py`
2. Implement `BaseProvider` (see `openai.py` for pattern)
3. Register in `providers/__init__.py` PROVIDER_REGISTRY
4. Add to `PROVIDER_DEFAULTS` in `commands/init.py`
5. Add to `check_api_keys()` in `commands/doctor.py`
6. Create `docs/providers/<name>.mdx`
7. Add mock tests in `tests/test_providers.py`

## Adding a new eval method

1. Create `packages/cli/evalflow/engine/methods/<name>.py`
2. Implement `evaluate()` returning float in [0, 1]
3. Add to `EvalMethod` enum in `models/dataset.py`
4. Wire into `evaluator.py` `_run_eval_methods()`
5. Add to eval_config.methods in dataset format docs
6. Add 100% test coverage in `tests/test_eval_methods.py`

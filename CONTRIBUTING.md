# Contributing

## Development setup

Use `uv` for the primary local workflow:

```bash
uv sync
```

If you prefer the checked-in local environment:

```bash
.\.venv\Scripts\Activate.ps1
```

## Running tests

From the repository root:

```bash
pytest --basetemp=.pytest-tmp packages/cli/tests -q
```

For coverage:

```bash
cd packages/cli
pytest --basetemp=..\..\.pytest-tmp\cov --cov=evalflow --cov-report=term-missing tests
```

## Smoke test and performance checks

Rebuild the wheel before timing a release candidate:

```bash
.\.venv\Scripts\python -m build packages/cli --no-isolation
```

Reusable local smoke run without re-installing dependencies:

```bash
$env:EVALFLOW_SMOKE_SKIP_INSTALL = "1"
$env:PYTHON_BIN = "C:\Users\DELL\Projects\evalflow\.venv\Scripts\python.exe"
.\.venv\Scripts\python scripts\smoke_test.py
```

Current Windows PowerShell baseline on Python 3.11:

- `import evalflow.main`: about `186 ms`
- `evalflow --help`: about `508 ms`
- `evalflow doctor` in a freshly initialized project: about `1.66 s`
- `python scripts/smoke_test.py` with `EVALFLOW_SMOKE_SKIP_INSTALL=1`: about `8.97 s`

Measure them with:

```bash
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python -c "import time; start=time.perf_counter(); import evalflow.main; print(round((time.perf_counter()-start)*1000, 1))"
```

```bash
$env:PYTHONUTF8 = "1"
Measure-Command { .\.venv\Scripts\python -m evalflow.main --help | Out-Null }
```

```bash
$tmp = Join-Path (Resolve-Path .pytest-tmp).Path "doctor-benchmark"
if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null
Push-Location $tmp
..\..\..\.venv\Scripts\evalflow.exe init --non-interactive | Out-Null
Measure-Command { $env:PYTHONUTF8 = "1"; ..\..\..\.venv\Scripts\evalflow.exe doctor | Out-Null }
Pop-Location
```

Notes:

- `evalflow doctor` should stay under three seconds without `--check-providers`.
- `evalflow --help` is optimized for low import cost; regressions should be investigated if it drifts materially above the current baseline.

## Commit message format

Use concise imperative commit messages. Preferred format:

```text
type(scope): summary
```

Examples:

```text
feat(cli): add compare command error hardening
fix(provider): surface auth failures as provider errors
docs(readme): update GitHub Pages documentation links
```

## Pull request checklist

- Confirm the affected prompt requirements are fully implemented
- Run the relevant test suite locally
- Include or update tests for new behavior
- Keep user-facing error messages specific and actionable
- Update docs, metadata, or examples when behavior changes
- If public URLs change, update `packages/cli/evalflow/urls.py`, `packages/cli/pyproject.toml`, and `README.md` together

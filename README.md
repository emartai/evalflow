```text
> evalflow
```

pytest for LLMs

[![PyPI](https://img.shields.io/pypi/v/evalflow)](https://pypi.org/project/evalflow/)
[![Python](https://img.shields.io/pypi/pyversions/evalflow)](https://pypi.org/project/evalflow/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/emartai/evalflow/actions/workflows/ci.yml/badge.svg)](https://github.com/emartai/evalflow/actions/workflows/ci.yml)

```text
You changed one prompt.
Summarization improved.
Classification silently broke.
Nobody noticed for 4 days.

evalflow catches this in CI before it ships.
```

## Install

```bash
pip install evalflow
```

## Quick Start

```bash
evalflow init
evalflow eval
```

What you get on day one:

- local prompt and dataset files
- SQLite-backed run history in `.evalflow/`
- CI-friendly exit codes
- offline cache support for repeatable checks

## Terminal Screenshot

```text
> evalflow eval

Running 5 test cases against gpt-4o-mini...

✓ summarize_short_article    0.91
✓ classify_sentiment         1.00
✓ extract_entities           0.87
✗ answer_with_context        0.61
✓ rewrite_formal             0.93

Quality Gate: PASS
Failures: 1
Run ID: 20240315-a3f9c2d81b4e
```

## Why evalflow

Traditional unit tests do not tell you when a prompt tweak quietly degrades a task.
evalflow gives you a small local quality gate for prompt, model, and dataset changes.

Use it when you need to:

- catch regressions before merge
- compare runs locally
- keep prompt versions in YAML
- run the same gate in CI and on a laptop

## GitHub Actions Workflow

```yaml
# .github/workflows/evalflow.yml
name: LLM Quality Gate

on:
  pull_request:
    paths:
      - "prompts/**"
      - "evals/**"
      - "**.py"

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install evalflow
      - run: evalflow eval
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Features

- pytest-style exit codes: `0=pass`, `1=fail`, `2=error`
- exact match, embedding, consistency, and LLM judge methods
- baseline snapshots catch regressions, not just low scores
- prompt registry keeps prompts versioned in YAML
- works with OpenAI, Anthropic, Groq, Gemini, and Ollama
- local SQLite storage, no account needed
- offline cache for repeated and CI-safe checks

## Command Surface

```bash
evalflow init
evalflow eval
evalflow doctor
evalflow runs
evalflow compare RUN_A RUN_B
evalflow prompt list
```

## Documentation

- Docs hub: [emartai.mintlify.app](https://emartai.mintlify.app/)
- Quickstart source: [docs/quickstart.mdx](https://github.com/emartai/evalflow/blob/main/docs/quickstart.mdx)
- CLI reference source: [docs/cli-reference.mdx](https://github.com/emartai/evalflow/blob/main/docs/cli-reference.mdx)
- CI guide source: [docs/ci-github-actions.mdx](https://github.com/emartai/evalflow/blob/main/docs/ci-github-actions.mdx)
- Provider docs: [docs/providers](https://github.com/emartai/evalflow/tree/main/docs/providers)

## Security

- evalflow reads API keys from environment variables, never config files
- `evalflow.yaml` stores env var names, not secret values
- keep `.env` and `.evalflow/` out of git
- see [docs/dev-doc/security.md](docs/dev-doc/security.md) for the full security model

## Reporting Security Issues

Please do not open public GitHub issues for security vulnerabilities.
Open a private [GitHub Security Advisory](https://github.com/emartai/evalflow/security/advisories/new).

## Examples

- [examples/openai-basic](examples/openai-basic)
- [examples/groq-ci](examples/groq-ci)
- [examples/langchain-app](examples/langchain-app)

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, tests, smoke checks, and performance baselines.

## License

MIT

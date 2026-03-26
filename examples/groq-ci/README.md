# groq-ci

You changed one prompt.
Summarization improved.
Classification silently broke.
Nobody noticed for 4 days.

evalflow catches this in CI before it ships.

Groq free tier - zero cost for CI.

## Install

```bash
pip install evalflow
cd examples/groq-ci
cp .env.example .env
```

## Run

```bash
evalflow doctor
evalflow eval --provider groq
```

## GitHub Actions

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
      - run: evalflow eval --provider groq
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
```

## Result

```text
> evalflow eval --provider groq

Running 3 test cases against llama-3.1-8b-instant...

✓ summarize-pr-description    0.91
✓ classify-ci-failure         1.00
✓ answer-readme-question      0.86

Quality Gate: PASS
Failures: 0
Run ID: 20240315-c7e8b1d23f9a
Duration: 3.1s
```

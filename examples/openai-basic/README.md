# openai-basic

You changed one prompt.
Summarization improved.
Classification silently broke.
Nobody noticed for 4 days.

evalflow catches this in CI before it ships.

## Install

```bash
pip install evalflow
cd examples/openai-basic
cp .env.example .env
```

## Run

```bash
evalflow doctor
evalflow eval
```

## Result

```text
> evalflow eval

Running 3 test cases against gpt-4o-mini...

✓ summarize-release-notes      0.92
✓ classify-support-priority    1.00
✓ answer-billing-question      0.88

Quality Gate: PASS
Failures: 0
Run ID: 20240315-a3f9c2d81b4e
Duration: 3.8s
```

## Files

- `evalflow.yaml`: minimal OpenAI config
- `evals/dataset.json`: summarization, classification, and QA checks
- `prompts/assistant.yaml`: example prompt registry entry
- `.env.example`: environment variables template

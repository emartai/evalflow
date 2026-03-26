# langchain-app

You changed one prompt.
Summarization improved.
Classification silently broke.
Nobody noticed for 4 days.

evalflow catches this in CI before it ships.

## Install

```bash
pip install evalflow langchain-openai langchain-core
cd examples/langchain-app
cp .env.example .env
```

## Run

```bash
python app.py
evalflow eval
```

## Result

```text
> python app.py
Reply: The assistant answers using the production prompt body.

> evalflow eval

Running 3 test cases against gpt-4o-mini...

✓ summarize-meeting-notes     0.90
✓ classify-user-intent        1.00
✓ answer-faq-context          0.87

Quality Gate: PASS
Failures: 0
Run ID: 20240315-b2d9f4e67c1b
Duration: 4.0s
```

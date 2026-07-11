# anthropic-basic

Run a minimal three-case evaluation against Anthropic Claude. The example checks
summarization, classification, and context-grounded question answering, then
applies a quality gate to the results.

## Clone and install

Python 3.10 or newer is required.

```bash
git clone https://github.com/emartai/evalflow.git
cd evalflow
python -m venv .venv
source .venv/bin/activate
python -m pip install "click>=8.1" -e "packages/cli[embeddings]"
```

The `embeddings` extra is required by the two similarity-based test cases. On
first use, evalflow downloads the local embedding model (about 80 MB).
`click` is included explicitly because the current CLI imports it directly.

## Configure Anthropic

```bash
cd examples/anthropic-basic
cp .env.example .env
```

Open `.env` and replace the placeholder with a real Anthropic API key:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
```

The `.env` file is loaded automatically and should never be committed.

## Run

```bash
evalflow doctor
evalflow eval
```

The first run should finish with all three cases evaluated and a passing quality
gate:

```text
Running 3 test cases against claude-3-5-haiku-20241022...

✓ summarize-release-notes
✓ classify-support-priority
✓ answer-billing-question

Quality Gate: PASS
Failures: 0
Run ID: <generated-run-id>
```

Exact similarity scores, duration, and the run ID vary by run. If the quality
gate does not pass, confirm the API key, rerun `evalflow doctor`, and inspect the
per-case output before changing thresholds.

## Files

- `evalflow.yaml`: minimal Anthropic configuration
- `evals/dataset.json`: summarization, classification, and QA checks
- `prompts/assistant.yaml`: example prompt registry entry
- `.env.example`: Anthropic environment-variable template

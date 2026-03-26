# context.md — evalflow Master Context

## What is evalflow?

evalflow is a developer-first CLI tool for catching LLM prompt regressions before they reach production. It is "pytest for LLMs" — automated quality gates that plug into CI/CD pipelines.

**Tagline:** pytest for LLMs. Catch prompt regressions before they reach production.

**One-liner pain story:**
```
You changed one prompt.
Summarization improved.
Classification silently broke.
Nobody noticed for 4 days.

evalflow catches this in CI before it ships.
```

---

## MVP Scope (what gets built)

The MVP is CLI-only. No cloud, no dashboard, no accounts, no billing. Just:

1. A Python CLI tool published to PyPI
2. An eval engine (4 layered methods)
3. A file-based prompt registry
4. Local SQLite run history
5. CI/CD integration (GitHub Actions)
6. Documentation site (Mintlify)

**North star metric:** Developer installs evalflow → runs first eval → adds to CI in under 10 minutes.

---

## Repository Structure

```
evalflow/
├── packages/
│   ├── cli/                    # Open source CLI (Python)
│   │   ├── evalflow/
│   │   │   ├── __init__.py
│   │   │   ├── main.py         # Typer app entrypoint
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── eval.py     # evalflow eval
│   │   │   │   ├── init.py     # evalflow init
│   │   │   │   ├── doctor.py   # evalflow doctor
│   │   │   │   ├── runs.py     # evalflow runs / compare
│   │   │   │   └── prompt.py   # evalflow prompt *
│   │   │   ├── engine/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py     # BaseProvider interface
│   │   │   │   ├── evaluator.py # Core eval orchestrator
│   │   │   │   ├── methods/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── exact_match.py
│   │   │   │   │   ├── embedding.py
│   │   │   │   │   ├── consistency.py
│   │   │   │   │   └── judge.py
│   │   │   │   └── providers/
│   │   │   │       ├── __init__.py
│   │   │   │       ├── openai.py
│   │   │   │       ├── anthropic.py
│   │   │   │       ├── groq.py
│   │   │   │       ├── gemini.py
│   │   │   │       └── ollama.py
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── config.py    # EvalflowConfig Pydantic model
│   │   │   │   ├── dataset.py   # TestCase, Dataset Pydantic models
│   │   │   │   ├── run.py       # EvalRun, RunResult Pydantic models
│   │   │   │   └── prompt.py    # PromptVersion Pydantic model
│   │   │   ├── storage/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── db.py        # SQLite async interface
│   │   │   │   └── cache.py     # Response cache (offline mode)
│   │   │   ├── registry/
│   │   │   │   ├── __init__.py
│   │   │   │   └── prompt_registry.py # YAML prompt registry
│   │   │   └── output/
│   │   │       ├── __init__.py
│   │   │       └── rich_output.py # All Rich terminal rendering
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── core/                   # Shared eval logic (CLI + future API)
│       ├── evalflow_core/
│       │   ├── __init__.py
│       │   └── types.py         # Shared types
│       └── pyproject.toml
├── examples/
│   ├── openai-basic/           # Minimal OpenAI example
│   ├── groq-ci/                # GitHub Actions + Groq free tier
│   └── langchain-app/          # evalflow inside LangChain
├── docs/                       # Mintlify documentation
│   ├── mint.json
│   ├── quickstart.mdx
│   ├── concepts.mdx
│   ├── cli-reference.mdx
│   └── ci-github-actions.mdx
├── .github/
│   └── workflows/
│       ├── ci.yml              # evalflow's own CI
│       └── publish.yml         # PyPI publish on tag
├── pyproject.toml              # Workspace root
└── README.md
```

---

## Tech Stack (MVP Only)

| Layer | Technology | Reason |
|---|---|---|
| CLI framework | Typer | Python type hints → clean commands, auto-help |
| Terminal output | Rich | Progress bars, tables, colors, error panels |
| Data models | Pydantic v2 | Validation, serialization, clean errors |
| Config files | PyYAML | YAML for evalflow.yaml and prompt files |
| Local storage | SQLite + aiosqlite | Zero setup, offline, single file |
| HTTP calls | httpx | Async, used for all provider calls |
| Embedding similarity | sentence-transformers | Local model, no API cost |
| Math | numpy | Consistency scoring, cosine similarity |
| Packaging | uv + pyproject.toml | Modern, fast Python packaging |
| Env vars | python-dotenv | .env file support |
| Response cache | shelve (stdlib) | Offline mode, zero dependencies |

**Python version:** 3.10+ minimum, 3.11+ recommended.

---

## CLI Commands (complete spec)

### `evalflow init`
Interactive setup wizard.
- Asks: provider choice, model, API key env var name
- Creates: `evalflow.yaml`, `prompts/` directory, `evals/dataset.json` (with 1 example test case pre-filled)
- Output: clear success message with next steps

### `evalflow eval`
Core command. Runs dataset against provider.
```
evalflow eval
evalflow eval --provider openai
evalflow eval --provider groq --model llama-3.1-8b-instant
evalflow eval --dataset evals/custom.json
evalflow eval --tag critical
evalflow eval --offline
```
- First run: saves baseline snapshot to SQLite
- Subsequent runs: diffs against baseline, shows delta
- Exit codes: 0=pass, 1=quality failure (blocks CI), 2=config error
- Run ID format: `YYYYMMDD-<12-char-sha256-hash>`

### `evalflow doctor`
System check. Outputs ✓/✗ checklist:
- evalflow version
- evalflow.yaml found
- dataset.json found + test case count
- API keys set (per configured provider)
- sentence-transformers model downloaded
- SQLite database initialized
- Git repository detected
- Optional providers (shows as optional)

### `evalflow runs`
List recent runs from local history.
```
evalflow runs
evalflow runs --limit 20
evalflow runs --since 7d
evalflow runs --failed-only
```

### `evalflow compare <run-a> <run-b>`
Side-by-side diff of two run IDs.
Shows: which test cases changed, which metrics moved, delta values.

### `evalflow prompt create <name>`
Scaffold a new prompt YAML file in `prompts/`.

### `evalflow prompt list`
Show all prompts + active version + last eval score.

### `evalflow prompt diff <name> <v1> <v2>`
Line-by-line diff of two prompt versions using Rich.

### `evalflow prompt promote <name> --to <staging|production>`
Update status field in YAML file.

---

## Dataset Format (public API — never break BC)

```json
{
  "version": "1.0",
  "test_cases": [
    {
      "id": "unique-kebab-case-id",
      "description": "Human readable explanation",
      "task_type": "summarization",
      "input": "the prompt or user message",
      "expected_output": "what good looks like",
      "context": "source material for grounding checks",
      "tags": ["critical", "regression"],
      "eval_config": {
        "methods": ["embedding_similarity", "exact_match"],
        "judge": false,
        "weight": 1.0
      }
    }
  ]
}
```

**task_type values:** `summarization`, `classification`, `extraction`, `qa`, `generation`, `rewrite`

**eval_config.methods values:** `exact_match`, `embedding_similarity`, `consistency`, `llm_judge`

---

## Prompt Registry Format

```yaml
# prompts/summarization.yaml
id: summarization
version: 2
status: production        # draft | staging | production
body: |
  You are a summarization assistant. Summarize the following
  text in exactly one sentence, capturing the main point only.
  Do not add opinions or context not present in the original.
author: emmanuel
created_at: "2024-03-01"
tags: ["core", "v2"]
```

Python usage:
```python
from evalflow import get_prompt
prompt = get_prompt("summarization")  # returns body of production version
```

---

## Eval Engine: Four Layers

### Layer 1 — Exact Match
- When: `exact_match` in methods
- How: string normalization + comparison
- Cost: $0, instant
- Best for: classification, structured output, yes/no

### Layer 2 — Embedding Similarity
- When: `embedding_similarity` in methods
- How: sentence-transformers `all-MiniLM-L6-v2`, cosine similarity
- Cost: $0 (local), ~100ms per comparison
- Best for: semantic relevance, paraphrase detection

### Layer 3 — Consistency Scoring
- When: `consistency` in methods
- How: run same input N times (default 3), compute variance with numpy
- Cost: N × provider API calls
- Best for: flaky model behavior detection

### Layer 4 — LLM-as-Judge
- When: `llm_judge` in methods AND `judge: true` in eval_config
- How: httpx call to Groq (default) with structured judge prompt
- Cost: 1 API call per test case (Groq free tier = $0)
- Best for: hallucination detection, grounded generation
- Default judge model: `llama-3.1-8b-instant` on Groq

---

## Providers

| Provider | How connected | Notes |
|---|---|---|
| OpenAI | openai SDK | Default provider |
| Anthropic | anthropic SDK | Full support |
| Groq | httpx (OpenAI-compatible) | Free tier, default judge |
| Gemini | httpx (OpenAI-compatible) | |
| Ollama | httpx (localhost:11434) | No API key needed |

All providers implement `BaseProvider`:
```python
class BaseProvider:
    async def complete(self, prompt: str, config: ProviderConfig) -> Response: ...
    async def health_check(self) -> bool: ...
```

---

## Configuration File Format

```yaml
# evalflow.yaml
version: "1.0"
project: my-ai-app

providers:
  openai:
    api_key_env: "OPENAI_API_KEY"
    default_model: "gpt-4o-mini"
  groq:
    api_key_env: "GROQ_API_KEY"
    default_model: "llama-3.1-8b-instant"

eval:
  dataset: "evals/dataset.json"
  baseline_file: ".evalflow/baseline.json"
  default_provider: "openai"
  consistency_runs: 3

thresholds:
  task_success: 0.80
  relevance: 0.75
  hallucination_max: 0.10
  consistency_min: 0.85

judge:
  provider: "groq"
  model: "llama-3.1-8b-instant"

prompts:
  directory: "prompts/"
```

---

## Error Message Standards

Every user-facing error must follow this format:
```
✗ <What went wrong — one line>

<Exact fix — 2-3 lines>
<Link if relevant>
```

Example:
```
✗ Missing API key for OpenAI

  Set OPENAI_API_KEY in your environment:
  export OPENAI_API_KEY="sk-..."

  Or add to evalflow.yaml:
  providers:
    openai:
      api_key_env: "OPENAI_API_KEY"

  Get a key at: https://platform.openai.com/api-keys
```

**Rules:**
- No Python tracebacks visible to users
- No "An error occurred" without specifics
- Always include the exact fix
- Always include a link when there's a relevant URL

---

## CI Integration

### GitHub Actions (copy-pasteable)
```yaml
# .github/workflows/evalflow.yml
name: LLM Quality Gate

on:
  pull_request:
    paths:
      - 'prompts/**'
      - 'evals/**'
      - '**.py'

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install evalflow
      - run: evalflow eval
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Exit code 1 from `evalflow eval` fails the build automatically.

---

## SQLite Schema

```sql
-- Runs table
CREATE TABLE runs (
    id TEXT PRIMARY KEY,           -- YYYYMMDD-<12-char-hash>
    created_at TIMESTAMP,
    provider TEXT,
    model TEXT,
    dataset_hash TEXT,
    prompt_version_hash TEXT,
    status TEXT,                   -- pass | fail | error
    overall_score REAL,
    duration_ms INTEGER
);

-- Results table (one row per test case per run)
CREATE TABLE results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES runs(id),
    test_case_id TEXT,
    status TEXT,                   -- pass | fail
    score REAL,
    exact_match_score REAL,
    embedding_score REAL,
    consistency_score REAL,
    judge_score REAL,
    raw_output TEXT,
    error TEXT
);

-- Baselines table
CREATE TABLE baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP,
    run_id TEXT REFERENCES runs(id),
    dataset_hash TEXT,
    scores_json TEXT              -- JSON blob of all scores
);

-- Prompt versions table
CREATE TABLE prompt_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id TEXT,
    version INTEGER,
    status TEXT,
    body TEXT,
    author TEXT,
    created_at TIMESTAMP
);
```

---

## Launch Checklist

### Before writing code
- [ ] `evalflow` GitHub org claimed
- [ ] PyPI package name `evalflow` reserved (pip install evalflow returns "not found")
- [ ] `evalflow.dev` or `evalflow.sh` domain registered
- [ ] `@evalflow` claimed on X/Twitter
- [ ] Discord server created (link goes in README)

### Code complete
- [ ] All 8 CLI commands working
- [ ] All 5 providers tested
- [ ] All 4 eval methods tested
- [ ] GitHub Actions workflow tested end-to-end
- [ ] `evalflow doctor` returns correct output
- [ ] `evalflow init` works in empty directory
- [ ] 3 examples all run without errors
- [ ] `pip install evalflow` and first eval under 10 minutes

### Documentation complete
- [ ] README: pain story opener, install command, terminal screenshot, CI badge
- [ ] Getting started guide live
- [ ] CLI reference complete
- [ ] 3 CI/CD guides (GitHub Actions, GitLab CI, CircleCI)
- [ ] All 3 examples tested and documented

### Launch actions
- [ ] Terminal demo video (Asciinema → GIF)
- [ ] Show HN post written
- [ ] dev.to post written
- [ ] X/Twitter launch thread written
- [ ] Awesome-llm-tools submission prepared

---

## What is NOT in MVP

- No web dashboard
- No user accounts or auth
- No Stripe or billing
- No A/B testing
- No rollback command
- No webhooks or notifications
- No production traffic SDK
- No REST API
- No team features
- No Docker
- No cloud storage

**Revenue at MVP: $0. This is intentional.**

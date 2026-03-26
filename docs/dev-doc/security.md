# security.md — evalflow Security Specification

## Security Philosophy

evalflow handles API keys, LLM provider credentials, and potentially sensitive prompt/output data. Security must be correct from day one — even at MVP with zero users.

**Core principle:** Never store a secret. Always read from environment.

---

## 1. API Key Handling

### Rules — non-negotiable

1. **Never store API keys in code, config files, or SQLite.** Keys are always read from environment variables at runtime.
2. **Never log API keys.** All logging, error output, and debug traces must redact credential values.
3. **Never echo API keys back to the user.** Even partial display (`sk-...xxxx`) is forbidden in normal output.
4. **`evalflow.yaml` stores env var names, not key values.**

### Correct pattern
```yaml
# evalflow.yaml — CORRECT
providers:
  openai:
    api_key_env: "OPENAI_API_KEY"   # name of env var, not the key itself
```

```python
# Loading at runtime — CORRECT
import os
api_key = os.environ.get(config.providers.openai.api_key_env)
if not api_key:
    raise MissingAPIKeyError(provider="openai", env_var="OPENAI_API_KEY")
```

### Wrong pattern (never do this)
```yaml
# evalflow.yaml — WRONG
providers:
  openai:
    api_key: "sk-abc123..."   # NEVER store key value in config
```

### `evalflow init` key handling
During `evalflow init`, if the user provides an API key interactively:
- **Do not write it to `evalflow.yaml`**
- Write only the env var name to config
- Print this message:
  ```
  → Add to your shell profile or .env file:
    export OPENAI_API_KEY="your-key-here"
  
  evalflow.yaml stores only the variable name, not the key.
  ```

---

## 2. `.env` File Security

### `.gitignore` requirements
`evalflow init` must add these entries to `.gitignore` if not already present:
```
.env
.env.local
.env.*
!.env.example
.evalflow/
*.evalflow.db
```

### `.env.example` generation
`evalflow init` must create an `.env.example` (if not present) with placeholder values:
```
# evalflow environment variables
# Copy to .env and fill in real values. Never commit .env to git.

OPENAI_API_KEY=sk-your-key-here
# ANTHROPIC_API_KEY=your-key-here
# GROQ_API_KEY=your-key-here
```

---

## 3. Sensitive Data in Eval Runs

### What gets stored in SQLite

SQLite stores eval run metadata and results. The following rules apply:

| Data | Stored | Notes |
|---|---|---|
| Run ID, timestamps | Yes | Safe |
| Provider name, model | Yes | Safe |
| Dataset hash | Yes | Hash only, not content |
| Prompt version hash | Yes | Hash only |
| Overall score, per-test scores | Yes | Safe |
| Raw LLM output | Yes, truncated | Max 2000 chars |
| Input prompts | No | Not stored by default |
| API keys | Never | Forbidden |
| Provider responses raw | No | Score only |

### Opt-out of output storage
Users can disable raw output storage in `evalflow.yaml`:
```yaml
storage:
  store_raw_outputs: false   # default: true
  max_output_chars: 2000     # default: 2000
```

### Future: PII warning
If a test case `input` field contains patterns that look like PII (email addresses, phone numbers, credit card numbers — basic regex), warn the user:
```
! Warning: test case "user-lookup" input may contain PII.
  Consider using synthetic data in eval datasets.
```
This is a warning only, not a block. Implement as a best-effort check.

---

## 4. Dependency Security

### Pinning strategy
- **Do not pin exact versions** in `pyproject.toml` (prevents users from getting security updates)
- **Do use minimum versions** with `>=` constraints
- **Do use upper bounds** only when a breaking change is known
- Run `pip audit` as part of CI

### Supply chain
- Prefer packages with high download counts and known maintainers
- Avoid packages with < 100k weekly downloads unless unavoidable
- All dependencies used in evalflow MVP:

| Package | Purpose | Risk level |
|---|---|---|
| typer | CLI framework | Low |
| rich | Terminal output | Low |
| pydantic | Data validation | Low |
| pyyaml | Config parsing | Medium — use `yaml.safe_load()` always |
| aiosqlite | Async SQLite | Low |
| httpx | HTTP client | Low |
| sentence-transformers | Embeddings | Medium (large, many deps) |
| numpy | Math | Low |
| python-dotenv | .env loading | Low |
| openai | OpenAI SDK | Low |
| anthropic | Anthropic SDK | Low |

### YAML safety
**Always use `yaml.safe_load()`.** Never use `yaml.load()` without Loader — it allows arbitrary code execution.

```python
# CORRECT
import yaml
config = yaml.safe_load(config_file.read_text())

# WRONG — arbitrary code execution risk
config = yaml.load(config_file.read_text())
```

---

## 5. File Path Security

### Path traversal prevention
Any user-supplied file paths (dataset path, prompt directory, config path) must be validated:

```python
from pathlib import Path

def safe_resolve(user_path: str, base_dir: Path) -> Path:
    """Resolve a user-supplied path, preventing path traversal."""
    resolved = (base_dir / user_path).resolve()
    if not str(resolved).startswith(str(base_dir.resolve())):
        raise ValueError(f"Path traversal detected: {user_path}")
    return resolved
```

### Allowed file extensions
- Config: `.yaml`, `.yml` only
- Dataset: `.json` only
- Prompt files: `.yaml`, `.yml` only

Reject any file path with extensions outside these lists.

---

## 6. HTTP Security

### Provider API calls
- Always use HTTPS. Never HTTP for provider calls.
- Set connection timeout: 30 seconds
- Set read timeout: 60 seconds (LLM responses can be slow)
- Never disable SSL verification (`verify=False` is forbidden)

```python
# CORRECT
async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=60.0)) as client:
    response = await client.post(url, headers=headers, json=body)

# WRONG
async with httpx.AsyncClient(verify=False) as client:  # Never
    ...
```

### Retry policy
Implement exponential backoff for transient errors (429, 502, 503):
- Max 3 retries
- Base delay: 1 second
- Max delay: 10 seconds
- Do not retry on 4xx errors (except 429)

---

## 7. Error Message Security

Error messages shown to users must not expose:
- Internal file paths (show relative paths only)
- Full stack traces (show user-friendly message, log full trace to debug)
- API keys or partial keys
- Raw HTTP response bodies from providers
- Internal database queries

```python
# CORRECT error display
console.print("[red]✗[/red] Failed to connect to OpenAI")
console.print("  Check your OPENAI_API_KEY and network connection.")

# WRONG
console.print(f"HTTPStatusError: {response.text}")  # may contain sensitive data
```

Developer debug mode (never on by default):
```
evalflow eval --debug
```
With `--debug`, full stack traces and verbose HTTP logs are shown. This flag should be clearly documented as "for development only."

---

## 8. CI/CD Security Guidance

The documentation and example workflows must include these security notes:

### In GitHub Actions docs
```yaml
# Store API keys as GitHub Secrets — never hardcode in workflow files
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

### In the README
Include a "Security" section:
```markdown
## Security

- evalflow reads API keys from environment variables, never config files
- The `evalflow.yaml` config is safe to commit — it contains no secrets
- Add `.env` to your `.gitignore` (evalflow init does this automatically)
- See [security.md](docs/security.md) for the full security model
```

---

## 9. SQLite Security

- SQLite file lives at `.evalflow/runs.db` inside the project directory
- File permissions: `600` (user read/write only) — set on creation
- The `.evalflow/` directory should be in `.gitignore` (added by `evalflow init`)
- No SQL injection risk: use parameterized queries always

```python
# CORRECT — parameterized query
await db.execute(
    "INSERT INTO runs (id, provider, model) VALUES (?, ?, ?)",
    (run_id, provider, model)
)

# WRONG — string interpolation
await db.execute(f"INSERT INTO runs VALUES ('{run_id}', '{provider}')")
```

---

## 10. Output Data Sanitization

LLM outputs can contain arbitrary text. Before displaying in the terminal:
- Truncate at 2000 characters for display
- Strip ANSI escape codes from LLM output before rendering
- Do not render LLM output as Rich markup (use `rich.markup.escape()`)

```python
from rich.markup import escape

# CORRECT — escape LLM output before rendering
console.print(escape(llm_output[:2000]))

# WRONG — LLM could inject Rich markup
console.print(llm_output)
```

---

## 11. Responsible Disclosure

Include in README and GitHub repo:

```markdown
## Reporting Security Issues

Please do not open public GitHub issues for security vulnerabilities.
Email: security@evalflow.dev

We aim to respond within 48 hours and will credit researchers in our changelog.
```

---

## Security Checklist (for each PR)

- [ ] No secrets or API keys in code, config, or tests
- [ ] All YAML loaded with `yaml.safe_load()`
- [ ] All file paths validated against path traversal
- [ ] All SQL uses parameterized queries
- [ ] All user-supplied strings escaped before Rich rendering
- [ ] All HTTP calls use HTTPS with SSL verification enabled
- [ ] Error messages don't expose internal details
- [ ] New dependencies checked with `pip audit`
- [ ] `.gitignore` entries correct

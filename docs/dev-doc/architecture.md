# architecture.md — evalflow MVP Architecture

## Overview

evalflow MVP is a pure Python CLI tool. There is no backend, no frontend, no cloud. The entire product is the CLI + eval engine + local SQLite storage.

The codebase is structured as a uv workspace monorepo with two packages:
- `evalflow-core`: shared types (for future API use)
- `evalflow`: the CLI tool published to PyPI

---

## Module Dependency Graph

```
main.py (Typer app)
    ↓
commands/
├── init.py
├── eval.py          → engine/evaluator.py → engine/methods/*
│                    → engine/providers/*
│                    → storage/db.py
│                    → storage/cache.py
├── doctor.py        → storage/db.py
├── runs.py          → storage/db.py
└── prompt.py        → registry/prompt_registry.py

All commands → output/rich_output.py (terminal rendering)
All commands → models/* (data structures)
All commands → exceptions.py (error types)
```

Key rule: **no circular imports**. Dependencies only flow downward in this list.

---

## Package: `evalflow` (CLI)

### `evalflow/main.py`
The Typer application entrypoint. Wires all commands together. The only file with the `app = typer.Typer(...)` declaration. Handles the global `--version` and `--debug` flags. Contains the top-level exception handler.

### `evalflow/__init__.py`
Exports the public Python API:
```python
from evalflow import get_prompt

__version__ = "0.1.0"

def get_prompt(name: str, status: str = "production") -> str:
    """Get a prompt body for use in application code."""
    ...
```

This is the only file that application developers import from.

---

### `evalflow/commands/`

Each file = one logical command group. Each file imports from `engine/`, `models/`, `storage/`, `registry/`, and `output/`. Never imports from another command file.

**`init.py`**
- `init_command()` — the `evalflow init` command
- Helper: `_add_gitignore_entries(path)` — adds security entries
- Helper: `_create_env_example(path)` — creates .env.example
- Helper: `_write_default_dataset(path)` — writes example dataset.json
- Helper: `_get_provider_defaults(provider)` — returns default model for provider

**`eval.py`**
- `eval_command()` — the `evalflow eval` command
- Helper: `_load_config_or_exit(debug)` — loads config with error handling
- Helper: `_validate_api_key_or_exit(config, provider)` — checks env var
- Helper: `_load_dataset_or_exit(path, debug)` — loads dataset with error handling

**`doctor.py`**
- `doctor_command()` — the `evalflow doctor` command
- Each check is a separate function returning `(bool, str)`: (passed, detail)
- Checks: `check_version()`, `check_python()`, `check_config()`, `check_dataset()`, `check_db()`, `check_git()`, `check_api_keys(config)`, `check_embeddings()`, `check_gitignore()`

**`runs.py`**
- `runs_command()` — `evalflow runs`
- `compare_command()` — `evalflow compare <a> <b>`
- Helper: `_parse_since(since_str)` — parses "7d", "30d" to timedelta

**`prompt.py`**
- `prompt_create()`, `prompt_list()`, `prompt_diff()`, `prompt_promote()`
- All delegate to `PromptRegistry` from `registry/`

---

### `evalflow/engine/`

The eval engine. Pure logic — no CLI, no output, no Rich.

**`base.py`**
```python
@dataclass
class ProviderConfig:
    api_key: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 1000
    timeout: float = 60.0

@dataclass  
class ProviderResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float

class BaseProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse: ...
    
    @abstractmethod
    async def health_check(self) -> bool: ...
    
    @classmethod
    @abstractmethod
    def provider_name(cls) -> str: ...
```

**`evaluator.py`**
```python
class EvalOrchestrator:
    """
    Coordinates a full eval run.
    Calls providers, runs eval methods, saves results.
    Does NOT do any terminal output — uses callbacks.
    """
    
    def __init__(
        self,
        config: EvalflowConfig,
        db: EvalflowDB,
        cache: ResponseCache,
        on_test_complete: Optional[Callable[[TestCaseResult], None]] = None
    )
    
    async def run_eval(self, dataset, provider_name, offline, tags) -> EvalRun
    async def _run_test_case(self, test_case, provider, provider_config, offline) -> TestCaseResult
    async def compare_to_baseline(self, run: EvalRun) -> Optional[BaselineComparison]
    def _compute_run_id(self, dataset, provider, model) -> str
    def _compute_overall_score(self, results: list[TestCaseResult]) -> float
```

**`providers/__init__.py`**
```python
PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}

def get_provider(name: str) -> type[BaseProvider]:
    if name not in PROVIDER_REGISTRY:
        raise ConfigError(
            f"Unknown provider: {name}",
            fix=f"Valid providers: {', '.join(PROVIDER_REGISTRY.keys())}"
        )
    return PROVIDER_REGISTRY[name]

def resolve_provider_config(provider_name: str, config: EvalflowConfig) -> ProviderConfig:
    """Extract ProviderConfig from EvalflowConfig for a given provider."""
```

**`providers/openai.py`** (template for all providers)
```python
class OpenAIProvider(BaseProvider):
    @classmethod
    def provider_name(cls) -> str:
        return "openai"
    
    async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
        # Uses openai AsyncClient
        # Never logs config.api_key
        # Implements retry with exponential backoff
        # Raises ProviderError on failure (not raw SDK errors)
    
    async def health_check(self) -> bool:
        # Lightweight check — models.list()
        # Returns False (not raises) on failure
```

**`methods/`**

Each method is a class with an `evaluate()` method. No side effects. Pure scoring functions.

```
exact_match.py    → ExactMatchEvaluator.evaluate(actual, expected) -> float
embedding.py      → EmbeddingEvaluator.evaluate(actual, expected) -> float  [lazy load]
consistency.py    → ConsistencyEvaluator.evaluate(prompt, provider, config, runs) -> float  [async]
judge.py          → LLMJudgeEvaluator.evaluate(input, expected, actual, context) -> JudgeResult  [async]
```

Method selection logic in `evaluator.py`:
```python
async def _run_eval_methods(self, test_case, actual_output, provider, config) -> dict[str, float]:
    scores = {}
    methods = test_case.eval_config.methods
    
    if EvalMethod.exact_match in methods:
        scores["exact_match"] = self.exact_match.evaluate(actual_output, test_case.expected_output)
    
    if EvalMethod.embedding_similarity in methods:
        scores["embedding"] = self.embedding.evaluate(actual_output, test_case.expected_output)
    
    if EvalMethod.consistency in methods:
        scores["consistency"] = await self.consistency.evaluate(...)
    
    if EvalMethod.llm_judge in methods and test_case.eval_config.judge:
        result = await self.judge.evaluate(...)
        scores["judge"] = result.score
    
    return scores
```

---

### `evalflow/models/`

All Pydantic v2 models. No logic — only structure, validation, and serialization.

```
config.py   → EvalflowConfig, ProviderConfig*, ProvidersConfig, EvalConfig, 
              ThresholdsConfig, JudgeConfig, PromptsConfig, StorageConfig

dataset.py  → TestCase, Dataset, EvalCaseConfig, EvalMethod (enum), TaskType (enum)

run.py      → EvalRun, TestCaseResult, RunStatus (enum), BaselineComparison

prompt.py   → PromptVersion, PromptStatus (enum)
```

(*Note: `ProviderConfig` in models is for config file parsing. `ProviderConfig` in `engine/base.py` is the runtime config passed to providers. Different classes, same name — keep them separate.)

---

### `evalflow/storage/`

**`db.py`** — `EvalflowDB`
```python
class EvalflowDB:
    DEFAULT_PATH = Path(".evalflow/runs.db")
    
    def __init__(self, db_path: Path = DEFAULT_PATH)
    async def __aenter__(self) -> "EvalflowDB"
    async def __aexit__(self, ...)
    
    async def initialize(self) -> None
        # CREATE TABLE IF NOT EXISTS for all tables
        # Set file permissions to 600
    
    async def save_run(self, run: EvalRun) -> None
    async def save_results(self, run_id: str, results: list[TestCaseResult]) -> None
    async def save_baseline(self, run: EvalRun, dataset_hash: str) -> None
    async def get_baseline(self, dataset_hash: str) -> Optional[dict]
    async def list_runs(self, limit, since_days, failed_only) -> list[dict]
    async def get_run(self, run_id: str) -> Optional[dict]
    async def get_run_results(self, run_id: str) -> list[dict]
    async def find_run_by_prefix(self, prefix: str) -> Optional[dict]
        # Allows partial run ID matching (first 8 chars)
```

All methods use `async with aiosqlite.connect(self.db_path) as conn:` pattern.
All queries use `?` parameterization.

**`cache.py`** — `ResponseCache`
```python
class ResponseCache:
    def __init__(self, cache_dir: Path)
    def _make_key(self, provider: str, model: str, prompt: str) -> str  # SHA-256 hash
    def get(self, provider: str, model: str, prompt: str) -> Optional[str]
    def set(self, provider: str, model: str, prompt: str, response: str) -> None
    def clear(self) -> None
    def stats(self) -> dict  # {"entries": int, "size_bytes": int}
```

Uses `shelve` from stdlib. Cache file at `.evalflow/response_cache`.

---

### `evalflow/registry/`

**`prompt_registry.py`** — `PromptRegistry`
```python
class PromptRegistry:
    def __init__(self, prompts_dir: Path)
    
    def list_prompts(self) -> list[PromptVersion]
        # Scans prompts_dir for *.yaml files
        # Returns sorted by name
    
    def get_prompt(self, name: str, status: str = "production") -> Optional[PromptVersion]
    
    def create_prompt(self, name: str, author: str = "unknown") -> PromptVersion
        # Creates prompts/{name}.yaml with draft status
        # version: 1
    
    def promote_prompt(self, name: str, to: str) -> None
        # Updates status field in YAML file
        # Validates 'to' is "staging" or "production"
    
    def increment_version(self, name: str) -> PromptVersion
        # Creates a new version entry in the YAML
        # Keeps history of previous versions
    
    def diff_versions(self, name: str, v1: int, v2: int) -> str
        # Returns unified diff of two version bodies
    
    def _load_file(self, path: Path) -> PromptVersion
        # Uses yaml.safe_load()
        # Uses safe_resolve() for path validation
    
    def _save_file(self, prompt: PromptVersion) -> None
        # Writes YAML back to file
```

---

### `evalflow/output/`

**`rich_output.py`**

Single file, single responsibility: all terminal output.

```python
# Module-level console instance
console = Console()

# All functions are module-level (no class needed)

def print_eval_header(provider: str, model: str, test_count: int) -> None
def print_test_result(result: TestCaseResult) -> None
def print_eval_summary(run: EvalRun, baseline: Optional[dict] = None) -> None
def print_baseline_comparison(comparison: BaselineComparison) -> None
def print_error(title: str, fix: str = "", link: str = "") -> None
def print_warning(message: str) -> None
def print_success(message: str) -> None
def print_info(message: str) -> None
def print_doctor_check(label: str, passed: bool, detail: str = "", optional: bool = False) -> None
def print_runs_table(runs: list[dict]) -> None
def print_compare_diff(run_a: dict, run_b: dict, results_a: list, results_b: list) -> None
def print_prompt_list(prompts: list[PromptVersion]) -> None
def print_prompt_diff(v1_body: str, v2_body: str, name: str) -> None
def create_eval_progress() -> Progress
```

Color constants:
```python
SUCCESS = "green"     # #4ADE80 from design.md
ERROR = "red"         # #F87171 from design.md  
WARNING = "yellow"    # #FACC15 from design.md
MUTED = "bright_black"  # #8B949E from design.md
```

---

### `evalflow/exceptions.py`

```python
class EvalflowError(Exception):
    """Base class for all evalflow errors."""
    pass

class ConfigError(EvalflowError):
    def __init__(self, message: str, fix: str = "", link: str = ""):
        self.message = message
        self.fix = fix
        self.link = link

class MissingAPIKeyError(ConfigError):
    def __init__(self, provider: str, env_var: str):
        super().__init__(
            f"Missing API key for {provider}",
            fix=f"Set {env_var} in your environment:\nexport {env_var}=\"your-key-here\"",
            link=f"https://evalflow.dev/docs/providers/{provider}"
        )

class ProviderError(EvalflowError):
    def __init__(self, provider: str, message: str, status_code: int = 0):
        self.provider = provider
        self.status_code = status_code
        super().__init__(message)

class DatasetError(EvalflowError):
    def __init__(self, message: str, fix: str = ""):
        self.fix = fix
        super().__init__(message)

class StorageError(EvalflowError):
    pass

class PromptNotFoundError(EvalflowError):
    def __init__(self, name: str):
        super().__init__(f"Prompt not found: {name}")
```

---

## Data Flow: Complete Eval Run

```
User: evalflow eval --provider groq

1. eval_command()
   ├── load EvalflowConfig from evalflow.yaml
   ├── load .env (python-dotenv)
   ├── validate GROQ_API_KEY in environment
   ├── load Dataset from evals/dataset.json
   └── create EvalOrchestrator(config, db, cache, callback=print_test_result)

2. EvalOrchestrator.run_eval(dataset, "groq")
   ├── run_id = sha256(dataset+groq+model)[:12] prefixed with date
   ├── get existing baseline from SQLite
   ├── for each test_case (concurrently, max 5):
   │   ├── check cache → if hit, use cached response
   │   ├── GroqProvider.complete(prompt, config) → ProviderResponse
   │   ├── cache response
   │   ├── run eval methods (per test_case.eval_config.methods):
   │   │   ├── ExactMatchEvaluator.evaluate()
   │   │   ├── EmbeddingEvaluator.evaluate()
   │   │   └── ConsistencyEvaluator.evaluate() [if configured]
   │   ├── compute weighted score
   │   ├── compare to threshold → pass/fail
   │   ├── build TestCaseResult
   │   └── callback(result) → print_test_result() [updates progress]
   ├── compute overall_score (weighted average)
   ├── compare to baseline → BaselineComparison
   ├── save EvalRun to SQLite
   └── return EvalRun

3. eval_command() (continued)
   ├── print_eval_summary(run, baseline)
   ├── if first run: save_baseline(run)
   └── sys.exit(0) if PASS, sys.exit(1) if FAIL
```

---

## State: What Lives Where

| Data | Location | Format | Persisted |
|---|---|---|---|
| Config | `evalflow.yaml` | YAML | Yes (committed) |
| Prompts | `prompts/*.yaml` | YAML | Yes (committed) |
| Dataset | `evals/dataset.json` | JSON | Yes (committed) |
| Run history | `.evalflow/runs.db` | SQLite | Yes (not committed) |
| Baselines | `.evalflow/runs.db` | SQLite | Yes (not committed) |
| Response cache | `.evalflow/response_cache` | shelve | Yes (not committed) |
| Embedding model | `.evalflow/models/` | Binary | Yes (not committed) |
| .env | `.env` | env vars | No (gitignored) |

The `.evalflow/` directory is gitignored. Everything inside it is local-only.
Everything outside `.evalflow/` (config, prompts, dataset) is safe to commit.

---

## Async Architecture

`evalflow eval` is the only command with significant async work (provider API calls).

Pattern used throughout:
```python
# In commands (sync Typer context):
import asyncio

def eval_command(...):
    asyncio.run(_async_eval(...))

async def _async_eval(...):
    async with EvalflowDB() as db:
        orchestrator = EvalOrchestrator(config, db, cache)
        run = await orchestrator.run_eval(dataset, provider)
```

Concurrent test case execution:
```python
# In EvalOrchestrator
semaphore = asyncio.Semaphore(5)  # max 5 concurrent

async def _run_with_semaphore(test_case):
    async with semaphore:
        return await self._run_test_case(test_case, ...)

results = await asyncio.gather(
    *[_run_with_semaphore(tc) for tc in test_cases],
    return_exceptions=True
)
```

Results are ordered to match input order (asyncio.gather preserves order).

---

## File: `evalflow.yaml` vs Code

Rule: business logic lives in code, not config.

**In evalflow.yaml:**
- Provider API key env var names
- Default model per provider
- Dataset file path
- Score thresholds
- Judge config

**NOT in evalflow.yaml:**
- Which eval methods to use (in dataset.json per test case)
- Prompt bodies (in prompts/*.yaml)
- Retry logic (in provider code)
- Scoring formula (in evaluator.py)

---

## Testing Architecture

```
tests/
├── conftest.py
│   ├── Fixtures: tmp_project_dir, mock_provider, sample_run, sample_config, sample_dataset
│   └── Helpers: run_command(args) → (exit_code, output)
│
├── unit/
│   ├── test_models.py          # Pure Pydantic validation
│   ├── test_eval_methods.py    # Pure scoring functions
│   └── test_registry.py       # Prompt registry with temp dirs
│
├── integration/
│   ├── test_storage.py         # SQLite with temp db
│   ├── test_evaluator.py       # Orchestrator with mock provider
│   └── test_commands.py        # CLI commands via Typer test client
│
└── e2e/
    └── test_error_paths.py     # All error scenarios end-to-end
```

Test isolation rules:
- Unit tests: no filesystem, no network, no database
- Integration tests: temp filesystem, mock network (httpx_mock), temp database
- E2E tests: full CLI invocations, real filesystem in temp dir, mock network

Never use `monkeypatch.setenv` for API keys — use `mock.patch.dict(os.environ, {...})`.

---

## Dependency Constraints

No circular imports. Import order must follow this hierarchy (lower numbers can't import from higher):

```
1. exceptions.py           (imports nothing from evalflow)
2. models/                 (imports only exceptions)
3. engine/base.py          (imports models, exceptions)
4. engine/methods/         (imports models, engine/base, exceptions)
5. engine/providers/       (imports models, engine/base, exceptions)
6. engine/evaluator.py     (imports all engine/*, models, storage, exceptions)
7. storage/                (imports models, exceptions)
8. registry/               (imports models, exceptions)
9. output/                 (imports models, exceptions)
10. commands/              (imports all of the above)
11. main.py                (imports commands/)
```

Verify with: `python -c "import evalflow"` — must complete without circular import errors.

# prompts.md — evalflow Coding Agent: 30-Prompt Build Plan

## How to use this file

Each prompt is self-contained and builds on the previous. Feed them to your coding agent (Cursor, Claude Code, Windsurf, etc.) in order. Each prompt references the context files:

- `context.md` — full product spec
- `design.md` — terminal design system
- `security.md` — security requirements
- `architecture.md` — file structure
- `testing.md` — test requirements

**Before starting:** Read context.md fully. All decisions should be consistent with that spec.

---

## PROMPT 1 — Monorepo scaffold and pyproject.toml

```
Read context.md fully before starting.

Create the complete evalflow monorepo directory structure exactly as defined in context.md under "Repository Structure".

Then create the root pyproject.toml as a uv workspace:

[tool.uv.workspace]
members = ["packages/cli", "packages/core"]

Create packages/core/pyproject.toml:
- Package name: evalflow-core
- Python >=3.10
- No external dependencies (types only)

Create packages/cli/pyproject.toml:
- Package name: evalflow
- Python >=3.10
- Dependencies:
  - typer>=0.12.0
  - rich>=13.7.0
  - pydantic>=2.6.0
  - pyyaml>=6.0.1
  - aiosqlite>=0.20.0
  - httpx>=0.27.0
  - python-dotenv>=1.0.0
  - numpy>=1.26.0
  - openai>=1.30.0
  - anthropic>=0.28.0
- Optional dependencies:
  - [embeddings]: sentence-transformers>=2.7.0
- Scripts entry point:
  - evalflow = "evalflow.main:app"

Create a root .gitignore that includes:
- Python standard ignores
- .env, .env.local, .env.*
- !.env.example
- .evalflow/
- *.evalflow.db

Create packages/cli/evalflow/__init__.py with version = "0.1.0" and a public get_prompt() stub.

Create packages/core/evalflow_core/__init__.py with shared type stubs.

Output: All files created. Run `uv sync` compatible structure.
```

---

## PROMPT 2 — Pydantic models (all data structures)

```
Read context.md sections: "Dataset Format", "Prompt Registry Format", "Configuration File Format", "SQLite Schema".
Read security.md section: "Sensitive Data in Eval Runs".

Create all Pydantic v2 models in packages/cli/evalflow/models/:

**config.py** — EvalflowConfig
- ProviderConfig: api_key_env: str, default_model: str
- ProvidersConfig: openai, anthropic, groq, gemini, ollama (all Optional)
- EvalConfig: dataset path, baseline_file, default_provider, consistency_runs
- ThresholdsConfig: task_success, relevance, hallucination_max, consistency_min
- JudgeConfig: provider, model
- PromptsConfig: directory
- StorageConfig: store_raw_outputs (bool), max_output_chars (int)
- EvalflowConfig: root model combining all above
- Class method: EvalflowConfig.from_yaml(path) — uses yaml.safe_load() per security.md

**dataset.py** — Dataset models
- EvalMethod enum: exact_match, embedding_similarity, consistency, llm_judge
- TaskType enum: summarization, classification, extraction, qa, generation, rewrite
- EvalCaseConfig: methods (list[EvalMethod]), judge (bool), weight (float default 1.0)
- TestCase: id, description, task_type, input, expected_output, context (optional), tags, eval_config
- Dataset: version, test_cases. Class method Dataset.from_json(path)
- Validation: test case IDs must be kebab-case, unique within dataset

**run.py** — Run result models
- RunStatus enum: pass_, fail, error
- TestCaseResult: test_case_id, status, score, exact_match_score, embedding_score, consistency_score, judge_score, raw_output (truncated to max_output_chars), error
- EvalRun: id, created_at, provider, model, dataset_hash, prompt_version_hash, status, overall_score, duration_ms, results list

**prompt.py** — Prompt version model
- PromptStatus enum: draft, staging, production
- PromptVersion: id, version (int), status, body, author, created_at, tags

All models must have:
- model_config = ConfigDict(frozen=False)
- Proper Optional fields with defaults
- Validators where needed (e.g. score between 0 and 1)

Write unit tests in packages/cli/tests/test_models.py covering model creation and validation.
```

---

## PROMPT 3 — SQLite storage layer

```
Read context.md sections: "SQLite Schema".
Read security.md sections: "SQLite Security", "Sensitive Data in Eval Runs".

Create packages/cli/evalflow/storage/db.py:

Implement EvalflowDB class with async context manager support:

class EvalflowDB:
    def __init__(self, db_path: Path)
    async def __aenter__(self) -> "EvalflowDB"
    async def __aexit__(self, ...)
    async def initialize(self) -> None  # creates tables if not exist
    async def save_run(self, run: EvalRun) -> None
    async def save_results(self, run_id: str, results: list[TestCaseResult]) -> None
    async def save_baseline(self, run: EvalRun) -> None
    async def get_baseline(self, dataset_hash: str) -> Optional[dict]
    async def list_runs(self, limit: int = 20, since_days: Optional[int] = None, failed_only: bool = False) -> list[dict]
    async def get_run(self, run_id: str) -> Optional[dict]
    async def get_run_results(self, run_id: str) -> list[dict]

Rules from security.md:
- All queries parameterized (no f-string SQL)
- File permissions set to 600 on creation
- Database file at .evalflow/runs.db relative to project root
- Create .evalflow/ directory if not exists

Create packages/cli/evalflow/storage/cache.py:

Implement ResponseCache using shelve:
- Cache responses keyed on SHA-256 hash of (provider + model + prompt_text)
- Cache file at .evalflow/response_cache
- Methods: get(key) -> Optional[str], set(key, value: str), clear()

Write tests in packages/cli/tests/test_storage.py using temp directories.
All tests must clean up after themselves.
```

---

## PROMPT 4 — BaseProvider interface and OpenAI provider

```
Read context.md sections: "Providers", "Eval Engine: Four Layers".
Read security.md sections: "HTTP Security", "API Key Handling".

Create packages/cli/evalflow/engine/base.py:

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

Create packages/cli/evalflow/engine/providers/openai.py:

class OpenAIProvider(BaseProvider):
    - Uses openai SDK with async client
    - Reads api_key from ProviderConfig (never logs it)
    - Sets timeout from security.md: connect 30s, read 60s
    - Implements exponential backoff retry (max 3, base 1s, max 10s) for 429/502/503
    - health_check() makes a lightweight models.list() call
    - Raises ProviderError (custom exception) on failure, not raw SDK errors

Create packages/cli/evalflow/engine/providers/__init__.py with a registry:

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "openai": OpenAIProvider,
    ...
}

def get_provider(name: str) -> type[BaseProvider]: ...

Create custom exceptions in packages/cli/evalflow/exceptions.py:
- EvalflowError (base)
- ConfigError
- MissingAPIKeyError(provider, env_var)
- ProviderError(provider, message)
- DatasetError
- StorageError

Write tests using httpx_mock or unittest.mock — never make real API calls in tests.
```

---

## PROMPT 5 — Remaining providers (Anthropic, Groq, Gemini, Ollama)

```
Read context.md section: "Providers".
Read packages/cli/evalflow/engine/providers/openai.py for the pattern to follow.
Read security.md section: "HTTP Security".

Create the following provider implementations. Each must follow the exact same BaseProvider pattern as OpenAI:

**anthropic.py** — AnthropicProvider
- Uses anthropic SDK with async client
- Maps Anthropic message format to ProviderResponse
- Handle anthropic-specific error types

**groq.py** — GroqProvider
- Groq is OpenAI-compatible — use httpx directly (not SDK)
- Base URL: https://api.groq.com/openai/v1
- Same retry logic as OpenAI provider
- This is also the default judge provider

**gemini.py** — GeminiProvider
- Use httpx directly to generativelanguage.googleapis.com
- API key passed as query param (Gemini-specific)
- Map Gemini response format to ProviderResponse

**ollama.py** — OllamaProvider
- Use httpx to localhost:11434
- No API key required (api_key field ignored)
- health_check() hits /api/tags endpoint
- If Ollama not running, give clear error:
  "✗ Ollama is not running. Start it with: ollama serve"

Register all providers in __init__.py registry.

Update packages/cli/evalflow/engine/providers/__init__.py:
PROVIDER_REGISTRY = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}

Write mock tests for each provider covering: successful response, retry on 429, provider error.
```

---

## PROMPT 6 — Eval methods: exact match and embedding similarity

```
Read context.md section: "Eval Engine: Four Layers".

Create packages/cli/evalflow/engine/methods/:

**exact_match.py**
class ExactMatchEvaluator:
    def evaluate(self, actual: str, expected: str) -> float:
        """Returns 1.0 for match, 0.0 for no match"""
    
    Normalization before comparison:
    - Lowercase both strings
    - Strip leading/trailing whitespace
    - Collapse multiple spaces to single space
    - Strip punctuation for "soft" comparison (second pass)
    
    Return 1.0 if either strict or soft match succeeds.
    
    Also implement:
    def evaluate_structured(self, actual: str, expected: str) -> float:
        """For JSON/structured output — parse both and compare semantically"""

**embedding.py**
class EmbeddingEvaluator:
    MODEL_NAME = "all-MiniLM-L6-v2"
    
    def __init__(self):
        self._model = None  # lazy load
    
    def _load_model(self):
        """Lazy load sentence-transformers on first use"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.MODEL_NAME)
            except ImportError:
                raise EvalflowError(
                    "sentence-transformers not installed.\n"
                    "Install with: pip install 'evalflow[embeddings]'"
                )
    
    def evaluate(self, actual: str, expected: str) -> float:
        """Returns cosine similarity score between 0 and 1"""
        self._load_model()
        embeddings = self._model.encode([actual, expected])
        # numpy cosine similarity
        return float(numpy_cosine_similarity(embeddings[0], embeddings[1]))
    
    def is_available(self) -> bool:
        """Check if sentence-transformers is installed"""

Create a shared singleton in packages/cli/evalflow/engine/methods/__init__.py:
- _embedding_evaluator: Optional[EmbeddingEvaluator] = None
- get_embedding_evaluator() -> EmbeddingEvaluator

Write tests for both — exact_match tests use pure strings, embedding tests mock SentenceTransformer.
```

---

## PROMPT 7 — Eval methods: consistency scoring and LLM judge

```
Read context.md section: "Eval Engine: Four Layers — Layer 3 and Layer 4".
Read security.md section: "Output Data Sanitization".

**consistency.py**
class ConsistencyEvaluator:
    async def evaluate(
        self,
        prompt: str,
        provider: BaseProvider,
        provider_config: ProviderConfig,
        runs: int = 3
    ) -> float:
        """
        Run same prompt N times, score variance.
        Returns: 1.0 - normalized_variance (higher = more consistent)
        
        Steps:
        1. Run prompt N times concurrently (asyncio.gather)
        2. Get embedding for each response
        3. Compute pairwise cosine similarities
        4. Return mean similarity (proxy for consistency)
        """
    
    Score interpretation:
    - 1.0 = identical responses
    - 0.9+ = highly consistent
    - <0.8 = inconsistent (likely flagged)

**judge.py**
JUDGE_SYSTEM_PROMPT = """
You are an expert evaluator assessing LLM outputs for quality and groundedness.
You will be given an input, expected output, and actual output.
Respond with ONLY a JSON object with these fields:
{
  "score": float between 0 and 1,
  "grounded": boolean,
  "reasoning": "one sentence explanation"
}
Do not add any text outside the JSON object.
"""

class LLMJudgeEvaluator:
    def __init__(self, judge_provider: BaseProvider, judge_config: ProviderConfig):
        ...
    
    async def evaluate(
        self,
        input_text: str,
        expected: str,
        actual: str,
        context: Optional[str] = None
    ) -> JudgeResult:
        """
        Send to judge LLM, parse JSON response.
        Validate response is valid JSON with required fields.
        On parse failure: return score=0.5 with error flag (don't crash).
        """
    
    @dataclass
    class JudgeResult:
        score: float
        grounded: bool
        reasoning: str
        error: Optional[str] = None

Security: escape all user content in judge prompt using f-string carefully.
Never put raw output directly into Rich markup — use rich.markup.escape().

Write tests: mock the judge provider, test JSON parsing, test parse failure graceful handling.
```

---

## PROMPT 8 — Core evaluator orchestrator

```
Read context.md sections: "Eval Engine: Four Layers", "Dataset Format", "SQLite Schema".

Create packages/cli/evalflow/engine/evaluator.py:

class EvalOrchestrator:
    def __init__(
        self,
        config: EvalflowConfig,
        db: EvalflowDB,
        cache: ResponseCache,
        progress_callback: Optional[Callable] = None
    ):
        ...
    
    async def run_eval(
        self,
        dataset: Dataset,
        provider_name: str,
        offline: bool = False,
        tags: Optional[list[str]] = None
    ) -> EvalRun:
        """
        Main eval orchestration:
        
        1. Validate provider config + API key present
        2. Filter test cases by tags if specified
        3. Generate run_id = f"{date}-{sha256(dataset+provider+model)[:12]}"
        4. For each test case (with progress callback):
            a. If offline: use cached response or skip
            b. Call provider.complete()
            c. Cache response
            d. Run applicable eval methods (from test_case.eval_config)
            e. Compute weighted score
            f. Determine pass/fail vs threshold
        5. Compute overall_score as weighted average
        6. Compare against baseline if exists
        7. Save run to SQLite
        8. Return EvalRun with all results
        """
    
    async def _run_test_case(
        self,
        test_case: TestCase,
        provider: BaseProvider,
        provider_config: ProviderConfig,
        offline: bool
    ) -> TestCaseResult:
        """Run all eval methods for a single test case"""
    
    def _compute_run_id(self, dataset: Dataset, provider: str, model: str) -> str:
        """Deterministic run ID from content hash"""
        from hashlib import sha256
        from datetime import date
        content = f"{dataset.model_dump_json()}{provider}{model}"
        hash_suffix = sha256(content.encode()).hexdigest()[:12]
        return f"{date.today().strftime('%Y%m%d')}-{hash_suffix}"
    
    async def save_baseline(self, run: EvalRun) -> None:
        """Save run as new baseline"""

Write integration tests with mocked provider that verify:
- correct run ID format
- baseline comparison logic
- tag filtering
- offline mode uses cache
```

---

## PROMPT 9 — Rich output renderer

```
Read design.md fully before writing any output code.
Read context.md section: "CLI Commands".

Create packages/cli/evalflow/output/rich_output.py.

This file handles ALL terminal output. No print() statements anywhere else in the codebase.
All other modules call functions from this module.

Implement these functions matching design.md exactly:

def print_eval_header(provider: str, model: str, test_count: int) -> None:
    """
    Output:
    Running 5 test cases against gpt-4o-mini...
    """

def print_test_result(result: TestCaseResult, index: int, total: int) -> None:
    """
    Output (aligned columns):
    ✓ summarize_short_article    0.91
    ✗ answer_with_context        0.61
    
    Green ✓ for pass, Red ✗ for fail
    Muted color for test case ID
    Score right-aligned
    """

def print_eval_summary(run: EvalRun, baseline: Optional[dict] = None) -> None:
    """
    Output:
    
    Quality Gate: PASS          ← green if pass, red if fail
    Baseline: saved             ← on first run
    Failures: 1                 ← number of failed test cases
    Duration: 4.2s
    Run ID: 20240315-a3f9c2d81b4e
    
    If baseline exists, show delta:
    Δ overall: +0.03 (improved)
    """

def print_error(title: str, fix: str, link: Optional[str] = None) -> None:
    """
    Output per design.md error format:
    ✗ Missing API key for OpenAI
    
      Set OPENAI_API_KEY in your environment
      or add it to evalflow.yaml
      
      https://platform.openai.com/api-keys
    """

def print_doctor_check(label: str, status: bool, detail: Optional[str] = None) -> None:
    """
    ✓ evalflow 0.1.0 installed
    ✗ OPENAI_API_KEY not set
    """

def print_runs_table(runs: list[dict]) -> None:
    """Rich table of recent runs with columns: Run ID, Date, Provider, Model, Score, Status"""

def print_compare_diff(run_a: dict, run_b: dict, results_a: list, results_b: list) -> None:
    """Side-by-side comparison of two runs with deltas highlighted"""

def create_eval_progress() -> Progress:
    """Returns a Rich Progress instance configured per design.md"""

def print_prompt_list(prompts: list[PromptVersion]) -> None:
def print_prompt_diff(v1: PromptVersion, v2: PromptVersion) -> None:

Color constants (from design.md):
SUCCESS_COLOR = "green"
ERROR_COLOR = "red"  
WARNING_COLOR = "yellow"
MUTED_COLOR = "bright_black"

All output uses Rich Console. Never use print().
Never render LLM output as Rich markup — always use escape().
```

---

## PROMPT 10 — `evalflow init` command

```
Read context.md section: "CLI Commands — evalflow init".
Read security.md sections: "API Key Handling", ".env File Security".

Create packages/cli/evalflow/commands/init.py:

Implement init_command() called by `evalflow init`.

Flow:
1. Check if evalflow.yaml already exists. If yes, ask "Overwrite? [y/N]"
2. Interactive prompts using Typer:
   a. Choose provider: [openai, anthropic, groq, gemini, ollama]
   b. Choose model (show sensible defaults per provider)
   c. Ask for API key env var name (default: OPENAI_API_KEY etc.)
      - NEVER ask for the actual key value
      - Print: "evalflow stores the variable name, not the key itself"
3. Write evalflow.yaml with chosen settings
4. Create prompts/ directory
5. Write evals/dataset.json with 1 example test case:
   {
     "version": "1.0",
     "test_cases": [{
       "id": "example-summarization",
       "description": "Basic summarization test",
       "task_type": "summarization",
       "input": "Summarize in one sentence: The quick brown fox jumps over the lazy dog.",
       "expected_output": "A fox jumps over a dog.",
       "context": "",
       "tags": ["example"],
       "eval_config": {"methods": ["embedding_similarity"], "judge": false, "weight": 1.0}
     }]
   }
6. Add security entries to .gitignore (per security.md)
7. Create .env.example (per security.md)
8. Create .evalflow/ directory

Output on completion:
  evalflow initialized

  Next steps:
  1. Add your API key to your environment:
     export OPENAI_API_KEY="your-key-here"
  
  2. Run your first eval:
     evalflow eval
  
  3. Add to CI (GitHub Actions):
     https://evalflow.dev/docs/ci-github-actions

Use print_error() from rich_output.py for any errors.
All success messages use Rich formatting per design.md.
```

---

## PROMPT 11 — `evalflow eval` command

```
Read context.md sections: "CLI Commands — evalflow eval", "CI Integration".

Create packages/cli/evalflow/commands/eval.py:

@app.command()
def eval_command(
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t"),
    offline: bool = typer.Option(False, "--offline"),
    debug: bool = typer.Option(False, "--debug"),
    save_baseline: bool = typer.Option(False, "--save-baseline"),
):

Flow:
1. Load evalflow.yaml (ConfigError → print_error() then sys.exit(2))
2. Load python-dotenv .env file
3. Validate API key present for chosen provider
   - If missing: print_error() with exact fix + link, sys.exit(2)
4. Load dataset (DatasetError → print_error() then sys.exit(2))
5. Create DB + cache instances
6. Run EvalOrchestrator.run_eval() with progress callbacks
7. During eval: call print_test_result() for each completed test case
8. After eval:
   a. Print eval summary via print_eval_summary()
   b. Compare to baseline if exists, show delta
   c. If --save-baseline flag: save as new baseline
   d. First run ever: save as baseline automatically, print "Baseline: saved"
9. Exit codes:
   - sys.exit(0) if PASS
   - sys.exit(1) if FAIL (quality below threshold)
   - sys.exit(2) if ERROR (config, provider, etc.)

With --debug flag:
- Show full stack traces
- Show HTTP request/response details
- Print "Debug mode enabled — not for production use"

Error handling: catch all EvalflowError subclasses, convert to print_error() + correct exit code.
Never let unhandled exceptions reach the user.
```

---

## PROMPT 12 — `evalflow doctor` command

```
Read context.md section: "CLI Commands — evalflow doctor".

Create packages/cli/evalflow/commands/doctor.py:

@app.command()
def doctor_command():

Implement a comprehensive system check that outputs a ✓/✗ checklist.

Checks to perform (in order):
1. evalflow version — always ✓, shows version number
2. Python version — ✓ if >=3.10, ✗ with upgrade instruction if not
3. evalflow.yaml found — ✓/✗ with path
4. evalflow.yaml valid — parse and validate, show specific error if invalid
5. evals/dataset.json found — ✓/✗, show test case count if found
6. dataset.json valid — parse and validate format
7. .evalflow/ directory exists
8. SQLite database accessible
9. Git repository detected — ✓/✗ (checks for .git directory)
10. For each configured provider in evalflow.yaml:
    - API key env var is set — ✓/✗ with exact var name
    - Provider health check (optional, only if --check-providers flag)
11. sentence-transformers installed — ✓ or "! optional — needed for embedding_similarity"
12. .gitignore has .env entry — ✓/✗ with fix instruction
13. .env file exists (but NOT committed to git)

Output format per design.md:
  ✓ evalflow 0.1.0 installed
  ✓ Python 3.11.4
  ✓ evalflow.yaml found
  ✓ dataset.json found (5 test cases)
  ✓ OPENAI_API_KEY set
  ! sentence-transformers not installed (optional)
  ✗ .gitignore missing .env entry

  1 issue found. Run evalflow doctor --fix to resolve.

Add --fix flag that auto-fixes what can be fixed (add .gitignore entries).

Final line: "Everything looks good. Run: evalflow eval" OR "X issues found."
```

---

## PROMPT 13 — `evalflow runs` and `evalflow compare` commands

```
Read context.md sections: "CLI Commands — evalflow runs, evalflow compare".

Create packages/cli/evalflow/commands/runs.py:

@app.command("runs")
def runs_command(
    limit: int = typer.Option(20, "--limit", "-n"),
    since: Optional[str] = typer.Option(None, "--since"),  # e.g. "7d", "30d"
    failed_only: bool = typer.Option(False, "--failed-only"),
):
    """List recent eval runs"""
    Load DB, call list_runs() with filters.
    Pass results to print_runs_table() from rich_output.py.
    If no runs: print "No runs found. Run: evalflow eval"
    
    Parse --since: accept "7d", "30d", "1h" format. Convert to timedelta.

@app.command("compare")
def compare_command(
    run_a: str = typer.Argument(..., help="First run ID"),
    run_b: str = typer.Argument(..., help="Second run ID"),
):
    """Compare two eval runs side by side"""
    Load both runs from DB. If either not found: clear error.
    Load results for both runs.
    Pass to print_compare_diff() from rich_output.py.
    
    print_compare_diff() should show:
    - Run metadata (date, provider, model, score) side by side
    - Per test case: ID, score in run A, score in run B, delta (colored green/red)
    - Overall: which run performed better, by how much
    - Test cases that changed status (pass→fail or fail→pass) highlighted

Handle: run IDs can be partial (first 8 chars). Auto-complete from DB.
```

---

## PROMPT 14 — `evalflow prompt` commands

```
Read context.md sections: "CLI Commands — evalflow prompt *", "Prompt Registry Format".
Read security.md section: "File Path Security".

Create packages/cli/evalflow/commands/prompt.py and packages/cli/evalflow/registry/prompt_registry.py:

**prompt_registry.py** — PromptRegistry class:
- __init__(self, prompts_dir: Path)
- list_prompts() -> list[PromptVersion]
- get_prompt(name: str, status: str = "production") -> Optional[PromptVersion]
- create_prompt(name: str, author: str) -> PromptVersion (writes YAML file)
- promote_prompt(name: str, target: str) -> None (updates status field in YAML)
- diff_versions(name: str, v1: int, v2: int) -> str (returns diff text)
- load_prompt_file(path: Path) -> PromptVersion (uses yaml.safe_load per security.md)
- All path operations use safe_resolve() from security.md

**prompt.py commands:**

@prompt_app.command("create")
def prompt_create(name: str = typer.Argument(...)):
    """Create a new prompt YAML file"""
    Check name is valid (lowercase, hyphens only).
    Create prompts/{name}.yaml with status: draft, version: 1.
    Output: "✓ Created prompts/{name}.yaml"

@prompt_app.command("list")
def prompt_list():
    """List all prompts with status and last eval score"""
    Load all YAML files from prompts/ directory.
    Display via print_prompt_list().

@prompt_app.command("diff")
def prompt_diff(
    name: str = typer.Argument(...),
    v1: int = typer.Argument(...),
    v2: int = typer.Argument(...),
):
    """Show diff between two versions of a prompt"""
    Load both versions from file history.
    Show colored diff using Rich.

@prompt_app.command("promote")
def prompt_promote(
    name: str = typer.Argument(...),
    to: str = typer.Option(..., "--to", help="staging or production"),
):
    """Promote a prompt version to staging or production"""
    Validate --to value is "staging" or "production".
    Run eval first warning: "Consider running evalflow eval before promoting to production."
    Update status in YAML file.
    Output: "✓ {name} promoted to {to}"

Also implement the public API in packages/cli/evalflow/__init__.py:
def get_prompt(name: str, status: str = "production") -> str:
    """Returns prompt body for use in application code"""
    Reads from prompts/ directory relative to working directory.
    Raises PromptNotFoundError if not found.
```

---

## PROMPT 15 — Main CLI app wiring

```
Read context.md sections: "CLI Commands" (all).
Read all previously created command files.

Create packages/cli/evalflow/main.py:

Wire all commands into a single Typer app.

app = typer.Typer(
    name="evalflow",
    help="pytest for LLMs — catch prompt regressions before they reach production.",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

Add a version callback:
@app.callback()
def main(version: bool = typer.Option(False, "--version", "-v")):
    if version:
        print(f"> evalflow v{__version__}")
        raise typer.Exit()

Register commands:
app.command("init")(init_command)
app.command("eval")(eval_command)
app.command("doctor")(doctor_command)
app.command("runs")(runs_command)
app.command("compare")(compare_command)

prompt_app = typer.Typer(help="Manage prompt versions")
app.add_typer(prompt_app, name="prompt")
prompt_app.command("create")(prompt_create)
prompt_app.command("list")(prompt_list)
prompt_app.command("diff")(prompt_diff)
prompt_app.command("promote")(prompt_promote)

Global error handler:
Wrap app() in try/except to catch any unhandled EvalflowError.
Print user-friendly message. Never show Python traceback to users.
With --debug, show full traceback.

if __name__ == "__main__":
    app()

Create a basic smoke test: `evalflow --help` and `evalflow --version` must work without any config files.
```

---

## PROMPT 16 — CI/CD integration files and examples

```
Read context.md sections: "CI Integration", "Repository Structure — examples/".
Read security.md section: "CI/CD Security Guidance".

Create .github/workflows/ci.yml — evalflow's own CI:
- Trigger: push and PR on main
- Matrix: Python 3.10, 3.11, 3.12
- Steps: checkout, setup-python, uv sync, pytest
- Run evalflow doctor --no-provider-check
- Ensure no secrets in logs

Create .github/workflows/publish.yml — PyPI publish:
- Trigger: on tag push (v*)
- Uses PyPI trusted publisher (OIDC) — no API token in secrets
- Build with uv build, publish with uv publish

Create examples/openai-basic/:
- README.md: step-by-step from pip install to first passing eval
- evalflow.yaml: minimal OpenAI config
- evals/dataset.json: 3 real test cases (summarization, classification, qa)
- prompts/assistant.yaml: example prompt file
- .env.example

Create examples/groq-ci/:
- README.md: complete CI setup guide
- .github/workflows/evalflow.yml: complete working GitHub Actions file
- evalflow.yaml: Groq config
- evals/dataset.json: 3 test cases
- NOTE in README: "Groq free tier — zero cost for CI"

Create examples/langchain-app/:
- README.md: how to use evalflow alongside LangChain
- app.py: simple LangChain app that uses get_prompt() from evalflow
- evals/dataset.json: LangChain-style test cases
- evalflow.yaml: config

Each example README must follow design.md: pain story, install, run, result screenshot (as text).

Create the copy-pasteable GitHub Actions workflow file at:
docs/ci-github-actions.yml (referenced from documentation)
```

---

## PROMPT 17 — Documentation site (Mintlify)

```
Read context.md section: "Launch Checklist — Documentation complete".
Read design.md section: "README Design".

Create docs/ directory with Mintlify structure:

docs/mint.json:
{
  "name": "evalflow",
  "logo": { "light": "/logo/light.svg", "dark": "/logo/dark.svg" },
  "favicon": "/favicon.svg",
  "colors": { "primary": "#4ADE80" },
  "navigation": [
    { "group": "Getting started", "pages": ["quickstart"] },
    { "group": "Core concepts", "pages": ["concepts", "eval-methods", "prompt-registry"] },
    { "group": "CLI reference", "pages": ["cli-reference"] },
    { "group": "CI/CD", "pages": ["ci-github-actions", "ci-gitlab", "ci-circleci"] },
    { "group": "Providers", "pages": ["providers/openai", "providers/groq", "providers/anthropic", "providers/ollama"] },
    { "group": "Examples", "pages": ["examples"] }
  ]
}

Create docs/quickstart.mdx:
- Title: "Get started in 10 minutes"
- Sections: Install, Initialize, Write your first test, Run eval, Add to CI
- Each section has a code block + expected output (as text)
- Final section: "You just set up a quality gate for your LLM. Every PR that touches prompts will now be tested automatically."

Create docs/concepts.mdx:
- What is a quality gate?
- What is a baseline?
- What is a prompt regression?
- How the four eval methods work (with when-to-use guidance)

Create docs/cli-reference.mdx:
- Full reference for every command and flag
- Generated from the command docstrings
- Include example output for each command

Create docs/ci-github-actions.mdx:
- Step-by-step GitHub Actions setup
- Include the complete workflow file
- Include secrets setup instructions
- Security note per security.md

Create docs/providers/groq.mdx:
- Highlight: free tier, no credit card
- Complete setup in 60 seconds
- Best for: CI/CD, teams on a budget

All docs pages must be concise, code-first, and follow design.md principles.
```

---

## PROMPT 18 — README.md

```
Read design.md sections: "README Design", "CLI Output Design", "Branding Rules".
Read context.md section: "Launch Checklist".

Create the root README.md. This is the most important marketing document evalflow has.

Structure (follow design.md exactly):

1. Logo/name (monospace, lowercase, dark background friendly):
\```
> evalflow
\```

2. Tagline:
pytest for LLMs

3. Badges (on one line):
[![PyPI](https://img.shields.io/pypi/v/evalflow)](...)
[![Python](https://img.shields.io/pypi/pyversions/evalflow)](...)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](...)
[![CI](https://github.com/evalflow/evalflow/workflows/CI/badge.svg)](...)

4. Pain story (exactly as in context.md — 4 lines):
\```
You changed one prompt.
Summarization improved.
Classification silently broke.
Nobody noticed for 4 days.

evalflow catches this in CI before it ships.
\```

5. Install (immediately visible):
\```bash
pip install evalflow
\```

6. Quick start (3 commands):
\```bash
evalflow init
evalflow eval
\```

7. Terminal screenshot (as code block showing real output per design.md):
\```
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
\```

8. GitHub Actions (1-click CI):
Show the 15-line workflow file

9. Features list (brief, no marketing language):
- pytest-style exit codes (0=pass, 1=fail)
- 4 eval methods: exact match, embedding, consistency, LLM judge
- Baseline snapshots — catches regressions, not just failures
- Prompt registry — version your prompts like code
- Works with OpenAI, Anthropic, Groq, Gemini, Ollama
- Local SQLite — no account needed

10. Documentation link
11. Security section (2 lines per security.md)
12. License: MIT

Rules:
- No long paragraphs
- No buzzwords
- No gradients or images
- Code-first
- Under 150 lines total
```

---

## PROMPT 19 — Offline mode and response caching

```
Read context.md section: "CLI Commands — evalflow eval --offline".
Read security.md section: "Output Data Sanitization".

Enhance packages/cli/evalflow/storage/cache.py:

class ResponseCache:
    """Disk cache for LLM responses using shelve."""
    
    def __init__(self, cache_dir: Path):
        self.cache_path = cache_dir / "response_cache"
    
    def _make_key(self, provider: str, model: str, prompt: str) -> str:
        """Deterministic cache key from content hash."""
        content = f"{provider}:{model}:{prompt}"
        return sha256(content.encode()).hexdigest()
    
    def get(self, provider: str, model: str, prompt: str) -> Optional[str]:
        """Return cached response or None."""
        key = self._make_key(provider, model, prompt)
        with shelve.open(str(self.cache_path)) as db:
            return db.get(key)
    
    def set(self, provider: str, model: str, prompt: str, response: str) -> None:
        """Cache a provider response."""
        key = self._make_key(provider, model, prompt)
        with shelve.open(str(self.cache_path)) as db:
            db[key] = response
    
    def clear(self) -> None:
        """Clear all cached responses."""
    
    def stats(self) -> dict:
        """Return cache stats: entry count, size on disk."""

Update EvalOrchestrator to use cache:
- In _run_test_case(): check cache before calling provider
- Always write to cache after successful provider call
- In offline mode: if no cache hit, skip test case with warning:
  "! Skipping {test_case_id} — no cached response (run online first)"

Add cache info to `evalflow doctor`:
  ✓ Response cache: 23 entries

Add `evalflow cache clear` as a hidden command (not in help, but works):
  evalflow cache clear → clears .evalflow/response_cache
```

---

## PROMPT 20 — `evalflow.yaml` validation and helpful config errors

```
Read security.md section: "YAML safety".
Read context.md section: "Error Message Standards", "Configuration File Format".

This prompt is about making config errors developer-friendly — no tracebacks, always actionable.

Enhance packages/cli/evalflow/models/config.py:

Add comprehensive validation to EvalflowConfig:

@classmethod
def from_yaml(cls, path: Path) -> "EvalflowConfig":
    """Load and validate config with helpful errors."""
    if not path.exists():
        raise ConfigError(
            "evalflow.yaml not found",
            fix="Run: evalflow init"
        )
    
    try:
        raw = yaml.safe_load(path.read_text())  # safe_load per security.md
    except yaml.YAMLError as e:
        raise ConfigError(
            "evalflow.yaml is not valid YAML",
            fix=f"Check line {e.problem_mark.line + 1}: {e.problem}"
        )
    
    if raw is None:
        raise ConfigError(
            "evalflow.yaml is empty",
            fix="Run: evalflow init to create a fresh config"
        )
    
    try:
        return cls.model_validate(raw)
    except ValidationError as e:
        # Convert Pydantic errors to human-readable messages
        first_error = e.errors()[0]
        field = " → ".join(str(loc) for loc in first_error["loc"])
        raise ConfigError(
            f"evalflow.yaml invalid field: {field}",
            fix=f"{first_error['msg']}"
        )

Update ConfigError to carry both title and fix:
class ConfigError(EvalflowError):
    def __init__(self, message: str, fix: str = ""):
        self.message = message
        self.fix = fix

Update eval_command to display ConfigError properly using print_error().

Create a config validation command accessible as `evalflow doctor --validate-config`:
- Validates yaml syntax
- Validates all fields
- Checks provider API keys present
- Reports specific line numbers for issues

Write tests covering: missing file, empty file, invalid YAML, missing required fields, invalid field values.
```

---

## PROMPT 21 — Dataset validation and helpful dataset errors

```
Read context.md section: "Dataset Format".

Enhance packages/cli/evalflow/models/dataset.py with comprehensive validation.

Add to Dataset class:

@classmethod
def from_json(cls, path: Path) -> "Dataset":
    """Load and validate dataset with helpful errors."""
    if not path.exists():
        raise DatasetError(
            f"Dataset not found: {path}",
            fix="Create evals/dataset.json or run: evalflow init"
        )
    
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise DatasetError(
            f"dataset.json is not valid JSON",
            fix=f"Syntax error at line {e.lineno}: {e.msg}"
        )
    
    # Validate version
    if "version" not in raw:
        raise DatasetError("Missing 'version' field in dataset.json", fix='Add: "version": "1.0"')
    
    # Validate test_cases present and non-empty
    if not raw.get("test_cases"):
        raise DatasetError(
            "No test cases found in dataset.json",
            fix="Add at least one test case to the test_cases array"
        )
    
    # Check for duplicate IDs
    ids = [tc.get("id") for tc in raw.get("test_cases", [])]
    duplicates = [id for id in ids if ids.count(id) > 1]
    if duplicates:
        raise DatasetError(
            f"Duplicate test case IDs: {set(duplicates)}",
            fix="Each test case must have a unique 'id' field"
        )
    
    # Validate each test case
    for i, tc in enumerate(raw.get("test_cases", [])):
        if not tc.get("id"):
            raise DatasetError(f"Test case #{i+1} missing 'id' field")
        if not tc.get("input"):
            raise DatasetError(f"Test case '{tc.get('id')}' missing 'input' field")
        if not tc.get("expected_output"):
            raise DatasetError(f"Test case '{tc.get('id')}' missing 'expected_output' field")
    
    return cls.model_validate(raw)

Add a lint command: `evalflow dataset lint [path]`
- Checks all validation rules
- Also checks: are IDs kebab-case?, are inputs non-empty?, are expected outputs reasonable length?
- Outputs per-test-case checklist

Add dataset hash computation:
def compute_hash(self) -> str:
    """SHA-256 of dataset content for run tracking."""
```

---

## PROMPT 22 — Full test suite

```
Read testing.md for all test requirements.
Read context.md for expected behavior of each component.

Create a comprehensive test suite in packages/cli/tests/:

Directory structure:
tests/
├── conftest.py              # Shared fixtures
├── test_models.py           # Pydantic model tests
├── test_storage.py          # SQLite and cache tests
├── test_eval_methods.py     # Exact match, embedding, consistency, judge
├── test_evaluator.py        # EvalOrchestrator integration tests
├── test_providers.py        # Provider mock tests
├── test_commands.py         # CLI command tests (using Typer test client)
├── test_registry.py         # Prompt registry tests
└── fixtures/
    ├── sample_config.yaml
    ├── sample_dataset.json
    └── sample_prompt.yaml

conftest.py must provide:
- tmp_project_dir fixture: creates a temp dir with valid evalflow.yaml + dataset.json
- mock_provider fixture: returns a MockProvider that returns predetermined responses
- sample_run fixture: a pre-built EvalRun for testing output functions

Test coverage requirements (from testing.md):
- All CLI commands: ≥80% line coverage
- Eval methods: 100% line coverage (they're pure functions)
- Storage: ≥90% coverage
- Models: 100% coverage (validation logic)

Key test cases to cover:
1. evalflow eval exits 0 on PASS, 1 on FAIL, 2 on error
2. Config error produces correct error message (no traceback)
3. Missing API key produces correct message with fix
4. Baseline is saved on first run
5. Regression detected when score drops
6. --offline uses cache, skips uncached test cases
7. Run IDs are deterministic for same input
8. Prompt promotion updates YAML file correctly
9. Dataset validation catches all error types
10. doctor returns correct ✓/✗ for each check

Run all tests: pytest packages/cli/tests/ -v --tb=short
All tests must pass. No skipped tests without documented reason.
```

---

## PROMPT 23 — Error handling hardening pass

```
Read context.md section: "Error Message Standards".
Read security.md section: "Error Message Security".

This prompt hardens all error paths in the codebase.

Audit every command file (init.py, eval.py, doctor.py, runs.py, prompt.py):

1. Every function that can fail must have try/except
2. Every except block must call print_error() — never print() a traceback
3. Every ConfigError, DatasetError, ProviderError, StorageError must be caught at the command level
4. Unknown exceptions caught as last resort:
   if debug:
       console.print_exception()
   else:
       print_error("An unexpected error occurred", "Run with --debug for details")
   sys.exit(2)

Verify these specific error paths work correctly:

Test manually:
- Delete evalflow.yaml → run evalflow eval → should show: "✗ evalflow.yaml not found\n  Run: evalflow init"
- Set wrong API key → run evalflow eval → should show provider error with fix
- Corrupt dataset.json → run evalflow eval → should show exact JSON error location  
- Run evalflow eval with no internet + no cache → should show clear offline error
- Run evalflow compare with invalid run IDs → "Run ID not found: xyz"
- Run evalflow prompt promote to invalid target → "Invalid target. Use: staging or production"

Create a dedicated integration test file: tests/test_error_paths.py
Test each error path above using Typer's test runner.
Verify: exit codes are correct, no stack traces in output, messages match error format from design.md.

Also verify: running any command in a directory without evalflow.yaml gives:
"✗ Not an evalflow project
  Run: evalflow init"
```

---

## PROMPT 24 — Package finalization and PyPI readiness

```
Read context.md section: "Launch Checklist — Code complete".

Finalize the package for PyPI publication:

Update packages/cli/pyproject.toml with complete metadata:
[project]
name = "evalflow"
version = "0.1.0"
description = "pytest for LLMs — catch prompt regressions before they reach production"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
keywords = ["llm", "testing", "ai", "quality", "ci", "evaluation", "prompts"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Testing",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]
[project.urls]
Homepage = "https://evalflow.dev"
Documentation = "https://evalflow.dev/docs"
Repository = "https://github.com/emartai/evalflow"
Issues = "https://github.com/emartai/evalflow/issues"
Changelog = "https://github.com/emartai/evalflow/blob/main/CHANGELOG.md"

Create LICENSE (MIT):
Copyright (c) 2026 evalflow

Create CHANGELOG.md:
## [0.1.0] - 2026-xx-xx
### Added
- evalflow eval: run LLM quality gates in CI
- evalflow init: project setup wizard
- evalflow doctor: system diagnostics
- evalflow runs: local run history
- evalflow compare: diff two runs
- evalflow prompt: version control for prompts
- Support for OpenAI, Anthropic, Groq, Gemini, Ollama
- GitHub Actions CI integration
- Offline mode with response caching

Create CONTRIBUTING.md:
- How to set up dev environment (uv sync)
- How to run tests (pytest)
- Commit message format
- PR checklist

Run final checks:
- uv build → wheel and sdist created
- pip install dist/*.whl in fresh venv → evalflow --help works
- evalflow --version shows 0.1.0
- All imports resolve correctly
```

---

## PROMPT 25 — End-to-end smoke test script

```
Create a comprehensive end-to-end smoke test that simulates a real user's first session.

Create scripts/smoke_test.sh:

#!/bin/bash
set -e

echo "=== evalflow smoke test ==="

# Create temp directory
TMPDIR=$(mktemp -d)
cd $TMPDIR

# Install evalflow
pip install evalflow

# Test --version
evalflow --version

# Test --help
evalflow --help

# Test init
evalflow init --provider groq --model llama-3.1-8b-instant --non-interactive

# Test doctor (without API key)
evalflow doctor || true  # Should show ✗ for API key but not crash

# Set API key (use real GROQ_API_KEY from environment)
if [ -z "$GROQ_API_KEY" ]; then
    echo "GROQ_API_KEY not set — skipping live eval test"
else
    # Test eval
    evalflow eval --provider groq
    
    # Test runs
    evalflow runs
    
    # Test doctor with key
    evalflow doctor
fi

# Test prompt commands (no API key needed)
evalflow prompt create test-prompt
evalflow prompt list

# Cleanup
cd -
rm -rf $TMPDIR

echo "=== Smoke test passed ==="

Create scripts/smoke_test_offline.sh:
Same flow but with --offline flag, using pre-cached responses.
Tests that offline mode works without any API key.

Create a Python smoke test: scripts/smoke_test.py
Uses subprocess to run each command and asserts:
- Exit code is correct
- Output contains expected strings
- No Python tracebacks in output

This should be runnable in CI as: python scripts/smoke_test.py
```

---

## PROMPT 26 — `evalflow init` non-interactive mode for CI

```
Read context.md — evalflow init must work in CI environments where there's no terminal.

Update packages/cli/evalflow/commands/init.py to support non-interactive mode:

@app.command("init")
def init_command(
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM provider"),
    model: Optional[str] = typer.Option(None, "--model", help="Model name"),
    non_interactive: bool = typer.Option(False, "--non-interactive", "--yes", "-y"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
):

Non-interactive mode:
- If --provider not specified, defaults to "openai"
- If --model not specified, uses provider default
- Skips all confirmation prompts
- Creates all files without asking
- Used in: CI environments, Docker containers, scripted setups

Interactive mode (default):
- Detects if running in a terminal (sys.stdin.isatty())
- If NOT a terminal and --non-interactive not set:
  print warning: "! No terminal detected. Use: evalflow init --non-interactive"
  sys.exit(2)

Add provider default models mapping:
PROVIDER_DEFAULTS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "groq": "llama-3.1-8b-instant",
    "gemini": "gemini-1.5-flash",
    "ollama": "llama3.2",
}

Update smoke_test.sh to use --non-interactive.

Update docs/quickstart.mdx to show both interactive and non-interactive modes.

Also: add evalflow init --list-providers flag that shows all supported providers with their default models. No files written, just prints the table.
```

---

## PROMPT 27 — Complete docstrings and CLI help text

```
Read design.md. Every user-facing string must match the design system.

Go through every command and function in the codebase and add/improve:

1. Typer command docstrings (become `evalflow <command> --help` text):
   - Each command: one-sentence description
   - Each option: clear description with default
   - Example in docstring where helpful

2. Module-level docstrings for all files

3. Function docstrings for all public functions

4. Inline comments for non-obvious logic (eval scoring, hash computation, etc.)

Verify `evalflow --help` output matches design.md style:
\```
> evalflow

  pytest for LLMs — catch prompt regressions before they reach production.

Options:
  --version  -v  Show version
  --help         Show this message and exit.

Commands:
  init      Set up evalflow in your project
  eval      Run the LLM quality gate
  doctor    Check your evalflow setup
  runs      List recent eval runs
  compare   Compare two eval runs
  prompt    Manage prompt versions
\```

Verify `evalflow eval --help`:
\```
Usage: evalflow eval [OPTIONS]

  Run the LLM quality gate against your dataset.

  Exits 0 on pass, 1 on quality failure (blocks CI), 2 on error.

Options:
  --provider   -p  LLM provider [openai|anthropic|groq|gemini|ollama]
  --model      -m  Model to use (overrides config)
  --dataset    -d  Path to dataset JSON [default: evals/dataset.json]
  --tag        -t  Run only test cases with this tag
  --offline        Use cached responses (no API calls)
  --debug          Show full error details
  --save-baseline  Save this run as the new baseline
  --help           Show this message and exit.
\```

Fix any help text that uses marketing language or buzzwords.
All help text should be factual, concise, lowercase where appropriate.
```

---

## PROMPT 28 — Final security audit

```
Read security.md fully.

Perform a final security audit pass on the entire codebase:

1. API key audit:
   - grep -r "api_key" across all .py files
   - Verify every occurrence is reading from env, not storing
   - Verify no key values appear in any test fixtures
   - Verify no key values in any default config templates

2. YAML safety audit:
   - grep -r "yaml.load(" across all .py files
   - Every occurrence must be yaml.safe_load()
   - Fix any violations

3. SQL injection audit:
   - grep -r "f\"" across storage/db.py
   - Every SQL query must use ? parameterized form
   - Fix any violations

4. Rich markup injection audit:
   - grep -r "console.print(" across all .py files
   - Every place that renders user/LLM content must use escape()
   - Fix any violations

5. Path traversal audit:
   - Find every place a user-supplied path is used
   - Verify safe_resolve() is called
   - Fix any violations

6. HTTP security audit:
   - grep -r "verify=False" — must be zero results
   - grep -r "http://" — must be zero results in provider calls
   - Verify timeout is set on all httpx calls

7. .gitignore audit:
   - Verify evalflow init creates correct .gitignore entries
   - Verify .evalflow/ is in .gitignore
   - Verify .env is in .gitignore

8. Test data audit:
   - No real API keys in test fixtures
   - No real user data in test fixtures
   - All test secrets are clearly fake (e.g., "sk-fake-key-for-testing")

Create security/audit_report.md documenting:
- What was checked
- What was found
- What was fixed
- Remaining known limitations

This file should be committed to the repo.
```

---

## PROMPT 29 — Performance and usability polish

```
This prompt is about making evalflow feel fast and professional.

1. Startup time optimization:
   - Profile: python -c "import evalflow; evalflow.main.app()"
   - Target: evalflow --help should respond in <500ms
   - Lazy-load sentence-transformers (only when embedding method is used)
   - Lazy-load provider SDKs (only when that provider is used)
   - Use importlib for deferred imports

2. Progress feedback:
   - Progress bar must update in real-time as each test case completes
   - Show currently running test case name
   - Show elapsed time
   - Never show a blank screen for >2 seconds

3. Concurrent eval runs:
   - Test cases should run concurrently (asyncio.gather)
   - Default concurrency: 5 parallel test cases
   - Add --concurrency flag to eval command
   - Order of output must match input order (collect results, print in order)

4. Large dataset handling:
   - Test with 100 test cases
   - Verify memory usage stays reasonable
   - Progress bar should work correctly at scale

5. First-run experience:
   - First time sentence-transformers model downloads: show clear progress
     "Downloading embedding model (80MB, one-time)..."
   - Model cached in .evalflow/models/ after first download

6. evalflow doctor speed:
   - Should complete in <3 seconds
   - Provider health checks are slow — only run with --check-providers flag
   - Default doctor run skips live API calls

7. Colored diff in compare:
   - Score improved (green) vs degraded (red) vs unchanged (no color)
   - Highlight test cases that changed pass/fail status
   - Show clear winner at bottom

Run the smoke test and measure actual timing. Document in CONTRIBUTING.md.
```

---

## PROMPT 30 — Launch readiness final check

```
Read context.md section: "Launch Checklist" fully.

This is the final prompt. Go through every item in the launch checklist and verify it's done.

Create scripts/launch_check.py that programmatically verifies:

1. Package structure:
   - All required files exist
   - pyproject.toml has complete metadata
   - LICENSE exists
   - CHANGELOG.md exists
   - README.md exists and is >100 lines
   - README.md contains: pip install evalflow, terminal screenshot, GitHub Actions workflow

2. CLI commands:
   - evalflow --version works
   - evalflow --help works  
   - evalflow init --non-interactive works in empty directory
   - evalflow doctor works
   - evalflow eval --help works

3. Examples:
   - examples/openai-basic/ has README.md, evalflow.yaml, evals/dataset.json
   - examples/groq-ci/ has README.md, .github/workflows/evalflow.yml
   - examples/langchain-app/ has README.md, app.py

4. Documentation:
   - docs/mint.json valid JSON
   - docs/quickstart.mdx exists
   - docs/cli-reference.mdx exists
   - docs/ci-github-actions.mdx exists

5. Tests:
   - pytest packages/cli/tests/ exits 0
   - Coverage report generated

6. Security:
   - No API keys in codebase (grep check)
   - All yaml.load calls use safe_load
   - security/audit_report.md exists

7. Build:
   - uv build completes without errors
   - Wheel can be installed: pip install dist/*.whl

8. Final install test:
   - In fresh virtualenv: pip install dist/*.whl
   - evalflow --version returns 0.1.0
   - evalflow init --non-interactive works
   - evalflow doctor runs without crash

Output: a report of all checks with ✓/✗.
All ✗ items must be fixed before launch.

After all checks pass, create a git tag:
git tag v0.1.0
git push origin v0.1.0

This triggers the publish.yml workflow which publishes to PyPI.
evalflow is live.
```

---

## Build order summary

| Prompts | What gets built | Output |
|---|---|---|
| 1-2 | Repo scaffold + all Pydantic models | Compiles, imports work |
| 3-4 | Storage layer + BaseProvider + OpenAI | Tests pass |
| 5-7 | All providers + eval methods | All providers work with mocks |
| 8-9 | Eval orchestrator + Rich output | `evalflow eval` runs end-to-end |
| 10-12 | init, eval, doctor commands | Core CLI works |
| 13-15 | runs, compare, prompt, main wiring | Full CLI wired up |
| 16-17 | CI files + documentation | Docs site ready |
| 18 | README | Marketing ready |
| 19-21 | Offline mode + error hardening + dataset validation | Production quality |
| 22-23 | Full test suite + error path tests | ≥80% coverage |
| 24-25 | PyPI packaging + smoke tests | Publishable |
| 26-27 | Non-interactive init + docstrings | CI-ready, polished |
| 28-30 | Security audit + performance + launch check | Launch ready |

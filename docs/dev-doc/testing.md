# testing.md — evalflow Test Requirements

## Philosophy

Tests in evalflow serve two purposes:
1. Catch regressions when the codebase changes
2. Document the expected behavior of each module

Tests must be **fast** (full suite under 30 seconds without network calls), **isolated** (no shared state between tests), and **readable** (test names explain what they test).

---

## Test Stack

```
pytest >= 8.0
pytest-asyncio >= 0.23
pytest-cov >= 5.0
httpx[mock] >= 0.27  # for mocking provider HTTP calls
```

All in `pyproject.toml` under `[project.optional-dependencies] dev`.

---

## Coverage Requirements

| Module | Min Coverage |
|---|---|
| `models/` | 100% |
| `engine/methods/` | 100% |
| `engine/evaluator.py` | 85% |
| `engine/providers/` | 80% |
| `storage/` | 90% |
| `registry/` | 90% |
| `commands/` | 80% |
| `output/` | 70% (visual output is hard to test) |
| Overall | ≥ 82% |

Run coverage: `pytest --cov=evalflow --cov-report=term-missing`

---

## Test Fixtures (conftest.py)

### `tmp_project_dir` fixture
```python
@pytest.fixture
def tmp_project_dir(tmp_path):
    """
    Creates a complete valid evalflow project in a temp directory.
    Includes: evalflow.yaml, evals/dataset.json, prompts/, .evalflow/
    """
    config = {
        "version": "1.0",
        "project": "test-project",
        "providers": {
            "openai": {"api_key_env": "OPENAI_API_KEY", "default_model": "gpt-4o-mini"}
        },
        "eval": {"dataset": "evals/dataset.json", "default_provider": "openai"},
        "thresholds": {"task_success": 0.80}
    }
    (tmp_path / "evalflow.yaml").write_text(yaml.dump(config))
    
    dataset = {
        "version": "1.0",
        "test_cases": [
            {
                "id": "test-summarize",
                "description": "Test summarization",
                "task_type": "summarization",
                "input": "Summarize: The cat sat on the mat.",
                "expected_output": "A cat sat on a mat.",
                "context": "",
                "tags": ["smoke"],
                "eval_config": {"methods": ["embedding_similarity"], "judge": False, "weight": 1.0}
            }
        ]
    }
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "dataset.json").write_text(json.dumps(dataset))
    (tmp_path / "prompts").mkdir()
    (tmp_path / ".evalflow").mkdir()
    
    return tmp_path
```

### `mock_provider` fixture
```python
@pytest.fixture
def mock_provider():
    """Provider that returns predetermined responses without network calls."""
    
    class MockProvider(BaseProvider):
        def __init__(self, responses: list[str] = None):
            self.responses = responses or ["Mock response for testing."]
            self.call_count = 0
            self.last_prompt = None
        
        async def complete(self, prompt: str, config: ProviderConfig) -> ProviderResponse:
            self.last_prompt = prompt
            response = self.responses[self.call_count % len(self.responses)]
            self.call_count += 1
            return ProviderResponse(
                content=response,
                model=config.model,
                prompt_tokens=10,
                completion_tokens=20,
                latency_ms=50.0
            )
        
        async def health_check(self) -> bool:
            return True
        
        @classmethod
        def provider_name(cls) -> str:
            return "mock"
    
    return MockProvider
```

### `sample_dataset` fixture
```python
@pytest.fixture
def sample_dataset():
    return Dataset(
        version="1.0",
        test_cases=[
            TestCase(
                id="test-1",
                description="Test 1",
                task_type=TaskType.summarization,
                input="Input text",
                expected_output="Expected output",
                tags=["smoke"],
                eval_config=EvalCaseConfig(methods=[EvalMethod.embedding_similarity])
            )
        ]
    )
```

### `run_cli` helper
```python
from typer.testing import CliRunner

runner = CliRunner()

def run_cli(args: list[str], env: dict = None, input: str = None):
    """Run a CLI command and return (exit_code, output)."""
    result = runner.invoke(app, args, env=env or {}, input=input, catch_exceptions=False)
    return result.exit_code, result.output
```

---

## Unit Tests: Models

### `test_models.py`

```python
class TestEvalflowConfig:
    def test_load_valid_yaml(self, tmp_path):
        """Config loads successfully from valid YAML."""
    
    def test_missing_file_raises_config_error(self, tmp_path):
        """Missing file raises ConfigError with helpful message."""
    
    def test_invalid_yaml_raises_config_error(self, tmp_path):
        """Invalid YAML syntax raises ConfigError with line number."""
    
    def test_empty_file_raises_config_error(self, tmp_path):
        """Empty file raises ConfigError with fix."""
    
    def test_provider_api_key_env_not_stored(self, tmp_path):
        """Config stores env var name, never key value."""
    
    def test_defaults_applied(self):
        """Optional fields get correct defaults."""

class TestDataset:
    def test_load_valid_json(self, tmp_path):
        """Dataset loads from valid JSON."""
    
    def test_missing_file_raises_dataset_error(self, tmp_path):
        """Missing file raises DatasetError."""
    
    def test_invalid_json_raises_dataset_error(self, tmp_path):
        """Invalid JSON raises DatasetError with line number."""
    
    def test_empty_test_cases_raises_error(self, tmp_path):
        """Empty test_cases list raises DatasetError."""
    
    def test_duplicate_ids_raises_error(self, tmp_path):
        """Duplicate test case IDs raise DatasetError."""
    
    def test_missing_required_fields_raises_error(self, tmp_path):
        """Test case missing 'input' raises DatasetError."""
    
    def test_tag_filtering(self, sample_dataset):
        """Dataset.filter_by_tag() returns only matching test cases."""
    
    def test_compute_hash_deterministic(self, sample_dataset):
        """Same dataset always produces same hash."""
    
    def test_compute_hash_changes_on_modification(self, sample_dataset):
        """Modified dataset produces different hash."""

class TestPromptVersion:
    def test_status_values(self):
        """Status must be draft, staging, or production."""
    
    def test_version_must_be_positive(self):
        """Version < 1 raises validation error."""
```

---

## Unit Tests: Eval Methods

### `test_eval_methods.py`

All tests are synchronous for exact_match and embedding, async for consistency and judge.

```python
class TestExactMatch:
    def test_exact_match_returns_1(self):
        result = ExactMatchEvaluator().evaluate("hello world", "hello world")
        assert result == 1.0
    
    def test_case_insensitive(self):
        result = ExactMatchEvaluator().evaluate("Hello", "hello")
        assert result == 1.0
    
    def test_whitespace_normalized(self):
        result = ExactMatchEvaluator().evaluate("hello  world", "hello world")
        assert result == 1.0
    
    def test_no_match_returns_0(self):
        result = ExactMatchEvaluator().evaluate("completely different", "text here")
        assert result == 0.0
    
    def test_empty_strings(self):
        """Both empty = match, one empty = no match."""
    
    def test_score_between_0_and_1(self):
        """All scores must be in [0, 1] range."""


class TestEmbeddingSimilarity:
    @patch("sentence_transformers.SentenceTransformer")
    def test_similar_returns_high_score(self, mock_st):
        """Semantically similar texts score > 0.8."""
        # Mock the model to return controlled embeddings
    
    @patch("sentence_transformers.SentenceTransformer")
    def test_different_returns_low_score(self, mock_st):
        """Semantically different texts score < 0.5."""
    
    def test_lazy_loads_model(self):
        """Model not loaded until first evaluate() call."""
    
    def test_import_error_raises_helpful_message(self):
        """Missing sentence-transformers gives actionable error."""
    
    def test_is_available_without_package(self):
        """is_available() returns False when not installed."""


class TestConsistency:
    @pytest.mark.asyncio
    async def test_identical_responses_score_1(self, mock_provider):
        """Provider returning same response each time → score near 1.0."""
        provider = mock_provider(responses=["Same response"] * 5)
        score = await ConsistencyEvaluator().evaluate("test", provider, config, runs=3)
        assert score > 0.95
    
    @pytest.mark.asyncio
    async def test_varied_responses_lower_score(self, mock_provider):
        """Provider returning different responses → score < 0.8."""
    
    @pytest.mark.asyncio
    async def test_runs_correct_number_of_times(self, mock_provider):
        """Runs exactly N times as configured."""
        provider = mock_provider()
        await ConsistencyEvaluator().evaluate("test", provider, config, runs=3)
        assert provider.call_count == 3


class TestLLMJudge:
    @pytest.mark.asyncio
    async def test_valid_json_response_parsed(self, mock_provider):
        """Valid judge JSON response parsed correctly."""
        provider = mock_provider(responses=['{"score": 0.9, "grounded": true, "reasoning": "Good"}'])
        result = await LLMJudgeEvaluator(provider, config).evaluate(...)
        assert result.score == 0.9
        assert result.grounded is True
    
    @pytest.mark.asyncio
    async def test_invalid_json_returns_error_result(self, mock_provider):
        """Invalid JSON doesn't crash — returns error JudgeResult."""
        provider = mock_provider(responses=["not valid json"])
        result = await LLMJudgeEvaluator(provider, config).evaluate(...)
        assert result.error is not None
        assert 0 <= result.score <= 1  # Fallback score
    
    @pytest.mark.asyncio
    async def test_score_clamped_to_range(self, mock_provider):
        """Score values outside [0,1] are clamped."""
```

---

## Integration Tests: Storage

### `test_storage.py`

```python
class TestEvalflowDB:
    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, tmp_path):
        """initialize() creates all required tables."""
        async with EvalflowDB(tmp_path / "test.db") as db:
            await db.initialize()
        # Verify tables exist
    
    @pytest.mark.asyncio
    async def test_save_and_retrieve_run(self, tmp_path, sample_run):
        """Run saved can be retrieved with same data."""
    
    @pytest.mark.asyncio
    async def test_list_runs_limit(self, tmp_path):
        """list_runs(limit=5) returns at most 5 runs."""
    
    @pytest.mark.asyncio
    async def test_list_runs_failed_only(self, tmp_path):
        """list_runs(failed_only=True) returns only failed runs."""
    
    @pytest.mark.asyncio
    async def test_baseline_save_and_retrieve(self, tmp_path, sample_run):
        """Baseline saved for dataset hash can be retrieved."""
    
    @pytest.mark.asyncio
    async def test_baseline_returns_latest(self, tmp_path):
        """Multiple baselines for same hash → returns most recent."""
    
    @pytest.mark.asyncio
    async def test_sql_injection_prevented(self, tmp_path):
        """Run ID with SQL metacharacters handled safely."""
    
    @pytest.mark.asyncio
    async def test_file_permissions_600(self, tmp_path):
        """DB file created with 600 permissions."""


class TestResponseCache:
    def test_cache_hit(self, tmp_path):
        cache = ResponseCache(tmp_path)
        cache.set("openai", "gpt-4o-mini", "test prompt", "cached response")
        result = cache.get("openai", "gpt-4o-mini", "test prompt")
        assert result == "cached response"
    
    def test_cache_miss_returns_none(self, tmp_path):
        cache = ResponseCache(tmp_path)
        assert cache.get("openai", "gpt-4o", "unknown prompt") is None
    
    def test_key_is_deterministic(self, tmp_path):
        """Same inputs always produce same cache key."""
    
    def test_different_models_different_keys(self, tmp_path):
        """gpt-4o and gpt-4o-mini are cached separately."""
    
    def test_clear_removes_all_entries(self, tmp_path):
        cache = ResponseCache(tmp_path)
        cache.set("openai", "gpt-4o-mini", "prompt", "response")
        cache.clear()
        assert cache.get("openai", "gpt-4o-mini", "prompt") is None
```

---

## Integration Tests: Evaluator

### `test_evaluator.py`

```python
class TestEvalOrchestrator:
    @pytest.mark.asyncio
    async def test_basic_eval_run(self, tmp_project_dir, mock_provider):
        """Full eval run produces EvalRun with correct structure."""
        provider_cls = mock_provider(responses=["The cat sat on the mat."])
        # ... setup and run
        assert isinstance(run, EvalRun)
        assert len(run.results) == 1
        assert run.status in [RunStatus.pass_, RunStatus.fail]
    
    @pytest.mark.asyncio
    async def test_run_id_format(self, tmp_project_dir, mock_provider):
        """Run ID matches YYYYMMDD-<12-char-hash> format."""
        import re
        assert re.match(r"\d{8}-[a-f0-9]{12}", run.id)
    
    @pytest.mark.asyncio
    async def test_run_id_deterministic(self, tmp_project_dir, mock_provider):
        """Same inputs produce same run ID."""
    
    @pytest.mark.asyncio
    async def test_baseline_saved_on_first_run(self, tmp_project_dir, mock_provider):
        """First run saves baseline to SQLite."""
    
    @pytest.mark.asyncio
    async def test_regression_detected(self, tmp_project_dir, mock_provider):
        """Score drop vs baseline produces regression indicator."""
    
    @pytest.mark.asyncio
    async def test_offline_uses_cache(self, tmp_project_dir, mock_provider):
        """--offline mode uses cached responses, doesn't call provider."""
        # First run online to populate cache
        # Second run offline — provider.call_count should not increase
    
    @pytest.mark.asyncio
    async def test_offline_skips_uncached(self, tmp_project_dir, mock_provider):
        """Uncached test cases in offline mode are skipped with warning."""
    
    @pytest.mark.asyncio
    async def test_tag_filtering(self, tmp_project_dir, mock_provider):
        """--tag flag runs only matching test cases."""
    
    @pytest.mark.asyncio
    async def test_concurrent_execution(self, tmp_project_dir, mock_provider):
        """Multiple test cases run concurrently."""
    
    @pytest.mark.asyncio
    async def test_provider_error_handled(self, tmp_project_dir):
        """Provider error produces failed test case, not crash."""
```

---

## Integration Tests: CLI Commands

### `test_commands.py`

```python
class TestEvalCommand:
    def test_exits_0_on_pass(self, tmp_project_dir, mock_provider):
        exit_code, _ = run_cli(["eval"], env={"OPENAI_API_KEY": "fake-key"})
        assert exit_code == 0
    
    def test_exits_1_on_fail(self, tmp_project_dir, mock_provider_bad_response):
        """When score below threshold, exit code is 1."""
        exit_code, _ = run_cli(["eval"])
        assert exit_code == 1
    
    def test_exits_2_on_missing_config(self, tmp_path):
        """Missing evalflow.yaml → exit 2."""
        exit_code, output = run_cli(["eval"])
        assert exit_code == 2
        assert "evalflow.yaml not found" in output
        assert "evalflow init" in output
        # No stack trace
        assert "Traceback" not in output
    
    def test_exits_2_on_missing_api_key(self, tmp_project_dir):
        """Missing API key → exit 2 with helpful message."""
        exit_code, output = run_cli(["eval"], env={})  # No API key
        assert exit_code == 2
        assert "OPENAI_API_KEY" in output
        assert "Traceback" not in output
    
    def test_output_matches_design(self, tmp_project_dir, mock_provider):
        """Output format matches design.md spec."""
        _, output = run_cli(["eval"], env={"OPENAI_API_KEY": "fake"})
        assert "Running" in output
        assert "Quality Gate:" in output
        assert "Run ID:" in output


class TestInitCommand:
    def test_creates_required_files(self, tmp_path):
        run_cli(["init", "--non-interactive", "--provider", "openai"])
        assert (tmp_path / "evalflow.yaml").exists()
        assert (tmp_path / "evals" / "dataset.json").exists()
        assert (tmp_path / "prompts").exists()
        assert (tmp_path / ".env.example").exists()
    
    def test_adds_gitignore_entries(self, tmp_path):
        run_cli(["init", "--non-interactive"])
        gitignore = (tmp_path / ".gitignore").read_text()
        assert ".env" in gitignore
        assert ".evalflow/" in gitignore
    
    def test_does_not_overwrite_without_force(self, tmp_project_dir):
        """Existing evalflow.yaml not overwritten without --force."""
    
    def test_api_key_not_written_to_yaml(self, tmp_path):
        """Even if user provides key, it's not written to evalflow.yaml."""
        run_cli(["init", "--non-interactive"])
        yaml_content = (tmp_path / "evalflow.yaml").read_text()
        assert "sk-" not in yaml_content  # No real key format in file


class TestDoctorCommand:
    def test_shows_checkmarks_for_valid_setup(self, tmp_project_dir):
        _, output = run_cli(["doctor"], env={"OPENAI_API_KEY": "fake"})
        assert "✓" in output
    
    def test_shows_x_for_missing_api_key(self, tmp_project_dir):
        _, output = run_cli(["doctor"], env={})
        assert "✗" in output
        assert "OPENAI_API_KEY" in output
    
    def test_exits_0_even_with_issues(self, tmp_project_dir):
        """doctor always exits 0 — it reports, doesn't block."""
        exit_code, _ = run_cli(["doctor"], env={})
        assert exit_code == 0


class TestRunsCommand:
    def test_no_runs_shows_helpful_message(self, tmp_project_dir):
        _, output = run_cli(["runs"])
        assert "No runs found" in output
    
    def test_shows_runs_after_eval(self, tmp_project_dir, mock_provider):
        run_cli(["eval"], env={"OPENAI_API_KEY": "fake"})
        _, output = run_cli(["runs"])
        assert "openai" in output.lower()
```

---

## E2E Tests: Error Paths

### `test_error_paths.py`

These tests verify that every error produces the correct user-facing message with no stack trace.

```python
ERROR_SCENARIOS = [
    # (description, setup_fn, expected_output_contains, expected_exit_code)
    ("missing config", delete_config, "evalflow.yaml not found", 2),
    ("empty config", write_empty_config, "evalflow.yaml is empty", 2),
    ("invalid yaml", write_invalid_yaml, "not valid YAML", 2),
    ("missing dataset", delete_dataset, "Dataset not found", 2),
    ("invalid json", write_invalid_json, "not valid JSON", 2),
    ("empty test cases", write_empty_cases, "No test cases", 2),
    ("duplicate ids", write_duplicate_ids, "Duplicate test case IDs", 2),
    ("missing api key", clear_env, "OPENAI_API_KEY", 2),
    ("unknown provider", set_unknown_provider, "Unknown provider", 2),
]

@pytest.mark.parametrize("description,setup,expected,code", ERROR_SCENARIOS)
def test_error_path(description, setup, expected, code, tmp_project_dir):
    setup(tmp_project_dir)
    exit_code, output = run_cli(["eval"])
    assert exit_code == code, f"Expected exit {code}, got {exit_code}"
    assert expected in output, f"Expected '{expected}' in output"
    assert "Traceback" not in output, "Stack trace leaked to user"
    assert "Exception" not in output or "✗" in output  # Exception only in formatted error
```

---

## Performance Tests

### `test_performance.py`

```python
def test_help_responds_fast():
    """evalflow --help must respond in under 500ms."""
    import time
    import subprocess
    start = time.monotonic()
    subprocess.run(["evalflow", "--help"], capture_output=True)
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"Help took {elapsed:.2f}s — too slow"

def test_doctor_responds_fast():
    """evalflow doctor must complete in under 3 seconds."""

@pytest.mark.asyncio
async def test_eval_concurrency(tmp_project_dir, mock_provider):
    """10 test cases should complete faster than 10 × single_case_time."""
    # Measure single case time
    # Measure 10 cases time
    # 10 cases should take < 3× single case (concurrency working)
```

---

## CI Configuration

Add to `packages/cli/pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = [
    "--tb=short",
    "--strict-markers",
    "-q",
]
markers = [
    "slow: marks tests as slow (deselect with '-m not slow')",
    "integration: marks integration tests",
    "e2e: marks end-to-end tests",
]

[tool.coverage.run]
source = ["evalflow"]
omit = ["tests/*", "evalflow/output/*"]  # output module is hard to coverage-test

[tool.coverage.report]
fail_under = 82
show_missing = true
```

Run in CI: `pytest --cov=evalflow --cov-fail-under=82`

---

## What NOT to Test

- Don't test Rich's rendering (it changes between versions)
- Don't test Typer's built-in help formatting
- Don't test Pydantic's built-in validation (test our custom validators)
- Don't make real API calls in tests (always mock)
- Don't test SQLite internals (test our interface to it)
- Don't test third-party SDK behavior (they have their own tests)

#!/bin/bash
set -euo pipefail

echo "=== evalflow offline smoke test ==="

INSTALL_SOURCE="${EVALFLOW_SMOKE_INSTALL_SOURCE:-evalflow}"
PYTHON_BIN="${PYTHON_BIN:-python}"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

cd "$TMPDIR"

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8="1"

pip install "$INSTALL_SOURCE"

evalflow --version
evalflow --help
evalflow init --provider groq --model llama-3.1-8b-instant --non-interactive

python - <<'PY'
import json
from pathlib import Path

path = Path("evals/dataset.json")
payload = json.loads(path.read_text(encoding="utf-8"))
payload["test_cases"][0]["expected_output"] = "A fox jumps over a dog."
payload["test_cases"][0]["eval_config"]["methods"] = ["exact_match"]
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY

python - <<'PY'
from pathlib import Path
from evalflow.storage.cache import ResponseCache

cache = ResponseCache(Path(".evalflow"))
prompt = "Summarize in one sentence: The quick brown fox jumps over the lazy dog."
cache.set("groq", "llama-3.1-8b-instant", prompt, "A fox jumps over a dog.")
PY

evalflow eval --provider groq --model llama-3.1-8b-instant --offline
evalflow runs
evalflow doctor || true
evalflow prompt create test-prompt
evalflow prompt list

echo "=== Offline smoke test passed ==="

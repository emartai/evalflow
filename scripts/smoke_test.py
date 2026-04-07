"""End-to-end smoke test for a first-time evalflow session."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}".strip()
    if "Traceback" in combined:
        raise AssertionError(f"Traceback detected for command: {' '.join(command)}\n{combined}")
    return result


def _assert_output_contains(result: subprocess.CompletedProcess[str], *needles: str) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    for needle in needles:
        if needle not in combined:
            raise AssertionError(f"Expected '{needle}' in output:\n{combined}")


def _install_source() -> str:
    value = os.environ.get("EVALFLOW_SMOKE_INSTALL_SOURCE", "evalflow")
    if value == "evalflow":
        return value
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (Path(__file__).resolve().parents[1] / candidate).resolve()
    return str(candidate)


def _python_bin() -> str:
    return os.environ.get("PYTHON_BIN", sys.executable)


def _reuse_current_env() -> bool:
    return os.environ.get("EVALFLOW_SMOKE_SKIP_INSTALL", "").lower() in {"1", "true", "yes"}


def _seed_offline_cache(venv_python: Path, cwd: Path) -> None:
    code = """
from pathlib import Path
from evalflow.storage.cache import ResponseCache

cache = ResponseCache(Path('.evalflow'))
prompt = 'Summarize in one sentence: The quick brown fox jumps over the lazy dog.'
cache.set('groq', 'llama-3.1-8b-instant', prompt, 'A fox jumps over a dog.')
"""
    result = subprocess.run(
        [str(venv_python), "-c", code],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"Failed to seed offline cache:\n{result.stdout}\n{result.stderr}")


def _rewrite_dataset_for_smoke(cwd: Path) -> None:
    path = cwd / "evals" / "dataset.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["test_cases"][0]["expected_output"] = "A fox jumps over a dog."
    payload["test_cases"][0]["eval_config"]["methods"] = ["exact_match"]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix="evalflow-smoke-"))
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        if _reuse_current_env():
            venv_python = Path(_python_bin())
            evalflow_bin = venv_python.with_name("evalflow.exe" if os.name == "nt" else "evalflow")
        else:
            venv_dir = tmpdir / ".venv"
            subprocess.run(
                [_python_bin(), "-m", "venv", str(venv_dir)],
                check=True,
                env=env,
            )
            venv_python = venv_dir / ("Scripts" if os.name == "nt" else "bin") / "python"
            evalflow_bin = venv_dir / ("Scripts" if os.name == "nt" else "bin") / "evalflow"

            install = _run([str(venv_python), "-m", "pip", "install", _install_source()], tmpdir, env)
            if install.returncode != 0:
                raise AssertionError(f"pip install failed:\n{install.stdout}\n{install.stderr}")

        version = _run([str(evalflow_bin), "--version"], tmpdir, env)
        assert version.returncode == 0
        _assert_output_contains(version, "> evalflow v0.1.3")

        help_result = _run([str(evalflow_bin), "--help"], tmpdir, env)
        assert help_result.returncode == 0
        _assert_output_contains(help_result, "pytest for LLMs", "init", "eval", "doctor")

        init_result = _run(
            [
                str(evalflow_bin),
                "init",
                "--provider",
                "groq",
                "--model",
                "llama-3.1-8b-instant",
                "--non-interactive",
            ],
            tmpdir,
            env,
        )
        assert init_result.returncode == 0
        _assert_output_contains(init_result, "evalflow initialized")
        _rewrite_dataset_for_smoke(tmpdir)

        doctor_without_key = _run([str(evalflow_bin), "doctor"], tmpdir, env)
        assert doctor_without_key.returncode == 0
        _assert_output_contains(doctor_without_key, "GROQ_API_KEY set", "issues found")

        prompt_create = _run([str(evalflow_bin), "prompt", "create", "test-prompt"], tmpdir, env)
        assert prompt_create.returncode == 0
        _assert_output_contains(prompt_create, "Created prompts/test-prompt.yaml")

        prompt_list = _run([str(evalflow_bin), "prompt", "list"], tmpdir, env)
        assert prompt_list.returncode == 0
        _assert_output_contains(prompt_list, "test-prompt")

        _seed_offline_cache(venv_python, tmpdir)

        offline_eval = _run(
            [
                str(evalflow_bin),
                "eval",
                "--provider",
                "groq",
                "--model",
                "llama-3.1-8b-instant",
                "--offline",
            ],
            tmpdir,
            env,
        )
        assert offline_eval.returncode == 0
        _assert_output_contains(offline_eval, "Quality Gate: PASS")

        runs_result = _run([str(evalflow_bin), "runs"], tmpdir, env)
        assert runs_result.returncode == 0
        _assert_output_contains(runs_result, "groq", "PASS")

        doctor_offline = _run([str(evalflow_bin), "doctor"], tmpdir, env)
        assert doctor_offline.returncode == 0
        _assert_output_contains(doctor_offline, "GROQ_API_KEY set")

        if env.get("GROQ_API_KEY"):
            live_eval = _run([str(evalflow_bin), "eval", "--provider", "groq"], tmpdir, env)
            if live_eval.returncode not in {0, 1}:
                raise AssertionError(f"Live eval failed unexpectedly:\n{live_eval.stdout}\n{live_eval.stderr}")
            _assert_output_contains(live_eval, "Quality Gate:")

        print("=== Smoke test passed ===")
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

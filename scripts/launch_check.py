"""Launch-readiness verification script for evalflow."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import tomllib


ROOT = Path(__file__).resolve().parents[1]
CLI_DIR = ROOT / "packages" / "cli"
PYPROJECT_PATH = CLI_DIR / "pyproject.toml"
README_PATH = ROOT / "README.md"
DIST_DIR = CLI_DIR / "dist"
TEMP_ROOT = ROOT / ".pytest-tmp"
REPORT_PATH = TEMP_ROOT / "launch-check-report.json"


def _configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


_configure_stdio()


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env["PYTHONUTF8"] = "1"
    merged_env["PYTHONIOENCODING"] = "utf-8"
    merged_env["TEMP"] = str(TEMP_ROOT)
    merged_env["TMP"] = str(TEMP_ROOT)
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
        env=merged_env,
    )


def _python_bin() -> Path:
    candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    if candidate.exists():
        return candidate
    return Path(sys.executable)


def _evalflow_bin() -> Path:
    if os.name == "nt":
        candidate = ROOT / ".venv" / "Scripts" / "evalflow.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "evalflow"
    if candidate.exists():
        return candidate
    return _python_bin()


def _cmd_evalflow(*args: str) -> list[str]:
    evalflow_bin = _evalflow_bin()
    if evalflow_bin.name.startswith("python"):
        return [str(evalflow_bin), "-m", "evalflow.main", *args]
    return [str(evalflow_bin), *args]


def _venv_python(venv_dir: Path) -> Path:
    """Return the Python executable path inside a virtual environment."""

    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _resolve_venv_evalflow_cmd(venv_dir: Path) -> list[str]:
    """Return the best command to run evalflow inside a virtual environment."""

    scripts_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    candidates = [
        scripts_dir / "evalflow.exe",
        scripts_dir / "evalflow",
        scripts_dir / "evalflow-script.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return [str(candidate)]
    return [str(_venv_python(venv_dir)), "-m", "evalflow.main"]


def _read_pyproject() -> dict:
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


def _report(results: list[CheckResult]) -> int:
    payload = [
        {"name": result.name, "ok": result.ok, "detail": result.detail}
        for result in results
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    for result in results:
        marker = "✓" if result.ok else "✗"
        print(f"{marker} {result.name}")
        if result.detail:
            print(f"  {result.detail}")

    failures = [result for result in results if not result.ok]
    print()
    if failures:
        print(f"✗ Launch check failed with {len(failures)} issue(s).")
        return 1

    print("✓ Launch check passed.")
    print(f"  Report written to {REPORT_PATH}")
    return 0


def _check(name: str, fn: Callable[[], str]) -> CheckResult:
    try:
        return CheckResult(name, True, fn())
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name, False, str(exc))


def _package_structure() -> str:
    required_files = [
        ROOT / "LICENSE",
        ROOT / "CHANGELOG.md",
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "security" / "audit_report.md",
        CLI_DIR / "pyproject.toml",
        CLI_DIR / "evalflow" / "main.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required_files if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing required files: {', '.join(missing)}")

    project = _read_pyproject()["project"]
    required_metadata = [
        "name",
        "version",
        "description",
        "readme",
        "license",
        "requires-python",
        "keywords",
        "classifiers",
        "urls",
    ]
    missing_metadata = [key for key in required_metadata if key not in project]
    if missing_metadata:
        raise RuntimeError(f"Missing pyproject metadata: {', '.join(missing_metadata)}")
    return "Required files and package metadata found."


def _readme_quality() -> str:
    text = README_PATH.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    if line_count <= 100:
        raise RuntimeError(f"README.md must be >100 lines, found {line_count}")
    for needle in ("pip install evalflow", "Terminal Screenshot", "GitHub Actions Workflow"):
        if needle not in text:
            raise RuntimeError(f"README.md missing required content: {needle}")
    return f"README.md is {line_count} lines and contains launch content."


def _examples_exist() -> str:
    required = [
        ROOT / "examples" / "openai-basic" / "README.md",
        ROOT / "examples" / "openai-basic" / "evalflow.yaml",
        ROOT / "examples" / "openai-basic" / "evals" / "dataset.json",
        ROOT / "examples" / "groq-ci" / "README.md",
        ROOT / "examples" / "groq-ci" / ".github" / "workflows" / "evalflow.yml",
        ROOT / "examples" / "langchain-app" / "README.md",
        ROOT / "examples" / "langchain-app" / "app.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing example files: {', '.join(missing)}")
    return "Example projects contain the required files."


def _docs_exist() -> str:
    mint = ROOT / "docs" / "mint.json"
    json.loads(mint.read_text(encoding="utf-8"))
    for relative in ("docs/quickstart.mdx", "docs/cli-reference.mdx", "docs/ci-github-actions.mdx"):
        path = ROOT / relative
        if not path.exists():
            raise RuntimeError(f"Missing documentation page: {relative}")
    return "Docs files exist and mint.json is valid JSON."


def _security_checks() -> str:
    py_files = list(ROOT.rglob("*.py"))
    forbidden_yaml_load = "yaml." + "load("
    yaml_load_violations = [
        str(path.relative_to(ROOT))
        for path in py_files
        if forbidden_yaml_load in path.read_text(encoding="utf-8", errors="ignore")
    ]
    if yaml_load_violations:
        raise RuntimeError(f"yaml.load found in: {', '.join(yaml_load_violations)}")

    secret_hits: list[str] = []
    secret_pattern = re.compile(r"\b(?:sk|AIza)[-_A-Za-z0-9]{12,}\b")
    allowed = {
        "sk-fake-key-for-testing",
        "sk-your-key-here",
    }
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if TEMP_ROOT in path.parents or ".venv" in path.parts or "dist" in path.parts:
            continue
        if path.suffix.lower() in {".db", ".pyc", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in secret_pattern.findall(text):
            if match not in allowed:
                secret_hits.append(f"{path.relative_to(ROOT)}:{match[:12]}...")
    if secret_hits:
        raise RuntimeError(f"Potential API keys found: {', '.join(secret_hits[:10])}")

    audit_report = ROOT / "security" / "audit_report.md"
    if not audit_report.exists():
        raise RuntimeError("security/audit_report.md is missing")
    return "No obvious API keys found, safe_load check passed, audit report exists."


def _build_distribution() -> str:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    uv_result: subprocess.CompletedProcess[str] | None = None
    try:
        uv_result = _run(["uv", "build"], cwd=ROOT, timeout=240)
    except FileNotFoundError:
        uv_result = None

    if uv_result is not None and uv_result.returncode == 0:
        return "uv build completed successfully."

    build_result = _run(
        [str(_python_bin()), "-m", "build", "packages/cli", "--no-isolation"],
        cwd=ROOT,
        timeout=240,
    )
    if build_result.returncode != 0:
        raise RuntimeError(
            "Build failed.\n"
            f"uv stderr:\n{uv_result.stderr if uv_result is not None else 'uv not installed'}\n"
            f"python -m build stderr:\n{build_result.stderr}"
        )
    return "uv not available locally; python -m build packages/cli --no-isolation succeeded."


def _wheel_exists() -> Path:
    wheels = sorted(DIST_DIR.glob("evalflow-*.whl"))
    if not wheels:
        raise RuntimeError("No wheel found in packages/cli/dist")
    return wheels[-1]


def _final_install_test() -> str:
    wheel = _wheel_exists()
    with tempfile.TemporaryDirectory(prefix="evalflow-launch-install-") as tmp:
        tmp_path = Path(tmp)
        venv_dir = tmp_path / ".venv"
        subprocess.run(
            [str(_python_bin()), "-m", "venv", "--system-site-packages", str(venv_dir)],
            check=True,
            cwd=ROOT,
        )
        python_bin = _venv_python(venv_dir)
        evalflow_cmd = _resolve_venv_evalflow_cmd(venv_dir)

        install = _run([str(python_bin), "-m", "pip", "install", str(wheel)], cwd=tmp_path, timeout=240)
        if install.returncode != 0:
            raise RuntimeError(f"pip install failed:\n{install.stdout}\n{install.stderr}")

        evalflow_cmd = _resolve_venv_evalflow_cmd(venv_dir)
        version = _run([*evalflow_cmd, "--version"], cwd=tmp_path)
        if version.returncode != 0 or "> evalflow v0.1.4" not in version.stdout:
            raise RuntimeError(f"Version check failed:\n{version.stdout}\n{version.stderr}")

        init = _run([*evalflow_cmd, "init", "--non-interactive"], cwd=tmp_path)
        if init.returncode != 0:
            raise RuntimeError(f"Init failed:\n{init.stdout}\n{init.stderr}")

        doctor = _run([*evalflow_cmd, "doctor"], cwd=tmp_path)
        if doctor.returncode != 0:
            raise RuntimeError(f"Doctor failed:\n{doctor.stdout}\n{doctor.stderr}")

    return "Wheel installs in a fresh system-site-packages venv and core CLI commands run."


def _cli_checks() -> str:
    version = _run(_cmd_evalflow("--version"))
    if version.returncode != 0 or "> evalflow v0.1.4" not in version.stdout:
        raise RuntimeError(f"--version failed:\n{version.stdout}\n{version.stderr}")

    help_result = _run(_cmd_evalflow("--help"))
    if help_result.returncode != 0 or "pytest for LLMs" not in help_result.stdout:
        raise RuntimeError(f"--help failed:\n{help_result.stdout}\n{help_result.stderr}")

    eval_help = _run(_cmd_evalflow("eval", "--help"))
    if eval_help.returncode != 0 or "Run the LLM quality gate against your dataset." not in eval_help.stdout:
        raise RuntimeError(f"eval --help failed:\n{eval_help.stdout}\n{eval_help.stderr}")

    with tempfile.TemporaryDirectory(prefix="evalflow-launch-cli-") as tmp:
        tmp_path = Path(tmp)
        init = _run(_cmd_evalflow("init", "--non-interactive"), cwd=tmp_path)
        if init.returncode != 0:
            raise RuntimeError(f"init --non-interactive failed:\n{init.stdout}\n{init.stderr}")

        doctor = _run(_cmd_evalflow("doctor"), cwd=tmp_path)
        if doctor.returncode != 0:
            raise RuntimeError(f"doctor failed:\n{doctor.stdout}\n{doctor.stderr}")

    return "CLI version/help/init/doctor checks passed."


def _test_and_coverage() -> str:
    pytest_result = _run(
        [
            str(_python_bin()),
            "-m",
            "pytest",
            "--basetemp=.pytest-tmp/launch-check-tests",
            "packages/cli/tests",
            "-q",
        ],
        cwd=ROOT,
        timeout=600,
    )
    if pytest_result.returncode != 0:
        raise RuntimeError(f"pytest failed:\n{pytest_result.stdout}\n{pytest_result.stderr}")

    coverage_path = TEMP_ROOT / "launch-coverage.xml"
    coverage_result = _run(
        [
            str(_python_bin()),
            "-m",
            "pytest",
            "--basetemp=.pytest-tmp/launch-check-cov",
            "--cov=evalflow",
            f"--cov-report=xml:{coverage_path}",
            "--cov-report=term-missing",
            "packages/cli/tests",
            "-q",
        ],
        cwd=ROOT,
        timeout=900,
    )
    if coverage_result.returncode != 0 or not coverage_path.exists():
        raise RuntimeError(
            f"Coverage run failed:\n{coverage_result.stdout}\n{coverage_result.stderr}"
        )
    return f"Tests pass and coverage report generated at {coverage_path}."


def _git_release(tag_release: bool, push_tag: bool) -> str:
    if not tag_release:
        return "Release tagging skipped. Re-run with --tag-release to create v0.1.4."

    git_dir = ROOT / ".git"
    if not git_dir.exists():
        raise RuntimeError("No .git directory found; run release tagging from a real git clone")

    tag_result = _run(["git", "tag", "v0.1.4"], cwd=ROOT)
    if tag_result.returncode != 0 and "already exists" not in tag_result.stderr:
        raise RuntimeError(f"git tag failed:\n{tag_result.stdout}\n{tag_result.stderr}")

    if not push_tag:
        return "Created or verified local tag v0.1.4. Re-run with --push-tag to publish it."

    push_result = _run(["git", "push", "origin", "v0.1.4"], cwd=ROOT, timeout=240)
    if push_result.returncode != 0:
        raise RuntimeError(f"git push failed:\n{push_result.stdout}\n{push_result.stderr}")
    return "Created and pushed git tag v0.1.4."


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the evalflow launch checklist.")
    parser.add_argument(
        "--tag-release",
        action="store_true",
        help="Create the local git tag v0.1.4 after all checks pass.",
    )
    parser.add_argument(
        "--push-tag",
        action="store_true",
        help="Push the v0.1.4 tag to origin after all checks pass.",
    )
    args = parser.parse_args()

    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    results = [
        _check("Package structure", _package_structure),
        _check("README launch content", _readme_quality),
        _check("CLI commands", _cli_checks),
        _check("Examples", _examples_exist),
        _check("Documentation", _docs_exist),
        _check("Tests and coverage", _test_and_coverage),
        _check("Security", _security_checks),
        _check("Build", _build_distribution),
        _check("Final install test", _final_install_test),
    ]

    if all(result.ok for result in results):
        results.append(
            _check(
                "Release tag",
                lambda: _git_release(args.tag_release, args.push_tag),
            )
        )

    return _report(results)


if __name__ == "__main__":
    raise SystemExit(main())

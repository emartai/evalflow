# Changelog

All notable changes to this project will be documented in this file.

## [0.1.5] - 2026-04-07

### Fixed

- run IDs are now unique per execution — timestamp plus random entropy prevents collisions when running the same dataset multiple times
- LLM judge now triggers correctly when `judge: true` is set in eval config, regardless of the `methods` list
- `evalflow doctor --fix` now creates `.env` from `.env.example` and shows actionable manual steps for issues it cannot auto-fix
- suppressed noisy HuggingFace Hub symlink and authentication warnings on Windows during embedding model load

## [0.1.4] - 2026-04-07

### Changed

- updated all docs URLs to point to emartai.mintlify.app
- GitHub Pages entry point now redirects to Mintlify

## [0.1.3] - 2026-04-07

### Fixed

- updated PyPI package description to show the full README instead of a one-line stub

## [0.1.2] - 2026-04-07

### Fixed

- completed Python 3.10 compatibility by replacing remaining `datetime.UTC` usage with `timezone.utc`
- made Rich terminal output safe on legacy Windows consoles by falling back to ASCII status symbols when Unicode glyphs are not supported
- stabilized the GitHub Actions smoke project setup so `evalflow doctor` passes consistently across Windows, macOS, and Ubuntu

### Changed

- expanded CI coverage to test Python 3.10, 3.11, and 3.12 on `ubuntu-latest`, `windows-latest`, and `macos-latest`

## [0.1.1] - 2026-04-07

### Changed

- polished eval output so progress display no longer clutters the final result transcript
- hardened the launch check final install verification on Windows by resolving installed CLI entry points more reliably
- improved concurrent eval cleanup so provider failures surface cleanly without leaked background task exceptions

## [0.1.0] - 2026-03-26

### Added

- `evalflow eval`: run LLM quality gates in CI
- `evalflow init`: project setup wizard
- `evalflow doctor`: system diagnostics
- `evalflow runs`: local run history
- `evalflow compare`: diff two runs
- `evalflow prompt`: version control for prompts
- Support for OpenAI, Anthropic, Groq, Gemini, and Ollama
- GitHub Actions CI integration
- Offline mode with response caching

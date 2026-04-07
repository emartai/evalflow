# Changelog

All notable changes to this project will be documented in this file.

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

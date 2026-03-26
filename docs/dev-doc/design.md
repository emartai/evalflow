# design.md — evalflow Design System

## 1. Brand Philosophy

evalflow is a developer-first CLI tool. Every design decision must serve one goal: make engineers trust it at first glance.

Design must be:
- Minimal
- Terminal-native
- Monochrome with purposeful color
- Functional over decorative
- Fast to scan

**Primary design rule:**
If it wouldn't look natural in a terminal, don't use it.

**The one-line principle:**
> evalflow design should feel like "a tool engineers trust at first glance"

---

## 2. Logo

Primary logo:

```
> evalflow
```

### Rules
- Always lowercase: `evalflow` — never `EvalFlow`, `Evalflow`, or `EVALFLOW`
- Monospace-friendly appearance
- No gradients, no icon, no mascot
- Works on both light and dark backgrounds
- The `>` prefix is the prompt character — it signals CLI nativity

### Usage examples

Inline text:
```
> evalflow
pytest for LLMs
```

CLI header:
```
> evalflow v0.1.0
```

GitHub README:
```
> evalflow

pytest for LLMs
```

Terminal output header:
```
> evalflow eval
```

### What the logo is NOT
- Not a wordmark with a special font
- Not an icon or SVG illustration
- Not a combination mark
- Not styled with color

---

## 3. Color Palette

Dark-mode first. Minimal colors. Color is used only for status — never for decoration.

### Core colors

| Role | Hex | Usage |
|---|---|---|
| Background | `#0B0F14` | Terminal background, dark surfaces |
| Primary text | `#E6EDF3` | All main text |
| Success | `#4ADE80` | PASS, ✓, positive delta |
| Warning | `#FACC15` | ! warnings, optional issues |
| Error | `#F87171` | FAIL, ✗, breaking issues |
| Muted text | `#8B949E` | Secondary info, test IDs, timestamps |

### Rules
- No gradients anywhere
- No more than 1 accent color visible at a time
- Status colors only — never use color for branding or decoration
- All text must pass WCAG AA contrast on `#0B0F14` background
- Light mode: invert background to `#FFFFFF`, primary text to `#1A1A2E` — keep status colors

### Color usage in CLI output

```
✓ summarize_short_article    0.91    ← green ✓, muted ID, white score
✗ answer_with_context        0.61    ← red ✗, muted ID, white score

Quality Gate: PASS                   ← bold green
Quality Gate: FAIL                   ← bold red
! sentence-transformers not set      ← yellow !
```

### What colors mean

| Color | Signal | Example |
|---|---|---|
| Green | Something passed or improved | ✓, PASS, +0.04 delta |
| Red | Something failed or regressed | ✗, FAIL, -0.12 delta |
| Yellow | Something optional or worth noting | ! warning, optional check |
| Muted gray | Secondary, informational | Run IDs, timestamps, provider names |
| White | Primary content | Scores, main text |

---

## 4. Typography

### Terminal (CLI)
Primary: monospace. The terminal renders whatever the user's terminal font is — don't override it.

Preferred fonts (for docs, README code blocks, screenshots):
- JetBrains Mono
- Fira Code
- Menlo
- Consolas
- `monospace` (system fallback)

### Documentation and README
- Body: system sans-serif (Inter or system-ui)
- Code: JetBrains Mono or Fira Code
- Headings: bold, minimal, short

### Rules
- Headings: bold, minimal — one idea per heading
- Body text: short lines, max 80 chars
- Avoid long paragraphs — developers scan, they don't read
- Use whitespace heavily
- Code is king — show code before prose

---

## 5. CLI Output Design

The CLI is the primary UI. Every character of output is product design.

### Standard eval output

```
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
Duration: 4.2s
```

### Column alignment rules
- Test case ID: left-aligned, padded to longest ID
- Score: right-aligned in a fixed-width column
- Minimum 4 spaces between ID column and score column
- All rows in a block must align — no ragged columns

### Status indicators

| Symbol | Meaning | Color |
|---|---|---|
| ✓ | Passed | Green |
| ✗ | Failed | Red |
| ! | Warning / optional | Yellow |
| → | Action / next step | Muted |
| • | Bullet point | White |

### Rules
- Use ✓ and ✗ — not emoji, not [PASS]/[FAIL], not colored words alone
- Compact output — no blank lines between individual test results
- One blank line before and after the summary block
- Keep output scannable from top — most important info first
- Scores: always 2 decimal places (0.91, 1.00, 0.07)

### What good output looks like vs bad

Good — compact, aligned, scannable:
```
✓ summarize_short_article    0.91
✓ classify_sentiment         1.00
✗ answer_with_context        0.61

Quality Gate: FAIL
```

Bad — verbose, unaligned, noisy:
```
[TEST 1] summarize_short_article: PASSED with score 0.91 🎉
[TEST 2] classify_sentiment: PASSED with score 1.00 ✅
[TEST 3] answer_with_context: FAILED - score was 0.61 which is below threshold ❌

QUALITY GATE STATUS: FAIL ❌❌❌
```

---

## 6. CLI Layout Structure

Every `evalflow` command follows this layout order:

```
[header]
[blank line]
[execution status]
[blank line]
[results]
[blank line]
[summary]
[blank line]
[next steps / exit]
```

### `evalflow eval` layout
```
Running X test cases against <model>...

✓ test-case-one    0.91
✓ test-case-two    1.00
✗ test-case-three  0.61

Quality Gate: PASS
Failures: 1
Run ID: 20240315-a3f9c2d81b4e
Duration: 4.2s
```

### `evalflow init` layout
```
  evalflow initialized

  Next steps:
  1. Add your API key:
     export OPENAI_API_KEY="your-key-here"

  2. Run your first eval:
     evalflow eval

  3. Add to CI:
     https://evalflow.dev/docs/ci-github-actions
```

### `evalflow doctor` layout
```
  ✓ evalflow 0.1.0 installed
  ✓ Python 3.11.4
  ✓ evalflow.yaml found
  ✓ evals/dataset.json found (5 test cases)
  ✓ OPENAI_API_KEY set
  ! sentence-transformers not installed (optional)
  ✗ .gitignore missing .env entry

  1 issue found. Run evalflow doctor --fix to resolve.
```

### `evalflow runs` layout
```
  Run ID                   Date        Provider   Score   Status
  ─────────────────────────────────────────────────────────────
  20240315-a3f9c2d81b4e   2024-03-15  openai     0.88    PASS
  20240314-c7e8b1d23f9a   2024-03-14  openai     0.71    FAIL
  20240313-b2d9f4e67c1b   2024-03-13  groq       0.91    PASS
```

---

## 7. Progress Indicators

Prefer simple text for short operations:

```
Running 5 test cases...
```

For longer operations, use a minimal progress bar:

```
[████████░░░░░░░░░░░░] 4/5 tests complete
```

Or Rich-style with test name:

```
Running ━━━━━━━━━━━━━━━━━━━━ 4/5  answer_with_context
```

### Rules
- Always show count (X/Y), not just percentage
- Show currently running test case name when possible
- Never show a blank screen for more than 2 seconds
- On first run, show model download progress:
  ```
  Downloading embedding model (80MB, one-time)...
  ```

---

## 8. Error Message Design

Error messages are the most important UX surface. Every error must be:
- Clear about what went wrong (one line)
- Actionable — tell the user exactly how to fix it
- Never a Python traceback

### Standard error format

```
✗ <What went wrong — one line>

  <Exact fix — 1-3 lines>
  <Link if relevant>
```

### Examples

Missing API key:
```
✗ Missing API key for OpenAI

  Set OPENAI_API_KEY in your environment:
  export OPENAI_API_KEY="sk-..."

  Get a key at: https://platform.openai.com/api-keys
```

Missing config:
```
✗ evalflow.yaml not found

  Run: evalflow init
```

Invalid dataset:
```
✗ dataset.json is not valid JSON

  Syntax error at line 14: Expecting ',' delimiter
```

Unknown provider:
```
✗ Unknown provider: "openai2"

  Valid providers: openai, anthropic, groq, gemini, ollama
```

### Rules
- Always use ✗ in red for errors
- One sentence for the problem
- 1-3 lines for the fix
- Include a link only when it's directly useful (API key signup, docs page)
- Never say "An error occurred" without specifics
- Never show Python exceptions, stack traces, or internal paths

---

## 9. Warning Message Design

Warnings are non-blocking issues:

```
! sentence-transformers not installed

  embedding_similarity method will be unavailable.
  Install with: pip install 'evalflow[embeddings]'
```

```
! No baseline found — saving this run as baseline.
```

```
! Running in offline mode — 2 test cases have no cached response and will be skipped.
```

### Rules
- Always use `!` in yellow for warnings
- Warnings don't block execution
- Include what the consequence is (what won't work)
- Include the fix when there is one

---

## 10. Success and Info Messages

```
✓ evalflow initialized
✓ Baseline saved (Run ID: 20240315-a3f9c2d81b4e)
✓ summarization promoted to production
```

Info (no symbol, muted):
```
  Comparing to baseline from 2024-03-14
  Using cached responses (offline mode)
```

---

## 11. Summary Block Design

The summary block appears at the end of every `evalflow eval` run:

```
Quality Gate: PASS          ← bold, colored (green/red)
Failures: 1                 ← number of test cases below threshold
Run ID: 20240315-a3f9c2d81b4e
Duration: 4.2s
```

When baseline comparison is available:
```
Quality Gate: PASS
Failures: 1
Δ overall: +0.03 vs baseline (improved)
Run ID: 20240315-a3f9c2d81b4e
Duration: 4.2s
```

When first run (baseline being set):
```
Quality Gate: PASS
Failures: 0
Baseline: saved
Run ID: 20240315-a3f9c2d81b4e
Duration: 4.2s
```

### Rules
- Always on separate lines
- Consistent label width (left-aligned labels)
- Delta shown as `+0.03` (green) or `-0.12` (red)
- Duration: one decimal place

---

## 12. README Design

The README is evalflow's landing page, pitch, and documentation entry point.

### Structure (in order)

```markdown
> evalflow

pytest for LLMs

[badges on one line]

[4-line pain story]

pip install evalflow

[quickstart: 2 commands]

[terminal output screenshot as code block]

[GitHub Actions workflow: 15 lines]

[Features: 6 bullets, no marketing]

[Links: docs, Discord, security]

[License: MIT]
```

### Pain story (always use this exact text)
```
You changed one prompt.
Summarization improved.
Classification silently broke.
Nobody noticed for 4 days.

evalflow catches this in CI before it ships.
```

### Rules
- No long intro paragraphs before the install command
- Install command visible without scrolling
- Terminal screenshot (as code block) within first 50 lines
- Code before prose — always
- Lines under 80 characters
- No buzzwords: "revolutionary", "powerful", "seamless", "robust"
- No marketing language
- Under 150 lines total

### README spacing

Good:
```
> evalflow

pytest for LLMs

pip install evalflow
```

Bad:
```
> evalflow — pytest for LLMs — catch prompt regressions before production
```

---

## 13. Documentation Design

Documentation site uses Mintlify. All pages follow these rules:

### Page structure
```
# Title (sentence case, imperative verb)

One-sentence description of what this page covers.

## Section

Short paragraph or code block — not both.
```

### Rules
- Sentence case headings: "Get started in 10 minutes" not "Getting Started In 10 Minutes"
- Code blocks before prose explanations — show it working, then explain
- Every page has a clear next step at the bottom
- No long introductions — get to the code in the first 5 lines
- Short paragraphs — max 3 sentences
- Never end a page without telling the user what to do next

### Code block style
Always specify the language:
```bash
pip install evalflow
```

Always show expected output in a separate block labeled with the result:
```bash
evalflow eval
```
```
Running 5 test cases against gpt-4o-mini...

✓ summarize_short_article    0.91
Quality Gate: PASS
```

---

## 14. GitHub Actions Workflow Style

The CI workflow file is a product artifact — it represents evalflow to users in their own codebase.

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

### Rules
- Job name: `eval` (not `test`, not `quality-gate`)
- Comment at top: `# .github/workflows/evalflow.yml`
- Steps are human-readable
- No unnecessary complexity
- Secret referenced as `${{ secrets.OPENAI_API_KEY }}` with a note to add it in repo settings

---

## 15. Social Preview Design

For GitHub social preview and Open Graph images. Text-only layout on dark background.

```
> evalflow

pytest for LLMs

Catch prompt regressions
before they reach production
```

### Rules
- Dark background: `#0B0F14`
- Centered text
- Monospace font
- No icons, no gradients, no decorative elements
- Green accent only on the `>` prompt character

---

## 16. Icons Reference

### Allowed in CLI
| Symbol | Use | Never use for |
|---|---|---|
| ✓ | Test passed, check complete | General positivity |
| ✗ | Test failed, check failed | Decoration |
| ! | Warning, optional issue | Emphasis |
| → | Next step, action | Decoration |
| • | Bullet point in lists | — |
| Δ | Delta / change | — |

### Never use in CLI
- Emoji of any kind (`🎉` `✅` `❌` `🚀`)
- Color blocks or box-drawing characters for decoration
- ASCII art
- Spinner animation (use progress bar instead)

---

## 17. Spacing Rules

### CLI output spacing
- 1 blank line between logical sections
- No blank lines between individual test results in the results list
- 1 blank line before summary block
- 1 blank line after summary block (before prompt returns)

Good:
```
Running 3 test cases...

✓ test-one    0.91
✓ test-two    1.00
✗ test-three  0.61

Quality Gate: FAIL
```

Bad (too much space):
```
Running 3 test cases...


✓ test-one    0.91

✓ test-two    1.00

✗ test-three  0.61


Quality Gate: FAIL
```

Bad (no space):
```
Running 3 test cases...
✓ test-one    0.91
✓ test-two    1.00
✗ test-three  0.61
Quality Gate: FAIL
```

### README spacing
- 1 blank line between paragraphs
- 2 blank lines before H2 headings
- No orphan lines at start or end of sections

---

## 18. Branding Rules

### Always
- Lowercase `evalflow` everywhere — in code, docs, social, CLI
- Monospace-friendly appearance
- Minimal developer aesthetic
- Factual descriptions — not marketing language

### Never
- `EvalFlow`, `Evalflow`, `EVALFLOW`
- Gradients anywhere
- Mascots or character illustrations
- Buzzwords: "powerful", "robust", "seamless", "game-changing", "revolutionary"
- Flashy accent colors
- Design elements that wouldn't look natural in a terminal

---

## 19. Design Priorities (in order)

When making design decisions, prioritize in this order:

1. CLI output clarity — can a developer scan it in 3 seconds?
2. Error message quality — is the fix obvious?
3. README first impression — does it earn trust without scrolling?
4. Documentation clarity — does the quickstart work in 10 minutes?
5. Spacing consistency — does it feel clean?
6. Logo and brand polish — least important

---

## 20. evalflow.yaml Style

The config file is a product surface. It should be self-documenting:

```yaml
# evalflow.yaml
version: "1.0"
project: my-ai-app

providers:
  openai:
    api_key_env: "OPENAI_API_KEY"   # env var name, never the key itself
    default_model: "gpt-4o-mini"

eval:
  dataset: "evals/dataset.json"
  default_provider: "openai"

thresholds:
  task_success: 0.80    # 0.0 - 1.0
  relevance: 0.75
```

### Rules
- Inline comments explain non-obvious fields
- Values are explicit (not magic numbers)
- Grouped logically (providers, eval, thresholds)
- Snake_case for all keys
- Quoted strings where ambiguity is possible

---

## 21. Dataset JSON Style

```json
{
  "version": "1.0",
  "test_cases": [
    {
      "id": "summarize-news-article",
      "description": "Model should summarize a news article in one sentence",
      "task_type": "summarization",
      "input": "Summarize in one sentence: [article text]",
      "expected_output": "A concise one-sentence summary of the main point.",
      "context": "",
      "tags": ["critical"],
      "eval_config": {
        "methods": ["embedding_similarity"],
        "judge": false,
        "weight": 1.0
      }
    }
  ]
}
```

### Rules
- IDs: kebab-case, descriptive, unique
- Descriptions: one sentence, explains what the test validates
- Task types: `summarization`, `classification`, `extraction`, `qa`, `generation`, `rewrite`
- Tags used for CI filtering: `critical` (every PR), `regression` (nightly)

---

## 22. Prompt YAML Style

```yaml
# prompts/summarization.yaml
id: summarization
version: 2
status: production
body: |
  You are a summarization assistant. Summarize the following
  text in exactly one sentence, capturing the main point only.
  Do not add opinions or context not present in the original.
author: emmanuel
created_at: "2024-03-01"
tags: ["core"]
```

### Rules
- `body` always uses YAML block scalar (`|`) for multiline text
- `status` is always one of: `draft`, `staging`, `production`
- `version` increments as integer (1, 2, 3)
- `author` is the GitHub username of the person who wrote it
- Tags are lowercase strings

---

## 23. Terminal Demo Video / GIF

The demo GIF is the most powerful marketing asset. It should show:

1. `pip install evalflow` (fast, ~5 seconds)
2. `evalflow init` (interactive, shows provider selection)
3. `evalflow eval` (progress bar → results table → PASS)

### Production rules
- Record with Asciinema, convert to GIF
- Max 60 seconds total
- Terminal: 80 columns × 24 rows
- Font: JetBrains Mono or Fira Code at 14px
- Background: `#0B0F14`
- No mouse cursor visible
- Typing speed: realistic (not instantly appearing text)
- Pause 2 seconds on the final result before looping

### What to show
- Real terminal (not a mock)
- Real output (not fabricated scores)
- No errors (run it until it's clean before recording)

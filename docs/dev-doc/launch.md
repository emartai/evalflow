# launch.md — evalflow Launch Playbook

## Pre-launch (1 week before)

### Accounts and handles
- [ ] GitHub org: github.com/evalflow
- [ ] PyPI package name reserved: `pip install evalflow` returns "not found"
- [ ] Domain registered: evalflow.dev or evalflow.sh
- [ ] X/Twitter: @evalflow
- [ ] Discord server created with invite link for README

### Content prepared
- [ ] Terminal demo video recorded (Asciinema → GIF, under 60 seconds)
  - Shows: pip install → evalflow init → evalflow eval → PASS result
- [ ] Show HN post written and reviewed
- [ ] dev.to/Hashnode post written (800-1200 words)
- [ ] X/Twitter launch thread written (7-10 tweets)
- [ ] awesome-llm-tools submission ready

### Technical
- [ ] `uv build` completes cleanly
- [ ] `pip install dist/*.whl` in fresh venv works
- [ ] `evalflow --version` returns `0.1.0`
- [ ] All 3 examples run without errors
- [ ] Mintlify docs site live at evalflow.dev/docs
- [ ] CI badge in README is green

---

## Launch day sequence

### 8:00 AM — PyPI publish
```bash
git tag v0.1.0
git push origin v0.1.0
# GitHub Actions publish.yml triggers automatically
# Verify: pip install evalflow
```

### 9:00 AM — GitHub repo public
- [ ] Set repo to public
- [ ] Add topics: llm, testing, ai, cli, quality-gate, pytest, prompts
- [ ] Pin README to top
- [ ] Add Discord link to repo description

### 10:00 AM — Show HN post

**Title:** Show HN: evalflow – pytest for LLMs, catches prompt regressions in CI

**Text:**
```
I built evalflow after a one-word prompt change silently broke our 
classification pipeline. Nobody noticed for 4 days.

evalflow is a CLI tool that catches LLM quality regressions in CI/CD 
before they reach production — the same way pytest catches code bugs.

How it works:
1. Write test cases (input → expected output)
2. Run evalflow eval in CI
3. If quality drops vs baseline, the build fails

It supports 4 eval methods: exact match, embedding similarity, 
consistency scoring, and LLM-as-judge (opt-in, uses Groq free tier).

pip install evalflow

Would love feedback on the dataset format and eval methods.
```

### 11:00 AM — X/Twitter thread

Tweet 1 (with GIF demo):
```
I shipped evalflow today — pytest for LLMs

You changed one prompt.
Summarization improved.
Classification silently broke.
Nobody noticed for 4 days.

evalflow catches this in CI before it ships.

pip install evalflow
```

Tweet 2:
```
How it works in 3 steps:

1. Write test cases in JSON
2. Run `evalflow eval` in GitHub Actions
3. Build fails if quality drops vs baseline

Exit 0 = pass. Exit 1 = regression. Exit 2 = error.

Developers know how to handle exit codes.
```

Tweet 3:
```
4 eval methods, layered:

Layer 1: Exact match (free, instant)
Layer 2: Embedding similarity (local, no API)  
Layer 3: Consistency scoring (variance across runs)
Layer 4: LLM-as-judge (opt-in, Groq free tier)

Use the cheapest method that answers your question.
```

Tweet 4:
```
Prompt version control is built in.

prompts/summarization.yaml:
  version: 3
  status: production
  body: |
    You are a summarization assistant...

evalflow prompt promote summarization --to production

Your app reads the live version at runtime.
```

Tweet 5:
```
Works with:
- OpenAI
- Anthropic  
- Groq (free tier, great for CI)
- Gemini
- Ollama (local, no API key)

evalflow.yaml stores the env var name, never the key.
Safe to commit.
```

Tweet 6:
```
All run history is local SQLite.
No account. No cloud. No data sent anywhere.

evalflow runs
evalflow compare run-abc123 run-def456

Works offline with cached responses.
```

Tweet 7 (CTA):
```
evalflow is open source (MIT).

GitHub: github.com/evalflow/evalflow
Docs: evalflow.dev/docs
Discord: [link]

Building in public. Would love feedback — what eval methods are missing?
```

### 2:00 PM — Community posts

Post to:
- [ ] Latent Space Discord (#tools channel)
- [ ] AI Engineer community on X
- [ ] LangChain Discord (#tools)
- [ ] Hacker News new (if Show HN didn't get traction)
- [ ] r/MachineLearning (check if appropriate)
- [ ] LinkedIn (shorter version)

### 6:00 PM — awesome lists

Submit PR to:
- [ ] github.com/tensorchord/Awesome-LLMOps
- [ ] github.com/HqWu-HITCS/Awesome-Chinese-LLM (if relevant)
- [ ] Any active awesome-llm-tools list

---

## Week 1 actions

### Daily
- Reply to every GitHub issue within 4 hours
- Reply to every X/Twitter mention
- Be active in Discord

### Post-launch content (within 7 days)
- [ ] "What I learned building evalflow" (dev.to)
- [ ] Share first GitHub star milestone on X
- [ ] Share first non-author user on X

### Metrics to track daily
| Metric | Day 1 | Day 3 | Day 7 | Target |
|---|---|---|---|---|
| GitHub stars | - | - | - | 50 |
| PyPI installs | - | - | - | 200 |
| Discord members | - | - | - | 30 |
| GitHub issues | - | - | - | >5 (means usage) |

---

## Show HN post tips

- Post at 8-10 AM ET on a weekday (Tuesday-Thursday best)
- Must start with "Show HN:"
- Keep text under 300 words
- Be honest about what's not done yet — HN rewards honesty
- Respond to every comment within the first hour
- Don't be defensive about criticism
- The demo video/GIF is the most important asset

---

## What to do if launch goes badly

If Show HN gets < 5 upvotes in 2 hours:
- Don't repost (against rules)
- Post on dev.to instead and share on X
- Go find 5 people on X who complained about LLM testing recently and DM them

If no GitHub stars after 24 hours:
- Check: is the README first impression clear?
- Ask 3 developer friends to read the README cold and tell you what's confusing
- Fix the first thing they say

If negative feedback:
- Read it. Take what's valid.
- Respond publicly: "Good point. We'll fix this."
- Don't argue.

---

## Revenue: $0 at launch (intentional)

The launch goal is not revenue. It's:
1. 50 GitHub stars in first week
2. 10 people using it in CI
3. 50 people in Discord or mailing list

Revenue comes at V1 (months 3-6) with the cloud dashboard.
The launch is purely about building trust and community.

# Claude Agent Skills: Structure, Authoring, Ecosystem, and Sports-Pipeline Applications
_Researched 2026-06-16. Scope: SKILL.md format + progressive disclosure + authoring best practices + plugins/marketplace ecosystem + how to build custom skills for a calibrated sports-prediction pipeline._

---

## TL;DR (highest-leverage takeaways)

- **Skills are filesystem-based capability packages** (a directory with SKILL.md at root) that Claude discovers automatically. Only the YAML `name`+`description` (~100 tokens total) is pre-loaded; the full body is read on demand; auxiliary files are loaded only if Claude references them. This is "progressive disclosure" -- context cost scales with actual use, not install count.
- **SKILL.md frontmatter has exactly two required fields**: `name` (max 64 chars, lowercase+hyphens) and `description` (max 1024 chars). The description is the discovery trigger -- Claude pattern-matches your request against every installed skill's description. Write it in third person: "Processes X. Use when Y."
- **Three loading tiers**: (1) metadata always in system prompt ~100 tokens; (2) SKILL.md body loaded when triggered, keep under 500 lines; (3) bundled files (FORMS.md, scripts/, reference/) loaded only when SKILL.md explicitly references them. Scripts execute via bash -- only output enters context, not code.
- **Claude Code skills are filesystem-only and get full network access**; API-hosted skills get no network access and no runtime pip installs; claude.ai skills are user-scoped only (not org-wide).
- **obra/superpowers** is the dominant community skill collection (accepted into official Anthropic marketplace Jan 2026, MIT, 222k+ uses): methodology-as-skill (brainstorming, TDD, systematic-debugging, planning, subagent coordination). Model: teach agents HOW to think, not just WHAT to do.
- **machina-sports/sports-skills** is the leading open-source sports-data skill collection: 14 sport-data skills (NBA, MLB, NFL, soccer, tennis, F1, ...) + 2 prediction-market skills (Kalshi, Polymarket) + a pure-compute `betting` skill (Kelly, arbitrage, odds conversion). Zero API keys for read-only sports data via ESPN/FastF1/etc. Install: `npx skills add machina-sports/sports-skills`.
- **Best practice development loop**: build with Claude A (expert), test with Claude B (fresh instance using the skill), observe gaps, iterate. Start minimal; the best skills started as "a few lines and a single gotcha."

---

## Key capabilities and techniques

### SKILL.md structure
```
<skill-dir>/
+-- SKILL.md            # Required: YAML frontmatter + markdown body (< 500 lines)
+-- REFERENCE.md        # Optional: loaded only when SKILL.md points here
+-- reference/
|   +-- domain-a.md    # Domain-scoped reference, loaded on demand
|   +-- domain-b.md
+-- scripts/
    +-- validate.py     # Executed via bash; code itself never enters context
    +-- analyze.py
```

Frontmatter fields (only name + description are required and load-bearing):
```yaml
---
name: processing-game-logs         # gerund form recommended; lowercase+hyphens; max 64 chars
description: Processes raw NBA/MLB/soccer game-log parquets into feature matrices
  for walk-forward model evaluation. Use when the user asks to process game logs,
  build features, or run a walk-forward split.
---
```

All other frontmatter fields (allowed-tools, hooks, disable-model-invocation,
user-invocable, etc.) are supported in Claude Code CLI but are stripped before
model context in API usage. Known GitHub issue #13005: custom frontmatter fields
are silently dropped.

### Progressive disclosure patterns (3 canonical patterns)
1. **High-level guide with references**: SKILL.md has quick-start inline; detail in FORMS.md/REFERENCE.md, linked once.
2. **Domain-scoped organization**: one skill, reference/ subdirectory with per-domain files (finance.md, sales.md). Claude reads only the one matching the task. Ideal for a multi-sport system (nba.md, mlb.md, soccer.md, tennis.md).
3. **Conditional workflow**: SKILL.md routes to different sub-files based on task type (new model vs. backtest vs. in-game regrade).

**Anti-pattern**: nested references (SKILL.md -> advanced.md -> detail.md). Claude may do `head -100` on intermediate files and miss content. Keep all references one level deep from SKILL.md.

### Where skills run / sharing scope
| Surface       | Custom skills    | Network access  | Sharing scope          |
|---------------|-----------------|-----------------|------------------------|
| Claude Code   | filesystem-only | Full (user's OS) | ~/.claude/skills/ (personal) or .claude/skills/ (project) or plugins |
| Claude API    | upload via /v1/skills | None      | Workspace-wide         |
| claude.ai     | upload as .zip  | Varies (user settings) | Per-user only     |

Claude Code is the right surface for this project: full network, project-level .claude/skills/, git-controlled.

### Plugins and namespacing (Claude Code)
Skills can be published as Claude Code plugins. Plugin skills use namespaced invocation: `plugin-name:skill-name`. The official marketplace (claudemarketplaces.com, claudepluginhub.com) aggregates community plugins. obra/superpowers was the first third-party plugin accepted into the official marketplace.

### obra/superpowers -- methodology skills
Seven-phase dev workflow as composable skills:
- `brainstorming` -- structured requirement/design clarification before any code
- `planning` -- breaks work into 2-5 minute tasks with file paths + verification steps
- `test-driven-development` -- RED-GREEN-REFACTOR enforcement
- `systematic-debugging` -- evidence-based root cause, not guessing
- `verification-before-completion` -- Claude proves it worked before declaring done
- `subagent-coordination`, `code-review`, `git-worktrees`, `writing-skills`

Install: official Anthropic marketplace or `npx claude install obra/superpowers`.

### machina-sports/sports-skills
14 sports-data skills (ESPN/FastF1/TFRRS endpoints, zero API key for read):
NBA, MLB, NFL, WNBA, NHL, soccer (23 commands, 13 leagues), tennis, F1, golf,
college BB, college FB, cross-country.
2 prediction-market skills: Kalshi (CFTC-regulated), Polymarket (CLOB, order placement).
`betting` skill: pure-compute toolkit (Kelly criterion, odds conversion, edge detection,
arbitrage) -- no network calls, runs deterministically.
`markets` skill: orchestrates ESPN <-> Kalshi <-> Polymarket data joins.
`sports-reporter`: composes data skills into journalism.
Install: `npx skills add machina-sports/sports-skills` or `pip install sports-skills`.

### Naming conventions
- Preferred: gerund form -- `processing-pdfs`, `running-walk-forward`, `evaluating-calibration`
- Acceptable: noun phrases -- `walk-forward-eval`, `calibration-audit`
- Forbidden: "anthropic", "claude" in name; uppercase; spaces; XML tags
- Vague names to avoid: `helper`, `utils`, `tools`, `data`

### Description writing rules
- Third person only (injected into system prompt; POV mismatch breaks discovery)
- State WHAT the skill does AND WHEN to invoke it (both halves matter)
- Include key domain terms users will say ("walk-forward", "Brier score", "in-game", "calibration")
- Max 1024 chars; no XML tags
- This is the only selector Claude uses when choosing among 100+ installed skills

---

## How THIS project should use it (specific, actionable)

### 1. Encode the pipeline as skills (not just CLAUDE.md prose)
Split the build pipeline into discoverable skills under `.claude/skills/`:

| Skill name                    | Triggers on                                          | What it encodes                                                 |
|-------------------------------|------------------------------------------------------|-----------------------------------------------------------------|
| `processing-game-logs`        | "process logs", "build features", "parquet"          | sport-adapter ingestion pattern; column contracts; LOC limits   |
| `running-walk-forward`        | "walk-forward", "OOS eval", "leak-free backtest"     | WF split rules; anti-leak checklist; per-file pytest only       |
| `evaluating-calibration`      | "Brier score", "calibration", "accuracy vs edge"     | Brier/log-loss eval scripts; honest-reject framing; no ROI      |
| `adding-sport-adapter`        | "new sport", "add adapter", "domains/<sport>"        | kernel/adapter contract; zero kernel edits rule; proof harness  |
| `running-ingame-regrade`      | "in-game", "live regrade", "CV_INGAME"               | regrade pipeline; shrink-toward-current MAE artifact warning    |
| `building-obsidian-brain`     | "vault", "brain rebuild", "build_all"                | serialized single-rebuild rule; person-free constraint          |
| `auditing-signal-catalog`     | "signal catalog", "gate", "REJECT"                   | gate harness path; honest-reject = success framing              |
| `running-benchmark`           | "benchmark", "300 frames", "CV pipeline"             | existing /benchmark skill -- already coded                      |

Each skill body is short (<200 lines). Domain-specific details live in reference/ files per sport.

### 2. Use domain-scoped reference/ for multi-sport support
```
.claude/skills/running-walk-forward/
+-- SKILL.md              # routing + quick-start
+-- reference/
    +-- nba.md            # NBA-specific WF params, data paths, corpus notes
    +-- mlb.md
    +-- soccer.md
    +-- tennis.md
```
When user says "run walk-forward for ATP", Claude reads SKILL.md then only tennis.md.

### 3. Encode hard-won gotchas as skill guardrails (not just memory)
The MEMORY.md records lessons like "bash cwd FLAKY -- prefix every cmd with cd /c/Users/neelj/nba-ai-system &&" and "NEVER 2 concurrent brain rebuilds". Put these in the relevant skill bodies as explicit WARNINGS so every future agent invocation gets them without relying on memory loading.

Example in `building-obsidian-brain/SKILL.md`:
```
WARNING: NEVER run two concurrent brain rebuilds. Both rmtree the same
vault/_Organized and corrupt it (WinError 32). Serialize; run the single
--strict rebuild yourself after any fleet.
WARNING: Always prefix bash commands: cd /c/Users/neelj/nba-ai-system && <cmd>
(cwd resets between bash calls in this harness).
```

### 4. Build a `calibration-audit` skill for auto-honest-checking
Every prediction output should run through a standard Brier/log-loss audit.
Encode this as a skill with a bundled `scripts/calibration_audit.py` that
accepts model predictions + actuals and emits a structured honesty report.
Claude B running any eval skill auto-invokes it without you asking.

Description: "Audits model predictions for calibration quality (Brier score,
reliability diagram, log-loss). Use after any model evaluation, walk-forward
run, or before any result is documented. Never claims edge; frames results as
calibration accuracy vs. devigged market baseline."

### 5. Borrow obra/superpowers methodology skills NOW
Install superpowers immediately. The `brainstorming` + `planning` + `systematic-debugging`
+ `verification-before-completion` skills will improve every wave of work.
The verification-before-completion skill is especially relevant: it forces Claude
to prove a fix worked (run the test, observe the output) before declaring done --
exactly the discipline this project needs for walk-forward integrity.

### 6. Install machina-sports/sports-skills for live data scaffolding
The `@nba-data` skill wraps ESPN endpoints for live box scores/lineups with
zero API key overhead -- useful for freshness-bump data collection.
The `betting` skill's Kelly + edge-detection utilities can be reused in the
in-game regrade pipeline (already calibrated, compute-only, no network).
The `markets` skill is a template for the ESPN <-> Kalshi/Polymarket join
if the project ever validates in-game market data as a calibration benchmark.

### 7. Skill for enforcing LOCAL-only commit discipline
Encode the LOCAL-commits-only invariant as a `committing-changes` skill
(overrides the default GSD commit behavior):
```yaml
description: Creates git commits in this project. ALWAYS uses targeted
git add (never git add -A). NEVER pushes to origin (origin is public).
Local commits only. Use when asked to commit changes.
```
This makes the constraint active on every commit request without relying on
the agent reading CLAUDE.md first.

### 8. Skill file size budget
- SKILL.md body: < 300 lines (tighter than the 500-line official limit; this project's files are < 300 LOC by invariant)
- Bundled scripts: individual files < 300 LOC (same rule as src/)
- Reference files: 100-750 LOC (data-module exemption applies)
- Add a ToC to any reference file > 100 lines

---

## Gotchas and limits

- **Custom frontmatter fields are silently stripped** before model context (GitHub issue #13005). Only `name` and `description` are load-bearing. Any metadata you put in other fields (e.g., `version`, `author`) is invisible to the model; put it in the SKILL.md body instead.
- **Skills do NOT sync across surfaces.** Claude Code skills are git-local; API-uploaded skills are workspace-only; claude.ai skills are user-only. For this project, .claude/skills/ (Claude Code, git-tracked) is the right home.
- **Claude API skills have no network access and no pip.** If you use skills via the API (e.g., the Agent SDK), pre-bundle all dependencies and data. This project runs Claude Code so full network is available.
- **Deep nesting breaks progressive disclosure.** SKILL.md -> a.md -> b.md means Claude may `head -100` the intermediate file and miss key content. One level deep only.
- **The description is the ONLY selector Claude uses.** Among 100+ skills, Claude picks based solely on description text vs. user request. Vague descriptions silently fail (skill never triggers). Test by checking whether Claude actually invokes the skill without being asked.
- **The 500-line SKILL.md limit is a soft performance guidance, not a hard error.** But exceeding it means more context consumed when triggered; split instead.
- **Malicious skill risk**: skills from unknown sources can run arbitrary bash. Only install skills from: this project's own .claude/skills/, obra/superpowers (MIT, audited), machina-sports/sports-skills (read-only data, audited before install). Audit any script before use.
- **Model-dependence**: a skill tuned for Opus may be too sparse for Haiku. For this project (Sonnet 4.6 as worker, Opus as reviewer), test that walk-forward / calibration skills give Sonnet enough detail to act correctly without hand-holding.
- **No guaranteed $ edge framing**: skills should NEVER frame outputs as betting profit or ROI. The `calibration-audit` skill description must explicitly say "never claims edge; frames as calibration accuracy." This is a build-time guardrail, not just a runtime one.
- **Windows path anti-pattern**: use forward slashes in all skill file references even on Windows (the harness runs in bash; backslashes cause failures).

---

## Sources

- [Agent Skills overview -- platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Skill authoring best practices -- platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Equipping agents for the real world with Agent Skills -- Anthropic engineering blog](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [obra/superpowers GitHub repo](https://github.com/obra/superpowers/)
- [machina-sports/sports-skills GitHub repo](https://github.com/machina-sports/sports-skills)
- [SKILL.md frontmatter reference -- anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/command-development/references/frontmatter-reference.md?plain=1)
- [Custom frontmatter fields stripped issue #13005 -- anthropics/claude-code](https://github.com/anthropics/claude-code/issues/13005)
- [Claude Agent Skills: A First Principles Deep Dive -- leehanchung.github.io](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)
- [Superpowers for Claude Code: Complete Guide 2026 -- pasqualepillitteri.it](https://pasqualepillitteri.it/en/news/215/superpowers-claude-code-complete-guide)
- [9 Tips for Building Claude Agent Skills -- Medium](https://medium.com/@tahirbalarabe2/9-tips-for-building-claude-agent-skills-3bca85c47a26)

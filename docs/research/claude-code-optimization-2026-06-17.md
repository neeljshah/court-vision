# Making the Claude Code system smarter -- researched audit (2026-06-17)

Deep-researched against Anthropic's official guidance + power-user practice, then
audited against THIS repo's actual md system. Sources at the bottom.

## The canonical principles (sourced)

1. **CLAUDE.md is a lookup table, not a brain dump.** It loads every session, so every
   token is a permanent per-turn tax. Rule of thumb: for each line ask *"would removing
   this cause Claude to make a mistake?"* -- if not, cut it. **Bloat makes Claude IGNORE
   the rules that matter** (they get lost in noise). [Anthropic best-practices]
2. **Instruction budget is finite.** Frontier models reliably follow ~150-200 instructions
   before quality degrades; Claude Code's own system prompt already eats ~50, leaving
   ~100-150 for your CLAUDE.md + rules. Keep load-bearing rules lean. [community/2026]
3. **Sometimes-relevant knowledge -> Skills, not CLAUDE.md.** Domain workflows belong in
   `.claude/skills/` (loaded on demand via progressive disclosure), so they don't tax
   every session. [Anthropic best-practices]
4. **Progressive disclosure for Skills.** SKILL.md body < 500 lines; push detail into
   referenced files ONE level deep; descriptions in third person stating *what it does +
   when to use it* (that's what Claude matches on). [Skill-authoring docs]
5. **Hooks for must-happen-every-time.** CLAUDE.md is advisory; hooks are deterministic.
   Use hooks for invariants you cannot allow an agent to skip. [Anthropic best-practices]
6. **Subagents for context isolation.** Research/ver, in a separate context window, return
   only a summary -- keeps the main thread clean. Add an *adversarial reviewer* in a fresh
   context before calling work done. [Anthropic best-practices]
7. **Manage context aggressively.** `/clear` between unrelated tasks; plan-then-code;
   tell compaction what to preserve. [Anthropic best-practices]

## Audit of THIS system (graded)

| Component | Grade | Verdict |
|-----------|-------|---------|
| `.claude/rules/` (4 @imports) | **A** | Modular, imperative, load-bearing. Textbook use of `@import`. |
| Skills (9) | **A-** | 3rd-person what+when descriptions, `model:` frontmatter, progressive disclosure (predict-matchup wraps a CLI). |
| Subagents (4 cv-*) | **A** | Context-isolated + model-tiered (opus=judgment, haiku=search). cv-honesty-gate IS the adversarial reviewer the docs recommend. |
| Hooks | **A** | PreToolUse guard = deterministic enforcement of the exact invariants that must never be skipped. |
| Output style + memory | **A** | Concision enforced; two-layer memory (CLAUDE.md + auto-memory index loads first 200 lines). |
| **CLAUDE.md (before)** | **B** | Within the 500-line limit BUT carried a 13-line DEAD section (5 vault notes now archived) + a guard repeated 3x. |
| **CLAUDE.md (after)** | **A-** | Dead section killed, guard de-duped to its rule import, +1 compaction-preservation line. 107->97 lines, ~1974->1810 tok. |

**Bottom line:** the system already follows nearly every documented best practice. The one
real gap was CLAUDE.md drift -- now fixed.

## What changed this session
- CLAUDE.md: removed the retired Vault Auto-Maintenance block (pointed at 5 GONE files);
  de-duplicated the retracted-numbers guard (now stated once + deferred to
  `@.claude/rules/no-edge-claims.md`); added one compaction-preservation rule tuned to the
  days-long autonomous builder (preserve modified files / test cmds / which flags stay OFF
  / no-edge + human-gated invariants). All safety guards verified intact.

## Optional next (behavioral / cheap -- not yet applied)
- **`/clear` between unrelated tasks** in interactive use -- the single highest-ROI habit
  per Anthropic (long mixed-context sessions degrade quality).
- **Quarterly CLAUDE.md prune** -- treat it like code; it drifts (this audit found 13
  dead lines). A `state-roadmap`-style check could flag stale path references.
- **Skill self-test loop** -- the docs' "Claude A authors / Claude B uses / observe /
  refine" cycle; you already have eval-gate as the objective half.
- Everything else (subagents, hooks, adversarial review, model tiering) is already done.

## Sources
- Anthropic, *Best practices for Claude Code* -- https://code.claude.com/docs/en/best-practices
- Anthropic, *Skill authoring best practices* -- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic, *Equipping agents with Agent Skills* -- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- *The Complete Guide to CLAUDE.md* (Ghosh, 2026) -- https://medium.com/@bijit211987/the-complete-guide-to-claude-md-memory-rules-loading-and-cross-tool-compression-97cc12ed037b
- *Claude Code Advanced Best Practices* (SmartScope, 2026) -- https://smartscope.blog/en/generative-ai/claude/claude-code-best-practices-advanced-2026/

# 10 -- Cohesion Architecture: how the whole Claude Code system fits together

ASCII only. READ-ONLY survey + design. Today 2026-06-17.

This document is the target design for how every knowledge-bearing surface in
Neel's Claude Code setup fits together so that **each piece of knowledge lives in
exactly ONE right place** and **the system maintains itself** across sessions.

It builds on (does not contradict) the prior organization-sprint outputs:
`docs/research/organization-sprint/{COHERENCE-PLAN,MEMORY-MAP,MEMORY-REORG-PROPOSAL,PROPOSED-CLAUDE}.md`.

--------------------------------------------------------------------------------
## 1. The surfaces that exist today (survey)

| Surface | Location | What it is | Load timing | Versioned? |
|---|---|---|---|---|
| User memory | `~/.claude/projects/C--Users-neelj/memory/` (178 files, 1.5MB) | Auto-memory: `MEMORY.md` index + ~177 topic notes (project-*, feedback-*, gotcha-*) | Index auto-loaded every session; topics on demand | No (user dir) |
| Project onboarding | `nba-ai-system/CLAUDE.md` (7.9KB) | "Agent onboarding": identity, read-order, go-commands, Task->Files, Rules, vault-maintenance | Auto-loaded when cwd in repo | Yes (public repo) |
| Rules | `nba-ai-system/.claude/rules/*.md` (4 files) | Hard, always-on behavioral constraints (cwd-prefix, no-commit data/vault, human-gated-paths, no-edge-claims) | Auto-loaded with CLAUDE.md | Yes |
| State | `docs/CLAUDE-state.md` AND `.planning/STATE.md` AND `.planning/CANONICAL_VALUES.md` | Three overlapping "current state / canonical numbers" files | On demand | Local-only (gitignored) |
| Planning | `.planning/` (ROADMAP.md 167KB + PROJECT.md + STATE.md + ~30 plan/prompt docs + subdirs) | GSD roadmap, milestone state, deep-dive plans, per-loop prompts | On demand / GSD skills | Local-only |
| Docs | `docs/` (~70 files + research/, strategy/, operations/, _audits/) | Reference: evidence packet, proofs, runbooks, architecture, research | On demand | Mixed (public + local-only) |
| Skills | `.claude/skills/` (repo) + global skills | Executable procedures (eval-gate, predict-matchup, calibration-report, ...) | Invoked by name/trigger | Yes |
| Agents | `.claude/agents/*.md` (7 cv-* / monitor agents) | Subagent role definitions | On spawn | Yes |
| Commands | `.claude/commands/*.md` (18 loop/build prompts) | Slash-command / "go" loop specs | On invocation | Local-only |
| Hooks/settings | `~/.claude/settings.json` | SessionStart (gsd-update + update_vault.py), PostToolUse (gsd-context-monitor), Stop (vault_session_close.py), statusline | Each lifecycle event | No (user dir) |
| Vault | `vault/` (Obsidian, rebuildable) | Working brain: sessions, models, improvements, intelligence atlases | On demand / hooks | Local-only, rebuildable |

**The core problem:** "current state" and "canonical facts" are spread across at
least five surfaces (MEMORY.md START-HERE block, CLAUDE.md TL;DR, docs/CLAUDE-state.md,
.planning/STATE.md, .planning/CANONICAL_VALUES.md, vault Decision Log). They drift.
Invariants are duplicated between MEMORY.md and `.claude/rules/`. Numbers appear in
CLAUDE.md that the no-edge-claims rule says only JOB_EVIDENCE_PACKET may own.

--------------------------------------------------------------------------------
## 2. Target architecture -- one role per surface

Each surface gets ONE job. The test for "where does X go" is the **lifetime +
audience + enforcement** of the knowledge:

- Is it an always-on *behavioral constraint*?  -> `.claude/rules/`
- Is it *durable cross-session learning* (a lesson, a gotcha, a project outcome)?  -> user **memory**
- Is it *how to onboard / where things live* (durable, public)?  -> `CLAUDE.md`
- Is it *the current mutable state / latest numbers*?  -> ONE state file
- Is it *forward-looking plan / roadmap*?  -> `.planning/`
- Is it *reference detail an agent reads on demand*?  -> `docs/`
- Is it an *executable procedure*?  -> skill / command / agent
- Is it *self-maintenance automation*?  -> hook

### 2.1 Knowledge-type -> where it lives -> who updates it

| Knowledge type | Single home | Format | Who writes it | When |
|---|---|---|---|---|
| Always-on behavioral constraint (cwd-prefix, no-commit data/vault, human-gated paths, no-edge-claims, ASCII, per-file-tests, no concurrent rebuilds) | `.claude/rules/*.md` | One rule per concern, imperative, no metrics | Human (or agent w/ human confirm) | When a constraint is born/changes |
| Durable learning: a gotcha, a validated/rejected experiment, a project-wave outcome, a directive | user **memory** topic note (`feedback-*`, `gotcha-*`, `project-*`) + one index line in `MEMORY.md` | Topic file holds detail; index = 1 line <200 chars | Agent at session stop (memory-writer step) | When a lesson is learned, in place if it already exists |
| Onboarding: identity, read-order, Task->Files map, key paths, go-command pointers, where-things-live | `CLAUDE.md` | Stable pointers only; NO live metrics, NO duplicated invariants (link to rules + state) | Human, rarely | When repo structure/entrypoints change |
| Current mutable state: branch/head, loop round, latest metrics, active phase, daemon count, open issues | ONE state file: `docs/CLAUDE-state.md` (see SSOT, sec. 4) | Dated sections, terse | Stop hook (auto) + agent on material change | Every session + on change |
| Canonical numbers that MAY be claimed + retracted-number blocklist | `docs/JOB_EVIDENCE_PACKET.md` (the claim truth source) | Claim + proof artifact + do-not-claim list | Human / honesty-gate agent | When a claim is proven/retracted |
| Forward plan / roadmap / milestone progress / per-loop build prompts | `.planning/` (ROADMAP.md, PROJECT.md, phase plans, GSD STATE.md) | GSD format | GSD skills + agents | During planning/execution |
| Reference detail (architecture, proofs, runbooks, methodology, research) | `docs/` (+ research/, operations/, strategy/) | Long-form, read on demand | Agent/human when authored | When work produces a durable artifact |
| Executable procedure (run the gate, predict a matchup, rebuild the brain) | skill (`.claude/skills/`) | SKILL.md + script | Human/agent | When a repeatable action stabilizes |
| Multi-step loop / "go" entrypoint | `.claude/commands/*.md` | Prompt spec | Human/agent | When a loop is defined |
| Subagent role | `.claude/agents/*.md` | Role + tools | Human | When a recurring role is needed |
| Self-maintenance automation | `~/.claude/settings.json` hooks | command hooks | Human (via update-config) | When a lifecycle behavior is wanted |

### 2.2 The clean separations (no overlap rules)

- **Rules never contain metrics or state.** They are timeless constraints. The
  no-edge-claims rule may name the retracted-number *blocklist* (those are
  permanent), but it points to JOB_EVIDENCE_PACKET for what may be claimed.
- **CLAUDE.md never contains live metrics.** Today it embeds a TL;DR with
  MAE/Brier/ROI numbers -- those belong to JOB_EVIDENCE_PACKET (claims) and
  CLAUDE-state.md (latest). CLAUDE.md links to both. This also removes the risk of
  CLAUDE.md silently violating no-edge-claims.
- **CLAUDE.md never duplicates invariants.** The "Rules" / "binding invariants"
  text in CLAUDE.md and in MEMORY.md both restate what `.claude/rules/` already
  enforces. CLAUDE.md keeps a one-line pointer: "Behavioral constraints live in
  `.claude/rules/` -- they are auto-loaded; do not restate them."
- **Memory holds learnings, not state.** A metric value is state (CLAUDE-state.md);
  "minimizing MAE pulls predictions toward the market and destroys edge" is a
  learning (memory). The MEMORY.md START-HERE block keeps the *north star + invariant
  pointers*, not a running status feed.
- **State has ONE home** (sec. 4). `.planning/STATE.md` stays as GSD's
  machine-managed milestone/phase counter; `docs/CLAUDE-state.md` is the
  human/agent-readable current-state narrative; `CANONICAL_VALUES.md` is folded
  into JOB_EVIDENCE_PACKET (claims) + a metrics-from-registry rule. No third copy.
- **Planning is forward; docs is reference; memory is lessons.** A finished plan's
  *outcome* becomes a memory note + a docs artifact; the plan doc itself stays in
  `.planning/` as history. The lesson is not re-pasted into three places.

### 2.3 How surfaces reference each other (the link graph)

```
                 .claude/rules/   <-- always-on, auto-loaded, no links needed
                       ^
                       | "constraints live here, do not restate"
   MEMORY.md  ----->  CLAUDE.md  -----> docs/CLAUDE-state.md   (current state)
   (north star,      (onboarding,  --> docs/JOB_EVIDENCE_PACKET.md (claims/blocklist)
    lessons index)    pointers)    --> .planning/ROADMAP.md     (forward plan)
        |                          --> docs/<reference>          (on-demand detail)
        | each index line links to ONE topic file
        v
   memory/<topic>.md  -- may cite a docs/ artifact for the full proof
```

Rule: a link points to the SINGLE home of that knowledge. No surface copies the
content it links to. Backlinks are optional; forward links are mandatory.

--------------------------------------------------------------------------------
## 3. Lifecycle -- how a learning flows into exactly one place

A new piece of knowledge is classified ONCE, at the moment it is learned, by a
single decision tree run at session-stop (and re-runnable by a memory-writer agent):

```
Is it an always-on constraint the agent must never violate?
  YES -> .claude/rules/<concern>.md  (create or sharpen existing rule). STOP.
Is it a number describing the system's latest measured status?
  YES, and it is a claim about quality/edge  -> docs/JOB_EVIDENCE_PACKET.md. STOP.
  YES, and it is just current status (branch, round, phase, daemon count) -> docs/CLAUDE-state.md. STOP.
Is it a durable lesson / gotcha / experiment verdict / directive?
  YES -> memory topic note (sharpen if it exists, else create) + 1 index line. STOP.
Is it a forward plan / task / roadmap change?
  YES -> .planning/ (GSD skill writes it). STOP.
Is it long-form reference produced by finished work?
  YES -> docs/<area>/  (and add a memory index line pointing to it if it is a lesson). STOP.
Is it a repeatable action?
  YES -> skill / command / agent. STOP.
```

The keystone is **"sharpen if it exists, else create"** for memory: the writer
greps the memory dir for the concept first and edits the existing note in place,
never adds a near-duplicate. This is already the directive in CLAUDE.md's vault
section ("dedup: sharpen the existing entry") -- it is promoted here to the
governing rule for ALL durable learnings.

--------------------------------------------------------------------------------
## 4. Single source of truth for state

**Current mutable state has exactly one human-readable home: `docs/CLAUDE-state.md`.**

- `.planning/STATE.md` -- KEEP, but its scope is narrowed to *GSD milestone/phase
  bookkeeping only* (frontmatter counters + phase list). It is machine-managed by
  GSD skills. It must not carry free-form "what changed this wave" prose -- that
  goes to CLAUDE-state.md / vault Decision Log.
- `CANONICAL_VALUES.md` -- RETIRE as a separate truth source. Its two real jobs
  split cleanly: (a) "do not quote a fixed model count; read it from the registry"
  is a one-line **rule** (or a line in CLAUDE.md Key Paths); (b) any claimable
  number is owned by JOB_EVIDENCE_PACKET. Leave a stub that redirects.
- `vault/Sessions/Decision Log.md` -- the append-only *event log* (one line per
  session, written by the Stop hook). It is history, not the current snapshot;
  CLAUDE-state.md is the current snapshot distilled from it.

So: **JOB_EVIDENCE_PACKET = what is true & claimable** (proof-backed, slow-moving);
**CLAUDE-state.md = what is true right now** (fast-moving status); **Decision Log =
what happened** (append-only). These three are non-overlapping and each is the
sole owner of its slice.

--------------------------------------------------------------------------------
## 5. How hooks keep it current (self-maintenance)

Current hooks (in `~/.claude/settings.json`):
- SessionStart: `gsd-check-update.js` + `update_vault.py` (refresh Home.md)
- PostToolUse: `gsd-context-monitor.js`
- Stop: `vault_session_close.py` (append Decision Log line + refresh Home.md)

Target hook responsibilities (additive, all local; configured via the
update-config skill, never by hand-editing in a way that drifts):

| Event | Hook job | Keeps current |
|---|---|---|
| SessionStart | Refresh vault Home.md (exists); print a 3-line Project Pulse from CLAUDE-state.md + open GSD phase | Agent starts with accurate state, no full-read needed |
| SessionStart | Staleness check: if `docs/CLAUDE-state.md` `last_updated` > N days behind HEAD commit date, emit a reminder line | State file cannot silently rot |
| PostToolUse | (exists) GSD context monitor | Context budget awareness |
| Stop | Append ONE Decision Log line (exists) | Append-only event history |
| Stop | **memory-writer pass**: scan the session transcript for durable learnings; for each, run the sec.-3 decision tree and write to the ONE right place (sharpen-or-create) | Learnings land once, automatically, not lost |
| Stop | **state-distill pass**: if material status changed (new metric, phase flip, daemon count), update the matching line in CLAUDE-state.md | Snapshot stays current without manual edits |

The two new Stop passes are what make the system self-maintaining: every session
that produces a learning or changes state writes it to its single home before the
session ends, so the next SessionStart Pulse is already accurate. They must be
idempotent (sharpen-or-create, edit-in-place) so re-runs do not duplicate.

Guardrails on the hooks themselves: the memory-writer never edits human-gated
paths, never commits data/vault, and obeys the MEMORY.md size limit (it must
prune/merge index lines when MEMORY.md exceeds the 24.4KB budget -- which it
currently does, at 31.6KB).

--------------------------------------------------------------------------------
## 6. Target end-state checklist (each piece in exactly one place)

- [ ] Invariants: ONLY in `.claude/rules/`; MEMORY.md + CLAUDE.md link, do not restate.
- [ ] Claimable/retracted numbers: ONLY in JOB_EVIDENCE_PACKET; rules' blocklist
      points to it; CLAUDE.md carries no live metrics.
- [ ] Current status: ONLY in docs/CLAUDE-state.md; STATE.md = GSD counters only;
      CANONICAL_VALUES retired to a redirect stub.
- [ ] Learnings: ONE memory topic note each + ONE index line; sharpen-or-create.
- [ ] Plans: ONLY in .planning/; their outcomes become a memory line + docs artifact.
- [ ] Self-maintenance: Stop hook writes learnings + distills state; SessionStart
      reads state for the Pulse and flags staleness.

--------------------------------------------------------------------------------
## 7. Top 5 changes to reach cohesion from today's state

1. **De-duplicate invariants into `.claude/rules/` and strip them from CLAUDE.md +
   MEMORY.md.** Today the binding-invariants/gotchas text is restated in MEMORY.md's
   START-HERE block AND in CLAUDE.md's "Rules" section AND enforced in
   `.claude/rules/`. Make `.claude/rules/` the sole owner; replace the other two
   with a one-line pointer. (Removes the biggest overlap and the drift risk.)

2. **Move all live metrics out of CLAUDE.md.** CLAUDE.md's TL;DR currently embeds
   MAE/Brier/ROI numbers -- which both duplicate JOB_EVIDENCE_PACKET and risk
   violating the no-edge-claims rule from the onboarding file itself. Replace with
   "honest numbers + claim rules live in docs/JOB_EVIDENCE_PACKET.md; latest status
   in docs/CLAUDE-state.md." (Apply the existing PROPOSED-CLAUDE.md from the
   org-sprint, which already drafts this slim version.)

3. **Collapse the three state files to one SSOT.** Designate docs/CLAUDE-state.md
   as the single current-state snapshot; narrow .planning/STATE.md to GSD
   counters only; retire CANONICAL_VALUES.md to a redirect stub (its "read counts
   from the registry" line becomes a rule). Eliminates the fan-out where "current
   state" lives in 5 places.

4. **Add the Stop-hook memory-writer + state-distill passes.** This is the
   mechanism that makes the system self-maintaining: at session end, classify each
   learning via the sec.-3 decision tree and write it to its single home
   (sharpen-or-create), and update changed status lines in CLAUDE-state.md. Without
   this, "one right place" is a manual discipline that erodes.

5. **Prune MEMORY.md back under budget and adopt the index-only contract.**
   MEMORY.md is 31.6KB vs a 24.4KB limit, so only part loads -- meaning the index
   silently drops entries today. Enforce "one line <200 chars per memory; detail in
   the linked file; START-HERE = north star + pointers, not a status feed," using
   the org-sprint MEMORY-REORG-PROPOSAL clustering. A truncated index is itself an
   incoherence the hooks must prevent going forward.

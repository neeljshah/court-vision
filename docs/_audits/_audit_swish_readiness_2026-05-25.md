# Swish Analytics Readiness Audit — Final Cold-Reader Pass

*Auditor: Claude (final iter), 2026-05-25 evening · Meeting: 2026-05-25 morning*
*Mode: cold-reader walkthrough as if Swish senior quant auditing github.com/neeljshah/court-vision*

---

## Section 1 — Phase 1 Findings: Recent execute_loop Commits

### Commits since iter-3.5 (`5bf21e97..HEAD`)

```
a49c2771 execute_loop: regenerate observability artifacts after R13
d20942b4 execute_loop R13: L46 EventBus adoption sweep — 4 more producer layers
56faf180 execute_loop: regenerate RUNBOOK + STATE_OF_LOOP after R12
633662b8 execute_loop R12: L42 fully clean + event-driven architecture complete
49010511 execute_loop R11: L46 EventBus adoption (4 producers) + L18 v2 + L49 NEW
```

### Files touched

All 32 files changed (`+5,357 / -184` lines) are scoped to `scripts/execute_loop/`. The only Markdown touched is internal: `scripts/execute_loop/RUNBOOK.md` and `scripts/execute_loop/STATE_OF_LOOP.md`. Every canonical doc — README, CLAUDE.md, ARCHITECTURE.md, CHANGELOG.md, VISION.md, ROADMAP.md, MASTER_PLAN.md, docs/SWISH_DEMO.md, PREDICTIONS_QUICKSTART.md, docs/ML_MODELS.md, docs/CEILING.md — is **unchanged since iter-3.5**.

### Cohesion verdict

**No new claims, no contradictions, no broken links introduced.** The execute_loop iterations are a self-contained refactor (EventBus adoption, layer cleanup, new state-summary layer L49) with their own internal test suite. They do not touch the public-facing story.

The aligned canonical numbers (85 artifacts / ~120 modules / ~49 endpoints / 2,661 tests / 71% acc / +20-28% ROI / 19,964-game holdout / 29 usable CV games) all hold across the chain.

---

## Section 2 — Cold-Reader Walkthrough (Senior Quant Perspective)

### Per-doc impression scores (1-10, where 10 = "I want a follow-up meeting")

| Doc | Score | Key strengths | Notable friction |
|-----|------:|---------------|------------------|
| `README.md` | **9** | Within 200 words: research-machine framing, the 1-3 yr window, the 71% result section is excellent, MAE-vs-median insight visible at line 68, mermaid moat diagram | Mermaid renders are GitHub-dependent; section is long (520 lines) but well-organized |
| `CLAUDE.md` | **8** | Compact task→files routing table; clear invariants; respects local-vs-clone gitignored split | Reads as agent-internal scaffolding — fine for that purpose, not for cold human |
| `ARCHITECTURE.md` | **8** | Six-system ascii diagram + component status table + module ownership map | **Had** an orphaned table fragment at lines 204-209 (no header row) — **fixed in this pass** |
| `CHANGELOG.md` | **9** | Keep-a-Changelog format; 0.15.0 (today's release) has Added/Changed/Fixed/Measured/Lessons sections; honest about the ~26 failing tests | None — this is the most institutional-quality doc in the repo |
| `VISION.md` | **8** | "Why Renaissance" is a strong intellectual frame; structural-arbitrage table is sharp; 6 revenue surfaces explicit | Slightly long opening before performance numbers (line 61); some duplication with README |
| `ROADMAP.md` | **8** | Phase-by-phase week/month/year structure; current-state header at line 8 | Some overlap with `docs/ROADMAP.md` and README §Roadmap (3 roadmap surfaces — but each scoped differently) |
| `MASTER_PLAN.md` | **8** | "Canonical Facts" table (line 24) gives every key metric + source file in one place; honest about R²-vs-MAE divergence | Long (executive summary + thesis + structural arg + history); aimed at deep readers |
| `docs/SWISH_DEMO.md` | **10** | 30-second pitch + headline number table + honest weaknesses + "what we'd build with Swish resources" + reproducibility table at bottom — exactly the interview cheat-sheet a quant would want | None — this is interview-ready |
| `PREDICTIONS_QUICKSTART.md` | **8** | Quick-start CLIs (predict_player, predict_slate, compare_to_lines); cycle 78-82 rejection table is unusually honest | Cycle/loop numbers (R7, cycle 110, etc.) require domain context to parse |
| `docs/ML_MODELS.md` | **9** | Tier discipline (1, 2, 2B, 3-6); q50 architecture decision called out explicitly; pregame vs in-play split at top | Some files referenced (v2 active vs v1 fallback) require digging |
| `docs/CEILING.md` | **9** | Honest "Now" vs "Long-run ceiling" table; CV lift estimates per stat are estimates not promises; agentic-system delta called out separately | None — sober and well-calibrated |

**Average across 11 canonical docs: 8.5 / 10.** Cold-reader impression is institutional-grade.

---

## Section 3 — Top 3 Weakest Spots (with surgical fixes)

### 1. ARCHITECTURE.md orphaned table rows (FIXED in this pass)

Lines 204-209 contained 6 markdown table rows with no header — they were stray rows describing live engine / quantile bands / minute trajectory / daily ops chain / live data feeds / health check that logically extended the "Module Ownership Map" table earlier. A quant reader would notice the rendering glitch (rows render but the header is missing on GitHub).

**Fix applied:** merged the orphaned rows into the Module Ownership Map table. Verified the related-links footer is preserved.

### 2. README §Roadmap line 438 "29 clean games" inconsistency (FIXED in this pass)

The README header (line 13), §"What's Built Today" (line 103), §Layer 1 (line 167), §"Next milestone" (line 307), and §Build Phases (line 386) all correctly cite "29 usable" (with the 9 CLEAN + 20 PARTIAL breakdown shown in two places). But the §Roadmap open-edge row at line 438 used the phrase "29 clean games" — a quant interviewer would spot this as inconsistent with the rest of the doc.

**Fix applied:** changed line 438 to "29 usable games (9 CLEAN + 20 PARTIAL) of 75 attempted" matching the language used at line 307.

### 3. Dual-gate methodology is implicit in README but explicit only in CHANGELOG/SWISH_DEMO (NOT FIXED — minor)

The "dual gate" — 4/4 walk-forward folds positive AND production single-split MAE strictly down — is the single most differentiated methodology choice in the loop. It's named explicitly in:
- `CHANGELOG.md` line 89 ("dual gate (4/4 WF folds positive AND production single-split MAE strictly down)")
- `docs/SWISH_DEMO.md` section "Full walk-forward gate" (line 82)

README line 68 mentions "Walk-forward, not random holdout — the only honest gate" — which captures the spirit, but not the specific dual-gate rule. A senior quant interviewer is likely to probe on this, and the SWISH_DEMO doc is correctly the place to land them. Recommendation: leave README as is (it's already 520 lines) and rely on the SWISH_DEMO link in the README header (already present at line 11) to surface this. **No fix applied** — the SWISH_DEMO doc is the right surface.

---

## Section 4 — Swish-Specific Checks

| # | Check | Pass/Fail | Evidence |
|---|-------|----------|----------|
| 1 | docs/SWISH_DEMO.md has all headline numbers a quant interviewer would test | **PASS** | Pre-game MAE table (line 21), in-game endQ3 vs pregame -43 to -53% table (line 33), endQ1 period head -37% (line 47), in-game ROI by snapshot table (line 56), win prob 0.7094 acc / 0.193 Brier (line 65), reproducibility table at bottom (line 159) |
| 2 | Dual-gate WF methodology explained somewhere visible | **PASS** | README line 68 "Walk-forward, not random holdout — the only honest gate"; SWISH_DEMO line 82 "Full walk-forward gate" with explicit 4/4 + single-split rule; CHANGELOG line 89 has the canonical statement |
| 3 | q50 vs mean-loss insight visible ("market scores against the median") | **PASS** | README line 76 ("MAE is the betting-relevant metric (sportsbook prop lines score against the median, not the mean)"); SWISH_DEMO line 79 ("Sportsbook O/U props score against the median, not the mean — q50 models are structurally aligned to that loss. BLK MAE improved -16.6% in one swap"); ML_MODELS.md line 44 (full architectural rationale); README §Results line 299 (one-paragraph callout) |
| 4 | Honest limitation set documented (no live injury feed, no real line data, no CLV vs Pinnacle yet) | **PASS** | SWISH_DEMO §"Honest Weaknesses" (line 93) — all 5 caveats including L5 proxy not real lines, pregame at ceiling, sparse 2025-26 DNP, CV not at scale, in-game backtest uses L5 not live lines; README line 13 ("Gate 1 (CLV vs Pinnacle close) not yet run — top priority"); ROADMAP.md line 16 (same); MASTER_PLAN.md line 50 ("Gate 1 status: NOT YET RUN") |
| 5 | CV pipeline differentiator clearly stated (build from broadcast vs buying Second Spectrum) | **PASS** | README line 147 (table row: "$15M Second Spectrum contract" vs "YOLOv8n + SIFT homography, $0.40/hr GPU"); README line 394 ("The differentiator is that CourtVision works from broadcast video, not from arena-installed camera rigs — so it covers college, G-League, and international games at the same cost as NBA"); README mermaid §System Architecture line 277 explicitly labels the CV-features block as "the moat"; VISION.md line 59 ("Converts broadcast video to court-coordinate spatial features") |

**5/5 Swish-specific checks PASS.**

---

## Section 5 — VERDICT

### GREEN for tomorrow's meeting.

The github story is institutional-grade and ready for a senior-quant cold read. Three iterations of audit polish + this final pass have produced:

- A canonical chain (README → CLAUDE → ARCHITECTURE → CHANGELOG → VISION → ROADMAP → MASTER_PLAN → SWISH_DEMO → PREDICTIONS_QUICKSTART → ML_MODELS → CEILING) where every numeric claim is consistent with every other canonical doc
- Headline numbers (85 artifacts / ~120 modules / ~49 endpoints / 2,661 tests / 71% acc / +20-28% ROI / 19,964-game holdout / 29 usable CV games / Gate 1 not yet run) repeat verbatim across all surfaces a Swish reviewer might click into
- Honest weaknesses (CLV not yet measured, L5 proxy not real lines, pregame at ceiling, CV not yet at scale) are documented in the visible places (README header, SWISH_DEMO §Honest Weaknesses, MASTER_PLAN Canonical Facts table)
- The three differentiation moments a quant interviewer will test (walk-forward dual gate, q50-against-the-median, broadcast-CV-vs-Second-Spectrum) are all visible in both the README and SWISH_DEMO

Recent execute_loop commits (R11-R13, 5 commits, +5,357 lines) are confined to `scripts/execute_loop/` and do not touch any public-facing doc. The canonical story is stable.

### Fixes applied tonight in this pass

1. **ARCHITECTURE.md** — merged 6 orphaned table rows (lines 204-209) into the Module Ownership Map table. Removes a visible rendering glitch a careful reader would spot.
2. **README.md** — line 438 §Roadmap row corrected from "29 clean games" to "29 usable games (9 CLEAN + 20 PARTIAL) of 75 attempted" to match the canonical breakdown used elsewhere in the same doc.

### Top 3 things to consider tonight if time permits (NONE are blockers)

1. **Print a 1-page hardcopy of `docs/SWISH_DEMO.md`** — 167 lines, dense with numbers, exactly the cheat-sheet a quant interview needs across the table. It's the single highest-leverage doc.
2. **Have `scripts/swish_demo.py` ready to run live** — the README references it (line 11) and SWISH_DEMO references it (line 149). A live "watch the model snap to a snapshot in front of you" is the closer.
3. **Memorize the 3 honest weaknesses** (no real lines / pregame at ceiling / CV not at scale) and the 3 directly-tied next builds (real line feed / live injury feed / 80-game CV ingest). Lead with the weakness, follow with the planned closing move — this is the credibility pattern that quant interviewers reward.

### What NOT to do tonight

- Do not touch `scripts/execute_loop/` — the bot loop is mid-iteration and any local change risks merge conflicts on the next push.
- Do not touch `docs/SWISH_DEMO.md` — it's at 10/10 cold-reader score; any edit risks introducing inconsistency.
- Do not regenerate canonical numbers — the 85/120/49/2661/71%/20-28%/19,964/29 set is now locked across the entire doc chain.

---

*Final auditor note: this is the user's last verification pass before the Swish Analytics meeting tomorrow. The repo presents as a serious, AI-native, honestly-validated sports research platform with a clear methodology (walk-forward dual gate), a clear edge (CV from broadcast + q50 quantile loss), a clear honest limitation set (Gate 1 pending, real lines pending, CV not at scale), and a clear next build (real line feed → Gate 1 → 80-game CV). That is exactly the right first impression for a Swish quant.*

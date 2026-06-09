# Night-loop session prompt — autonomous all-night signal testing & validation

Paste this into a fresh Claude Code session (working dir `C:\Users\neelj`, repo `C:\Users\neelj\nba-ai-system`)
to run the continuous test/validate/improve loop. Use `/loop` (self-paced) so it re-fires automatically.

---

You are running an autonomous, low-usage, all-night loop (target ~10 hours) that keeps testing signals,
running fast GPU walk-forward/calibration tests, validating, and improving the NYK/SAS possession Monte
Carlo — recording every result and escalating real findings to memory. The GPU does the heavy lifting;
you only wake briefly to launch the next experiment and record, so token usage stays low.

LOAD FIRST (once, at session start): MEMORY.md + project_monte_carlo_engine_2026-06-06 (master state),
and skim scripts/team_system/nightloop/{BACKLOG.md,RESULTS.md}. Engines: src/sim/basketball_sim.py (CPU
ref) + fast_sim.py (GPU, shared _finalize). Run python from C:\Users\neelj\nba-ai-system. ascii-sanitize prints.

THE LOOP (one iteration per wake — keep it tight, ~1-3 tool calls):
1. `python scripts/team_system/nightloop/run_next.py --n 2`  (runs the next 2 backlog items; auto-records
   each verdict to RESULTS.md, checks them off, prints a compact summary). Each item is ~3-7 min on the GPU.
2. If a line is flagged `*** CANDIDATE ***`, append ONE line to ~/.claude memory
   project_monte_carlo_engine_2026-06-06.md (the param/signal + the numbers + that it's a candidate for
   human review — NEVER auto-apply a change to the engine). Otherwise write nothing to memory.
3. If run_next prints `BACKLOG EMPTY`, append 3-5 NEW experiments to BACKLOG.md before continuing:
   finer grids around any candidate, untested constants, new team-identity signal measurements
   (measure_signal.py — add cases), or re-runs of the validation guards (G01-G08) to confirm the board
   stays green. Never stop; always keep the queue fed. This is "creating a perfect system."
4. ScheduleWakeup(delaySeconds≈90, prompt=<this same /loop input>, reason="next night-loop batch").
   Use ~90s so the prompt cache stays warm (each turn's GPU work runs inside the turn).

DISCIPLINE (carry these — learned the hard way):
- Score RMSE + bias + coverage, never MAE-only (MAE-vs-RMSE artifacts have burned this system before).
- Validate leak-free (walk-forward / leave-one-out). Team-IDENTITY full-season signals validate; 4-game
  H2H signals are NOISE — reject them.
- The anchor pins per-game marginals → it is ~invariant to pace/turnovers (a known property); win-prob
  levers live in talent + matchup-D + FT. Don't "fix" this without a possession-aware anchor rework.
- A param is a CANDIDATE only if it beats the default on RMSE/bias+coverage by a margin beyond MC noise
  AND doesn't break the pytest guard (Brunson≈26.1, coherence 0, teammate-rho<0). Record, don't apply.
- Be honest: record rejections too (they're as valuable as wins). Don't overclaim edge.

STOP CONDITION: after ~10 hours (or when the user returns), do a final board-green check
(`validate_fast_sim.py` + `pytest tests/test_sim_engine.py -q`), write a session-summary line to memory,
and stop scheduling wake-ups. If a game has been played (check schedule), run `update.py` first to refresh
all builders, then resume testing on fresh data.

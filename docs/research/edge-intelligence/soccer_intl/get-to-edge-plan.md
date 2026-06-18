# soccer_intl -- GET-TO-EDGE PLAN (prioritized path: quick wins -> big bets)

_Part of the edge-intelligence corpus. The concrete, prioritized path from where the WC prop
vertical is today (a thin but honest calibrated board) to a PROVEN edge -- each step with approach
+ how it is validated (calibration vs CLV). Markets are mostly efficient; the realistic destination
is a trustworthy calibrated board where 2-4 markets carry real OOS skill and ONE (Saves) is a
plausible CLV candidate. No $-edge is claimed. Grounded in deep-dives 04 + 06 and the code. ASCII._

## Starting point (honest)
- 24 WC events, every player 1 match (espn_player_stats.parquet); 960/1241 players club-prior-backed.
- ONE proven-calibration stat: Saves (bss +0.3365) -- suggestive on correlated n, partly structural.
- Four marginal stats: Fouls/Fouls-Drawn/Shots/SOT. Five weak/cut: Cards/Assists/Goals/G+A/Offsides.
- CLV = 0 captured (prop_line_history ~1 row). Self-improve ratchet: 48/48 INSUFFICIENT_DATA.
- The proving spine (eval-gate, walk-forward, DM, tiering) is rigorous and ready; the gap is DATA +
  CLV CAPTURE, not algorithms (06 sec 7).

## Phase 0 -- QUICK WINS (days; data + ops + correctness, no model risk)

1. **Capture closing lines (CRITICAL, ops).**
   - Approach: schedule prop_line_history.log_board_lines to tick every ~10-15 min up to kickoff over
     the tournament window (06 sec 6 #1). The code exists; this is scheduling.
   - Validate: prop_line_history.jsonl grows past 1 row; clv_summary reports n_with_real_close>0.
     This UNBLOCKS every edge claim -- nothing graduates without it.

2. **Keep ingesting matchdays + re-run the cache.**
   - Approach: after each matchday run `ingest_espn_players` + `ingest_espn_athlete`, then
     `python -m scripts.platformkit.props_eval --cache` (04 sec 6 #1).
   - Validate: leak-free per-player WC rates begin to exist (players reach 2+ matches); per-stat bss
     recomputed OOS. This is the dominant lever -- the vertical mostly improves by waiting.

3. **Surface effective-N (distinct matches), not pooled n=662.**
   - Approach: add a clustered/match-based N to prop_calibration.json and require proven to also
     clear a distinct-match count (06 sec 6 #4; 04 sec 6 #3).
   - Validate: "proven" can no longer be mis-read as 662 independent samples; Saves stays proven only
     if it clears the match-based bar too.

4. **Fix per_start->per90 denominator + expand _NAME_TO_ABBR + resolver-coverage report.**
   - Approach: use appearances not starts (model-levers #10); fill the WC nation map
     (soccer_team_map.py); add resolved/unresolved/opp-mapped counts to the board payload.
   - Validate: re-run cache -- removing spurious OVER edges is a NULL/negative delta = success;
     resolver coverage becomes a monitored health metric (kills the top fake-edge risk).

## Phase 1 -- MEASURE THE HIDDEN ERROR (weeks; converts unmeasured risk to measured)

5. **Backtest with PROJECTED minutes (not realized).**
   - Approach: run props_eval feeding `player_minutes.expected_minutes` instead of realized minutes
     (04 sec 6 #5; model-levers #3).
   - Validate: report the calibration GAP vs the realized-minutes backtest. Expect some stats to
     re-tier DOWN honestly. A downgrade here is a success (proof-standards: honest downgrades).

6. **Position-conditioned dispersion + baseline (keepers vs outfielders).**
   - Approach: split phi and the position baseline by role (data has G/CD/CM/AM/SUB etc).
   - Validate: per-stat OOS Brier improves on >=2 independent matchdays; gate via recal_eval-style
     temporal split; ship only if non-regressing (the ratchet, self_improve.py).

7. **Re-test opponent-adjust + isotonic recal as N grows.**
   - Approach: re-run the +opp-adj cache and recal_eval each matchday.
   - Validate: opp-adj ships only if OOS Brier improves on >=2 matchdays (currently null, lever #5);
     recal re-enables only when the in-sample-vs-OOS overfit gap (+0.01003) closes (lever #6).

## Phase 2 -- GRADUATE TO CLV (weeks-months; the actual edge proof)

8. **Build the CLV-proven top tier in prop_tiering.**
   - Approach: once N settled prop bets with real positive CLV accumulate for a stat, promote to
     CLV_PROVEN above CALIBRATION_PROVEN; reuse diebold_mariano on per-bet CLV clustered by match
     (06 sec 6 #7). The tier ladder is currently only two tiers in practice.
   - Validate: a stat reaches CLV_PROVEN only with cluster-robust CI(CLV)>0 -- the market's own
     verdict that we were ahead of the close.

9. **Prove Saves first (the only candidate), then Fouls/Fouls-Drawn.**
   - Approach: paper-accrue Saves edges (prop_paper, only_reliable=True) with closing lines captured;
     focus on low-attention/rotation keepers x heavy-underdog teams (inefficiency-catalog S1).
   - Validate: P(over) calibration vs realized (already strong) PLUS forward CLV-vs-close / DFS
     line-movement (edge-theory.md DFS note). CRITICAL: because Saves bss is partly structural, the
     proof MUST be CLV/movement, not re-confirming the near-trivial .5-line calibration.

## Phase 3 -- BIGGER BETS (months; data-bound, only if vertical is a priority)

10. **Predicted-lineups minutes model (lever #11).** Ingest probable XIs / injury news to sharpen
    expected_minutes -- where most live-board error actually lives. Validate: OOS calibration of
    minutes vs realized; conditional P(over) on lineup-confirmed rows.
11. **Joint / correlated props (lever #12).** Shared-latent shot-volume -> coherent Shots/SOT/G+A;
    unlocks SGP pricing (P5). Validate on the FULL stat-pair surface, not just the dominant pair.
12. **Multi-tournament prior corpus (data).** Prior WC / continental / club leagues as a 2nd
    INDEPENDENT corpus to confirm any per-stat skill OOS before promoting (proof-standards #4).

## The destination (honest ceiling)
A well-calibrated, honestly-tiered WC prop board where Saves is CLV-tested and 2-3 more
(Fouls/Fouls-Drawn first) are calibration-proven, with the rest correctly demoted. The binding
constraints, in order: (a) DATA DEPTH (waiting for matchdays + a 2nd corpus), (b) MINUTE-PROJECTION
error (Phase 1 step 5), (c) MARKET EFFICIENCY (caps any $ claim regardless of calibration). The
realistic best is a trustworthy calibrated decision-support product with ONE plausible CLV-edge cell
(low-attention keeper Saves), not a profit engine -- and that is a defensible, honest outcome.

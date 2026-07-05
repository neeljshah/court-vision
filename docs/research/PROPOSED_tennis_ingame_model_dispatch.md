# PROPOSED: nba/tennis model dispatch in live_board.live_model_home_prob

**Status:** PROPOSED (diagnosis only; human-gated -- `live_board.py` is on the
human-gated-paths list, this lane does not edit it). LANE 3, 2026-07-05 wave.

## What this closes (evidence, not speculation)

Root-caused why the tennis in-play channel's `corpus_labeled` metric reads
`[0,0]` despite live ticks flowing every cycle. **The settle-labeling chain
works correctly for tennis; the tick-capture chain does not; the two symptoms
were previously conflated.**

Evidence gathered live, 2026-07-05 ~20:37 UTC (all read-only, reproducible):

1. `inplay_kalshi.fetch_inplay("tennis")` returns 17 real in-play legs today
   (Fritz/Bublik, Dimitrov/Fery, Zverev/Lehecka, de Minaur/Cobolli,
   Sinner/Mochizuki, plus 5 WTA pairs). Ticks flow fine.
2. `ingame_live_state.live_states("tennis")` returns 2 distinct ESPN live
   matches today (Sinner/Mochizuki, Bencic/Gauff). The team-name bridge
   (`inplay_capture_loop._scan_live_by_legs`) correctly matches
   `KXATPMATCH-26JUL05SINMOC` <-> ESPN `177476` (Sinner/Mochizuki) -- **the
   bridge is not broken**.
3. A live `poll_once(sports=["tennis"])` call against that matched game
   returns `reason: "no_model_prob"` (not `"no_live_state"`), confirming the
   pipeline reaches `_process_game`'s `model_p = _prob01(md_fn(sport, state))`
   line and dies there because
   `live_board.live_model_home_prob("tennis", state)` returns `None`
   unconditionally -- `live_board.py`'s dispatch (~L123-160) branches only on
   `mlb` and `soccer`/`soccer_intl`; there is no `nba` or `tennis` arm.
4. Corpus-wide check of `data/cache/ingame_grade/tennis/*.jsonl` (572 files,
   every file ever written for this sport): **every single file contains
   exactly one line -- the `settle_stamp.stamp_final` row** (`{"settled":
   true, "home_win": 0.0|1.0, ...}`). Zero files contain a captured
   `model_prob`/`yes_home_prob` tick row. `max_lines_in_any_file == 1` across
   the full corpus, not a sample.
5. This means `settled_finals` + `settle_stamp` (the ESPN-final-detection +
   sets-won-derived `home_win` label writer) work correctly end-to-end for
   tennis -- 572 real, correct labels exist -- but they land on grade files
   `_stamp_final` creates FRESH (keyed by the numeric ESPN event id), because
   `on_tick`/`capture_pair_once` never created that file first (it would have
   been keyed by the Kalshi ticker string, and zero such files exist in the
   corpus at all -- `0` non-numeric-keyed filenames).
6. `inplay_aggregate_grade`'s OUTCOME arm (the arm that needs a settled label)
   gates on `g["outcome"] is not None AND g["d"]` (a non-empty per-state
   Brier-diff list) -- so even though 572 real settled outcomes exist,
   `n_settled_games` is 0 because zero of those games ever had a ticked row to
   compute a Brier diff from. This is the direct mechanism behind
   `corpus_labeled=[0,0]`.

## Root cause (single point, not two problems)

`scripts/platformkit/frontend/live_board.py::live_model_home_prob`'s sport
dispatch has no `nba` or `tennis` branch (confirmed by direct call: returns
`None` for a real live tennis state today). This is the SAME gap
`inplay_capture_loop.DEFAULT_SPORTS`' existing npb/kbo comment already
documents as "no live model wired... deliberate (no live model exists yet)".
Tennis and NBA are NOT in that same category, though: unlike npb/kbo, both
sports DO have a real, already-shipped, calibrated `predict_live` (NBA:
W146/W156 temperature-recalibrated repricer; tennis: W156 Platt-on-logit
in-game recal) reachable via `predictor_jd._build_predictor`, AND a separately
REPLICATED, proven base+prior calibration surface
(`data/cache/ingame/models/{nba,tennis}_ingame.json`, `verdict: "REPLICATED"`,
`prior_status: "proven"`, n_games=2634/40588) built by
`scripts.platformkit.ingame.ingame_serve` that nothing serves into a live
tick either.

This wave's shadow modules (`domains/basketball_nba/ingame_shadow.py`,
`domains/tennis/ingame_shadow.py`, wired into `inplay_capture_loop.
_process_game` the same way `_wnba_shadow`/`_sp_shadow` already are) surface
the `predictor_jd`-side model as an ADDITIONAL measurement field
(`model_prob_nba_shadow`, `model_prob_tennis_shadow`), so its calibration can
be tracked once ticks start landing. **They do not close this gap by
themselves**: because the shadow calls sit AFTER `_process_game`'s
`model_p is None -> return row` early exit (the same structural position
`_wnba_shadow` already occupies -- confirmed live: wnba's shadow field is
also `None` on a `no_model_prob` tick today), the shadow fields only populate
once a tick is captured at all, which for tennis/nba does not happen at 100%
today.

## The actual fix (why it is PROPOSED, not built)

Add `nba` and `tennis` branches to `live_board.live_model_home_prob`,
following the existing `mlb` branch's shape (thin dispatch to a domain-side
`*_live_model.py` helper, or directly to `predictor_jd._build_predictor(sport)
.predict_live(...)`), OR promote `ingame_serve.serve_ingame` (the proven
base+prior surface) into the dispatch instead of the raw predictor. Either
choice is a decision about which of two already-REPLICATED models becomes
the FIRST thing tennis/nba tick capture depends on for real -- exactly the
class of decision `live_board.py`'s human-gated-paths status exists to
protect, and the two candidate models (repricer-based vs
ingame_serve-based) are not byte-identical, so picking one is a real choice,
not a mechanical wire-up.

**Not proposing a diff here** because both candidate implementations are
substantive (not a 3-line patch) and the choice between them is exactly the
kind of decision the human-gated-paths rule reserves. Recommend: pick
`ingame_serve.serve_ingame` (the ALREADY-PROVEN, ALREADY-REPLICATED artifact,
vs the repricer path which has never been through that same replication
gate) as the served model, so tennis/nba's FIRST live-tick capture depends on
what this codebase's own honesty ladder already calls proven, not on an
unaudited alternate path.

## What this fix would unlock (measurement, not edge)

Once wired: tennis/nba ticks stop dying at `no_model_prob`, `on_tick` starts
writing real (model_prob, devigged_price) pairs, `settle_stamp`'s ALREADY
572-deep tennis label corpus stops being orphaned, and
`inplay_aggregate_grade`'s OUTCOME arm can finally see `n_settled_games > 0`
for tennis -- turning `corpus_labeled` from a permanent `[0,0]` into a real,
growing number. This is calibration measurement infrastructure, not an edge
claim; no $ /ROI framing applies.

## Files referenced (all read-only during this diagnosis)

- `scripts/platformkit/frontend/live_board.py` (the gap; NOT edited)
- `scripts/platformkit/ingame/inplay_capture_loop.py` (`_process_game`,
  `_default_model_fn`, `_stamp_final` -- edited only to add the two new
  shadow wrappers, see LANE 3 wave commit)
- `scripts/platformkit/ingame/settled_finals.py`,
  `scripts/platformkit/ingame/settle_stamp.py` (verified working correctly)
- `scripts/platformkit/ingame/inplay_aggregate_grade.py` (OUTCOME arm gate)
- `scripts/platformkit/ingame/ingame_serve.py` +
  `data/cache/ingame/models/{nba,tennis}_ingame.json` (the proven,
  unserved artifacts)
- `domains/basketball_nba/predictor.py`, `domains/tennis/predictor.py`
  (the repricer-based alternative)
- `data/cache/ingame_grade/tennis/*.jsonl` (572 files, corpus-wide evidence)

## INDEPENDENT CONFIRMATION (separate trace, 2026-07-05 ~21:30 UTC, ~1h later)

A second, independently-run diagnosis (different entry point: the brief named
`ingame_outcome_verdict_multi.py`'s live `SPORT=tennis n_files=0 n_labeled=0`
render, not `inplay_aggregate_grade`'s `corpus_labeled`) reached the **same
terminal root cause** via a different downstream consumer. Recorded here
rather than as a second file so the two traces stay one diagnosis, not two.

**Live reproduction, this trace:**
- `feed_health.scan(["tennis"])` right now: `espn n_events=0`, `kalshi
  n_events=0`, `pinnacle n_events=12`. This is the exact evidence shape named
  in the task brief ("13 live pinnacle tennis events... espn n_events=0").
  **This does NOT describe the capture-loop's actual state resolution** --
  `feed_health`'s `kalshi`/`espn` probes go through
  `odds_provider.aggregate.default_providers()` (pregame odds-comparison
  stack), a completely different code path from
  `ingame_live_state.live_states("tennis")` (the one `inplay_capture_loop`
  actually calls). Direct call confirms the REAL capture path sees 3 live
  ESPN tennis matches right now (Bencic/Gauff, Arseneault/Osuigwe) and the
  Kalshi in-play feed carries 9 distinct tennis tickers, one of which
  (`KXWTAMATCH-26JUL05BENGAU`) has already started. **The bridge
  (`_scan_live_by_legs`) is not broken today** -- same conclusion as the
  first trace's point 2, reconfirmed an hour later with different matches.
- Bonus, separate, smaller bug found while tracing `feed_health`'s ESPN
  probe specifically: `odds_provider/espn.py::EspnProvider.fetch` (used ONLY
  by `feed_health`/`aggregate.default_providers()`, NOT by
  `ingame_live_state.py` or the capture loop) treats every tennis scoreboard
  event as a flat match (`comp = (ev.get("competitions") or [{}])[0]`).
  Tennis events are tournaments with `competitions: []` at the top level
  (real matches nest under `groupings[].competitions[]` --
  `ingame_live_state.py` already handles this correctly via
  `_tennis_matches`/`_events_for`). So `EspnProvider.fetch("tennis")`
  structurally returns `n_events=0` ALWAYS, live or not -- this is why
  `feed_health` shows `espn n_events=0` even though 3 tennis matches are
  live right now. Real, provable, but scoped to the pregame-odds-comparison
  probe (`feed_health`/`aggregate.py`, not `tennis_*`-owned, not touched
  here) -- does not affect state resolution or settlement.
- `ingame_outcome_verdict_multi.build_verdict_for_sport("tennis")` live
  today: `n_files=0 n_labeled=0`, reproducing the brief's `corpus_labeled=0`
  claim exactly. Traced to the SAME terminal cause as the first trace
  (`live_board.live_model_home_prob` has no tennis branch), via a
  DIFFERENT and more precise mechanism than "0-line files": every one of
  the (now 573) tennis grade files contains exactly ONE line -- the
  `settle_stamp` row `{"sport":"tennis","game_id":"<espn_numeric_id>",
  "settled":true,"home_win":0.0|1.0,"state_summary":"FINAL",
  "edge_claimed":false}` -- with **no `market_prob`/`model_prob` keys at
  all**. `live_grade._load_pairs` (called by
  `ingame_outcome_verdict.build_verdict` via `_brier_by_game_segment`)
  requires both keys present and valid; a file with neither returns `rows =
  []`, which hits `if not rows: continue` BEFORE `n_files` is ever
  incremented -- so `n_files=0` in this specific tool's output means
  "zero files had a real tick," not "zero files were discovered" (573 WERE
  discovered via `_seg._discover`, confirmed directly).
- Separately (and NOT itself a bug, just a design fact worth recording for
  whoever eventually wires the model): even once ticks start landing, this
  verdict tool's `_brier_by_game_segment` looks up the outcome via
  `outcome_fn(gid)` where `gid = rows[0]["game_id"]` -- literally whatever
  ID happened to land in the tick row. Cross-sport check of the SAME
  verdict tool's inputs: `soccer_intl`'s grade files ARE correctly
  Kalshi-ticker-named (43/47, e.g. `KXWCGAME-26JUL01BELSEN.jsonl`, 252 real
  paired lines) because `_process_game` reaches `_dt.on_tick(sport, gid,
  ...)` (which writes the tick keyed by the Kalshi-ticker loop variable)
  BEFORE any settle stamp exists -- `SoccerOutcomeResolver.final_score`
  then correctly receives that same Kalshi ticker. Tennis's `on_tick` call
  is never reached (the `no_model_prob` early-return sits upstream of it),
  so the ONLY grade file tennis ever gets is `_stamp_final`'s
  ESPN-numeric-id-keyed stamp -- a namespace `TennisOutcomeResolver.home_win`
  (correctly, by its own Kalshi-ticker-native design, shared with
  `WnbaOutcomeResolver`) cannot parse. This is a DOWNSTREAM consequence of
  the same live_board gap, not an independent bug in
  `tennis_outcome_resolver.py` -- confirmed `TennisOutcomeResolver` resolves
  correctly on real Kalshi tickers in its own designed callers
  (`ingame_tail_scan_multi.py`, `ingame_paper_settle.py`), and correctly
  returns `None` (not a bug) for `KXWTAMATCH-26JUL05BENGAU` right now
  because that match is still live (no `winner=True` yet) -- it will
  resolve once the match finishes. Once `live_board` gets a tennis branch,
  `on_tick` starts writing Kalshi-ticker-keyed files for tennis too and this
  verdict tool's `n_files`/`n_labeled` will move for the same reason
  `inplay_aggregate_grade`'s `corpus_labeled` will.

**Net: no new root cause, no fix needed beyond what's already proposed
above.** Two independent traces, two different downstream consumers
(`inplay_aggregate_grade` and `ingame_outcome_verdict_multi`), one terminal
cause (`live_board.live_model_home_prob` has no tennis dispatch branch), both
confirming the settle/label side and the state-resolution/bridge side are
each independently correct. No `inplay_capture_loop.py` edit made (owned by
a different lane this wave); no scraping infra added; nothing committed.

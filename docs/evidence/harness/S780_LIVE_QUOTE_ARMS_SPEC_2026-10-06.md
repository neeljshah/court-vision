# S780 -- per-sport live paper quote arms (nfl, nba, soccer, tennis) -- SPEC ONLY

PAPER ONLY. Hypothetical maker quote INTENTS from captured shards; no network, venue client, executor or
order path. Calibration and execution-quality wording only. Owner directive 2026-10-06 ~00:5xZ: the desk
quotes LIVE (paper) during games for every served sport, quant grade. Author: live paper quoting lead. (Briefed as S778; S778 was taken by the issues lead (dc133cc21) and S779 is held for the nba + soccer scoring lead, so this row is S780.)

## 1. Before-condition (measured 2026-10-06 00:5xZ, master)

- Intents exist for MLB only: `data/cache/live_shadow/mlb/2026-09-29.jsonl` and `2026-09-30.jsonl`
  (1,014 arm rows, 2 games); no other sport directory under `data/cache/live_shadow/`.
- `live_shadow_cli.py` main: `--sports` `choices=["mlb"]`; `live_shadow_fills_io.py` main: `--sport`
  `choices=["mlb"]`; `live_shadow_quoter.decide` builds MLB p0 and the MLB live model only.
- NBA slice S518 is BUILT + two-tier VERIFIED and PARKED on `harness-h281` (22b05fb04: new modules
  `live_shadow_nba.py`, `live_shadow_nba_prior.py`, a lazy dispatch in `live_shadow_cli.py` and
  `live_shadow_io.py`, S519-pinned files untouched). Not on master.
- Captured inputs exist for every target sport: `data/cache/ingame_books_local/kalshi/{nba,nfl,soccer,
  tennis}` and `data/cache/ingame_state_local_v2/state/{nba,nfl,soccer,tennis}`.
- Served schedule: the paper-desk config serves mlb + nfl today; nba + soccer from 2026-10-07 (switch 1,
  aa8b4b586); tennis behind switch 2. NFL served games today get NO live intents.
- The sealed scoreboard (`scripts/platformkit/execution/ingame_scoreboard.py`) defines the arms:
  A = the tick's mid untouched; B = mid-only walk-forward recalibration; C = mid + `SEALED_FIT_FEATURES
  [sport]` (nba: score_diff, quarter, seconds_remaining; nfl: score_diff, period, game_seconds_remaining,
  down, distance, possession_is_home, home/away timeouts; soccer: score_diff, minute, red cards + present
  flags); fit path `baseline_four_arm.predict_rows`, window = strictly earlier nights settled before the
  night minus 3 days (embargo 3); tennis: no regulation clock and no FEATURES entry.

## 2. Row

Add live quote arms per sport that price from the SAME sources the sealed scoreboard scores, so the live
paper intents and the nightly scoreboard measure one object:

| sport | arm `mid` (scoreboard A) | arm `scoreboard_b` (B) | arm `scoreboard_c` (C) | model arm |
|---|---|---|---|---|
| nba | yes | yes | yes | S518 `nba_logistic` (land the parked slice first; unchanged) |
| nfl | yes | yes | yes (NFL completeness via `nfl_eligibility`) | none |
| soccer | yes, per outcome ticker (home / tie / away) | yes | yes | none |
| tennis | yes | yes | NO (no FEATURES; state = sets only) | none |

Pricing of B and C: coefficients are a FROZEN FIT ARTIFACT, never fitted inside the recorder:
`data/cache/live_shadow/_fits/<sport>/<D>.json` = output of `predict_rows`' fit on the nights the sealed
policy allows for scored date D (strictly earlier nights, settled before D-3), with the training-row
digest, the policy digest and the code digests recorded. A new offline CLI
`scripts/platformkit/execution/live_shadow_fit.py --sport S --date D` writes it once per day (dispatcher,
after the night). The recorder reads the artifact for t's UTC date; a missing, mismatched-policy or
non-finite artifact gives `no_quote` reason `fit_missing` / `fit_refused` (counted), never a fallback.
Fewer than the policy's minimum prior rows = `fit_warmup` (counted).

AMENDED 2026-10-06 ROUND 2 (reason: under the tick-day rule a US-evening game starting before midnight UTC
on D crossed into D+1 and switched to a D+1 fit not yet produced, so the rest of the game hit
`fit_missing`; round-1 review): (i) the recorder reads the artifact for the GAME's `scheduled_start` UTC
day, not the tick's day, so one game keeps one fit for its whole run (an unparseable start = counted
`schedule_start_invalid`); (ii) the fit for day D+1 is produced DURING day D: it needs only games settled
before (D+1)-3 = D-2, complete before D starts, while D's own history is written 06:37Z-18:44Z on D, so
a game starting late on D never waits on a fit; (iii) the fit CLI accepts `--day D+1` while the clock is
on day D and refuses (`fit_not_due`, counted, no artifact) only when the clock is before the embargo
boundary (day - 3) 00:00Z. Population (round 2): B and C share the sealed STATE-COMPLETE, HOME-ORIENTED
population (`ingame_scoreboard_amendment.py:34`, `ingame_scoreboard_rules.py:153`): away/tie tickers =
`not_home_oriented`, a state the sealed `tick_row`/`state_eligibility` cannot encode = `state_incomplete`,
both counted for B and C alike; `fit_refused` only for a fit that fails to apply. Pre-live ticks are
priced by B/C exactly when the sealed `tick_row` encodes them (the scorer's `pre-live` segment).

Quote construction: unchanged `quote_engine.make_quotes` around the arm's probability (cents, 1..99),
qty 1 per side, `independent_intent_zero`, expiry = every_s * 2, per-side quote ids. Book freshness bar
`quote_freshness.state_age_ceiling_sec(sport)`; state bar per sport in the S518 manner (nba 30 s; nfl,
soccer, tennis measured from the state cadence census before build, written into the build memo).

Orientation: each ticker prices its own yes event (scoreboard rule); soccer = three tickers per game, each
an independent intent stream; the tie ticker uses `score_diff == 0` orientation exactly as
`ingame_scoreboard_rules.ticker_outcome`.

Schema: identical `live_shadow_v1` arm rows (runbook section 6) with `sport` set, plus `fit_date` and
`fit_sha256` on B/C rows (null on mid). Shards at `<out>/<sport>/<D>.jsonl`. MLB rows byte-identical to
master (pinned fixture `mlb_run_row_pre_change.json` from S518 reused).

Process shape: ONE child process for all sports (`--sports mlb,nba,nfl,soccer,tennis`), lazy per-sport
dispatch (S518 pattern), so the RAM bar stays one process: peak <= 150 MB with 3 simultaneous live games
across 2 sports, measured; the recorder lock stays one per out-root.

Files: NEW `live_shadow_sport.py` (dispatch + B/C pricing), `live_shadow_fit.py` (fit CLI),
`live_shadow_soccer.py` (three-outcome orientation), each <= 300 lines; minimal edits to
`live_shadow_cli.py` (choices + comma list) and `live_shadow_io.py` (shard path per sport, already in
S518) and `live_shadow_fills_io.py` (`--sport` choices; books path per sport). NEVER edit the S519-pinned
`live_shadow_quoter.py`, `blend_apply.py`, `mlb_live_model.py` (a hash change excludes rows from the S519
window), nor the scoreboard modules, `fill_realism.py`, `paper_night*.py`.

## 3. Order

1. Land S518 (parked `harness-h281`, rebase onto master, re-run its 5 test files per file).
2. Fit CLI + artifact contract; dry run on the scoreboard history for nba/nfl/soccer (as-of check: no
   training row with settlement >= D-3).
3. Arms for nfl and soccer (served now / from 10-07), then tennis (mid + B only), then nba B/C.
4. Fills receipt per sport (`--sport` extended; soccer = 3 tickers per game, clustered by game).

## 4. Verifier contract (two tiers)

- Tier 1 CONTRACT (Opus, read-only): every section-2 rule maps to code + a test; MLB run/arm rows
  byte-identical to the pre-change fixture; the three S519-pinned files hash to the sealed values; no
  fit inside the recorder; every refusal reason counted in the heartbeat; LOC <= 300 per file.
- Tier 2 ADVERSARIAL (codex astra or Opus): mutants at least on (a) fit window off by one day (embargo
  3 -> 2), (b) fit read for the wrong UTC date, (c) soccer tie orientation flipped, (d) tennis C arm
  emitted, (e) state bar loosened, (f) missing fit falls back to mid, (g) MLB row field order changed,
  (h) per-sport shard written to the mlb directory. Each must be killed by a test; survivors get a test
  or a written equivalence argument.

## 5. Per-file tests (one process per file; never the full suite)

```
python -m pytest tests/platformkit/execution/test_live_shadow_sport.py -q
python -m pytest tests/platformkit/execution/test_live_shadow_fit.py -q
python -m pytest tests/platformkit/execution/test_live_shadow_soccer.py -q
python -m pytest tests/platformkit/execution/test_live_shadow_nba.py -q
python -m pytest tests/platformkit/execution/test_live_shadow_nba_e2e.py -q
python -m pytest tests/platformkit/execution/test_live_shadow_cli.py -q
python -m pytest tests/platformkit/execution/test_live_shadow_io.py -q
python -m pytest tests/platformkit/execution/test_live_shadow_fills_io.py -q
```
Fixtures: verbatim captured rows (books + state) for one nfl, one soccer, one tennis game, copied by a
probe script, never edited.

## 6. First live night must show

- For each served sport with a game that night: >= 1 arm row per arm per game in
  `data/cache/live_shadow/<sport>/<D>.jsonl`, decision counts by (arm, reason), and B/C rows carrying
  `fit_date` = the game's `scheduled_start` UTC day and a `fit_sha256` that matches that artifact
  (amended 2026-10-06 round 2: a game starting before midnight UTC keeps its start-day fit after
  midnight; the D+1 fit is produced during D, so zero `fit_missing` is expected on a served game).
- Heartbeat: peak_rss_mib <= 150, write_errors 0, the three capture heartbeats fresh all night.
- MLB rows of that night still count for S519 (run row sha256 map equals the pinned values).
- The fills receipt per sport runs (exit 0 or a counted refusal) and lists both pass bounds.
- Disclosed limits: B/C are walk-forward recalibrations of the venue mid (calibration, not a model of
  the game); tennis has no state features; soccer intents per outcome are not netted.

## 7. Not in scope

Any venue order path; sizing; a new seal (a later row seals a cumulative comparison of the live arms on
the S519 pattern once >= 30 paired games per sport exist); WNBA (season over); ncaaf (no aliases).

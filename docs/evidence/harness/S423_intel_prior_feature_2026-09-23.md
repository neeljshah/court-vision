# S423 -- pregame intelligence prior as a declared in-game feature block (PREPARE)

Spec: docs/evidence/tracking/specs/S423_spec.md. Worktree harness-h80, master a1e8a472e.
PREPARE only: construct fixtures, no corpus scored, no charged trial, no seal, no ledger row,
no network. The builder read data/cache only to name the attestation path and confirm column
names; it never ran the corpus through this code and wrote nothing under data/.
Vocabulary follows contract Q6; automated scan via contract_preflight.

## Before-condition, quoted from master a1e8a472e

(a) scripts/platformkit/ingame/baseline_four_arm_features.py
- :17 `    'nba': ('score_diff', 'quarter', 'seconds_remaining'),`
- :163 `def parse_state(text: str, sport: str) -> dict:` ... :168
  `    return {key: result[key] for key in FEATURES[sport]}`
- :188 `def logistic(train: list[dict], test: dict, names: list[str]) -> float:`
- :239-240 `    for arm, names in [('B', ['mid']), ('C', ['mid', *FEATURES[sport]]),` /
  `                       ('B_lag', ['mid_lag'])]:`

(b) scripts/platformkit/ingame/baseline_four_arm.py
- :107-108 `        for arm, names in [('B', ['mid']), ('C', ['mid', *FEATURES[sport]])]:` /
  `            record[arm] = logistic(train, test, names) if train else record['A']`
- :95-96 `        train = [s for s in train if first[s['game_id']].date() < first[gid].date()` /
  `                 and settled[s['game_id']] < boundary - EMBARGO]`
- :89 `                           home=row.get('home', '__all_home__'),`

(c) docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md
- :35 "Only state features: score_diff, quarter, seconds_remaining. Nothing else."
- :40-41 "No outcome, close, audit or external enriched field / may become a feature." (line 40
  opens with the tail of the previous sentence; the quoted sentence spans 40-41 verbatim).

(e) docs/INTELLIGENCE.md:135 `build(entity_id, as_of)  ->  AtlasArtifact | None` and
intel/team_pace_identity.py:152 `rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]` (the
`<=` admits the tip-off date; S423 uses its own strict `<` and never imports intel/).

Column names confirmed read-only: data/team_advanced_stats.parquet = game_id (string),
game_date (string YYYY-MM-DD), team_tricode, off_rtg, def_rtg, pace, oreb_pct, dreb_pct,
ast_pct, efg_pct, ts_pct, tov_ratio (9,990 rows; 30 tricodes). Its game_id is an NBA-stats id,
not the corpus's ESPN id, so the game's own row is excluded by DATE, never by id.
data/cache/inplay_odds/nba_checkpoints_full.parquet carries game_id (int64) and game_date
(string). Slug codes in that parquet: the 30 tricodes plus pho and wsh, so the frozen alias
table covers the slug space exactly.

## Home-side attestation source (named)

`data/cache/nba_pbp_wallclock_raw/summary/<game_id>.json` -- the cached ESPN summary payload,
fields `header.id` (must equal the corpus game_id) and
`header.competitions[0].competitors[].homeAway` + `.team.abbreviation`. 1,610 files present.
Correction to the spec's attribution: the S360 converter
(scripts/platformkit/ingame/nba_checkpoints_to_joined.py) caches nothing; the cache is written by
scripts/platformkit/venue_history/nba_wallclock_join.py (`RAW_CACHE / "summary" / f"{eid}.json"`),
which the upstream checkpoint builder scripts/platformkit/venue_history/nba_checkpoints_full.py
reuses. ESPN abbreviations are normalized with the landed
domains/basketball_nba/espn_nba_bridge.py `_norm_abbr` (GS, NO, NY, SA, UTAH, WSH); that is the
attestation source's own landed normalizer, not a widening of the frozen slug alias table.
Real row checked read-only: 401810825 summary says home ATL, away MIL; ticker
nba-mil-atl-2026-03-14, so the slug reads away-home and slug_order_disagrees is counted when a
slug reads home-away.

## What was built (all NEW files; no landed file edited)

- scripts/platformkit/ingame/intel_prior_snapshot.py -- build(as_of_utc, source_path) and
  build_rows(...): as-of filter FIRST (rows dated on/after the league-local as_of date are
  counted and dropped before any validation), same season, last 10, floor 5; vector
  off_rtg_mean, def_rtg_mean, pace_mean, n_games, last_game_date; snapshot carries as_of_utc,
  source_sha256 (digest and rows read from the same bytes), source_rows, asof_kind. LIVE mode
  refuses source_newer_than_asof on mtime (integer ns, `>=`) or any row date on/after as_of.
  Absurd-but-finite ratings (off/def outside 50-200, pace outside 60-140), NaN, bool and
  non-numeric values refuse the team (source_row_invalid); duplicate (team, game_id) or
  (team, date) refuses the team (source_duplicate_row); results do not depend on row order.
- scripts/platformkit/ingame/intel_prior_join.py -- frozen ALIASES (MappingProxyType), slug
  codes, ESPN attestation of the home side AND the tip-off instant (FIX 1b; the checkpoint
  game_date is a counted cross-check only), as_of = 00:00 America/New_York on the instant's
  local date, asserted strictly before tip-off, INTEL_PRIOR_NBA and INTEL_PRIOR_NBA_X, attach() per tick,
  census-only CLI writing census.json + blocks.json (not run by the builder).
- scripts/platformkit/ingame/intel_prior_arm.py -- imports the landed predict_rows,
  select_rows, EMBARGO, parse_state, lagged_mid, logistic, logit, timestamp and the S383
  _stratified_cells. B, C and B_lag are the landed values on the prior-eligible subset; B and C
  are refit on the landed training games and must agree to 1e-12 (landed_arm_mismatch);
  the landed fold is re-checked against EMBARGO and the tick count (landed_fold_mismatch).
  C_intel and C_intx are fitted on exactly those games (and on the lag-eligible games inside
  b_lag_subset). Cells go through S383 via a landed-shape view (A = reference, B = arm).
  The CLI requires the landed sealed-and-committed prereg check before any fit.
- tests/platformkit/ingame/test_intel_prior_feature.py -- 16 tests (12 build + 4 FIX 1b),
  construct fixtures only.
- docs/evidence/ingame/S423_NBA_INTEL_PRIOR_PREREG_DRAFT_2026-09-23.md -- UNSEALED.

## Named refusals and counters

Per game (census `refusals_per_game`): code_unmapped, home_side_unattested, prior_thin,
prior_absent, source_after_tipoff, join_by_name_refused, plus source_row_invalid,
source_duplicate_row, source_duplicate_game (FIX 1b), season_aggregate_refused,
source_row_undated, source_empty, as_of_not_before_tipoff (FIX 1b), tipoff_instant_invalid
(FIX 1b), ticker_conflict, game_id_invalid. Since FIX 1b the join no longer emits
tipoff_date_missing / tipoff_date_conflict / tipoff_date_invalid: a missing or conflicting
checkpoint date is counted checkpoint_date_disagrees, never a refusal. Counters (not
refusals): slug_order_disagrees, checkpoint_date_disagrees, alias_applied:WSH,
alias_applied:PHO. Snapshot counters: rows_on_or_after_asof, rows_other_season,
source_row_unmapped_team, and team_refused:<name> per refused team (a separate key from the
per-row counts, so one counter keeps one meaning). Arm: prior_changed_within_game, prior_invalid (per game, with ticks),
landed_arm_mismatch and landed_fold_mismatch (hard stops).

Fixture counts exercised by the tests: rows_on_or_after_asof = 2 (the two own-date rows);
source_after_tipoff = 1; join_by_name_refused = 1 (slug) and 1 (attestation); code_unmapped = 1;
slug_order_disagrees = 1; prior_changed_within_game = 1; prior_thin = 1; prior_absent = 1;
source_row_invalid = 2 (NaN and absurd); source_duplicate_row = 1 (both row orders).

## r1 join census -- BEFORE FIX 1b (retracted pre-fix record; the orchestrator re-runs it)

RETRACTED: on 57 of these 1,430 joined games the tip-off date came from a UTC-dated checkpoint
game_date, so the game's own row entered its prior and as_of fell after tip-off. The 0.8977
fraction and the READING's 'strictly before tip-off' below are the pre-fix record only. The
post-fix census goes to docs/evidence/forward/intel_prior/2026-09-23_r1_join_fix1b/.

Original heading: orchestrator, read-only, 2026-09-23 18:45:21Z-18:45:41Z, candidate worktree.

Command (census-only CLI; --out is a directory holding census.json and blocks.json):
python -m scripts.platformkit.ingame.intel_prior_join --corpus-dir <main checkout>/data/cache/ingame_grade_joined/nba_checkpoints_r1
--checkpoints <main checkout>/data/cache/inplay_odds/nba_checkpoints_full.parquet --summary-dir <main checkout>/data/cache/nba_pbp_wallclock_raw/summary
--source <main checkout>/data/team_advanced_stats.parquet --out docs/evidence/forward/intel_prior/2026-09-23_r1_join
- n_games: 1593
- n_joined: 1430
- fraction_with_prior_before_tipoff: 0.8976773383553045
- refusals_per_game: prior_absent 89, prior_thin 74
- counters: alias_applied:PHO 1, alias_applied:WSH 1
- asof_kind: reconstructed on every joined game (no source row carries a receipt); source sha256 d54ba998aa14eed1f8d278a0b26d2dcca969ac33e274261aef32c8863af9ff91
- artifacts: census.json 371 bytes sha256 30df865086a48870e47ef335161b8472927130f857bc2e1c4a62a72443fbd3ed;
  blocks.json 478363 bytes sha256 982b195b2090d7b31e4f54469059e60de26d124ef939b9d8c405ffa266cdf41c (one block per joined game:
  prior_net_diff, prior_pace_mean, home, away, as_of_utc = 00:00 America/New_York written as the UTC instant it is,
  04:00Z or 05:00Z, for example 2024-11-12T05:00:00+00:00; corrected wording, FIX 1b)
- READING (BEFORE, retracted): 1,430 of 1,593 r1 games (89.8 percent) were joined; 57 of them leaked; the 163 refusals are
  the season openers (prior_absent, no same-season rows before the date) and games within the first games of a season
  (prior_thin, fewer than 5); no code_unmapped, home_side_unattested, source_after_tipoff or join_by_name_refused occurred.
  No r1 FIT was run (the arm CLI requires a sealed prereg; the draft is unsealed).

## r1 join census -- AFTER FIX 1b (orchestrator, read-only, 2026-09-23 19:02:36Z-19:02:54Z from the candidate worktree)

Same command as the BEFORE run with --out docs/evidence/forward/intel_prior/2026-09-23_r1_join_fix1b (a directory holding
census.json and blocks.json).
- n_games: 1593; n_joined: 1430; fraction_with_prior_before_tipoff: 0.8976773383553045 (unchanged: the 57 leaking games
  were joined before and after -- the fix changes WHICH rows enter their priors, not whether they join)
- refusals_per_game: prior_absent 89, prior_thin 74
- counters: alias_applied:PHO 1, alias_applied:WSH 1, checkpoint_date_disagrees 57
- asof_kind: reconstructed on every joined game; source sha256 d54ba998aa14eed1f8d278a0b26d2dcca969ac33e274261aef32c8863af9ff91
- artifacts: census.json 408 bytes sha256 36ac5f8bb40777c76e32fe48bd7071c430479b05b53994bccb54b7291548bdf7;
  blocks.json 601342 bytes sha256 19d4ebbf8dd21d08bed4023b36d046e2a13a7d4de3e691d17df704fc0f1a1b9c
- DIFF against the BEFORE artifact: exactly 57 games' blocks changed (the 57 with checkpoint_date_disagrees); the others
  have identical block, home, away and as_of_utc values (every entry gained tipoff_utc and tipoff_local_date); 401810008 -4.4167 (as_of 2025-11-03T05:00Z, after tip-off) -> -10.02 (as_of 2025-11-02T04:00Z).
- READING: 1,430 of 1,593 r1 games (89.8 percent) carry a reconstructed prior whose as-of is 00:00 America/New_York on the
  local tip-off date, strictly before the attested tip-off instant; the 163 refusals are season openers (prior_absent) and
  early-season games (prior_thin). No r1 FIT was run (the arm CLI requires a sealed prereg; the draft is unsealed).

## Reproduced-first evidence (guards broken in scratch copies, never in owned files)

Scratch runner loaded a modified copy under the real module name, then ran this test file:
- (a)(b) `day >= local` changed to `day > local`: test_a and test_b FAIL.
- (c) season-aggregate guard removed: test_c FAILS.
- (d) name refusal renamed to code_unmapped and GS guessed: test_d FAILS.
- (e) constant-within-game check removed: test_e FAILS.
- (f) home side taken from slug order: test_f FAILS.
- (g) live mtime check removed: test_g FAILS.
- (h) landed_arm_mismatch check removed: test_h FAILS (DID NOT RAISE).
- (i) block appended to FEATURES['nba'] at fit time: test_i FAILS.
- (j) UNDERPOWERED floor replaced by SINGLE-WINDOW: test_j FAILS.
- (k) sort and duplicate refusal removed: test_k FAILS.
With the owned files restored: 12 passed.

## FIX 1b (round 1 REJECT from both Opus tiers; spec AMENDMENT 2 and its ADDENDUM)

Defect: the tip-off date was the checkpoint game_date, which is the UTC date on 57 games.
Reproduced first, before any change:
- Real game, read-only, with the PRE-FIX join: 401810008 (NYK home, CHI away; ticker
  nba-chi-nyk-2025-11-03; summary start 2025-11-03T00:00Z = 11-02 19:00 ET; game_date
  2025-11-03) gave as_of 2025-11-03T05:00Z, five hours AFTER tip-off, and prior_net_diff
  -4.4167 with the own row. 401809510 ORL-BOS (start 2025-11-08T00:00Z) gave as_of
  2025-11-08T05:00Z and -2.7222.
- Construct: the four new tests run against the pre-fix modules (scratch loader) all FAIL: the
  late-night test (own row admitted, net +8.0 instead of below zero), as_of_not_before_tipoff
  (no refusal), source_duplicate_game (source_duplicate_row instead), fold completeness
  (landed_arm_mismatch instead of landed_fold_mismatch).
Fix, as ruled: (a) tip-off instant from header.competitions[0].date through parse_venue_time
(ESPN writes minutes, so ':00' seconds are padded losslessly); as_of = 00:00 America/New_York
on its local date, rendered as UTC; the join asserts as_of < tip-off and refuses
as_of_not_before_tipoff; game_date is a cross-check counted checkpoint_date_disagrees.
(b) Tests: a late-night game with game_date the UTC next day and own rows that flip the sign
(own row out, prior equal to the previous-day snapshot, checkpoint_date_disagrees 1, as_of
strictly before tip-off); a one-day-early own row is admitted as a prior row; the same game id
on two dates refuses source_duplicate_game in both row orders. (c) excluded counts sit beside
every cell (cell['excluded'], plus n_warmup, n_ot, n_outside_periods). (d)
landed_fold_mismatch checks both directions: the landed train_games must EQUAL the set of
eligible games meeting the date and EMBARGO rule; a perturbed train_games trips it. (e) The
draft body states that OT is not scored by the landed machinery. (f) This memo.
After the fix, real games, read-only: 401810008 as_of 2025-11-02T04:00Z, prior_net_diff
-10.02 (the verifier's no-own-row value), checkpoint_date_disagrees 1; 401810019 -8.6867
(verifier -8.687); 401809510 as_of 2025-11-07T05:00Z, -6.1194; 401810825 (dates agree)
as_of 2026-03-14T04:00Z, no counter.
Guards broken in scratch copies after the fix, each test FAILS: tip-off from game_date again
(late-night test); as_of assertion removed; source_duplicate_game check removed; fold
completeness reduced to a subset check; per-cell exclusions removed (test_j).
With the owned files restored: 16 passed.

## FIX 1c (round 2: both Opus tiers ACCEPT WITH CORRECTIONS; spec AMENDMENT 3)

- (a) A summary with no competitions[0].date now refuses tipoff_instant_invalid (was
  home_side_unattested): the start is read outside the KeyError block, so None reaches
  tipoff_instant(). A minute-precision time with an offset (for example
  '2025-11-03T00:30+01:00') also refuses tipoff_instant_invalid, fail-closed and counted;
  only the 'Z' minute form is padded, and ESPN writes Z. Both are test assertions.
- (b) As-of before every tick is now a GUARANTEE: attach() refuses the whole game
  as_of_not_before_first_tick when as_of_utc is not strictly before the game's first
  parseable tick ts; eligible_subset counts it per game. Measured by both tiers on the AFTER
  census: as_of is before the first tick on 1,430 of 1,430 joined games, the first tick
  1.03-75.5 min after the scheduled start (median 11.8), so the guard fires on no r1 game.
- (c) Memo wording corrected (the DIFF line above, the NOT VERIFIED lines below).
- Reproduced first (scratch copies of the fixed files): start read inside the KeyError block
  again gives home_side_unattested, and the test fails; the first-tick guard removed keeps an
  as_of-after-tick game, and the test fails.
- Pass counts after FIX 1c: test_intel_prior_feature.py 16 passed; landed
  test_baseline_four_arm_nba.py 134, test_baseline_four_arm_period.py 72,
  test_baseline_four_arm.py 53.

## Honest limits

- Every r1 prior is RECONSTRUCTED: team_advanced_stats has no receipt timestamp and later stat
  revisions are not excluded. It is not receipt-causal.
- (restated after FIX 1b) The tip-off instant is the attested summary's start. as_of is 00:00
  America/New_York on that instant's local date and is asserted strictly before it, so no row
  dated on the local tip-off date (the game's own row) can enter. A late game on the previous
  local date can end after as_of but before this tip-off; the prior is used only at ticks after
  tip-off. A row dated one day early IS admitted as a prior row: the date cannot tell it from
  the game itself unless the same game id also appears on another date (source_duplicate_game).
- The checkpoint game_date and the ticker date are UTC dates on some games (57 in 2025-11), so
  neither is used as a source; checkpoint_date_disagrees is the measurement.
- 88 joined games have no own row in team_advanced_stats (for example 401766128): thinner
  source coverage for those teams, not a leak (nothing from the game can enter).
- Season boundary is by month (August onward starts a season); playoff rows count as the same
  season. The 2025-10/11 thin window will surface as prior_thin / prior_absent, never imputed.

## NOT VERIFIED

- No r1 fit: the arm CLI requires a sealed prereg and the draft is unsealed; the r1 join census above is the orchestrator's read-only run, not a fit.
- MEASURED by the orchestrator's AFTER census (not by this lane): summary-cache coverage is
  complete for the corpus (home_side_unattested 0 over 1,593 games), and slug_order_disagrees
  is 0 over the 1,430 joined games.
- LIVE mode was exercised with a temporary file's mtime only; no live receipt snapshot exists.
- NTFS stores mtime in 100 ns units; the test's one-nanosecond case lands exactly on as_of.
- The arm's run time on the full corpus (six fits per tick plus lag refits) is unmeasured.
- The CLI paths (join census, arm with a sealed prereg) ran only for --help by this lane.
- The post-fix r1 census was run by the orchestrator (AFTER section), not by this lane; this
  lane's own real-game checks cover four games.
- The cause of the UTC-dated game_date in the checkpoint builder is not investigated
  (NEXT-ROW; the builder is human-gated upstream).
- Postponed or rescheduled games: whether the summary date is the played start is unchecked.

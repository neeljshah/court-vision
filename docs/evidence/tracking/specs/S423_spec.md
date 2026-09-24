GAP S423 | sport nba (pattern sport-blind) | worktree harness-h80 (master-based) | log cx_s423_intel_prior_feature
# Pregame intelligence prior as a declared in-game feature block: a dated per-team prior joined to every tick

SINGLE PROBLEM: arm C conditions on logit(mid) plus three NBA numbers and knows nothing about the two teams. The intelligence
layer feeds pregame products only, and NONE of its team artifacts is dated per game. No per-game team prior can be joined to a
tick without reading the game's own future, so the hypothesis "a pregame team prior (and its interaction with the realized state)
moves C toward the mid" cannot be preregistered.

BINDING BEFORE-CONDITION (quote from master; the orchestrator re-measures each one before the build, Q8):
(a) baseline_four_arm_features.py:17 `'nba': ('score_diff', 'quarter', 'seconds_remaining'),`; :163-168 parse_state returns `{key:
    result[key] for key in FEATURES[sport]}`; :188 `def logistic(train: list[dict], test: dict, names: list[str]) -> float:`;
    :239-240 lagged_subset arms `('B', ['mid'])`, `('C', ['mid', *FEATURES[sport]])`, `('B_lag', ['mid_lag'])`.
(b) baseline_four_arm.py:107-108 `for arm, names in [('B', ['mid']), ('C', ['mid', *FEATURES[sport]])]:` / `record[arm] =
    logistic(train, test, names) if train else record['A']`. At :95-96, training = games whose first tick is on an earlier date
    AND that settled before boundary - EMBARGO. At :89 `home=row.get('home', '__all_home__')`: the corpus has no home key.
(c) S382_NBA_PREREG_DRAFT_r1_2026-09-21.md:35 "Only state features: score_diff, quarter, seconds_remaining. Nothing else." and
    :40-41 "No outcome, close, audit or external enriched field may become a feature." S423 can never enter E2.
(d) nba_checkpoints_r1 row keys (first row of shard 00529e50...jsonl, parse_float=str): close_ts, game_id ('401810825', an ESPN
    id), market_prob, market_ticker ('nba-mil-atl-2026-03-14'), model_prob, outcome, seconds_since_last_trade, side ('home'),
    sport, state_summary ('home_score=0 away_score=0 quarter=1 seconds_remaining=2880'), traded, ts. NO team code, NO tip-off, NO
    game_date; the upstream data/cache/inplay_odds/nba_checkpoints_full.parquet adds game_date only. Team codes exist ONLY inside
    the ticker slug; home/away order in the slug is UNATTESTED.
(e) What the layer can emit as of a date. data/cache/atlas_team_*.parquet (16 files, 30 rows each): ONE row per team, as_of =
    2026-05-31 on every row -- a season-final snapshot dated after 1,588 of the corpus's 1,593 games (leaks; refused).
    data/intelligence/defensive_schemes.parquet: 30 rows, no date, no as_of column (refused). The atlas CODE builds as-of
    (docs/INTELLIGENCE.md:135 `build(entity_id, as_of)`; intel/team_pace_identity.py:152 `rows = rows[rows["game_date"] <=
    pd.Timestamp(as_of)]`), but intel/ is human-gated and `<=` admits the tip-off date itself. The dated per-game source under it
    is data/team_advanced_stats.parquet (9,990 rows: game_id, game_date, team_tricode, off_rtg, def_rtg, pace, oreb_pct, dreb_pct,
    ast_pct, efg_pct, ts_pct, tov_ratio; 2022-10-18..2026-05-30; NO receipt timestamp, NO home flag). matchup_grid.parquet (4,900
    rows, 325 dates) is CV-derived, barred by the runtime contract. Injury: injury_features.parquet (254 rows, 2025-09-05..
    2026-05-26) and 7 daily injury_status_*.json (2026-05-26..06-03) do not date the corpus span: OUT OF SCOPE.
(f) Probe (orchestrator, read-only, 2026-09-23): of 1,593 corpus games, 1,386 have BOTH slug codes present in team_advanced_stats
    on the same game_date. Misses: 117 in 2025-10/11, 72 in the 2025-04..06 playoffs, 5 after the source ends, aliases WSH / PHO
    once each. No source row carries a receipt: any historical prior is RECONSTRUCTED.

CHANGE (owned NEW files only; NO landed module is edited -- baseline_four_arm_features.py is S414's (MODIFIED ADDITIVE), the
baseline_four_arm / _period modules S417's; FEATURES, CORPORA and every landed test stay byte-identical):
1. scripts/platformkit/ingame/intel_prior_snapshot.py: build(as_of_utc, source_path) returns {team: vector} from
    team_advanced_stats rows with game_date STRICTLY BEFORE the as_of date (never <=), same season, the last N=10 games; fewer
    than 5 refuses prior_thin. Vector: off_rtg_mean, def_rtg_mean, pace_mean, n_games, last_game_date. Each snapshot carries
    as_of_utc, source sha256, row count, asof_kind in {receipt, reconstructed}. LIVE mode (receipt) refuses
    `source_newer_than_asof` when the source mtime or any row date is on or after as_of. HISTORICAL mode cannot pass the file test
    (every source postdates the corpus), so it filters ROWS and labels the snapshot reconstructed; later stat revisions are not
    excluded (memo says so). Counts only; ASCII; no network.
2. scripts/platformkit/ingame/intel_prior_join.py: per game, it resolves home/away tricodes, the tip-off date and the prior block.
    Codes come from the ticker slug via a FROZEN alias table (WSH->WAS, PHO->PHX, counted); the home side is attested by a NAMED
    source (the ESPN summary cached by the S360 converter, path in the memo); slug order is a cross-check only
    (slug_order_disagrees). Tip-off date = the game_date from the checkpoint parquet; the snapshot's as_of is 00:00 league-local
    on that date. Declared block INTEL_PRIOR_NBA = ('prior_net_diff', 'prior_pace_mean'), prior_net_diff = (home off-def) - (away
    off-def). Interaction block INTEL_PRIOR_NBA_X adds 'prior_x_score' = prior_net_diff * score_diff and 'prior_x_score_late' =
    prior_x_score * (quarter >= 4). The block is CONSTANT within a game (asserted per tick). Named refusals, counted per game,
    never imputed: code_unmapped, home_side_unattested, prior_thin, prior_absent, source_after_tipoff, join_by_name_refused.
3. scripts/platformkit/ingame/intel_prior_arm.py imports the landed select_rows, parse_state, lagged_mid, logistic and the fold /
    EMBARGO rule. On the prior-eligible subset it fits B, C, B_lag, C_intel (['mid', *FEATURES['nba'], *INTEL_PRIOR_NBA]) and
    C_intx (C_intel names plus the two interaction names) on identical training games. Its B and C must equal the landed values
    on the same input to 1e-12 (else `landed_arm_mismatch`); paired_losses per tick in the landed shape feed the S417 period
    machinery; B and C are RECOMPUTED on the eligible subset (b_lag_subset pattern), excluded count beside every cell.
4. tests/platformkit/ingame/test_intel_prior_feature.py (construct fixtures only) and the memo
    docs/evidence/harness/S423_intel_prior_feature_2026-09-23.md: quotes, per-refusal counts from the orchestrator's read-only r1
    join, the FRACTION of r1 games with a prior strictly before tip-off; ends NOT VERIFIED.
5. The unsealed prereg draft docs/evidence/ingame/S423_NBA_INTEL_PRIOR_PREREG_DRAFT_2026-09-23.md, carrying the text below.

PREREGISTRATION TEXT (draft; the orchestrator alone seals it): Arms A, B, B_lag, C, C_intel and C_intx, all ridge logistic, fitted
on past games only. PRIMARY cell: C_intel minus B, Brier, period-first (Q1..Q4 and OT per phase()), whole-game bootstrap with seed
13, on the prior-eligible subset. SECOND cell: C_intx minus B, Brier, phase Q4 only (the interaction: a strong team behind late).
Standing controls: C_intel minus B_lag and C_intx minus B_lag on the B_lag subset; a below-zero primary not also below zero
against B_lag is LAG-ABSORBED. Descriptive: C_intel minus C (the prior's increment), logloss beside every Brier cell. Floors: >= 30
scored games per cell or UNDERPOWERED; exclusions counted per refusal; no imputation. Corpora: r1 is touched (S392) and
reconstructed, so any r1 result is SINGLE-WINDOW at best; the 2026-27 forward corpus with LIVE receipt snapshots is the only route
to a second corpus and to AHEAD. Charge: one FWER-ledger row at launch, reading K at launch, AFTER the sealed E2 trial has run,
inside the family's K budget. EXPECTED: NULL on the primary (the venue already prices team strength); weak-to-NULL on the Q4
interaction cell, the only place a venue lag could show. A NULL is a completed result and closes the row.

TESTS (false-PASS risks; each must fail the build if broken): (a) a source row dated ON the tip-off date or later is excluded, and
a source whose only rows postdate as_of refuses source_after_tipoff; (b) the game's own row in team_advanced_stats never enters
its prior (fixture where it flips the sign); (c) a season-level aggregate (as_of after tip-off, or no as_of) is refused by name;
(d) a join by team NAME refuses join_by_name_refused, and an unknown code refuses (the alias table is frozen, never guessed);
(e) a block value that changes within a game refuses prior_changed_within_game; (f) swapped slug order with an attested home side
keeps the attested sign and counts slug_order_disagrees; (g) LIVE mode refuses a source whose mtime is after as_of; (h) landed B
and C reproduce to 1e-12 on a fixture; (i) FEATURES['nba'] and parse_state(text, 'nba') byte-identical before and after import;
(j) a one-game fixture is UNDERPOWERED; (k) repeat builds are byte-identical.

CONTROLS / ACCEPTANCE: PREPARE only; fixtures only: no charged trial, no seal, no ledger row, no network. The builder never writes
data/ (the orchestrator alone runs the read-only r1 census and, later, the live snapshots). It never edits intel/, src/, the S382
draft, the sealed MLB prereg, or any S414 / S417 owned file. Per-file tests one at a time; contract_preflight FAIL=0; <= 300 LOC
per file; ASCII; Q6 vocabulary; landed tests pass unchanged; memo ends NOT VERIFIED.

DO NOT: state or imply a market advantage or a currency amount; print any retracted figure; read the atlas_team_* parquets,
defensive_schemes.parquet or any season-level aggregate as a per-game feature; use a CV-derived artifact as an in-game input;
infer the home side from the slug alone; fill a missing prior with a league mean or zero; add the block to FEATURES['nba'] or to
the E2 draft; call a reconstructed prior receipt-causal; widen N, the minimum-games floor or the alias table after any read.

AMENDMENT 1 (2026-09-23 18:5xZ; binding; from the Opus build report and the orchestrator's read-only r1 join census, run from the
candidate worktree at 18:45Z). (a) SPEC CORRECTION: the home-side attestation source is data/cache/nba_pbp_wallclock_raw/summary/
<game_id>.json (1,610 files), WRITTEN by scripts/platformkit/venue_history/nba_wallclock_join.py (the fetch the NBA checkpoint
builder nba_checkpoints_full.py reuses); the S360 converter caches nothing -- the spec's attribution is corrected, the source is
the same cache the corpus was built from. ESPN codes (GS, NO, NY, SA, UTAH, WSH) pass through the landed _norm_abbr in
domains/basketball_nba/espn_nba_bridge.py; the slug alias table (WSH->WAS, PHO->PHX) stays frozen. On the real row 401810825 the
summary says home ATL / away MIL with ticker nba-mil-atl, so slugs read AWAY-HOME; this convention rests on one attested row and
the join never relies on it (slug order is a cross-check counted as slug_order_disagrees). (b) MEASURED r1 JOIN CENSUS
(census-only CLI, --out is a DIRECTORY holding census.json and blocks.json; committed under
docs/evidence/forward/intel_prior/2026-09-23_r1_join/): n_games 1,593; n_joined 1,430; fraction_with_prior_before_tipoff
0.8977; refusals per game prior_absent 89, prior_thin 74; aliases applied PHO 1, WSH 1; asof_kind reconstructed on every game
(no source row carries a receipt); source sha256 d54ba998...; blocks.json 478,363 bytes (one block per joined game:
prior_net_diff, prior_pace_mean, home, away, as_of_utc 00:00 league-local on the tip-off date as +00:00 -- the verifiers
decide whether that zone rendering is the spec's '00:00 league-local'). The census slot in the memo is filled by the
orchestrator with these numbers. (c) Refusal names the builder added beyond the spec's list are ACCEPTED as named and counted
(source_row_invalid, source_duplicate_row, season_aggregate_refused, tipoff_date_missing, tipoff_date_conflict,
tipoff_date_invalid, ticker_conflict and the rest listed in the memo); none is imputed. (d) The builder's sealer choices are
recorded in the unsealed draft and are NOT sealed by this amendment: the C_intx-minus-B_lag control scored on Q4 only (to pair
with the second cell); LAG-ABSORBED = the Brier cell's interval wholly below zero while the matching B_lag control's is not.
(e) NOT VERIFIED carried forward: the r1 FIT (arms B, C, B_lag, C_intel, C_intx on the prior-eligible subset) has NOT been run
-- the arm CLI requires a sealed prereg and the draft is unsealed; the sealing order in the spec (after the E2 trial, inside the
family's K budget) stands; ESPN cache coverage checked on one game; NTFS 100 ns mtime granularity on the LIVE-mode test.

AMENDMENT 2 (2026-09-23 19:0xZ; binding; from round 1 on the build -- Opus tier 2 REJECT on a real-row leak; tier 1 folded in
when it arrives). MEASURED BY TIER 2 ON THE REAL r1 JOIN: the checkpoint parquet's game_date is the UTC date, one day after the
league-local date, on 57 of the 1,593 games (all in 2025-11; 1,536 agree with the ESPN summary's tip-off converted to
America/New_York). The join takes the tip-off date from that column (intel_prior_join.py:98-100) and the snapshot keeps rows
dated strictly before it, so on those 57 joined games the game's OWN team_advanced_stats row (same NBA game id, dated the
local date) enters the prior: 401810008 NYK-CHI prior_net_diff -4.4167 with its own row, -10.02 without; 401810019 -7.352 vs
-8.687; as_of_utc 2025-11-03T05:00Z is five hours AFTER tip-off. The spec's CHANGE 2 premise ('tip-off date = the game_date
from the checkpoint parquet') was wrong. RULING: (a) THE TIP-OFF INSTANT IS THE ATTESTED SUMMARY'S UTC START (the same file that
attests the home side; parsed through parse_venue_time); the as-of is 00:00 America/New_York on the LOCAL date of that instant,
rendered in the artifact as the UTC instant it is (04:00Z / 05:00Z -- the memo and AMENDMENT 1(b) are corrected: no '+00:00 at
00:00'); the join ASSERTS as_of < tip-off instant and refuses as_of_not_before_tipoff by name otherwise; the checkpoint game_date
is a CROSS-CHECK only, counted checkpoint_date_disagrees per game (never the source, never a refusal by itself); a game without
a summary is refused home_side_unattested as before. (b) A test with a late-night game whose UTC date differs from its local date
pins: the own row excluded, prior identical to the previous-day prior, checkpoint_date_disagrees 1, as_of strictly before
tip-off; and a fixture where the own row is dated one day early (the doubleheader-style construct) states the intended result:
a row dated strictly before the local tip-off date IS a prior row (it cannot be the game itself -- the same game id appearing
on an earlier date is refused source_duplicate_game, counted). (c) The orchestrator RE-RUNS the census after the fix; the memo's
census section is replaced (the 0.8977 fraction and 'every prior strictly before tip-off' are retracted as the pre-fix record
and kept labelled BEFORE); the artifacts are regenerated under docs/evidence/forward/intel_prior/2026-09-23_r1_join_fix1b/.
CORRECTIONS: (d) excluded counts beside EVERY cell (intel_prior_arm.py:150-168 reports them only at the top level; the spec
requires per cell). (e) OT: the landed period machinery scores Q1-Q4 only (baseline_four_arm_period.py:9); the PREREG TEXT's
'Q1..Q4 and OT per phase()' resolves to what phase() emits; the draft states in its body (not only the builder notes) that OT
ticks are not scored by the landed machinery and would need a landed change (NEXT-ROW), so the primary cell is Q1-Q4 -- a
sealer-visible statement, unsealed. (f) Memo line 115 and the AMENDMENT 1(b) rendering statement corrected as in (a).
Round-1 tier-2 passes stand as recorded (season boundary, join refusals, arm tolerances 2e-12 / 5e-13, fold mismatch, training
identity, census hashes, home / away on all 1,430 joined games, three re-derived blocks within 1e-9, draft verbatim). LESSON
(landing lessons 34): a date column in a derived corpus is not a tip-off; the attested instant is.
AMENDMENT 2 ADDENDUM (2026-09-23 19:1xZ; Opus tier 1 REJECT on the SAME leak, found independently: 57 of 1,430 joined games with
game_date the UTC date (2025-11-03..11); example 401809510 ORL-BOS tipped 7 pm ET on 11-07, game_date 2025-11-08, ticker
nba-bos-orl-2025-11-08 -- the ticker date is shifted too, so nothing downstream catches it; last_game_date equals the ET tip-off
date on both sides for all 114 team-sides). Tier 1's additions, RULED: (g) the tip-off instant is read from the summary's
header.competitions[0].date through parse_venue_time (the field the attestation already reads); (h) the fixture's date field is
READ by the code (tests (a) and (b) proved exclusion only when game_date was already local -- the false PASS the spec warned of);
the new test has game_date the UTC next day and the own row flipping the sign; (i) landed_fold_mismatch also checks
COMPLETENESS (every eligible game meeting the date and embargo rule is in the landed training set), with one test that trips
it on a perturbed train_games; (j) the memo's Honest-limits and READING lines restated after the fix. Tier 1 confirmed the
as_of rendering is league-local midnight written in UTC (not UTC midnight) on all 1,430 blocks -- the defect is the input date.

AMENDMENT 3 (2026-09-23 19:1xZ; binding; from round 2 on fix 1b -- Opus tier 1 ACCEPT WITH CORRECTIONS, Opus tier 2 ACCEPT WITH
CORRECTIONS; no blocker). Both tiers re-derived changed blocks from the source to 1e-9 (401809510 -6.119444; 401810027 7.114286;
401810061 -6.121111), confirmed exactly the 57 checkpoint_date_disagrees games changed, as_of strictly before the scheduled
instant on all 1,430, the first r1 tick 1.03-75.5 min AFTER the scheduled instant on all 1,430 (median 11.8), team_advanced_stats
game_date LOCAL on every checked row (the own row at offset 0 on 1,342 games, absent on 88, never at +1 or -1 only), DST
renderings correct, no same-team same-date rows. CORRECTIONS RULED (fix 1c): (a) a summary whose competitions[0].date is missing
refuses tipoff_instant_invalid (not home_side_unattested): the start is read outside the KeyError block so None reaches
tipoff_instant(); one test. (b) AS-OF BEFORE EVERY TICK BECOMES A GUARANTEE, NOT A MEASUREMENT: attach() (or eligible_subset)
refuses as_of_not_before_first_tick by name when as_of_utc is not strictly before the game's first tick ts; one construct test;
the memo states the measured fact (holds on 1,430 of 1,430) beside the guard. (c) Memo: 'every other block identical' reads
'identical block, home, away and as_of_utc values (every entry gained tipoff_utc and tipoff_local_date)'; the NOT VERIFIED lines
saying the summary-cache coverage is unmeasured and the post-fix census not run are restated as MEASURED by the orchestrator's
AFTER run (home_side_unattested 0 over 1,593); the 88 joined games whose own row is absent from the source are stated as thinner
coverage, not a leak; a minute-precision time with an offset refusing tipoff_instant_invalid stated (ESPN writes Z). NOT
VERIFIED carried: the r1 fit (unsealed draft); the cause of the UTC-dated checkpoint game_date (NEXT-ROW for the checkpoint
builder, which is human-gated upstream); postponed or rescheduled games' summary dates.

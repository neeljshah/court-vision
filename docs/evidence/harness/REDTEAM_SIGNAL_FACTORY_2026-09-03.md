# RED TEAM: the signal factory plan -- 2026-09-03

Read-only adversarial review of `docs/research/organization-sprint/PLAN_SIGNAL_FACTORY_2026-09-03.md`
(169 lines) against the code it extends and the parquet catalogue it enumerates. Every number below
was recomputed on disk this session. No S-id is allocated here; no module was edited.
Calibration language only. REJECT / NULL / BEHIND / SINGLE-WINDOW are successes.

Context that moved under the plan while this review ran: `eval_gate/ledger.py` now carries
`FWER_OPTIONAL_FIELDS`, `load_fwer` and `next_k_family` (S13 landed at :116-149).

## 1. Findings

| id | plan sec | scenario | sev | evidence (recomputed) | smallest fix |
|----|----------|----------|-----|----------------------|--------------|
| SF-1 | 3 (T1->T2) | A T1 screen and its T2 verdict score the SAME corpus rows. `promote(top_n=20 per family per ISO week by T1 Brier improvement)` selects on the outcomes T2 then scores. CPCV purging removes train/test adjacency INSIDE one evaluation; it cannot purge a hypothesis that was CHOSEN using those test outcomes. | HIGH | `run_tier` T0/T1 and T2 both take `states` from `corpus_cache.load_gate_corpus(sport)`; no partition field anywhere in the `TierResult` signature (plan sec 3). | Named purge the tiers module needs: a **screen/verdict partition**. Split each corpus by `corpus_unit` or by ISO-week blocks of `date` into SCREEN and VERDICT; `run_tier(h,"T1")` may load only SCREEN, `run_tier(h,"T2")` only VERDICT; assert the two `event_id` sets are disjoint and store both partition sha256 on the `TierResult`. |
| SF-2 | 3, 4 | K prices only charged T2/T3 trials, so the width the search actually had never reaches `deflated_p`. The plan's own S16 ACCEPT bar is "at least 200 T0/T1 screens in one pod hour, 0 ledger charges from T0/T1". Selecting 20 of 200+ and deflating by K=1 is the forking-paths problem with a receipt. | HIGH | plan sec 3 table ("charged: no", "reportable: never") vs sec 6 ACCEPT; `backtest_runner._charge_ledger` (:131) increments by exactly 1 per call. | Charge the screen: `k_global = cumulative_k(prior, n_screened_in_family_since_last_charge)`, not `+1`. Keep T1 rows unreportable; only the COUNT enters K. Do this even with SF-1's partition in place. |
| SF-3 | 3, 4 | "spec committed BEFORE the runner's first pass (commit timestamp checked by the verifier)" is impossible for a spec under `docs/research/`: that tree is gitignored, so there is no add-commit to timestamp. | HIGH | `git check-ignore -v` returns `.gitignore:476  docs/research/*`; `git ls-files docs/research/` counts 1 file; `git log --diff-filter=A -- <plan>` returns EMPTY. | Move `FACTORY_TIERS_SPEC_2026-09-03.md` and `FWER_FAMILIES_SPEC_2026-09-03.md` to `docs/evidence/harness/` (tracked; four memos already live there). |
| SF-4 | 3 | Even once tracked, `PromotionRule.from_spec(path)` reads the WORKING TREE. The committed blob can be old while the rule actually applied is an uncommitted edit; the timestamp check passes and says nothing about the rule used. Committer dates are settable anyway. | HIGH | plan sec 3 (`rule = PromotionRule.from_spec(path)`); no blob pin in the `TierResult` field list. | `from_spec` computes `git hash-object <path>` and stores it as `spec_blob` on every `TierResult` and every charged ledger row. Content identity, not a settable date. |
| SF-5 | 2 | `regime_calibration.buckets` assigns `confidence=T1/T2/T3` by a GLOBAL tercile rank over every row handed in (:52-58, `order = sorted(range(len(rows)), key=...)`). A row's conditioning value therefore depends on other rows' predictions, including later ones. Conditioning a hypothesis on it makes the hypothesis transductive. | HIGH | `regime_calibration.py` lines 52-58 read on disk. | Drop `confidence=` from the legal conditioning alphabet, or recompute terciles from TRAIN rows only inside `walk_forward` and carry the fitted cut points forward. |
| SF-6 | 2 | The plan states the conditioning alphabet as `phase=`, `rest=B2B/RESTED/NORMAL`, `month=YYYY-MM`, `confidence=T1/T2/T3` "VERBATIM". The code emits none of that reliably: `month` is a two-digit `"%02d" % dt.month` with no year, or the raw `season_month`/`month` field; `rest=` falls through to the raw value on anything non-numeric; `phase=` is whatever `game_phase/period/inning` holds. The alphabet is open, so `enumerate_family` cannot enumerate it and `semantic_hash` has no closed canonical form. | HIGH | `regime_calibration.py:34-42` (`_month`), :60-70 (`rest`/`phase`). | Freeze the alphabet in the grammar module as an explicit enum and MAP `buckets()` output onto it, rejecting anything unmapped. Do not take the key strings verbatim. |
| SF-7 | 2 | "WTA mirrors `_wta`" is false for 6 of 8 tennis parquets. Two of the shared files are not per-tour mirrors at all: `serve_return_profiles` carries both tours in a `tour` column (ATP 1,084 / WTA 246 rows) and `schedule_density` is ATP-only (61,232 of 61,232 event_ids carry `-atp-`). | MED | direct `ls` plus column reads; full list in section 2. | Correct the catalogue; enumerate WTA only from `asof_hold_wta` (11,270 x 20) and `asof_setdetail_wta` (11,270 x 40) until the rest are materialized. |
| SF-8 | 1, 2 | Runtime purity is declared but unenforceable. `runtime_contract.classify_feature` uses `re.fullmatch`, so across the 806 feature columns of the plan's own catalogue it returns UNKNOWN 751, RUNTIME 55, TRAINING_ONLY **0**. `data/registry/signal_registry.parquet` (86 rows x 11 cols) has NO `runtime_available` column. The only `runtime_available` data on disk is a per-row boolean in `signals/officials_asof.py`. So S11's `runtime_available` is a hand-typed spec boolean with nothing behind it, and S04's "a student whose registered inputs carry `runtime_available=False` is refused" can never fire on a grammar-enumerated hypothesis. | HIGH | script over every catalogue parquet calling `classify_feature`; `signal_registry` columns read on disk. | `enumerate_family` calls `classify_feature` on every column and REFUSES to emit a student-lane hypothesis on anything not RUNTIME. UNKNOWN must fail closed for the student lane; it may still enumerate for the teacher lane. |
| SF-9 | 6 | Q1 ANSWER, CORRECTED AFTER TRACING PROVENANCE. The plan's catalogue contains NO column that requires the CV pipeline at inference. `player_tracking_features_asof.parquet` derives from `data/nba/playertrackv3_*.json` (`scripts/fetch_player_tracking_v3.py` -> `playertrack_to_parquet.py`), i.e. the NBA Stats `boxscoreplayertrackv3` endpoint; `asof_defender_rollup` derives from `defender_matchup_states` (`ingest_defender_matchup_states.py`, "ZERO network", over an on-disk NBA Stats matchup corpus). Both are API-delivered tracking PRODUCTS, not video. So the runtime-contract axis here is not video-vs-API, it is SAME-GAME vs AS-OF: the prior-N as-of rollups are obtainable pregame, the raw same-game fields (`speed`, `distance`, `touches`, `contestedFieldGoals*`, `defendedAtRim*`, `reboundChances*`) are box-score fields published after the game and are not. The concrete availability defect the plan inherits by extending this runner is `build_minutes_matrix`: it merges `pivot_player_metrics(novel_metrics_players.parquet)` on `personId` ALONE onto every game row of that player. That parquet is `player, metric, value, r2, n` -- no game or date key -- and `novel_metric_lift.UPPER_BOUND_CAVEAT` states it itself: "full-season static estimates; an as-of version is required before any production claim". The four `CANDIDATE_METRICS` (`load_speed_elasticity`, `load_touch_elasticity`, `contest_rest_response`, `b2b_speed_drop`) are therefore season-static values joined onto the very games that produced them. | HIGH | `foundry_runner.py:23-45`; `playertrack_to_parquet.py:1-19`; `ingest_defender_matchup_states.py:1-11`; `asof_defender_rollup.py:1-34`; `novel_metrics_players.parquet` columns read on disk. | Two separate fixes, do not conflate them: (a) the grammar tags a column by SAME-GAME vs AS-OF availability, not by whether a camera was involved upstream; (b) `CANDIDATE_METRICS` must not enter any screen until an as-of version exists -- the module already says so. |
| SF-10 | 3 | `dm_test.diebold_mariano(d, game_ids)` is a NO-OP on all four pregame corpora: each has exactly one row per `event_id`, so `n_clusters == n`, every cluster sum is a single deviation, and the cluster-robust SE equals the iid SE. The clustering the plan's own S17 row cares about (ICC 0.291) lives in TICKS, not in pregame rows. | HIGH | rows vs unique event_id: NBA 1,814/1,814; MLB 38,809/38,809; soccer 25,834/25,834; tennis 41,886/41,886. | The pregame cluster key is not the game. Pass the sport's declared key from section 3; keep `game_id` only for tick / in-game horizons. |
| SF-11 | 3 (T3) | NBA can never satisfy a rising replication floor. `min_corpora_eff` is capped at `n_corpora`, and NBA has 2 `corpus_unit`s (2024-25: 1,225; 2025-26: 589), so it returns 2 at every K. If SF-1's screen/verdict partition consumes one unit, T3 has zero units left and every NBA verdict is SINGLE-WINDOW by construction. MLB and tennis also have 2 units; only soccer has 6. | MED | `fwer_budget.min_corpora_eff` (:55) final `min(floor, n_corpora)`; `corpus_unit` value counts recomputed. | Partition NBA by ISO-week/season blocks rather than by `corpus_unit`, and state SINGLE-WINDOW in the register row when the floor is unmet. Do not lower the floor. |
| SF-12 | 5 | Q5 path A, false "already tested" via grid snapping. `semantic_hash` snaps params to the grid {3,5,10,20}. Two genuinely different searched hypotheses (halflife 4 and halflife 6) collapse to one hash; the second returns a `lookup` hit and charges nothing, so K undercounts the width the search actually had and `eps_eff` stays loose. | HIGH | plan sec 2 ("params snapped to the grid") against sec 5 ACCEPT ("re-proposal charges nothing"). | Snap for STORAGE, count for CHARGE: the runner increments K by proposals RECEIVED, not by distinct hashes STORED. A lookup hit still increments the family counter. |
| SF-13 | 5 | Q5 path B, corpus identity is a bare string. `UNIQUE(hash, tier, corpus, corpus_unit)` carries no content hash, so a rebuilt corpus (a season appended, a source re-derived) reuses a verdict computed on rows that no longer exist. `corpus_cache` already computes exactly what is needed. | HIGH | `corpus_cache._source_manifest` (:66) writes a per-source `{mtime, sha256}` sidecar that `load_gate_corpus` already enforces via `StaleCorpusError`. | Add `corpus_sha` (sha256 over the sorted sidecar sha256 values) to the result UNIQUE key and to `lookup(...)`. |
| SF-14 | 5 | Q5 path C, a lookup hit serves a STALE bar. The stored row carries the `k_global` of its own run; re-reported later at a larger K its `deflated_p` is looser than the bar in force. | MED | `result` schema stores both `raw_p` and `deflated_p` (plan sec 5). | `lookup` returns `raw_p`; the reader recomputes `deflated_metrics.deflated_p(raw_p, k_global_now)`. Never serve a stored `deflated_p`. |
| SF-15 | 5 | sqlite treats NULL as distinct under UNIQUE, so a pooled-corpus row written with `corpus_unit = NULL` silently never dedups, and the sec-5 ACCEPT test ("1 trial + 1 lookup") passes or fails on a detail the plan does not fix. | LOW | sqlite UNIQUE/NULL semantics; plan sec 5 schema declares no NOT NULL. | Declare `corpus_unit TEXT NOT NULL DEFAULT ''` and write the empty string for the pooled case. |
| SF-16 | 2 | Conditioning cardinality is uncapped, so S14's family sizes -- the BH denominator -- get chosen after seeing the catalogue. The NBA gate corpus alone spans 14 distinct `YYYY-MM` months; 14 months x 3 rest x 3 confidence multiplies the 3,384-row base enumeration into the 1e5-1e6 range. | HIGH | month count recomputed on the joined NBA corpus; base enumeration in section 4. | The frozen FAMILIES spec must fix the CONDITIONING SET per family, not only the columns. Default for v1: conditioning = the empty set for every T1/T2 family. |
| SF-17 | 4 | The two-stage bar is a ~100x loosening and the plan never prints the magnitude. At the section-4 base enumeration K = 3,384, global Bonferroni gives a per-test bar of 1.4775e-05; under `across_families = deflated_p(p, 34)` a within-family BH discovery can clear at p up to 0.05/34 = 1.4706e-03. Ratio 99.5x. | HIGH | `0.05/3384` and `0.05/34` computed; `fwer_budget.eps_eff` (:42), `deflated_metrics.deflated_p` (:63). | Keep S14 LAST as planned and add to its ACCEPT: the memo prints BOTH bars and their ratio at the frozen K, so the loosening is a stated number and not a side effect. |
| SF-18 | 8 | The chi-square regime-drift monitor is partly degenerate on `confidence=T1/T2/T3`: terciles are re-ranked inside `buckets()` on whatever frame it is handed, so those shares are ~1/3 in the fitting window AND ~1/3 in the monitored window by construction and can never drift. That component is a recycled denominator (contract B9). | MED | `regime_calibration.buckets` :52-58. | Run the chi-square over the `phase` / `rest` / `month` components only, or freeze the tercile cut points from the fitting window and apply them unchanged to the monitored window. |

### The exact check for question 3 (prove the promotion rule predates the first pass)

Timestamps alone cannot prove it: `%cI` is settable via `GIT_COMMITTER_DATE`, and SF-3 shows the
spec as planned is not committable at all. The check that actually holds is content identity plus
ordering, all three parts required:

    # 1. the spec must be TRACKED (SF-3 fix) and its add-commit must exist
    git log --diff-filter=A --format='%H %cI' -- docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md
    # 2. its blob hash NOW must equal the blob hash stored on every charged row
    git hash-object docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md
    sqlite3 data/cache/eval_gate/hypotheses.sqlite \
      "select distinct prereg_sha256 from result where tier in ('T2','T3')"
    # 3. the add-commit must be an ANCESTOR of the commit that added the runner's tier path
    git merge-base --is-ancestor <spec_add_sha> <runner_change_sha> && echo ORDERED
    # 4. and the first result row must postdate the add-commit
    sqlite3 data/cache/eval_gate/hypotheses.sqlite \
      "select min(run_at) from result where tier in ('T2','T3')"

Part 2 is the load-bearing one: it is tamper-evident without trusting any clock. Editing the spec
after the fact changes its blob hash, and every stored row then fails the equality check.

## 2. Missing-parquet list (plan section 2 enumerated; verified by ls plus schema read)

7 of the 42 explicitly named paths do not exist. Everything else was confirmed present at the row
counts the plan states (NBA gate 1,814 x 14; MLB 38,809 x 8; soccer 25,834 x 15; tennis 41,886 x 10;
`asof_player_adv` 77,728 x 9; `bullpen_relief_chains` 71,523 x 10; `nba_checkpoints_full`
465,249 x 13 -- that one under `data/cache/inplay_odds/`, as the plan says).

| missing path | plan claim | status |
|---|---|---|
| `data/domains/soccer/asof_discipline_features.parquet` | "still NOT materialized -- one call, one family" | ABSENT; the plan is CORRECT about it |
| `data/domains/tennis/asof_features_wta.parquet` | "WTA mirrors `_wta`" | ABSENT |
| `data/domains/tennis/asof_return_wta.parquet` | same | ABSENT |
| `data/domains/tennis/asof_meta_wta.parquet` | same | ABSENT |
| `data/domains/tennis/schedule_density_wta.parquet` | same | ABSENT; and `schedule_density.parquet` is ATP-only (61,232/61,232) |
| `data/domains/tennis/serve_return_profiles_wta.parquet` | same | ABSENT; not needed -- `serve_return_profiles.parquet` has a `tour` column (ATP 1,084 / WTA 246) |
| `data/domains/tennis/travel_scouting_wta.parquet` | same | ABSENT |

Present WTA mirrors: `asof_hold_wta` (11,270 x 20), `asof_setdetail_wta` (11,270 x 40). All glob
families resolved: `opp_allowed_asof_*` 4, `possession_states_*` 2, `pbp_foul_states_*` 2,
`mlb_pitch_states__*` 5, `soccer_shotxgstates__*` 6, `soccer_cardstates__*` 2, `*_price_series` 8.

## 3. Cluster-key recommendation per sport (input to the tiers module)

One-way random-effects ICC via `ingame/gap_effective_n.intraclass_correlation` (:30), computed on
the base squared-error loss `(y - p_base)**2` -- the closest available stand-in for the paired
Brier differential T2 actually scores. `n_eff = n / (1 + ICC*(mbar-1))`.

| sport | n | candidate key | clusters | ICC | design effect | n_eff | recommendation |
|---|---|---|---|---|---|---|---|
| NBA | 1,814 | `away_team` | 30 | 0.0238 | 2.41 | 752 | **team** -- materially below n (41 pct of n) |
| NBA | 1,814 | `home_team` | 30 | 0.0035 | 1.21 | 1,502 | one-sided fit; take the more conservative of the two |
| NBA | 1,814 | `season` | 2 | 0.0025 | 3.25 | 558 | UNUSABLE as a key: 2 clusters means df = 1 |
| MLB | 38,800 | `away_team` | 32 | 0.0022 | 3.67 | 10,580 | **team** -- 27 pct of n |
| MLB | 38,800 | `season` | 17 | 0.0007 | 2.69 | 14,441 | second choice |
| soccer | 25,834 | `div` | 6 | 0.0004 | 2.65 | 9,733 | **div** -- also the replication unit; 38 pct of n |
| soccer | 25,834 | `home_team` | 187 | 0.0025 | 1.35 | 19,194 | weaker |
| tennis | 41,886 | `p1_id` | 1,613 | 0.0041 | 1.10 | 37,962 | **player** -- clustering barely bites (91 pct of n) |
| tennis | 41,886 | `tourney_id` | 2,322 | 0.0023 | 1.04 | 40,294 | equivalent to player |

Reading: the one-row-per-event fact (SF-10) makes `game_id` clustering worthless on all four.
Team/div clustering IS material for NBA (n_eff 752 against n 1,814) and MLB (10,580 against 38,800),
marginal for soccer, negligible for tennis. Declared keys: NBA `team`, MLB `team`, soccer `div`,
tennis `player`. HONEST CAVEATS: (a) team is a CROSSED factor -- each row carries a home and an away
team -- so a one-way ICC on one side understates it; a two-way cluster-robust variance, or a
row-level bootstrap that resamples both team labels, is the correct estimator, and these numbers are
a LOWER bound on the correction. (b) The NBA `season` and the soccer/tennis `corpus_unit` ICCs rest
on 2 to 6 clusters and are noisy; they are listed for completeness, not proposed as keys. (c) On the
RAW outcome `y` rather than the loss, NBA `home_team` ICC is 0.0808 (design effect 5.81, n_eff 312)
-- outcome clustering is stronger than loss clustering, so a monitor that clusters the outcome and a
gate that clusters the loss will not agree; each artifact must state which it used.

## 4. Proposed FAMILIES draft (input to FWER_FAMILIES_SPEC_2026-09-03.md)

Transforms grid from plan section 2 = 9 instances: `raw` (1) + `ew` halflife {3,5,10,20} (4) +
`rank_in_league` (1) + `z_vs_league` (1) + `delta_vs_prior` (1) + `ratio_to_opponent` (1).
Feature counts are the modelable columns actually on disk (join keys, ids, dates, `*_n_prior`
counters and `y` excluded). Hypotheses per family = features x 9 at EMPTY conditioning, one horizon
and one market per family (SF-16 freezes conditioning to the empty set for v1).

| family | sport | horizon | market | features | hypotheses |
|---|---|---|---|---|---|
| nba_gate | nba | pregame | ml | 11 | 99 |
| nba_team_adv | nba | pregame | ml | 27 | 243 |
| nba_defender | nba | pregame | ml | 18 | 162 |
| nba_boxdetail | nba | pregame | ml | 30 | 270 |
| nba_carryover | nba | pregame | ml | 6 | 54 |
| nba_quarter_shape | nba | period | spread | 15 | 135 |
| nba_player_adv | nba | pregame | prop | 5 | 45 |
| nba_roster_value | nba | pregame | ml | 4 | 36 |
| nba_opp_allowed | nba | pregame | prop | 16 | 144 |
| mlb_gate | mlb | pregame | ml | 5 | 45 |
| mlb_inning | mlb | period | total | 6 | 54 |
| mlb_carryover | mlb | pregame | ml | 6 | 54 |
| mlb_bullpen | mlb | pregame | ml | 4 | 36 |
| mlb_framing | mlb | pregame | ml | 3 | 27 |
| mlb_pitch_profiles | mlb | pregame | prop | 19 | 171 |
| soc_gate | soccer | pregame | total | 10 | 90 |
| soc_xg | soccer | pregame | total | 9 | 81 |
| soc_style | soccer | pregame | total | 13 | 117 |
| soc_referee | soccer | pregame | total | 4 | 36 |
| ten_gate | tennis | pregame | ml | 6 | 54 |
| ten_serve | tennis | pregame | ml | 15 | 135 |
| ten_hold | tennis | pregame | ml | 16 | 144 |
| ten_return | tennis | pregame | ml | 18 | 162 |
| ten_setdetail | tennis | pregame | ml | 36 | 324 |
| ten_meta | tennis | pregame | ml | 11 | 99 |
| ten_schedule | tennis | pregame | ml | 3 | 27 |
| ten_profiles | tennis | pregame | ml | 4 | 36 |
| ten_travel | tennis | pregame | ml | 2 | 18 |
| ig_nba_poss | nba | live_tick | inplay | 12 | 108 |
| ig_nba_foul | nba | live_tick | inplay | 9 | 81 |
| ig_mlb_pitch | mlb | live_tick | inplay | 19 | 171 |
| ig_soc_shotxg | soccer | live_tick | inplay | 4 | 36 |
| ig_soc_card | soccer | live_tick | inplay | 6 | 54 |
| ig_ten_game | tennis | live_tick | inplay | 4 | 36 |

**34 families, 376 features, 3,384 hypotheses** at empty conditioning -- 3.4x the plan's
"at least 1,000" ACCEPT bar for S11, so that bar is reachable without any conditioning and SF-16's
v1 freeze costs nothing. `nba_defender` and every in-game family carry SF-9 columns and must be
tagged by SAME-GAME vs AS-OF availability (SF-9) before any student screen reads them.
`soc_discipline` is deliberately absent from this draft: its parquet is not materialized (section 2).

## 5. NOT VERIFIED

- No module was run end to end. Every finding is a static read plus recomputation of catalogue
  shapes, ICC and bar arithmetic. No T1/T2/T3 trial was executed and nothing was charged.
- SF-1 and SF-2 are structural readings of the plan text; no factory code exists yet to test them
  against, so the MAGNITUDE of the selection effect is NOT measured, only its mechanism named.
- The ICC table uses `(y - p_base)**2` as a stand-in for a real paired Brier differential. The true
  design effect under a fitted candidate is unmeasured and may differ.
- Two-way (crossed home/away team) cluster-robust variance was NOT computed; the NBA and MLB
  team-clustered n_eff figures are one-way and are a LOWER bound on the correction.
- `asof_defender_rollup` provenance WAS traced after the first draft of this memo and the result
  REVERSED the original SF-9 claim; SF-9 above is the corrected version. The earlier reading, that
  these columns require video at inference, was wrong: both it and `player_tracking_features_asof`
  come from NBA Stats endpoints. What is NOT verified is the pregame publication latency of
  `boxscoreplayertrackv3` -- the same-game-vs-as-of split in SF-9 rests on it being a box-score
  endpoint, which was not timed against a live slate.
- S04's `student_gate.py` was dispatched to codex and is not reviewed here; only the plan's
  section 1 text and the runtime-purity clause it depends on were checked.
- The 806-column classification covers the parquets named in plan section 2 plus the
  `data/cache/ingame/` globs; other repo parquets were not scanned.
- The FAMILIES hypothesis counts assume one horizon and one market per family. Any family that
  legitimately spans two markets doubles its count and the section-4 total.

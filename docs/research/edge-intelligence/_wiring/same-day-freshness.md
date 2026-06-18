# WIRING SPEC -- SAME-DAY FRESHNESS (the one real pregame lever)

_Part of the edge-intelligence corpus (`_wiring/`). Executable spec for a future BUILD agent.
Grounded in deep-dive 07 (sec 5/6/7: "the only real accuracy lever") + 01 (sec 5: freshness flag
OFF, totals BEHIND by the freshness gap) + 12 (sec 5/7: same-day lineups are the lever we mostly
cannot see keylessly). HONESTY: this is the ONLY pregame input that can structurally close the gap
to the devigged close on totals/props; measured as a leak-free WF lift vs THE CLOSE, not vs the
prior model. ASCII only. READ-ONLY on code; this file only proposes (builders live under `src/**`
and `domains/**`)._

---

## 0. Why this is THE lever (and the only one)

The project's standing diagnosis, stated in three places:
- deep-dive 07 sec 5: "At the historical-data ceiling... ~17 feature-add REVERTs (Loop 7):
  per-row historical features cannot extract more. The real lever is same-day freshness
  (minutes/role/lineup), which a historical box model cannot see."
- deep-dive 01 sec 7: NBA ML MATCHES the close (Brier 0.1735 vs 0.1672); "Totals/ATP stay BEHIND
  by a freshness gap (injuries/lineups/park/weather/SP) that a box model structurally cannot see
  -- closeable only by ingesting same-day availability, not by better modeling."
- `_framework/cut-list-no-edge.md` CUT 2: redirect NBA effort to "(a) same-day FRESHNESS/
  availability (the one unmodeled lever)".

So: every dollar of modeling effort on historical box features is in a CUT category. Freshness is
the one pregame KEEP. The book prices it; we currently do not see it; that delta IS the gap.

There is already a freshness SCAFFOLD: `scripts/platformkit/eval_gate/freshness_schema.py` defines
the typed `InjuryDelta` record, schema validation, and -- critically -- the VINTAGE LEAK GUARD.
This spec wires that scaffold into the actual train + inference builders.

---

## 1. The data to ingest at slate time (per sport)

All keyless / free (the project's hard constraint, deep-dive 12 sec 2.1). Ingest at SLATE TIME
(hours before tip), each row stamped with `extracted_at` (the vintage key, see sec 3):

| sport | freshness inputs | keyless source |
|-------|------------------|----------------|
| NBA   | projected minutes, starting lineup, late scratch, load-management OUT, injury status (OUT/DOUBTFUL/QUESTIONABLE/PROBABLE) | ESPN injury feed (already used by `domains/basketball_nba/ingest_espn_*`), NBA.com injury report |
| MLB   | CONFIRMED starting pitcher (the biggest single MLB lever -- deep-dive 01 sec 6, current Elo is pitcher-blind on 2022-26, deep-dive 12 sec 5 item 4), lineup, bullpen availability, weather/park | `statsapi.mlb.com` probable-pitchers endpoint (same keyless API as `domains/mlb/ingest_current.py`) |
| soccer| confirmed XI, late withdrawals, keeper start | ESPN / football-data (already used by `domains/soccer/ingest_espn_*`) |
| tennis| late withdrawals / retirements, surface confirmation | Sackmann is post-hoc; withdrawals are the only same-day soccer-analog signal |

The PRIMARY NBA targets are projected MINUTES and STARTING/SCRATCH, because counting props scale
~linearly with minutes (`minutes_aware_props.py` already models elasticity; deep-dive 07 sec 1).
The PRIMARY MLB target is the confirmed starting pitcher.

---

## 2. Wire into BOTH builders (the PARITY requirement -- binding)

The most expensive bug class (memory `feedback_train_inference_parity`): a freshness feature added
to the inference builder but not the train builder reads 0.0 at inference and silently degrades.
This spec REQUIRES both, with an asserted-equal schema.

### 2a. Train builder (historical reconstruction, leak-free)
- For team markets: the NBA freshness features attach to the predictor's as-of pipeline. The
  domain seam is `domains/basketball_nba/asof_features.py` (the leak-free as-of feature parquet,
  deep-dive 12 sec 2.1) -- add `vacated_minutes`, `stars_out_count`, `starter_change` columns
  built from the HISTORICAL injury/lineup record, each stamped with the date it was KNOWN.
- For props: `build_pergame_dataset(...)` (`src/prediction/prop_pergame.py:3804`) walks games
  chronologically; add the freshness columns for game G from the injury/lineup record known
  strictly BEFORE G's tip. Append the names to `feature_columns(stat)` (`prop_pergame.py:382`)
  AT THE END (append-only, preserves the 85/129 legacy slicing).
- CAUTION (memory `feedback_no_season_final_features`): never use a season-FINAL minutes average
  as a feature for an individual game -- it leaks the future. Use only PRIOR-to-G rolling minutes +
  the as-of injury status.

HISTORICAL RECONSTRUCTION HONESTY: a back-filled injury status is often outcome-conditioned (we
know post-hoc who actually sat). `freshness_schema.py` already handles this: `is_fallback_proxy`
+ `partition_for_eval(deltas, tip_off)` split leak-free vs fallback-proxy rows; any metric on the
proxy rows is an OPTIMISTIC UPPER BOUND, NEVER the headline verdict. The headline WF lift must use
ONLY forward-captured (`extracted_at < tip`) rows.

### 2b. Inference builder (slate-time)
- The slate-time ingest (sec 1) writes `InjuryDelta` rows (validated via
  `freshness_schema.validate_delta`) into a freshness store keyed by (player/team, game_date).
- The inference feature_row for prop/win-prob must read the SAME column names in the SAME ORDER
  the model was trained on. For props, `predict_pergame(stat, feature_row, ...)`
  (`prop_pergame.py:4859`) slices to `n_features_in_`; the feature_row MUST carry the freshness
  columns or they slice off (the dead-funnel failure mode from `wire-the-dead-funnel.md` sec 0).

### 2c. PARITY ASSERTION (per-file test, binding)
After any freshness retrain, a per-file test asserts:
`set(feature_columns(stat)) == set(model._meta.feature_names)` AND
`model.n_features_in_ == len(feature_columns(stat))`. Mismatch -> FAIL the build (memory
`feedback_pkl_integrity_check`). Also assert the inference builder emits a non-null freshness
column on a known slate row (catches the "reads 0.0" silent failure directly).

HUMAN-GATED: `prop_pergame.py` / `win_probability.py` / `asof_features.py` are under `src/**` and
`domains/**` -- propose-only. The build agent writes the INGEST module + the freshness store + the
PROPOSED builder diff (under `docs/research/organization-sprint/`) + the WF measurement. The
ingest + store can live in `scripts/platformkit/` (a safe area) or a new `domains/<sport>/
ingest_freshness.py` (additive, human-confirm before merge).

---

## 3. The vintage leak guard (this is the whole ballgame)

A freshness delta may inform a prediction ONLY IF it was KNOWN before tip-off. `freshness_schema.py`
already enforces this:
- `assert_vintage(delta, tip_off_iso)` (asserts `extracted_at < tip`, raises LEAK on violation).
- Every ingested row carries `extracted_at` = the ISO datetime the row BECAME KNOWN (not the game
  date). The slate-time scraper must stamp the actual fetch time, idempotently append-only, so the
  forward record is honest. Do NOT overwrite a row's `extracted_at` on re-fetch.
- For backtests, `partition_for_eval` keeps only forward-captured rows in the headline metric.

This is the difference between a real lever and the retracted `+18.38%` market-follow artifact:
the guard is what makes the lift CAUSAL (info known before tip) rather than hindsight.

---

## 4. How to measure (leak-free WF lift vs THE CLOSE)

The bar is NOT "beats the prior model" -- it is "closes the gap to the devigged close" (the gap
freshness is DEFINED as, deep-dive 01 sec 7). Procedure:
1. Build the WF set with freshness columns, forward-captured rows ONLY (sec 3).
2. Run `scripts/platformkit/eval_gate/run_gate.py` `evaluate_corpus` (walk-forward, leak-free,
   `select_inside=True`) on the markets freshness should move: NBA TOTALS + counting props,
   MLB moneyline (pitcher), totals.
3. Report per-corpus Brier(model_with_freshness), Brier(close), BSS, ECE, clustered DM stat+p+CI95
   (deep-dive 01 sec 2c). The win condition: the BSS-vs-close gap SHRINKS (totals move from BEHIND
   toward MATCH) with `all_improve` across folds, replicated on >=2 seasons (proof-standards item 4).
4. A NULL is still a success: if freshness does NOT shrink the gap (e.g. the keyless feed is too
   noisy / too late), record it -- it tells us the keyless freshness ceiling is below the close,
   which is itself a finding (deep-dive 12 sec 7: "same-day lineups... are the lever we mostly
   cannot see keylessly").

Evidence tier: starts HYPOTHESIS (strongest prior of any lever in the corpus); advances to
CALIBRATION-PROVEN only on leak-free OOS gap-shrink replicated on >=2 corpora with forward-captured
vintage. NEVER CLV-PROVEN until forward paper accrues (deep-dive 12 sec 5: prop CLV not yet
computable).

## 5. Ordering (do the highest-prior first)
1. MLB confirmed starting pitcher (deep-dive 01 sec 6: "the biggest single lever"; current Elo is
   pitcher-blind on 2022-26 per deep-dive 12 sec 5 item 4 -- this is the cleanest, most-measurable
   freshness win, and the keyless probable-pitcher endpoint already exists).
2. NBA projected minutes + scratches into props (the documented decisive NBA lever, deep-dive 07
   item 6).
3. NBA stars-out / vacated-minutes into win-prob + totals.
4. soccer confirmed XI; tennis withdrawals (thin, lower prior).

## 6. Honest ceiling
Per deep-dive 07 sec 7 + 12 sec 7: freshness is the ONLY input that could close the totals/props gap
to the close, but the keyless feeds are LATE and NOISY relative to a book's paid, instant injury
desk. The realistic best is "shrink the totals gap from BEHIND toward MATCH on the games where a
clean OUT/scratch is known pre-tip" -- a CALIBRATION win, not a $-edge (the book sees the same news).
Where the keyless feed lags the book, the gap stays open and we record that honestly.

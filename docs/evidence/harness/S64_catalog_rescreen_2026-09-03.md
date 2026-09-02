# S64 -- the 60 catalog classes and the 86 registry signals, re-screened with archived differentials

2026-09-03 | lane H1 (main repo) | UNCHARGED RE-SCREEN | calibration language only

`spa_catalog_report.txt` prints `NOT_EVALUABLE` sixty times for one stated
reason: *"historical per-signal loss differentials are not archived"*. The 86
registry signals were never market-tested at all. This lane does not re-open
those verdicts -- it supplies the evidence they never kept.

**These are SCREENS, not findings.** No FWER ledger row was appended, no prereg
was sealed, no K was read, nothing was promoted or priced. A SCREEN_POSITIVE is
a candidate for a later charged trial and nothing more. `data/registry/` was
read only.

---

## What was run

`scripts/platformkit/eval_gate/catalog_rescreen.py` (300 LOC, additive). Per
signal: a walk-forward single-feature logistic on `[logit(incumbent), feature]`
scored against the incumbent alone, **per `corpus_unit`, ordered by
`event_date`** (S50), with the per-unit paired differential written to
`data/cache/eval_gate/differentials/<sport>/<signal>.parquet` (Q9).

Incumbent, LABELLED per sport -- never pooled, never implied:

| sport | incumbent | source |
|---|---|---|
| soccer | **devigged decimal close** | `close_join.gate_corpus_states` |
| tennis | **devigged decimal close** | `close_join.gate_corpus_states` |
| nba | **p_base** (no close on this corpus) | `gate_corpus_nba.parquet` |
| mlb | **p_base** (no close on this corpus) | `gate_corpus_mlb.parquet` |

Leak contract: expanding-window folds (`stack_fit.expanding_window_splits`,
5 folds after a 50% warm-up); a training row must predate the test block's first
date by at least `walkforward.EMBARGO_DAYS` (imported, never restated);
standardizer and logistic fit on TRAIN rows only; DM clustered on `event_id`
(`dm_test.diebold_mariano`). No bar or threshold in any existing module was
touched.

## Distribution across the 146

| | catalog (60) | registry (86) | total (146) |
|---|---|---|---|
| testable | **60** | **0** | 60 |
| SCREEN_POSITIVE | 2 | 0 | 2 |
| SCREEN_NULL | 57 | 0 | 57 |
| SCREEN_NEGATIVE | 1 | 0 | 1 |
| NOT_TESTABLE | 0 | 86 | 86 |

Positive **at any margin** (delta > 0, significance ignored): **38 of 60**
catalog screens. Negative at any margin: 22 of 60. At the DM 0.05 level only 3
of 60 separate from zero in either direction -- which is what an efficient
market looks like, and the deltas below are in the 4th-5th decimal of Brier.

All 86 registry signals are NOT_TESTABLE for the same measured reason: neither
the full `signal_id` nor its leaf token names a column in any of the four gate
corpora or in any of the 32 named catalogue parquets that carries an
`event_id`/`game_id` key. Both absent names are recorded per signal in the JSON
(`absent_columns`), e.g. `player.scoring.catch_shoot_ppp` /
`catch_shoot_ppp`. They are player-, lineup- and team-grain descriptors
(59 player / 19 team / 8 lineup; 72 `folded`, 14 `deferred`) with no feature
column materialised anywhere on this box.

## Top 10 catalog SCREENS by paired Brier delta

Positive delta = the two-feature model lost less than the incumbent on that
sample. Every row is a SCREEN.

| # | signal | incumbent | delta | DM p | n | n_eff | verdict |
|---|---|---|---|---|---|---|---|
| 1 | nba:EloRatioXB2BDiffSignal | p_base | +0.002657 | 0.2575 | 881 | 881 | SCREEN_NULL |
| 2 | nba:B2BDifferentialSignal | p_base | +0.002630 | 0.2623 | 881 | 881 | SCREEN_NULL |
| 3 | nba:Win10XRestDiffSignal | p_base | +0.001700 | 0.4371 | 881 | 881 | SCREEN_NULL |
| 4 | nba:EloXRestDiffSignal | p_base | +0.001618 | 0.4456 | 881 | 881 | SCREEN_NULL |
| 5 | nba:RestDiffSignedSignal | p_base | +0.001542 | 0.4804 | 881 | 881 | SCREEN_NULL |
| 6 | nba:RestBucketSignal | p_base | +0.001163 | 0.5811 | 895 | 895 | SCREEN_NULL |
| 7 | nba:HomeB2BIndicatorSignal | p_base | +0.001011 | 0.6495 | 895 | 895 | SCREEN_NULL |
| 8 | nba:AbsRestDiffSignal | p_base | +0.000387 | 0.8500 | 881 | 881 | SCREEN_NULL |
| 9 | nba:AbsRestDiffXEloMismatchSignal | p_base | +0.000366 | 0.8597 | 881 | 881 | SCREEN_NULL |
| 10 | nba:EloXHomeB2BSignal | p_base | +0.000234 | 0.9131 | 895 | 895 | SCREEN_NULL |

The ten largest deltas are ALL NBA, ALL against `p_base` (not a close), and ALL
SCREEN_NULL: the NBA corpus is 1,814 rows, so `n_eff` ~ 890 buys no resolution
at this effect size. Read them as noise, not as a ranking.

The only three screens that separate from zero:

| signal | incumbent | delta | DM p | n_eff | corpus_unit | verdict |
|---|---|---|---|---|---|---|
| mlb:EloClosenessSqH2HSignal | p_base | +0.000093 | 0.0348 | 13,992 | era_2010_2021 | SCREEN_POSITIVE |
| mlb:EloRatioH2HSignal | p_base | +0.000084 | 0.0494 | 13,992 | era_2010_2021 | SCREEN_POSITIVE |
| soccer:LamTotalDeviationSignal | devigged close | -0.000470 | 0.0314 | 8,161 | D1/E0/E1/F1/I1/SP1 | SCREEN_NEGATIVE |

Both MLB SCREEN_POSITIVEs are against **p_base, not a close** (Brier 0.242547
-> 0.242454 on `mlb_EloClosenessSqH2HSignal`), sit on a **single corpus_unit**,
and would not survive any multiplicity correction over 60 screens -- at
`alpha = 0.05` and 60 screens, 3 crossings is the number chance produces. They
are logged as candidates for a charged trial, not as results. The single
SCREEN_NEGATIVE is the honest direction: adding `lam_total` deviation to the
devigged soccer close makes the forecast worse.

## Runtime availability

**0 of 146 signals is declared runtime-available.** `foundry/seed_queue.py:49-51`
sets `runtime_available = False` for every catalogue column by construction
("honest-conservative: the teacher lane owns these columns until a runtime
adapter is measured"), and `signal_registry.parquet` carries no runtime column
at all (its schema is signal_id/entity/domain/granularity/source/formula/
leak_rule/consumer/ev_tier/coverage_pct/status).

Separately measured, and NOT the same claim: all 60 catalog features are pure
transforms of schedule-grain ingredients (Elo, rest days, back-to-back flags,
rolling win10, head-to-head rate, Poisson lambdas, surface Elo, best-of) that
the domain replays compute from schedule + result parquets with no video and no
tracking. They are therefore runtime-*computable* in principle. Nobody has
measured a runtime adapter for any of them, so the declared count stays 0.

## A defect this lane found and fixed before reporting

A row whose base-ingredient replay never joined carries all-NaN ingredients, but
a threshold transform such as `(best_of == 5.0).astype(float)` maps NaN to a
finite `0.0`. On the first pass that invented an entire tennis **WTA** corpus_unit
(and part of an MLB `era_2022_2026` unit) out of 11,270 and 11,179 rows that had
no ingredients at all. Fixed by masking unjoined rows out of every feature
before screening; the shipped run screens tennis on ATP only and MLB on
`era_2010_2021` only, and says so in every affected row's `corpus_unit`.

## Reproduction (A2)

All 60 archived differentials were re-scored **from the parquet alone** --
`d = loss_incumbent - loss_model` recomputed, `diebold_mariano` re-run on
`event_id` clusters -- and 60/60 reproduce their JSON `n`, `n_eff`,
`brier_delta` and `dm_p` to 1e-12. That is the Q9 property S63 could not
satisfy: this artifact can be re-scored without re-running the model.

## Tests

`scripts/platformkit/eval_gate/test_catalog_rescreen.py` -- **8 passed**
(per-file). A planted incumbent-invisible driver yields SCREEN_POSITIVE with an
archived differential of exactly the expected length (450 rows, `n_eff` equal to
its distinct cluster count) whose `d` column equals
`loss_incumbent - loss_model`; the same construction with no plant does not
screen positive; a missing column yields NOT_TESTABLE naming the absent column
with no differential written; a corpus_unit below the row minimum yields
NOT_TESTABLE with an empty differential; `verdict_of` is pinned on four cases.

## Artifacts

- `docs/evidence/harness/CATALOG_RESCREEN_2026-09-03.json` -- 146 rows: signal,
  sport, kind, incumbent (labelled), n, n_eff, brier_delta, DM p, corpus_unit,
  differential_path, verdict, absent_columns.
- `data/cache/eval_gate/differentials/{nba,mlb,soccer,tennis}/*.parquet` -- 60
  per-unit paired differentials (gitignored; local + rebuildable).
- `scripts/platformkit/eval_gate/catalog_rescreen.py` (300 LOC),
  `scripts/platformkit/eval_gate/test_catalog_rescreen.py`.

## NOT VERIFIED

- **Nothing here is a finding.** No prereg, no FWER charge, no K read, no
  multiplicity correction applied across the 60 screens. The 3 crossings at
  alpha 0.05 are consistent with chance alone at that count.
- **Two sports are screened against `p_base`, not a close.** NBA and MLB gate
  corpora carry no devigged close, so their screens measure "does the feature
  add to our own base", never "does it beat the market". Only soccer and tennis
  are market-relative.
- **Single-unit sports.** MLB screened on `era_2010_2021` only (the adapter's
  `_get_games()` covers `games.parquet`, so all 11,179 `era_2022_2026` rows have
  no base ingredients); tennis screened on ATP only (`TennisAdapter._get_matches()`
  is ATP; all 11,270 WTA rows have none). Q5's two-corpus rail is therefore
  UNMET for both -- both are SINGLE-UNIT screens.
- Incumbent coverage is partial where the close is: soccer 16,322 of 25,834 rows
  carry a close, tennis 25,693 of 30,616 ATP rows; NBA `2025-26` joins 536 of 589.
- The soccer/tennis closes carry `vintage: SYNTHETIC` (S34) -- `state_ts` is
  constructed, not a real odds timestamp. Nothing was scored against a real
  quote time.
- The fold protocol is expanding-window with a date embargo, **not** CPCV and not
  `walkforward.walk_forward` itself (that harness is O(n^2) in same-team purge
  checks and cannot walk a 39k-row corpus). Q4's CPCV requirement is UNMET; this
  is a screen, so nothing rests on it, but a charged trial must not reuse this
  protocol as-is.
- `base_frame` rebuilds each sport's base ingredients by calling the same domain
  replay functions the adapter's `feature_bundle` calls; it was NOT diffed
  row-by-row against a real `feature_bundle` output, because that bundle drops
  `event_id` and cannot be joined back.
- Registry NOT_TESTABLE is a NAME lookup: a registry signal whose feature exists
  on disk under a different column name would be missed. The lookup covers the
  4 gate corpora plus the catalogue parquets that carry an `event_id`/`game_id`
  key; parquets without such a key were skipped and are not counted as absent
  evidence.
- `n_eff` here is the DM cluster count (one cluster per event, pregame), not an
  autocorrelation-adjusted effective sample.
- No pod work, no deploy, no `data/registry/` write, no flag flipped on, no bar
  moved, no ledger row. No monetary quantity of any kind is computed anywhere
  in this lane; every number above is a Brier-scale calibration difference.

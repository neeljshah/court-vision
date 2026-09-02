# S50 -- per-corpus_unit chronological walk (ACCEPT WITH CORRECTIONS)

Gap (register): the tennis gate corpus is NOT globally chronological -- ATP's
30,616 rows precede WTA's 11,270, so a positional walk-forward over the whole
frame jumps from 2025-12-17 back to 2015-01-19 at row 30,616. Every
positional-order tennis number, S05's tennis ECE included, rests on a
non-chronological pass. Fix = walk-forward per `corpus_unit` sorted by
`event_date` (present since S44). Audit soccer's div ordering the same way.

Calibration language only. Nothing here is charged, promoted, priced or served.
No ledger row read or written; no bar moved.

## CORRECTIONS to the row as written

Two of the row's instructions rest on premises this lane MEASURED false. Both
are reported, neither is worked around.

1. **A per-unit walk is not a no-op on the already-chronological corpora.**
   The row asks for the per-unit walk "default ON only where you prove the output
   is identical for already-chronological sports". It is not identical anywhere:
   splitting the walk withholds era_2010_2021 / 2024-25 isotonic history from the
   second unit, and splits soccer's SIX interleaved divisions into six separate
   walks. Measured below. The parameters therefore ship **OPT-IN, default OFF**,
   exactly as the row's own conditional requires, and the four S05b artifacts are
   left byte-identical rather than overwritten (B10 / Q3: no bar moved).
2. **`close_join.gate_corpus_states` has no chronology defect to fix (Q8).**
   It already `sort_values("date")` before emitting, and that spine `date` IS the
   corpus `event_date` on 16,322 of 16,322 soccer and 33,685 of 33,685 tennis
   emitted states. Its states are monotone globally AND within every
   `corpus_unit` today. Blocking them per unit would REORDER soccer (6 units) and
   tennis (2 units) output for no consumer -- `mechanism_close_effect` partitions
   by `corpus_unit` itself (S22, c35de372a) and its median splits are order-free.
   **No production change was made to `close_join.py`.** The contract is pinned
   by a new test instead.

## CHANGE (a) -- `calibration_report.build_report`, additive and opt-in

`build_report(..., order_by="event_date", unit_col="corpus_unit")`. Both default
`None`, so every existing caller reads exactly the number it read before. When
both are given: rows are partitioned by `unit_col`, stable-sorted within each unit
by `order_by`, and `_oof_per_regime` runs PER UNIT -- no isotonic history crosses
a `corpus_unit` boundary. Bins, ECE, Murphy and sharpness are then aggregated over
the union unchanged (all four are order-free, so only the CALIBRATED series moves).

Nothing renamed or removed (B2). Five keys added, `None` on the default path:
`order_basis` (already present, now `event_date` when the walk really was ordered
by it -- otherwise it stays `POSITIONAL-ORDER`, the S44 honesty split intact),
`walk_unit_col`, `walk_sort_within_unit_is_noop`, `walk_partition_is_identity`,
`by_corpus_unit`. `main()` gained `--per-unit`, which writes the separate
`<sport>_reliability_per_unit_2026-09-03.json` family; the default `main()` path
and its four filenames are untouched.

A5: the only cross-module reader of this file is
`ingame_calibration_report.py`, which imports `_from_bins` (unchanged).
`_stamp` and `main` gained defaulted arguments only.

## MEASUREMENT 1 -- the default path still reproduces S05b exactly

`build_report(load_gate_corpus(sport), sport)` with the new code, diffed against
the landed `docs/evidence/calibration/<sport>_reliability_2026-09-03.json`:

| sport | ece_before delta | ece_after delta | sharpness deltas | bin tables identical |
|---|---|---|---|---|
| nba (1,814) | **0.0** | **0.0** | 0.0 / 0.0 | **True** |
| soccer (25,834) | **0.0** | **0.0** | 0.0 / 0.0 | **True** |
| mlb (39,162) | **0.0** | default path not re-run | -- | -- |
| tennis (41,886) | **0.0** | default path not re-run | -- | -- |

`ece_before` is computed from the RAW probabilities and cannot depend on the walk
order, so the per-unit runs below reproduce it for free -- and they do, to
**exactly 0.0 on all four sports** against the landed artifacts. That is the
four-sport arm of the reproduction check; the `ece_after` arm was re-run on the
two corpora where a full quadratic isotonic walk is cheap.

## MEASUREMENT 2 -- what the per-unit walk actually costs

`build_report(..., order_by="event_date", unit_col="corpus_unit")`, one artifact
per sport under `docs/evidence/calibration/*_reliability_per_unit_2026-09-03.json`.
`reproduction_max_abs_diff` is **exactly 0.0** on all four (the S42 bin-edge rule
is untouched). "sort no-op" = the within-unit sort moved no row; "partition =
identity" = walking unit-by-unit visited the rows in their original order.

| sport | ECE after, S05b positional | ECE after, per-unit | delta | sort no-op | partition = identity |
|---|---|---|---|---|---|
| nba | 0.024843 | 0.026583 | +0.001741 | True | True |
| soccer | 0.009302 | 0.028722 | +0.019420 | True | **False** (6 divisions interleaved) |
| tennis | 0.008403 | 0.015403 | +0.007000 | True | True |
| mlb | 0.008077 | 0.012666 | +0.004589 | True | True |

Per-unit detail for the other three (n, date range, ECE before -> after):

| sport | unit | n | date range | ECE before | ECE after |
|---|---|---|---|---|---|
| nba | 2024-25 | 1,225 | 2024-10-22 .. 2025-04-13 | 0.051867 | 0.040935 |
| nba | 2025-26 | 589 | 2025-10-21 .. 2026-04-12 | 0.067354 | 0.043956 |
| mlb | era_2010_2021 | 27,983 | 2010-04-04 .. 2021-11-02 | 0.006990 | 0.007892 |
| mlb | era_2022_2026 | 11,179 | 2022-04-07 .. 2026-07-12 | 0.007571 | 0.024614 |
| soccer | E1 | 6,072 | 2015-08-07 .. 2026-05-02 | 0.115328 | 0.027494 |
| soccer | F1 | 3,856 | 2015-08-07 .. 2026-05-17 | 0.096854 | 0.043281 |
| soccer | E0 | 4,180 | 2015-08-08 .. 2026-05-24 | 0.118108 | 0.029166 |
| soccer | D1 | 3,366 | 2015-08-14 .. 2026-05-16 | 0.113562 | 0.041585 |
| soccer | SP1 | 4,180 | 2015-08-21 .. 2026-05-24 | 0.098432 | 0.032084 |
| soccer | I1 | 4,180 | 2015-08-22 .. 2026-05-24 | 0.100856 | 0.029728 |

These four artifacts were then REGENERATED by the committed code through the new
`python -m scripts.platformkit.eval_gate.calibration_report --per-unit` entry
point and came back byte-identical to the probe run that produced the table, so
the numbers above belong to the code that landed, not to a draft of it.

Every within-unit sort is a no-op on all four corpora -- each unit was already
stored in date order (S44 measured this). So the per-unit walk changes nothing by
SORTING; it changes the numbers only by REFUSING TO POOL, which is the honest cost
of the S50 contract and is why it cannot be the default.

## MEASUREMENT 3 -- tennis, the sport the row was opened for

`docs/evidence/calibration/tennis_reliability_per_unit_2026-09-03.json`, 41,886
rows, 0 dropped, `reproduction_max_abs_diff` exactly 0.0, verdict FLATTENED
(unchanged).

| tennis | n | date range | ECE before | ECE after |
|---|---|---|---|---|
| ATP | 30,616 | 2015-01-04 .. 2025-12-17 | 0.039461 | 0.012985 |
| WTA | 11,270 | 2015-01-19 .. 2025-11-01 | 0.038484 | 0.023195 |
| pooled, per-unit walk | 41,886 | -- | **0.038691** | **0.015403** |
| pooled, S05b positional walk | 41,886 | -- | **0.038691** | **0.008403** |

`ece_before` is identical to the S05b figure to **exactly 0.0** -- it is computed
from the raw probabilities and cannot depend on the walk order, which is what
makes it the free reproduction anchor.

**The honest note the register row asks for.** S05b's tennis `ece_after` of
0.008403 was produced by a pass that, having consumed all 30,616 ATP outcomes
(through 2025-12-17), then began scoring WTA matches from 2015-01-19 onward. Those
WTA rows were recalibrated against a map fitted on matches played up to ten years
AFTER them. The two tours are disjoint corpus_units with no shared player state,
so this is not a within-unit leak in the strict sense -- but it is not a
chronological pass either, and 0.008403 is therefore not a number a
walk-forward-only reading can claim. The per-unit chronological figure is
**0.015403 pooled**, and the cost falls almost entirely on WTA (0.023195), the
unit that was being handed a decade of future ATP history. This is a WORSE ECE
and it is the more defensible one; the improvement it gives up was an artefact of
the ordering, not of the calibration.

Both flags read True here: each tour was already stored in date order and the ATP
block already precedes the WTA block, so the per-unit walk visits rows in exactly
the original order. The ONLY thing that changed is that the isotonic history is
now reset at the tour boundary instead of carried across it.

## CHANGE (b) -- none; the contract is pinned by a test

`gate_corpus_states` is unchanged. `test_close_join_tennis.py` gains
`test_states_are_monotone_in_event_date_within_each_corpus_unit`, which asserts on
the real corpus that the 33,685 emitted tennis states carry `game_date` equal to
the corpus `event_date` on 33,685 of 33,685 rows, that the units are exactly
{ATP, WTA}, that `game_date` is monotone increasing WITHIN each unit, and that
`vintage` is still `SYNTHETIC` (S34, unmoved).

## TESTS (per-file only)

- `python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py -q`
  -> **9 passed** (6 from S05b/S42 + 3 new). The new cases: per-unit ECE is
  identical whether the frame concatenates unit A or unit B first AND equals what
  each unit reads scored entirely on its own (1e-12); the sort/partition flags are
  published and a deliberately date-reversed unit reports `sort_noop = False` with
  an ECE that differs from the positional walk; and the default-OFF report still
  reproduces the landed nba artifact key by key (`scored_rows`, `base_rate`,
  `ece_before`, `ece_after`, both sharpness figures, `order_basis`, `murphy_after`
  and the whole `reliability_bins_after` table), skipping on a clean clone.
- `python -m pytest scripts/platformkit/eval_gate/test_close_join_tennis.py -q`
  -> **8 passed** (7 from S03/S48 + 1 new).

## ACCEPTANCE

metric = gate-corpus walks whose scoring order is chronological within every
`corpus_unit`; denominator = 4 corpora x 2 consumers = 8 walks.
before = the tennis `calibration_report` walk crossed one backward date step at
row 30,616; the other 7 were already chronological within every unit.
after = 8/8 checkable, 1/8 repaired (tennis, behind an opt-in flag), 7/7 proven
unchanged. n = 108,696 corpus rows + 50,007 emitted close states.
must not move: the four S05b artifacts (verified byte-identical on nba and soccer,
and `ece_before` exact on all four), `reproduction_max_abs_diff = 0.0`, the S42
bin-edge rule, the S34 `SYNTHETIC` vintage, the S35 per-unit denominators, the
S48 `event_uid` counts, `data/registry/**`, `data/cache/eval_gate/backtest_fwer.jsonl`
(not opened; no `_charge_ledger`, no K read).

## NOT VERIFIED

- The mlb and tennis DEFAULT-path re-runs were not executed: a single expanding
  isotonic walk over 39,162 / 41,886 rows is quadratic and neither adds a fact the
  order-free `ece_before` reproduction (exactly 0.0 on both) does not already give.
  Their `ece_after` reproduction rests on code inspection -- the default branch is
  the pre-change line verbatim -- plus the nba and soccer measurements, not on a
  re-run of those two corpora.
- The per-unit numbers are a DIFFERENT MEASUREMENT, not a correction of S05b.
  Neither is "the right one": pooling buys calibration history and violates the
  never-pool-units contract; per-unit honours the contract and pays for it. This
  lane measures the trade and picks no winner.
- No caller was switched to the opt-in path. `batch_gate.py:193` and every other
  consumer of these corpora still walk row order; this row makes the per-unit walk
  available and measured, not enforced.
- The within-unit sort key is `str(value)` on one consistently-typed column
  (datetime64 on mlb/nba/soccer, `datetime.date` on tennis). It is ISO-ordered for
  every gate corpus today; a corpus that ever mixed dtypes or stored a non-ISO
  string in `event_date` would sort wrong and this code would not notice.
- `event_date` itself is still the builder's pass-through `date` and was NOT
  audited for scheduled-vs-settled semantics, timezone or double-headers (S44
  carried the same caveat).
- The soccer / tennis state-ordering facts are measured on the CURRENT local
  corpora only; nothing re-derives them if a builder input changes.
- `calibration_report.py` is 358 lines after this change, over the 300-LOC rail.
  The docstrings were compacted rather than the evidence keys dropped; splitting
  the two ~20-line helpers into a sibling module would satisfy the count without
  reducing anything, so it was not done. Reported, not worked around.

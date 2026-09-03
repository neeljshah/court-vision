# S123 (a) + (c) -- the NBA in-game baseline ordering is now RECORDED, and a screen can name its anchor

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S123 (signals-ingame), the secondary
finding of S92. **Parts (a) and (c) only.** Part (b) -- what the answer layer should say
about the NBA in-game incumbent -- is Neel's decision and was NOT touched.

Verdict: **LANDED, DESCRIPTIVE.** The ordering S92 measured as a by-product now has a
home in the S43 in-game calibration report, and `ingame_screen_nba` can state which arm
it anchors on instead of inheriting it silently. No bar, no gate, no charge.
Uncharged: no prereg DRAFT, no seal, K never read, `_charge_ledger` never called,
`data/cache/eval_gate/backtest_fwer.jsonl` never opened -- **18 rows, md5
`a4ae7c13995672e478d59770591b83ba`, before and after** (the value S92 recorded).
`data/registry/` untouched, no flag flipped on, no bar moved (Q3: `ingame_screen.BAR`
is still 0.004, asserted by the new test), no pod contact, no push.
Calibration language only (Q6): this memo compares Brier scores of three arms and claims
nothing about value.

---

## STEP 0 -- premise (Q8): reproduced, NOT falsified

Recomputed from the S92 archives alone, **no refit** -- `p_null` and `p_incumbent` are
read as archived, so this is a reproduction of the ordering, not a re-scoring.

| corpus | ticks | games | market (`market_prob`) | recal null (`p_null`) | ladder BASE (`p_incumbent`) |
|---|---|---|---|---|---|
| `s92_nba_lineup_dynamic_2026-09-03_all.csv` | 79,554 | 661 | **0.142877** | **0.144293** | **0.146850** |
| `s92_nba_lineup_dynamic_2026-09-03_rated.csv` | 33,713 | 284 | **0.144101** | **0.146843** | **0.153324** |

All six reproduce the S92 memo exactly. The ordering is
**market < recal_null < ladder_base** by Brier on both corpora.

**The report had no NBA in-game block.** `ingame_calibration_report.py` before this lane:
one corpus (`SERIES_CSV` = `s06_stacker_series_2026-09-03.csv`, MLB window 1), one output
(`mlb_ingame_reliability_2026-09-03.json`), three MLB series (`raw_model`,
`e4_blend_leakfree_gd`, `market`). No NBA path, and no artifact in
`docs/evidence/calibration/` carrying this ordering. **NOT FALSIFIED for (a).**

**Which arm is which in `ingame_screen_nba` (S102).** Confirmed by reading the loader and
`ingame_screen._fit`:

* **INCUMBENT / anchor = the RAW IN-PLAY MARKET LINE.** `load_screen` puts
  `frame["market"]` into the tier's `p_e4` slot, so `brier_e4 == brier_market` by
  construction -- the module docstring already labels that identity honestly.
* **NULL arm = S94's global recalibration of that line**, `[1, logit(p_e4)]` fit
  walk-forward on exactly the candidate's rows (`ingame_screen._fit`, its `null` return).
* The BAR is applied to `improvement_vs_null`, so the two arms differ ONLY by the feature
  term.
* The `nba_mechanism_ladder` BASE **does not appear in S102 at all** -- it is S84's and
  S92's incumbent, on a different (Polymarket checkpoint) corpus. The two lanes were
  measuring candidates against different anchors, and nothing said so.

## (a) The NBA in-game block in the S43 report

`scripts/platformkit/eval_gate/ingame_calibration_report.py` gains `nba_ingame_block`
(one S92 corpus through the module's own `build_ingame_report`) and `main_nba` (both
corpora, one artifact). The MLB `main()` is untouched; `__main__` dispatches to the NBA
path only on an explicit `nba` argument, so the default entry point is unchanged.

    python -m scripts.platformkit.eval_gate.ingame_calibration_report nba

```
CORPUS | ARM | BRIER | ECE | N | N_INFORMATIVE | N_EFF
all | market | 0.142877 | 0.010583 | 79554 | - | 1142.2
all | recal_null | 0.144293 | 0.011753 | 79554 | 61710 | 1145.6
all | ladder_base | 0.146850 | 0.013125 | 79554 | 72483 | 1135.5
rated | market | 0.144101 | 0.021414 | 33713 | - | 509.8
rated | recal_null | 0.146843 | 0.033990 | 33713 | 26637 | 517.8
rated | ladder_base | 0.153324 | 0.035221 | 33713 | 31017 | 513.3
```

Artifact: `docs/evidence/calibration/nba_ingame_baseline_2026-09-03.json` (144 KB).
Per corpus and per arm it carries reliability bins on the ONE S42 bin rule
(`calib_decomp.bin_edges(10)`), ECE, the three Murphy terms, sharpness, the max-loser-WP
distribution, `ess.n_eff` (game-clustered, over that arm's OWN level loss) and -- for the
two model arms -- the S87 `n / n_informative / n_eff` triple from
`attach_informative_summary`. The market arm has no `n_informative` because it is the
reference the S87 flags are computed AGAINST; that is the existing `build_ingame_report`
contract, not a gap opened here.

**ECE orders the same way as Brier on both corpora** (0.0106 / 0.0118 / 0.0131 and
0.0214 / 0.0340 / 0.0352), so the ordering is not a Brier-versus-ECE artifact:
recalibrating the line makes it measurably *less* reliable at this grain, not more.

DESCRIPTIVE: the artifact arms no bar and no gate. Its `mode` is `DESCRIPTIVE` and its
`note` says so in the file.

## (c) `ingame_screen_nba` can now NAME its anchor

`load_screen(path, n_folds, incumbent=...)` takes one of
`("market", "recal_null", "ladder_base")`.

* **`"market"` is the DEFAULT and returns the frame untouched** -- the screen every
  published NBA artifact was produced by. Asserted byte-identical by the new test
  (`pd.testing.assert_frame_equal` plus a CSV-render equality) and on the real corpus by
  the pre-existing `test_the_loader_puts_the_market_in_the_anchor_slot...` (232,951 rows,
  797 games, `p_e4 == market`), which still passes.
* **`"recal_null"`** puts S94's global recalibration in the anchor slot. It IS
  `s94_nba_early_shrinkage._recal` -- the same unregularised `LogisticRegression(C=1e6)`
  on `[logit(market)]` -- fit walk-forward, not a restatement of it.
* **`"ladder_base"`** puts `nba_mechanism_ladder` BASE there, fit by that module's own
  `_fit_predict` on its own triple `[logit_p0, margin_s, z]`, rebuilt from the tick rows
  by `ladder_base_columns`.

The machinery lives in a NEW sibling module
`scripts/platformkit/foundry/ingame_incumbent_nba.py` (115 lines) purely because
`ingame_screen_nba.py` sat at 278 of its 300-line rail. `ingame_screen_nba.py` gains 3
lines of wiring, a docstring paragraph and two `meta` keys (`incumbent`,
`incumbent_options`), and is now 295 lines. `foundry/ingame_screen.py` is IMPORTED, never
edited (S121 owns it).

**The fold rule is the tier's own**, restated once in `folds()` for a multi-column fit:
blocks in `game_date` order, block 0 train-only, a train game's LAST tick at least
`EMBARGO_DAYS` before the fold's first tick, with game-disjointness and the purge
ASSERTED per fold exactly as `walk_forward_feature` asserts them.

**The known ceiling, stated:** a FITTED anchor exists only out of fold, so the train-only
seed block has none. Those rows are dropped and the survivors re-blocked, which keeps the
screen's fold count. Re-blocking cannot leak -- every surviving row's anchor was fit on
games that ended at least `EMBARGO_DAYS` before its own fold, hence before any block it
can land in -- but it does mean an option run screens on **fewer rows than the default**,
so the two are NOT comparable row-for-row.

### The option, measured on the real S86 screen corpus (uncharged, descriptive)

| anchor | rows | games | blocks | anchor Brier | market on the SAME rows |
|---|---|---|---|---|---|
| `market` (default) | 232,951 | 797 | 6 | 0.078611 (all rows) | -- |
| `recal_null` | 192,635 | 673 | 6 | **0.078930** | 0.078611 |
| `ladder_base` | 192,635 | 673 | 6 | **0.080471** | 0.078611 |

**A THIRD corpus reproduces the ordering.** The S86 screen side is a different capture
(Kalshi in-play ticks, all periods, dead clock included) from S92's two Polymarket
checkpoint corpora, and on it the order is again
`market 0.078611 < recal_null 0.078930 < ladder_base 0.080471`. Only the ORDERING
transfers: the Brier LEVELS are not comparable across these corpora (S92 excludes
dead-clock ticks by construction, S86 does not), so no level is quoted across them.

## Tests (per-file only)

    python -m pytest tests/platformkit/foundry/test_ingame_screen_nba.py -q                 # 8 passed
    python -m pytest scripts/platformkit/eval_gate/test_ingame_calibration_report.py -q     # 5 passed

New: `test_the_default_incumbent_is_byte_identical_to_the_screen_before_the_option`
(frame equality, CSV equality, no added column on the default path, `BAR == 0.004`, an
unknown name raises); `test_recal_null_anchor_reproduces_s94s_global_recalibration` (on a
synthetic S86-shaped frame whose line is miscalibrated by a KNOWN 0.7 logit shrink: the
anchor matches an INDEPENDENT restatement -- raw sklearn, the fold rule rewritten inside
the test -- to `max |diff| < 1e-12` on every row, the seed block's rows are absent, and
the anchor's Brier beats the raw market's, i.e. the known shrink is recovered);
`test_ladder_base_anchor_is_out_of_fold_and_finite`; and
`test_nba_block_records_the_three_arms_with_bins_and_the_informative_triple` (each arm's
Brier equals a directly computed mean squared error to 1e-12, the bins sum to n, the S87
triple is present on both model arms, and the block reproduces the known ordering).

## A5 -- every reader of what the diff touches

`load_screen` callers: `foundry/run_ingame_screen.py:58` (`nba.load_screen()`),
`eval_gate/s101_aci_coverage.py:194` and `eval_gate/s114_ingame_ensemble.py:277`
(`load_screen(n_folds=N_FOLDS)`). All three call it with no `incumbent`, so all three keep
the default market anchor -- the change is a keyword with a no-op default (B2).
`s94`/`s96`/`s97`/`s98`/`s103`/`s115` define their OWN `load_screen`; none imports this
one. `build_ingame_report` has exactly one other caller, this module's own MLB `main()`,
which is unchanged. The `write_meta` additions are two NEW keys in an
`INSERT OR REPLACE` key/value table -- additive, no rename, no removal.

## NOT VERIFIED

* **Part (b) is untouched and stays OPEN.** Nothing in the answer layer was changed, and
  this memo makes no recommendation about what it should say.
* **The option has ZERO production callers.** No published screen was regenerated on
  `recal_null` or `ladder_base`; the table above is a descriptive one-off measurement of
  the anchors themselves, not a re-run of any hypothesis sweep.
* **No candidate was re-screened against the new anchors.** Whether the 576 S102
  hypotheses behave differently under `ladder_base` is UNMEASURED.
* The three corpora are three capture windows of two venues, all NBA. The ordering is
  reproduced three times but this is one sport and no AHEAD is claimed: **SINGLE-WINDOW**.
* Brier LEVELS are not comparable across the S92 and S86 corpora (different tick
  populations); only the within-corpus ordering is.
* `ladder_base` rebuilds the ladder's `p0` from the game's first price in THIS corpus,
  which is the ladder's own rule but on a different tick stream than
  `nba_checkpoints_full.parquet`. It is the ladder's BASE construction, not a bit-for-bit
  replay of the ladder's own fitted numbers.
* The seed-block drop makes an option run a strictly smaller corpus than the default; a
  future screen comparing across anchors must re-run the default on the same rows.
* Lane's own report; no verifier re-run.

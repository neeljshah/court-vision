# S121 -- the in-game screen/verdict partition, moved from the TICKER to the TICK

Date: 2026-09-03 | Area: signals-ingame | Verdict: **PREMISE CONFIRMED + FIXED ADDITIVELY;
all 14 MLB and both soccer verdicts UNCHANGED (SCREEN_NULL, 0 of 14 clear the +0.004 bar)**
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked in section 6).
Calibration language only (Q6). Uncharged: no prereg sealed, K never read, ledger never opened.

---

## 0. STEP 0 PREMISE (Q8) -- re-measured first, CONFIRMED

### 0a. The partition function, exactly as it stood

`scripts/platformkit/foundry/ingame_screen.py:127-132` builds ONE state per TICKER, stamped
with that ticker's game-first date:

```python
def partition(rows: pd.DataFrame, seed: int = SEED):
    """SF-1 sides over the SCORED games. Ticks are not in the foundry hash partition, so this
    is the spec's game-first-date ISO-week rule (tiers.partition_corpus, basis iso_week)."""
    states = [{"game_id": game, "state_ts": "%sT12:00:00" % date}
              for game, date in sorted(rows.groupby("game")["game_date"].min().items())]
    return partition_corpus(states, seed=seed)
```

`tiers._block` turns that stamp into `"%04d-W%02d" % isocalendar()`, `partition_corpus`
alternates the sorted blocks (`assign = (index + seed) % 2`, seed 0), and `run()` then took
**every tick of a screen-side ticker**:

```python
side = rows[rows["game"].isin(part.screen_ids)].reset_index(drop=True)
```

The unit assigned is the ticker; the unit scored is the tick. A Kalshi ticker parks several
nights under one key (S105/S106), so the two units disagree whenever a ticker's ticks outlive
its own ISO week.

### 0b. Reproducing 495 / 15,702 from the S82 archive

Source: `data/cache/eval_gate/s82_ingame_screen_series_2026-09-03.csv` (219,828 rows = 14
features x 15,702 ticks; **15,702 unique `tick_index` over 41 tickers**, matching the S119
header and the S82 report's own `n_ticks`).

| measured on the archive | value |
|---|---|
| unique scored screen ticks | **15,702** over 41 tickers |
| ISO week of every ticker's first tick | **2026-W27 for 41 of 41** (the screen block) |
| ISO week of the ticks themselves | 2026-W27 **15,207** / 2026-W28 **495** |
| the 495, by date | 2026-07-06 **344**, 2026-07-07 **151** |
| tickers contributing them | **4** |

**495 of 15,702 (3.15 pct) of the S82 screen ticks are dated in the VERDICT week. Premise
CONFIRMED.** 2026-07-06 is the Monday that opens 2026-W28; the S82 partition's verdict side is
exactly that week (`s82_ingame_screen_2026-09-03.json`, `n_verdict_games` 86).

### 0c. The reverse leak (verdict-side ticks dated in a screen week): **ZERO**

Measured on the whole raw store, not the archive (`hedge_trial_arms.load_corpus` +
`ingame_replay_scoreboard.discover_store`, 52,558 ticks over 178 tickers). Cross-week ticks,
by (ticker week -> tick week):

| ticker week | tick week | ticks |
|---|---|---|
| 2026-W26 | 2026-W27 | 188 |
| 2026-W27 | 2026-W28 | **495** |

**Nothing runs backwards.** The reason is structural, not lucky: `stacker._first_dates` sets a
ticker's date to the minimum date of its OWN ticks, so no tick can predate its ticker's block;
the leak is one-directional by construction. The verdict side here is the last block (W28), and
its forward spill would be W29, which the corpus does not reach (`ts_max` 2026-07-12T23:02:46Z).
So the reverse count is 0 and the whole defect sits on the screen side.

The tier did **not** already partition at tick level, so the row does not fire FALSIFIED.

---

## 1. The change (smallest additive)

New module `scripts/platformkit/foundry/tick_partition.py` (96 lines), because
`ingame_screen.py` was at 286 of its 300-line rail:

* `partition_mode(mode=None)` -- explicit argument beats `FOUNDRY_INGAME_PARTITION` beats the
  frozen default **`ticker_week`**. An unknown mode raises rather than silently defaulting.
* `tick_partition(rows, seed=0, state_summary=None)` -- one state per TICK, handed to the SAME
  frozen `tiers.partition_corpus` ISO-week rule. No new block rule was written and **no bar,
  seed or threshold was touched** (Q3/B10: `BAR` is still 0.004, `SEED` still 0).
* `screen_side(rows, part, mode=..., state_summary=...)` -- returns the screen-side rows plus a
  `tick_grain` meta block. In `tick_week` it asserts (i) no tick lands on both sides, (ii) no
  tick lands on neither, and (iii) with `state_summary`, that **no REAL GAME (S106
  `real_game_split`) contributes to both sides**.
* **The real-game purge.** A tick is blocked by the first tick of its own real game, not by its
  own stamp, so a real game that runs past midnight into the next ISO week is never cut in half.
  This is what makes assertion (iii) hold rather than merely be checked.

`ingame_screen.run()` now takes an optional `mode` and calls `screen_side` with the ticks' own
`state_summary`; `ingame_screen_soccer.run()` takes the same `mode` but passes
`state_summary=None` and says so in its meta (`real_game_purged: false`) -- `real_game_split`'s
boundary rules are inning-based, so a soccer summary parses to `inning=None` and no purge is
claimed that did not happen.

**Additive only (B2):** the default path is byte-identical to S82/S117 -- the reports gain one
new key, `partition.tick_grain`; nothing was renamed or removed. A5 sweep of every reader of the
touched artifacts (`s106_requote.py:88-105`, `run_ingame_screen.py:38`,
`ingame_screen_soccer.py:271-276`, `test_ingame_screen.py:101-102`) shows all of them read
`results`, `corpus`, `partition["basis"]` or `partition["n_screen_games"]` -- none is affected.

Per-file tests (both new, both green):

```
python -m pytest tests/platformkit/foundry/test_tick_partition.py -q     # 5 passed
python -m pytest tests/platformkit/eval_gate/test_s121_requote.py -q     # 4 passed
```

They cover the row's two named cases -- a ticker spanning two ISO weeks (the default keeps all
4 of its ticks; `tick_week` keeps 2) and tick-level disjointness/exhaustiveness -- plus the
past-midnight real game kept whole and the env-var/unknown-mode behaviour. Regression, all green:
`test_ingame_screen.py` 6 passed, `test_ingame_screen_soccer.py` 4 passed,
`test_ingame_screen_nba.py` 5 passed, `test_ingame_supply_mlb.py` 4 passed,
`test_s114_ingame_ensemble.py` 7 passed.

---

## 2. The re-quote -- from the archives, NO refit

`scripts/platformkit/eval_gate/s121_requote.py` ->
`data/cache/eval_gate/s121_requote_2026-09-03.json`.

`p_null` and `p_candidate` are the ARCHIVED walk-forward predictions. The tick-clean side is a
strict SUBSET of the archived rows, so no model is refitted and no probability recomputed.
Unlike S119's real-game re-quote (which moved only intervals), **the point estimates DO move
here, because the denominator changes** -- that is the whole finding, and it is stated rather
than hidden.

**A2 reproduction.** Recomputed from the series alone, this script reproduces S119's published
real-game table to **0.00e+00** and S119's `calendar_clean_sensitivity` table to **0.00e+00**
(max |improvement difference| over all 14 features, both).

### 2a. Two clean sides, and why the headline is the purged one

| side | rule | n ticks | n tickers | n real games | leader `tick_index_in_game` |
|---|---|---|---|---|---|
| S82 as published | every tick of a W27 ticker | 15,702 | 41 | 88 | +0.003332 |
| naive tick-own-week | drop every tick dated in W28 | 15,207 | 41 | 85 | +0.001628 |
| **`tick_week` + S106 purge (HEADLINE)** | block each tick by its REAL GAME's first tick | **15,336** | 41 | **85** | **+0.001951** |

The 366 vs 495 gap is one real game: **`KXMLBGAME-26JUL051920SDLAD#3`** ran
2026-07-05T23:21:25Z -> 2026-07-06T02:27:09Z, so 129 of its 173 ticks carry a W28 date while the
game itself began in the screen week. The naive rule cuts that game in half; the purged rule
keeps it whole and drops only the **3 real games that lie entirely in W28 (366 ticks)**. The
naive column is kept in the artifact as the S119 cross-check, not as the headline.

### 2b. S82's 14-feature table, old vs tick-clean (bar +0.004, frozen)

CIs are the real-game-clustered DM intervals (S106 clusters, the S119 unit).

| feature | n old | n new | n_eff old | n_eff new | impr old | impr new | CI95 real-game old | CI95 real-game new | verdict |
|---|---|---|---|---|---|---|---|---|---|
| `tick_index_in_game` | 15,702 | 15,336 | 120.7 | 119.8 | +0.003332 | +0.001951 | [-0.003705, +0.010370] | [-0.004516, +0.008417] | SCREEN_NULL (unchanged) |
| `leverage_proxy` | 15,702 | 15,336 | 388.3 | 379.7 | +0.001148 | +0.001202 | [-0.000219, +0.002515] | [-0.000195, +0.002599] | SCREEN_NULL (unchanged) |
| `times_through_order` | 15,702 | 15,336 | 1849.9 | 1775.4 | +0.001063 | +0.001036 | [-0.000728, +0.002854] | [-0.000787, +0.002860] | SCREEN_NULL (unchanged) |
| `pitch_tempo_seconds` | 15,702 | 15,336 | 419.1 | 404.8 | +0.000651 | +0.000667 | [-0.000612, +0.001914] | [-0.000627, +0.001961] | SCREEN_NULL (unchanged) |
| `pitch_count` | 15,702 | 15,336 | 1857.1 | 1753.5 | +0.000612 | +0.000606 | [-0.000565, +0.001789] | [-0.000590, +0.001802] | SCREEN_NULL (unchanged) |
| `balls` | 15,702 | 15,336 | 1204.4 | 1131.9 | +0.000203 | +0.000218 | [-0.000238, +0.000645] | [-0.000231, +0.000667] | SCREEN_NULL (unchanged) |
| `strikes` | 15,702 | 15,336 | 2026.9 | 1957.6 | +0.000005 | +0.000016 | [-0.000244, +0.000253] | [-0.000238, +0.000270] | SCREEN_NULL (unchanged) |
| `outs` | 15,702 | 15,336 | 4240.6 | 4095.1 | -0.000010 | -0.000012 | [-0.000322, +0.000301] | [-0.000331, +0.000307] | SCREEN_NULL (unchanged) |
| `score_change_recency` | 15,702 | 15,336 | 280.1 | 287.3 | -0.000241 | -0.000281 | [-0.000518, +0.000037] | [-0.000553, -0.000009] | SCREEN_NULL (unchanged) |
| `base_out_state` | 15,702 | 15,336 | 1616.9 | 1620.6 | -0.000315 | -0.000283 | [-0.001109, +0.000479] | [-0.001085, +0.000519] | SCREEN_NULL (unchanged) |
| `inning_progress` | 15,702 | 15,336 | 456.7 | 453.4 | -0.000268 | -0.000343 | [-0.001385, +0.000848] | [-0.001476, +0.000790] | SCREEN_NULL (unchanged) |
| `base_state` | 15,702 | 15,336 | 846.9 | 809.4 | -0.000479 | -0.000450 | [-0.001335, +0.000377] | [-0.001314, +0.000415] | SCREEN_NULL (unchanged) |
| `run_expectancy` | 15,702 | 15,336 | 1536.9 | 1465.9 | -0.000438 | -0.000462 | [-0.001304, +0.000427] | [-0.001346, +0.000422] | SCREEN_NULL (unchanged) |
| `score_diff` | 15,702 | 15,336 | 144.3 | 138.8 | -0.018007 | -0.017895 | [-0.038664, +0.002650] | [-0.039051, +0.003262] | SCREEN_NULL (unchanged) |

**0 of 14 clear the +0.004 bar on either side. Every verdict is unchanged.** The leak was
never load-bearing for a verdict; it was load-bearing for the leader's HEADLINE NUMBER, which
falls 41 pct (+0.003332 -> +0.001951) and whose interval still spans zero.

**One honest re-label inside the non-finding:** `score_change_recency`'s real-game CI moves from
[-0.000518, +0.000037] to [-0.000553, -0.000009] -- it now excludes zero on the NEGATIVE side,
i.e. the feature measurably *hurts* the recalibrated null. That is a bar the feature fails
harder, not a discovery; the verdict stays SCREEN_NULL.

### 2c. S117 soccer -- the archive allows the check, and it changes nothing

| arm | n ticks | n games | tick weeks | ticker weeks | dropped | table |
|---|---|---|---|---|---|---|
| headline (train floor 1000) | 163 | 2 | 2026-W28 | 2026-W28 | **0** | **unchanged** |
| mintrain200 (SENSITIVITY) | 825 | 8 | 2026-W28 | 2026-W28 | **0** | **unchanged** |

Both S117 archives sit entirely inside ONE ISO week, so there is no boundary to cross and the
tick-clean partition is the identity. Reported as a measured null, not skipped: every
improvement, CI and verdict is byte-identical (`n_clearing_bar_new` 0 for both arms).

---

## 3. What this does NOT claim

* No edge, ROI or dollar language anywhere; a SCREEN is a non-finding and stays one (Q6).
* No charge: no prereg seal, no `_charge_ledger` call, K never read (the module chain imports
  nothing from `backtest_runner`). The FWER ledger still has 18 rows.
* The `tick_week` mode is **opt-in**. The default remains `ticker_week`, so S82 and S117 remain
  reproducible byte-for-byte and no published artifact was overwritten.
* Nothing was re-run on the corpus: section 2 is a re-quote of archived paired losses.

## 4. Files

| path | role |
|---|---|
| `scripts/platformkit/foundry/tick_partition.py` | the mode, the tick partition, the asserts |
| `scripts/platformkit/foundry/ingame_screen.py` | `run()` uses `screen_side`; reports `partition.tick_grain` |
| `scripts/platformkit/foundry/ingame_screen_soccer.py` | same, `state_summary=None` (no purge claimed) |
| `scripts/platformkit/eval_gate/s121_requote.py` | the archive-only re-quote |
| `tests/platformkit/foundry/test_tick_partition.py` | 5 tests |
| `tests/platformkit/eval_gate/test_s121_requote.py` | 4 tests |
| `data/cache/eval_gate/s121_requote_2026-09-03.json` | the artifact (local, gitignored) |

## 5. Reproduce

```
python -m scripts.platformkit.eval_gate.s121_requote
python -m pytest tests/platformkit/foundry/test_tick_partition.py -q
python -m pytest tests/platformkit/eval_gate/test_s121_requote.py -q
FOUNDRY_INGAME_PARTITION=tick_week python -m scripts.platformkit.foundry.run_ingame_screen
```

## 6. Contract self-check (sections B and Q)

| rule | status |
|---|---|
| B1 circular metric | NO -- the excluded set is named exactly (366 ticks = 3 W28-only real games) and its complement is quoted beside it |
| B2 non-additive schema | NO -- `partition.tick_grain` added; no key renamed or removed; all 4 readers swept (A5) |
| B3 fall-through loss | NO -- a single-block archive is REPORTED (`single_block: true`), not quarantined; soccer with no inning state claims no purge |
| B4 re-claim loop | N/A -- a screen is a non-finding and claims nothing |
| B5 pre-verification deploy | NO -- no pod contact, no file copied |
| B6 orphans | NO -- nothing moved or retired; both new modules have a per-file test |
| B7 head-slice evidence | NO -- the whole 15,702-tick archive is used; the 495 are counted by date over all of it |
| B8 self-fit as independent | N/A -- no fit; archived predictions only |
| B9 degenerate denominator | NO -- the unit is the real game (85), the S106-corrected cluster, and n_eff is reported per feature |
| B10 moved bar | NO -- BAR 0.004 and SEED 0 byte-identical to master |
| Q1 prereg sealed | N/A -- uncharged screen re-quote, no scored claim |
| Q2 ledger charged first | N/A -- no charge; `_charge_ledger` never reachable from this chain |
| Q3 no bar moved | PASS -- 0.004 everywhere |
| Q4 leak contract via CPCV | N/A here -- no new fit; the archived predictions came from S82's purged walk-forward, and this row REMOVES a leak from that contract rather than adding one |
| Q5 two corpora for an AHEAD | N/A -- no AHEAD; every verdict is SCREEN_NULL |
| Q6 calibration language only | PASS -- no dollar/ROI/edge language; no retracted figure appears |
| Q7 sampling rail scope | PASS -- n = 15,336 SCORED ticks over 85 real games; the 4 leaking tickers are an exhaustive CONSTRUCT enumeration |
| Q8 premise first | PASS -- section 0, CONFIRMED, with the reverse leak measured at 0 |
| Q9 archive the differential | PASS -- the artifact carries `table_old`, `table_new` and `table_naive_tick_week` per feature, all recomputable from `s82_ingame_screen_series_2026-09-03.csv` alone |
